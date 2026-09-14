# Feetech HLS Protocol

Documentation of the FT-SCS serial servo protocol used by the HLS3950M.

> Filled from the Feetech wiki at `wiki.aifitlab.com/feetech-servo-motor-docs/feetech-hls-servo-memory-table-analysis`.

## Overview

- **Protocol family:** FT-SCS (same frame format and instruction set as STS3215)
- **Physical layer:** TTL single-wire half-duplex (3-wire: V+, GND, Signal)
- **Direction switching:** Handled by the URT-1 in hardware (auto-routing)
- **Baud rate:** **1000000** (1 Mbps) default. Configurable 38400–1 Mbps (register 0x06, values 0–7)
- **Bus addressing:** Each servo has a unique ID (1–253). Broadcast ID is `0xFE`.
- **Position resolution:** 12-bit, 0–4095, centre 2048. `deg = counts * 360 / 4096`
- **Byte order:** Little-endian (magnetic encoder type)

## Relationship to SCS/STS protocol

**Same protocol family (FT-SCS).** The HLS3950 uses the identical frame format, instruction set, and checksum algorithm as the STS3215. The register map is very similar but has important differences (see below).

Evidence:
- Same manufacturer (Feetech/FeiTe)
- Wiki confirms: "The servo uses the FT-SCS custom protocol"
- Same instruction codes, same SYNC_WRITE/SYNC_READ layout
- Same baud rate range and default

## Frame format

Identical to STS3215:

```
[0xFF, 0xFF, Servo ID, Length, Instruction, Parameter 1, ..., Parameter N, Checksum]
```

- **Header:** Always `0xFF, 0xFF`
- **Length:** N + 2 (N = parameter bytes)
- **Checksum:** `~sum(packet[2:N]) & 0xFF`
- **Word values:** Little-endian

## Instructions

Same instruction set as STS3215:

| Code | Name            | Description |
|------|-----------------|-------------|
| `0x01` | PING          | Check if servo is present |
| `0x02` | READ          | Read N bytes from a register |
| `0x03` | WRITE         | Write to a register |
| `0x04` | REG WRITE     | Buffered write (executed on ACTION) |
| `0x05` | ACTION        | Execute pending REG WRITE commands |
| `0x06` | RESET         | Parameter restore (preserves ID) |
| `0x08` | RESTART       | Reboot servo |
| `0x0A` | RESET         | Reset revolution count |
| `0x0B` | CALIBRATE     | Position calibration (with or without parameter) |
| `0x82` | SYNC_READ     | Read the same register block from multiple servos |
| `0x83` | SYNC_WRITE    | Write to the same register block on multiple servos |

## Register map

### EEPROM (persistent — do not write without human approval)

| Addr | Size | Meaning | Notes |
|------|------|---------|-------|
| `0x00` | byte | Firmware major | 3 |
| `0x01` | byte | Firmware minor | |
| `0x02` | byte | END | 0 = little-endian |
| `0x03` | byte | Servo major version | |
| `0x04` | byte | Servo minor version | |
| `0x05` | byte | Servo ID | **Do not write** |
| `0x06` | byte | Baud rate | 0 = 1 Mbps. **Do not write** |
| `0x07` | byte | Sub ID | Secondary ID (write-only). Not on STS. |
| `0x08` | byte | Response status level | 0 = minimal, 1 = all |
| `0x09` | word | Min angle limit | 0–4094 |
| `0x0B` | word | Max angle limit | 1–4095 |
| `0x0D` | byte | Max temperature limit | 70 °C default |
| `0x0E` | byte | Max input voltage | 0.1 V units |
| `0x0F` | byte | Min input voltage | 0.1 V units |
| `0x10` | word | Max torque | 0–1000 (0.1%) |
| `0x12` | byte | Phase | Special function byte — different bits than STS |
| `0x13` | byte | Unload condition | Protection enable bits |
| `0x14` | byte | LED alarm condition | |
| `0x15` | byte | Position Kp | |
| `0x16` | byte | Position Kd | |
| `0x17` | byte | Position Ki | |
| `0x18` | byte | Min starting torque | 0.1% |
| `0x19` | byte | Integral limit | Max integral = value × 4 |
| `0x1A` | byte | Positive dead zone | 0.087° units |
| `0x1B` | byte | Negative dead zone | 0.087° units |
| `0x1C` | word | Protection current | 0–2047 (6.5 mA) |
| `0x1E` | byte | Angular resolution | 1–128 |
| `0x1F` | word | Position offset | ±4095 (bit 15 = direction) |
| `0x21` | byte | Operating mode | 0=pos, 1=speed, 2=**constant current**, 3=PWM |
| `0x22` | byte | Current loop Kp | **Different from STS** (STS = holding torque) |
| `0x23` | byte | Current loop Ki | **Different from STS** (STS = protection time) |
| `0x25` | byte | Velocity loop Kp | Speed mode only |
| `0x26` | byte | Overcurrent protection time | 10 ms units |
| `0x27` | byte | Velocity loop Ki | Speed mode only |

