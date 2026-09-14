# Sprint 02 — Study GradientOS Architecture

> **Largely COMPLETE 2026-09-08** — the deep study happened as part of the motion-jerkiness
> diagnosis (see `GradientOS/docs/jerkiness-diagnosis.md` §5, §7, §8 for the full traces).
> What remains is filling in the two stub docs in `docs/gradientos/`. The teaching section
> below (§"GradientOS Architecture Crash Course") now lives here as the primary output.

## Goal

Clone GradientOS, understand its architecture, and document how to add a new servo protocol backend. No code edits.

## Prerequisites

- STS3215 protocol validated ✅ (sprint-01-sts3215-protocol.md, complete)
- Human says "go" to clone GradientOS ✅ (approved, done)

## Tasks

### Clone
- [x] Human approved clone
- [x] Forked GradientOS as `GradientOS-feetech` on GitHub
- [x] Cloned fork to `/home/ubuntu/workspaces/GradientOS/` (origin = fork, upstream = original)
- [x] Cloned upstream reference to `/home/ubuntu/workspaces/GradientOS-upstream/`

### Study the codebase
- [x] Identify the language(s) and overall structure (Python controller + FastAPI API + React web UI + C IK solver extension)
- [x] Find the hardware/servo abstraction layer (`arm_controller/actuator_interface.py` ABC + `backends/` registry)
- [x] Find the EtherCAT protocol implementation (`backends/ethercat_rtcore/` — RTOS path, separate from the Python bus path)
- [x] Determine if there's an interface/abstract class for servo backends (`ActuatorBackend` ABC; `FeetechBackend` implements it)
- [x] Study the "build your own robot" workflow (`robots/` registry + `RobotConfig` ABC; `--robot` CLI flag)
- [x] Understand the joint model: can a joint map to multiple actuators? (YES — `logical_to_physical_map`; twin motors 20/21, 30/31; feedback read from primary only, secondary mirrored)
- [x] Understand config format: how are servos, joints, and robot geometry defined? (`RobotConfig` ABC properties; `robots/gradient0/config.py` has IDs, limits, PID gains, offsets)
- [x] Check safety mechanisms (URDF joint limits clamped before every write; servo EEPROM angle limits; e-stop = STOP command flag)
- [x] Check the web UI structure and how it interfaces with the backend (React → FastAPI `/control/*` endpoints → UDP commands → controller loop)
- [x] Check license and any constraints on modification (MIT — no constraints)

### Document findings
- [ ] Fill in docs/gradientos/architecture-notes.md ← **remaining**
- [ ] Fill in docs/gradientos/adding-a-servo-family.md ← **remaining**
- [x] Identify the specific files/classes that need to be modified or extended (backends/<family>/ config+protocol+driver; robots/<robot>/config.py; registry entries)
- [x] Identify whether a plugin system exists or if core changes are needed (registry pattern — new backends/robots register via modules, no core edits)
- [x] Document the plan for STS3215 and HLS3950 backend implementation (STS3215: implemented at `src/gradient_os/arm_controller/backends/sts3215/`; HLS3950: see the HLS sprint)

## Definition of done

- [x] GradientOS architecture is documented (crash course below; full-doc fill-in remains)
- [x] The extension path for a new servo family is clearly identified
- [x] Specific files and interfaces to implement are listed
- [ ] Open questions from docs/gradientos/ are answered (two stub docs remain)

---

## GradientOS Architecture Crash Course

> This section is the teaching deliverable of Sprint 02 — an AI-led walkthrough of how
> GradientOS is put together, written for the project owner. It focuses on the parts that
> matter for this project: robot selection, servo-backend selection, and how a command
> becomes motion. File references use paths under `src/gradient_os/`.

### 1. The two-axis selection system: robots × backends

GradientOS is deliberately built so that **"what robot am I driving?"** and **"how do I
talk to the motors?"** are two independent choices:

```
            run_controller.py startup
            ┌────────────────────────────────┐
            │  --robot gradient0   (WHAT)    │
            │  --servo-backend feetech (HOW) │
            └───────────────┬────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
  ROBOT REGISTRY                        BACKEND REGISTRY
  robots/__init__.py                    backends/__init__.py + registry.py
  "gradient0", "gradient0_5", ...       "feetech", "simulation", ...
        │                                       │
        ▼                                       ▼
  RobotConfig (ABC)                     ActuatorBackend (ABC)
  robots/gradient0/config.py            backends/feetech/driver.py
  - servo IDs (10,20,21,30,31…)          - serial protocol (SCS/STS frames)
  - joint limits (rad)                   - register addresses (0x29, 0x38…)
  - twin-motor mapping                   - encoder resolution (4095)
  - PID gains per actuator               - sync read/write batching
  - master calibration offsets           - PID write, zeroing, factory reset
```

Both registries are module-level Python registries (dicts) — there is no plugin loader or
config file parsing. Adding a robot = implementing the `RobotConfig` ABC in a new
`robots/<name>/config.py` and registering it. Adding a servo family = implementing the
`ActuatorBackend` ABC in `backends/<family>/` and registering it. Nothing in the core
changes; that is the whole design principle ("no hardcoded values in high-level code").

### 2. The startup sequence (how selection actually happens)

`run_controller.py` main():

1. Parse CLI args: `--robot gradient0 --servo-backend feetech`
2. `get_robot_config("gradient0")` → looks up the robot registry → instantiates `Gradient0Config`
3. `robot_config.set_active_robot(selected_robot)` → publishes the active robot's values
   into module-level constants (`robot_config.SERVO_IDS`, `LOGICAL_TO_PHYSICAL_MAP`, …)
   that legacy code still reads
