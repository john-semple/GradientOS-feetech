# Sprint 03 — Study GradientOS Architecture

## Goal

Clone GradientOS, understand its architecture, and document how to add a new servo protocol backend. No code edits.

## Prerequisites

- Sprint 02 complete (both servo protocols understood)
- Human says "go" to clone GradientOS

## Tasks

### Clone
- [x] Human approved clone
- [x] Forked GradientOS as `GradientOS-feetech` on GitHub
- [x] Cloned fork to `/home/ubuntu/workspaces/GradientOS/` (origin = fork, upstream = original)
- [x] Cloned upstream reference to `/home/ubuntu/workspaces/GradientOS-upstream/`

### Study the codebase
- [ ] Identify the language(s) and overall structure
- [ ] Find the hardware/servo abstraction layer
- [ ] Find the EtherCAT protocol implementation
- [ ] Determine if there's an interface/abstract class for servo backends
- [ ] Study the "build your own robot" workflow
- [ ] Understand the joint model: can a joint map to multiple actuators?
- [ ] Understand config format: how are servos, joints, and robot geometry defined?
- [ ] Check safety mechanisms (e-stop, limits, torque)
- [ ] Check the web UI structure and how it interfaces with the backend
- [ ] Check license and any constraints on modification

### Document findings
- [ ] Fill in docs/gradientos/architecture-notes.md
- [ ] Fill in docs/gradientos/adding-a-servo-family.md
- [ ] Identify the specific files/classes that need to be modified or extended
- [ ] Identify whether a plugin system exists or if core changes are needed
- [ ] Document the plan for STS3215 and HLS3950 backend implementation

## Definition of done

- GradientOS architecture is documented
- The extension path for a new servo family is clearly identified
- Specific files and interfaces to implement are listed
- Open questions from docs/gradientos/ are answered

## Notes

- This is a read-only phase. No edits to GradientOS.
- Two clones exist: `GradientOS/` (fork, for edits) and `GradientOS-upstream/` (reference, pull-only).
- GradientOS already has a Feetech backend stub at `src/gradient_os/arm_controller/backends/feetech/` — study this in detail.
- There is also `docs/feetech_sts3215_instructions.md` in GradientOS — read it.