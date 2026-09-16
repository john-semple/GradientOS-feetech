# Sprint 10 — Smooth Streaming Executor: Implementation & Lessons

## Overview

Sprint 10 migrates GradientOS's motion executors from arrive-and-stop waypoint
streaming to **continuous setpoint streaming with lookahead**, exploiting the
Case A firmware behavior measured in Sprint 07 (mid-cruise goal rewrites blend
with velocity continuity). The streaming is wrapped entirely inside the
backend so the planner, command API, web UI, and weld planner require zero
changes.

This document covers the implementation, the iterative tuning process on real
hardware, and every lesson learned along the way.

---

## What Was Built

### MotionHandle (`motion_handle.py`)

Thread-safe lifecycle handle returned by `execute_timed_path()`:

| Method | Behavior |
|--------|----------|
| `cancel()` | Stop immediately, path is dead. Writes current-position-as-goal so the servo decelerates over the lookahead horizon. Estop-equivalent. |
| `pause()` | Stop feeding goals, hold position, path stays alive. Pacing thread blocks on a resume event. |
| `resume()` | Re-derive nearest path timestamp from sync_read, resume streaming. Profiled reconnect for large drift (> 0.1 rad). |
| `is_done()` | Path completed normally. |
| `wait(timeout)` | Block until done or timeout. Replaces `thread.join()` pattern. |

State machine: `RUNNING → PAUSED → RUNNING` (resume) or `→ CANCELLED / DONE`.

### StreamingMixin (`backends/_streaming_mixin.py`)

Shared implementation mixed into both `STS3215Backend` and `HLS3950Backend`.

**Pacing loop:** variable frequency (100 Hz fast / 33 Hz slow), 100 ms
lookahead, per-joint velocity caps from path demand, stream guard clamping
to path bounds, horizon rule (stop at path_end), interleaved position reads
every 100 ms for live UI feedback.

**Per-joint cap sizing:** `max|Δq/Δt| × 1.2` per joint, clamped [150, 2000]
LSB. Per-joint (not flat) so low-velocity joints don't aggressively chase
across backlash gaps.

**Config override:** `streaming_enabled: False` in robot config disables
streaming with no code change. For HLS3950 if bench testing reveals firmware
doesn't blend smoothly.

### SimulationBackend streaming

Robust pacing at 100 Hz with 50 ms lookahead — exercises the same logic as
real hardware (write frequency, lookahead, cancel, pause/resume, horizon
expiry). `sim_fast_forward` option uses a virtual clock instead of
`time.sleep` for fast automated tests.

### Executor migration

- `_open_loop_executor_thread`: hands off to `execute_timed_path` when
  streaming is available, falls back to dense streaming otherwise.
- `_trajectory_executor_thread`: routes move steps to streaming (takes
  precedence over profiled segments; covers both weld and non-weld moves).
- `handle_stop_command()`: cancels active streaming handle before legacy brake.

---

## Iterative Tuning on Real Hardware

### Iteration 1: Initial implementation

First run on real hardware: better than the original arrive-and-stop executor
but worse than the Sprint 04 profiled-segment executor. Smooth during the
beginning of rotysquare when J1/J2 weren't moving much, jerky when they were.

**Root cause:** `max(caps)` — the fastest joint's velocity cap was used as
the speed register value for ALL servos. Low-velocity joints (J1/J2 with
high backlash) aggressively chased each micro-goal across the backlash gap
at 100 Hz, creating hunt oscillation.

**Fix:** Added `_prepare_streaming_commands()` that builds per-joint speed
register values. Joints with small velocity demand get low caps.

### Iteration 2: Per-joint caps — better but still bogging down

After per-joint caps: beginning of rotysquare looked even better, but big-
torque movements on J1/J2 bogged down and slowed jerkily. The last move
(arm lifting against gravity) seemed underpowered.

