# backends/_streaming_mixin.py
#
# Shared setpoint-streaming implementation for Feetech-class servo backends
# (STS3215, HLS3950).  Both drivers are near-identical copies, so the pacing
# logic lives here and is mixed into each backend class.
#
# Sprint 10 — Smooth Streaming Executor.

import math
import threading
import time
from typing import Optional

from ..motion_handle import MotionHandle


# Streaming constants (from Sprint 07 bench data)
PACING_FREQUENCY_HZ = 100  # fast moves
SLOW_PACING_FREQUENCY_HZ = 33  # slow moves — larger goal steps, no micro-vibration
LOOKAHEAD_S = 0.100  # 100 ms — more profile distance for the firmware to smooth over velocity discontinuities
STREAMING_ACCEL = 10  # bench-safe recipe (Sprint 01)
CAP_MIN = 60  # minimum speed register value; lowered from 150 to reduce overshoot-stall on slow moves
CAP_MAX = 2000
CAP_FLOOR = 60  # firmware hard floor is 50 LSB (4.4 deg/s); 60 gives slight torque authority through backlash
CAP_MULTIPLIER = 1.2  # 1.2x path velocity demand — servo tracks stream without racing ahead
CAP_SCALE_LSB_PER_DEG_S = 1.0 / 0.088  # 0x2E LSB ≈ 0.088 deg/s
RESUME_DRIFT_THRESHOLD_RAD = 0.1  # ~5.7 deg, about 2x typical 50ms lookahead travel

# Interleaved read: do a position read every N milliseconds to give the UI
# live position feedback.  Time-based (not cycle-based) so the read rate is
# consistent regardless of pacing frequency.  The read happens after the
# write, inside the pacing loop — no second thread touches the bus.
READ_INTERVAL_S = 0.100  # 10 Hz position feedback

# Slow move threshold: if the fastest joint's velocity demand is below this,
# use the slow pacing frequency (larger goal steps, eliminates micro-vibration
# from tiny goal deltas quantizing in the servo's 12-bit encoder).
SLOW_MOVE_THRESHOLD_DEG_S = 50.0


