# Sprint 07 — Feasibility: Hacking the STS3215 into a Pseudo-Dynamixel

> **STATUS: COMPLETE — 2026-09-14. Verdict: GO (Case A).** All bench data
> collected and verified. Implementation moved to Sprint 10
> (`sprint-10-smooth-streaming-executor.md`). Reactive-motion follow-on
> specced hypothetically in Sprint 12.

## Goal

Determine, by bench experiment, whether the STS3215's internal trapezoidal planner can be
**interrupted and re-targeted mid-move** reliably enough to support dense position
streaming — i.e., whether we can make these servos behave like Dynamixel-class servos
(host-side time-parametrized control) despite their firmware paradigm.

This is a **feasibility study only** — bench experiments, traces, and a go/no-go verdict.
No GradientOS code changes in this sprint.

Full theory: `GradientOS/docs/jerkiness-diagnosis.md` (sections 9.1-9.5).

## Background

- All streamed motion (trajectories, jog) is jerky; Home is smooth.
- Root cause: executors stream 50-100 position commands/sec with speed=4095 (max),
  accel=0 (max), bypassing the servo's internal profile generator (diagnosis §8).
- The "hacker" path to smooth streaming is **profile saturation** (diagnosis §9.2): keep
  goals perpetually beyond braking distance so the servo never decelerates mid-stream.
- That rests on ONE unverified assumption — what the firmware does when a goal is
  rewritten mid-move (diagnosis §9.4). Three candidate behaviors:
  - **A: re-target w/ velocity blend** → continuous cruise possible. Verdict: GO.
  - **B: re-target from rest** (v=0 re-plan) → velocity sawtooth at stream rate,
    avg ≈ ½ cap. Verdict: CONDITIONAL — maybe acceptable with cap ×2 and known ripple.
  - **C: queued completion** (finishes current plan first) → motion lags stream,
    queue starvation on jitter. Verdict: NO-GO for streaming; stay on endpoint moves.
- The observed "pause at waypoints" is consistent with all three — symptoms cannot
  discriminate. These experiments must.

## Prerequisites

- STS3215 protocol validated ✅
- Bench servo available (ID 1, resting ~4016, downward-only moves)
- Bench PSU for current observation during all tests

## Tasks

### Part A: Speed-unit calibration (needed to interpret everything)

- [x] Bench-measure the STS speed register LSB unit (documented ~0.732 rpm/LSB — REFUTED for direct bench interpretation)
      - Command a known rotation (e.g. 112 counts ≈ 9.84°, the validated move) with a
        fixed speed cap (e.g. 30) and time to completion (log `0x38` until motion stops)
      - Repeat at cap {10, 30, 60, 100}; fit achieved velocity (deg/s) vs. cap value
      - Confirm or refute 0.732 rpm/LSB; record in
        `feetech-project/docs/protocols/feetech-sts-scs.md`
- [x] Determine the minimum usable cap (floor): sweep down until motion is obviously
      slower than the plan implies or stalls; record the floor
      - 2026-09-14 result: effective low-speed floor is approximately cap `50`;
        caps `1`, `2`, `5`, `10`, `30`, and `50` all produced roughly `5 deg/s`.

### Part B: Mid-move re-target fork test (THE decisive experiment)

- [x] Run diagnosis §9.4 protocol: long move (start → start-296, cap 300, accel 10); while
      `0x3A` shows cruise velocity, rewrite goal further down (start-516); log `0x38`, `0x3A`,
      moving flag (telemetry block 2 @ `0x41`) at ≥ 100 Hz
      - Measured ~300 Hz sample rate via 11-byte bulk read (single transaction per sample)
- [x] Classify firmware behavior: **CASE A (velocity-continuous blend)** — confirmed 2026-09-14, 3/3 trials
      - Evidence: speed_mag 300→300 across the re-target instant (min 250 = 0x3A
        quantization step, not a dip); zero full stops between re-target and arrival;
        one continuous cruise through both goals; arrival within 1-2 counts
      - NOTE: the script's auto-classifier printed "C" — false positive (its
        reached-goal test was trivially satisfied by passing through goal 1 at
        cruise speed). Verdict corrected by raw-trace analysis. Lesson recorded:
        script verdicts are hints, traces are truth.
