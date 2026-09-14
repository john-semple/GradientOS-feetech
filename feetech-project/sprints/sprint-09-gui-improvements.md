# Sprint 09 — GUI Improvements: Jog Controls, Calibration UI, Config Selector

> Created 2026-09-11.
> This is a web-UI-focused sprint. The backend command paths for calibration already
> exist (UDP: `CALIBRATE`, `SET_ZERO`, `FACTORY_RESET` in `run_controller.py`) but are
> not exposed through the FastAPI API or the web UI. Part of this sprint is bridging
> that gap.

## Goal

Improve the web UI's operator-facing workflows in three areas: (1) fix and expand the
jog controls, (2) add a servo ID assignment + joint calibration screen, and (3) add a
robot configuration / servo / attachment selector screen. An optional fourth workstream
adds RC-controller / gamepad input as an alternative jog method.

## Prerequisites

- Web UI running (`./run-web.sh`) with API + controller online ✅ (existing)
- Sprint 04 (endpoint-paradigm quick fix) complete ✅ — jog velocity path works
- Sprint 08 (full-arm hardening) recommended first or consciously deferred —
  calibrating joint limits is safer on a hardened power bus, but the calibration UI
  can be built and tested independently on the bench arm
- Physical arm or simulator available for validation

## Workstream A — Jog Controls Investigation & Rework

### Problem statement

The current jog controls (`ControlPanel.tsx` lines 262-589) are **Cartesian-only**:
linear XYZ velocity jog and angular Roll/Pitch/Yaw velocity jog, both IK-solved by the
backend (`_jog_controller_thread` in `command_api.py` lines 1138-1306). There is **no
per-joint jog** (J1-J6 individual control). The angular buttons are labeled
`+Roll/+Pitch/+Yaw` but internally map `ac.x→v_roll, ac.y→v_pitch, ac.z→v_yaw`, which
is consistent within the code but may not match the operator's mental model of the
arm's frame. The "misassignment" the user perceives is likely one or more of:

1. **No joint-level jog** — an operator who wants to move one servo/joint independently
   has no way to do it from the web UI (only the legacy PyQt UI has this).
2. **Frame ambiguity** — the RPY labels don't indicate which way the arm actually moves
   (e.g. "+Y = away from base?" is not obvious without visual cues).
3. **No jog mode toggle** — the panel jumps between realtime velocity and incremental
   based on a checkbox, which is not discoverable.

### Tasks

- [ ] **Investigate**: Reproduce the jog control confusion on the live arm. Document
      exactly which jog button produces an unexpected motion and why (frame convention,
      sign flip, IK singularity, etc.). Write findings to `DEVLOG.md`.
- [ ] **Add per-joint jog mode**: Add a toggle between "Cartesian jog" (current XYZ+RPY)
      and "Joint jog" (J1-J6, one row per joint with +/− buttons or a slider). The
      joint-jog path should send individual servo position deltas via a new API
      endpoint (or reuse the existing UDP command path exposed through FastAPI).
- [ ] **Add an API endpoint for joint jog**: `POST /control/jog/joint` with
      `{joint_id, delta_deg, speed}` that commands a single logical joint. If the
      backend already supports this through the UDP path, wrap it in FastAPI instead
      of duplicating logic.
- [ ] **Fix frame labeling**: Add visual indicators on the jog buttons showing the
      physical motion direction (e.g. "Base ↻", "Elbow up", "Wrist ↺") alongside or
      instead of the abstract `+X / +Roll` labels. Consider a small frame diagram.
- [ ] **Improve jog mode discoverability**: Make the realtime vs incremental toggle a
      clear segmented control (two buttons: "Velocity" / "Step"), not a checkbox.
- [ ] **Add deadman visual feedback**: When deadman is required and not held, grey out
      jog buttons and show a "Hold deadman" overlay or badge.
- [ ] **Jog sensitivity presets**: Add coarse/fine toggle or a visible step-size
      readout so the operator knows how far a click will move the arm.
- [ ] Validate all jog modes on the physical arm (or sim) — record which buttons move
      which joints and confirm labels match motion.

### Definition of done (Workstream A)

- Joint-level jog (J1-J6) works from the web UI
- Cartesian jog labels are unambiguous (operator can predict motion direction)
- Velocity / Step mode is a clear toggle, not a hidden checkbox
- No jog button produces motion that contradicts its label
- `npm run build` passes

