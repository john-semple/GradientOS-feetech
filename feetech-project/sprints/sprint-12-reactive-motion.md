# Sprint 12 — Reactive Motion: Camera-Rate Obstacle Avoidance (HYPOTHETICAL)

> **Status: hypothetical / not scheduled.** This sprint depends on (a) Sprint 10
> landing (setpoint streaming executor), and (b) the camera/vision stack
> reaching "obstacle state at frame rate" capability. The avoidance
> **algorithms do not exist yet** — Part A of this sprint IS the algorithm
> work. Everything after Part A is provisional and will be reshaped by what
> Part A produces.

## Goal

Give the arm the ability to **see an obstacle and bend its motion around it
without stopping** — camera-rate setpoint rewrites over the Sprint 10 streaming
executor, exploiting Case A blending so that avoidance is "curve away," never
"abort and replan from rest."

Target reaction chain (measured budget, Sprint 07 + vision estimates):

```
camera frame ──20–50 ms──▶ obstacle state ──1–5 ms──▶ avoidance ──▶ IK ──▶ ~3 ms sync_write
──────────────────────────── total ~30–60 ms ────────────────────────────────
```

15–30 Hz effective reaction rate. At typical EE speeds that is ~50 mm of travel
per reaction cycle — comfortable for cooperative-speed avoidance of a second
arm; NOT fast enough for a human hand at full speed (physical e-stop stays
mandatory; the bus can torque-off all servos in one ~3 ms packet if a hardware
trip is ever added).

## What we have (already proven, no bench work needed)

- Case A: setpoint rewrites bend motion with velocity continuity (Sprint 07)
- Whole-arm dispatch: one sync_write, ~3 ms (measured)
- Position differencing at 50 ms window → ~1.8 deg/s velocity estimates at
  zero extra bus cost (bulk read already carries 0x38) — needed for damped
  correction, not for streaming itself
- Short-horizon handoff: app extends the path, backend streams it; if the
  app stops extending, motion stops within horizon-time (fail-safe by
  physics — no watchdog needed)

## What does NOT exist yet (the point of this sprint)

1. **Obstacle representation:** how a camera frame becomes "stuff the arm must
   not touch" — bounding volumes? occupancy grid? point cloud clusters?
2. **Avoidance policy:** how a target velocity/position is modified to dodge
   obstacles — artificial potential fields? velocity obstacles? repulsive
   gradients over the occupancy map? Each has very different compute and
   tuning profiles on the RevPi.
3. **Prediction:** single-frame obstacle state gives ~50 ms of blind travel;
   constant-velocity prediction of the obstacle buys 1–2 frames of margin.
   Necessary at these latencies? Unknown.
4. **IK feasibility under avoidance:** avoidance reshapes the EE path;
   joint-limit and singularity behavior under continuous reshaping is untested.

## Tasks

### Part A — Algorithm discovery (the real work; everything else waits on it)

- [ ] **A1. Obstacle state contract.** Define the interface between vision
      and motion: what structure, at what rate, with what latency stamp.
      Candidate: list of oriented bounding boxes in the robot frame,
      timestamped, at camera rate (30 Hz class).
      - Input needed: what the vision stack can actually produce
        (detection latency, frame rate, coordinate transform quality)
      - Deliverable: a dataclass + a fake producer (synthetic obstacles
        moving on scripted paths) so motion-side work can start WITHOUT
        cameras
- [ ] **A2. Avoidance policy selection — evaluate 2–3 candidates in sim.**
      This is a design experiment, not implementation:
      - [ ] **Repulsive velocity fields** (classic artificial potential):
            add obstacle-avoidance velocity ∝ 1/distance² to the commanded
            EE velocity. Simple, cheap (~sub-ms), but local-minima behavior
            (obstacle exactly between arm and goal) must be characterized.
      - [ ] **Velocity obstacles / ORCA-class**: compute the set of EE
            velocities that collide within the horizon, project the
            commanded velocity out of it. More principled for MOVING
            obstacles (the other arm), moderately more compute.
      - [ ] **Occupancy-grid gradient descent** (if a voxel/occupancy
            representation falls out of A1): continuous gradient descent to
            goal through the grid. Most general, most compute, likely
            overkill for 2 arms.
      - Evaluation criteria (in the simulation backend, no hardware):
            reaction shape quality (no path chatter), compute time vs the
            33 ms frame budget, behavior when the obstacle crosses the path
            vs blocks the goal, tuning knob count
      - Deliverable: chosen policy + sim evidence + tuned parameters +
            written rationale (decision log)
- [ ] **A3. Prediction decision.** Test whether constant-velocity obstacle
      prediction is needed for the chosen policy at the measured latency —
      sim experiment: sweep obstacle speeds, with/without prediction,
      measure clearance margins. Keep prediction ONLY if margins demand it.
