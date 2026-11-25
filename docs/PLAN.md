# GradientOS Feature Overhaul — Implementation Plan

> Branch: `feat/robot-studio-tools-apriltag`
> Status: SPECIFICATION — ready for agent handoff
> Scope: single-node deployment (controller + API share filesystem)

---

## Overview

Three features delivered as 14 self-contained implementation chunks:

1. **Declarative TOML config** replacing Python-class robot configs, with
   gear-ratio support across all angle-conversion code paths.
2. **Interchangeable end effectors** with a tool registry, runtime TCP offsets,
   a separate ToolBackend for non-servo actuators, and hot-swap.
3. **Planner `path_mode`/`pause_s` extensions** + AprilTag routing stubs.

Each chunk is sized so an AI agent can implement it, run the three gates
(`pytest tests/` with 0 skipped, `npm run test:run`, `npm run build`), and
produce a single working PR.

---

## Dependency graph + parallel tracks

```
Chunk 0  (config-to-startup wiring + test shim)
  └-> Chunk 1a (TOML schema + loader + GET API + CSV)
        └-> Chunk 1b (gear ratio across 9 code paths) ───────────┐
              └-> Chunk 2  (Robot Studio UI + store + App.tsx)     │
                    └-> Chunk 3  (ABC extensions + protocol)         │ Track B:
                          └-> Chunk 4+5 (assembly + discovery) ────┤ Chunk 10 (planner)
                          │     └-> Chunk 6  (zeroing)               │   └-> Chunk 11 (scrubber)
                          └-> Chunk 7a (ToolBackend + TCP runtime)   │
                                └-> Chunk 7b (mosfet + hot-swap)     │
                                      └-> Chunk 8  (tool UI + health)│
                                            └-> Chunk 9  (IK drag) ─┘
                                                └-> Chunk 12 (palette + stubs)
```

**Three parallel tracks after Chunk 0+1a+1b:**
- **Track A (critical path):** 3 -> 4+5 -> 6 -> 7a -> 7b -> 8 -> 9 -> 12
- **Track B (independent):** 10 -> 11
- **Track C (independent after 2):** 12-stubs (palette + AprilTag)

**Fastest delivery:** 0 -> 1a -> 1b -> (1b unlocks 3 and 10) ->
3 -> 4+5 -> 6 -> 7a -> 7b -> 8 -> 9 -> 12, with 10->11 in parallel.

---

## Critical corrections incorporated (from feasibility + UX critique)

These 15 corrections were found by two independent review agents and are
**baked into the chunk specs below**. An agent implementing a chunk must
not regress them:

1. **Gear ratio silently no-ops in closed-loop mode.** The closed-loop
   executor (`trajectory_execution.py:1237`) has its own offset conversion
   and was missing from the first draft. **Added to Chunk 1b's edit list.**
2. **Single-servo refactor breaks gripper.** Adding `logical_idx` to
   `set_single_actuator_position` fails because both callers pass
   `servo_id=100` (gripper, not a logical joint). **Dropped
   `logical_idx` param; gear applied inside the backend by actuator_id
   lookup instead.**
3. **Abstract methods break EtherCAT backend.** Adding `@abstractmethod`
   to `ActuatorBackend` prevents `EthercatRTCoreBackend` instantiation.
   **All new ABC methods are non-abstract defaults raising
   `NotImplementedError`. Do NOT modify EthercatRTCoreBackend.**
4. **STS3215 has no torque-enable at register 0x28.** The register map has
   0x29=acceleration there. `set_torque_enabled` is implemented as low-PID
   + zero-accel, NOT a torque-register write. **Verify against STS3215
   datasheet before coding.**
5. **TOML migration breaks 4 test files + conftest.**
   `Gradient0Config` must remain as a thin shim loading from TOML. **Chunk 0.**
6. **Response field is `cartesian_path`, not `pathPoints`.**
   (`command_api.py:2019`). **Fixed in Chunk 11.**
7. **`/ik/solve` and `/control/move-line-absolute` do not exist.** Chunk 9
   must add a lightweight `/ik/solve` endpoint. **Added to Chunk 9.**