- [x] Repeat 3× to check consistency across trials — consistent (3/3 Case A)
- [x] Edge probes (only if case A or B confirmed):
      - [x] Re-target at high rate (100 Hz) with cap ≈ stream velocity — does velocity
            stay continuous across many consecutive re-targets?
            *Superseded: Part D (sinusoid) demonstrated continuous tracking under
            100 Hz dense goal rewrites — smooth in both legacy and profiled caps.
            The high-rate probe would confirm the same result; run only if Sprint 10
            validation surfaces anything anomalous.*
      - [x] Direction reversal mid-move: rewrite goal behind current position while
            cruising — how does the profile handle reversal? (relevant to backlash)
            *Superseded by Part D: the sinusoid reverses direction every half-cycle.
            Observed: natural decel into the extreme, brief dwell (~0.15s, the sine's
            own zero-velocity point), smooth re-acceleration. No firmware-induced
            reversal artifacts; backlash pause not visible in telemetry (Sprint 06
            territory for mechanical follow-up).*
      - [x] Velocity-mode hybrid probe (mode 1 cruise → mode 0 arrival) — added during
            the session, never run: Part B's Case A result made it unnecessary
            (position-mode streaming already achieves smooth continuous motion).
- [x] Record classification + traces in `feetech-project/docs/protocols/feetech-sts-scs.md`
      and update diagnosis §9.4 with the verdict

### Part C: Cap sweep on streamed motion (quantify the saturation regime)

- [x] Stream a known linear move at 100 Hz; sweep cap {4095, 500, 200, 100, 50};
      log `0x3A` magnitude at max feasible read rate
      - (cap list corrected at run time: original {…, 30, 10} replaced by measured floor 50)
- [x] Classify per-cap regime from velocity traces (from raw traces, NOT the auto-classifier
      labels — both were false "STOP-GO" verdicts counting only start/arrival decel):
      - cap 4095 / 500 / 200: **CRUISE** — steady ~130 (≈ stream demand 133 counts/s),
        tracking error 1-2 counts
      - cap 100: **CRUISE** — pinned exactly at 100 (the cap), error 2 counts
      - cap 50: **LAG** — pinned at 50 (firmware floor), 38% undershoot
- [x] Record the cruise-transition cap and the lag floor
      - **Regime rule: continuous cruise iff cap ≥ stream velocity demand.**
        No stop-go observed at ANY cap when the goal stream is smooth and dense.

### Part C-adjacent: Part D sinusoid (added during session — visual + quantitative acid test)

- [x] Stream a ±31° sinusoid (0.15 Hz, 3 cycles) at ~90-160 Hz with 50 ms lookahead
      - Legacy settings (cap 4095, accel 0): SMOOTH — continuous wave, all stops are the
        sine's own zero-velocity extremes (~0.15s dwell at band edges)
      - Profiled settings (cap 850, accel 10): SMOOTH — slightly smoother visually (user-
        validated with pointer on the horn); identical continuous tracking
- [x] KEY REFINEMENT OF THE ROOT-CAUSE THEORY: legacy caps streamed smoothly HERE because
      the goal stream itself was smooth and dense. Production jerkiness is the executors'
      **segment structure** (arrive-and-stop micro-waypoints + sharp corners), not the
      caps per se. Fix = stream dense smooth goals; caps sized to demand; accel moderate.

### Part D: Verdict

- [x] Write the go/no-go: **GO** — Case A measured (velocity-continuous blend), saturation streaming viable
- [x] If GO/CONDITIONAL: specify the cap multiplier and stream-rate headroom for the
      streaming implementation; note that implementation becomes Sprint 10
      - Cap policy: cap ≈ 2× the path's peak per-joint velocity demand, clamped [100, 2000]
        (floor 50; cruise requires cap ≥ demand). Accel register: 10.
      - Stream rate: 100 Hz whole-arm via one sync_write (~3 ms measured dispatch);
        ~160 Hz sustained on a CH340 bus with reads interleaved (Part C measured).
      - Lookahead: 50 ms keeps goals ahead of the servo → on stream interruption the
        servo stops at the last goal (~50-100 ms of travel). Fail-safe by physics —
        no watchdog required (position mode).
