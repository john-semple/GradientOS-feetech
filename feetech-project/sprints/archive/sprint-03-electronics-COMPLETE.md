# Sprint 03 — Electronics Validation

## Goal

Wire the test bench safely, verify all electrical connections, and confirm the servo powers on correctly — before any software commands are sent.

## Prerequisites

- Sprint 00 complete (docs exist)
- Hardware on hand: Pi 5, URT-1, Micro USB cable, bench PSU, STS3215 servo, multimeter

## Tasks

### PSU setup
- [x] Turn on bench PSU with nothing connected
- [x] Set voltage to 12V
- [x] Set current limit to 2A (conservative for one servo)
- [x] Verify 12V with multimeter at PSU output terminals

### Wire PSU to URT-1
- [x] PSU OFF
- [x] Connect PSU V+ to URT-1 servo-power terminal (+)
- [x] Connect PSU V- to URT-1 servo-power terminal (-)
- [x] Continuity check: verify correct terminals with multimeter
- [x] PSU ON, no servo connected
- [x] Measure 12V at URT-1 servo-power terminal with multimeter
- [x] Measure 12V at the SCS/TTL servo output port (V+ pin)
- [x] PSU OFF

### Connect URT-1 to Pi
- [x] Plug Micro USB cable into URT-1 and Pi
- [x] Check `ls /dev/ttyUSB*` on the Pi (or host)
- [x] Confirm URT-1 appears as /dev/ttyUSB0
- [x] Note: if in Docker, device passthrough needs compose edit (requires human approval) — **resolved via Design B USB passthrough (udev mirror + bind-mount /dev/openchamber:/dev/serial)**

### Verify STS3215 voltage rating
- [x] Check the STS3215 label for rated voltage
- [x] Confirm it says 12V (not 6V or 7.4V)
- [x] If not 12V — STOP and re-evaluate power plan

### Connect one servo
- [x] PSU OFF
- [x] Connect one STS3215 to URT-1 SCS/TTL port (3-pin)
- [x] Verify connector orientation
- [x] PSU ON
- [x] Watch PSU current readout — should be low (idle, 50-200mA) — **measured 299mA (acceptable for 12V STS3215)**
- [x] If current spikes, cut power immediately — **no spike**
- [x] Wait 30 seconds, touch-test servo — should not be hot — **confirmed cool**
- [x] PSU OFF

### Docker USB passthrough (if running in container)
- [x] Discuss compose edit with human
- [x] Add `devices:` block to host docker-compose.yml (WITH APPROVAL) — **implemented as Design B: udev mirror + device_cgroup_rules + group_add + bind-mount**
- [x] Restart container
- [x] Verify /dev/ttyUSB0 visible inside container — **visible as /dev/serial/ch340 (stable alias) and /dev/serial/ttyUSB0**

## Definition of done

- [x] One STS3215 connected to URT-1, powered at 12V, idle current is reasonable (299mA)
- [x] No smoke, no heat, no unexpected current draw
- [x] URT-1 visible as /dev/ttyUSB0 (on host or in container) — visible on host as /dev/ttyUSB0, in container as /dev/serial/ch340
- [x] All measurements documented in test-bench-wiring.md

## Safety

Read [docs/safety.md](../docs/safety.md) before starting. Key points:
- Set current limit low (2A)
- Verify voltage with multimeter before connecting servo
- Cut power if anything spikes
- Never walk away with power on