### RAM (cleared on power cycle)

| Addr | Size | Meaning | Notes |
|------|------|---------|-------|
| `0x28` | byte | Torque switch | 0=off, 1=on, 2=damping. **Does NOT accept 128 for calibration** (STS does) |
| `0x29` | byte | Acceleration | 0 = MAX. Use small non-zero value. |
| `0x2A` | word | Target position | Bit 15 = direction. Writing enables torque. |
| `0x2C` | word | **Target current** | **Different from STS** (STS = PWM speed). Mode 2: -2047 to 2047. |
| `0x2E` | word | Operating speed | 0.732 RPM/LSB. Bit 15 = direction. 0 = max default. |
| `0x30` | word | Torque limit | 0–1000 (0.1%) |
| `0x32` | byte | Kp (RAM copy) | From EEPROM 0x15 |
| `0x33` | byte | Kd (RAM copy) | From EEPROM 0x16 |
| `0x34` | byte | Ki (RAM copy) | From EEPROM 0x17 |
| `0x37` | byte | Lock flag | 0=unlocked, 1=locked |

### Feedback (read-only)

| Addr | Size | Meaning | Notes |
|------|------|---------|-------|
| `0x38` | word | Present position | Bit 15 = direction |
| `0x3A` | word | Present speed | 0.732 RPM. Bit 15 = direction |
| `0x3C` | word | Present load | PWM duty. Bit 10 = direction |
| `0x3E` | byte | Present voltage | 0.1 V units |
| `0x3F` | byte | Present temperature | °C |
| `0x40` | byte | Async write flag | |
| `0x41` | byte | Servo status | Bit flags (see below) |
| `0x42` | byte | **Moving flag** | **Not on STS.** BIT0=moving, BIT1=reached target |
| `0x43` | word | **Target position** | **Not on STS.** Current target readback |
| `0x45` | word | Present current | 6.5 mA units |

## Key differences from STS3215

| Feature | STS3215 | HLS3950 |
|---------|---------|---------|
| 0x2C register | PWM open-loop speed | **Target current** |
| 0x22 register | Holding torque | **Current loop Kp** |
| 0x23 register | Protection time | **Current loop Ki** |
| 0x07 register | Reserved | **Sub ID** (secondary write-only ID) |
| 0x21 mode 2 | PWM open-loop | **Constant current** |
| 0x28 = 128 | Calibrate midpoint | **Not supported** — use 0x0B instruction only |
| 0x42 register | Not present | **Moving flag** (BIT0=moving, BIT1=reached) |
| 0x43 register | Not present | **Target position readback** |
| Status bit 1 | Angle limit | **Magnetic encoder** |
| Status bit 3 | Range | **Current** |
| Status bit 5 | Overload | **Load** |

## Calibration

The HLS3950 supports position calibration via the `0x0B` instruction only:

- **Without parameter:** calibrates current position to 2048 (centre)
- **With parameter:** calibrates to a specific value (e.g. 1024)

```
# Calibrate to centre
[0xFF, 0xFF, ID, 0x02, 0x0B, Checksum]

# Calibrate to 1024
[0xFF, 0xFF, ID, 0x04, 0x0B, 0x00, 0x04, Checksum]
```

