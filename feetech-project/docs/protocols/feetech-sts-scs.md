# Feetech STS/SCS Protocol

Documentation of the SCS/STS serial servo protocol used by the STS3215.
Confirmed against one physical STS3215 (ID 1, firmware 3.10) on this bench.

## Overview

- **Protocol family:** SCS (Serial Controlled Servo) / STS
- **Physical layer:** TTL single-wire half-duplex (3-wire: V+, GND, Signal)
- **Direction switching:** Handled by the URT-1 in hardware (auto-routing, no enable IO needed in software)
- **Baud rate:** **1000000** (1 Mbps). Confirmed: servo is silent at 500000, 250000, 115200, 57600. The CH340 adapter reaches 1 Mbps reliably.
- **Bus addressing:** Each servo has a unique ID (1-253). Broadcast ID is `0xFE`.
- **Position resolution:** 12-bit, 0-4095, centre 2048. `deg = counts * 360 / 4096`.

## Frame format

All packets share this structure:

```
[0xFF, 0xFF, Servo ID, Length, Instruction, Parameter 1, ..., Parameter N, Checksum]
```

- **Header:** Always `0xFF, 0xFF`.
- **Servo ID:** Target servo ID, or `0xFE` for broadcast.
- **Length:** Number of bytes that follow, including the instruction, parameters, and checksum (i.e. everything from Instruction to Checksum inclusive).
- **Instruction:** Command code (see below).
- **Parameters:** Instruction-dependent.
- **Checksum:** Bitwise inverse of the sum of all bytes from Servo ID through the last parameter, i.e. `~sum(packet[2:N]) & 0xFF`.

Word values (16-bit) are **little-endian**: low byte first, high byte second.

## Instructions

| Code | Name            | Description |
|------|-----------------|-------------|
| `0x01` | PING          | Check if servo is present. No parameters. |
| `0x02` | READ          | Read N bytes from a register. Params: `[addr, length]`. |
| `0x03` | WRITE         | Write to a register. Params: `[addr, value...]`. |
| `0x06` | RESET         | Factory reset (preserves ID). **EEPROM — do not call unless asked.** |
| `0x08` | RESTART       | Reboot servo. **Do not call unless asked.** |
| `0x0B` | CALIBRATE_MID | Set current position as centre. **EEPROM — do not call unless asked.** |
| `0x82` | SYNC_READ     | Read the same register block from multiple servos in one round-trip. |
| `0x83` | SYNC_WRITE    | Write to the same register block on multiple servos in one broadcast packet. |

### PING

Request:
```
[0xFF, 0xFF, ID, 0x02, 0x01, Checksum]
```
Response:
```
[0xFF, 0xFF, ID, 0x02, Error, Checksum]
```
`Error == 0x00` means healthy.

### READ

Request:
```
[0xFF, 0xFF, ID, 0x04, 0x02, Addr, Length, Checksum]
```
Response (1-byte read):
```
[0xFF, 0xFF, ID, 0x03, Error, Value, Checksum]
```
Response (2-byte read):
```
[0xFF, 0xFF, ID, 0x04, Error, Val_L, Val_H, Checksum]
```

### WRITE

Byte write:
```
[0xFF, 0xFF, ID, 0x04, 0x03, Addr, Value, Checksum]
```
Word write:
```
[0xFF, 0xFF, ID, 0x05, 0x03, Addr, Val_L, Val_H, Checksum]
```
WRITE has no response packet (fire-and-forget).

### SYNC_WRITE

Broadcast (`0xFE`) packet that writes a fixed-length data block to the same start address on multiple servos at once. Per-servo entry is `[ID, Accel, Pos_L, Pos_H, Time_L, Time_H, Speed_L, Speed_H]` (7 data bytes + ID). Start address is `0x29` (acceleration), so the block covers accel + goal position + goal time + goal speed.

### SYNC_READ

Broadcast request for the same register block from multiple servos; each servo responds in ID order. Used for the high-frequency position feedback loop.

## Register map

Only registers confirmed on this servo. `0x28`-`0x2F` are **RAM** (cleared on power cycle). `0x00`-`0x17` are **EEPROM** (persist) — treat as read-only unless the human explicitly asks.

### EEPROM (persistent — do not write)

| Addr | Size | Meaning | Confirmed value |
|------|------|---------|-----------------|
| `0x00` | byte | Firmware major | 3 |
| `0x01` | byte | Firmware minor | 10 |
| `0x03` | word | Model number | 777 = STS3215 |
| `0x05` | byte | Servo ID | 1 — **do not write** |
| `0x06` | byte | Baud rate | `0` = 1 Mbps — **do not write** |
| `0x09` | word | Min angle limit | 0 (unrestricted) |
| `0x0B` | word | Max angle limit | 4095 (unrestricted — the servo will not protect itself) |
| `0x15` | byte | Position Kp | 32 |
| `0x16` | byte | Position Kd | 32 (note: Kd is at `0x16`, before Ki at `0x17`) |
| `0x17` | byte | Position Ki | 0 |

### RAM (cleared on power cycle)

