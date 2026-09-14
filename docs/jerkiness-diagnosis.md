# Motion Jerkiness Diagnosis & Theory Guide

> **Status:** Living document — update as theories are tested and resolved.
> **Symptoms:** Arm is jerky during all motion (trajectories, jogging, straight-line moves). Servos oscillate and stall at waypoints. Backlash causes wild arm oscillation. The **only exception** is the **Home** button, which moves perfectly smoothly.

---

## 1. Observation Summary

| Motion type               | How it's commanded                                  | Speed sent | Accel sent | Smooth? |
|---------------------------|-----------------------------------------------------|------------|------------|---------|
| **Home button** (top bar) | Single `set_servo_positions(q, 500, 500)`           | 500        | 500 deg/s² | ✅ Smooth |
| **Jog** (UI jog)          | `set_servo_positions(q, 800, 0)` @ 25 Hz            | 800        | 0          | ❌ Jerky |
| **Move line (profiled)**  | Pre-planned path, streamed `sync_write` @ 50/100 Hz | **4095**   | **0**      | ❌ Jerky |
| **Trajectory (rotysquare)** | Pre-planned `move` steps, streamed @ 100 Hz        | **4095**   | **0**      | ❌ Jerky |
| **Joint move** (in traj)  | Single `set_servo_positions(q, speed, 0)`           | configured | 0          | varies   |

The single common factor that separates smooth motion from jerky motion is the **speed and acceleration values sent to the servos**, combined with **how frequently new setpoints are streamed**.

---

## 2. The Smoking Gun: Two Conflicting Control Paradigms

The codebase mixes two fundamentally different servo control strategies, and the jerky paths use the **wrong one**.

### Paradigm A — Servo-Internal Profile (what Home uses)

```
Software sends ONE target position with moderate speed/accel
  → Feetech STS3215 firmware runs an internal trapezoidal profile
  → Servo smoothly accelerates, cruises, decelerates to target
  → No per-cycle setpoint streaming required
```

- **Used by:** Home button (`run_controller.py:997`), `joint_move` steps in trajectories, `TRANSLATE`/`ROTATE` single-point IK commands.
- **Code path:** `servo_driver.set_servo_positions(q, speed=500, accel=500)` → single `sync_write` packet.
- **Result:** Smooth. The servo's on-board controller handles the entire motion profile.

### Paradigm B — Host-Side Streaming Profile (what everything jerky uses)

```
Software pre-computes a dense joint-space path (100+ waypoints)
  → Streams each waypoint via sync_write at 50–100 Hz
  → Each packet commands speed=4095 (MAX), accel=0 (MAX)
  → Servo tries to reach each tiny waypoint at maximum velocity
  → Servo's internal planner is effectively bypassed/overdriven
```

- **Used by:** `handle_move_profiled` (closed-loop @50 Hz, open-loop @100 Hz), `handle_run_trajectory` (move steps @100 Hz), jog loop (@25 Hz with speed=800, accel=0).
- **Code path:** `trajectory_execution._open_loop_executor_thread` / `_closed_loop_executor_thread` → `backend.sync_write(cmds)` where `cmds` contain `(servo_id, pos, speed=4095, accel=0)`.
- **Result:** Jerky. The host and the servo's internal controller fight each other.

### Why speed=4095, accel=0 is catastrophic for streaming

Look at where the streaming commands are built:

**Open-loop executor** (`trajectory_execution.py:744-746`):
```python
precomputed_cmds = [
    servo_driver.logical_q_to_syncwrite_tuple(q, utils.ENCODER_RESOLUTION, 0) for q in joint_path
]
#                                                                    ^^^^^^^^^^^^^^^^^  ^^^
#                                                                  speed=4095 (MAX)  accel=0 (MAX)
```

**Closed-loop executor** (`trajectory_execution.py:1061`):
```python
commands_for_sync_write.append((servo_id, final_servo_pos_value, encoder_max, 0))
#                                                                     ^^^^^^^^^^^  ^^^
#                                                                   speed=4095    accel=0
```

When you stream 100 waypoints per second, each commanding the servo to move at **maximum speed and maximum acceleration** to a target that's only ~1mm away, you get:

