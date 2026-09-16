# backends/simulation/backend.py
#
# Simulation backend for GradientOS.
# Provides an in-memory simulation of the actuator system for development and testing.

from typing import Optional, TYPE_CHECKING
import math
import os
import threading
import time
import numpy as np

from ..registry import get_encoder_resolution
from ...actuator_interface import ActuatorBackend
from ...motion_handle import MotionHandle

if TYPE_CHECKING:
    from ...robots.base import RobotConfig


class SimulationBackend(ActuatorBackend):
    """
    In-memory simulation backend for development and testing.
    
    This backend simulates the behavior of physical actuators without requiring
    actual hardware. It's useful for:
    - Development and debugging of motion planning algorithms
    - Testing trajectory execution logic
    - Running the controller UI without a physical robot
    
    The simulation maintains joint positions in radians internally and converts
    to/from raw encoder values as needed to match the interface expected by
    other parts of the system.
    """
    
    def __init__(
        self,
        robot_config: Optional[dict] = None,
        num_joints: Optional[int] = None,
        has_gripper: Optional[bool] = None,
        encoder_resolution: Optional[int] = None,
    ):
        """
        Initialize the simulation backend.
        
        Can be initialized either with a robot_config dict (preferred) or with
        explicit parameters. If robot_config is provided, its values are used
        as defaults, but explicit parameters will override them.
        
        Args:
            robot_config: Optional dict from RobotConfig.get_config_dict() to get parameters from.
            num_joints: Number of logical joints to simulate (default: 6 or from robot_config).
            has_gripper: Whether to simulate a gripper (default: False or from robot_config).
            encoder_resolution: Encoder resolution to simulate (default: 4095 for 12-bit).
        """
        # Get defaults from robot_config if provided
        if robot_config is not None:
            if isinstance(robot_config, dict):
                default_num_joints = robot_config.get('num_logical_joints', 6)
                default_has_gripper = robot_config.get('has_gripper', False)
            else:
                # Assume it's a RobotConfig object with attributes
                default_num_joints = robot_config.num_logical_joints
                default_has_gripper = robot_config.has_gripper
        else:
            # No robot config provided - require explicit parameters
            if num_joints is None:
                raise ValueError("SimulationBackend requires either robot_config or explicit num_joints parameter")
            default_num_joints = num_joints
            default_has_gripper = False
        
        # For encoder resolution, get from the active servo backend via registry
        try:
            default_encoder_resolution = get_encoder_resolution()
        except Exception:
            default_encoder_resolution = 4095  # Fallback to common 12-bit encoder
        
        # Apply overrides
        self._num_joints = num_joints if num_joints is not None else default_num_joints
        self._has_gripper = has_gripper if has_gripper is not None else default_has_gripper
        self._encoder_resolution = encoder_resolution if encoder_resolution is not None else default_encoder_resolution
        self._encoder_center = self._encoder_resolution // 2
        
        self._robot_config = robot_config
        self._positions = [0.0] * self._num_joints
        self._gripper_position = 0.0
        self._raw_positions: dict[int, int] = {}

        if self._robot_config:
            self._actuator_ids = list(self._robot_config.get("actuator_ids", []))
            raw_l2p = dict(self._robot_config.get("logical_to_physical_map", {}))
            self._logical_to_physical = {
                int(logical_idx): [int(physical_idx) for physical_idx in physical_indices]
                for logical_idx, physical_indices in raw_l2p.items()
            }
            self._mapping_ranges = list(self._robot_config.get("actuator_mapping_ranges_rad", []))
            self._inverted_actuator_ids = set(self._robot_config.get("inverted_actuator_ids", set()))
            self._master_offsets = list(
                self._robot_config.get(
                    "logical_joint_master_offsets_rad",
                    [0.0] * self._num_joints,
                )
            )
            self._gripper_id = self._robot_config.get("gripper_actuator_id")
        else:
            self._actuator_ids = list(range(self._num_joints))
            self._logical_to_physical = {idx: [idx] for idx in range(self._num_joints)}
            self._mapping_ranges = [(-math.pi, math.pi)] * len(self._actuator_ids)
            self._inverted_actuator_ids = set()
            self._master_offsets = [0.0] * self._num_joints
            self._gripper_id = 100 if self._has_gripper else None

        self._initialize_raw_cache()
        self._initialized = False
    
    def initialize(self) -> bool:
        self._initialized = True
        print(f"[Sim] Simulation backend initialized with {self._num_joints} joints")
        return True
    
    def shutdown(self) -> None:
        self._initialized = False
        print("[Sim] Simulation backend shut down")
    
    @property
    def num_joints(self) -> int:
        return self._num_joints
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    @property
    def encoder_resolution(self) -> int:
        """Returns the configured encoder resolution."""
        return self._encoder_resolution

    # =========================================================================
    # Setpoint Streaming (Sprint 10)
    # =========================================================================

    @property
    def supports_setpoint_streaming(self) -> bool:
        """True — simulation supports setpoint streaming with robust pacing."""
        return True

    def execute_timed_path(
        self,
        path: list[tuple[float, list[float]]],
        options: Optional[dict] = None,
    ) -> MotionHandle:
        """Execute a timed path as a continuous setpoint stream in simulation.

        Mirrors real-hardware behavior: paces at 100 Hz with 50 ms lookahead
        so write frequency, lookahead correctness, cancel timing, pause/resume,
        and horizon expiry are all exercised.

        The ``sim_fast_forward`` option (options dict or SIM_FAST_FORWARD env
        var) skips time.sleep calls for automated tests — positions replay
        instantly but pacing logic still runs.
        """
        if not path:
            raise ValueError("execute_timed_path: empty path")

        options = options or {}
        num_joints = self._num_joints

        # Validate path
        for i, (t, q) in enumerate(path):
            if len(q) != num_joints:
                raise ValueError(
                    f"execute_timed_path: sample {i} has {len(q)} joints, "
                    f"expected {num_joints}"
                )

        # Fast-forward mode
        fast_forward = options.get('sim_fast_forward', False)
        if not fast_forward:
            fast_forward = os.environ.get('SIM_FAST_FORWARD', '0') == '1'

        # Compute path bounds (stream guard)
        path_min = [float('inf')] * num_joints
        path_max = [float('-inf')] * num_joints
        for _, q in path:
            for j in range(num_joints):
                if q[j] < path_min[j]:
                    path_min[j] = q[j]
                if q[j] > path_max[j]:
                    path_max[j] = q[j]

        handle = MotionHandle()

        def _sim_cancel():
            current = list(self._positions[:num_joints])
            clamped = [
                max(path_min[j], min(path_max[j], current[j]))
                for j in range(num_joints)
            ]
            self.set_joint_positions(clamped, speed=4095, acceleration=10)

        handle._set_cancel_callback(_sim_cancel)

        thread = threading.Thread(
            target=self._sim_pacing_loop,
            args=(handle, path, path_min, path_max, fast_forward),
            daemon=True,
        )
        handle._set_thread(thread)
        thread.start()

        return handle

    def _sim_pacing_loop(
        self,
        handle: MotionHandle,
        path: list[tuple[float, list[float]]],
        path_min: list[float],
        path_max: list[float],
        fast_forward: bool,
    ) -> None:
        """Simulation pacing loop — mirrors real hardware at 100 Hz.

        In fast-forward mode, a virtual clock advances by ``period`` each
        cycle instead of using wall-clock time, so a 5-second path completes
        in milliseconds.
        """
        period = 1.0 / 100  # 100 Hz
        lookahead = 0.050  # 50 ms
        path_end = path[-1][0]
        start_time = time.monotonic()
        num_joints = self._num_joints

        # Initial write
        first_q = self._sim_interp(path, path[0][0])
        first_q = self._sim_clamp(first_q, path_min, path_max)
        self.set_joint_positions(first_q, speed=4095, acceleration=10)

        cycle = 0
        try:
            while not handle._should_stop():
                if handle.is_paused():
                    handle._wait_for_resume()
                    if handle._should_stop():
                        break
                    current = list(self._positions[:num_joints])
                    best_t = self._sim_nearest_path_t(path, current)
                    start_time = time.monotonic() - best_t
                    cycle = 0

                if fast_forward:
                    t_now = cycle * period
                else:
                    t_now = time.monotonic() - start_time
                t_lookahead = t_now + lookahead

                if t_now > path_end:
                    final_q = self._sim_clamp(list(path[-1][1]), path_min, path_max)
                    self.set_joint_positions(final_q, speed=4095, acceleration=10)
                    break

                goal_q = self._sim_interp(path, t_lookahead)
                goal_q = self._sim_clamp(goal_q, path_min, path_max)
                self.set_joint_positions(goal_q, speed=4095, acceleration=10)

                cycle += 1
                if not fast_forward:
                    sleep_until = start_time + cycle * period
                    sleep_t = sleep_until - time.monotonic()
                    if sleep_t > 0:
                        time.sleep(sleep_t)

        except Exception as e:
            print(f"[Sim Streaming] Pacing loop error: {e}")
        finally:
            handle._mark_done()

    def _sim_interp(
        self,
        path: list[tuple[float, list[float]]],
        t_target: float,
    ) -> list[float]:
        """Linear interpolation between path samples at time t_target."""
        if t_target <= path[0][0]:
            return list(path[0][1])
        if t_target >= path[-1][0]:
            return list(path[-1][1])

        lo, hi = 0, len(path) - 1
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
        return [q0[j] + alpha * (q1[j] - q0[j]) for j in range(len(q0))]

    def _sim_clamp(
        self,
        q: list[float],
        path_min: list[float],
        path_max: list[float],
    ) -> list[float]:
        return [max(path_min[j], min(path_max[j], q[j])) for j in range(len(q))]

    def _sim_nearest_path_t(
        self,
        path: list[tuple[float, list[float]]],
        current_q: list[float],
    ) -> float:
        """Find the path timestamp nearest to current_q in joint space."""
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
        return best_t
    
    def set_joint_positions(
        self,
        positions_rad: list[float],
        speed: float,
        acceleration: float,
    ) -> None:
        if len(positions_rad) != self._num_joints:
            raise ValueError(f"Expected {self._num_joints} positions, got {len(positions_rad)}")
        self._positions = list(positions_rad)
        self._update_raw_from_logical()
    
    def get_joint_positions(self, verbose: bool = False) -> list[float]:
        if verbose:
            print(f"[Sim] Current positions: {np.round(self._positions, 3)}")
        return list(self._positions)
    
    def prepare_sync_write_commands(
        self,
        positions_rad: list[float],
        speed: int = 4095,
        accel: int = 0,
    ) -> list[tuple]:
        # In simulation, just return the positions as-is
        return [(i, pos, speed, accel) for i, pos in enumerate(positions_rad)]
    
    def sync_write(self, commands: list[tuple]) -> None:
        # Update positions from the commands
        # Commands are in format [(servo_id, raw_pos, speed, accel), ...]
        # We keep raw actuator values exactly as commanded, then derive logical
        # joint angles from those raw values using robot mapping metadata.
        for servo_id_or_idx, raw_pos, _, _ in commands:
            servo_id = int(servo_id_or_idx)
            clamped_raw = max(0, min(self._encoder_resolution, int(raw_pos)))

            # Normal case: caller sends actuator IDs directly.
            if servo_id in self._actuator_ids:
                self._raw_positions[servo_id] = clamped_raw
                continue

            # Backward-compat: allow actuator index addressing.
            if 0 <= servo_id < len(self._actuator_ids):
                mapped_servo_id = self._actuator_ids[servo_id]
                self._raw_positions[mapped_servo_id] = clamped_raw
                continue

            # Unknown actuator ID; keep a best-effort cache.
            self._raw_positions[servo_id] = clamped_raw

        self._update_logical_positions_from_raw()
    
    def sync_read_positions(self, servo_ids: list[int] = None, timeout_s: Optional[float] = None) -> dict[int, int]:
        # Return cached raw values for requested actuator IDs.
        result = {}
        target_ids = servo_ids if servo_ids else list(self._actuator_ids)
        for servo_id in target_ids:
            sid = int(servo_id)
            if sid in self._raw_positions:
                result[sid] = self._raw_positions[sid]
            elif 0 <= sid < len(self._actuator_ids):
                mapped = self._actuator_ids[sid]
                result[sid] = self._raw_positions.get(mapped, self._encoder_center)
            else:
                result[sid] = self._encoder_center
        return result

    def sync_read_block(
        self,
        servo_ids: list[int],
        start_address: int,
        data_len: int,
        timeout_s: Optional[float] = None,
        poll_delay_s: float = 0.0,
        diagnostics: bool = False,
    ) -> dict[int, bytes]:
        """
        Simulate a block read by returning zeroed bytes for each servo.
        
        This keeps telemetry consumers running in simulation mode without
        requiring real hardware feedback.
        """
        actuator_ids = self._robot_config.get('actuator_ids', []) if self._robot_config else []
        target_ids = servo_ids if servo_ids else list(actuator_ids)
        if not target_ids or data_len <= 0:
            return {}
        payload = bytes([0] * data_len)
        return {sid: payload for sid in target_ids}
    
    def raw_to_joint_positions(self, raw_positions: dict[int, int]) -> list[float]:
        if not raw_positions:
            return [0.0] * self._num_joints
        for sid, raw in raw_positions.items():
            sid_int = int(sid)
            if sid_int in self._actuator_ids:
                self._raw_positions[sid_int] = int(raw)
            elif 0 <= sid_int < len(self._actuator_ids):
                self._raw_positions[self._actuator_ids[sid_int]] = int(raw)
        self._update_logical_positions_from_raw()
        return list(self._positions)
    
    def set_single_actuator_position(
        self,
        actuator_id: int,
        position_rad: float,
        speed: int,
        accel: int,
    ) -> None:
        if actuator_id == self._gripper_id and self._has_gripper:
            self._gripper_position = position_rad
            self._raw_positions[actuator_id] = self._angle_to_raw(position_rad, actuator_id)
            return
        
        # Map servo ID to joint index
        joint_idx = self._servo_id_to_joint_index(actuator_id)
        if joint_idx is not None and 0 <= joint_idx < self._num_joints:
            self._positions[joint_idx] = position_rad
            physical_angle = position_rad + self._master_offset_for_joint(joint_idx)
            self._raw_positions[actuator_id] = self._angle_to_raw(physical_angle, actuator_id)
    
    def read_single_actuator_position(self, actuator_id: int) -> Optional[int]:
        if actuator_id in self._raw_positions:
            return self._raw_positions[actuator_id]
        if 0 <= actuator_id < len(self._actuator_ids):
            mapped = self._actuator_ids[actuator_id]
            return self._raw_positions.get(mapped, self._encoder_center)
        return self._encoder_center
    
    def _servo_id_to_joint_index(self, servo_id: int) -> Optional[int]:
        """Map a servo ID to its logical joint index."""
        if not self._robot_config:
            return servo_id if 0 <= servo_id < self._num_joints else None
        
        actuator_ids = self._robot_config.get('actuator_ids', [])
        logical_to_physical = self._robot_config.get('logical_to_physical_map', {})
        
        for logical_idx, physical_indices in logical_to_physical.items():
            for phys_idx in physical_indices:
                if phys_idx < len(actuator_ids) and actuator_ids[phys_idx] == servo_id:
                    return logical_idx
        return None
    
    def set_current_position_as_zero(self, actuator_id: int) -> bool:
        print(f"[Sim] Set zero for actuator {actuator_id}")
        return True
    
    def set_pid_gains(self, actuator_id: int, kp: int, ki: int, kd: int) -> bool:
        print(f"[Sim] Set PID for actuator {actuator_id}: Kp={kp}, Ki={ki}, Kd={kd}")
        return True
    
    def apply_joint_limits(self) -> bool:
        print("[Sim] Applied joint limits (simulated)")
        return True
    
    @property
    def has_gripper(self) -> bool:
        return self._has_gripper
    
    @property
    def gripper_actuator_id(self) -> Optional[int]:
        return 100 if self._has_gripper else None
    
    def get_gripper_position(self) -> Optional[float]:
        return self._gripper_position if self._has_gripper else None
    
    def get_present_actuator_ids(self) -> set[int]:
        ids = set(self._actuator_ids)
        if self._has_gripper and self._gripper_id is not None:
            ids.add(self._gripper_id)
        return ids
    
    def ping_actuator(self, actuator_id: int) -> bool:
        return actuator_id in self.get_present_actuator_ids()

    def _initialize_raw_cache(self) -> None:
        self._raw_positions.clear()
        for servo_id in self._actuator_ids:
            self._raw_positions[int(servo_id)] = self._encoder_center
        if self._has_gripper and self._gripper_id is not None:
            self._raw_positions[int(self._gripper_id)] = self._encoder_center

    def _master_offset_for_joint(self, logical_joint_idx: int) -> float:
        if 0 <= logical_joint_idx < len(self._master_offsets):
            return float(self._master_offsets[logical_joint_idx])
        return 0.0

    def _servo_id_to_config_index(self, servo_id: int) -> Optional[int]:
        try:
            return self._actuator_ids.index(int(servo_id))
        except ValueError:
            return None

    def _is_direct_mapping(self, servo_id: int) -> bool:
        return int(servo_id) not in self._inverted_actuator_ids

    def _mapping_range_for_servo(self, servo_id: int) -> tuple[float, float]:
        cfg_idx = self._servo_id_to_config_index(servo_id)
        if cfg_idx is not None and cfg_idx < len(self._mapping_ranges):
            lo, hi = self._mapping_ranges[cfg_idx]
            return float(lo), float(hi)
        return -math.pi, math.pi

    def _raw_to_angle(self, raw_value: int, servo_id: int) -> float:
        lo, hi = self._mapping_range_for_servo(servo_id)
        span = hi - lo
        if abs(span) < 1e-12:
            return lo
        normalized = float(raw_value) / float(self._encoder_resolution)
        if self._is_direct_mapping(servo_id):
            return lo + normalized * span
        return hi - normalized * span

    def _angle_to_raw(self, angle_rad: float, servo_id: int) -> int:
        lo, hi = self._mapping_range_for_servo(servo_id)
        span = hi - lo
        if abs(span) < 1e-12:
            return self._encoder_center
        clamped = max(lo, min(hi, float(angle_rad)))
        normalized = (clamped - lo) / span
        if not self._is_direct_mapping(servo_id):
            normalized = 1.0 - normalized
        raw = int(round(normalized * float(self._encoder_resolution)))
        return max(0, min(self._encoder_resolution, raw))

    def _update_logical_positions_from_raw(self) -> None:
        logical_positions = [0.0] * self._num_joints
        for logical_idx in range(self._num_joints):
            physical_indices = self._logical_to_physical.get(logical_idx, [logical_idx])
            physical_angles: list[float] = []
            for phys_idx in physical_indices:
                if 0 <= int(phys_idx) < len(self._actuator_ids):
                    servo_id = self._actuator_ids[int(phys_idx)]
                    raw = self._raw_positions.get(servo_id, self._encoder_center)
                    physical_angles.append(self._raw_to_angle(raw, servo_id))
            if physical_angles:
                mean_physical = float(sum(physical_angles)) / float(len(physical_angles))
                logical_positions[logical_idx] = mean_physical - self._master_offset_for_joint(logical_idx)
        self._positions = logical_positions

        if self._has_gripper and self._gripper_id is not None:
            raw_gripper = self._raw_positions.get(int(self._gripper_id), self._encoder_center)
            self._gripper_position = self._raw_to_angle(raw_gripper, int(self._gripper_id))

    def _update_raw_from_logical(self) -> None:
        for logical_idx, logical_angle in enumerate(self._positions):
            physical_indices = self._logical_to_physical.get(logical_idx, [logical_idx])
            physical_angle = float(logical_angle) + self._master_offset_for_joint(logical_idx)
            for phys_idx in physical_indices:
                if 0 <= int(phys_idx) < len(self._actuator_ids):
                    servo_id = self._actuator_ids[int(phys_idx)]
                    self._raw_positions[servo_id] = self._angle_to_raw(physical_angle, servo_id)

        if self._has_gripper and self._gripper_id is not None:
            self._raw_positions[int(self._gripper_id)] = self._angle_to_raw(
                self._gripper_position,
                int(self._gripper_id),
            )