| Addr | Size | Meaning | Notes |
|------|------|---------|-------|
| `0x28` | byte | Torque enable | Auto-set to 1 by a goal-position write; do not write `1` directly (see Safety). |
| `0x29` | byte | Goal acceleration | **`0` means MAXIMUM, not "none".** Use a small non-zero value (e.g. 10). |
| `0x2A` | word | Goal position | Writing this also enables torque. Little-endian. |
| `0x2C` | word | Goal time | (not exercised on this bench) |
| `0x2E` | word | Goal speed | Speed limit. See measured behavior below before assuming units. |
| `0x38` | word | Present position | 0-4095, centre 2048. Read-only. |
| `0x3A` | word | Present speed | **Same units as goal cap `0x2E`** (~0.088 deg/s per LSB). Bit 15 = direction (SET = decreasing counts); magnitude = `raw & 0x7FFF`. Quantized in steps of 50. NOT two's-complement. |
| `0x3C` | word | Present load | Direction bit `0x400`, magnitude `0x3FF` (0-1023). |
| `0x3E` | byte | Input voltage | value / 10 = volts (e.g. 120 = 12.0 V). |
| `0x3F` | byte | Temperature | °C. |
| `0x41` | byte | Status / error flags | `0x00` = healthy. See status bits below. |

### Status bits (`0x41`)

| Bit | Mask | Name |
|-----|------|------|
| 0 | `0x01` | Input voltage error |
| 1 | `0x02` | Angle limit error |
| 2 | `0x04` | Overheating |
| 3 | `0x08` | Range error |
| 4 | `0x10` | Checksum error |
| 5 | `0x20` | Overload |
| 6 | `0x40` | Instruction error |

## Speed command behavior (measured)

Sprint 07 Part A was run on 2026-09-14 with one STS3215 on `/dev/ttyUSB0`
(CH340), servo ID `1`, accel `10`, 12.0 V bench supply, and the PSU current
limit watched by the operator. Motion sounded and looked normal; the PSU draw
was uneventful. Logs were written under:

```
feetech-project/data/part_a_traces/20260914_143947/
feetech-project/data/part_a_traces/20260914_144045/
feetech-project/data/part_a_floor_probe/20260914_144246/
feetech-project/data/part_a_extended_slope/20260914_144403/
```

Key findings:

- Servo discovery confirmed ID `1`, starting near position `3906`, with voltage
  about `12.0 V` and temperature `33 C`.
- The low-speed floor is approximately command cap `50`. Caps `1`, `2`, `5`,
  `10`, `30`, and `50` all produced about the same motion, roughly `5 deg/s`,
  and `0x3A` decoded to magnitude `50`.
- The documented `0.732 rpm/LSB` value does not match this bench behavior when
  interpreted directly as `goal_speed -> achieved speed`.
- Above the floor, speed does rise with cap, but less than the documented value
  would imply:

| Goal speed cap | Move | Position-timed speed | Approx. rpm/LSB |
|----------------|------|----------------------|-----------------|
| `100` | 223 counts down | `9.0 deg/s` | `0.0151` |
| `200` | 223 counts down | `17.2 deg/s` | `0.0143` |
| `300` | 222 counts down | `22.9 deg/s` | `0.0127` |

Interpretation: for Sprint 07 Part B, avoid caps below `50` if the goal is to
study planner behavior rather than the firmware's minimum-speed clamp. Use cap
`300` as planned for the mid-move re-target fork test, and interpret `0x3A`
using the observed direction encoding instead of a plain signed integer.

**Update (2026-09-14, Parts B/C/D + trace cross-analysis):** the speed scale and
the `0x3A` encoding are now fully resolved:

- **`0x2E` (goal cap) and `0x3A` (present speed) are the same units.** During cruise
  the present-speed plateau decodes to *exactly* the commanded cap (100→100,
  200→200, 300→300 across hundreds of samples).
- **LSB scale ≈ 0.088 deg/s** (output shaft), consistent across caps 50-300 and
  the floor. The documented `0.732 rpm/LSB` is the **motor shaft** value:
  output-shaft 0.0147 rpm/LSB × ~50:1 gearbox ≈ 0.73 rpm/LSB at the motor.
- **`0x3A` encoding: bit 15 = direction flag (SET = decreasing counts), low 15
  bits = magnitude.** Decode `mag = raw & 0x7FFF`; NOT two's-complement (a signed
  parse of raw 32868 gives −2868: wrong magnitude and wrong sign). The register
  quantizes in steps of 50 LSB (~4.4 deg/s).
- **Direction-reversal behavior (Part D sinusoid):** natural deceleration into
  the extreme, ~0.15 s dwell at the sine's own zero-velocity point, smooth
  re-acceleration. No firmware reversal artifacts; gear-backlash pause not
  visible in telemetry.

## Mid-move goal rewrites (Sprint 07 Part B verdict — measured 2026-09-14)

**Firmware semantics: CASE A — velocity-continuous blend.** Writing a new goal
while cruising aborts the current profile and re-plans from the servo's present
position *and velocity*. Measured 3/3 trials: speed held 300→300 across a
mid-cruise goal rewrite (retarget at t≈0.60 s), zero stops, single continuous
cruise through both goals, arrival within 1-2 counts.

