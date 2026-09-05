# Sprint 05 — HLS3950 Backend in GradientOS

## Goal

Implement a Feetech HLS3950 servo backend in GradientOS and test it on the bench.

## Prerequisites

- Sprint 04 complete (STS3215 backend working, pattern established)
- Sprint 02 Part B complete (HLS3950 protocol identified)
- Second URT-1 adapter (if HLS3950 needs a different channel/adapter)

## Tasks

### Implementation
- [ ] If HLS shares the SCS protocol: extend the STS3215 backend
- [ ] If HLS uses a new protocol: implement a new backend following the STS3215 pattern
- [ ] Map GradientOS joint commands → HLS protocol writes
- [ ] Map HLS protocol reads → GradientOS feedback
- [ ] Create a robot configuration for the HLS3950 arm

### Testing (bench scale)
- [ ] Test with 1 HLS3950 servo: ping, read, command moves
- [ ] Test with 2 servos if available
- [ ] Verify feedback flows back to GradientOS
- [ ] Confirm the app can switch between STS3215 and HLS3950 configs

### Document
- [ ] Document the HLS3950 backend implementation
- [ ] Record differences from the STS3215 backend
- [ ] Update decision log

## Definition of done

- HLS3950 backend works in GradientOS
- 1-2 servos controlled through the GradientOS app
- App can switch between STS3215 and HLS3950 arm configs
- Code committed to the GradientOS fork

## Notes

- The implementation approach depends heavily on what Sprint 02 reveals about the HLS protocol.
- If the HLS3950 is not URT-1 compatible, this sprint includes sourcing the correct adapter.
- Same constraint: keep paired servos as independent actuators.