1. **Staircase velocity profile** — The servo accelerates hard toward each micro-target, then immediately gets a new target before settling. This produces a series of micro-jolts rather than continuous smooth motion.
2. **Servo PID wind-up/overcorrection** — With `Kp=50-65` and `accel=0`, the servo's internal PID sees a large instantaneous error (because it's been told to go max speed to a new point) and slams the motor. By the time it reacts, a new target arrives. The derivative term (`Kd=20-30`) tries to damp, but the setpoint keeps jumping.
3. **Backlash excitation** — Each micro-jolt reverses load direction on the gears. Backlash means the motor moves slightly before the load engages, creating a "snap." Repeated 100×/second, this becomes oscillation.
4. **Spring-like stalling** — When backlash + oscillation cause the servo to overshoot, the position error reverses, the servo drives back, overshoots again. With high Kp and no acceleration limit, this becomes a limit cycle (the "spring" behavior you describe). The servo stalls because it's constantly reversing and can't settle.

### Why Home is smooth

Home sends `0,0,0,0,0,0` with `speed=500, accel=500`. The Feetech servo receives one target, runs its **internal** trapezoidal profile (accel ramp → cruise at speed 500 → decel ramp), and arrives smoothly. No setpoint streaming, no fighting between host and servo controllers.

---

## 3. Theory Ranking

### Theory A: **Streaming with max speed/accel is the root cause** (HIGH confidence)

**Evidence:**
- Home (single command, moderate speed/accel) → smooth.
- All jerky paths (streamed, speed=4095, accel=0) → jerky.
- The only variable that changes between smooth and jerky is the command paradigm.
- Backlash oscillation and "spring" behavior are textbook symptoms of high-gain, high-acceleration setpoint streaming on gearmotors with backlash.

**Prediction:** If we send streamed waypoints with **moderate speed (~500) and moderate accel (~500 deg/s²)** instead of (4095, 0), the jerky motion should largely disappear. The servo's internal controller will smooth between waypoints.

**Test:** Change `logical_q_to_syncwrite_tuple(q, 500, 5)` and `(servo_id, pos, 500, 5)` in the executors. Run rotysquare. Compare.

---

### Theory B: **Host-side loop frequency is too low / jittery** (MEDIUM confidence)

**Evidence:**
- Open-loop runs at 100 Hz, closed-loop at 50 Hz. Jog at 25 Hz.
- At 100 Hz, each step is 10 ms. If the loop has jitter (e.g., Python GC, serial I/O latency), the servo sees irregular time gaps between setpoints.
- The servo doesn't know the time spacing — it just sees "go to point X at max speed." If a setpoint is 15 ms late, the servo has already reached the previous point and stopped, then gets a jolt to the next.

**Code:** The open-loop executor uses `time.sleep(deadline - now)` which is not hard real-time. Python's `time.sleep` on Linux has ~1-2 ms jitter, and GC pauses can be 5-10 ms.

**Prediction:** If timing jitter is a contributor, running at a **lower frequency with moderate speed** (so each step takes longer than the jitter) will help. This compounds with Theory A.

**Test:** Look at diagnostics output — check `loop_durations` variance and overrun percentage. If overruns >5%, timing is a factor.

---

### Theory C: **Closed-loop software PID is disabled, relying purely on servo PID** (MEDIUM confidence, confirms A)

**Evidence:** `trajectory_execution.py:1041-1043`:
```python
# Software PID correction intentionally disabled. We command the planned target
# to let inner servo PID be the only stabilizing loop during tuning.
commanded_physical_angle_rad = target_physical_angle_rad
```

The closed-loop executor **reads** feedback and computes error, but then **commands the raw target** (no correction). This means the closed-loop path is effectively open-loop with extra read overhead. The read adds latency (sync read over serial at 1 Mbaud for 6-8 servos takes 5-15 ms) which eats into the 20 ms (50 Hz) cycle budget, causing overruns and jitter (Theory B).

**Implication:** If you're not using the software correction, the closed-loop executor gives you **all the overhead of feedback with none of the benefit**. The open-loop executor at 100 Hz would actually be faster and smoother for the same setpoint-streaming approach.

---

### Theory D: **PID tuning is wrong for the streaming paradigm** (MEDIUM confidence)

