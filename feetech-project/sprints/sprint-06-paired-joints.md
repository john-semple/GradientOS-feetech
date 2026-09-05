# Sprint 06 — Paired-Servo Joint Model with Backlash Offset

## Goal

Add a software layer that maps one logical joint to two physical actuators with an angular offset for backlash reduction.

## Prerequisites

- Sprint 04 and 05 complete (both backends working)
- Understanding of GradientOS's joint model (from Sprint 03)

## Background

J2 and J3 each have two servos driving the same joint output. By driving them with a small angular offset, mechanical backlash is taken up and play is reduced. The servos remain independent actuators in the protocol backend — the offset is applied at the joint model layer, not the servo communication layer.

## Tasks

### Study GradientOS joint model
- [ ] Determine if GradientOS supports one logical joint → multiple actuators natively
- [ ] If not, design the extension needed
- [ ] Identify where in the command path the offset should be applied

### Implementation
- [ ] Implement the paired-joint model (one logical joint → two actuator targets)
- [ ] Add configurable angular offset per joint pair
- [ ] Ensure the offset is applied symmetrically (one servo leads, one lags)
- [ ] Handle position feedback: report the logical joint position from one or both actuators

### Testing
- [ ] Test with 2 paired STS3215 servos on the bench
- [ ] Verify both servos move to their respective targets (offset applied)
- [ ] Test with offset = 0 (should behave as two independent servos at same position)
- [ ] Test with small offset (e.g. 1-2 degrees)
- [ ] Measure backlash reduction if possible (physical measurement on the joint)

### Document
- [ ] Document the paired-joint model and offset configuration
- [ ] Record measured backlash reduction results
- [ ] Update decision log

## Definition of done

- Paired servos can be commanded as one logical joint through GradientOS
- Angular offset is configurable per joint
- Backlash reduction is measurable (or at least observable)
- Offset = 0 works identically to independent actuators

## Notes

- Start with a very small offset (0.5-1 degree) to avoid over-stressing the servos.
- The offset direction matters — it should preload the gear mesh in the normal load direction.
- This is a software-only change — no hardware modifications to the servo pairing.
- If GradientOS's joint model can't be extended easily, this may require deeper changes. Assess in Sprint 03 first.