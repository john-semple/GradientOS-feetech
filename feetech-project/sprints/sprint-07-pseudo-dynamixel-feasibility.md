# Sprint 07 — Feasibility: Hacking the STS3215 into a Pseudo-Dynamixel

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

- [ ] Run diagnosis §9.4 protocol: long move (4016 → 3600, cap 300, accel 10); while
      `0x3A` shows cruise velocity, rewrite goal to 3400; log `0x38`, `0x3A`,
      moving flag (telemetry block 2 @ `0x41`) at ≥ 100 Hz
- [ ] Classify firmware behavior: A (velocity-continuous blend), B (re-plan from rest,
      velocity dip), or C (finish plan first, full stop at old goal)
- [ ] Repeat 3× to check consistency across trials
- [ ] Edge probes (only if case A or B confirmed):
      - [ ] Re-target at high rate (100 Hz) with cap ≈ stream velocity — does velocity
            stay continuous across many consecutive re-targets?
      - [ ] Direction reversal mid-move: rewrite goal behind current position while
            cruising — how does the profile handle reversal? (relevant to backlash)
- [ ] Record classification + traces in `feetech-project/docs/protocols/feetech-sts-scs.md`
      and update diagnosis §9.4 with the verdict

### Part C: Cap sweep on streamed motion (quantify the saturation regime)

- [ ] Stream a known linear move at 100 Hz; sweep cap {4095, 500, 100, 30, 10, floor};
      log `0x3A` magnitude at max feasible read rate
- [ ] Classify per-cap regime from velocity traces: stop-go (zero-crossings at stream
      rate) / continuous cruise / lag (position error growing)
- [ ] Record the cruise-transition cap and the lag floor

### Part D: Verdict

- [ ] Write the go/no-go: which firmware case was measured, and whether saturation
      streaming is viable (A: full go; B: conditional — quantify ripple; C: no-go)
- [ ] If GO/CONDITIONAL: specify the cap multiplier and stream-rate headroom for the
      streaming implementation; note that implementation becomes a future sprint
- [ ] If NO-GO: recommend the endpoint-paradigm path as permanent (not stopgap) for
      Feetech, and record that streaming requires different hardware

## Definition of done

- Speed LSB conversion measured and documented
- Mid-move re-target semantics classified (A/B/C) with traces, consistent across trials
- Cap-sweep curve documented (stop-go → cruise → lag boundaries)
- Go/no-go verdict written with tuning parameters (or a permanent-paradigm recommendation)
- `docs/jerkiness-diagnosis.md` §9.4 and §9.5 updated with measured results
- No production code changed

## Notes

- All bench tests use the existing guardrails: downward-only moves from ~4016, ≥10°
  moves for visibility, PSU current watched, safe-move recipe (seed goal, set accel/speed
  first, verify readback) before every motion.
- Do NOT pitch cap multipliers until Part B resolves the fork.
- If Part B yields case C, stop — Part C's streamed sweep is then only useful for
  documenting how bad current behavior is; the sweep's real value is under A or B.
- The quick fix (endpoint-paradigm motion) is deliberately OUT of this sprint — see
  Sprint 04 (quick fix). This sprint only answers "can we ever hack them into pseudo-Dynamixels?"

## Session log

| Date | Notes |
|------|-------|
| 2026-09-14 | Part A bench run completed on STS3215 ID `1` via `/dev/ttyUSB0` at 12.0 V. Operator reported smooth motion and boring PSU current. Logs saved under `feetech-project/data/part_a_traces/20260914_143947/`, `feetech-project/data/part_a_traces/20260914_144045/`, `feetech-project/data/part_a_floor_probe/20260914_144246/`, and `feetech-project/data/part_a_extended_slope/20260914_144403/`. Result: low-speed caps clamp at about cap `50`; direct `0.732 rpm/LSB` interpretation is refuted on this bench; above-floor measured speeds were about `9.0 deg/s` at cap `100`, `17.2 deg/s` at cap `200`, and `22.9 deg/s` at cap `300`. Part B remains the decisive firmware fork test. |
