# Sprint 04 — STS3215 Backend in GradientOS

> **COMPLETE — archived 2026-09-08.** The Feetech backend ships in GradientOS at
> `src/gradient_os/arm_controller/backends/sts3215/` (config.py, protocol.py, driver.py)
> and drives the physical 8-servo arm daily through the web UI. Checkbox pass below
> reflects what was actually done. This sprint was renumbered from 04 during the
> 2026-09-08 sprint-plan restructure (now: paired joints is sprint-04).

## Goal

Implement a Feetech STS3215 (SCS/STS protocol) servo backend in GradientOS and test it on the bench with 1-2 servos.

## Tasks

### Setup
- [x] Create a fork of GradientOS on GitHub (`GradientOS-feetech`, origin of this repo)
- [x] Add fork as remote in the local GradientOS clone
- [x] Create a feature branch for the STS3215 backend (work happens on fork branches)

### Implementation
- [x] Implement the servo backend interface using SCS/STS protocol (`STS3215Backend(ActuatorBackend)` in `backends/feetech/driver.py`)
- [x] Map GradientOS joint commands → SCS protocol writes (position, speed, torque) (`prepare_sync_write_commands`, `set_joint_positions`)
- [x] Map SCS protocol reads → GradientOS feedback (position, load, temperature) (`sync_read_positions`, `sync_read_block` + telemetry parsing in `backends/feetech/config.py`)
- [x] Create a robot configuration that uses the STS3215 backend (`robots/gradient0/config.py`, `default_servo_backend="feetech"`)
- [x] Ensure paired servos are independent actuators (not master/slave) (twin motors 20/21, 30/31 commanded individually; feedback read from primary, mirrored — backlash offset is the paired-joints sprint)

### Testing (bench scale)
- [x] Test with 1 servo: ping, read, command moves through GradientOS (single-servo validation in `feetech-project/code/hello_world_j1.py`, `sense_motion.py`)
- [x] Test with 2 servos: independent commands, no interference (extended naturally to all 8: `hello_world_all_joints.py`, `coordinated_home.py`)
- [x] Verify feedback (position, load) flows back to GradientOS (telemetry stream to web UI alerts, `telemetry_all.py`)
- [x] Test the web UI with the new backend (user runs the arm daily via web UI, incl. Home, jog, rotysquare)

### Document
- [x] Document the implementation (protocol details: `docs/protocols/feetech-sts-scs.md`; backend architecture: GradientOS `arm_controller/ARCHITECTURE.md`)
- [x] Record any issues encountered and solutions (write-then-read flakiness, ~3 ms transaction floor, EEPROM safety notes — all in protocol doc)
- [x] Update decision log if architectural decisions were made

## Definition of done

- [x] STS3215 backend works in GradientOS
- [x] Servos controlled through the GradientOS app (not raw scripts) — full 8-servo arm
- [x] Feedback (position, load) displays correctly
- [x] Code is committed to the GradientOS fork

## Notes

- Archived during the 2026-09-08 restructure: sprint numbers shifted; this sprint's
  remaining scope (none) is closed. The arm is operational; motion-quality work continues
  in sprint-02 (endpoint-paradigm quick fix) and sprint-05 (pseudo-Dynamixel feasibility).