# Test Bench Wiring

Phase 1 electronics validation. The goal is a safely wired test bench with one servo responding to commands before any scaling.

## Components

| Component | Role |
|-----------|------|
| Raspberry Pi 5 | Host computer, runs the control software |
| Feetech URT-1 | USB-to-TTL/RS485 signal converter |
| Micro USB cable | Connects URT-1 to Pi USB port |
| 32V 10A benchtop PSU (CC/CV) | Provides regulated servo power |
| STS3215 servo (or HLS3950) | The servo under test |
| Multimeter | Voltage and continuity verification |
| Servo cables | URT-1 to servo, daisy-chain if multiple |

## URT-1 overview

From the URT-1 manual (FE-URT-1 USE MANUAL, FeiTe/Feetech):

- **USB interface:** Mini USB (per manual) — **verify your board**: user reports Micro USB. Check the physical port.
- **Two servo channels:**
  - **Channel A (SMS/RS485, 4-pin 5264-4AW):** for SMS series servos
  - **Channel B (SCS/TTL, 3-pin 5264-3AW):** for SCS series servos (STS3215 goes here)
- **Servo power terminal:** 5.08mm screw terminal block. This is where external PSU power connects. URT-1 does NOT regulate this voltage — it passes through to the servo bus.
- **Overcurrent limit on servo power port:** 6A. Fine for test bench; will need bypassing at full-arm scale.
- **USB power:** 500mA overcurrent/overvoltage protected. This powers only the URT-1's logic (USB-to-serial chip, signal level converter). It does NOT power servos.
- **Signal levels:** Switchable 5V or 3.3V (for the TTL channel). The URT-1 converts USB signals to these levels.
- **Driver:** CH340C chip. On Linux/Raspberry Pi, the `ch341` kernel module handles this. Device appears as `/dev/ttyUSB0`.
- **Auto signal routing:** Half-duplex with hardware auto-switching, no extra enable IO needed.

## Wiring steps (Phase 1)

### Step 1: Verify the PSU

- [ ] Turn on bench PSU with nothing connected to the output
- [ ] Set voltage to 12V
- [ ] Set current limit to 2A (low starting point for one servo)
- [ ] Verify voltage with multimeter at the PSU output terminals
- [ ] Confirm polarity: V+ and V- are correct

### Step 2: Wire PSU to URT-1 servo-power terminal

- [ ] PSU OFF
- [ ] Connect PSU V+ to URT-1 servo-power terminal (+)
- [ ] Connect PSU V- to URT-1 servo-power terminal (-)
- [ ] Double-check polarity with multimeter (continuity check from PSU terminal to URT-1 terminal)
- [ ] PSU ON, no servo connected yet
- [ ] Measure voltage at the URT-1 servo-power terminal with multimeter — confirm 12V
- [ ] Measure voltage at the servo output port (the 3-pin SCS/TTL connector) — confirm 12V present on the V+ pin
- [ ] PSU OFF

### Step 3: Connect URT-1 to Pi via USB

- [ ] Plug Micro USB cable into URT-1
- [ ] Plug other end into Pi USB port
- [ ] On the Pi, check for the device: `ls /dev/ttyUSB*`
- [ ] Confirm the URT-1 shows up (likely `/dev/ttyUSB0`)
- [ ] Note: if running inside Docker, this device won't be visible yet — needs `devices:` block in docker-compose.yml (requires human approval)

### Step 4: Connect one servo

- [ ] PSU OFF
- [ ] Connect one STS3215 to the URT-1's SCS/TTL port (3-pin connector)
- [ ] Double-check the connector orientation (anti-reverse design helps, but verify)
- [ ] PSU ON
- [ ] Watch the bench PSU current readout — should be low (idle current, maybe 50-200mA)
- [ ] If current spikes immediately, cut power and investigate
- [ ] Touch-test the servo after 30 seconds — should not be hot

### Step 5: Verify servo is alive (software, Phase 2)

This step is in sprint-02, not here. Phase 1 is purely electrical.

## Power architecture diagram (text)

```
  Bench PSU (32V 10A, CC/CV)
  ├── Set to 12V, current limit 2-3A
  │
  ├── V+ ──────────────────► URT-1 servo-power terminal (+)
  ├── V- ──────────────────► URT-1 servo-power terminal (-)
  │
  │   URT-1 (signal converter only, does NOT regulate voltage)
  │   ├── USB (Micro) ────► Raspberry Pi USB port (/dev/ttyUSB0)
  │   ├── SCS/TTL port (3-pin) ────► STS3215 servo
  │   └── SMS/RS485 port (4-pin) ──► (unused for STS3215)
  │
  │   Common ground: PSU V- = URT-1 GND = servo GND (tied internally by URT-1)
```

## Full-arm power architecture (Phase 7, future)

```
  High-current PSU (12V, 30A+)
  ├── V+ ──────────────────► Servo power bus/backbone (direct, bypasses URT-1)
  ├── V- ──────────────────► Servo power bus/backbone
  │
  │   URT-1 (signal only)
  │   ├── USB ────► Pi
  │   ├── Signal GND ────► tied to servo bus GND (common reference)
  │   ├── SCS/TTL signal ────► servos (signal pin only)
  │   └── URT-1 servo-power terminal: NOT used at scale (6A limit)
```

## Open items for this doc

- [ ] Confirm URT-1 USB port type (manual says Mini, user reports Micro — check the board)
- [ ] Confirm STS3215 is the 12V variant (verify with multimeter before connecting servo)
- [ ] Once HLS3950 is tested, add its wiring section (may use different URT-1 channel)
- [ ] Document Docker USB passthrough when the compose edit is approved