Implications for streaming control:

- Dense position streaming is fully viable: goals may be rewritten at 100+ Hz
  mid-move; the servo blends each rewrite into the running profile.
- On stream interruption the servo decelerates to the last written goal and
  stops there — position mode is inherently fail-safe (no runaway).
- Regime map for streamed moves (Part C, stream demand ~133 counts/s):
  cap ≥ demand → continuous cruise (error 1-2 counts); cap < demand →
  progressive lag (cap 50 = firmware floor: 38% undershoot). No stop-go regime
  occurs at any cap when the goal stream is smooth and dense — stop-go is a
  property of arrive-and-stop segment structure, not of the caps.
- Design recipe: cap ≈ 2× peak velocity demand (clamp [100, 2000]), accel
  register 10, goals streamed dense with ~50 ms lookahead.

Traces: `feetech-project/data/part_b_traces/`, `part_c_traces/`,
`part_d_sinusoid/20260914_153114/`.

## Critical safety behaviours (measured)

1. **Writing the goal register `0x2A` auto-enables torque.** `0x28` flips 0 -> 1 on a goal write. You do not need to (and should not) write `0x28 := 1` to move the servo.
2. **Writing `0x28 := 1` on its own is dangerous.** At rest the goal register reads 0 while the servo sits near 4095, and acceleration `0x29` reads 0 (= *maximum* acceleration). Torque-enabling in that state commands an instant ~358° full-range swing at max acceleration. Always seed the goal first (see the safe-move recipe in `SERVO-NOTES.md`).
3. **Acceleration `0x29 = 0` means MAXIMUM.** Not "none" or "disabled". Always write a small non-zero value before moving.
4. **The angle limits are unrestricted (0/4095).** The servo will not protect itself against a mechanical hard stop.

## Communication gotchas

- **It is *write*-then-read that is flaky, not reads in general.** Measured over 200 transactions each: back-to-back reads failed **0/400**, while write-then-read failed **1/200**. Do **not** put a 10 ms sleep on every read — that triples loop time for nothing. Retry only after a *write*; read freely. A single `None` is almost always this, not a missing servo — never conclude "no servo" from one failed read.
- **pyserial port autodetection does not work on this bench** (by design). Always pass the port explicitly (`/dev/serial/ch340`).
- **Current register `0x45` is not trustworthy on this firmware** (`0.006 A` during motion is implausible). Take real current from the bench PSU readout.

## Latency and loop rate (measured)

Every servo transaction costs about **3 ms**, and that is a **floor you cannot optimise away in software**:

| Operation | median | p95 | worst of 200 |
|-----------|--------|-----|--------------|
| `ping` | 2.90 ms | 3.01 ms | 4.43 ms |
| `read_register_word` (2 bytes) | 2.99 ms | 3.82 ms | 3.85 ms |
| `sync_read_block` (8 bytes, 1 txn) | 3.00 ms | 3.09 ms | 4.35 ms |

**Latency is per-transaction, not per-byte.** Reading 8 bytes in one `sync_read_block` costs the same ~3 ms as reading 2 bytes. Wire time at 1 Mbps for a 6-byte frame is ~0.06 ms (~2% of the round trip) — the other 98% is USB scheduling on the CH340. Nothing in the container, the bind mount, or Docker contributes measurably.

Consequences for any control loop:

- 1 servo, position only: **343 Hz** (2.92 ms/iteration).
- 9 servos read **individually**: ~**38 Hz**. Too slow — do not do this.
- 9 servos in **one** `sync_read_block` / `sync_write_goal_pos_speed_accel`: still ~**300 Hz**. **Always batch.** This is why those functions exist.
- Budget for jitter — 4-core Pi with no CPU limits on this container, shared with OpenChamber/OpenCode/LLM agent, on a `PREEMPT` (not `PREEMPT_RT`) kernel, swap in use. Occasional multi-millisecond scheduler stalls are normal.
- **Do not write a hard-realtime loop in Python in this container.** Soft-realtime telemetry, jogging, and sequencing are fine. The project's hard-realtime answer is the EtherCAT path (`backends/ethercat_rtcore`), which does **not** work from in here — this container is on a bridge network with no added capabilities and is not privileged, so it cannot touch raw Ethernet.

## Reference implementation

The in-repo implementation lives at `src/gradient_os/arm_controller/backends/sts3215/protocol.py`, with constants in `src/gradient_os/arm_controller/backends/sts3215/config.py`. The bench notes in `SERVO-NOTES.md` (workspace root) are the authoritative guide for driving this specific servo.

**Note on register 0x2C:** On the STS3215, register 0x2C is "Goal Time" and writing 0x0000 during SYNC_WRITE is harmless. The HLS3950 has "Target Current" at the same address — writing 0 disables the motor. The two backends use different SYNC_WRITE layouts as a result. See `feetech-project/docs/protocols/feetech-hls.md` for the HLS-specific layout.
