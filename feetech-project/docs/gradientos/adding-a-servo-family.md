# Adding a Servo Family to GradientOS

> This file is a stub. It documents the process of adding a new servo protocol backend to GradientOS. Filled in during Phase 3 after studying the codebase.

## Goal

Add Feetech STS3215 (SCS/STS protocol) and HLS3950 (HLS protocol) as servo backends in GradientOS, alongside the existing EtherCAT backend.

## What we need to learn (Phase 3)

- [ ] Where is the servo protocol abstraction in the codebase?
- [ ] What interface does a servo backend implement?
- [ ] How does the "build your own robot" workflow select a servo type?
- [ ] What configuration is needed to add a new servo family?
- [ ] Can multiple protocol backends coexist (for switching between arms)?

## Expected implementation (subject to change after Phase 3)

### STS3215 backend (Phase 4)

1. Implement the servo backend interface using the SCS/STS protocol
2. Use the `scservo` Python library (or custom implementation) for serial communication
3. Map GradientOS joint commands to SCS protocol writes (position, speed, torque)
4. Map SCS protocol reads to GradientOS feedback (position, load, temperature)
5. Create a robot configuration that uses the STS3215 backend
6. Test on the bench with 1-2 servos

### HLS3950 backend (Phase 5)

1. Depends on Phase 2 resolving the HLS protocol question
2. If HLS shares the SCS protocol — extend the STS3215 backend
3. If HLS uses a new protocol — implement a new backend from scratch
4. Same mapping pattern: GradientOS commands → HLS protocol writes

### Key design constraint

Paired servos (J2, J3) must remain **independent actuators** in the backend. The backlash-offset logic is a separate layer (Phase 6), not part of the servo backend.

## Open questions

- [ ] Does GradientOS have a plugin/extension system for servo protocols?
- [ ] Or do new backends need to be compiled/added to the core?
- [ ] How does the web UI handle new servo types?
- [ ] Are there licensing concerns with modifying GradientOS?