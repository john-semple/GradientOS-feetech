# Feetech STS/SCS Protocol

Documentation of the SCS/STS serial servo protocol used by the STS3215.

> This file is a stub. It will be filled in during Phase 2 (sprint-02-servo-protocol.md) from Feetech documentation and bench testing.

## Overview

- **Protocol family:** SCS (Serial Controlled Servo) / STS
- **Physical layer:** TTL single-wire half-duplex (3-wire: V+, GND, Signal)
- **Direction switching:** Handled by the URT-1 in hardware (auto-routing, no enable IO needed)
- **Baud rate:** ~115200 typical (confirm from docs)
- **Bus addressing:** Each servo has a unique ID (1-253 typical)

## Frame format

TBD — to be documented from Feetech protocol reference.

Expected structure (based on community libraries):
- Header bytes
- Servo ID
- Command/instruction
- Parameters (variable length)
- Checksum

## Key registers

| Address | Name | Access | Description |
|---------|------|--------|-------------|
| TBD | Servo ID | R/W | Bus address |
| TBD | Position | R/W | Target position / current position |
| TBD | Speed | W | Movement speed |
| TBD | Torque enable | R/W | Enable/disable motor output |
| TBD | Model number | R | Servo model identifier |
| TBD | Firmware version | R | Firmware revision |
| TBD | Load/torque | R | Current load feedback |
| TBD | Temperature | R | Internal temperature |
| TBD | Current | R | Current draw (if supported) |

## Commands

TBD — to be documented. Expected:
- PING (check if servo is present)
- READ (read register)
- WRITE (write register)
- SYNC WRITE (broadcast to multiple servos)
- Factory reset

## Community libraries

- `scservo` Python package — commonly used for SCS/STS family
- Also known as STServo library
- Uses pyserial for the serial port interface
- The URT-1's auto-routing means no special half-duplex handling needed in software

## Research sources

- [ ] Feetech protocol documentation (check wiki.aifitlab.com)
- [ ] Feetech FD software (host computer app)
- [ ] Community `scservo` library source code
- [ ] Bench testing with a logic analyzer if needed

## Open questions

- [ ] Confirm exact frame format
- [ ] Confirm default baud rate and configurable range
- [ ] Get the full register map with addresses
- [ ] Confirm SYNC WRITE support (for efficient multi-servo commands)
- [ ] Confirm position resolution (steps per revolution)