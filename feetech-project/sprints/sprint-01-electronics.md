# Sprint 01 — Electronics Validation

## Goal

Wire the test bench safely, verify all electrical connections, and confirm the servo powers on correctly — before any software commands are sent.

## Prerequisites

- Sprint 00 complete (docs exist)
- Hardware on hand: Pi 5, URT-1, Micro USB cable, bench PSU, STS3215 servo, multimeter

## Tasks

### PSU setup
- [ ] Turn on bench PSU with nothing connected
- [ ] Set voltage to 12V
- [ ] Set current limit to 2A (conservative for one servo)
- [ ] Verify 12V with multimeter at PSU output terminals

### Wire PSU to URT-1
- [ ] PSU OFF
- [ ] Connect PSU V+ to URT-1 servo-power terminal (+)
- [ ] Connect PSU V- to URT-1 servo-power terminal (-)
- [ ] Continuity check: verify correct terminals with multimeter
- [ ] PSU ON, no servo connected
- [ ] Measure 12V at URT-1 servo-power terminal with multimeter
- [ ] Measure 12V at the SCS/TTL servo output port (V+ pin)
- [ ] PSU OFF

### Connect URT-1 to Pi
- [ ] Plug Micro USB cable into URT-1 and Pi
- [ ] Check `ls /dev/ttyUSB*` on the Pi (or host)
- [ ] Confirm URT-1 appears as /dev/ttyUSB0
- [ ] Note: if in Docker, device passthrough needs compose edit (requires human approval)

### Verify STS3215 voltage rating
- [ ] Check the STS3215 label for rated voltage
- [ ] Confirm it says 12V (not 6V or 7.4V)
- [ ] If not 12V — STOP and re-evaluate power plan

### Connect one servo
- [ ] PSU OFF
- [ ] Connect one STS3215 to URT-1 SCS/TTL port (3-pin)
- [ ] Verify connector orientation
- [ ] PSU ON
- [ ] Watch PSU current readout — should be low (idle, 50-200mA)
- [ ] If current spikes, cut power immediately
- [ ] Wait 30 seconds, touch-test servo — should not be hot
- [ ] PSU OFF

### Docker USB passthrough (if running in container)
- [ ] Discuss compose edit with human
- [ ] Add `devices:` block to host docker-compose.yml (WITH APPROVAL)
- [ ] Restart container
- [ ] Verify /dev/ttyUSB0 visible inside container

## Definition of done

- One STS3215 connected to URT-1, powered at 12V, idle current is reasonable
- No smoke, no heat, no unexpected current draw
- URT-1 visible as /dev/ttyUSB0 (on host or in container)
- All measurements documented in test-bench-wiring.md

## Safety

Read [docs/safety.md](../docs/safety.md) before starting. Key points:
- Set current limit low (2A)
- Verify voltage with multimeter before connecting servo
- Cut power if anything spikes
- Never walk away with power on