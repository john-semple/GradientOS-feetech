# Sprint 01 — Servo Protocol Validation (STS3215) — COMPLETE

> **COMPLETE 2026-09-08.** All Part A items validated on the bench and documented.
> HLS3950 protocol validation (formerly Part B) moved to the HLS sprint
> (`sprint-05-hls3950.md`).

## Goal

Send commands to the STS3215 from the Pi (minimal Python script) and confirm it responds.

## Prerequisites

- Sprint 00 complete; test bench wired, servo powers on safely ✅ (sprint-03-electronics.md)
- URT-1 visible as /dev/ttyUSB0 in the environment where code runs ✅
- Python environment with pyserial available ✅

## Part A: STS3215 (SCS/STS protocol)

### Research
- [x] Find Feetech SCS/STS protocol documentation (confirmed against bench servo; full frame format in docs/protocols/feetech-sts-scs.md)
- [x] Review the `scservo` Python library source code (informed the protocol implementation in GradientOS `backends/feetech/protocol.py`)
- [x] Document the frame format in docs/protocols/feetech-sts-scs.md (header, checksum, all instructions)
- [x] Document the register map in docs/protocols/feetech-sts-scs.md (EEPROM + RAM, status bits, critical safety behaviours)

### Code
- [x] Write minimal Python script: open serial port at correct baud rate (`code/` scripts; 1 Mbps confirmed, silent at lower rates)
- [x] Send PING to servo ID 1 — confirm response
- [x] Read model number and firmware version (model 777 = STS3215, firmware 3.10)
- [x] Read current position (0x38; resting ~4016)
- [x] Command a small move (1-5 degrees) (5° → 4.83° achieved)
- [x] Confirm servo moves and reports new position (3× back-and-forth 10° moves, exact return to start)
- [x] Read load/current feedback during a move (load peaked 96/1023 during 10° move; move current 0.54 A from PSU)
- [x] Read temperature (31-33 °C idle via 0x3F)

### Document
- [x] Fill in docs/protocols/feetech-sts-scs.md with confirmed protocol details (incl. latency table: ~3 ms/transaction floor, batching consequences)
- [x] Fill in docs/hardware/servo-specs/STS3215.md with measured values (12.0 V, PID 32/32/0, safe-move recipe, motion accuracy table)
- [x] Record actual idle current, move current, and stall current from bench PSU readout
      (idle 299 mA; move 0.54 A; stall ~0.67 A / 8 W spike — measured 2026-09-08 via arm
      pressure test, manual downward pull on the end effector)

## Definition of done

- [x] STS3215 responds to commands: ping, read, move
- [x] All protocol findings documented
- [x] Measured current values recorded

## Notes

- Start with small moves (1-5 degrees). Never command a full-range swing as the first move.
- Watch the bench PSU current readout during all moves.
- If a servo doesn't respond, check: baud rate, servo ID, wiring, ground connection.
- Code goes in `code/` directory in this repo.
- Stall current caveat: 8 W was a brief spike under manual pull — a sustained jam against a
  higher PSU current limit may read higher.