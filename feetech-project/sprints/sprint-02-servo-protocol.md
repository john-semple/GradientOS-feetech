# Sprint 02 — Servo Protocol Validation

## Goal

Send commands to the STS3215 from the Pi (minimal Python script) and confirm it responds. Then repeat for the HLS3950 to resolve the protocol question.

## Prerequisites

- Sprint 01 complete (test bench wired, servo powers on safely)
- URT-1 visible as /dev/ttyUSB0 in the environment where code runs
- Python environment with pyserial available

## Part A: STS3215 (SCS/STS protocol)

### Research
- [ ] Find Feetech SCS/STS protocol documentation (check wiki.aifitlab.com)
- [ ] Review the `scservo` Python library source code
- [ ] Document the frame format in docs/protocols/feetech-sts-scs.md
- [ ] Document the register map in docs/protocols/feetech-sts-scs.md

### Code
- [ ] Write minimal Python script: open serial port at correct baud rate
- [ ] Send PING to servo ID 1 — confirm response
- [ ] Read model number and firmware version
- [ ] Read current position
- [ ] Command a small move (1-5 degrees)
- [ ] Confirm servo moves and reports new position
- [ ] Read load/current feedback during a move
- [ ] Read temperature

### Document
- [ ] Fill in docs/protocols/feetech-sts-scs.md with confirmed protocol details
- [ ] Fill in docs/hardware/servo-specs/STS3215.md with measured values
- [ ] Record actual idle current, move current, and stall current from bench PSU readout

## Part B: HLS3950 (protocol unknown)

### Research
- [ ] Search for HLS3950 or HLS series protocol documentation online
- [ ] Check Feetech FD software / wiki for HLS support
- [ ] Look for community projects using HLS servos
- [ ] If no docs: use logic analyzer to capture Feetech app → servo traffic

### Determine physical interface
- [ ] Is it TTL (3-pin) or RS485 (4-pin)?
- [ ] Does it connect to the URT-1's SCS/TTL port, SMS/RS485 port, or neither?
- [ ] If not URT-1 compatible, identify the correct adapter

### Code (if protocol discovered)
- [ ] Write minimal Python script for HLS3950
- [ ] PING, read model, read position, command small move
- [ ] Same validation sequence as STS3215

### Document
- [ ] Fill in docs/protocols/feetech-hls.md with confirmed protocol details
- [ ] Fill in docs/hardware/servo-specs/HLS3950.md with measured values
- [ ] Record whether HLS shares SCS protocol or is separate

## Definition of done

- STS3215 responds to commands: ping, read, move
- HLS3950 protocol is identified (or determined to need further reverse-engineering)
- All protocol findings documented
- Measured current values recorded for both servo types

## Notes

- Start with small moves (1-5 degrees). Never command a full-range swing as the first move.
- Watch the bench PSU current readout during all moves.
- If a servo doesn't respond, check: baud rate, servo ID, wiring, ground connection.
- Code goes in `code/` directory in this repo.