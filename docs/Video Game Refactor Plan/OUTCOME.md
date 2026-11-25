# GradientOS Feature Overhaul — Intended Outcome

## What we're building

Three major features for the GradientOS robot arm system, delivered in a
UI that feels like a video game rather than an engineering form:

1. **New arm support** — declarative TOML config, gear-ratio math,
   a joint-discovery ritual, and zeroing — so a new HLS3950 arm with
   different geometry and a gear-reduced J1 can be commissioned without
   editing Python code.
2. **Interchangeable end effectors** — a tool registry with hot-swap,
   runtime TCP offsets, and a separate ToolBackend for non-servo actuators
   (mosfets, relays).
3. **AprilTag routing** — planner `path_mode`/`pause_s` extensions and
   stub endpoints so the AprilTag vision sub-project slots in without
   re-architecting.

## The experience (target)

### You open the UI

The 3D viewport fills the screen — your arm rendered from its URDF,
sitting on the grid. The header shows a status pill: **"HLS3950 Arm ·
Gripper"** with a green connection dot. A new arm icon in the header
opens **Robot Studio**.

### Robot Studio — the hangar

A card grid like a character-select screen. Each card: thumbnail, name,
version, backend, solver. Click to mount. Switching arms shows a
**"Mount & Boot"** loading overlay ("Initializing servo bus…
Calibrating encoders…") — the restart happens behind it, no warning
dialog.

A second card row below: **End Effectors** — gripper, drill+mosfet,
2-servo claw. These mount **hot** — one click, no restart. The 3D arm
swaps the tool mesh instantly, the ControlPanel morphs (gripper slider ->
drill toggle -> claw sliders), and the status pill updates.

### Build-a-Bot — the VAB

"+ New Robot" opens a template picker ("6-DOF arm", "4-DOF", "SCARA",
"Custom"), not a URDF upload wall. URDF import is an optional "Import CAD"
action inside an existing robot's edit view.

### Joint Discovery Ritual — the centerpiece

Instead of typing servo IDs in a spreadsheet, you physically assemble the
arm and run a ritual that feels like calibrating a controller in a racing
sim:

1. **Pre-assembly:** plug servos in one at a time, rename from factory
   ID=1 to a temp unique ID (101, 102, ...). A wizard walks you through
   each servo with a progress bar.

2. **Discovery:** all servos on the bus with unique temp IDs. The
   software puts all servos into **super-low PID compliance** (you can
   push them by hand but they don't free-fall). The UI dims, spotlights the
   3D model, and says **"J1 of 6 — move joint 1 by hand."**

3. You grab the arm and wiggle J1. The corresponding joint on the 3D model
   **lights up** with a pulsing halo. The detected servo card pulses cyan.
   You sweep to both mechanical limits — bars fill green and **click** at
   the hard stops, like tuning an RC transmitter.

4. If two servos move together (twin-motor shoulder), the UI detects
   correlation and asks **"2 servos moving together — same joint?"** with
   confirm/split buttons. A brace bracket links the two servo cards.

5. Enter gear ratio (default 1:1; your J1 with 1:2 reduction types 2.0).

6. **Lock J1:** snap-into-place animation, mechanical clench, glow flips
   blue->green, checkmark stamps, step counter advances: **"J2 of 6 —
   move joint 2 by hand."** Six of these and you've commissioned the arm
   in under 90 seconds.

7. The ritual writes `joints.toml` + `robot_info.csv` (a spreadsheet-
   readable full spec of every joint).

### Zeroing

Per-joint "Set current as zero" with a live raw-position readout. Move
the joint to where you want zero, click the button, done. Works for tool
servos too.

### Piloting — the cockpit

The 3D viewport IS the jog controller, not a 12-button wall:

- **Puppet mode:** click-drag the tool-tip in 3D; the arm follows via IK
  with a live cyan ghost preview. Release to commit. Shift = fine mode,
  Ctrl = axis-constrain.
- **Button mode:** the jog grid, demoted to precision fallback.
- **Orbit mode:** the default Three.js camera.

A **throttle slider** with a green/yellow/red ramp. **Spacebar = STOP**,
always. Joint stress tints the 3D mesh yellow->red (MechWarrior paper-doll
damage). Hover a joint for exact V/I/temp.

### Trajectory planning — the mission planner

The 3D path is the primary editor — add waypoints by clicking in space,
drag them in 3D, the ribbon draws itself. A **timeline scrubber** under
the viewport previews the move (Into the Breach style) — drag it and
the ghost arm animates through the path before you commit to the real arm.

Per-waypoint **floating cards** pop next to the markers in 3D: path-mode
chips (linear/capture-speed), speed slider, pause field. A playlist-style
sidebar list (not a tree) for reordering.

### AprilTag (reserved for sub-project)

A vision panel slot is reserved with stub endpoints. The planner already
supports `path_mode` and `pause_s` so the sub-project slots in without
re-architecting. Camera calibration + hand-eye are a separate sub-project.

### Command palette (Cmd+K)

Fuzzy-search any action: "mount drill", "zero J3", "plan linear",
"focus on tool", "e-stop". Keyboard-first power-user access.

## What's under the hood

- **Declarative TOML config** per arm + per tool, replacing Python classes.
  Editable in the UI, saved to disk, spreadsheet-exportable as CSV.
- **Gear ratio** support across all 9 angle-conversion code paths
  (including the closed-loop executor that was silently missing from
  the first draft).
- **HLS3950 backend** already exists; the new arm uses it.
- **ToolBackend** — a separate interface for mosfets/relays/GPIO that
  doesn't fit the servo model. Hot-swap with a quiescence barrier (abort
  motion -> park -> torque off -> swap -> torque on).
- **Runtime TCP offset** replacing the hardcoded `END_EFFECTOR_OFFSET`
  constant — tools define their own tool-tip offset (3-vector,
  world-frame-at-zero-pose rotated by target rotation; rotation
  component deferred to v2).
- **Planner** gets `path_mode` (linear/capture-speed) + per-waypoint
  `pause_s`. Joint-space mode deferred to a future phase.
- **All calibration/discovery data** on a dedicated `/calibrate/stream`
  SSE endpoint (not multiplexed into `/monitor` — that would break
  the existing `handleMessage` telemetry parser).
- **Single-node deployment** (controller + API share filesystem).
  Distributed config replication is out of scope for this release.

## What an agent receives

Each of the 14 implementation chunks in `docs/PLAN.md` is self-contained:
an AI agent implements one chunk, runs the three gates (`pytest tests/`
with 0 skipped, `npm run test:run`, `npm run build`), and produces a
working PR. The full specs (TOML schemas, API Pydantic models,
motion-detection algorithm, ABC signatures, state machine, gear-ratio edit
list, component props, store scope) are in `docs/PLAN.md`.

## Success criteria

- A new user can commission a new arm (pre-assembly rename -> discovery
  ritual -> zeroing) in under 10 minutes without touching a Python file.
- Gear-reduced joints (J1 1:2) move correctly in all modes (open-loop,
  profiled, closed-loop, streaming, jog).
- Tools hot-swap in one click; the ControlPanel morphs; the 3D arm updates.
- Trajectory preview shows the move before commit.
- The existing gradient0 arm works identically after TOML migration.
- `pytest tests/` (0 skipped), `npm run test:run`, `npm run build` all
  pass after every chunk.