- [ ] **A4. Joint-space vs task-space avoidance.** The camera sees the EE
      region, but the arm's links also collide. Decide: EE-point avoidance
      only (simplest; fine for reaching past one obstacle) vs per-link
      avoidance (capsule model per link — more IK complexity). Sim evidence
      decides; EE-point first if unclear.
- [ ] **A5. Reaction-loop integration design.** Specify how the avoidance
      layer feeds the Sprint 10 stream:
      - Jog-style loop: each cycle, integrate commanded EE velocity →
        apply avoidance policy → IK → extend the timed path handed to the
        backend (sliding horizon ~200–300 ms)
      - The backend API from Sprint 10 needs a `replace_remaining_path()`
        (or equivalent) on the handle — small extension, spec it here,
        implement in Sprint 10 if it lands first
      - Abort semantics: what clears avoidance state; what happens when the
        obstacle leaves (path relaxes back? finish on the dodged path?)
- [ ] **A6. Gate review.** With A1–A5 written: decide GO / reshape / park.
      If the policy needs more compute than the RevPi has, or the vision
      contract can't be met with available cameras, PARK this sprint and
      record why. No implementation debt on an unproven algorithm.

### Part B — Implementation (only after A6 GO)

- [ ] Obstacle-state consumer in the controller (thread-safe, timestamped,
      latest-wins; never blocks motion on a missing frame)
- [ ] Chosen avoidance policy integrated per A5's design
- [ ] `replace_remaining_path` on the streaming handle (Sprint 10 backend)
- [ ] Velocity estimator helper (`get_velocity()` via 50 ms position
      differencing — rolling deque in servo_driver, few lines)
- [ ] Damped correction: nudge next setpoints by a fraction of observed
      position error while streaming (uses the velocity/position feedback
      already in the bulk read)
- [ ] Vision pipeline: camera → detection → robot-frame transform →
      A1's contract (depends on vision stack readiness; can be faked with
      A1's synthetic producer for motion-side testing)

### Part C — Validation (sim first, then bench)

- [ ] Sim: scripted obstacle crossings — path bends, no chatter, no stall
      in local minima (per A2's chosen policy), goal still reached
- [ ] Sim: obstacle blocking the goal — arm holds at safe distance (or
      defined give-up behavior), recovers when it clears
- [ ] Sim: moving obstacle (constant-velocity second arm model) — clearance
      maintained across approach angles; prediction on/off per A3 verdict
- [ ] Sim: frame dropouts (vision stalls 200 ms) — arm behavior degrades
      gracefully (holds/finishes conservative path), never runs away
- [ ] Bench (single arm + synthetic obstacles): obstacle state injected via
      the fake producer, physical arm bends around a virtual obstacle;
      PSU watched, guardrails per Sprint 07 bench practice
- [ ] Bench: two-arm dry run ONLY if the second arm exists and both run
      Sprint 10 — otherwise this is the explicit stop point
- [ ] Latency budget measured end-to-end on the real stack; compared to
      the 30–60 ms target; recorded

## Definition of done

- Part A: policy chosen with sim evidence; contract + integration design
  written; GO/park decision recorded with rationale
- Part B (if GO): avoidance bends paths at camera rate behind the capability
  flag; no motion without vision frames is degraded, never dangerous
- Part C (if GO): sim scenarios pass; single-arm bench demo of bending
  around a synthetic obstacle; latency budget measured and documented
- Everything above the backend unchanged except the avoidance loop itself
  (new module) — planner/weld/UI untouched

## Risks / notes

- **The algorithm work is the sprint.** Budget A1–A6 generously; Parts B/C
  are conventional once A lands. If A stalls, park the sprint — the unified
  streaming architecture from Sprint 10 loses nothing by waiting.
- RevPi compute: YOLO detection + avoidance + IK + 100 Hz stream all on one
  board — the A2 compute criterion exists precisely for this. If it doesn't
  fit, options are a smaller detection model, lower frame rate, or moving
  vision to a companion computer (contract A1 already anticipates this).
- Local minima are the classic failure of the simplest policies; A2 must
  test the "obstacle directly between arm and goal" case explicitly.
- Safety invariant regardless of policy: avoidance may only ever modify
  velocity/target within joint limits and the stream envelope — the Sprint 10
  per-goal clamp is the enforcement point.
- Physical e-stop remains the human-safety device for fast intrusions;
  camera-rate avoidance is for cooperative-speed machine-to-machine motion
  (the stated two-arm use case), not human-rated safety.
- This sprint assumes Sprint 10's handle API; if `replace_remaining_path`
  gets built into Sprint 10 directly, Part B shrinks.