# TODO

## Current state

**Sprint 00 (Setup & Documentation):** Complete. Repo created, docs pushed, GradientOS forked and cloned.

**Sprint 01 (STS3215 Protocol Validation):** Complete. Full protocol doc, register map, measured electricals, safe-move recipe. Stall current measured 2026-09-08 (8 W spike under manual pull, ~0.67 A @ 12 V). See `sprints/archive/sprint-01-sts3215-protocol-COMPLETE.md`.

**Sprint 03 (Electronics Validation):** Complete. Test bench wired, STS3215 powered at 12V, idle current 299mA, no heat/smoke. USB passthrough to OpenChamber container implemented (Design B). Measurements documented in `docs/hardware/test-bench-wiring.md`.

**Sprint 02 (GradientOS Architecture Study):** Mostly complete — the deep study happened during the motion-jerkiness diagnosis. AI-taught architecture crash course written into the sprint file (two-axis selection, startup sequence, command path, motion pipeline, twin motors, HLS extension path, sharp edges). Remaining: fill the two stub docs in `docs/gradientos/`.

**STS3215 backend in GradientOS (old sprint, archived):** Complete — `STS3215Backend` ships in GradientOS at `src/gradient_os/arm_controller/backends/sts3215/` and drives the physical 8-servo arm daily via the web UI. See `sprints/archive/sprint-04-sts-backend-COMPLETE.md`.

**The arm:** Built, wired, and operational (8 servos, IDs 10/20/21/30/31/40/50/60). Runs through GradientOS (Home, jog, rotysquare trajectory). Known issue: motion jerkiness on streamed paths — diagnosis and fix plan in `GradientOS/docs/jerkiness-diagnosis.md`.

**GradientOS clones ready:**
- `GradientOS/` — fork (for edits), tracks `john-semple/GradientOS-feetech`
- `GradientOS-upstream/` — clean reference (pull-only)

## Next action

1. **Sprint 10 (Smooth Streaming Executor)** — up next. Migrate motion executors
   from arrive-and-stop waypoint streaming to continuous setpoint streaming with
   50 ms lookahead, wrapped entirely inside the backend. Exploits Case A firmware
   behavior measured in Sprint 07. See `sprints/sprint-10-smooth-streaming-executor.md`.
2. **Sprint 09 (GUI Improvements)** — after Sprint 10. Jog controls, calibration
   UI, config selector. Unblocked by Sprint 08b (test infra) complete. See
   `sprints/sprint-09-gui-improvements.md` for the full plan and safety rule
   (arm powered off during calibration-UI build; human present for first
   calibration/EEPROM runs).
3. **Sprint 05 (HLS3950)** — in progress. Servos bench-validated, not yet in the
   arm. Remaining: robot config, multi-servo test, app switching, decision log.

## Sprint plan (restructured 2026-09-15)

| Sprint | File | Status | Description |
|--------|------|--------|-------------|
| 05 | `sprint-05-hls3950.md` | 📖 In progress | **HLS3950: protocol validation + backend** — protocol confirmed (FT-SCS, same family as STS3215), backend implemented and bench-validated (1 servo: PING, read, move, SYNC_WRITE, SYNC_READ, profiled segment). Servos work but not yet in the arm. Remaining: robot config, multi-servo test, app switching, decision log |
| 06 | `sprint-06-paired-joints.md` | ⏸ Deferred | Paired-servo joint model with backlash offset (twin motors 20/21, 30/31) — saved for later |
| 08 | `sprint-08-full-arm-hardening.md` | ⏸ Not started | Full-arm hardening: power bus, udev stability, joint-limit verification, temperature soak, operator handoff doc |
| 08b | `sprint-08b-test-infrastructure.md` | ✅ Complete 2026-09-14 | Test infrastructure baseline: vitest suite for web UI (8 smoke tests + fetch mock), backend suite repaired (57 passed / 0 skipped — was 6 failed + whole API file silently skipped due to missing httpx). Unblocks Sprint 09. |
| 09 | `sprint-09-gui-improvements.md` | ⏸ Not started (after 10) | GUI improvements: jog controls, calibration UI, config selector |
| 10 | `sprint-10-smooth-streaming-executor.md` | ⏸ **Up next** | Smooth streaming executor (Case A setpoint streaming) — supersedes 04b endpoint paradigm |
| 11 | `sprint-11-automated-tool-change.md` | ⏸ Not started | Automated tool change system: coupler design, tool rack, change sequence, tool-aware motion |
| 12 | `sprint-12-reactive-motion.md` | 💤 Hypothetical | Reactive motion / obstacle avoidance (depends on 10 + vision stack) |

### Archived (complete)

- `sprints/archive/sprint-00-setup-COMPLETE.md` — Setup & documentation
- `sprints/archive/sprint-01-sts3215-protocol-COMPLETE.md` — STS3215 protocol validation
- `sprints/archive/sprint-02-gradientos-study-COMPLETE.md` — GradientOS architecture study
- `sprints/archive/sprint-03-electronics-COMPLETE.md` — Electronics validation
- `sprints/archive/sprint-04-sts-backend-COMPLETE.md` — STS3215 backend in GradientOS
- `sprints/archive/sprint-04b-endpoint-paradigm-quickfix-COMPLETE.md` — Endpoint-paradigm quick fix (smooth motion)
- `sprints/archive/sprint-07-pseudo-dynamixel-feasibility-COMPLETE.md` — Pseudo-Dynamixel feasibility study (verdict: GO)

### Sprint ordering / dependencies

```
10 (streaming executor) ── up next; supersedes 04b; unifies all motion
09 (GUI improvements) ──── after 10; jog/calibration/config UI on the 08b test base
08b (test infra) ──────── ✅ done 2026-09-14; prerequisite for 09
11 (tool change) ──────── after 08 + 10; needs precise repeatable motion
06 (paired joints) ────── deferred; complements motion mechanically (backlash preload)
08 (arm hardening) ────── not started; power/limits/safety
05 (HLS3950) ──────────── in progress; bench + backend, not in arm yet
12 (reactive motion) ──── hypothetical; depends on 10 + vision stack
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
- [x] ~~STS3215 mid-move re-target semantics: case A/B/C~~ — **resolved 2026-09-14**: CASE A (velocity-continuous blend), 3/3 bench trials. Streaming is GO (sprint-07 Part B)
- [x] ~~STS3215 speed register LSB unit~~ — **resolved 2026-09-14**: LSB ≈ 0.088 deg/s output-shaft (0x2E and 0x3A same units; documented 0.732 rpm/LSB = motor shaft pre-gearbox). Speed floor = 50. (sprint-07 Part A)