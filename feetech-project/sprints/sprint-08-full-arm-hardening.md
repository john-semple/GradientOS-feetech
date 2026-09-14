# Sprint 08 — Full-Arm Hardening: Power, Stability, and Safety

> Restructured 2026-09-08 from the old "Sprint 07 — Full 6DOF Arm Config & Scale".
> **Most of the original sprint is already done in practice**: the 8-servo arm is built,
> wired, and runs through GradientOS daily (`feetech-project/code/coordinated_home.py`
> drives all 8 servo IDs; the robot config `robots/gradient0` exists and works; the
> user pressure-tests the physical arm). What remains is the operational hardening that
> was never done because the project jumped from bench-scale to full-arm organically.

## Goal

Harden the existing working 8-servo arm for reliable, safe, repeatable operation: proper
power distribution, stable USB naming, verified joint limits, and operator documentation.

## What dropped from the original sprint (and why)

- ~~"Create full 6DOF robot config"~~ — exists (`src/gradient_os/arm_controller/robots/gradient0/config.py`), arm runs on it
- ~~"Command joints through GradientOS"~~ — daily reality (jog, Home, rotysquare)
- ~~"Verify feedback channels"~~ — telemetry streams to the web UI already
- ~~"Test web UI with full arm"~~ — the web UI is the primary control path
- What survived: the power-bus design (bench PSU is not a permanent mount), udev
  stability, real joint-limit verification (servos are currently UNRESTRICTED 0-4095 per
  the EEPROM check in the protocol doc — the arm relies on software clamps only),
  temperature monitoring over long runs, and the operator handoff doc

## Prerequisites

- The physical arm (present, running) ✅
- Sprint 06 (paired joints) complete or consciously deferred
- Sprint 04b (endpoint-paradigm quick fix) recommended first — hardening motion before
  hardening wiring avoids debugging two variables at once

## Tasks

### Power distribution
- [ ] Design servo power bus/backbone for 8 servos (bypass URT-1's 6A limit)
- [ ] Source appropriate power wiring (bus bar or heavy-gauge backbone)
- [ ] Wire URT-1 for signal only, with ground tied to servo bus ground
- [ ] Determine appropriate PSU for full arm (bench PSU not practical mounted)
- [ ] Add inline fuses or current limiting per joint group
- [ ] Measure worst-case simultaneous-move current draw (8 servos accelerating together)

### USB device stability
- [ ] Write udev rule on the Pi host for stable URT-1 naming (by serial number)
- [ ] Install udev rule on host with sudo (human does this)
- [ ] Verify URT-1 appears at stable name after replug
- [ ] Physical USB unplug/replug test — check `journalctl -t openchamber-usb-mirror` after (carried from TODO blocked items)

### Joint limits & safety
- [ ] Audit `URDF_JOINT_LIMITS` in the robot config against the physical arm's real
      mechanical limits (currently software-clamped only; servo EEPROM limits are
      UNRESTRICTED 0/4095 — a config error could swing a joint into a hard stop)
- [ ] Write verified limits to servo EEPROM (`apply_joint_limits` exists in the backend) —
      with human approval per the EEPROM guardrails
- [ ] Verify e-stop behavior: STOP command flag halts streams promptly at full arm scale
- [ ] Temperature soak: run a long trajectory loop, log all 8 servo temps (`0x3F`),
      confirm none exceed ~50 °C under continuous duty

### Document
- [ ] Document the full arm wiring and power distribution
- [ ] Update safety doc with full-arm considerations
- [ ] Create an operator handoff doc for running the arm (startup, shutdown, jog, home,
      trajectory loading, what the alerts mean, what to do on oscillation)

## Definition of done

- Power backbone handles full simultaneous load without sagging (measured)
- USB device naming stable across replugs
- Joint limits verified mechanically and (optionally) written to EEPROM
- Temperature soak passes with margin
- Operator handoff doc exists

## Notes

- This is now a hardening sprint, not a bring-up sprint — bring-up already happened.
- The power backbone is critical — voltage sag at the end of the chain causes erratic
  behavior (and may be a confounder in motion-smoothness debugging; do power first if
  oscillation persists after sprint-04)).
- Consider per-servo or per-joint fuses to protect against a single stalled servo cooking
  itself (stall current measured ~0.67 A brief spike; sustained jam may read higher).