---

## Workstream B — Servo ID Assignment & Calibration Screen

### Problem statement

There is **no calibration UI in the web UI**. The legacy PyQt UI
(`ui/pages/calibration_page.py`) has `CALIBRATE`/`SET_ZERO`/`FACTORY_RESET` controls,
but those commands are UDP-only (`run_controller.py` lines 277-471) and not exposed
through the FastAPI API. The operator needs a guided flow:

1. Click a button to enter calibration mode.
2. For each joint, the UI prompts: "Move joint N to its maximum [positive/negative]
   position."
3. The operator jogs the joint to the limit (using the new joint jog from Workstream A,
   or by manually pushing the arm if torque-off is supported).
4. The UI reads the raw servo position and records it as the min/max limit.
5. After all joints are calibrated, the UI writes the limits to servo EEPROM (with
   explicit human confirmation) and/or saves them as the robot config's
   `actuator_limits_rad`.

### Tasks

- [ ] **Expose calibration commands via FastAPI**: Add endpoints to `api/main.py`:
  - `POST /control/calibrate/enter` — enter calibration mode (torque off on target
    servos, start streaming raw positions)
  - `POST /control/calibrate/exit` — exit calibration mode, restore torque
  - `GET  /control/calibrate/positions` — return current raw positions for all servos
    (or SSE stream like the existing telemetry path)
  - `POST /control/calibrate/set-zero` — zero a specific joint
  - `POST /control/calibrate/write-limits` — write min/max to servo EEPROM (requires
    confirmation param)
  - `POST /control/calibrate/factory-reset` — factory reset a specific servo ID
- [ ] **Build the calibration screen** as a new panel in the web UI (new sidebar item
      or a modal launched from the control panel). The screen should:
  - List all joints (J1-J6 + gripper) with their current servo IDs and raw positions
  - Provide a guided step-by-step flow: for each joint, prompt "Move to max +", "Move
    to max −", capture the position, show it
  - Show a live raw-position readout per servo during calibration
  - Display the captured min/max next to each joint
  - Have a "Write limits to EEPROM" button with a confirmation dialog (danger action)
  - Have a "Save as config" button that persists the limits to the robot config
- [ ] **Add servo ID assignment**: Within the calibration screen (or a sub-screen),
      allow the operator to view and reassign servo IDs. This may require:
  - Reading the current ID of a servo (PING scan)
  - Writing a new ID to the servo EEPROM
  - Re-scanning to confirm
  - Backend endpoint: `POST /control/servo/set-id {old_id, new_id}`
- [ ] **Safety interlocks**: Torque must be off before ID write. Confirm before any
      EEPROM write. Show a warning that changing IDs requires re-powering the bus.
- [ ] Test the full calibration flow on the bench arm with at least 2 servos.

### Definition of done (Workstream B)

- Operator can enter calibration mode from the web UI
- Guided joint-by-joint min/max capture works with live position readout
- Limits can be written to servo EEPROM from the web UI with confirmation
- Servo IDs can be viewed and reassigned from the web UI
- `npm run build` passes; API endpoints tested

---

## Workstream C — Robot Configuration & Attachment Selector (lower priority)

### Problem statement

The robot config system is pluggable (`RobotConfig` ABC in `robots/base.py`) but only
one robot (`gradient0`) exists. The operator has no way to select a different robot
configuration, servo backend (STS3215 vs HLS3950), or attachment (gripper type) from
the web UI. The config is set at startup in the controller.

### Tasks

- [ ] **Design the selector screen**: A modal or full-screen panel that lets the
      operator pick:
  - **Robot geometry**: a named robot config (e.g. "Gradient0 6-DOF", future configs)
  - **Servo backend**: STS3215 / HLS3950 (maps to `default_servo_backend` in the
    config, or an override)
  - **Attachment**: gripper type / none (future: different grippers, tool changers)
  - Show a summary card for each option (joint count, servo count, DH params preview)
- [ ] **Backend endpoint**: `GET /config/robots` — list available robot configs by
      scanning `robots/` directory for `RobotConfig` subclasses. `POST /config/active`
      — set the active robot (calls `set_active_robot()`). Note: this likely requires
      a controller restart or hot-reload — determine whether hot-reload is feasible or
      if a "save + restart" pattern is needed.
