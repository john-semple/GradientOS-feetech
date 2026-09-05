# 6DOF Arm Geometry

## Joint layout

| Joint | Axis | Servos | Notes |
|-------|------|--------|-------|
| J1 | Roll | 1x | Base rotation |
| J2 | Pitch | 2x paired | Two servos driving same joint output |
| J3 | Pitch | 2x paired | Two servos driving same joint output |
| J4 | Roll | 1x | |
| J5 | Pitch | 1x | |
| J6 | Roll | 1x | Wrist/end-effector rotation |

**Total servos:** 8 per arm

## Servo pairs (J2 and J3)

- Both servos in a pair are the **same model** (both STS3215 or both HLS3950)
- Both servos are **mechanically coupled to the same joint output** (shared shaft or gear train)
- In code, paired servos are **independent actuators** — not hardcoded as master/slave
- Each servo has its own bus ID and is addressed individually

### Backlash reduction (future, Phase 6)

- Goal: drive paired servos with a **small angular offset** to take up mechanical backlash
- This is a software layer on top of the actuator abstraction, not baked into the hardware interface
- Each servo in a pair receives slightly different target positions
- Implementation requires understanding GradientOS's joint model (Phase 3)
- **Not implemented until Phase 6** — code structure must leave room for it without hardcoding it early

## Two arms, one app

| Arm | Servo model | Protocol backend | URT-1 |
|-----|-------------|------------------|-------|
| Arm A | STS3215 | STS/SCS adapter | URT-1 #1 (SCS/TTL channel) |
| Arm B | HLS3950 | HLS adapter (TBD) | URT-1 #2 (channel TBD) |

- Arms run **independently, one at a time** — never simultaneously
- Same GradientOS app instance, different protocol backend selected per arm
- Joint layout is identical for both arms (configurable in GradientOS)
- Reduction ratios, motor type, and joint distances are configurable in the app

## Configurability

GradientOS is expected to support configurable:
- Joint count and type
- Reduction ratios per joint
- Motor/servo type per joint
- Joint distances (link lengths)

This needs to be confirmed in Phase 3 when studying the GradientOS codebase.

## Open questions

- [ ] Confirm GradientOS supports the joint model described above (Phase 3)
- [ ] Confirm paired-servo joints are expressible in GradientOS's config (Phase 3)
- [ ] Determine if backlash-offset is a new feature or can be built on existing joint config (Phase 3/6)