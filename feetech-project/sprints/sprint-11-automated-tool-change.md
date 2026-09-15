# Sprint 11 — Automated Tool Change System

## Goal

Design and implement an automated tool change system for the arm, allowing it to
swap end-effectors (e.g. weld torch, gripper, sensor probe) without human
intervention during a task sequence.

## Prerequisites

- Sprint 10 (smooth streaming executor) complete — precise, repeatable motion
  is required for tool change docking alignment
- Sprint 08 (full-arm hardening) recommended first — stable power, verified
  joint limits, and known positioning repeatability
- Mechanical design for tool changer interface (tool-side + arm-side coupling)
- Decision: passive mechanical lock vs. active latch (servo/EM lock)

## Tasks

### Mechanical design
- [ ] Define tool changer interface standard (mechanical mating geometry,
      electrical/pneumatic passthrough if needed)
- [ ] Design arm-side coupler (mounts to the current end-effector flange)
- [ ] Design tool-side dock/cradle (holds idle tools in a known position)
- [ ] Prototype the coupling mechanism — passive dowel+spring lock or active latch
- [ ] Verify docking tolerance vs. arm positioning repeatability (how much
      misalignment can the coupling absorb?)

### Tool rack / dock
- [ ] Design a tool rack that holds multiple tools at known positions
- [ ] Mount rack within arm reach; measure and record dock slot positions
- [ ] Add dock slot identifiers (mechanical fiducials or simple switches)

### Software — tool change sequence
- [ ] Define a tool change motion sequence (approach → align → dock → lock →
      disconnect → retreat, and the reverse for pickup)
- [ ] Implement tool change as a parameterized trajectory (dock slot index →
      joint-space or Cartesian sequence)
- [ ] Add tool state tracking to the controller (which tool is currently
      attached, if any)
- [ ] Add API commands for tool change (e.g. `CHANGE_TOOL <slot>`, `RELEASE_TOOL`)
- [ ] Add web UI controls for tool selection and change

### Software — tool-aware motion
- [ ] Add tool payload parameters to the kinematic model (weight, COM offset,
      inertia) so motion profiles adapt per tool
- [ ] Verify cap/accel parameters adjust correctly with different payloads
- [ ] Test that streaming executor (Sprint 10) handles tool-induced dynamics

### Safety
- [ ] Verify tool lock engagement before motion (mechanical interlock or sensor)
- [ ] Add fault handling: what happens if docking fails mid-sequence?
- [ ] E-stop behavior with a tool attached (drop-safe? hold position?)
- [ ] Document weight limits and tool change safety procedure

### Validation
- [ ] Bench: single tool pickup and release, repeated 10× — confirm reliable
      docking and release
- [ ] Full sequence: pick tool A → perform task → return A → pick tool B
- [ ] Measure cycle time and positioning repeatability across changes

## Definition of done

- Arm can autonomously pick up and release at least 2 different tools
- Tool change sequence is repeatable (10/10 successful cycles)
- Tool state tracked in controller and visible in web UI
- Motion profiles adapt to active tool payload
- Safety procedure documented

## Notes

- The coupling design is the hard part — everything downstream is software.
  Start with a simple mechanical prototype before building the full rack.
- Repeatability of the arm's end-effector position determines how tight the
  docking tolerance can be. Measure this in Sprint 08 first if unknown.
- Consider whether electrical passthrough is needed (e.g. for a weld torch
  trigger signal) — this dramatically complicates the coupling.