**Evidence:**
- Current gains: `Kp=50-65, Ki=0-1, Kd=10-30` (`config.py:383-389`).
- These are reasonable for **single-command position moves** (Paradigm A) but may be too aggressive for **high-frequency setpoint streaming** (Paradigm B).
- With `Kp=65` on the shoulder and `accel=0`, the servo drives hard toward each micro-setpoint. A lower Kp would make the servo "lazier" between setpoints, smoothing the motion — but at the cost of tracking accuracy.

**Prediction:** If Theory A is correct, then PID tuning alone (without changing speed/accel) would help but is treating the symptom, not the cause. Lower Kp (e.g., 20-30) would reduce jerk but add lag.

---

### Theory E: **Savitzky-Golay smoothing is insufficient or misapplied** (LOW confidence)

**Evidence:** `_plan_high_fidelity_trajectory` applies a SavGol filter with `window_length=15, polyorder=3` to the joint-space path. This smooths the **planned** trajectory, but:
1. If the IK solutions themselves are noisy (e.g., near singularities), the filter may not fully remove discontinuities.
2. The filter operates on position only — velocity and acceleration derivatives of the filtered path may still have steps.

**Prediction:** This is a secondary effect. Even a perfectly smooth path will be jerky if commanded at speed=4095, accel=0. Fix Theory A first.

---

### Theory F: **Twin-motor synchronization issue** (LOW-MEDIUM confidence)

**Evidence:** For twin-motor joints (20+21, 30+31), the closed-loop executor only reads **one** servo per pair and synthesizes the other's position by mirroring (`trajectory_execution.py:968-974`). If the two motors have slightly different response, they fight each other through the shared mechanical linkage, causing oscillation.

**Prediction:** If twin-motor joints oscillate more than single-motor joints (J4/J5/J6), this is a contributor. Check which joints oscillate worst.

---

## 4. Proposed Experiments (in priority order)

### Experiment 1: Moderate speed/accel in streaming executors ⭐ HIGHEST PRIORITY

**Hypothesis:** Theory A — streaming at speed=4095/accel=0 is the root cause.

**Change:**
- `trajectory_execution.py:745` (open-loop precompute):
  ```python
  # Before:  servo_driver.logical_q_to_syncwrite_tuple(q, utils.ENCODER_RESOLUTION, 0)
  # After:   servo_driver.logical_q_to_syncwrite_tuple(q, 500, 5)
  ```
- `trajectory_execution.py:1061` (closed-loop command build):
  ```python
  # Before:  commands_for_sync_write.append((servo_id, final_servo_pos_value, encoder_max, 0))
  # After:   commands_for_sync_write.append((servo_id, final_servo_pos_value, 500, 5))
  ```

**Test:** Run rotysquare trajectory and jog. Observe smoothness. Run with diagnostics and check tracking error.

**Risk:** Moderate speed limits the servo's ability to keep up with the planned path if the path is fast. But the path is planned at 0.1 m/s — at 100 Hz that's 1mm/step. A speed setting of 500 (out of 4095) should be more than enough for 1mm steps.

---

### Experiment 2: Use open-loop executor for trajectories (skip closed-loop overhead)

**Hypothesis:** Theory C — closed-loop with disabled software PID wastes cycle time on reads, causing jitter.

**Change:** In `handle_move_profiled`, default `closed_loop=False`. Or: enable the software PID correction if you want closed-loop benefit.

**Test:** Compare open-loop (100 Hz) vs closed-loop (50 Hz) smoothness with Experiment 1 applied.

---

### Experiment 3: Reduce loop frequency to 50 Hz for open-loop streaming

**Hypothesis:** Theory B — 100 Hz with Python timing jitter causes irregular setpoint spacing.

**Change:** Set open-loop frequency to 50 Hz (matching closed-loop). With moderate speed/accel, the servo's internal planner will interpolate between the more widely-spaced setpoints.

**Test:** Run rotysquare at 50 Hz vs 100 Hz, compare smoothness.

---

### Experiment 4: PID tuning sweep (only after Experiment 1)

**Hypothesis:** Theory D — after fixing speed/accel, residual jerk may be from PID being slightly off.

**Test:** Use the built-in `handle_tune_pid_joint` / `handle_tune_pid_all` to sweep Kp/Ki/Kd. Start with lower Kp (30) and increase until tracking error is acceptable without oscillation.

---

### Experiment 5: Check diagnostics for timing overruns

