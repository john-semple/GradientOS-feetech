# Sprint 10 — Smooth Streaming Executor (Case A Setpoint Streaming)

## Goal

Migrate GradientOS's motion executors from arrive-and-stop waypoint streaming to
**continuous setpoint streaming with lookahead**, exploiting the Case A firmware
behavior measured in Sprint 07 — and wrap it **entirely inside the backend** so
the planner, command API, web UI, and weld planner require **zero changes**.

This replaces the current split-brain motion model (endpoint paradigm for paused
moves / dense streaming for everything else) with **one unified motion model**:
every motion is a dense, smooth goal stream; the final point is the only one
that means "stop."

## Background (all measured in Sprint 07, bench data complete)

- **Case A confirmed (Part B, 3/3 trials):** the STS3215 firmware blends
  mid-cruise goal rewrites into the running profile with velocity continuity.
  No stop, no re-plan from rest, no queued completion.
- **Part D:** a smooth dense goal stream produces smooth motion even with
  legacy settings (cap 4095, accel 0). Production jerkiness is the executors'
  *segment structure* (arrive-and-stop micro-waypoints), not the caps.
- **Part C:** continuous cruise iff cap ≥ stream velocity demand; below → lag.
  Measured at ~160 Hz actual write rate over one CH340 bus with reads
  interleaved — bus headroom is proven, not assumed.
- **Cap scale (Part A):** 0x2E LSB ≈ 0.088 deg/s; speed floor 50 LSB.
  0x3A feedback = same units, bit15 direction + 0x7FFF magnitude, steps of 50.
- **Fail-safe by physics:** on stream interruption the servo decelerates to the
  last written goal (~50–100 ms of travel with 50 ms lookahead). Position mode
  needs **no watchdog**; the short-horizon handoff bounds any app hang to
  horizon-time of motion (see scratchpad 2026-09-14 watchdog correction).

## Design (backend-owned streaming)

```
Planner ──(t, position) timed path──▶ Backend ──100–160 Hz setpoint stream──▶ Servos
                                      owns: pacing, 50 ms lookahead,
                                      per-segment cap sizing, accel 10,
                                      horizon expiry
```

The planner keeps doing exactly what it does today: produce timed
(position, velocity) profiles. The **timing ownership moves into the backend**:
a pacing thread converts the timed path into a dense setpoint stream.

### The streaming recipe (what the backend does per move)

1. Receive a timed path: list of (t, q[8]) samples covering the move.
2. Compute per-joint velocity demand from the path; set cap ≈ 2× the fastest
   joint demand (clamped [100, 2000]; floor 50 from Part A).
3. Write accel=10 once per move (bench safe recipe).
4. Pace at 100 Hz (measured sustainable with reads interleaved):
   write `position(t_now + 50 ms lookahead)` via sync_write for all 8 servos.
5. On path end: final point written once; firmware decelerates and arrives
   (endpoint accuracy preserved — servo still stops AT a goal).
6. Never write a goal outside the path's own joint-limit-safe envelope.

### Why no watchdog

Position mode + short horizon: if the app dies, goals stop arriving, the servo
stops at the last written goal (~50 ms of travel ahead). The only guard kept
is one line in the pacing loop: stop writing when `t > path_end` (buffer-replay
bug containment, not a safety system). A watchdog becomes mandatory only if
velocity mode is ever introduced.

## Prerequisites

- Sprint 07 complete ✅ (all bench data, verdicts, and calibrations in
  `feetech-project/data/part_*` + protocol doc)
- Sprint 04b capability-flag pattern established ✅ (21 gating tests)
- The arm for validation (rotysquare playback + a continuous move)

## Tasks

### Backend interface (GradientOS)

- [ ] Add `supports_setpoint_streaming` property to `ActuatorBackend` ABC,
      default `False` (Sprint 04b opt-in pattern — every backend inherits "off")
- [ ] Add `execute_timed_path(path, options) -> handle` to the ABC with a
      default implementation that raises `NotImplementedError` (backends
      without streaming keep their existing behavior untouched)
      - `path`: list of (t_seconds, joint_positions) tuples
      - `options`: optional per-joint velocity caps, accel override
      - returns a handle supporting `cancel()` and `is_done()`
