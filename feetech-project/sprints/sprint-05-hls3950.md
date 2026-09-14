# Sprint 05 — HLS3950 Protocol Validation & Backend in GradientOS

## Goal

Identify the HLS3950 servo protocol (the biggest hardware unknown in the project), then implement a Feetech HLS3950 servo backend in GradientOS and test it on the bench.

## Prerequisites

- STS3215 backend working in GradientOS (archived: archive/sprint-04-sts-backend-COMPLETE.md) — pattern established
- Second URT-1 adapter (if HLS3950 needs a different channel/adapter)
- HLS3950 servo(s) on hand

> The HLS3950 protocol validation (originally Sprint 02 Part B in the pre-restructure plan; now sprint-01 is the completed STS protocol sprint) now lives in this sprint.
> It must complete before the Implementation section below can be planned concretely.

## Tasks

### HLS3950 protocol validation

#### Research
- [x] Search for HLS3950 or HLS series protocol documentation online — found at wiki.aifitlab.com
- [x] Check Feetech FD software / wiki for HLS support — Feetech wiki has full HLS memory table
- [x] Look for community projects using HLS servos — none found (GitHub search empty)
- [x] If no docs: use logic analyzer to capture Feetech app → servo traffic — not needed, wiki has full docs

#### Determine physical interface
- [x] Is it TTL (3-pin) or RS485 (4-pin)? — **TTL single-wire (3-pin), same as STS3215**
- [x] Does it connect to the URT-1's SCS/TTL port, SMS/RS485 port, or neither? — **SCS/TTL port, confirmed working**
- [x] If not URT-1 compatible, identify the correct adapter — not needed, URT-1 works

#### Minimal code (if protocol discovered)
- [x] Write minimal Python script for HLS3950
- [x] PING, read model, read position, command small move — all confirmed on bench (ID 30, firmware 3.43)
- [x] Same validation sequence as STS3215

#### Document protocol findings
- [x] Fill in docs/protocols/feetech-hls.md with confirmed protocol details
- [x] Fill in docs/hardware/servo-specs/HLS3950.md with measured values
- [x] Record whether HLS shares SCS protocol or is separate — **same FT-SCS protocol family, different register map**

### Implementation
- [ ] ~~If HLS shares the SCS protocol: extend the STS3215 backend~~ — same protocol family but separate backend created per user decision
- [x] If HLS uses a new protocol: implement a new backend following the STS3215 pattern
- [x] Map GradientOS joint commands → HLS protocol writes
- [x] Map HLS protocol reads → GradientOS feedback
- [ ] Create a robot configuration for the HLS3950 arm — backend registered; robot config variant pending

### Testing (bench scale)
- [x] Test with 1 HLS3950 servo: ping, read, command moves — confirmed (ID 30, firmware 3.43)
- [ ] Test with 2 servos if available
- [x] Verify feedback flows back to GradientOS — SYNC_READ, telemetry, moving flag confirmed
- [ ] Confirm the app can switch between STS3215 and HLS3950 configs — pending full-arm integration

### Document
- [x] Document the HLS3950 backend implementation
- [x] Record differences from the STS3215 backend
- [ ] Update decision log

## Definition of done

- [x] HLS3950 backend works in GradientOS
- [x] 1 servo controlled (PING, read, move, SYNC_WRITE, SYNC_READ, profiled segment)
- [ ] App can switch between STS3215 and HLS3950 arm configs
- [ ] Code committed to the GradientOS fork

## Notes

- The HLS3950 uses the same FT-SCS protocol family as the STS3215.
- **Critical difference:** SYNC_WRITE layout differs (0x2C = Target Current on HLS; writing 0 disables motor). HLS backend starts at 0x2A with 6 bytes + non-zero current; STS starts at 0x29 with 7 bytes + zeros for Time.
- EEPROM angle limits are factory-restricted (1024-3071), not unrestricted 0-4095 like STS3215.
- Calibration via 0x0B instruction only (no torque-switch 128 shortcut).
- Same constraint: keep paired servos as independent actuators.