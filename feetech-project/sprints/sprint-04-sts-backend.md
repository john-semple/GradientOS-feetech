# Sprint 04 — STS3215 Backend in GradientOS

## Goal

Implement a Feetech STS3215 (SCS/STS protocol) servo backend in GradientOS and test it on the bench with 1-2 servos.

## Prerequisites

- Sprint 03 complete (GradientOS architecture understood, extension path identified)
- Sprint 02 complete (STS3215 protocol validated)
- Docker USB passthrough working (if running in container)

## Tasks

### Setup
- [ ] Create a fork of GradientOS on GitHub (if not already done)
- [ ] Add fork as remote in the local GradientOS clone
- [ ] Create a feature branch for the STS3215 backend

### Implementation
- [ ] Implement the servo backend interface using SCS/STS protocol
- [ ] Map GradientOS joint commands → SCS protocol writes (position, speed, torque)
- [ ] Map SCS protocol reads → GradientOS feedback (position, load, temperature)
- [ ] Create a robot configuration that uses the STS3215 backend
- [ ] Ensure paired servos are independent actuators (not master/slave)

### Testing (bench scale)
- [ ] Test with 1 servo: ping, read, command moves through GradientOS
- [ ] Test with 2 servos: independent commands, no interference
- [ ] Verify feedback (position, load) flows back to GradientOS
- [ ] Test the web UI with the new backend (if applicable)

### Document
- [ ] Document the implementation in docs/gradientos/adding-a-servo-family.md
- [ ] Record any issues encountered and solutions
- [ ] Update decision log if architectural decisions were made

## Definition of done

- STS3215 backend works in GradientOS
- 1-2 servos controlled through the GradientOS app (not raw scripts)
- Feedback (position, load) displays correctly
- Code is committed to the GradientOS fork

## Notes

- Keep paired servos as independent actuators — backlash offset is Phase 6.
- Don't over-engineer for the full 8-servo arm yet — this is bench scale.
- If GradientOS doesn't have a plugin system, follow whatever pattern the EtherCAT backend uses.