**Hypothesis:** Theory B — quantifies the timing jitter.

**Test:** Enable diagnostics (`MINI_ARM_IK_LOG=1` or `diagnostics=True`), run a trajectory, inspect `diagnostics/*/timing.png` and the printed overrun summary. If `overruns > 5%`, timing is a contributor.

---

## 5. Key Code Locations

| What | File | Line | Notes |
|------|------|------|-------|
| Open-loop precompute (speed=4095, accel=0) | `trajectory_execution.py` | 744-746 | `logical_q_to_syncwrite_tuple(q, ENCODER_RESOLUTION, 0)` |
| Closed-loop command build (speed=4095, accel=0) | `trajectory_execution.py` | 1061 | `(servo_id, pos, encoder_max, 0)` |
| Software PID disabled | `trajectory_execution.py` | 1041-1043 | `commanded_physical_angle_rad = target_physical_angle_rad` |
| Home command (smooth) | `run_controller.py` | 997 | `set_servo_positions(angles, DEFAULT_SERVO_SPEED=500, DEFAULT_SERVO_ACCEL=500)` |
| Jog command (speed=800, accel=0) | `command_api.py` | 1257 | `set_servo_positions(q_clamped, 800, 0)` |
| Move line defaults | `command_api.py` | 348-352 | closed=50Hz, open=100Hz |
| Trajectory move step frequency | `command_api.py` | 552 | `'freq': 100` |
| Default servo speed/accel | `backends/sts3215/config.py` | 86-89 | `500` / `500 deg/s²` |
| Default profile velocity/accel | `robots/gradient0/config.py` | 348-355 | `0.1 m/s` / `0.05 m/s²` |
| PID gains (per joint) | `robots/gradient0/config.py` | 383-389 | Kp=50-65, Ki=0-1, Kd=10-30 |
| SavGol smoothing params | `trajectory_execution.py` | 585-586 | window=15, polyorder=3 |
| Twin-motor mirroring | `trajectory_execution.py` | 968-974 | Only reads primary, synthesizes secondary |

---

## 6. Recommended Action Plan

1. **Test Experiment 1** (moderate speed/accel in executors) — this is the single highest-impact change and is a one-liner in two places.
2. **If still jerky**, run Experiment 5 (diagnostics) to quantify timing.
3. **If still jerky**, test Experiment 2 (open-loop only) to eliminate closed-loop read overhead.
4. **If residual jerk remains**, run Experiment 4 (PID sweep) with the built-in tuner.
5. **Long-term:** Consider implementing a proper host-side velocity/acceleration-limited trajectory controller that sends **position + velocity + acceleration time-profiled** commands, or switch to the Feetech servo's internal profile mode for all moves (send sparse waypoints with moderate speed/accel and let the servo interpolate).

---

## 7. Why Home Works — Detailed Trace

1. UI clicks Home → POST `/control/home` → `api/main.py:417`
2. API sends UDP message `"0,0,0,0,0,0"` to controller → `run_controller.py:983`
3. Controller parses 6 angles → `set_servo_positions([0,0,0,0,0,0], speed=500, accel=500)` → `run_controller.py:997`
4. `servo_driver.set_servo_positions` → converts to raw values → single `sync_write` packet → `servo_driver.py:698`
5. **One packet, one target, moderate speed/accel.** Feetech firmware runs internal trapezoidal profile → smooth motion.

**No path planning. No setpoint streaming. No 100 Hz loop. Just one command and the servo does the rest.**

---

## 8. Why Trajectories/Jog Jerk — Detailed Trace (rotysquare example)

1. UI runs trajectory → `handle_run_trajectory` → `command_api.py:412`
2. For each `move_absolute` step → `_plan_linear_move` → IK batch solve → 100+ joint-space waypoints → `command_api.py:540-555`
3. `_trajectory_executor_thread` → `_execute_joint_path` → `_open_loop_executor_thread` → `trajectory_execution.py:1174, 716`
4. Precompute: `logical_q_to_syncwrite_tuple(q, ENCODER_RESOLUTION=4095, 0)` for every waypoint → `trajectory_execution.py:744`
5. Loop at 100 Hz: `backend.sync_write(cmd)` → sends 6-8 servo position commands with **speed=4095, accel=0** → `trajectory_execution.py:772`
6. **100 times per second**, each servo is told "go to this new position at maximum speed and maximum acceleration."
7. Servo PID (Kp=50-65) sees a new error 100×/second, slams the motor each time → micro-jolts → backlash excitation → oscillation → "spring" behavior.