4. Backend class from `backends/__init__.py`'s `BACKEND_CLASSES` dict → instantiated with
   the robot's config dict → `backend.initialize()` (opens serial port, pings servos,
   applies PID gains)
5. `backend_registry.set_active_backend_instance(backend)`
6. `utils._populate_servo_constants()` / `_populate_robot_constants()` — pulls encoder
   resolution, baud rate, PID defaults, etc. from the active backend config and robot
   config into `utils` module constants

After step 6, **every module in the codebase can ask three places for truth**:

| Who asks | Where they look |
|---|---|
| "How many joints? What limits? What IDs map to joint 2?" | `robot_config.*` (active robot) |
| "What encoder resolution? Baud? How do I write a register?" | active backend instance / `utils` constants |
| "Is a backend active at all?" | `backends.registry.get_active_backend()` |

The `utils.current_logical_joint_angles_rad` global is the shared belief of where the
arm is; the trajectory executors update it, and planners read it as the start of the next
move.

### 3. The command path: UI button → motion

Full chain, using the Home button (the one motion that is smooth today):

```
React web UI (web-ui/src)
  → POST /control/home  (FastAPI, src/gradient_os/api/main.py:417)
  → UDP message "0,0,0,0,0,0" to controller
  → run_controller.py UDP loop parses it as raw joint angles (:983-997)
  → servo_driver.set_servo_positions(angles, speed=500, accel=500)
  → backend.sync_write([(servo_id, raw_pos, speed, accel), …])   ← ONE packet
  → Feetech protocol frames on the wire (URT-1 → servo bus)
  → servo firmware: internal trapezoidal profile to the goal
```

Key structural fact: there are **two command channels** into the controller —
the UDP command loop (raw angles and high-level commands) and the FastAPI layer that
wraps the same handlers. Everything ends at `servo_driver`/backend sync_write.

### 4. The motion pipeline: planner → executor → servo

Two paradigms coexist, and this is the crux of the jerkiness diagnosis:

**Single-point path** (Home, TRANSLATE, ROTATE, joint moves):
one IK solve → one sync_write → firmware profiles the move.

**Trajectory path** (MOVE_LINE, trajectories like rotysquare, jog):
`trajectory_planner.generate_trapezoidal_profile` (Cartesian, time-parametrized) →
IK batch solve per point (`ik_solver.solve_ik_path_batch`) → unwrap + Savitzky-Golay
smoothing → dense joint path (~100 Hz) → executor thread streams position setpoints
via sync_write at 50–100 Hz. The streamed setpoints carry speed=4095/accel=0 (max/max),
which is what bypasses the servo's internal profiler and produces the reported jerkiness
(full analysis: `GradientOS/docs/jerkiness-diagnosis.md`).

Executors (`trajectory_execution.py`):
- `_open_loop_executor_thread` — write-only stream, 100 Hz
- `_closed_loop_executor_thread` — sync-read feedback each cycle, computes error telemetry,
  but the software correction is currently disabled (commands the raw planned target)
- `_jog_controller_thread` (command_api.py) — 25 Hz velocity integration + IK per cycle

### 5. Logical joints vs physical actuators (twin motors)

A 6-DOF logical arm has 9 physical servos here, because J2 and J3 are driven by paired
motors (IDs 20+21, 30+31). The mapping lives in the robot config:

- `logical_joint_to_actuator_ids`: joint 1 → [10], joint 2 → [20, 21], …
- Commands are built per physical servo; feedback is read from the **primary** only
  (20, 30) and the partner's reading is synthesized by mirroring (backlash offset is
  future work — the paired-joint sprint).
- The IK solver only ever sees the 6 logical angles; the twin mapping is invisible above
  the backend/servo_driver layer.

### 6. What this means for adding the HLS3950

Because selection is two-axis, adding the HLS3950 touches **only the HOW axis**:

1. New `backends/hls/` — config (registers, baud), protocol (frame builder/parser),
   driver (ActuatorBackend implementation), registered in `BACKEND_CLASSES`
2. Robot configs choose it via `default_servo_backend = "hls"` or CLI override
3. `robots/gradient0/config.py` needs nothing — unless the HLS arm geometry differs,
   in which case that's a new *robot*, not a new backend

The reverse is also true: the same Feetech backend can drive different arms by pairing
it with different robot configs. That is the payoff of the architecture — servo family
and kinematics never tangle.

### 7. Where the sharp edges are (learned from the diagnosis work)

- **Migration is mid-flight**: `servo_protocol.py` is a deprecated dispatcher kept for
  compatibility; new code should call the backend directly. Some modules still read
  `utils` constants populated at startup — always populate before use.
- **The executors hardcode streaming parameters** (speed=max/accel=0) in shared code —
  the current jerkiness root cause, and the reason Sprint 04 (endpoint-paradigm) adds a
  backend capability flag instead of editing executors globally.
- **Closed-loop reads but doesn't correct** — software PID is intentionally disabled
  ("during tuning"); it's open-loop with extra bus reads today.
- **Time on the bus is precious**: ~3 ms per transaction floor, so batched sync
  read/write is mandatory for multi-servo cycles; per-servo reads cap at ~38 Hz.

## Notes

- This is a read-only phase. No edits to GradientOS.
- Two clones exist: `GradientOS/` (fork, for edits) and `GradientOS-upstream/` (reference, pull-only).
- GradientOS already has a Feetech backend at `src/gradient_os/arm_controller/backends/sts3215/` — studied in detail during the diagnosis.
- License: MIT (Angus Muffatti, 2025) — no modification constraints.