**Root cause:** Bus contention. The telemetry thread (running at 10 Hz)
was doing `sync_read` calls on the same CH340 single-wire bus while the
pacing thread was writing at 100 Hz. The reads blocked the serial port
for 10-20 ms, starving the write stream. The servo got irregular goal
timing — write, write, nothing for 30 ms, write, write — causing
decelerate-then-jerk patterns.

Evidence in logs: `[STS3215 SyncRead] WARNING: Expected 64 bytes, got 62.
No response from IDs: [20]` — servos couldn't respond because the bus was
busy with writes.

**Fix:** Suppress telemetry reads while a streaming handle is active.
The telemetry loop uses `utils.current_logical_joint_angles_rad` (last
known positions) instead of doing its own serial reads during moves.

### Iteration 3: Bus contention fixed — vibration appeared

After suppressing telemetry: the bogging-down was gone, but a new
vibration appeared, especially on slow moves. The arm had a micro-buzz
at ~100 Hz.

**Root cause:** The 3× cap multiplier was too high for slow moves. At
low velocity (say 5 deg/s), the cap was 15 deg/s. The servo raced to
each 50 ms lookahead goal (a tiny distance), arrived in 1-2 ms, stopped,
waited 8 ms, then raced again. Overshoot-stall-overshoot at 100 Hz.

**Fix attempt:** Lowered cap multiplier from 3× to 1.2×, floor from 300
to 150.

### Iteration 4: Lower caps — still vibrating on slow moves

Vibration persisted on slow moves even with 1.2× caps. The fundamental
problem: at 100 Hz with 50 ms lookahead, each goal is a tiny step. The
servo's 12-bit encoder and 0.088 deg/s speed resolution quantize the
tiny deltas into discrete jumps.

**Root cause:** Goal step size too small at 100 Hz for slow moves.
Not a cap problem — a pacing frequency problem.

**Fix:** Variable pacing — 100 Hz on fast moves, 33 Hz on slow moves
(< 50 deg/s). At 33 Hz each goal is 3× larger, giving the firmware more
profile distance to smooth over.

### Iteration 5: Variable pacing + increased lookahead

Raised slow-move threshold from 10 to 50 deg/s (most rotysquare moves
are 10-40 deg/s, so they now use 33 Hz). Increased lookahead from 50 ms
to 100 ms for more firmware smoothing distance. Result: a bit better
on fast parts, still slightly jerky on slow parts.

**Remaining vibration cause (diagnosed but not yet fixed):** The
trapezoidal velocity profile itself has acceleration discontinuities
(accel → cruise → decel transitions). When streamed, these map to
sudden changes in goal spacing that the servo's PID reads as micro-
jerks. The real fix is S-curve velocity profiling in the planner, which
smooths the acceleration transitions. This is a planner change, not an
executor change — deferred to future work.

### Iteration 6: GUI not updating during moves

The GUI showed stale positions until each move finished. The interleaved
reads in the pacing loop were supposed to update
`utils.current_logical_joint_angles_rad` every 100 ms.

**Root cause:** Wrong relative import. The pacing loop used
`from ... import utils` (3 dots) which resolves to `gradient_os.utils` —
which doesn't exist. The correct import is `from .. import utils` (2 dots)
which resolves to `gradient_os.arm_controller.utils`. The `ImportError`
was caught by a bare `except ImportError: pass`, so `utils_ref` was always
`None` and positions were never updated.

**Fix:** Changed `from ... import utils` to `from .. import utils`.

**Remaining GUI lag:** ~0.5 s lag persists. The 10 Hz read rate + the
read timeout (20 ms) + UDP transmission + React render cycle add up.
Future improvement: reduce read interval to 50 ms (20 Hz) or have the
pacing thread push positions directly via UDP instead of going through
the telemetry loop.

---

## Lessons Learned

### Architecture & Design

