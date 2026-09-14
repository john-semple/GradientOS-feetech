# TODO

## Current state

**Sprint 00 (Setup & Documentation):** Complete. Repo created, docs pushed, GradientOS forked and cloned.

**Sprint 01 (STS3215 Protocol Validation):** Complete. Full protocol doc, register map, measured electricals, safe-move recipe. Stall current measured 2026-09-08 (8 W spike under manual pull, ~0.67 A @ 12 V). See `sprints/sprint-01-sts3215-protocol.md` (marked complete in place).

**Sprint 03 (Electronics Validation):** Complete. Test bench wired, STS3215 powered at 12V, idle current 299mA, no heat/smoke. USB passthrough to OpenChamber container implemented (Design B). Measurements documented in `docs/hardware/test-bench-wiring.md`.

**Sprint 02 (GradientOS Architecture Study):** Mostly complete — the deep study happened during the motion-jerkiness diagnosis. AI-taught architecture crash course written into the sprint file (two-axis selection, startup sequence, command path, motion pipeline, twin motors, HLS extension path, sharp edges). Remaining: fill the two stub docs in `docs/gradientos/`.

**STS3215 backend in GradientOS (old sprint, archived):** Complete — `FeetechBackend` ships in GradientOS at `src/gradient_os/arm_controller/backends/feetech/` and drives the physical 8-servo arm daily via the web UI. See `sprints/archive/sprint-04-sts-backend-COMPLETE.md`.

**The arm:** Built, wired, and operational (8 servos, IDs 10/20/21/30/31/40/50/60). Runs through GradientOS (Home, jog, rotysquare trajectory). Known issue: motion jerkiness on streamed paths — diagnosis and fix plan in `GradientOS/docs/jerkiness-diagnosis.md`.

**GradientOS clones ready:**
- `GradientOS/` — fork (for edits), tracks `john-semple/GradientOS-feetech`
- `GradientOS-upstream/` — clean reference (pull-only)

## Next action

1. **Sprint 04 (Endpoint-Paradigm Quick Fix)** — USER-VALIDATED. Smooth motion confirmed on physical arm (rotysquare). ~10 A PSU peak (~120 W @ 12 V). Code complete: 21 gating tests pass. Remaining items: `move_line` with pauses test, quantitative endpoint accuracy measurement, decision log entry.
2. **Sprint 07 (Pseudo-Dynamixel Feasibility)** — bench-only study (speed LSB calibration + mid-move re-target fork test + cap sweep); can run before or alongside Sprint 04; its verdict decides the long-term streaming architecture for weld paths and jog.
3. Requires: GradientOS Python environment set up in container (Dockerfile rebuild pending — see Cursor handoff instructions)

## Sprint plan (restructured 2026-09-08)

| Sprint | File | Status | Description |
|--------|------|--------|-------------|
| 00 | `sprint-00-setup.md` | ✅ Complete | Setup & documentation |
| 01 | `sprint-01-sts3215-protocol.md` | ✅ Complete | STS3215 protocol validation (restored from archive at user request) |
| 02 | `sprint-02-gradientos-study.md` | 📖 ~90% | GradientOS architecture study — crash course written; remaining: fill `docs/gradientos/` stubs |
| 03 | `sprint-03-electronics.md` | ✅ Complete | Electronics validation — wire test bench safely |
| 04 | `sprint-04-endpoint-paradigm-quickfix.md` | ✅ User-validated (smooth) | **Quick fix: endpoint-paradigm motion** — one goal per segment, strictly gated by `supports_profiled_segments` backend capability (Feetech only; all other backends unaffected). Code implemented, 21 gating tests pass, user-validated on physical arm (smooth motion, ~10 A PSU peak). Remaining: `move_line` test, endpoint accuracy measurement, decision log |
| 05 | `sprint-05-hls3950.md` | 📖 In progress | **HLS3950: protocol validation + backend** — protocol confirmed (FT-SCS, same family as STS3215), backend implemented and bench-validated (1 servo: PING, read, move, SYNC_WRITE, SYNC_READ, profiled segment). Critical fix: 0x2C = Target Current on HLS, writing 0 disables motor — SYNC_WRITE layout differs from STS. Remaining: robot config, multi-servo test, app switching, decision log |
| 06 | `sprint-06-paired-joints.md` | ⏸ Not started | Paired-servo joint model with backlash offset (twin motors 20/21, 30/31) |
| 07 | `sprint-07-pseudo-dynamixel-feasibility.md` | ⏸ Not started | **Feasibility study (bench only, no code):** can STS3215 trapezoid planning be interrupted/re-targeted mid-move (pseudo-Dynamixel streaming)? Verdict: GO / CONDITIONAL / NO-GO |
| 08 | `sprint-08-full-arm-hardening.md` | ⏸ Not started | Full-arm hardening: power bus, udev stability, joint-limit verification, temperature soak, operator handoff doc |

### Archived (complete)

- `sprints/archive/sprint-04-sts-backend-COMPLETE.md` — STS3215 backend in GradientOS

### Sprint ordering / dependencies

```
04 (quick fix, Feetech-gated) ──┐ motion smooth now
07 (feasibility bench study) ───┤ verdict decides long-term streaming
                                └──▶ possible future sprint: saturation streaming for weld/jog
06 (paired joints) ── independent; complements 04 mechanically (backlash preload)
08 (arm hardening) ── after 04; power/limits/safety
05 (HLS3950) ──────── independent; bench + backend work for the HLS servo line
```

## Blocked items

- [x] ~~Docker USB passthrough~~ — **resolved via Design B (udev mirror + bind-mount), see `usb/README.md`**
- [ ] GradientOS Python environment in container — Dockerfile rebuild needed (build-essential, cmake, python3-dev, uv + venv install). Instructions prepared for Cursor.
- [ ] Physical USB unplug/replug test — passthrough propagation verified via node add/remove, but real plug pull not yet done. Check `journalctl -t openchamber-usb-mirror` after. (Now tracked in sprint-08.)
- [x] HLS3950 protocol research — **resolved**: same FT-SCS protocol family as STS3215, confirmed from wiki.aifitlab.com. Backend implemented and bench-validated (see sprint-05-hls3950.md)

## Open questions to resolve

- [x] ~~Confirm URT-1 USB port type~~ — **confirmed Micro USB**
- [x] ~~Confirm STS3215 is 12V variant~~ — **confirmed 12V**
- [x] ~~HLS3950 protocol family, physical interface, and URT-1 compatibility~~ — **resolved**: FT-SCS protocol (same family as STS3215), TTL single-wire, URT-1 SCS/TTL port confirmed working
- [ ] STS3215 mid-move re-target semantics: case A/B/C (sprint-07 Part B — the decisive experiment)
- [ ] STS3215 speed register LSB unit — documented ~0.732 rpm/LSB, unverified (sprint-07 Part A)