**Do NOT use the STS3215 torque-switch shortcut** (writing 128 to 0x28). The HLS3950 torque switch only accepts 0 (off), 1 (on), 2 (damping). Writing 128 is ignored.

## Status bits (0x41)

| Bit | Mask | Name |
|-----|------|------|
| 0 | `0x01` | Voltage |
| 1 | `0x02` | Magnetic encoder |
| 2 | `0x04` | Temperature |
| 3 | `0x08` | Current |
| 5 | `0x20` | Load |

## SYNC_WRITE layout

**Different from STS3215.** The STS3215 uses start address 0x29 with 7 bytes per servo:
`[Accel(1), Pos(2), Time(2), Speed(2)]` — writing 0x0000 to the Time field (0x2C) is harmless.

The HLS3950 **cannot use this layout** because register 0x2C is "Target Current" on the HLS — **writing 0 to 0x2C disables the motor** (zero current = zero torque). The servo accepts the goal register write but never executes the move, and gets stuck in a state where even individual writes stop working until a restart (0x08 instruction).

HLS3950 SYNC_WRITE uses start address 0x2A with 6 bytes per servo:
`[Pos_L(1), Pos_H(1), Current_L(1), Current_H(1), Speed_L(1), Speed_H(1)]`

- **Acceleration** is set separately via an individual write to 0x29 before the sync_write
- **Target Current** (0x2C) is set to a non-zero value (default 980, the torque limit in 0.1% units) so the motor has torque to move
- **Position** and **Speed** are the same as STS3215

The sync_write data is: `(servo_id, position, speed, accel)` — same tuple format as STS3215, but the protocol function handles the layout difference internally.

## Implementation

The in-repo implementation lives at `src/gradient_os/arm_controller/backends/hls3950/`:
- `config.py` — register constants, telemetry parsers, SYNC_WRITE layout (0x2A start, 6 bytes, non-zero current)
- `protocol.py` — frame construction, serial I/O, sync_write with HLS-specific current handling
- `driver.py` — `HLS3950Backend(ActuatorBackend)` class

## Critical safety behaviours (measured on bench, 2026-09-11)

1. **Writing 0 to register 0x2C (Target Current) DISABLES THE MOTOR.** The servo accepts goal commands but never executes them, and gets stuck. A restart (0x08 instruction) is required to recover. The STS3215 writes 0x0000 here (harmless — 0x2C is "Goal Time" on STS), so the HLS backend cannot share the STS sync_write packet format.

2. **EEPROM angle limits are factory-restricted (1024–3071 on this servo).** Not unrestricted 0–4095 like the STS3215. Commands outside the limits are silently clamped — the servo does not move and does not report an error.

3. **The torque switch (0x28) does NOT accept 128 for calibration.** Only the 0x0B instruction works. Writing 128 is silently ignored.

4. **The moving flag (0x42) shows 0x03 (moving + reached) during motion, 0x00 when settled.** This is HLS-specific feedback not available on the STS3215.

5. **Same safe-move recipe as STS3215:** seed the goal register with the current position, set acceleration (0x29) and speed (0x2E) before commanding a move. Do not write 0x28=1 on its own (dangerous — the goal register defaults to 0 after restart, which would swing to position 0).

## Bench validation (confirmed 2026-09-11)

- [x] PING at 1 Mbps via URT-1 SCS/TTL port — responded on ID 30
- [x] Read firmware (3.43), servo version (10.18), position, voltage (12.0V), temp (27°C), status (0x00)
- [x] 10° oscillation (3 cycles, 1024 ↔ 1136) — all targets exact, returned to start
- [x] SYNC_WRITE (batch position command) — 2 cycles, all exact, servo not stuck
- [x] SYNC_READ (batch position read) — correct data
- [x] Moving flag during slow motion — 0x42 = 0x03 (moving) during move, 0x00 when settled
- [x] `execute_profiled_segment` (backend class method) — -89.8° → -79.8° → back, exact
- [ ] Measure stall current
- [ ] 30-second touch test (temperature under load)