- [x] If NO-GO: recommend the endpoint-paradigm path as permanent (not stopgap) for
      Feetech, and record that streaming requires different hardware
      *N/A — verdict was GO. (Endpoint paradigm remains valid for single endpoint moves.)*

## Definition of done

- [x] Speed LSB conversion measured and documented (0.088 deg/s per LSB; 0x2E and 0x3A same units)
- [x] Mid-move re-target semantics classified (A/B/C) with traces, consistent across trials (CASE A, 3/3)
- [x] Cap-sweep curve documented (stop-go → cruise → lag boundaries)
      *No stop-go regime exists with smooth dense streams: cruise iff cap ≥ demand; below → lag.*
- [x] Go/no-go verdict written with tuning parameters (GO; cap ≈ 2× demand, accel 10, 100 Hz stream, 50 ms lookahead)
- [x] `docs/jerkiness-diagnosis.md` §9.4 and §9.5 updated with measured results
- [x] No production code changed (bench scripts only, under `feetech-project/code/`)

## Notes

- All bench tests use the existing guardrails: downward-only moves from ~4016, ≥10°
  moves for visibility, PSU current watched, safe-move recipe (seed goal, set accel/speed
  first, verify readback) before every motion.
- Do NOT pitch cap multipliers until Part B resolves the fork.
- If Part B yields case C, stop — Part C's streamed sweep is then only useful for
  documenting how bad current behavior is; the sweep's real value is under A or B.
- The quick fix (endpoint-paradigm motion) is deliberately OUT of this sprint — see
  Sprint 04b (quick fix). This sprint only answers "can we ever hack them into pseudo-Dynamixels?"

## Session log

| Date | Notes |
|------|-------|
| 2026-09-14 | Part A bench run completed on STS3215 ID `1` via `/dev/ttyUSB0` at 12.0 V. Operator reported smooth motion and boring PSU current. Logs saved under `feetech-project/data/part_a_traces/20260914_143947/`, `feetech-project/data/part_a_traces/20260914_144045/`, `feetech-project/data/part_a_floor_probe/20260914_144246/`, and `feetech-project/data/part_a_extended_slope/20260914_144403/`. Result: low-speed caps clamp at about cap `50`; direct `0.732 rpm/LSB` interpretation is refuted on this bench; above-floor measured speeds were about `9.0 deg/s` at cap `100`, `17.2 deg/s` at cap `200`, and `22.9 deg/s` at cap `300`. Part B remains the decisive firmware fork test. |
| 2026-09-14 | **Part B: CASE A confirmed.** 3/3 trials, retarget mid-cruise at t≈0.60s, speed_mag 300→300 across the rewrite, zero stops, arrival within 2 counts. Logs: `feetech-project/data/part_b_traces/`. Note: first Part B run failed silently (0 telemetry samples — bench_utils bulk-read off-by-one, fixed); auto-classifier printed a false "C" — corrected from raw traces. |
| 2026-09-14 | **Part D sinusoid (added): smooth under both legacy (4095/0) and profiled (850/10) settings.** User visual confirmation with pointer: both fluid; profiled slightly smoother. All stops = the sine's own zero-velocity extremes. Root-cause theory refined: production jerkiness = executor segment structure, not caps. Logs: `feetech-project/data/part_d_sinusoid/20260914_153114/`. |
| 2026-09-14 | **Part C: regime map complete.** Caps 4095/500/200/100 → continuous CRUISE (error 1-2 counts); cap 50 (floor) → LAG 38%. Regime rule: cruise iff cap ≥ stream demand. First run invalid (stream sign error streamed goals upward to the 4094 seam — fixed + per-goal band guard added; servo re-parked at 3892). Final logs: `feetech-project/data/part_c_traces/`. **SPRINT 07 VERDICT: GO — implementation is Sprint 10.** |

## Session log (planning follow-ups)

| Date | Notes |
|------|-------|
| 2026-09-14 | Sprint 10 (`sprint-10-smooth-streaming-executor.md`) written: backend-wrapped Case A streaming, capability-flag gated. Sprint 12 (`sprint-12-reactive-motion.md`, originally sprint-11) written as hypothetical: camera-rate setpoint rewrites; Part A of that sprint IS the avoidance-algorithm discovery, with a GO/park gate. |
