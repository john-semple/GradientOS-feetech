# Feetech Servo Integration Project

Project to integrate Feetech servos (STS3215 and HLS3950) with GradientOS on a Raspberry Pi 5.

## Overview

The goal is to add Feetech's cheaper serial-bus servos as an alternative to GradientOS's EtherCAT protocol, enabling a custom 6DOF robot arm. The project starts with a test bench (1-2 servos) and scales up to a full 6DOF arm with paired servos for backlash reduction.

## Hardware

| Component | Details |
|-----------|---------|
| Host | Raspberry Pi 5 (Pi 5 SBC, 4GB RAM) |
| Servo adapter | Feetech URT-1 (USB to TTL/RS485) |
| Servo family 1 | Feetech STS3215 (SCS/TTL protocol, 12V) |
| Servo family 2 | Feetech HLS3950 (protocol TBD, 12V) |
| Power (test bench) | 32V 10A benchtop PSU with CC/CV mode |
| USB cable | Micro USB (URT-1 to Pi) |

## Two servo families, two arms

- **STS3215 arm** — uses the SCS/TTL channel on the URT-1
- **HLS3950 arm** — uses a separate URT-1 (protocol/channel TBD)
- Arms are run independently, one at a time, never simultaneously
- Same GradientOS app, different protocol backend per arm

## 6DOF arm geometry

| Joint | Type | Servos |
|-------|------|--------|
| J1 | Roll | 1x (STS3215 or HLS3950) |
| J2 | Pitch | 2x paired (same model) |
| J3 | Pitch | 2x paired (same model) |
| J4 | Roll | 1x |
| J5 | Pitch | 1x |
| J6 | Roll | 1x |

Paired servos drive the same joint output. Backlash reduction via small angular offset is a future goal — servos remain independent actuators in code (not hardcoded master/slave).

## Project phases

| Phase | Sprint | Description |
|-------|--------|-------------|
| 0 | sprint-00 | Setup & documentation |
| 1 | sprint-01 | Electronics validation — wire test bench safely |
| 2 | sprint-02 | Servo protocol validation — ping, read, command moves |
| 3 | sprint-03 | Study GradientOS architecture (clone, read, document) |
| 4 | sprint-04 | Implement STS3215 backend in GradientOS |
| 5 | sprint-05 | Implement HLS3950 backend in GradientOS |
| 6 | sprint-06 | Paired-servo joint model with backlash offset |
| 7 | sprint-07 | Full 6DOF arm config + scale |

## Key open questions

- [ ] HLS3950 protocol — is it compatible with SCS/TTL or a new protocol? (resolved in Phase 2)
- [ ] HLS3950 — which URT-1 channel? SMS/RS485 (4-pin) or SCS/TTL (3-pin)?
- [ ] Docker USB passthrough — needs `devices:` block in host docker-compose.yml (requires human approval)
- [ ] udev rule for stable device naming (needed when scaling to two URT-1s)

## Repository layout

```
GradientOS/                         ← this fork (john-semple/GradientOS-feetech)
  feetech-project/                  ← this folder — your project work
    README.md                       # project overview (this file)
    TODO.md                         # current state + next action
    docs/
      safety.md                     # PSU limits, E-stop habits, what to never do
      hardware/
        test-bench-wiring.md        # Phase 1 wiring, safety checks
        servo-specs/
          STS3215.md                # pinout, protocol, register map, voltage
          HLS3950.md                # same — protocol confirmation is a key task
        6dof-arm-geometry.md        # J1-J6 layout, servo placement, pairs
      protocols/
        feetech-sts-scs.md          # STS/SCS protocol family documentation
        feetech-hls.md              # HLS protocol documentation
      gradientos/
        architecture-notes.md       # how GradientOS is structured
        adding-a-servo-family.md    # the "build your own robot" extension path
      decisions/
        decision-log.md             # ADR-style dated decisions + rationale
    sprints/
      sprint-00-setup.md
      sprint-01-electronics.md
      sprint-02-servo-protocol.md
      sprint-03-gradientos-study.md
      sprint-04-sts-backend.md
      sprint-05-hls-backend.md
      sprint-06-paired-joints.md
      sprint-07-full-arm.md
    code/                           # empty until Phase 2
  src/gradient_os/arm_controller/backends/feetech/  ← existing GradientOS Feetech stub
  docs/feetech_sts3215_instructions.md              ← existing GradientOS Feetech docs
```

## GradientOS upstream tracking

Two clones on the Pi:

| Folder | Remote | Purpose |
|--------|--------|---------|
| `GradientOS/` | `origin: john-semple/GradientOS-feetech` (your fork), `upstream: gradient-industrial-robotics/GradientOS` | Working copy — edits and commits go here |
| `GradientOS-upstream/` | `gradient-industrial-robotics/GradientOS` | Clean reference, pull-only — check what they're improving |

To merge upstream improvements: `git pull upstream master` in `GradientOS/`.

## Safety

See [docs/safety.md](docs/safety.md) before any wiring or power-on.