**The servo's internal motion planner is completely bypassed. The host is trying to be the planner, but it's commanding as if the servo has no dynamics.**

---

## 9. Refinement — Why per-waypoint profiles stop-and-go, and the saturation model

> Added after theory discussion: the user correctly identified that even "smarter" per-waypoint
> commanding (e.g. Goal Time per segment) still produces stop-go if each segment is an
> independent point-to-point profile.

### 9.1 The stop-go trap

A Feetech internal profile is a **point-to-point trapezoid with zero-velocity endpoints**:
accelerate from rest → cruise → decelerate to arrive with v=0. Chaining one profile per
waypoint means velocity crosses zero at **every waypoint boundary**. Position is
continuous, but velocity is not — acceleration spikes at every boundary excite backlash.

- This applies to per-segment Goal Time commands too — **unless** the firmware blends a new
  goal from current velocity instead of re-planning from rest. Unknown on this bench
  (Goal Time is "not exercised" in the bench notes). Treat Goal Time as a secondary
  experiment, not the primary fix.

### 9.2 The escape hatch: profile saturation (the "perpetual carrot")

Key property of the internal planner: **the deceleration phase only starts once the servo
comes within braking distance of its goal.** If a new, further goal always arrives before
the servo gets within braking distance of the current one, the servo never decelerates —
it cruises continuously, perpetually chasing the next waypoint.

| Speed cap vs. stream velocity | Servo behavior | Result |
|---|---|---|
| Cap >> stream velocity (current: 4095) | Servo catches each ~1mm waypoint almost instantly, decelerates to rest, waits for next packet | **Stop-go at 100 Hz** — the observed "pauses at waypoints" |
| Cap ≈ stream velocity (+~15% headroom), updated per-step | Goal stays perpetually just ahead; servo never enters decel phase mid-stream | **Continuous cruise** at ≈ planned velocity |
| Cap < stream velocity | Servo falls progressively behind; lag grows; path distortion; late "run home" | Lag / path error — dangerous |

So with position-only hardware, the **speed register becomes the velocity controller**:
stream dense positions as before, but set the speed register per-step to the planned joint
velocity (converted to servo units) plus headroom. The servo's cap-following then
approximates velocity tracking. This is how the LeRobot SO-ARM/SO-100 community drives the
same STS3215 servos (streamed positions at modest Hz with moderate speed values) and gets
smooth replay.

This also explains why jogging is jerky: the jog loop streams at 25 Hz with a fixed
speed=800 — far above the tiny per-step velocity implied by 0.2 m/s jog caps — so the servo
catches each target, stops, and waits 40 ms. Same mechanism, same fix.

Note: stop-go at **true trajectory boundaries** (end of a move, pauses between steps) is
correct and desired. The saturation model only changes behavior *within* a continuous move.

### 9.3 What this changes about Experiment 1

A flat `speed=500` is probably still far above actual planned joint velocities
(~0.25 rad/s ≈ 2-3 rpm for 0.1 m/s Cartesian moves). The proper fix is:

1. Compute per-step joint velocities from the planned dense path (numerical
   differentiation — the path is already dense, so this is trivial).
2. Convert rad/s → STS speed register LSB. The STS speed unit was commonly documented as
   **~0.732 rpm/LSB**, but Sprint 07 Part A refuted that as a direct interpretation on
   this bench. The 2026-09-14 ID `1` test found an effective low-speed floor around cap
   `50`: caps `1`, `2`, `5`, `10`, `30`, and `50` all moved at roughly `5 deg/s`.
   Above that floor, measured position-timed speeds were about `9.0 deg/s` at cap `100`,
   `17.2 deg/s` at cap `200`, and `22.9 deg/s` at cap `300` (about `0.013-0.015
   rpm/LSB` over this short-move setup). Treat the conversion as empirical and
   Feetech-firmware-specific, not a datasheet constant.
3. Add ~10-20% headroom so the servo never quite catches the stream.
4. Set accel register to a moderate fixed value (bench safe-move recipe uses 10).

