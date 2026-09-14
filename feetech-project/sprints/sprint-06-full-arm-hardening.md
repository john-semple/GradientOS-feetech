# Sprint 07 — Full 6DOF Arm Config & Scale

## Goal

Configure and run the full 6DOF arm (8 servos) through GradientOS, with proper power distribution and stable USB device naming.

## Prerequisites

- Sprint 06 complete (paired-joint model working)
- All 8 servos for at least one arm (STS3215 or HLS3950)
- Full mechanical assembly of the arm

## Tasks

### Power distribution
- [ ] Design servo power bus/backbone for 8 servos (bypass URT-1's 6A limit)
- [ ] Source appropriate power wiring (bus bar or heavy-gauge backbone)
- [ ] Wire URT-1 for signal only, with ground tied to servo bus ground
- [ ] Determine appropriate PSU for full arm (bench PSU may not be practical mounted)
- [ ] Add inline fuses or current limiting per joint group

### USB device stability
- [ ] Write udev rule on the Pi host for stable URT-1 naming (by serial number)
- [ ] Install udev rule on host with sudo (human does this)
- [ ] Update docker-compose.yml devices: block to use stable name (with human approval)
- [ ] Verify URT-1 appears at stable name after replug

### Configuration
- [ ] Create full 6DOF robot config in GradientOS
- [ ] Define all 8 servos with correct IDs, joint assignments, and reduction ratios
- [ ] Configure paired joints (J2, J3) with backlash offset from Sprint 06
- [ ] Set joint limits (min/max positions) for safety
- [ ] Configure link lengths and geometry

### Testing
- [ ] Power on with current limit low, verify all 8 servos idle
- [ ] Command individual joints through GradientOS
- [ ] Command coordinated multi-joint moves
- [ ] Test the web UI with full arm
- [ ] Verify all feedback channels (position, load, temperature)
- [ ] Run for extended period, monitor temperatures

### Document
- [ ] Document the full arm wiring and power distribution
- [ ] Document the complete robot configuration
- [ ] Record any issues and solutions
- [ ] Update safety doc with full-arm considerations
- [ ] Create an operator handoff doc for running the arm

## Definition of done

- Full 6DOF arm (8 servos) controlled through GradientOS
- All joints move correctly with coordinated motion
- Paired joints operate with backlash offset
- Power distribution handles full load without sagging
- USB device naming is stable across replugs
- Arm can be switched between STS3215 and HLS3950 configs

## Notes

- This is the biggest sprint. Don't rush — test incrementally (add one joint at a time if needed).
- Monitor servo temperatures during extended runs.
- The power backbone is critical — voltage sag at the end of the chain causes erratic behavior.
- Consider per-servo or per-joint fuses to protect against a single stalled servo cooking itself.