- [ ] **Attachment model**: Add an `AttachmentConfig` concept to the robot config (or
      a separate registry) so grippers/tools are swappable, not hardcoded. At minimum,
      define the interface even if only one gripper is implemented.
- [ ] **Persistence**: Save the selected config to `localStorage` and/or a server-side
      config file so it persists across restarts.
- [ ] Build the UI with cards/radio buttons, a preview of the selected config, and a
      confirm button.
- [ ] If hot-reload is not feasible, implement a "Apply & Restart Controller" flow
      that gracefully shuts down and restarts the controller with the new config.

### Definition of done (Workstream C)

- Selector screen renders available robot configs, servo backends, and attachments
- Selecting a config and applying it changes the active robot (via restart if needed)
- The selection persists across restarts
- `npm run build` passes

---

## Workstream D — RC Controller / Gamepad Input (optional, lower priority)

### Problem statement

There is **no gamepad/joystick/RC input handling anywhere in the repo**. The operator
controls the arm exclusively through the web UI or legacy PyQt UI. An RC controller
or USB gamepad would provide tactile, proportional jog control — especially useful
for calibration (Workstream B) and manual positioning.

### Tasks

- [ ] **Research input options**: Determine the best approach:
  - **Browser Gamepad API** (`navigator.getGamepads()`) — works in the web UI, no
    backend changes needed, but limited to USB/Bluetooth gamepads visible to the
    browser host
  - **Backend evdev/pygame** — reads `/dev/input/js*` on the Pi, sends jog commands
    directly; works with RC receivers via USB dongles; requires backend code
  - **Hybrid** — browser Gamepad API for UI-side, backend evdev for headless operation
- [ ] **Implement the chosen approach**:
  - If browser Gamepad API: add a `useGamepad` hook in the web UI that polls
    `navigator.getGamepads()`, maps axes to jog velocities, and sends them through
    the existing `POST /control/jog/velocity` endpoint. Add a "Connect Controller"
    button and a mapping configuration UI (which axis → which DOF).
  - If backend evdev: add an input device listener to the controller that reads
    joystick events and feeds them into the jog controller thread. Add API endpoint
    to configure the axis mapping.
- [ ] **Controller mapping UI**: Let the operator assign axes/buttons to jog DOFs
  (linear X/Y/Z, angular roll/pitch/yaw, or joint J1-J6). Include a deadzone
  setting and a max-velocity scaling slider.
- [ ] **Safety**: Require deadman (button hold) on the gamepad to enable motion.
      Auto-stop on disconnect. Show a "Controller connected" indicator in the UI.
- [ ] Test with at least one real input device (USB gamepad or RC dongle).

### Definition of done (Workstream D)

- An RC controller or gamepad can jog the arm with proportional control
- Axis mapping is configurable from the web UI
- Deadman safety works (motion stops when button released or controller disconnected)
- Connection status is visible in the UI
- `npm run build` passes

---

## Sequencing & Notes

- **Workstream A (jog controls) should go first** — the calibration flow in
  Workstream B needs joint-level jog to move individual joints to their limits.
- **Workstream B (calibration) depends on A** for joint jog, and on new FastAPI
  endpoints to bridge the existing UDP calibration commands.
- **Workstream C (config selector) is independent** and can be done in parallel with
  A or B, but is lower priority and may require backend architecture work (hot-reload
  or restart-on-config-change) that could expand scope.
- **Workstream D (RC input) depends on A** (jog velocity endpoint already exists, but
  joint jog endpoint from A is needed if RC controls individual joints). It is
  optional and can be deferred.
- If scope is too large for one sprint, split: A+B as "Sprint 09a: Jog + Calibration",
  C+D as "Sprint 09b: Config Selector + Input Device". The workstreams are designed
  to be splittable.
- The web UI is a single-file monolith (`App.tsx` is 4090 lines). Consider extracting
  the new calibration screen and config selector into separate component files
  (following the `ControlPanel.tsx` / `TelemetryCharts.tsx` pattern) rather than
  growing `App.tsx` further.
- All new FastAPI endpoints should follow the existing patterns in `api/main.py`
  (error handling, response models, controller-availability checks).
- EEPROM writes are irreversible-ish (require factory reset to undo). Every EEPROM
  write endpoint must require an explicit confirmation parameter and log the action.