This conversion is **Feetech-specific** and belongs in the Feetech backend
(config + a rad/s→register helper), exposed to the shared executor as a backend
capability. Backends with real velocity feedforward (future EtherCAT/Dynamixel) ignore it.

### 9.4 The gating unknown: mid-move goal acceptance semantics

> The saturation model in 9.2 rests on an UNVERIFIED firmware assumption: that writing a
> new goal mid-move re-plans from the servo's current state. Three candidate firmware
> behaviors exist, and the observed "pause at waypoints" symptom is consistent with ALL
> of them (with max caps, re-target-from-rest and queued completion both look like
> instant-completion-then-idle too). This must be measured before the cap sweep.

| Behavior | Mid-move goal write | Saturation regime result | Tuning consequence |
|---|---|---|---|
| **A: re-target w/ velocity blend** | Aborts profile, re-plans from current pos+vel | Continuous cruise | Cap = planned velocity + headroom |
| **B: re-target from rest** | Re-plans trapezoid assuming v=0; PID drags velocity to new reference | Velocity sawtooth at stream rate, avg ≈ ½ cap | Cap ≈ 2× planned velocity; ripple is expected, PID-mediated |
| **C: queued completion** | Finishes current plan first | Motion lags one segment; jitter starves queue → micro-stops | Cap = planned velocity; needs stream-rate headroom |

Robustness: velocity-matched caps improve outcomes in all three cases, so the fix
direction is safe — but the real case determines tuning (cap multiplier, headroom,
expected ripple). This test GATES the cap sweep.

**Bench protocol (single servo, existing guardrails — bench servo ID 1, near 4016, move downward):**

1. Command a long move: goal 4016 → 3600, speed cap 300, accel 10 (~2 s travel).
2. Mid-move (while `0x3A` shows clear nonzero velocity, position ≈ 3800), rewrite goal to 3400.
3. Log `0x38` (position), `0x3A` (present speed), moving flag (telemetry block 2 @ `0x41`).

Interpretation:
- Velocity continuous, no dip, never reaches old goal → **Case A** (saturation works as pitched).
- Velocity dips toward zero, re-accelerates, old goal not reached → **Case B** (cap ×2, expect ripple).
- Servo fully stops at old goal first, then proceeds → **Case C** (queuing confirmed; stream-rate headroom needed).

### 9.5 Falsifiable bench test (uses existing telemetry)

Present speed register (`0x3A`) provides per-servo velocity feedback, but Sprint 07
Part A observed direction-encoded values near `32768 - magnitude` during downward
bench moves. Decode `0x3A` from logged traces with this in mind rather than assuming a
plain signed integer. Test protocol:

1. Stream a known linear move at 100 Hz.
2. Sweep the speed cap: {4095, 500, 300, 100, 50} while logging `0x3A` at max feasible
   read rate.
3. Classify each run from the velocity trace: stop-go (velocity zero-crossings at stream
   rate) vs. continuous cruise (velocity ≈ constant, matches planned velocity) vs. lag
   (velocity below plan, position error growing).
4. The cap where velocity transitions from stop-go to cruise is the design point; the
   value where lag appears is the floor. Do not spend Part C time below cap `50` unless
   deliberately documenting the measured minimum-speed clamp.

This turns the saturation theory into a measured curve: cap value vs. achieved velocity
smoothness. **Run the mid-move re-target test (9.4) first** — its result selects the cap
multiplier and headroom used in this sweep.

---

## 10. The Temporary Architecture Change — Feetech-Native Profiled Segments

> Status: **Sprint 04** (`feetech-project/sprints/sprint-04-endpoint-paradigm-quickfix.md`)
> — the quick fix. Sprint 07 (`sprint-07-pseudo-dynamixel-feasibility.md`) is the bench-only
> feasibility study for the pseudo-Dynamixel streaming path (§9). §9.4's fork test is
> Sprint 07 Part B.

### 10.1 The idea

Stop dense streaming for the Feetech backend entirely. For each planned *move step*,
collapse the 100+ dense waypoints into **ONE goal command** — endpoint position, per-joint
speed cap, moderate accel — and let the servo's internal trapezoidal profiler run the
whole segment. This is exactly what the Home button already does, and Home is the one
motion that is demonstrably smooth.