class StreamingMixin:
    """
    Mixin providing ``supports_setpoint_streaming`` and ``execute_timed_path``
    for Feetech-class servo backends.

    The pacing thread:
      1. Computes per-joint velocity caps from the path (max |Δq/Δt| × 2)
      2. Writes accel=10 once before the stream starts
      3. Paces at 100 Hz, writing position(t_now + 50ms lookahead) via sync_write
      4. Clamps every goal to the path's own min/max per joint (stream guard)
      5. Stops writing when t > path_end (horizon rule)
      6. On cancel: writes current position as goal (servo decelerates over horizon)
      7. On pause: stops feeding goals, holds position
      8. On resume: re-derives nearest path t from sync_read, resumes streaming
    """

    @property
    def supports_setpoint_streaming(self) -> bool:
        """True — setpoint streaming is supported (Sprint 10).

        Can be disabled via robot config ``streaming_enabled: False``.
        """
        if hasattr(self, '_streaming_disabled') and self._streaming_disabled:
            return False
        return True

    def _set_streaming_config(self, robot_config: dict) -> None:
        """Read streaming config from robot config dict. Call from __init__."""
        self._streaming_disabled = not robot_config.get('streaming_enabled', True)

    def execute_timed_path(
        self,
        path: list[tuple[float, list[float]]],
        options: Optional[dict] = None,
    ) -> MotionHandle:
        """Execute a timed path as a continuous setpoint stream.

        See ActuatorBackend.execute_timed_path for full docs.
        """
        if not path:
            raise ValueError("execute_timed_path: empty path")

        options = options or {}
        num_joints = self.num_joints
        n = len(path)

        # Validate path
        for i, (t, q) in enumerate(path):
            if len(q) != num_joints:
                raise ValueError(
                    f"execute_timed_path: sample {i} has {len(q)} joints, "
                    f"expected {num_joints}"
                )

        # Compute per-joint path bounds (stream guard)
        path_min = [float('inf')] * num_joints
        path_max = [float('-inf')] * num_joints
        for _, q in path:
            for j in range(num_joints):
                if q[j] < path_min[j]:
                    path_min[j] = q[j]
                if q[j] > path_max[j]:
                    path_max[j] = q[j]

        # Compute per-joint velocity caps from path
        caps = self._compute_velocity_caps(path, options)

        # Accel override
        accel = int(options.get('accel_override', STREAMING_ACCEL))

        # Create handle
        handle = MotionHandle()
        handle._set_cancel_callback(
            lambda: self._cancel_stream(handle, path, path_min, path_max, caps, accel)
        )

        # Start pacing thread
        thread = threading.Thread(
            target=self._pacing_loop,
            args=(handle, path, path_min, path_max, caps, accel, options),
            daemon=True,
        )
        handle._set_thread(thread)
        thread.start()

        return handle

    def _compute_velocity_caps(
        self,
        path: list[tuple[float, list[float]]],
        options: Optional[dict],
    ) -> list[int]:
        """Compute per-joint speed register values from path velocity demand.

        cap = max|Δq/Δt| over the path × CAP_MULTIPLIER, clamped [CAP_MIN, CAP_MAX].
        Units: 0x2E LSB via Part A scale (0.088 deg/s per LSB).
        """
        num_joints = self.num_joints
        overrides = options.get('velocity_caps') if options else None

        if overrides and len(overrides) == num_joints:
            return [max(CAP_FLOOR, min(CAP_MAX, int(c))) for c in overrides]

        max_vel_rad_s = self._compute_max_velocities(path)

        caps = []
        for j in range(num_joints):
            v_deg_s = math.degrees(max_vel_rad_s[j])
            cap_lsb = int(v_deg_s * CAP_SCALE_LSB_PER_DEG_S * CAP_MULTIPLIER)
            cap_lsb = max(CAP_MIN, min(CAP_MAX, cap_lsb))
            if cap_lsb < CAP_FLOOR:
                cap_lsb = CAP_FLOOR
            caps.append(cap_lsb)
        return caps

    def _compute_max_velocities(
        self,
        path: list[tuple[float, list[float]]],
    ) -> list[float]:
        """Compute the maximum per-joint velocity (rad/s) over the path."""
        num_joints = self.num_joints
        max_vel_rad_s = [0.0] * num_joints
        for i in range(1, len(path)):
            t_prev, q_prev = path[i - 1]
            t_curr, q_curr = path[i]
            dt = t_curr - t_prev
            if dt <= 0:
                continue
            for j in range(num_joints):
                v = abs(q_curr[j] - q_prev[j]) / dt
                if v > max_vel_rad_s[j]:
                    max_vel_rad_s[j] = v
        return max_vel_rad_s

    def _interpolate_path(
        self,
        path: list[tuple[float, list[float]]],
        t_target: float,
    ) -> list[float]:
        """Linear interpolation between path samples at time t_target."""
        n = len(path)
        if t_target <= path[0][0]:
            return list(path[0][1])
        if t_target >= path[-1][0]:
            return list(path[-1][1])

        # Binary search for the interval
        lo, hi = 0, n - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if path[mid][0] <= t_target:
                lo = mid
            else:
                hi = mid

        t0, q0 = path[lo]
        t1, q1 = path[hi]
        dt = t1 - t0
        if dt <= 0:
            return list(q1)

        alpha = (t_target - t0) / dt
        return [
            q0[j] + alpha * (q1[j] - q0[j])
            for j in range(len(q0))
        ]

    def _clamp_to_path_bounds(
        self,
        q: list[float],
        path_min: list[float],
        path_max: list[float],
    ) -> list[float]:
        """Clamp each joint to the path's own min/max (stream guard)."""
        return [
            max(path_min[j], min(path_max[j], q[j]))
            for j in range(len(q))
        ]

    def _cancel_stream(
        self,
        handle: MotionHandle,
        path: list[tuple[float, list[float]]],
        path_min: list[float],
        path_max: list[float],
        caps: list[int],
        accel: int,
    ) -> None:
        """Write current position as goal to stop the arm in place."""
        try:
            raw = self.sync_read_positions(timeout_s=0.05)
            if raw:
                current_q = self.raw_to_joint_positions(raw)
                current_q = self._clamp_to_path_bounds(current_q, path_min, path_max)
                commands = self._prepare_streaming_commands(
                    current_q, caps, accel,
                )
                self.sync_write(commands)
        except Exception:
            pass

    def _prepare_streaming_commands(
        self,
        positions_rad: list[float],
        caps: list[int],
        accel: int,
    ) -> list[tuple]:
        """Build sync_write commands with per-joint speed caps.

        Unlike ``prepare_sync_write_commands`` which uses a single speed for
        all servos, this method uses the per-joint velocity caps computed
        from the path.  This prevents low-velocity joints from aggressively
        chasing across backlash gaps at 100 Hz, which causes hunt oscillation
        on J1/J2 (the high-backlash joints).
        """
        commands = []
        for logical_idx, physical_indices in self._logical_to_physical_map.items():
            angle_with_offset = (
                positions_rad[logical_idx] + self._master_offsets_rad[logical_idx]
            )
            speed_reg = caps[logical_idx] if logical_idx < len(caps) else max(caps)

            for physical_idx in physical_indices:
                servo_id = self._servo_ids[physical_idx]
                if servo_id not in self._present_servo_ids:
                    continue
                raw_pos = self._angle_to_raw(angle_with_offset, physical_idx)
                commands.append((servo_id, raw_pos, speed_reg, accel))
        return commands

    def _pacing_loop(
        self,
        handle: MotionHandle,
        path: list[tuple[float, list[float]]],
        path_min: list[float],
        path_max: list[float],
        caps: list[int],
        accel: int,
        options: dict,
    ) -> None:
        """The pacing thread that streams lookahead setpoints.

        Uses variable pacing: 100 Hz on fast moves, 33 Hz on slow moves.
        Slower pacing on slow moves gives each goal a larger step size,
        eliminating the micro-vibration from tiny goal deltas quantizing
        in the servo's 12-bit encoder / 0.088 deg/s speed resolution.

        Interleaves a position read every 100 ms (time-based, not cycle-based)
        after the write, so the UI gets live position feedback at 10 Hz
        without a second thread competing for the bus.
        """
        # Determine pacing frequency from path velocity
        max_vel_deg_s = max(
            math.degrees(v) for v in self._compute_max_velocities(path)
        )
        if max_vel_deg_s < SLOW_MOVE_THRESHOLD_DEG_S:
            period = 1.0 / SLOW_PACING_FREQUENCY_HZ
            print(f"[Streaming] Slow move ({max_vel_deg_s:.1f} deg/s) → pacing at {SLOW_PACING_FREQUENCY_HZ} Hz")
        else:
            period = 1.0 / PACING_FREQUENCY_HZ
            print(f"[Streaming] Fast move ({max_vel_deg_s:.1f} deg/s) → pacing at {PACING_FREQUENCY_HZ} Hz")

        path_end = path[-1][0]
        start_time = time.monotonic()

        # Write accel once per move
        try:
            first_q = self._interpolate_path(path, path[0][0])
            first_q = self._clamp_to_path_bounds(first_q, path_min, path_max)
            commands = self._prepare_streaming_commands(
                first_q, caps, accel,
            )
            self.sync_write(commands)
        except Exception as e:
            print(f"[Streaming] ERROR on initial write: {e}")
            handle._mark_done()
            return

        # Import utils for live position updates
        utils_ref = None
        try:
            from .. import utils as utils_ref
        except ImportError:
            pass

        cycle = 0
        last_read_time = 0.0
        try:
            while not handle._should_stop():
                # Handle pause
                if handle.is_paused():
                    handle._wait_for_resume()
                    if handle._should_stop():
                        break
                    start_time = self._resume_from_current(
                        handle, path, path_min, path_max, caps, accel
                    )
                    if start_time is None:
                        handle._mark_done()
                        return
                    last_read_time = 0.0  # force a read on resume

                t_now = time.monotonic() - start_time
                t_lookahead = t_now + LOOKAHEAD_S

                # Horizon rule: stop writing when t > path_end
                if t_now > path_end:
                    final_q = self._clamp_to_path_bounds(
                        list(path[-1][1]), path_min, path_max
                    )
                    try:
                        commands = self._prepare_streaming_commands(
                            final_q, caps, accel,
                        )
                        self.sync_write(commands)
                    except Exception:
                        pass
                    break

                # Write lookahead goal
                goal_q = self._interpolate_path(path, t_lookahead)
                goal_q = self._clamp_to_path_bounds(goal_q, path_min, path_max)

                try:
                    commands = self._prepare_streaming_commands(
                        goal_q, caps, accel,
                    )
                    self.sync_write(commands)
                except Exception as e:
                    if cycle < 5:
                        print(f"[Streaming] Write error at cycle {cycle}: {e}")

                # Interleaved position read: DISABLED for diagnostic — the 20ms
                # read timeout eats 2 pacing periods at 100Hz and nearly the full
                # period at 33Hz, causing write timing jitter that manifests as
                # motion twitch on slow moves. Comment out the next 3 lines to
                # re-enable for GUI position feedback.
                # now = time.monotonic()
                # if now - last_read_time >= READ_INTERVAL_S:
                #     last_read_time = now
                #     try:
                #         raw = self.sync_read_positions(timeout_s=0.02)
                #         if raw:
                #             read_q = self.raw_to_joint_positions(raw)
                #             if utils_ref is not None:
                #                 utils_ref.current_logical_joint_angles_rad = list(read_q)
                #     except Exception:
                #         pass

                # Pace — single sleep for the full period
                cycle += 1
                sleep_until = start_time + cycle * period
                sleep_t = sleep_until - time.monotonic()
                if sleep_t > 0:
                    time.sleep(sleep_t)

        except Exception as e:
            print(f"[Streaming] Pacing loop error: {e}")
        finally:
            handle._mark_done()

    def _resume_from_current(
        self,
        handle: MotionHandle,
        path: list[tuple[float, list[float]]],
        path_min: list[float],
        path_max: list[float],
        caps: list[int],
        accel: int,
    ) -> Optional[float]:
        """Re-derive nearest path timestamp from current servo position.

        Returns a new start_time for the pacing loop, or None if resume
        is not possible.
        """
        try:
            raw = self.sync_read_positions(timeout_s=0.05)
            if not raw:
                # Can't read — resume from path start as fallback
                return time.monotonic() - path[0][0]
            current_q = self.raw_to_joint_positions(raw)

            # Find nearest path timestamp by minimum joint-space distance
            best_t = path[0][0]
            best_dist = float('inf')
            for t, q in path:
                dist = sum(
                    (current_q[j] - q[j]) ** 2
                    for j in range(min(len(current_q), len(q)))
                )
                if dist < best_dist:
                    best_dist = dist
                    best_t = t

            # Check drift
            drift = math.sqrt(best_dist)
            if drift > RESUME_DRIFT_THRESHOLD_RAD:
                # Large drift: execute a short profiled segment to nearest point
                nearest_q = self._interpolate_path(path, best_t)
                nearest_q = self._clamp_to_path_bounds(nearest_q, path_min, path_max)
                if hasattr(self, 'plan_profiled_segment'):
                    try:
                        commands = self.plan_profiled_segment(current_q, nearest_q)
                        self.sync_write(commands)
                        time.sleep(0.2)  # brief wait for the profiled segment
                    except Exception:
                        pass

            # Resume streaming from best_t: set start_time so that
            # t_now = best_t at the current monotonic time
            return time.monotonic() - best_t

        except Exception as e:
            print(f"[Streaming] Resume error: {e}")
            return time.monotonic() - path[0][0]