- [ ] Implement in `STS3215Backend`:
      - [ ] Pacing thread: 100 Hz loop, 50 ms lookahead evaluation of the
            timed path (linear interpolation between samples)
      - [ ] Per-move cap sizing: max |Δq/Δt| over the path × 2, clamped
            [100, 2000] (units: 0x2E LSB via Part A scale)
      - [ ] accel 10 written once per move before the stream starts
      - [ ] `cancel()`: write current position as goal (stop in place),
            join thread
      - [ ] Horizon rule: stop writing goals when `t > path_end` (one line)
      - [ ] Stream guard: every written goal clamped to the path's own
            min/max per joint (Sprint 07 Part C lesson: validate EVERY
            streamed goal, not just endpoints)
- [ ] Simulation backend: `supports_setpoint_streaming = True` with a
      trivial implementation (interpolate the path on a timer so sim
      behavior stays equivalent)
- [ ] HLS3950 backend: inherits `False` (its firmware semantics are
      unstudied at stream rate — do NOT enable until a bench fork test
      like Sprint 07 Part B is run on HLS hardware)

### Executor migration (minimal surface)

- [ ] `_open_loop_executor_thread`: when `supports_setpoint_streaming` is
      true, hand the precomputed (t, q) path to `execute_timed_path` instead
      of pacing goal writes itself; dense waypoint streaming remains the
      fallback for backends without the capability
- [ ] `move_line` / weld moves: same handoff (this sprint finally covers the
      continuous-path case that Sprint 04b explicitly excluded)
- [ ] Jog loop: keep its existing structure (it already streams at a
      sustainable rate); optionally migrate if the handle API fits naturally —
      NOT a blocker
- [ ] `joint_move` steps: keep `execute_profiled_segment` for single
      endpoint moves (a one-point stream is the degenerate case; the existing
      path is simpler and already smooth)

### Validation (gating matrix — Sprint 04b pattern, explicit tests)

- [ ] `--servo-backend sts3215 --robot gradient0` → setpoint streaming ACTIVE
- [ ] `--servo-backend simulation --robot gradient0` → streaming path
      executes equivalently (timing behavior preserved in sim)
- [ ] No backend active (legacy servo_protocol path) → unchanged
- [ ] HLS3950 → dense streaming unchanged (capability off)
- [ ] Cancel handle: cancel mid-move stops the arm within ~100 ms, holds
      position (no runaway)
- [ ] App-hang simulation: stop extending/feeding paths → arm stops within
      path_end + lookahead; no continued motion (fail-safe by physics)

### Bench validation (physical arm)

- [ ] Rotysquare playback: as smooth as Sprint 04b endpoint mode (user visual)
- [ ] Continuous `move_line` (the Sprint 04b gap): EE path continuous,
      no per-waypoint hesitation, PSU peak ≤ the ~10 A already observed
- [ ] Long diagonal multi-joint move: no joint oscillation, arrival within
      normal tolerance
- [ ] Optional comparison capture: bulk-telemetry log during one move for
      the archive (0x3A continuity check as in Part D)

### Documentation

- [ ] Update `docs/jerkiness-diagnosis.md`: §9.4/9.5 with Sprint 07
      measured results (Case A verdict + cap map) — *can be done before
      implementation; data is complete*
- [ ] Update diagnosis §10/§11: endpoint paradigm is superseded as the
      general motion model (remains valid for single endpoint moves)
- [ ] Decision log: timing ownership moved into the backend; unified
      motion model rationale
- [ ] Update `feetech-project/TODO.md` sprint table + this sprint's
      checkboxes as items land

## Definition of done

- All motion types (trajectories, move_line, weld) run as continuous
  setpoint streams behind the capability flag; no stop-go at any cap ≥ demand
- Planner, command API, web UI, weld planner: zero changes
- Gating matrix tests pass (sts3215 active / sim equivalent / legacy
  unchanged / HLS unchanged)
- Cancel + app-hang fail-safes demonstrated
- User-validated smooth on physical arm (rotysquare + continuous line)
- Docs + decision log updated

## Risks / notes

- The pacing thread runs inside the controller process; GIL contention with
  IK/vision threads is the main performance risk. Mitigation: the loop is
  tiny (interpolate + one sync_write); measure actual write rate first thing
  on the arm — Part C sustained ~160 Hz with reads interleaved.
- CH340 ~3 ms/transaction floor (measured): the 100 Hz whole-arm stream plus
  periodic reads fits with headroom, but do not add extra per-cycle reads
  without checking the budget.
- Per-joint caps are computed from the path itself (max demand × 2) — no
  user tuning required; overrides available via `options`.
- The velocity-mode hybrid and any watchdog machinery are explicitly OUT of
  scope: position mode's stop-at-last-goal behavior is the fail-safe
  (scratchpad 2026-09-14).
- If the HLS3950 is ever migrated to streaming, it needs its own Sprint 07
  Part B fork test first (its firmware is a different revision).