```
Current (broken):    plan 100+ waypoints ──stream@100Hz──▶ servo (caps maxed)  = stop-go
Temporary (Feetech): plan 1 endpoint/cap per segment ──send once──▶ firmware trapezoid = smooth
```

Per-joint speed caps are sized so each joint's firmware trapezoid finishes in ≈ the
planned segment duration (slowest joint sets the duration; other joints' caps are scaled
down to match). Requires the rad/s → speed-register LSB conversion (see 10.4).

### 10.2 Key feasibility advantage: it does NOT depend on the 9.4 firmware fork

The saturation-streaming fix (9.2-9.5) hinges on unverified mid-move re-planning behavior.
Profiled segments do not rewrite goals mid-move: each segment completes before the next
command lands (trajectory JSONs like rotysquare separate moves with explicit 1 s pauses).
So Case A/B/C firmware semantics are irrelevant — **this approach is implementable
today** with no bench unknowns other than the speed-unit calibration.

### 10.3 Coverage vs. non-coverage

| Motion type | Covered by profiled segments? | Notes |
|---|---|---|
| Home / reposition / joint moves | ✅ Fully | Already proven smooth (Home path) |
| Paused multi-segment trajectories (rotysquare) | ✅ Well | rotysquare JSON has `pause: 1.0` after every move; each move is a ~1 cm displacement — ideal for single-goal segments |
| Jog | ⚠️ Partial | Velocity-mode jog doesn't map to single goals; keep 25 Hz loop with velocity-matched caps, or defer |
| Continuous weld paths / long straight lines | ❌ No | Path straightness + multi-joint coordination degrade; these keep dense streaming (gated on 9.4 + 9.5) |

### 10.4 Known costs and risks

1. **Path shape**: each joint runs an independent joint-space trapezoid; the EE path
   between endpoints is not a straight line. For ~1 cm segments, deviation is negligible.
   For long segments, unacceptable — those stay on dense streaming.
2. **Coordination**: equalizing per-joint arrival times via caps is approximate; arrival
   mismatch = transient path deviation. Mitigated by pauses; matters only for welds.
3. **No exact duration control**: segment runs "as fast as the caps allow" rather than
   the planned duration (exact duration needs the unverified Goal Time register). Pauses
   absorb the drift; trajectory playback duration will not match plan exactly.
4. **Backlash**: profiled segments make at most ONE direction reversal per segment
   (the decel-to-arrival), vs 100 direction-chasing jolts/sec in streaming mode.
   This directly attacks the reported oscillation.
5. **Speed unit calibration is the shared prerequisite** — the rad/s → LSB conversion is
   needed for both this stopgap and the long-term saturation streaming. Measure first.

### 10.5 Backend scoping

The profiled-segment policy is a **Feetech backend capability**:

- Feetech backend exposes `supports_profiled_segments` (property on `ActuatorBackend`
  ABC, default `False`; FeetechBackend overrides `True`) + a `plan_profiled_segment()`
  helper that converts a planned joint path (endpoint, per-joint velocity) into one
  sync_write command with computed caps.
- The shared trajectory executor asks the backend which policy to use per step type
  via `_backend_supports_profiled_segments()` (queries the active backend instance at
  runtime — never a string check or global constant); backends with real PVA support
  (future EtherCAT/Dynamixel) keep dense streaming.
- Simulation and other backends inherit current behavior — zero impact.

**Implementation status (Sprint 04):** Code complete. 21 gating-matrix tests pass
(`tests/test_profiled_segments.py`). Physical-arm validation pending.

### 10.6 Relationship between the two fixes

| | Profiled segments (this section) | Saturation streaming (9.2-9.5) |
|---|---|---|
| Implementable today | ✅ (after LSB calibration) | ⚠️ gated on 9.4 fork test |
| Path accuracy | endpoints only | full path |
| Best for | paused trajectories, P2P moves | continuous paths, welds, jog |
| Backend scope | Feetech only | Feetech only |

Recommended sequencing: **Sprint 04 (endpoint segments, immediate)** can ship first —
it needs no bench unknowns beyond a conservative flat cap, with LSB calibration
(Sprint 07 Part A) refining it. **Sprint 07 (fork test → cap sweep)** then decides the
long-term streaming question: its verdict determines whether continuous paths and jog
can ever migrate to saturation streaming, or whether the endpoint paradigm is permanent
for Feetech-class hardware.