1. **Per-joint speed caps are critical for streaming.** Using `max(caps)`
   (the fastest joint's cap) for all servos causes backlash hunt
   oscillation on high-backlash joints. Each joint must get its own cap
   proportional to its velocity demand. `prepare_sync_write_commands()`
   only accepts a single flat speed — don't use it for streaming. Build
   a custom `_prepare_streaming_commands()` with per-joint caps.

2. **Bus contention is the silent killer on single-wire protocols.** The
   CH340 is half-duplex — reads and writes share one wire. Having two
   threads (pacing + telemetry) independently accessing the bus causes
   unpredictable collisions that manifest as motion jerk, not as errors.
   The fix is to make one thread own the bus during motion and have all
   reads happen inside the write loop on a controlled schedule.

3. **Interleaved reads must be time-based, not cycle-based.** When pacing
   frequency changes (variable pacing), a cycle-based read interval
   ("every 10 cycles") produces inconsistent read rates. Time-based
   ("every 100 ms") gives consistent UI feedback regardless of write rate.

4. **Variable pacing beats write skipping.** Skipping writes at 100 Hz
   (wake up, decide "not this cycle", sleep, wake up, decide "not this
   cycle", sleep, wake up, write) wastes CPU on unnecessary wake-ups and
   causes GIL contention. Variable pacing (sleep for the full 30 ms
   period) is cleaner — fewer wake-ups, less GIL contention, better
   timing precision as a fraction of the period.

5. **The cap multiplier should be close to 1×, not high.** A high
   multiplier (2×–3×) gives the servo "racing room" that causes
   overshoot-stall vibration on slow moves. 1.2× gives just enough
   headroom to track the stream without racing ahead. The earlier
   bogging-down was caused by bus contention, not by insufficient cap
   headroom — so lowering the multiplier after fixing contention was
   safe.

6. **Lookahead affects both smoothness and safety.** 50 ms lookahead
   gives tight estop response but tiny goal steps. 100 ms gives more
   firmware profile distance to smooth over discontinuities but doubles
   the estop travel. This is a fundamental trade-off — there's no free
   lunch.

### Bugs & Debugging

7. **Python relative imports: count the dots carefully.** `from ... import
   utils` (3 dots) from `gradient_os.arm_controller.backends._streaming_mixin`
   resolves to `gradient_os.utils` — wrong. `from .. import utils` (2 dots)
   resolves to `gradient_os.arm_controller.utils` — correct. A bare
   `except ImportError: pass` silently swallows the error, making it
   invisible. Always test relative imports in isolation.

8. **Silent failures from try/except/pass are dangerous.** The pacing
   loop's import failure was caught and ignored, so `utils_ref` was
   always `None`. The code "worked" (no crash) but the GUI never updated.
   When using try/except for optional imports, at least log a warning.

9. **Tuples unpack as scalars, not as indexed collections.** When
   unpacking `t0, q0 = path[lo]`, `t0` is a float, not a tuple. `t1[0]`
   raises `TypeError: 'float' object is not subscriptable`. Use `t1`
   directly. This bug was caught by sim tests before hitting hardware.

10. **SimulationBackend's `prepare_sync_write_commands` returns float
    angles, not raw encoder ints.** Using `sync_write()` with these
    commands fails silently (the sim stores bad values). Use
    `set_joint_positions()` for sim streaming writes.

11. **Fast-forward sim mode needs a virtual clock.** When `time.sleep` is
    skipped, `time.monotonic()` barely advances, so `t_now > path_end`
    never triggers and the pacing loop hangs forever. Use
    `cycle * period` as a virtual clock in fast-forward mode.

12. **`_backend_supports_setpoint_streaming()` must check `_use_backend()`
    first.** The end-to-end test patches `_use_backend` to return False
    (forcing legacy path). Without checking it, streaming activates even
    when the test expects legacy behavior.

### Process & Communication

13. **Don't make design decisions without user approval.** The variable
    pacing + interleaved read approach was implemented without
    presenting options first. The user should have been asked which
    approach they preferred before code was written. Present options,
    explain trade-offs, then implement what they choose.

14. **Don't move the arm without asking.** Editing code while the
    controller is running can cause it to pick up new code on the next
    motion command, moving the arm unexpectedly. Always ask the user to
    stop the controller before making changes that affect motion.

15. **Test on hardware early and often.** The initial implementation
    passed all 93 sim tests but had multiple issues that only appeared
    on real hardware (bus contention, backlash oscillation, cap sizing).
    Sim tests verify logic; only hardware validates dynamics.

16. **Read the logs carefully.** The `[STS3215 SyncRead] WARNING: No
    response from IDs` messages in the first hardware run were the key
    diagnostic for bus contention. They appeared before any motion
    problems were reported, but their significance wasn't recognized
    until the user reported jerky motion.

---

## Current State

### What works
- Streaming path is active and confirmed in logs
- Per-joint velocity caps prevent backlash hunt oscillation
- Bus contention eliminated (telemetry reads suppressed during moves)
- Variable pacing (33 Hz slow / 100 Hz fast) reduces micro-vibration
- Interleaved reads provide ~10 Hz position feedback to UI during moves
- Cancel/pause/resume handle API works
- All 93 backend tests pass, web UI tests + build pass

### What still needs work
- **Slow-move vibration:** trapezoidal velocity profile has acceleration
  discontinuities that cause micro-jerks when streamed. Fix: S-curve
  velocity profiling in the planner (future sprint).
- **GUI lag:** ~0.5 s delay between servo position and UI display.
  Fix: increase read rate to 20 Hz or push positions directly from
  pacing thread (future improvement).
- **Bench validation:** all physical-arm checkboxes still unchecked
  (rotysquare smoothness, continuous move_line, HLS3950 Case A
  verification, long diagonal oscillation check).

### Key constants (current values)

| Constant | Value | Rationale |
|----------|-------|-----------|
| `PACING_FREQUENCY_HZ` | 100 | Fast moves — Sprint 07 measured sustainable |
| `SLOW_PACING_FREQUENCY_HZ` | 33 | Slow moves — larger goal steps, no micro-vibration |
| `LOOKAHEAD_S` | 0.100 | 100 ms — more firmware smoothing distance |
| `CAP_MULTIPLIER` | 1.2 | Close to 1× — track stream without racing ahead |
| `CAP_MIN` / `CAP_FLOOR` | 150 | Minimum torque authority for backlash |
| `CAP_MAX` | 2000 | Safety clamp |
| `STREAMING_ACCEL` | 10 | Sprint 01 bench-safe recipe |
| `READ_INTERVAL_S` | 0.100 | 10 Hz UI feedback |
| `SLOW_MOVE_THRESHOLD_DEG_S` | 50 | Most rotysquare moves are below this |
| `READ_TIMEOUT_S` | 0.020 | Enough for 8-servo sync read response |

---

## File Inventory

| File | Role |
|------|------|
| `motion_handle.py` | MotionHandle + MotionState enum |
| `backends/_streaming_mixin.py` | Shared pacing loop, cap sizing, stream guard, cancel/pause/resume |
| `actuator_interface.py` | ABC: `supports_setpoint_streaming`, `execute_timed_path()` |
| `backends/sts3215/driver.py` | Inherits StreamingMixin |
| `backends/hls3950/driver.py` | Inherits StreamingMixin (config override ready) |
| `backends/simulation/backend.py` | Robust sim streaming with fast_forward |
| `trajectory_execution.py` | Executor handoff, `_execute_streaming_step()`, `_joint_path_to_timed()` |
| `command_api.py` | `handle_stop_command()` cancels streaming handle |
| `run_controller.py` | Telemetry loop skips serial reads during streaming |
| `tests/test_setpoint_streaming.py` | 36 gating-matrix tests |
| `feetech-project/sprints/sprint-10-smooth-streaming-executor.md` | Sprint spec (updated) |