8. **TCP offset is a 3-vector in a non-obvious frame** ("world-frame-at-
   zero-pose rotated by target rotation", `ik_solver.py:29-31`), not a
   wrist-frame 6-vector. **Chunk 7a spec uses 3-vector; rotation component
   deferred to v2.**
9. **Hot-swap quiescence barrier misses jog + streaming.** `should_stop`
   alone doesn't stop jog (`jog_thread`) or streaming (`streaming_handle`).
   **Barrier must call `handle_stop_command()` (`command_api.py:818-832`).**
10. **API endpoints must proxy via UDP**, not call `servo_driver` directly
    (API and controller are separate processes). **All calibrate/rename
    endpoints explicitly proxy via UDP commands.**
11. **`set_active_robot`'s 9-servo assumption** (`robot_config.py:236`)
    breaks for generalized TOML robots. **Chunk 0 generalizes this.**
12. **SSE calibration on `/monitor` breaks `handleMessage`.** Calibration
    frames without `joints` key make the UI drop to "no data". **New
    dedicated `/calibrate/stream` SSE endpoint.**
13. **Distributed config filesystem mismatch.** **Plan scoped to
    single-node; config GETs proxy via UDP to controller.**
14. **Discovery bus contention.** `_telemetry_loop` skips reads during
    streaming moves; no "discovery mode" command exists. **New
    `DISCOVERY_START`/`DISCOVERY_STOP` UDP commands with a flag that
    pauses the streaming-move guard.**
15. **PID restore on crash.** If controller crashes mid-discovery, servos
    left compliant. **Recovery file checked on startup.**

---

# CHUNK 0: Config-to-startup wiring + test shim

**Goal:** Make `run_controller.py` boot from TOML files instead of
hardcoded Python class registry, without breaking existing tests.

**Files touched:**
- `src/gradient_os/arm_controller/robots/__init__.py`
- `src/gradient_os/arm_controller/robots/base.py`
- `src/gradient_os/arm_controller/robot_config.py`
- `src/gradient_os/run_controller.py`
- `tests/conftest.py`
- `tests/test_driver.py`
- `tests/test_profiled_segments.py`
- `tests/test_setpoint_streaming.py`

**Changes:**

1. Keep `Gradient0Config` as a thin shim. The class stays at
   `robots/gradient0/config.py` but its `__init__` loads
   `config/arms/gradient0/manifest.toml` + `joints.toml` via
   `config_loader.load_robot("gradient0")` and populates the same
   properties. All existing imports
   (`from ...gradient0.config import Gradient0Config`) continue to work.

2. Generalize `set_active_robot` (`robot_config.py:236`): remove the
   `if len(_actuator_ids) >= 9` hardcoded 9-servo assumption. Read joint
   count from the loaded config. Per-joint PID gains loop iterates over
   `actuator_ids` length, not a hardcoded 9.

3. Make `run_controller.py` L135 boot from TOML: `get_robot_config(name)`
   scans `config/arms/` instead of the hardcoded `_ROBOT_REGISTRY` dict
   in `robots/__init__.py:30-32`. Keep `register_robot()` escape hatch
   for tests/sim.

4. Fix the 4 test files that import `Gradient0Config` directly — they
   get the shim, which constructs the same object shape.

**Tests:**
- Existing `pytest tests/` passes unchanged after migration (this is the
  acceptance gate — 0 skipped).

---

# CHUNK 1a: TOML schema + config loader + GET API + CSV

**Goal:** Declarative TOML config files per arm and per tool, with
Pydantic-validated loader, GET-only API endpoints, and CSV export.

**Files touched:**
- new `src/gradient_os/arm_controller/config_schema.py`
- new `src/gradient_os/arm_controller/config_loader.py`
- `src/gradient_os/api/main.py`
- new `config/arms/gradient0/manifest.toml`
- new `config/arms/gradient0/joints.toml`
- new `config/tools/gripper_default/manifest.toml`

## TOML schemas

### `config/arms/{id}/manifest.toml`

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `id` | string | yes | — | `^[a-z0-9_-]{1,32}$`, equals dir name |
| `name` | string | yes | — | non-empty |
| `version` | string | yes | — | semver |
| `description` | string | no | `""` | — |
| `backend` | string | yes | — | `sts3215`|`hls3950`|`simulation`|`ethercat_rtcore` |
| `ik_backend` | string | no | `ikfast` | `ikfast`|`numeric` |
| `dh_path` | string | yes | — | relative path, CSV exists |
| `urdf_path` | string | yes | — | relative path, .urdf exists |
| `thumbnail` | string | no | `""` | relative path |
| `mounted_tool` | string | no | `null` | references existing tool |
| `default_speed` | int | no | `500` | 0..4095 |
| `default_acceleration_deg_s2` | float | no | `500.0` | > 0 |
| `serial_port` | string | no | `/dev/ttyUSB0` | — |
| `udp_listen_ip` | string | no | `0.0.0.0` | valid IPv4 |
| `udp_port` | int | no | `3000` | 1..65535 |

### `config/arms/{id}/joints.toml`

Uses `[[joint]]` array-of-tables. Order defines logical joint index (0-based).

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `name` | string | yes | — | non-empty, unique |
| `servo_ids` | array int | yes | — | length 1..4, each 1..253, unique across joints |
| `gear_ratio` | float | no | `1.0` | **> 0** (reject 0 and negative) |
| `limits_rad` | array 2 float | yes | — | min < max |
| `mapping_range_rad` | array 2 float | no | `[-pi, pi]` | min < max |
| `inverted` | bool | no | `false` | — |
| `master_offset_rad` | float | no | `0.0` | finite |
| `default_pid` | array 3 int | no | backend default | each 0..254 |
| `gravity_loaded` | bool | no | `false` | selects compliance PID |

Optional `[[gripper]]` table (at most one):

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `servo_id` | int | yes | — | 1..253, not in any joint.servo_ids |
| `limits_rad` | array 2 float | yes | — | min < max |
| `mapping_range_rad` | array 2 float | no | `[-pi, pi]` | — |
| `inverted` | bool | no | `false` | — |
| `default_pid` | array 3 int | no | backend default | — |

**Note on `mapping_range_rad` vs `limits_rad` vs `gear_ratio`:**
`mapping_range_rad` is the **physical** (motor-shaft) range. `limits_rad`
is the **logical** (joint) range. The loader validates that
`limits_rad * gear_ratio` fits within `mapping_range_rad`. This is
critical — an agent that stores logical ranges as physical will cause the
servo to clamp at half travel on a gear-reduced joint.

### `config/tools/{id}/manifest.toml`

| Field | Type | Required | Default | Validation |
|---|---|---|---|---|
| `id` | string | yes | — | `^[a-z0-9_-]{1,32}$`, equals dir |
| `name` | string | yes | — | non-empty |
| `version` | string | yes | — | semver |
| `type` | string | yes | — | `gripper`|`drill`|`2servo_claw`|`vacuum`|`custom` |
| `thumbnail` | string | no | `""` | relative path |
| `tcp_offset` | array 3 float | yes | — | `[dx, dy, dz]` in metres |
| `controller_kind` | string | yes | — | `actuator`|`tool_backend` |

If `controller_kind = "actuator"`:

| Field | Type | Required | Validation |
|---|---|---|---|
| `servo_ids` | array int | yes | each 1..253, not in arm joints |
| `limits_rad` | array of [min,max] per servo | yes | — |
| `mapping_range_rad` | array of [min,max] per servo | no | — |
| `inverted` | array bool per servo | no | — |
| `default_pid` | array 3 int | no | — |

If `controller_kind = "tool_backend"`:

| Field | Type | Required | Validation |
|---|---|---|---|
| `backend_kind` | string | yes | `mosfet`|`i2c_relay`|`gpio` |
| `channels` | array of channel tables | yes | 1..8 |

Channel table:

| Field | Type | Required | Validation |
|---|---|---|---|
| `id` | int | yes | 0..15 |
| `name` | string | yes | e.g. `drill_motor` |
| `kind` | string | yes | `onoff`|`pwm`|`continuous` |

**Note:** `tcp_offset` is a **3-vector** `[dx, dy, dz]`, NOT a 6-DOF
pose. This matches the existing `END_EFFECTOR_OFFSET` semantics in
`ik_solver.py:33` (world-frame-at-zero-pose, rotated by target rotation
at call sites `:114, :145, :331`). Rotation component of TCP is
**deferred to v2**.

### Validation rules (in config_loader.py)

1. All `servo_ids` across all `[[joint]]` tables plus `[[gripper]]`
   must be unique.
2. `gear_ratio` strictly positive (> 0).
3. `limits_rad * gear_ratio` must fit within `mapping_range_rad`.
4. `dh_path` CSV row count must equal number of `[[joint]]` entries.
5. `mounted_tool` (if set) must resolve to an existing tool whose
   `servo_ids` do not collide with arm joint servo_ids.
6. `id` equals directory name.

### Filled example: gradient0

`config/arms/gradient0/manifest.toml`:
```toml
id = "gradient0"
name = "Gradient0"
version = "1.0.0"
description = "6-DOF arm with twin-motor shoulder and elbow"
backend = "sts3215"
ik_backend = "ikfast"
dh_path = "mini-6dof-arm/dh_params.csv"
urdf_path = "mini-6dof-arm/mini-6dof-arm.urdf"
thumbnail = "config/arms/gradient0/thumbnail.png"
mounted_tool = "gripper_default"
default_speed = 500
default_acceleration_deg_s2 = 500.0
serial_port = "/dev/ttyUSB0"
udp_listen_ip = "0.0.0.0"
udp_port = 3000
```

`config/arms/gradient0/joints.toml` (matches `gradient0/config.py` exactly):
```toml
[[joint]]
name = "base"
servo_ids = [10]
gear_ratio = 1.0
limits_rad = [-3.141592653589793, 3.141592653589793]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [50,1,20]
gravity_loaded = false

[[joint]]
name = "shoulder"
servo_ids = [20,21]
gear_ratio = 1.0
limits_rad = [-1.5707963267948966,1.5707963267948966]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [65,1,30]
gravity_loaded = true

[[joint]]
name = "elbow"
servo_ids = [30,31]
gear_ratio = 1.0
limits_rad = [-1.5707963267948966,1.5707963267948966]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [50,1,25]
gravity_loaded = true

[[joint]]
name = "wrist_roll"
servo_ids = [40]
gear_ratio = 1.0
limits_rad = [-3.141592653589793,3.141592653589793]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [50,0,10]
gravity_loaded = false

[[joint]]
name = "wrist_pitch"
servo_ids = [50]
gear_ratio = 1.0
limits_rad = [-1.8326,2.0944]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [50,0,10]
gravity_loaded = false

[[joint]]
name = "wrist_yaw"
servo_ids = [60]
gear_ratio = 1.0
limits_rad = [-3.141592653589793,3.141592653589793]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
master_offset_rad = 0.0
default_pid = [50,0,10]
gravity_loaded = false

[[gripper]]
servo_id = 100
limits_rad = [0.0,3.141592653589793]
mapping_range_rad = [-3.141592653589793,3.141592653589793]
inverted = true
default_pid = [40,0,10]
```

`config/tools/gripper_default/manifest.toml`:
```toml
id = "gripper_default"
name = "Default Gripper"
version = "1.0.0"
type = "gripper"
thumbnail = "config/tools/gripper_default/thumbnail.png"
tcp_offset = [0.180,0.0,0.0]
controller_kind = "actuator"
servo_ids = [100]
limits_rad = [[0.0,3.141592653589793]]
mapping_range_rad = [[-3.141592653589793,3.141592653589793]]
inverted = [true]
default_pid = [40,0,10]
```

## API endpoints (GET only in this chunk)

All config GETs **proxy via UDP** to the controller (which reads its local
disk). In single-node deployment they share filesystem, but proxying via
UDP is the safe pattern for future distributed support.

```python
class RobotSummary(BaseModel):
    id: str
    name: str
    version: str
    backend: str
    ik_backend: str
    mounted_tool: Optional[str]
    thumbnail: Optional[str]

class RobotListResponse(BaseModel):
    robots: list[RobotSummary]

class JointConfig(BaseModel):
    name: str
    servo_ids: list[int]
    gear_ratio: float
    limits_rad: tuple[float,float]
    mapping_range_rad: tuple[float,float]
    inverted: bool
    master_offset_rad: float
    default_pid: tuple[int,int,int]
    gravity_loaded: bool = False

class RobotDetailResponse(BaseModel):
    id: str
    name: str
    version: str
    backend: str
    ik_backend: str
    mounted_tool: Optional[str]
    thumbnail: Optional[str]
    joints: list[JointConfig]
    gripper: Optional[GripperConfig]
    dh_path: str
    urdf_path: str
    default_speed: int
    default_acceleration_deg_s2: float
    serial_port: str
    udp_listen_ip: str
    udp_port: int

class ToolSummary(BaseModel):
    id: str
    name: str
    version: str
    type: str
    thumbnail: Optional[str]

class ToolListResponse(BaseModel):
    tools: list[ToolSummary]

class ActiveConfigResponse(BaseModel):
    active_robot_id: str
    active_tool_id: Optional[str]
    backend: str
    ik_backend: str
```

| Endpoint | Method | Response | Errors |
|---|---|---|---|
| `/config/robots` | GET | `RobotListResponse` | 500 if dir unreadable |
| `/config/robots/{id}` | GET | `RobotDetailResponse` | 404, 422 |
| `/config/tools` | GET | `ToolListResponse` | 500 |
| `/config/tools/{id}` | GET | `ToolDetailResponse` | 404, 422 |
| `/config/active` | GET | `ActiveConfigResponse` | 503 |

**Static-file routes for URDF/mesh serving** (runtime-added robots need
a serving path — Vite bakes meshes at build time):
- `GET /config/robots/{id}/urdf` → serves the URDF file
- `GET /config/robots/{id}/mesh/{filename}` → serves STL meshes
- `GET /config/tools/{id}/mesh/{filename}` → serves tool meshes

## robot_info.csv format

One row per physical actuator. Generated on save + startup.

| Column | Units | Example |
|---|---|---|
| `robot_id` | — | `gradient0` |
| `robot_name` | — | `Gradient0` |
| `robot_version` | — | `1.0.0` |
| `backend` | — | `sts3215` |
| `logical_joint_index` | 0-based | `1` |
| `logical_joint_name` | — | `shoulder` |
| `actuator_config_index` | 0-based | `1` |
| `actuator_id` | — | `20` |
| `twin_secondary` | bool | `false` (for ID 21: `true`) |
| `gear_ratio` | motor_rad/joint_rad | `1.0` |
| `inverted` | bool | `true` |
| `master_offset_rad` | radians | `0.0` |
| `limit_min_rad` | radians | `-1.5708` |
| `limit_max_rad` | radians | `1.5708` |
| `mapping_min_rad` | radians | `-3.1416` |
| `mapping_max_rad` | radians | `3.1416` |
| `pid_kp` | — | `65` |
| `pid_ki` | — | `1` |
| `pid_kd` | — | `30` |
| `encoder_resolution` | counts | `4095` |
| `is_gripper` | bool | `false` |

## Tests

`tests/arm_controller/test_config_loader.py`:
1. `test_load_gradient0_manifest` — load manifest, assert every field
   matches `Gradient0Config()` (the shim).
2. `test_load_gradient0_joints_matches_class` — `actuator_ids`,
   `logical_to_physical_map`, `inverted_actuator_ids`, offsets, PID,
   gripper all match.
3. `test_gear_ratio_default_is_one` — no gear_ratio field -> all 1.0.
4. `test_validation_rejects_duplicate_servo_ids`.
5. `test_validation_rejects_missing_dh_path`.
6. `test_validation_rejects_limits_outside_mapping_range` (after gear
   scaling).
7. `test_validation_rejects_bad_id_format`.
8. `test_round_trip_write_read` — modify gear_ratio to 2.0, write,
   reload, assert persisted.
9. `test_migration_equivalence_full_dict` — `get_config_dict()` from
   TOML vs from class, equal except new `gear_ratios` key.

---

# CHUNK 1b: Gear ratio across ALL 9 code paths

**Goal:** Insert gear-ratio multiply/divide at the logical-physical
boundary in every angle-conversion path. Gradient0 stays 1.0 (no behavior
change). The new HLS3950 arm's J1 uses 2.0.

**Apply order (invariant across all paths):**
```
WRITE:  physical_angle = (logical_angle + master_offset) * gear_ratio
        raw = normalize_to_encoder(physical_angle, mapping_range, inverted)
READ:   physical_angle = denormalize_from_encoder(raw, mapping_range, inverted)
        logical_angle = physical_angle / gear_ratio - master_offset
```

**Files touched (exhaustive — 9 edit sites + 4 plumbing sites):**

### A. `robots/base.py`
Add after `logical_joint_master_offsets_rad` (~L300):
```python
@property
def gear_ratios(self) -> list[float]:
    return [1.0] * self.num_logical_joints
```
Add `'gear_ratios': self.gear_ratios` to `get_config_dict()` (~L533).

### B. `robot_config.py`
Add `GEAR_RATIOS: list[float] = None` near L67.
In `set_active_robot` after L204:
```python
global GEAR_RATIOS
GEAR_RATIOS = robot.gear_ratios
```
Add `global GEAR_RATIOS` to the global declaration block L162-172.

### C. `utils.py`
In `_populate_robot_constants` (~L285) after L317:
```python
global GEAR_RATIOS
GEAR_RATIOS = robot_config.GEAR_RATIOS
```
Add `GEAR_RATIOS = None` to module globals, add to global decl block.

### D. `backends/sts3215/driver.py`
In `__init__` after L96:
```python
self._gear_ratios: list[float] = robot_config.get(
    'gear_ratios', [1.0] * len(self._logical_to_physical_map))
```

**1.** `prepare_sync_write_commands` (L376):
```python
# BEFORE
angle_with_offset = positions_rad[logical_idx] + self._master_offsets_rad[logical_idx]
# AFTER
angle_with_offset = (positions_rad[logical_idx] + self._master_offsets_rad[logical_idx]) * self._gear_ratios[logical_idx]
```

**2.** `plan_profiled_segment` (L476): same change.

**3.** `raw_to_joint_positions` (L605):
```python
# BEFORE
positions[logical_idx] = avg_angle - self._master_offsets_rad[logical_idx]
# AFTER
g = self._gear_ratios[logical_idx]
positions[logical_idx] = (avg_angle / g) - self._master_offsets_rad[logical_idx] if abs(g) > 1e-9 else avg_angle - self._master_offsets_rad[logical_idx]
```
**Note:** apply to the **averaged** value for twins, not per-servo.

**4.** `set_single_actuator_position` (L613): do NOT add `logical_idx`
param. Instead, look up `actuator_id`'s owning logical joint inside the
backend and apply gear there:
```python
# inside set_single_actuator_position, before _angle_to_raw:
if actuator_id != self._gripper_servo_id:
    for li, phys_indices in self._logical_to_physical_map.items():
        if config_idx in phys_indices:
            position_rad = position_rad * self._gear_ratios[li]
            break
# gripper: no gear (gripper not in logical_to_physical_map)
raw_pos = self._angle_to_raw(position_rad, config_idx)
```

**5.** Add `read_single_actuator_angle_rad`:
```python
def read_single_actuator_angle_rad(self, actuator_id: int) -> Optional[float]:
    raw = self.read_single_actuator_position(actuator_id)
    if raw is None: return None
    config_idx = self._servo_ids.index(actuator_id)
    physical = self._raw_to_angle(raw, config_idx)
    for li, phys_indices in self._logical_to_physical_map.items():
        if config_idx in phys_indices:
            g = self._gear_ratios[li]
            return (physical / g) - self._master_offsets_rad[li] if abs(g)>1e-9 else physical - self._master_offsets_rad[li]
    return physical  # gripper or unmapped
```

### E. `backends/hls3950/driver.py`
Apply **exactly the same changes** as section D (identical file structure).

### F. `backends/simulation/backend.py`
Mirror `_gear_ratios` field and apply in `prepare_sync_write_commands`
and `raw_to_joint_positions`.

### G. `backends/ethercat_rtcore/backend.py`
**Do NOT modify.** Inherits non-abstract defaults from the ABC
(Chunk 3). Gear ratio on EtherCAT is a future task.

### H. `servo_driver.py` (legacy path)

**6.** `set_servo_positions` (L649-651, legacy fallback):
```python
g = utils.GEAR_RATIOS[logical_joint_index] if utils.GEAR_RATIOS else 1.0
target_physical_angle_rad = (logical_joint_angles_rad[logical_joint_index] + utils.LOGICAL_JOINT_MASTER_OFFSETS_RAD[logical_joint_index]) * g
```

**7.** `get_current_arm_state_rad` (L1004, legacy fallback):
```python
g = utils.GEAR_RATIOS[logical_joint_index] if utils.GEAR_RATIOS else 1.0
logical_angle = (logical_angle / g) - utils.LOGICAL_JOINT_MASTER_OFFSETS_RAD[logical_joint_index] if abs(g)>1e-9 else logical_angle - utils.LOGICAL_JOINT_MASTER_OFFSETS_RAD[logical_joint_index]
```

**8.** `logical_q_to_syncwrite_tuple` (L1261):
```python
g = utils.GEAR_RATIOS[logical_idx] if utils.GEAR_RATIOS else 1.0
angle_with_offset = (logical_joint_angles_rad[logical_idx] + utils.LOGICAL_JOINT_MASTER_OFFSETS_RAD[logical_idx]) * g
```

**9.** `trajectory_execution.py:_closed_loop_executor_thread` (L1237):
```python
# BEFORE
angle_with_master_offset = target_angle_rad + LOGICAL_JOINT_MASTER_OFFSETS_RAD[...]
# AFTER
g = utils.GEAR_RATIOS[logical_idx] if utils.GEAR_RATIOS else 1.0
angle_with_master_offset = (target_angle_rad + LOGICAL_JOINT_MASTER_OFFSETS_RAD[...]) * g
```
**THIS WAS MISSING from the original plan. Closed-loop is the default for
MOVE_LINE. Without this, gear ratio silently no-ops in closed-loop mode.**

### I. `servo_driver.py` (single-servo refactor)
Refactor `set_single_servo_position_rads` (L491-514) to delegate to
`backend.set_single_actuator_position(actuator_id=servo_id, position_rad,
speed, accel)` — **NO `logical_idx` param** (see correction #2). Gear
applied inside backend by actuator_id lookup (section D.4).

### J. `plan_profiled_segment` speed-cap sizing (`sts3215/driver.py:457-470`)
`deltas = abs(end_q[j] - start_q[j])` is in logical space. With gear=2
on J1, J1's physical travel is 2x. Scale the speed cap by gear so the
geared joint's physical speed matches:
```python
physical_delta = deltas[j] * self._gear_ratios[logical_idx]
# use physical_delta in the max-across-joints calc
```

### K. `servo_driver.py` (limits helper)
Add `_logical_to_physical_for_actuator(config_index, angle_rad)`:
```python
def _logical_to_physical_for_actuator(config_index, angle_rad):
    if not utils.GEAR_RATIOS: return angle_rad
    for li, phys_indices in robot_config.LOGICAL_TO_PHYSICAL_MAP.items():
        if config_index in phys_indices:
            return angle_rad * utils.GEAR_RATIOS[li]
    return angle_rad
```
Use in `set_servo_angle_limits_from_urdf` (L895) and `reinitialize_servo`
(L1188): `angle_to_raw(_logical_to_physical_for_actuator(config_index, limit),
config_index)`.

**Gripper:** no gear. Gripper is not in `logical_to_physical_map`;
`_gripper_angle_to_raw` has no gear path. **Explicitly documented as
unsupported — a geared gripper tool would need a future extension.**

## Tests

`tests/arm_controller/test_gear_ratio_roundtrip.py` (using SimulationBackend):
1. `test_write_applies_gear_ratio` — ratio 2.0, command 0.5rad, assert
   raw = angle_to_raw(0.5*2.0, 0).
2. `test_read_divides_gear_ratio` — set raw for 1.0rad physical, read,
   assert 0.5rad.
3. `test_offset_then_gear_order` — offset 0.1, gear 2.0, command 0.3rad,
   assert raw for (0.3+0.1)*2.0=0.8rad.
4. `test_round_trip_identity_with_unit_gear`.
5. `test_single_servo_path_uses_backend_conversion` — gear 3.0, assert
   raw for 0.5*3.0=1.5rad.
6. `test_limits_scaled_by_gear` — gear 2.0, limits pi/4, assert raw
   for pi/2.
7. **`test_closed_loop_applies_gear_ratio`** — command via closed-loop
   path, assert raw applies gear. (THIS TEST WAS MISSING.)
8. `test_twin_motor_averaging_with_gear` — twin pair, gear 2.0, read
   asserts averaged physical / gear - offset.
9. `test_inverted_with_gear` — inverted=True + gear=2.0, no double
   inversion.
10. `test_gear_zero_rejected` — Pydantic rejects gear_ratio=0.

---

# CHUNK 2: Robot Studio UI shell + store + App.tsx extraction

**Goal:** Card-grid robot/tool selection, template picker,
dynamic URDF in the visualizer, lightweight store. New components in
sibling files — App.tsx gains only mount points.

**Files touched:**
- `web-ui/src/App.tsx` (minimal wiring)
- new `web-ui/src/state/store.ts`
- new `web-ui/src/state/types.ts`
- new `web-ui/src/components/robotstudio/RobotStudioPanel.tsx`
- new `web-ui/src/components/robotstudio/RobotCard.tsx`
- new `web-ui/src/components/robotstudio/ToolLoadoutCards.tsx`
- `web-ui/src/ArmVisualizer.tsx`

## App.tsx changes (exhaustive — 5 touch sites)

1. `SidebarPanelId` union (L103): add `"robotstudio" | "discovery" |
   "calibration"`.
2. Persisted-settings validator (L279-286): add the new strings to the
   exhaustive check so they persist correctly.
3. `panelByKey` (L3500): add key for new panels.
4. `handleSelectSidebarPanel` (L3521): handle new panel ids.
5. `activeDrawerContent`/`activeDrawerHeader`/`activeDrawerHeightMode`
   switch (L3574-3812): add cases for new panels.
6. `onKeyDown` (L3488): add Cmd+K handler **before** the
   `editable || alt || ctrl || meta` guard at L3496:
   ```ts
   if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase()==="k") {
     setIsPaletteOpen(v => !v); event.preventDefault(); return;
   }
   ```
7. Import + mount: `<RobotStudioPanel>` when `activePanel === "robotstudio"`.

## Store (useSyncExternalStore, ~60 lines)

`web-ui/src/state/store.ts`:
```ts
import { useSyncExternalStore } from "react";
export type AppState = {
  mountedArmId: string | null;
  mountedToolId: string | null;
  armManifest: RobotManifest | null;
  toolManifest: ToolManifest | null;
  connectionState: "disconnected"|"connected"|"error";
};
// ... standard getState/setState/subscribe/useAppState
```

**Scope boundary: store holds ONLY `{mountedArmId, mountedToolId,
armManifest, toolManifest, connectionState}`. All other state stays in
App.tsx `useState`. Store module has NO Three.js imports (jsdom-safe).**

App.tsx mirrors shared state via one effect:
```ts
useEffect(() => setState({
  mountedArmId, mountedToolId, armManifest, toolManifest, connectionState
}), [mountedArmId, mountedToolId, armManifest, toolManifest, connectionState]);
```

## ArmVisualizer.tsx

- Dynamic URDF path: `urdfPath` prop driven by `armManifest.urdf_path`
  (not hardcoded L589-591).
- Generalize `joint${index+1}` loop (L955-1033) to handle N joints
  (already index-driven — verify no hardcoded 6).
- Mesh loading: URDF + STLs fetched from API
  (`GET /config/robots/{id}/urdf`, `GET /config/robots/{id}/mesh/{filename}`).
  Add a custom loader hook for cross-origin mesh resolution.

## Components

| File | Props | jsdom-testable |
|---|---|---|
| `RobotStudioPanel.tsx` | `{templates, activeRobotId, onMount, onEdit, onDiscover}` | Yes |
| `RobotCard.tsx` | `{template, onMount, onEdit}` | Yes |
| `ToolLoadoutCards.tsx` | `{tools, activeToolId, onEquip}` | Yes |

Template picker: "6-DOF arm", "4-DOF", "SCARA", "Custom" + optional
"Import CAD" action (URDF upload) inside edit view.

## Tests
- `RobotStudioPanel.test.tsx`, `RobotCard.test.tsx`,
  `ToolLoadoutCards.test.tsx` (jsdom, `installFetchMock`).

---

# CHUNK 3: ActuatorBackend ABC extensions (non-abstract) + protocol primitives

**Goal:** Add compliance mode, torque enable, servo ID rename, and
angle-read methods to the ABC and implement in STS3215/HLS3950/Simulation.

**Critical:** All new methods are **non-abstract defaults** (raise
`NotImplementedError`) on the ABC. Do NOT modify `EthercatRTCoreBackend`.

**Files touched:**
- `src/gradient_os/arm_controller/actuator_interface.py`
- `src/gradient_os/arm_controller/backends/sts3215/driver.py`
- `src/gradient_os/arm_controller/backends/sts3215/protocol.py`
- `src/gradient_os/arm_controller/backends/sts3215/config.py`
- `src/gradient_os/arm_controller/backends/hls3950/driver.py`
- `src/gradient_os/arm_controller/backends/hls3950/protocol.py`
- `src/gradient_os/arm_controller/backends/hls3950/config.py`
- `src/gradient_os/arm_controller/backends/simulation/backend.py`

## ABC additions (in actuator_interface.py after L518)

```python
def set_compliance_mode(self, enabled: bool, actuator_id: Optional[int]=None,
    gravity_loaded: bool=False) -> bool:
    raise NotImplementedError(f"{type(self).__name__} does not implement set_compliance_mode")

def set_torque_enabled(self, actuator_id: int, enabled: bool) -> bool:
    raise NotImplementedError(f"{type(self).__name__} does not implement set_torque_enabled")

def set_actuator_id(self, current_id: int, new_id: int) -> bool:
    raise NotImplementedError(f"{type(self).__name__} does not implement set_actuator_id")

def read_single_actuator_angle_rad(self, actuator_id: int) -> Optional[float]:
    raise NotImplementedError(f"{type(self).__name__} does not implement read_single_actuator_angle_rad")
```

## Compliance PID

| Joint class | Kp | Ki | Kd |
|---|---|---|---|
| gravity_loaded=True | 20 | 0 | 5 |
| gravity_loaded=False | 5 | 0 | 2 |

RAM-only (not EEPROM — avoid wear). Save/restore in in-memory dict
`compliance_saved_pid: dict[int, tuple[int,int,int]]`. On controller
restart, `initialize` re-applies default PID from config.

## set_torque_enabled — CRITICAL DATASHEET NOTE

**STS3215 does NOT have a torque-enable register at 0x28.** The register
map (`sts3215/config.py`) has 0x29=acceleration there. Implement
`set_torque_enabled` as: low-PID (compliance gains) + zero-accel +
zero-speed. **Verify against the STS3215 datasheet before coding.**
Add `SERVO_ADDR_TORQUE_ENABLE` constant to config modules only AFTER
verification.

HLS3950: torque register at 0x28 with different semantics (does NOT
accept 128 for calibration; use 1/0 only, per `hls3950/config.py:13`).

## set_actuator_id

Protocol primitive: write reg 0x05 with EEPROM unlock (0x37->0, write
0x05, 0x37->1). **Servo reboots after rename** — update
`_present_servo_ids` and re-ping.

## Implementations

| File | Methods |
|---|---|
| `sts3215/driver.py` | all 4 (compliance via PID, torque via low-PID+zero-accel, ID via protocol, angle read) |
| `hls3950/driver.py` | all 4 (same, torque reg 0x28 with 1/0 semantics) |
| `simulation/backend.py` | all 4 (no-op compliance, no-op torque, update dict for ID, angle read with gear) |
| `ethercat_rtcore/backend.py` | **NO CHANGES** (inherits defaults) |

## Tests
- `test_compliance_mode.py`, `test_torque_enabled.py`,
  `test_set_actuator_id.py` (using SimulationBackend).

---

# CHUNK 4+5 (MERGED): Assembly & joint discovery ritual

**Goal:** Pre-assembly servo rename wizard + post-assembly joint
discovery ritual. Merged because both share the rename UDP machinery,
the polling endpoint, and the 30Hz streaming path.

**Files touched:**
- `src/gradient_os/run_controller.py`
- `src/gradient_os/arm_controller/command_api.py`
- `src/gradient_os/api/main.py`
- new `web-ui/src/components/robotstudio/PreAssemblyWizard.tsx`
- new `web-ui/src/components/discovery/DiscoveryRitual.tsx`
- new `web-ui/src/components/discovery/ServoRadar.tsx`
- new `web-ui/src/components/discovery/discoveryUtils.ts`

## New controller UDP commands

| Command | Purpose |
|---|---|
| `DISCOVERY_START` | Enter discovery mode: write low PID to all, pause streaming-move guard in `_telemetry_loop` |
| `DISCOVERY_STOP` | Restore PID, exit discovery mode |
| `RENAME_SERVO,old,new` | Rename servo ID via `set_actuator_id` |
| `CALIBRATE_EXIT` | Explicit exit from calibration mode (existing `CALIBRATE` exits on any-other-command; add explicit token) |

## Recovery file

`config/arms/{id}/.discovery_in_progress` — checked on controller
startup. If present, restore default PID from manifest before
proceeding (handles controller crash mid-discovery leaving servos
compliant).

## Discovery mode streaming

**New dedicated SSE endpoint `/calibrate/stream`** (NOT `/monitor` —
avoids breaking `handleMessage` which expects `joints` in every frame).

30Hz all-servo raw positions via **SyncRead** (NOT individual reads —
9x10ms=90ms is too slow for 30Hz). Frame format:
```json
{"type":"calibration","servos":[{"id":101,"raw_position":2048},...]}
```

**Bus contention:** discovery mode flag in `_telemetry_loop` pauses the
streaming-move skip guard (L301-308). No concurrent
SyncRead+SyncWrite during discovery.

## Pre-assembly rename wizard

`PreAssemblyWizard.tsx`: plug-in-one-at-a-time, detect at ID=1
(**reconfigure polling to scan ID=1, NOT `utils.SERVO_IDS`**), rename to
101+i via `RENAME_SERVO`. Handles already-renamed, collisions,
factory-reset. Progress bar, stepper, servo cards.

## Motion-detection algorithm

- **Threshold:** 8 LSB (4x jitter floor), 0.02 rad of motor shaft.
- **MOVING:** 3 consecutive samples above threshold (100ms latency).
- **SETTLED:** 5 consecutive below threshold (167ms).
- **Twin detection:** Pearson r>0.95 AND amplitude ratio
  max(sA/sB, sB/sA)<1.1. **Inverted twins: r~-0.95 -> use abs(r) and
  check for anti-correlation.**
- **Coupled:** r<0.5 or inconsistent ratio -> UI asks
  twin/coupled/separate.
- **Sweep limits:** running min/max, stable 10 samples (333ms), range
  >0.1 rad.
- **Window:** 1-second rolling buffer (30 samples).

## Discovery ritual UX

1. UI dims, spotlights 3D model, says "J1 of 6 — move joint 1 by hand."
2. User wiggles joint -> detected servo card pulses cyan, joint glows.
3. Sweep to limits -> bars fill green, click at hard stops.
4. Twin: correlation detected -> "2 servos moving together — same joint?"
   confirm/split. Brace bracket ︷ between cards.
5. Gear ratio entry (default 1.0).
6. Lock: snap animation, glow blue->green, checkmark, step counter.
7. On completion: writes `joints.toml` + `robot_info.csv` via
   `POST /config/robots`.

**Twin serialization:** `servo_ids = [A, B]` with single `gear_ratio` in
joints.toml.

## API endpoints (all UDP-to-controller)

| Endpoint | Method | UDP command |
|---|---|---|
| `/servo/{id}/rename` | POST | `RENAME_SERVO,old,new` |
| `/servo/{id}/factory-reset` | POST | `FACTORY_RESET,ID` (existing) |
| `/calibrate/enter/{servo_id}` | POST | `CALIBRATE,ID` (existing) + compliance |
| `/calibrate/exit/{servo_id}` | POST | `CALIBRATE_EXIT` (new) |
| `/calibrate/stream` | GET (SSE) | new dedicated stream |

## Tests
- `discoveryUtils.test.ts` (pure: correlation, motion detect, group
  proposal — jsdom).
- `PreAssemblyWizard.test.tsx` (mock fetch, mock SSE).

---

# CHUNK 6: Zeroing over web API

**Goal:** Expose existing zeroing over HTTP. Reuses existing UDP commands
— does NOT build duplicate paths.

**Files touched:**
- `src/gradient_os/api/main.py`
- `src/gradient_os/run_controller.py` (minimal — new `SET_ZERO_SERVO,ID`)

## API endpoints (all UDP-to-controller)

| Endpoint | Method | UDP command | Notes |
|---|---|---|---|
| `/calibrate/set-zero/{joint}` | POST | `SET_ZERO,N` (existing, L445) | 1-based, zeroes all servos for joint |
| `/calibrate/set-zero-servo/{servo_id}` | POST | `SET_ZERO_SERVO,ID` (new) | single servo, for tools |

**SSE:** calibration data on `/calibrate/stream` (from Chunk 4+5), NOT
`/monitor`. `handleMessage` (App.tsx:2454) is unchanged.

## Zeroing UI

Per-joint: live raw-position readout + "Set current as zero" button.
Wraps existing `servo_driver.set_current_position_as_hardware_zero`
(L1049) via the existing `SET_ZERO` UDP path.

## Tests
- `test_api_calibrate_endpoints.py` (httpx TestClient, mock UDP).

---

# CHUNK 7a: ToolBackend ABC + TCP runtime offset

**Goal:** Separate interface for non-servo tool actuators + replace
hardcoded END_EFFECTOR_OFFSET with runtime 3-vector TCP.

**Files touched:**
- new `src/gradient_os/arm_controller/tool_interface.py`
- `src/gradient_os/ik_solver.py`
- `src/gradient_os/arm_controller/command_api.py`
- `src/gradient_os/arm_controller/trajectory_execution.py`

## ToolBackend ABC

`tool_interface.py`:
```python
class ToolBackend(ABC):
    @property
    @abstractmethod
    def num_channels(self) -> int: ...
    @abstractmethod
    def initialize(self) -> bool: ...
    @abstractmethod
    def shutdown(self) -> None: ...
    @abstractmethod
    def set_channel(self, channel_id: int,
        kind: Literal["onoff","pwm","continuous"], value: float) -> bool: ...
    @abstractmethod
    def get_channel_state(self, channel_id: int) -> Optional[float]: ...
    @abstractmethod
    def emergency_off(self) -> None: ...
```

Controller holds `actuator_backend` + `tool_backend: Optional[ToolBackend]`.
Tool servos (controller_kind=actuator) go through ActuatorBackend.
Tool non-servo actuators (controller_kind=tool_backend) go through
ToolBackend.

## TCP offset refactor

**CRITICAL FRAME SEMANTICS:** `END_EFFECTOR_OFFSET` (`ik_solver.py:33`) is a
3-vector `[0.180, 0.0, 0.0]` in "world-frame-at-zero-pose rotated by target
rotation" (per comment `:29-31`). NOT a wrist-frame 6-DOF pose.

`set_active_tcp(offset_3vec: np.ndarray)` stores a 3-vector. The 3 call
sites (`:114, :145, :331`) apply `target_rotation.dot(tcp_offset)` ->
replace the constant with the runtime value.

**No rotation component in v1** — tools define a 3-vector TCP, not a
6-DOF pose. Document this limitation. Rotation component deferred to v2.

When no tool is mounted, `tcp_offset` defaults to the current
`[0.180, 0.0, 0.0]` (preserves existing behavior).

**Stateful solver:** today `ik_solver.py` is stateless (reads constant at
every call). Making TCP runtime means the solver reads a module-level
variable set by `set_active_tcp()`. This affects:
- `command_api.handle_move_line` (L974)
- `command_api.handle_move_profiled` (L310)
- jog loop (L1222+)
- `trajectory_execution._plan_linear_move` (L486)
All inherit the runtime TCP automatically (they all call `solve_ik` which
reads the module variable).

## Tests
- `test_tcp_offset.py` (FK with default offset matches existing
  behavior; FK with zero offset; FK with custom offset).

---

# CHUNK 7b: MosfetToolBackend + hot-swap state machine + gripper de-special-casing

**Goal:** Implement tool backends, hot-swap with quiescence barrier,
remove gripper "joint 7" special-casing.

**Files touched:**
- new `src/gradient_os/arm_controller/backends/tools/mosfet_backend.py`
- new `src/gradient_os/arm_controller/backends/tools/i2c_relay_backend.py`
- new `src/gradient_os/arm_controller/backends/tools/gpio_backend.py`
- `src/gradient_os/run_controller.py`
- `src/gradient_os/arm_controller/command_api.py`
- `src/gradient_os/arm_controller/robots/base.py`
- `src/gradient_os/arm_controller/utils.py`
- `src/gradient_os/arm_controller/servo_driver.py`
- `src/gradient_os/api/main.py`

## Tool backend implementations

- `MosfetToolBackend` (gpiod/RPi.GPIO). **GPIO permissions:**
  verify `/dev/gpiomem` access in the systemd unit.
- `I2CRelayToolBackend` (PCF8574/MCP23008).
- `GpioToolBackend`.
- Factory: `tool_backends.create(kind, config)` maps backend_kind strings.

## Hot-swap quiescence barrier (CORRECTED)

**Call `handle_stop_command()` (`command_api.py:818-832`) which:**
1. Cancels `streaming_handle` (L829-830)
2. Sets `should_stop = True` (L831)
3. Stops jog via `handle_jog_stop()` (L1339) — **NOT just should_stop**
   (jog_thread doesn't check should_stop)

**THEN** join `trajectory_state["thread"]` with timeout 2s.
**THEN** join `trajectory_state["jog_thread"]`.

**Blocking `handle_move_profiled` path:** the executor thread is local,
NOT in `trajectory_state["thread"]`. The barrier sets `should_stop=True` and
waits for the blocking call to return. A separate watchdog thread sends
the barrier if the UDP handler is blocked.

**State machine:**
```
IDLE -> SET_ACTIVE_TOOL -> BARRIER
BARRIER -> is_running==False -> PARK
BARRIER -> timeout 2s -> ABORT (409 MOTION_ACTIVE)
PARK -> executor joined -> DEENERGISE
DEENERGISE -> torque off ack -> SWAP
SWAP -> Tool instance built -> REINIT
REINIT -> initialize() ok -> IDLE
REINIT -> initialize() failed -> ABORT (500 SWAP_FAILED)
```

**Partial-failure recovery:**
| Failure | Recovery |
|---|---|
| Barrier timeout | Re-arm should_stop=False, reply PARK_FAILED, no swap |
| set_torque_enabled(False) fails on one servo | Continue rest, log, reply SWAP_FAILED, no swap |
| ToolBackend.initialize() raises | Roll back, re-enable torque, reply SWAP_FAILED |
| Tool servo ping fails | Reply SWAP_FAILED,SERVO_NOT_PRESENT, keep old tool |

**try/finally always re-enables torque and resets should_stop=False.**

## Gripper de-special-casing (exhaustive — 4 sites)

1. `base.py:189-192` — `logical_joint_to_actuator_ids` adds gripper as
   joint `num_logical_joints+1`. Remove that addition. Gripper is now a
   tool, not joint 7.
2. `utils.SERVO_ID_GRIPPER` (L45) — remove or make dynamic from
   mounted tool config.
3. `servo_driver.py:960` — `arm_servo_ids = [sid for sid in
   utils.SERVO_IDS if sid != utils.SERVO_ID_GRIPPER]`. Remove the
   gripper filter; tool servos are managed by tool config.
4. `api/main.py:603-618` — `arm = angles[:6]; gripper = angles[6]`.
   Replace with dynamic split based on `num_logical_joints`.

**E-stop:** wire `tool_backend.emergency_off()` into
`handle_stop_command` (`command_api.py:818`) after streaming handle cancel.

## UDP: `SET_ACTIVE_TOOL,tool_id,force`

## API endpoint

```python
class SetActiveToolRequest(BaseModel):
    tool_id: str
    force: bool = False

class SetActiveToolResponse(BaseModel):
    status: Literal["ok","aborted","parked"]
    previous_tool_id: Optional[str]
    new_tool_id: str
    park_pose: Optional[list[float]]
```
`POST /config/active/tool` -> UDP `SET_ACTIVE_TOOL,tool_id,force`.
Errors: 404, 409, 503, 500.

## Tests
- `test_hot_swap_state_machine.py` (partial-failure recovery matrix).
- `test_tool_backend.py`.

---

# CHUNK 8: Tool UI + paper-doll joint health

**Goal:** Dynamic ControlPanel from mounted tool, tool loadout cards with
equip animation, paper-doll joint health on 3D arm.

**Files touched:**
- `web-ui/src/ControlPanel.tsx`
- `web-ui/src/ArmVisualizer.tsx`
- new `web-ui/src/components/viewport/JointHealthTooltip.tsx`
- new `web-ui/src/health/jointHealth.ts`

## Dynamic ControlPanel

Gripper slider (L235-247) -> dynamic tool controls from mounted tool
manifest (fetched via `GET /config/tools/{id}`). Tool manifest reaches
frontend via the config API.

- gripper -> angle slider
- drill -> power toggle + speed dial
- 2-servo claw -> two independent sliders + zero buttons

## Paper-doll health

**Data flow:** `latest.servos` (already in SSE, App.tsx:2354-2372) ->
`servoHealth` prop on ArmVisualizer.

**Load formula (normalized):**
```
dutyNorm = drive_duty_per_mille / 1000
tempNorm = clamp((temp_c - 35) / (70 - 35), 0, 1)
currentNorm = clamp(current_a / 2.5, 0, 1)
load = 0.5*dutyNorm + 0.3*tempNorm + 0.2*currentNorm
```
Twin: max load across servos (worst-case wins).

**Color:** lerp green->yellow->red by load. Applied via
`mesh.material.emissive` + `emissiveIntensity = 0.25 + load*0.6` (NOT
material replacement — avoids flicker).

**Hover tooltip:** `onJointHover` callback prop -> HTML overlay
(portal to document.body) via new `ArmVisualizerHandle.projectToScreen`.

## Components

| File | jsdom-testable |
|---|---|
| `JointHealthTooltip.tsx` | Yes (pure HTML) |
| `jointHealth.ts` | Yes (pure: computeLoad, loadToColor) |

## Tests
- `jointHealth.test.ts`, `JointHealthTooltip.test.tsx`.

---

# CHUNK 9: IK drag mode (AFTER Chunk 7a — needs TCP)

**Goal:** Click-drag the tool-tip in 3D; the arm follows via IK with a
ghost preview.

**Files touched:**
- `web-ui/src/ArmVisualizer.tsx`
- new `web-ui/src/components/viewport/ViewportToolbar.tsx`
- new `web-ui/src/ik/useIkDrag.ts`
- `src/gradient_os/api/main.py` (new endpoint)

## New lightweight endpoint

`POST /ik/solve`:
```python
class IkSolveRequest(BaseModel):
    target: tuple[float,float,float]
    orientation: Literal["fixed","current"] = "fixed"

class IkSolveResponse(BaseModel):
    ok: bool
    joints_rad: Optional[list[float]]
    reason: Optional[str]
```
Single IK call (NOT a full plan). Reuses `ik_solver.solve_ik()`.

## ViewportToolbar

Segmented `[Orbit][Puppet][Pick]` mode toggle. OrbitControls
disabled in Puppet mode (`controls.enabled = false`).

## IK drag spec

- **Drag plane:** perpendicular to camera, through current tool-tip.
  Recomputed at drag-start. Visualized as faint quad, fades after 200ms.
- **IK frequency:** 30Hz (rAF-gated, coalesce mousemove).
- **No-solution:** ghost turns red (`emissive: 0xef4444`), badge
  `⚠ {reason}`, real arm does not move.
- **Commit-on-release** (default): `POST /trajectory/execute-preview`
  (the existing absolute-move path — `move-line-absolute` does NOT
  exist). Live puppet (opt-in): deadman + 3s hold, streams
  `set_servo_positions`.
- **Ghost:** `robot.clone(true)`, opacity 0.35, cyan, depthWrite false.
  Removed on pointerup.
- **Shift** = fine (0.1x sensitivity, 0.25x commit speed).
- **Ctrl** = axis-constrain (dominant axis of first 10px).
- **Alt** = temporary orbit (one gesture).

## Component

`useIkDrag.ts` (throttle + fetch, jsdom-testable with mock rAF +
fake timers).

## Tests
- `useIkDrag.test.ts` (mock rAF + fake timers + mock fetch).

---

# CHUNK 10: Planner path_mode + pause_s (parallel track)

**Goal:** `path_mode: linear | capture_speed` (defer joint) +
per-waypoint `pause_s`.

**Files touched:**
- `src/gradient_os/trajectory_planner.py`
- `src/gradient_os/arm_controller/trajectory_execution.py`
- `src/gradient_os/arm_controller/command_api.py`
- `src/gradient_os/api/main.py`

## path_mode semantics

| Value | Behaviour |
|---|---|
| `linear` | Existing trapezoidal, `DEFAULT_PROFILE_VELOCITY` |
| `capture_speed` | Trapezoidal with `max_velocity = capture_speed_m_s` (default 0.02 m/s), accel = v/0.5s |

`capture_speed` is a user-specified Cartesian velocity. When AprilTag
lands, the controller will set it from the detection frame rate. For
now it's a slow uniform approach speed for camera-capture waypoints.

**`joint` mode is DEFERRED** — it requires a new joint-space planner that
doesn't exist (trajectory_planner.py is 206 lines, Cartesian-only).

## Threading

API request -> UDP `PLAN_TRAJECTORY_POINTS,...,MODE=linear|capture_speed,CAPV=<float>`
-> `command_api.handle_plan_trajectory_points` ->
`_plan_preview_points_payload(path_mode=, capture_speed_m_s=)` ->
picks `generate_capture_speed_profile` vs `generate_trapezoidal_profile`.

## pause_s per waypoint

`pause_s_after: float = 0.0` field on move step dicts. Executor loop
(`trajectory_execution.py:873-879`): after step completes, if
`pause_s_after > 0`, insert interruptible sleep (check `should_stop`
every 10ms). **Insertion point: AFTER move completes, BEFORE next
step.** Existing pause step (L646) uses `time.sleep` (blocking);
`pause_s_after` uses the interruptible pattern from L892-894.

## New planner function

```python
def generate_capture_speed_profile(start_pos, end_pos,
    capture_speed_m_s=0.02, frequency=100):
    ramp_time = 0.5
    max_accel = capture_speed_m_s / ramp_time
    return generate_trapezoidal_profile(
        start_pos, end_pos, capture_speed_m_s, max_accel, frequency)
```

## Pydantic request models

```python
class PlanPointsRequest(BaseModel):
    points: list[tuple[float,float,float]]
    path_mode: Literal["linear","capture_speed"] = "linear"
    capture_speed_m_s: float = 0.02
    pause_s: Optional[list[float]] = None  # one per point
    speed_multiplier: float = 1.0

class PlanWeldRequest(BaseModel):
    model_id: str
    edge_id: str
    start_s: float = 0.0
    end_s: float = 1.0
    sample_count: int = 40
    weld_type: Literal["fillet","butt","spot"] = "fillet"
    weld_name: str = ""
    waypoints_override: Optional[list[tuple[float,float,float]]] = None
    sections: Optional[list[dict]] = None
    preview_name: Optional[str] = None
    options: Optional[dict] = None
    path_mode: Literal["linear","capture_speed"] = "linear"
    capture_speed_m_s: float = 0.02
    pause_s_approach: float = 0.0
    pause_s_retract: float = 0.0
```

Validation: `len(pause_s)==len(points)`, each `pause_s[i]` in [0, 60],
`capture_speed_m_s` in [0.001, 0.5].

## Tests
- `test_capture_speed_profile.py`, `test_pause_s_after.py`.

---

# CHUNK 11: Timeline scrubber + waypoint cards (AFTER Chunk 10)

**Goal:** Scrubber bar under viewport previews trajectory; floating
per-waypoint edit cards in 3D.

**Files touched:**
- `web-ui/src/ArmVisualizer.tsx`
- new `web-ui/src/components/timeline/TimelineScrubber.tsx`
- new `web-ui/src/timeline/scrubUtils.ts`
- new `web-ui/src/components/viewport/WaypointEditCard.tsx`

## CRITICAL FIELD NAME FIX

The `/trajectory/plan-points` response field is **`cartesian_path`**
(`command_api.py:2019`), NOT `pathPoints`. **Use `cartesian_path`
throughout.**

## Timeline scrubber

- **Preview data:** reuses `/trajectory/plan-points` response
  `cartesian_path` + `trajectory.moves` (for per-frame joint angles).
  No new endpoint.
- **Ghost arm:** persistent clone (separate from IK drag's transient
  clone). `ArmVisualizerHandle.setScrubPose(jointsRad: number[] | null)`
  — new imperative handle method. Writes to `scrubAnglesRef`; animate
  loop blends when non-null. Coexists with `joints` prop effect
  (L1687-1707) by using a separate ref.
- **Play:** animates ghost through full path. Speed 0.25-4x. Loop
  toggle. Preview-only (NOT real arm).
- **"Send to arm at scrub position":** `POST /trajectory/execute-preview`
  (deadman + 0.25x speed).
- **Layout:** 56px bar, `absolute bottom-0 inset-x-0 z-20`. Track with
  segment colors by path_mode (linear=cyan, capture=rose). Waypoint
  markers. Hover tooltip.

## Waypoint edit card

- **Positioning:** project 3D waypoint to 2D via
  `ArmVisualizerHandle.projectToScreen`. Update on camera move
  (OrbitControls `change` event). 30Hz throttle.
- **Contents:** path-mode chips (linear/capture-speed), speed slider
  (0-2 m/s), pause field (0-10000ms), duplicate, delete.
- **Edge clipping:** clamp to viewport, flip card to opposite side, off-
  screen dir-arrow (Destiny-style).
- **Real-time update:** edits call existing handlers ->
  `requestPlannerPreview` -> `cartesian_path` updates -> ribbon
  rebuilds.

## Components

| File | jsdom-testable |
|---|---|
| `TimelineScrubber.tsx` | Yes (pure HTML/SVG) |
| `scrubUtils.ts` | Yes (pure: tToPathIndex, interpolateJoints, totalDuration) |
| `WaypointEditCard.tsx` | Yes (pure HTML) |

## Tests
- `scrubUtils.test.ts`, `TimelineScrubber.test.tsx`,
  `WaypointEditCard.test.tsx`.

---

# CHUNK 12: Command palette + AprilTag stubs

**Goal:** Fuzzy-search command palette + reserved AprilTag vision panel
with stub endpoints.

**Files touched:**
- `web-ui/src/App.tsx` (minimal — Cmd+K handler + mount)
- new `web-ui/src/components/palette/CommandPalette.tsx`
- new `web-ui/src/components/palette/fuzzyMatch.ts`
- new `web-ui/src/components/palette/useCommandActions.ts`
- new `web-ui/src/components/vision/AprilTagPanel.tsx`
- `src/gradient_os/api/main.py`

## Command palette

**24 actions:**

| Group | Actions |
|---|---|
| Motion | Home, Rest, Stop, Zero J1, Zero J2, Zero J3, Zero J4, Zero J5, Zero J6 |
| Tools | Mount Gripper, Mount Vacuum, Mount Weld Torch, Unmount Tool |
| Planning | Plan Linear, Plan Capture-Speed, Add Waypoint Here, Delete Selected Waypoint, Duplicate Waypoint, Run Preview |
| View | Reset View, Focus on Tool, Focus on J1-J6, Toggle Bounding Box, Toggle Camera |
| Mode | Enter Calibration, Enter IK Puppet, Enter Discovery |
| Config | Set Speed Multiplier, Open Settings |

**Keybindings:** Cmd/Ctrl+K open, Esc close, arrows navigate, Enter execute,
Tab jump group, Cmd+Enter execute + keep open.

**Implementation:** custom (no cmdk dep). Custom subsequence fuzzy
matcher (~30 lines, no Fuse.js dep). Portal to document.body, z-[100].

`useCommandActions.ts` returns `CommandAction[]` from the store.
Dispatches to existing App.tsx handlers (no duplicated logic).

## AprilTag stubs

| Endpoint | Method | Status | Response |
|---|---|---|---|
| `/vision/apriltags` | GET | 501 | `{"detections":[],"camera_id":"none","fps":0.0}` |
| `/vision/apriltags/stream` | GET (SSE) | 501 | same per frame |
| `/waypoint/from-tag` | POST | 501 | `WaypointFromTagRequest` schema in response body |

```python
class AprilTagDetection(BaseModel):
    tag_id: int
    family: str
    pose_position_m: tuple[float,float,float]
    pose_quaternion: tuple[float,float,float,float]
    pixel_center: tuple[int,int]
    pixel_corners: list[tuple[int,int]]
    timestamp_s: float
    confidence: float

class WaypointFromTagRequest(BaseModel):
    tag_id: int
    offset_m: tuple[float,float,float] = (0.0,0.0,0.0)
    orientation_mode: Literal["tag","current","fixed"] = "tag"
    fixed_orientation_quat: Optional[tuple[float,float,float,float]] = None
```

**Stub routes registered in `api/main.py` — no collision with existing
routes** (verified: no `/vision/*` routes exist today).

## AprilTagPanel

Reserved stub panel: camera feed placeholder, "detections: none — vision
service not configured."

## Components

| File | jsdom-testable |
|---|---|
| `CommandPalette.tsx` | Yes |
| `fuzzyMatch.ts` | Yes (pure) |
| `useCommandActions.ts` | Yes |
| `AprilTagPanel.tsx` | Yes |

## Tests
- `CommandPalette.test.tsx`, `fuzzyMatch.test.ts`.

---

# Cross-cutting rules for all chunks

1. **Three gates must pass after every chunk:** `pytest tests/` (0 skipped),
   `npm run test:run`, `npm run build`.
2. **New UI components go in sibling files** under
   `web-ui/src/components/`. App.tsx gains only import + mount point +
   minimal wiring. Do NOT bloat App.tsx further.
3. **3D-dependent logic stays in `ArmVisualizer.tsx`** (untestable in
   jsdom). Extract all math/state/fetch into pure utility files
   (testable). ArmVisualizer reaches new features via
   `ArmVisualizerHandle` methods or new props.
4. **SSE calibration/discovery data on `/calibrate/stream`** (new
   dedicated endpoint), NOT `/monitor` (would break `handleMessage`).
5. **All calibration/rename API endpoints proxy via UDP** to the
   controller, NOT direct `servo_driver` calls from the API process.
6. **DEVLOG.md + AGENT_SCRATCHPAD.md** must be updated for every chunk
   (repo workflow rule).
7. **Single-node deployment** (controller + API share filesystem).
   Distributed config replication is out of scope.
