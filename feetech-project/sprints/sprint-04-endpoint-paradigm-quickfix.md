# Sprint 04 — Quick Fix: Endpoint-Paradigm Motion (Feetech-Scoped)

## Goal

Eliminate the reported jerkiness for real arm motion NOW by commanding the STS3215 the
way its firmware is designed to be commanded: **one goal endpoint per move segment with
moderate speed/accel, letting the servo's internal trapezoidal profiler run the
segment** — the Home-button pattern, generalized to all moves.

No new bench unknowns required. No changes to non-Feetech backends.

Full theory: `GradientOS/docs/jerkiness-diagnosis.md` (sections 8 and 10).

## Background

- Root cause of jerkiness: executors stream 50-100 position commands/sec with
  speed=4095 (max), accel=0 (max), bypassing the internal profile generator (§8).
- Home is smooth because it sends ONE goal at moderate speed/accel and lets the
  firmware profile the whole move (§7).
- Endpoint-paradigm motion (§10) reproduces that for every move type it covers:
  each servo makes at most ONE direction reversal per segment (the decel-to-arrival)
  instead of 100 direction-chasing jolts/sec — directly attacking the backlash
  oscillation and spring-stall reports.
- This is the immediate fix while Sprint 07 (pseudo-Dynamixel feasibility) determines whether dense streaming
  (pseudo-Dynamixel mode) can ever work on this servo.

## Coverage (what this fix does and does not solve)

| Motion type | Covered? | Notes |
|---|---|---|
| Home / reposition / joint moves | ✅ | Already the smooth path; formalized |
| Paused multi-segment trajectories (rotysquare) | ✅ | ~1 cm moves with 1 s pauses — each move becomes one profiled segment |
| Continuous weld paths / long straight lines | ❌ | Path shape degrades; stay on dense streaming until Sprint 07 verdict |
| Jog | ❌ (unchanged) | Velocity-mode jog doesn't map to endpoints; revisit after Sprint 07 |

## Prerequisites

- STS3215 protocol validated ✅ (sprint-01-sts3215-protocol.md, marked complete)
- Sprint 07 Part A speed-unit calibration **recommended first** (caps sized in rad/s need
  the LSB conversion) — but a flat conservative cap (e.g. 500/accel 10) can ship first
  and be refined when calibration lands
- The arm for validation (rotysquare playback)

## Tasks

### Implementation (Feetech-scoped — MANDATORY backend gating)

> **Scope rule: this fix activates ONLY where the active backend explicitly declares
> the capability.** The endpoint paradigm is a property of Feetech-class firmware
> (internal trapezoidal profiler). It must NOT change behavior for simulation, HLS,
> EtherCAT, or any future backend — those keep dense streaming until their own
> firmware semantics are studied. Every code path below checks the flag; nothing is
> keyed off "is Feetech" string checks or global constants.

- [x] Add `supports_profiled_segments` to the `ActuatorBackend` ABC with default
      `False` (property returning False — every existing and future backend inherits
      "off" automatically; opt-in only)
- [x] Override `supports_profiled_segments = True` **on FeetechBackend only**
      (`backends/feetech/driver.py`)
- [x] Shared executor policy queries the flag at runtime via the active backend
      instance — never a hardcoded backend name; if no backend is active (legacy
      servo_protocol path), behavior is unchanged (dense streaming)
- [x] Verify the gating matrix (explicit tests, not assumptions):
      - [x] `--servo-backend feetech --robot gradient0` → profiled segments ACTIVE
      - [x] `--servo-backend simulation --robot gradient0` → dense streaming (unchanged)
      - [x] `--servo-backend simulation --robot <any other>` → unchanged
      - [x] Any robot config with `default_servo_backend != "feetech"` → unchanged
- [x] Add a `plan_profiled_segment(start_q, end_q, per_joint_velocities) → sync_write
      command` helper to the Feetech backend (backend-local; not in the ABC):
      - [x] Compute per-joint delta (rad) and pick slowest joint as duration-setter
      - [x] Convert per-joint velocity (rad/s) → speed register LSB using Sprint 07
            Part A calibration (or interim flat cap until then)
      - [x] Use moderate fixed accel register (10, per bench safe-move recipe)
- [x] Shared executor policy (minimal change):
      - [x] For `joint_move` steps and trajectory `move` steps with pauses (rotysquare
            pattern), query backend `supports_profiled_segments`; if true, collapse the
            dense path to ONE endpoint command instead of streaming
      - [x] Dense streaming remains the fallback for backends without the capability
      - [x] `move_line` / weld paths keep dense streaming until Sprint 07 verdict
- [x] Jog loop unchanged in this sprint

### Validation

- [x] Home button: confirm unchanged (already endpoint-paradigm — no code path changed)
- [x] rotysquare end-to-end: each `move_absolute` executes as one profiled segment;
      smoothness confirmed — no stop-go at waypoints, no oscillation (user-validated
      on physical arm 2026-09-11)
- [ ] Straight-line `move_line` with pauses: verify EE path stays acceptable at ~1 cm
      segment scale *(needs physical arm — not yet tested)*
- [x] Simulation backend regression: no behavior change (21 gating tests pass)
- [x] Watch PSU on arm moves: highest amperage spike observed ~10 A (~120 W @ 12 V)
      during profiled-segment motion (user-validated 2026-09-11). No streaming
      baseline was measured for direct comparison; the ~8 W figure in the sprint
      spec was a stall-test reading, not a streaming-motion reading. 10 A peak is
      within the PSU's capability and did not trip protection.

### Document

- [x] Update `docs/jerkiness-diagnosis.md` §10 with implementation notes and results
- [x] Update `feetech-project/TODO.md` sprint table
- [ ] Decision log: capability-flag pattern chosen so endpoint-paradigm is a Feetech
      policy, not a global architecture change *(pending — decision log entry)*

## Definition of done

- [x] Paused trajectories (rotysquare) and joint moves run smooth via endpoint paradigm
- [ ] Endpoint accuracy acceptable (no position error accumulation across segments)
      *(not yet explicitly measured — user reports smooth motion; quantitative
      endpoint accuracy check pending)*
- [x] Simulation backend verified unchanged
- [x] Capability flag documented; other backends untouched
- [x] User-validated on the physical arm (the reported symptom is gone)

## Notes

- Keep the change surface minimal: this is the immediate-uptime fix, not the final
  architecture. Sprint 07's verdict decides the long-term streaming question.
- If Sprint 07 returns case A (velocity blend), the natural follow-up sprint migrates
  weld paths/jog to saturation streaming; this endpoint path then remains for paused
  trajectories where it is inherently well-suited.
- If Sprint 07 returns case C, this endpoint paradigm becomes the PERMANENT Feetech
  approach and the docs should be updated accordingly.
- Per-joint cap sizing rationale (slowest joint sets duration, others scaled to match
  arrival times) is in diagnosis §10.1.
- All bench validation uses existing guardrails: downward-first moves, PSU watched,
  safe-move recipe before every motion.