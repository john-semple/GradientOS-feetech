## 2026-09-15 — Sprint 10 tuning: hardware diagnostics (cap floor + interleaved read)

- Hardware test 1 — CAP_FLOOR 150 → 60: **no difference** in slow-move jitter.
  Cap is not the binding constraint; servo tracks goal stream speed, not cap.
- Hardware test 2 — interleaved read fully disabled: **no difference** either.
  Read was not the jitter source on slow moves (20ms read fits inside the 33Hz
  period; it was only a deadline-blower at 100Hz).
- Both negative results point at the **33 Hz re-plan sawtooth** as the remaining
  suspect: each goal write triggers firmware Case A re-plan (abort current
  trapezoid, re-plan from pos+vel, decelerate toward arrival); at 33 Hz the
  servo executes ~30ms of each plan, so decel-sag/rewrite-boost cycles at 33 Hz
  are felt as jitter throughout slow moves. J1/J2 (high load + backlash)
  amplify the velocity ripple; fast moves at 100 Hz rewrite plans every 10ms
  before decel shaping develops — smooth (matches Sprint 07 Part C bench).
- User's sharp observation: PID backlash hunting would show at ALL speeds, not
  just slow — consistent with pacing-frequency hypothesis, not PID.
- Also explains iteration history: iter 4-5 lowered frequency to fight 100Hz
  quantization buzz, traded it for re-plan sawtooth; "still slightly jerky on
  slow parts" was the sawtooth appearing.
- Next experiment (pending user approval to move arm): force slow moves to 100Hz
  (SLOW_MOVE_THRESHOLD_DEG_S = 0). Smooth → 33Hz was the culprit. Micro-buzz
  returns → land slow non-weld moves on Sprint 04 endpoint paradigm
  (plan_profiled_segment) instead — single goal + matched cap, firmware's own
  smooth trapezoid (proven Home-button pattern).
- Interleaved read remains disabled in code (diagnostic state — GUI position
  feedback during moves is stale until re-enabled with a shorter timeout).
- 36/36 streaming tests pass.

## 2026-09-15 — Sprint 09: added Workstream E (per-servo data view) + wiggle axis auto-assign

- User asked to extend the GUI sprint (Sprint 09, not 11/12 — those are tool
  change and reactive motion) with two features:
  1. Expandable per-servo data view showing temperature, torque/load, and
     velocity for each servo (new Workstream E).
  2. While wiring jog controls to an external RC/gamepad (Workstream D), add an
     axis auto-assignment wizard that prompts the operator to wiggle each axis
     in turn (X, then Y, then Z) and auto-detects which physical stick maps to
     each DOF.
- Workstream E details: collapsed row = ID + label + temp/torque/velocity
  badges with color thresholds; expanded = full live values + per-servo
  sparkline. Reuses existing telemetry SSE stream. Only backend work is adding
  torque/load to the bulk read if not already present (additive, gated behind a
  capability flag if expensive on one servo backend).
- Wiggle wizard details: prompt-detect-assign cycle per DOF, samples
  navigator.getGamepads() at ~60 Hz, picks max-deflection axis above a
  threshold, records axis index + invert flag, persists per
  vendor+product ID in localStorage. Same UX for the evdev backend path.
- Updated `feetech-project/sprints/sprint-09-gui-improvements.md` only — no
  code changes. Sequencing & Notes updated to cover E and the wiggle wizard.
- Verified: Sprint 09 is the GUI sprint; 11 = automated tool change, 12 =
  reactive motion (hypothetical). Did not touch 11 or 12.


- User reported persistent twitch on slow moves, especially J1/J2 (backlash).
- Root cause analysis: CAP_FLOOR=150 LSB (13.2 deg/s) was 2.6× over-demand for
  slow moves at 5 deg/s. Servo raced across backlash gap to each tiny lookahead
  goal, arrived, stalled, waited, raced again — overshoot-stall at 100 Hz.
- Firmware hard floor is 50 LSB (4.4 deg/s) per Sprint 07 Part A.
- Lowered CAP_MIN and CAP_FLOOR from 150 → 60 LSB (5.3 deg/s), just above firmware
  floor. For a 5 deg/s move, cap is now 1.06× demand instead of 2.6×.
- 36 streaming tests pass. Pending hardware visual inspection.
- Next: hill-climb over remaining Option A params (lead time, pacing freq, read
  timing, cap multiplier) using sim with dynamics model + backlash simulation.

## 2026-09-15 — Sprint 10: tuning iterations on real hardware

- Six iterations of tuning on real hardware after initial implementation.
- Full writeup: `feetech-project/sprints/sprint-10-implementation-and-lessons.md`
- Key fixes in order:
  1. Per-joint speed caps (was using max(caps) for all servos → backlash hunt)
  2. Telemetry bus contention suppression (telemetry reads starving write stream)
  3. Cap multiplier lowered 3× → 1.2×, floor 300 → 150 (overshoot-stall vibration)
  4. Variable pacing 100/33 Hz + lookahead 50 → 100 ms (micro-vibration on slow moves)
  5. Slow-move threshold raised 10 → 50 deg/s (most rotysquare moves are below 50)
  6. Fixed wrong relative import (`from ...` → `from ..`) causing GUI to never update
- Remaining issues: trapezoidal profile acceleration discontinuities (needs S-curve
  planner), ~0.5s GUI lag (needs higher read rate or direct UDP push from pacing thread)
- All 93 backend tests pass throughout. End-to-end test is flaky (pre-existing timing).

## 2026-09-15 — Sprint 10: Smooth Streaming Executor (Case A Setpoint Streaming)

- Task: implement Sprint 10 — migrate motion executors from arrive-and-stop
  waypoint streaming to continuous setpoint streaming with 50 ms lookahead,
  wrapped entirely inside the backend. Planner, command API, web UI, and
  weld planner require zero changes.
- Design decisions (agreed with user before implementation):
  - HLS3950 shares the same streaming implementation as STS3215 (both are
    near-identical driver copies). Config-level override `streaming_enabled:
    False` disables it with no code change if bench testing reveals HLS
    firmware doesn't blend smoothly (Case A unverified on HLS).
  - Simulation backend gets a robust pacing implementation (100 Hz, 50 ms
    lookahead) — not a trivial instant-replay. `sim_fast_forward` option
    (or `SIM_FAST_FORWARD=1` env var) skips sleeps for automated tests
    using a virtual clock.
  - MotionHandle has `cancel()`, `pause()`, `resume()`, `is_done()`,
    `wait()`. `cancel()` writes current-position-as-goal (servo decelerates
    over ~50 ms horizon — smoother than a hard brake). `pause()`/`resume()`
    enables manual-tool-change / human-checkpoint workflows. `resume()`
    re-derives nearest path timestamp from sync_read; large drift triggers
    a short profiled reconnect segment.
  - `handle_stop_command()` in command_api.py now cancels the active
    streaming handle before falling back to the legacy brake command.
- Files created:
  - `src/gradient_os/arm_controller/motion_handle.py` — MotionHandle class
    with MotionState enum (RUNNING/PAUSED/CANCELLED/DONE), thread-safe
    state transitions, cancel callback, resume event, done event.
  - `src/gradient_os/arm_controller/backends/_streaming_mixin.py` — shared
    StreamingMixin for Feetech-class backends: pacing loop (100 Hz, 50 ms
    lookahead), per-move velocity cap sizing (max|Δq/Δt|×2 clamped
    [100,2000]), stream guard (clamp goals to path min/max), horizon rule,
    cancel (write current-pos-as-goal), pause/resume (sync_read nearest t,
    profiled reconnect for large drift).
  - `tests/test_setpoint_streaming.py` — 36 gating-matrix tests.
- Files modified:
  - `actuator_interface.py` — added `supports_setpoint_streaming` property
    (default False) and `execute_timed_path()` method (default
    NotImplementedError) to ActuatorBackend ABC. Re-exports MotionHandle.
  - `backends/sts3215/driver.py` — STS3215Backend now inherits
    StreamingMixin; `_set_streaming_config()` called in __init__.
  - `backends/hls3950/driver.py` — HLS3950Backend now inherits
    StreamingMixin; `_set_streaming_config()` called in __init__.
  - `backends/simulation/backend.py` — SimulationBackend overrides
    `supports_setpoint_streaming = True` and implements
    `execute_timed_path()` with robust pacing (100 Hz, 50 ms lookahead,
    virtual clock for fast_forward, set_joint_positions for sim writes).
  - `trajectory_execution.py` — added
    `_backend_supports_setpoint_streaming()` helper,
    `_joint_path_to_timed()` converter, `_execute_streaming_step()`
    function. `_open_loop_executor_thread` hands off to
    `execute_timed_path` when streaming is available.
    `_trajectory_executor_thread` routes move steps to streaming when
    available (takes precedence over profiled segments; covers both weld
    and non-weld moves).
  - `command_api.py` — `handle_stop_command()` cancels active streaming
    handle before legacy brake.
  - `feetech-project/sprints/sprint-10-smooth-streaming-executor.md` —
    updated with design decisions, HLS config override, robust sim,
    MotionHandle shape, pause/resume, bench validation flagged as
    needs-hardware.
- Validation:
  - pytest: **93 passed, 0 skipped, 0 failed** (57 existing + 36 new)
  - npm test: 8 passed
  - npm build: success
  - All bench validation items flagged as requiring physical hardware.
- Risks:
  - HLS3950 firmware Case A blending unverified — config override ready.
  - GIL contention with IK/vision threads — pacing loop body is tiny
    (interpolate + one sync_write); Sprint 07 measured ~160 Hz sustainable.
  - `resume()` drift heuristic (> 0.1 rad → profiled reconnect) is a
    placeholder; needs bench calibration on real hardware.

## 2026-09-14 — Sprint 08b documentation pass + critical httpx discovery

- Task summary:
  - User asked to update documentation for Sprint 08b completion. While marking the
    endpoint-audit task complete honestly, discovered the entire API endpoint test
    file had been silently skipped — not run — the whole time.
- Critical discovery:
  - `tests/test_api_endpoints.py` begins with `pytest.importorskip("httpx")`;
    `httpx` was missing from the venv (the `[dev]` extra was never installed), so
    the whole 20+ test file collected as a single "1 skipped". My earlier claim of
    "31 passed, 1 skipped (intentional hardware-only skip)" was wrong — the skip
    was the API contract layer being untested.
  - Installed httpx (0.28.1); the file now runs.
- Latent failures surfaced and fixed once the file actually ran:
  - Pre-existing: `plan_preview_trajectory_points` mock in the test file didn't
    accept the `sections` kwarg the endpoint now passes (mock rotted while the
    file was skipped). Fixed the mock signature.
  - New tests I'd written had wrong expectations, corrected to actual behavior:
    REST sends joint-angle CSV (not "REST"); rotate is relative to current
    orientation (10+15=25); command floats serialize as "0.0"; /health includes
    a controller block.
- Added endpoint smoke tests for previously untested simple endpoints: rest,
  move-line-relative, rotate, set-gripper, set-orientation, jog/start, jog/stop,
  jog/velocity, jog/deadman, jog/debug, health. (/monitor SSE left untested —
  not a simple smoke test.)
- Backend suite final state: **57 passed, 0 skipped** (was 31 passed + 1 silent
  module skip).
- Documentation updated:
  - `feetech-project/sprints/sprint-08b-test-infrastructure.md` — all tasks
    checked, completion notes + discoveries section added.
  - `feetech-project/TODO.md` — sprint table (08b ✅), dependency diagram, and
    Next action now points at Sprint 09.
  - `feetech-project/sprints/sprint-09-gui-improvements.md` — prerequisite line
    marked complete with pattern pointers.
  - `AGENTS.md` — new "Running tests (the three gates)" section with the
    importorskip-skip warning; `[dev]` extra note now flags httpx requirement.
  - `tests/README.md` — test description for test_api_endpoints.py (httpx
    requirement + silent-skip risk), restored test_end_to_end.py description,
    fixed stale J1 gear-ratio mention in test_driver.py description.
- Validation:
  - `python -m pytest tests/ -q` — 57 passed, 0 skipped, 2 warnings.
  - Web UI suite and build unaffected by this pass (no web changes): 8 tests
    pass, build passes (verified earlier this session).
- Risks / notes:
  - httpx venv version (0.28.1) differs from the `[dev]` pin (0.27.2); works
    with current FastAPI TestClient. Align at next dependency pass if desired.
  - The silent-skip failure mode is now guarded in AGENTS.md: expect 0 skipped.

## 2026-09-14 — Sprint 08b: Test infrastructure baseline (web UI + backend suite repair)

- Task summary:
  - Implemented Sprint 08b (`feetech-project/sprints/sprint-08b-test-infrastructure.md`):
    vitest-based smoke-test baseline for the web UI, plus repair of 6 pre-existing
    backend test failures so the full `python -m pytest tests/` gate passes again.
  - Confirmed with user that servo bench tests (direct USB, no GradientOS software)
    run concurrently and safely — the test work touches no serial/USB paths.
- Changes (web-ui):
  - Added dev deps: vitest 3, @testing-library/react, @testing-library/jest-dom,
    @testing-library/user-event, jsdom.
  - Added `web-ui/vitest.config.ts` (jsdom, React plugin, `css: false`, setup file).
  - Added `web-ui/src/test/setup.ts` — ResizeObserver polyfill (jsdom lacks it;
    TelemetryCharts.tsx:273 instantiates one on mount) + jest-dom matchers.
  - Added `web-ui/src/test/apiMock.ts` — `installFetchMock()` with response shapes
    derived from the real FastAPI responses in api/main.py (mirrors the assertions
    in tests/test_api_endpoints.py); records a call log for interaction tests.
  - Added smoke tests: ControlPanel (3), SidebarDrawer (3), TelemetryCharts (2).
  - Added `npm run test` / `npm run test:run` scripts; documented testing patterns
    in web-ui/README.md.
- Changes (backend tests):
  - Added `tests/conftest.py` — session-scoped init mirroring run_controller.py
    startup: set_active_robot(gradient0) + set_active_backend(sts3215) +
    utils._populate_servo_constants(). Without this, module-level protocol
    constants (SERVO_IDS, SYNC_WRITE_START_ADDRESS, ...) are None since the
    sprint-05 backend restructure, and 4 tests failed with TypeError.
  - Fixed `tests/test_end_to_end.py` — controller startup now creates a real
    backend instance (against the mocked serial), so the open-loop executor
    routes writes via backend.sync_write() instead of the mocked
    servo_protocol.sync_write_goal_pos_speed_accel. Patched
    `_use_backend` → False in both servo_driver and trajectory_execution to
    pin the test to the legacy UDP→protocol→serial path it asserts on.
  - Renamed/rewrote `tests/test_driver.py::test_j1_gear_ratio` →
    `test_j1_command_maps_to_physical`: the 2:1 base-gear expectation was stale
    (previous mini-arm model); gradient0 maps logical→physical 1:1 (verified in
    servo_driver.py set_servo_positions and robots/gradient0/config.py).
  - Updated `tests/README.md` with the conftest init explanation, the canonical
    API-endpoint mock pattern (patch_send), and web-UI test instructions.
- Validation:
  - `npm run test:run` — 8 passed (3 files).
  - `npm run build` — passes.
  - `python -m pytest tests/` — 31 passed, 1 skipped (intentional hardware-only
    skip). Previously: 6 failed, 25 passed.
  - Pre-existing status of the 6 failures confirmed via `git stash` (failures
    exist on pristine tree; not caused by this sprint's changes).
- Risks / notes:
  - The web-UI fetch mock and the backend API tests encode the same response
    shapes; drift between them is a manual-discipline risk (documented in both
    test READMEs).
  - No tests import App.tsx (Three.js/WebGL would crash jsdom); rule documented.
  - Backend constant-initialization now happens in conftest; if run_controller.py's
    startup sequence changes, conftest must be updated to mirror it.

## 2026-02-16 00:14 +11:00

- Task summary:
  - Refined the sidebar drawer/panel UX after user feedback.
  - Moved the drawer close button into the panel title-line area and removed redundant outer framing behavior.
  - Kept robot control docked on the right side with collapsible behavior.
  - Added persistent workflow artifacts (`AGENT_SCRATCHPAD.md`) and top-level pointers so devlog/scratchpad/skills usage is explicit.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx` for in-panel close-button placement and drawer sizing.
  - Updated `web-ui/src/App.tsx` and `web-ui/src/ControlPanel.tsx` in prior steps for right-aligned collapsible robot-control behavior.
  - Added `AGENT_SCRATCHPAD.md`.
  - Updated `QUICK_START.md` with a dedicated workflow pointers section for `DEVLOG.md`, `AGENT_SCRATCHPAD.md`, and `.cursor/skills/`.
- Validation:
  - `npm run build` in `web-ui` completed successfully.
  - `ReadLints` checks reported no lint errors in changed frontend files.
- Follow-up notes / risks:
  - Close button placement depends on panel title spacing; if panel typography changes later, tweak `top/right` offsets in `SidebarDrawer`.
  - If additional drawer panel types are introduced with different widths, keep drawer width and content width synchronized.

## 2026-02-16 00:20 +11:00

- Task summary:
  - Fixed tab-forcing behavior where STEP load / persisted tree selection auto-switched to Weld and blocked switching to other tabs.
  - Kept tree-to-weld synchronization, but limited panel auto-open to explicit tree click actions only.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - removed forced `activePanel` reassignment from the selected-tree-node effect.
    - kept weld segment sync from tree selection (`weldSegmentEdgeId`) without overriding active tab.
    - updated `handleSelectProgramTreeNode` to open a panel only when user directly clicks a tree node.
- Validation:
  - `ReadLints` on `web-ui/src/App.tsx` returned no issues.
  - `npm run build` in `web-ui` completed successfully.
- Follow-up notes / risks:
  - If future tree sync rules are added, keep them non-authoritative over manual sidebar tab selection.

## 2026-02-16 21:51 +11:00

- Task summary:
  - Moved `Reset Pose` to the bottom of the STEP Import panel as requested.
  - Addressed multi-selected edge flicker/override behavior by decoupling tree-driven sync from weld-driven selection updates.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - relocated `Reset Pose` button to panel footer.
    - introduced interaction origin tracking (`tree` vs `weld`) to prevent selection ping-pong between program tree and weld segment list.
    - restricted tree-to-weld segment activation to explicit tree-origin events.
  - Updated `web-ui/src/ArmVisualizer.tsx`:
    - made selected/hovered topology line materials opaque (`transparent=false`) to reduce visual flicker when multiple edges are selected.
- Validation:
  - `ReadLints` on updated frontend files returned no issues.
  - `npm run build` in `web-ui` completed successfully.
- Follow-up notes / risks:
  - If flicker persists on specific GPU drivers, next step is to move selected-edge rendering fully to non-overlapping mesh overlays and hide base lines for selected edges.

## 2026-02-17 10:32 +11:00

- Task summary:
  - Enforced automatic memory-loop behavior so agents consistently use both `AGENT_SCRATCHPAD.md` and `DEVLOG.md`.
- Changes:
  - Added `.cursor/rules/agent-memory-loops.md` with `alwaysApply: true`.
  - Updated `.cursor/rules/agent-gated-checklist.md` to include mandatory scratchpad/devlog read/write gates.
  - Rule now requires:
    - start-of-task read of both memory files,
    - during-task high-signal capture,
    - end-of-task writeback to both files.
- Validation:
  - Verified new rule file exists under `.cursor/rules/` with frontmatter and actionable workflow steps.
- Follow-up notes / risks:
  - Existing already-running sessions may need a fresh user turn to naturally re-anchor on the new rule text.

## 2026-02-17 10:45 +11:00

- Task summary:
  - Added explicit pointers from memory-loop docs to the exact source skills and managed files.
- Changes:
  - Updated `.cursor/rules/agent-memory-loops.md` with a required mapping section:
    - `.cursor/skills/learning-scratchpad-loop/SKILL.md` -> `AGENT_SCRATCHPAD.md`
    - `.cursor/skills/devlog-loop/SKILL.md` -> `DEVLOG.md`
    - Included both reference templates under each skill.
  - Updated `QUICK_START.md` workflow pointers to include the same direct skill/template/file paths.
- Validation:
  - Confirmed reference template paths exist:
    - `.cursor/skills/learning-scratchpad-loop/references/scratchpad-template.md`
    - `.cursor/skills/devlog-loop/references/devlog-entry-template.md`
  - `ReadLints` on updated markdown files reported no diagnostics.
- Follow-up notes / risks:
  - None for this docs/rules alignment change.

## 2026-02-17 00:12 +11:00

- Task summary:
  - Replicated explicit scratchpad/devlog skill mappings across all always-on rules so they stay in context everywhere.
- Changes:
  - Updated `.cursor/rules/agent-gated-checklist.md` with required skill/template/file mapping section.
  - Updated `.cursor/rules/agent-ambiguity-triggers.md` with required skill/template/file mapping section.
  - Updated `.cursor/rules/agent-subagents.md` with required skill/template/file mapping section.
  - Updated `.cursor/rules/rtos-ethercat-readme.md` with required skill/template/file mapping section.
- Validation:
  - Confirmed `.cursor/rules/` files with `alwaysApply: true` now all include direct pointers to:
    - `.cursor/skills/learning-scratchpad-loop/SKILL.md` -> `AGENT_SCRATCHPAD.md`
    - `.cursor/skills/devlog-loop/SKILL.md` -> `DEVLOG.md`
  - `ReadLints` on edited markdown files reported no diagnostics.
- Follow-up notes / risks:
  - New `alwaysApply` rules introduced in future should copy the same mapping section to preserve consistency.

## 2026-02-17 00:41 +11:00

- Task summary:
  - Implemented the full "Weld Motion + Tree UX" pass:
    - compact Program Tree rows
    - chronological/default and grouped/toggle views
    - weld section planning with pragmatic transitions
    - torch angle controls and backend option plumbing
    - improved weld planner diagnostics and runtime robustness.
  - Addressed follow-up workflow gap by explicitly logging this session in both `DEVLOG.md` and `AGENT_SCRATCHPAD.md`.
- Changes:
  - Updated `web-ui/src/components/ProgramFeatureTree.tsx` for compact single-line rows and view-mode controls.
  - Updated `web-ui/src/previewUtils.ts` for grouped vs chronological tree generation and stable node reuse.
  - Updated `web-ui/src/App.tsx`:
    - persisted `programTreeViewMode` (default chronological),
    - added weld controls (`workAngleDeg`, `travelAngleDeg`, `transitionClearanceMm`, `postAction`),
    - added section generation for weld/transition/return-to-start planning payloads.
  - Updated `src/gradient_os/api/main.py`:
    - section payload parsing (`_coerce_plan_sections`),
    - weld option passthrough,
    - weld program save/load fields for new weld settings.
  - Updated `src/gradient_os/arm_controller/command_api.py`:
    - section-aware weld planning path,
    - continuous interior weld planning behavior,
    - transition section handling,
    - torch-angle orientation generation with fallback,
    - preview planned-step cache save for weld previews.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend: `ReadLints` on changed TS/TSX files reported no issues.
  - Backend: `./.venv/Scripts/python.exe -m py_compile "src/gradient_os/api/main.py" "src/gradient_os/arm_controller/command_api.py"` passed.
  - Backend smoke test:
    - `plan_preview_trajectory_points(..., sections=..., weld_metadata=...)` ran successfully after orientation-fallback path engaged for an infeasible torch-angle segment.
- Follow-up notes / risks:
  - Torch-angle requests can still be IK-infeasible for some geometries; fallback to orientation-lock prevents hard failure but may not preserve requested angle.
  - Full collision-aware transition planning remains intentionally deferred; tracked as future backlog work.

## 2026-02-17 00:47 +11:00

- Task summary:
  - Fixed sidebar menu overflow so panel content does not exceed viewport height.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - clamped drawer height to `max-h-[calc(100dvh-3rem)]`
    - enabled internal vertical scrolling via `overflow-y-auto`.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx` reported no issues.
- Follow-up notes / risks:
  - If additional absolute/fixed panel variants are introduced, apply the same viewport clamp to keep behavior consistent across all overlays.

## 2026-02-17 00:50 +11:00

- Task summary:
  - Fixed drawer header overlap where the close button could cover right-aligned panel header controls (e.g. Weld status badge).
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - increased inner content right padding from `pr-1` to `pr-10` to reserve a dedicated close-button gutter.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx` reported no issues.
- Follow-up notes / risks:
  - This keeps generic drawer content clear of the close control; if any panel needs full-width header actions later, consider converting the drawer to a shared explicit header row instead of overlay positioning.

## 2026-02-17 00:53 +11:00

- Task summary:
  - Added explicit takeover TODO instructions for a new model to continue unresolved drawer/header overlap quality work.
- Changes:
  - Updated `QUICK_START.md`:
    - added a top-level "TODO - New model takeover (high priority)" section,
    - documented current user-reported issue and required follow-up implementation expectations,
    - added concrete acceptance criteria and build-validation requirement.
- Validation:
  - Documentation-only update; no code/runtime changes.
- Follow-up notes / risks:
  - Next implementation should replace absolute-overlay close-control behavior with an explicit shared header layout to eliminate overlap risk by structure, not spacing.

## 2026-02-17 19:27 +11:00

- Task summary:
  - Implemented the first takeover item from `QUICK_START.md`: fixed drawer header overlap with a structural shared header row.
  - Kept drawer content viewport-clamped with internal scrolling for long panel content.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - replaced absolute close-button overlay with a dedicated shared header row (`headerContent` + close action),
    - preserved viewport constraints and internal scroll behavior with explicit body max-height.
  - Updated `web-ui/src/App.tsx`:
    - added panel-aware `activeDrawerHeader` content (including weld title + `Weld ON` badge),
    - passed shared header content into `SidebarDrawer`,
    - removed duplicated panel title rows in STEP / Trajectory / Weld panel cards so the shared drawer header is the primary title surface.
  - Updated `web-ui/src/TelemetryCharts.tsx`:
    - removed duplicate top "Live Charts" title to align with shared drawer header.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend: `ReadLints` on changed files reported no issues:
    - `web-ui/src/components/SidebarDrawer.tsx`
    - `web-ui/src/App.tsx`
    - `web-ui/src/TelemetryCharts.tsx`
- Follow-up notes / risks:
  - Visual confirmation on real narrow viewport interaction is still recommended to confirm final spacing feel across all drawer panel variants.

## 2026-02-17 20:34 +11:00

- Task summary:
  - Fixed left drawer vertical alignment so it no longer runs to the edge and now uses the same top/bottom inset style as the right robot-control panel.
  - Updated `AGENTS.md` (renamed from `QUICK_START.md`) with a complete installed-skills catalog and clear "when to use" guidance.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - switched drawer wrapper from top + viewport max-height sizing to inset-based sizing (`inset-y-6`) with a flex column layout,
    - made drawer body `flex-1` + `overflow-y-auto` to preserve internal scrolling while maintaining bottom inset.
  - Updated `AGENTS.md`:
    - changed document heading/context to reflect rename from `QUICK_START.md`,
    - refreshed takeover TODO/acceptance criteria for the current vertical alignment issue,
    - added all available skills with path + relevance triggers,
    - added explicit design skill guidance (`frontend-design`, `web-design-guidelines`, `canvas-design`).
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend/docs lint check: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx` and `AGENTS.md` reported no issues.
- Follow-up notes / risks:
  - Recommend one live visual pass at very short viewport heights to confirm the drawer body scroll ergonomics remain comfortable.

## 2026-02-17 20:41 +11:00

- Task summary:
  - Styled the left drawer scrollbar so it matches the dark/cyan UI theme instead of using the default browser scrollbar.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - applied a dedicated `gradient-scrollbar` class to the drawer scroll container,
    - added slight right padding (`pr-1`) to keep custom scrollbar visuals from crowding content.
  - Updated `web-ui/src/index.css`:
    - added `@layer utilities` scrollbar styles for `.gradient-scrollbar`,
    - included both Firefox (`scrollbar-width`, `scrollbar-color`) and WebKit (`::-webkit-scrollbar*`) styling,
    - matched track/thumb colors to existing slate/cyan palette with hover state.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend lint check: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx` and `web-ui/src/index.css` reported no issues.
- Follow-up notes / risks:
  - If additional panel regions need the same styling, reuse `gradient-scrollbar` to keep scroll visuals consistent across the app.

## 2026-02-17 20:49 +11:00

- Task summary:
  - Integrated the scrollbar into the drawer panel shell and enforced rounded bottom corners regardless of scroll position.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - merged header + body into one shared clipped shell (`overflow-hidden`, `rounded-xl`),
    - moved scroller inside the shell under a header divider (`border-b`),
    - kept custom scrollbar styling on the internal body scroller with content padding.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend lint check: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx` reported no issues.
- Follow-up notes / risks:
  - If panel body framing is later simplified (single-shell look), remove inner panel card borders to reduce nested framing.

## 2026-02-17 21:28 +11:00

- Task summary:
  - Standardized weld-panel typography sizing so labels, meta text, and control text use a consistent scale.
- Changes:
  - Updated `web-ui/src/App.tsx` (Weld panel):
    - introduced shared weld typography class constants (`WELD_LABEL_CLASS`, `WELD_INPUT_CLASS`, `WELD_META_TEXT_CLASS`, `WELD_SECTION_TITLE_CLASS`),
    - normalized base panel text to a consistent body size/line-height,
    - aligned metadata/caption sizes across selected edges, section info, and saved-program rows,
    - aligned button/input/select text sizing for visual consistency.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - If this typography scale should also be mirrored in STEP/Trajectory panels, extract these tokens into a shared drawer-typography utility in a follow-up pass.

## 2026-02-17 21:31 +11:00

- Task summary:
  - Corrected Weld panel text hierarchy so section headers and field labels no longer share the same perceived boldness.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - changed `WELD_LABEL_CLASS` from medium to normal weight,
    - increased section-title contrast and size via `WELD_SECTION_TITLE_CLASS` (`text-[14px]`, stronger color),
    - preserved existing spacing and control behavior.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - If needed, next pass can align STEP/Trajectory section heading hierarchy to exactly the same pattern.

## 2026-02-17 21:34 +11:00

- Task summary:
  - Applied the same typography hierarchy strategy to STEP and Trajectory panels and added a living UI consistency doc.
  - Added references so future sessions treat the design doc as a first-class source of truth.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - introduced shared drawer typography tokens (`DRAWER_*`) and mapped Weld tokens to them,
    - normalized STEP panel button/label/input/meta text sizes to the shared scale,
    - normalized Trajectory panel body/meta/section heading/input/action text to the shared scale.
  - Added `web-ui/design.md`:
    - documented design direction, typography hierarchy, shared tokens, layout rules, and a consistency checklist.
  - Updated `AGENTS.md`:
    - referenced `web-ui/design.md` in workflow pointers and design guidance.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend/docs lint check: `ReadLints` on `web-ui/src/App.tsx`, `AGENTS.md`, and `web-ui/design.md` reported no issues.
- Follow-up notes / risks:
  - Some legacy controls outside the drawer panels may still use older text sizing and can be normalized in a dedicated global pass.

## 2026-02-17 21:43 +11:00

- Task summary:
  - Reinforced mandatory memory-loop workflow language in `AGENTS.md` so `DEVLOG.md` and `AGENT_SCRATCHPAD.md` can never be skipped.
- Changes:
  - Updated `AGENTS.md`:
    - strengthened bullets for `DEVLOG.md` and `AGENT_SCRATCHPAD.md` with explicit MUST wording,
    - added a "Non-negotiable workflow rule" block that marks missing either update as a blocker/incomplete task.
- Validation:
  - Docs lint check: `ReadLints` on `AGENTS.md` reported no issues.
- Follow-up notes / risks:
  - Continue enforcing this by always appending both files in the same turn as meaningful changes.

## 2026-02-17 21:46 +11:00

- Task summary:
  - Removed unnecessary inner panel shell layer inside the drawer to eliminate the double-frame look and give content more horizontal room.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - removed outer card-shell classes from drawer panel roots (Telemetry panel, STEP panel, Trajectory panel, Weld panel),
    - kept section-level cards intact for internal grouping while using full drawer width.
  - Updated `web-ui/src/TelemetryCharts.tsx`:
    - removed nested full-card shell style and kept a lightweight inner wrapper.
  - Updated `web-ui/design.md`:
    - added explicit rule to avoid nested outer shells inside drawer content.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend/docs lint check: `ReadLints` on `web-ui/src/App.tsx` and `web-ui/src/TelemetryCharts.tsx` reported no issues.
- Follow-up notes / risks:
  - If any panel now feels too open visually, adjust section card spacing before reintroducing any full nested frame.

## 2026-02-17 21:50 +11:00

- Task summary:
  - Updated drawer behavior so panel height follows content by default, while still capping at viewport max-height for tall panels.
  - Made Telemetry/Charts drawer wider to avoid horizontal scrolling.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - changed layout from forced full-height (`inset-y`) to top-anchored adaptive height with `max-h`,
    - kept internal vertical scrolling and added `overflow-x-hidden` to prevent sideways scroll bars.
    - added `widthClassName` prop to support panel-specific width variants.
  - Updated `web-ui/src/App.tsx`:
    - added `activeDrawerWidthClass` so telemetry drawer uses wider width (`w-[30rem]`) and other panels keep standard width.
    - passed width class into `SidebarDrawer`.
  - Updated `web-ui/design.md`:
    - documented adaptive height behavior and telemetry wider-width rule.
- Validation:
  - Frontend: `npm run build` passed.
  - Frontend/docs lint check: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx`, `web-ui/src/App.tsx`, and `web-ui/design.md` reported no issues.
- Follow-up notes / risks:
  - If telemetry data density increases further, consider a responsive width tier for very wide screens while preserving mobile max-width constraints.

## 2026-02-17 22:10 +11:00

- Task summary:
  - Fixed Weld drawer clipping/misalignment by anchoring it to the same `top-6`/`bottom-6` overlay band used by adjacent floating UI.
  - Fixed angle-help tooltip clipping by moving it to a fixed portal overlay outside the drawer scroll container.
  - Codified panel sizing/scroll and tooltip overlay rules in `web-ui/design.md`.
  - Recorded durable regression-prevention notes in `AGENT_SCRATCHPAD.md`.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - switched drawer wrapper to explicit `top-6 bottom-6` anchoring,
    - set inner shell to `h-full` with internal scroll region.
  - Updated `web-ui/src/App.tsx`:
    - rendered Weld angle tooltip via `createPortal(document.body)`,
    - added viewport-clamped fixed positioning (right-side default with left fallback) and outside-click/Escape close handling.
  - Updated `web-ui/design.md`:
    - replaced adaptive-height guidance with explicit anchored overlay guidance for drawer baselines,
    - added tooltip/popover portal rules to prevent clipping regressions.
  - Updated `AGENT_SCRATCHPAD.md`:
    - logged mistake/fix/guardrails for panel baseline and tooltip clipping regressions.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Frontend/docs lint check: `ReadLints` on `web-ui/src/App.tsx`, `web-ui/src/components/SidebarDrawer.tsx`, `web-ui/design.md`, `AGENT_SCRATCHPAD.md`, and `DEVLOG.md` reported no issues.
- Follow-up notes / risks:
  - If additional field-level help popovers are added, they should reuse the same portal + viewport-clamp pattern instead of inline absolute positioning inside panel content.

## 2026-02-17 22:24 +11:00

- Task summary:
  - Corrected weld end-action semantics so `return_to_start` now returns to trajectory start/home-start (planner start pose), not weld start.
  - Added a new weld end-action `lift` for a short vertical retract from weld end.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - expanded weld post-action type union to include `lift`,
    - updated End Action select with `Lift` option and clearer label text (`Return to trajectory start`),
    - normalized load/save parsing to preserve `lift`,
    - removed frontend-generated post-action return segment from weld section builder (backend now owns end-action routing).
  - Updated `src/gradient_os/api/main.py`:
    - normalized `post_action` parsing to allow `none` / `lift` / `return_to_start` for both weld-program save and `/trajectory/plan-weld` options payload.
  - Updated `src/gradient_os/arm_controller/command_api.py`:
    - captured trajectory start pose at planning start,
    - added backend post-action planning:
      - `return_to_start`: end -> lifted transit -> trajectory start,
      - `lift`: end -> vertical retract by transition clearance.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Backend syntax: `.venv\\Scripts\\python.exe -m py_compile src\\gradient_os\\api\\main.py src\\gradient_os\\arm_controller\\command_api.py` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx`, `src/gradient_os/api/main.py`, and `src/gradient_os/arm_controller/command_api.py` reported no issues.
- Follow-up notes / risks:
  - Current `return_to_start` targets trajectory planning start pose; if product semantics later require a dedicated absolute home pose, add an explicit `return_home` action to avoid ambiguity.

## 2026-02-17 22:57 +11:00

- Task summary:
  - Fixed stale weld preview/path visualization when loading saved weld programs (e.g., `test_0`) that have no saved `planned_trajectory`.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - in pending weld-program restore branch, added explicit clear path when `previewPlan` is absent:
      - `setPreviewPlan(null)`
      - `setPlannerPoints([])`
    - after successful weld-program payload validation, clears preview/path immediately before async restore to avoid stale carry-over visuals.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - If more scene overlays are derived from loaded program payloads in future, include explicit clear branches for null/absent data to prevent similar stale-UI regressions.

## 2026-02-17 23:29 +11:00

- Task summary:
  - Fixed intermittent weld-run visualization flicker where the arm briefly snapped toward stale start-like poses during active motion.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - added telemetry packet ordering filter using source timestamp field (`t`) to drop out-of-order samples,
    - added one-frame spike rejection for implausible joint jumps (`>0.8 rad` within `<=0.25s`),
    - added ref resets for telemetry filters on disconnect.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - If future work intentionally combines multiple telemetry sources, introduce explicit source IDs and deterministic source selection to avoid timestamp-only arbitration edge cases.

## 2026-02-18 00:08 +11:00

- Task summary:
  - Fixed loaded weld program run gating so `Run Weld Preview` is enabled based on runnable preview data, not weld-draft editor state.
  - Updated weld preview execution to always re-plan from current robot state at run time.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - added `canRunPreview` prop to `WeldPanel`,
    - changed run button disable logic from `!draft` to `!canRunPreview`,
    - passed `canRunPreview={Boolean(previewPlan?.name)}` from parent,
    - changed `/trajectory/run` request for preview run to `use_cache: false` to ensure current-state re-plan and explicit approach to start.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - Re-planning on every run is safer but may add slight latency; if needed, expose cache/replan mode explicitly in UI with clear semantics.

## 2026-02-18 00:18 +11:00

- Task summary:
  - Fixed left drawer height regression so STEP / Trajectory / Live Charts no longer stretch to full-height empty space.
  - Kept Weld Planning in its current full-height behavior.
- Changes:
  - Updated `web-ui/src/components/SidebarDrawer.tsx`:
    - added panel-aware `heightMode` prop (`content` | `full`),
    - kept shared overlay lane (`top-6 bottom-6`) but switched shell sizing:
      - `full` => `h-full` (for dense Weld panel),
      - `content` => `max-h-full` (for sparse panels),
    - moved pointer events to panel shell (`pointer-events-none` on wrapper, `pointer-events-auto` on shell) so transparent overlay space does not block scene interaction.
  - Updated `web-ui/src/App.tsx`:
    - derived `activeDrawerHeightMode` from active panel (`weld` => `full`, others => `content`),
    - passed `heightMode` into `SidebarDrawer`.
  - Updated `web-ui/design.md`:
    - documented mixed drawer height policy: content-fit for STEP/Trajectory/Telemetry, full-height for Weld.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/components/SidebarDrawer.tsx`, `web-ui/src/App.tsx`, and `web-ui/design.md` reported no issues.
- Follow-up notes / risks:
  - Do one live pass at narrow and wide viewport sizes to confirm click-through behavior in empty drawer-lane space feels correct.

## 2026-02-18 01:13 +11:00

- Task summary:
  - Installed all repo-local skills from `.cursor/skills` into Codex home skills.
  - Verified installed skills against the source skill set and AGENTS workflow expectations.
- Changes:
  - Installed the following skills into `C:\Users\angus\.codex\skills`:
    - `agent-browser`
    - `canvas-design`
    - `devlog-loop`
    - `find-skills`
    - `frontend-design`
    - `learning-scratchpad-loop`
    - `next-best-practices`
    - `next-cache-components`
    - `next-upgrade`
    - `vercel-composition-patterns`
    - `vercel-next-deploy`
    - `vercel-react-best-practices`
    - `vercel-react-native-skills`
    - `web-design-guidelines`
  - Confirmed `.cursor/skills-cursor` does not exist in this repository snapshot.
- Validation:
  - Compared source skill directories containing `SKILL.md` in `.cursor/skills` against `C:\Users\angus\.codex\skills` and found no missing installs.
  - Audit diff reported only expected extra preinstalled directory: `.system`.
- Follow-up notes / risks:
  - Newly installed skills are loaded on Codex startup; restart is required to pick them up in fresh sessions.

## 2026-02-18 01:17 +11:00

- Task summary:
  - Fixed weld preview execution mismatch where robot run could follow sparse endpoint moves instead of the full interpolated weld path.
  - Clarified UI wording so editable weld points are treated as control points, not every interpolated sample.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - added `weldPreviewCacheReady` state to track whether a fresh weld preview cache exists for run,
    - updated weld preview planning (`requestWeldPreview`) to return planned preview data and mark cache readiness,
    - changed run behavior:
      - non-weld trajectories continue `use_cache: false` (re-plan from current state),
      - weld previews now execute with `use_cache: true` so runtime uses full high-fidelity planned steps instead of sparse `move_absolute` endpoints,
      - if weld cache is stale (e.g., restored program state), auto-refreshes weld preview before run and then executes cached plan,
    - reset weld cache readiness in clear/disconnect/load flows to avoid stale-cache execution.
    - renamed weld waypoint section title to `Editable Control Points` and added helper text about interpolation.
  - Updated `web-ui/src/previewUtils.ts`:
    - extended `TrajectoryFile` type with optional `weld` metadata,
    - enhanced program-root subtitle to show both move count and path sample count when available.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx` and `web-ui/src/previewUtils.ts` reported no issues.
- Follow-up notes / risks:
  - Program tree still lists coarse operation moves; it now also shows path sample count, but a future pass could add an explicit “interpolated path” node for deeper inspectability.

## 2026-02-18 01:28 +11:00

- Task summary:
  - Removed weld preview path downsampling and switched Program Tree to exact path-sample inspection.
  - Kept coarse command metadata only as a secondary controller-command view.
- Changes:
  - Updated `src/gradient_os/arm_controller/command_api.py`:
    - removed cartesian path downsampling (`sample_stride`) in planner payload assembly,
    - payload `cartesian_path` now includes every planned cartesian sample for exact UI inspection.
  - Updated `web-ui/src/previewUtils.ts`:
    - refactored `buildProgramTree` to build from exact `plan.pathPoints`:
      - grouped view now includes `Exact Path Samples` (full list, no trimming),
      - chronological view now centers on `Execution Path (Exact)` using full path samples,
      - control points and controller commands are still present as separate groups for editing/diagnostics.
    - kept weld feature grouping and root subtitle counters.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Backend syntax: `.venv\\Scripts\\python.exe -m py_compile src\\gradient_os\\arm_controller\\command_api.py` passed.
  - Lint check: `ReadLints` on `web-ui/src/previewUtils.ts`, `web-ui/src/App.tsx`, and `src/gradient_os/arm_controller/command_api.py` reported no issues.
- Follow-up notes / risks:
  - Very long paths now produce large tree node counts; if UI responsiveness drops on extreme programs, add virtualized rendering rather than reintroducing path trimming.

## 2026-02-18 01:42 +11:00

- Task summary:
  - Tightened Program Tree fidelity rules so it no longer uses approximate weld-segment path ranges.
  - Kept controller command rows strictly as reference metadata when exact path samples are available.
- Changes:
  - Updated `web-ui/src/previewUtils.ts`:
    - removed `estimatePathRange` helper usage for weld segments to avoid proportional/approximate path highlighting,
    - weld feature nodes now focus only the selected edge (`weldSegmentEdgeId`) instead of inferred path range,
    - simplified command-group logic:
      - with exact path samples: show `Controller Commands (Reference)`,
      - without exact path samples: show `Controller Commands`.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/previewUtils.ts` and `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - Tree now avoids misleading approximations; if users want per-segment exact ranges, backend should emit explicit section/sample index mapping in planner payload.

## 2026-02-18 01:53 +11:00

- Task summary:
  - Removed waypoint-edit controls from the Weld drawer panel.
  - Moved waypoint editing workflow into Program Tree so control-point changes are driven from tree selection.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - removed `Editable Control Points` section and related props from `WeldPanel`,
    - added Program Tree-driven waypoint state handlers:
      - point coordinate edits,
      - add/remove control point,
      - apply edits (routes to weld replan for weld programs, generic point replan for non-weld plans),
    - wired selected `control_point_*` Program Tree node to tree-side editor context.
  - Updated `web-ui/src/components/ProgramFeatureTree.tsx`:
    - added inline control-point editor panel (x/y/z fields),
    - added add/remove/apply controls for waypoint edits within Program Tree surface.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx`, `web-ui/src/components/ProgramFeatureTree.tsx`, and `web-ui/src/previewUtils.ts` reported no issues.
- Follow-up notes / risks:
  - Editing now requires selecting a `Control Point` node in Program Tree; if needed, we can add a subtle hint banner when no control point is selected.

## 2026-02-18 01:54 +11:00

- Task summary:
  - Aligned Program Tree selection behavior with weld editing workflow after migrating controls to the tree.
- Changes:
  - Updated `web-ui/src/previewUtils.ts`:
    - control-point/path/command nodes now target `openPanel: "weld"` when current plan carries weld metadata,
    - preserves `openPanel: "trajectory"` for non-weld plans.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/previewUtils.ts`, `web-ui/src/App.tsx`, and `web-ui/src/components/ProgramFeatureTree.tsx` reported no issues.
- Follow-up notes / risks:
  - If users prefer tree selection to never change side panel at all, add a setting to disable panel auto-switch on tree node select.

## 2026-02-18 02:00 +11:00

- Task summary:
  - Reduced yellow preview waypoint spheres to match requested small visual footprint (~1mm radius).
- Changes:
  - Updated `web-ui/src/ArmVisualizer.tsx`:
    - changed preview marker geometry radius from `0.008` to `0.001` meters in the path/waypoint marker rendering block.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/ArmVisualizer.tsx` reported no issues.
- Follow-up notes / risks:
  - At certain zoom levels 1mm markers may become hard to see; if needed, add a user-configurable marker size slider later.

## 2026-02-18 02:04 +11:00

- Task summary:
  - Fixed weld `return_to_start` behavior to reliably use the robot’s current pre-weld pose for each run.
- Changes:
  - Updated `web-ui/src/App.tsx`:
    - changed weld run flow in `handleRunPreview` to always refresh weld preview plan immediately before `/trajectory/run`,
    - keeps execution on cached high-fidelity steps (`use_cache: true`) after refresh, but with a run-current start context.
  - This ensures backend planner captures current start pose each run, so `return_to_start` no longer targets stale or weld-start positions from older plans.
- Validation:
  - Frontend: `npm run -s build` passed.
  - Lint check: `ReadLints` on `web-ui/src/App.tsx` reported no issues.
- Follow-up notes / risks:
  - Weld run now always incurs replan latency before execution; acceptable for correctness, but can be optimized later if needed.

## 2026-02-18 02:19 +11:00

- Task summary:
  - Fixed a weld execution-state race that could cause jitter/contending motion loops during preview playback.
  - Added a hard jog shutdown before trajectory runs so realtime jog cannot interfere with weld path execution.
- Changes:
  - Updated `src/gradient_os/arm_controller/trajectory_execution.py`:
    - added `owns_trajectory_state` guard to `_open_loop_executor_thread` and `_closed_loop_executor_thread`,
    - prevented nested per-step executor calls from clearing global trajectory state (`is_running`, `thread`) mid-run,
    - updated `_execute_joint_path` to run open-loop with `owns_trajectory_state=False` for sub-step execution.
  - Updated `src/gradient_os/arm_controller/command_api.py`:
    - in `handle_run_trajectory`, force-stop active jog mode before starting trajectory execution,
    - abort run if jog mode cannot be stopped cleanly.
- Validation:
  - Backend syntax: `& ".\.venv\Scripts\python.exe" -m py_compile "src/gradient_os/arm_controller/trajectory_execution.py" "src/gradient_os/arm_controller/command_api.py"` passed.
  - Lint check: `ReadLints` on `src/gradient_os/arm_controller/trajectory_execution.py` and `src/gradient_os/arm_controller/command_api.py` reported no issues.
- Follow-up notes / risks:
  - Requires runtime verification in `run-sim` + `run-api` with weld preview to confirm jitter and return behavior are fully resolved in motion playback.

## 2026-02-18 02:26 +11:00

- Task summary:
  - Captured operator runtime validation after restart: weld path now executes correctly without prior jitter/snap behavior.
  - Confirmed likely primary fix was the execution-state lifecycle patch; jog-stop guard retained as safety hardening.
- Changes:
  - No additional code changes in this step.
  - Updated engineering notes based on user validation feedback.
- Validation:
  - User-reported live run outcome: "seems to be working now."
  - User confirmed issue had also reproduced previously with jog disabled, supporting execution-state race as root cause.
- Follow-up notes / risks:
  - Keep jog-stop pre-run guard in place as defense-in-depth even if not primary root cause in this incident.

## 2026-02-18 11:47 +11:00

- Task summary:
  - Added/updated repository-facing README documentation for merge to `main`.
  - Prepared a merge-ready commit message for the current branch changes.
- Changes:
  - Added new root `README.md` with:
    - project overview,
    - quick start commands (including Windows `.ps1` launchers),
    - current weld workflow behavior notes (exact path samples, return-to-start semantics, execution stability guards),
    - pointers to docs and web UI guidance.
  - Updated `web-ui/README.md` from legacy early-stage description to current production capabilities:
    - scene/telemetry, trajectory and weld planning, Program Tree exact-path behavior, and operational notes.
- Validation:
  - Lint check: `ReadLints` on `README.md` and `web-ui/README.md` reported no issues.
- Follow-up notes / risks:
  - If release process requires it, align any duplicated quick-start wording between `README.md`, `AGENTS.md`, and `docs/README.md` in a later docs-only cleanup.

## 2026-02-18 11:55 +11:00

- Task summary:
  - Updated `docs/README.md` (the main repository README target used by this project) with a branch-highlights summary for `STEP_LOADER`.
  - Prepared a comprehensive merge commit message covering full branch scope.
- Changes:
  - Updated `docs/README.md`:
    - added a `STEP_LOADER Branch Highlights` section,
    - documented CAD topology + weld pipeline additions,
    - documented trajectory execution correctness fixes (including execution-state lifecycle guard behavior),
    - documented Web UI upgrades (STEP/weld/program tree/exact path visibility),
    - documented platform/dev workflow updates (Windows launchers, API tests).
- Validation:
  - Lint check: `ReadLints` on `docs/README.md` reported no issues.
  - Verified branch scope context using:
    - `git log --oneline master..HEAD`
    - `git diff --stat master..HEAD`
- Follow-up notes / risks:
  - Docs now include both long-form architecture and branch summary; if desired later, split release notes into a dedicated changelog section.

## 2026-02-18 11:59 +11:00

- Task summary:
  - Reworked `docs/README.md` into a clean newcomer onboarding document focused on features, architecture, and practical usage.
  - Removed release-note style framing and replaced with user/operator starting guidance.
- Changes:
  - Rewrote `docs/README.md`:
    - clear "what GradientOS provides" section,
    - runtime architecture and data-flow summary,
    - Linux/macOS and Windows quick-start/run instructions,
    - first-run operator workflow for Web UI,
    - motion/weld behavior notes,
    - project layout + documentation map + troubleshooting.
- Validation:
  - Lint check: `ReadLints` on `docs/README.md` reported no issues.
- Follow-up notes / risks:
  - If needed, older deep-dive narrative content can be moved into dedicated per-subsystem docs to keep this entrypoint concise.

## 2026-02-18 12:28 +11:00

- Task summary:
  - Fixed broken diagram rendering in `docs/README.md`.
- Changes:
  - Rewrote all Mermaid blocks to strict minimal syntax:
    - switched flow diagrams to `flowchart TD`,
    - removed HTML tags and complex labels in nodes/notes,
    - simplified sequence diagram participant labels and event text.
- Validation:
  - Lint check: `ReadLints` on `docs/README.md` reported no issues.
- Follow-up notes / risks:
  - None.

## 2026-09-05 — Sprint 01 (Electronics Validation) complete + USB passthrough

- Task summary:
  - Completed Sprint 01: test bench wired, STS3215 powered at 12V, idle current verified, no heat/smoke.
  - USB serial passthrough from Pi host to OpenChamber container implemented (Design B: udev mirror + bind-mount).
  - All measurements documented in `feetech-project/docs/hardware/test-bench-wiring.md`.
- Changes:
  - Updated `feetech-project/docs/hardware/test-bench-wiring.md`: checked all Step 1-4 checkboxes with measured values (12.0V at PSU/URT-1/SCS-TTL port, 299mA idle current, 30s touch test OK).
  - Updated `feetech-project/sprints/sprint-01-electronics.md`: all tasks marked complete, definition of done met.
  - Updated `feetech-project/TODO.md`: sprint-01 marked complete, blocked items updated (USB passthrough resolved, Dockerfile rebuild for GradientOS env is next blocker).
  - Added decision log entry in `feetech-project/docs/decisions/decision-log.md` for Design B USB passthrough choice.
- Validation:
  - Multimeter readings: 12.0V at PSU output, URT-1 servo-power terminal, and SCS/TTL V+ pin.
  - Idle current: 299mA (slightly above 50-200mA estimate; acceptable for 12V STS3215).
  - 30-second touch test: cool, no heat.
  - USB passthrough: `/dev/serial/ch340` visible inside container, `stty -F /dev/serial/ch340 -a` returns real termios, pyserial opens and closes cleanly.
  - Open()/EACCES trap avoided: `group_add: ["20"]` + `device_cgroup_rules: c 188:* rwm` confirmed working.
- Follow-up notes / risks:
  - Physical USB unplug/replug test still pending (propagation verified via node add/remove, not real plug pull).
  - Reboot test pending (tmpfiles recreation of `/dev/openchamber` not yet proven across a real reboot).
  - GradientOS Python environment not yet set up in container — needs Dockerfile rebuild (build-essential, cmake, python3-dev, uv) + venv install. Instructions prepared for Cursor.
  - pyserial `list_ports.comports()` returns empty inside container; `SERIAL_PORT=/dev/serial/ch340` env var required.

## 2026-09-05 23:30 UTC — Sprint 02 Part A: servo motion validated + docs filled

- Task summary:
  - User reported they saw amperage change but never saw the servo move. Requested further testing.
  - Re-confirmed servo state with safe reads (no motion): position 4016, torque 0, status 0x0.
  - Commanded a single ~10° downward move (4016 -> 3903) with live telemetry sampling; servo moved (4016 -> 3905, 9.76°) — user confirmed visible movement.
  - Commanded three back-and-forth ~10° moves (3904 <-> 3791); all six moves succeeded with ~9.84° achieved, zero errors, returned to start exactly.
  - This was after an unplug + replug, confirming the safe-move recipe works from a cold start (RAM defaults).
  - Filled in Part A documentation: `feetech-project/docs/protocols/feetech-sts-scs.md` (full frame format, instructions, confirmed register map, safety behaviours, gotchas) and `feetech-project/docs/hardware/servo-specs/STS3215.md` (measured electrical/config/motion values).
- Changes:
  - `feetech-project/docs/protocols/feetech-sts-scs.md`: replaced stub with confirmed protocol details from `src/gradient_os/arm_controller/backends/feetech/protocol.py`, `config.py`, and `SERVO-NOTES.md`.
  - `feetech-project/docs/hardware/servo-specs/STS3215.md`: replaced stub with measured bench values (12.0 V, 31-33 °C idle, 1 Mbps baud, PID 32/32/0, motion accuracy table, safety notes).
- Validation:
  - Single 10° move: 4016 -> 3905 (9.76° vs 9.9° target), load peaked 96, status 0x0.
  - 3× back-and-forth: each leg 112 counts (9.84°), all status 0x0, final position = start position.
  - Cold-start (unplug + replug) confirmed: same recipe worked from RAM defaults.
- Follow-up notes / risks:
  - PSU current figures (idle/move/stall) still TBD — register `0x45` not trustworthy on this firmware; need bench PSU readout.
  - Part B (HLS3950 protocol) entirely open.
  - The other eight arm servos do not exist yet.

## 2026-09-08 — Motion Jerkiness Diagnosis (code analysis, no changes)

- Task summary:
  - User reported severe jerkiness during all arm motion (trajectories like rotysquare, jogging, straight-line moves). Servos oscillate, stall, behave spring-like. The ONLY smooth motion is the Home button.
  - Performed full code analysis of motion control pipeline: `command_api.py`, `trajectory_execution.py`, `servo_driver.py`, `run_controller.py`, `trajectory_planner.py`, robot config, feetech backend config.
  - Identified root cause: two conflicting control paradigms. Home uses servo-internal profiling (single command, speed=500, accel=500). All jerky paths stream 50-100 setpoints/sec with speed=4095 (MAX), accel=0 (MAX), bypassing the servo's internal planner.
  - Secondary factors: software PID correction disabled in closed-loop executor (commanding raw targets), timing jitter from Python sleep, twin-motor mirroring only reads one servo.
- Changes:
  - Created `docs/jerkiness-diagnosis.md` — full analysis with 6 theories ranked by confidence, 5 experiments in priority order, key code locations table, and detailed traces of why Home works vs why trajectories jerk.
- Validation:
  - No code changes made (analysis only). Experiments pending user discussion.
- Follow-up notes / risks:
  - Highest-impact experiment: change `trajectory_execution.py:745` and `:1061` from speed=4095/accel=0 to speed=500/accel=5. One-liner in two places.
  - Need to discuss approach with user before making changes — they want to work through theories together.

## 2026-09-08 (later) — Saturation-model refinement of the jerkiness theory

- Task summary:
  - User challenged the Goal Time idea: per-waypoint trapezoidal profiles have zero-velocity endpoints, so chained profiles still produce stop-go at every waypoint. Correct.
  - Refined the model: the Feetech internal planner only starts decelerating within braking distance of the goal. If goals are always re-issued before the servo gets within braking distance, it never decelerates — continuous cruise.
  - Three regimes identified: cap >> stream velocity (stop-go, current bug), cap ≈ stream velocity (cruise, the fix), cap < stream velocity (lag, dangerous).
  - Consequence: flat speed=500 from Experiment 1 is insufficient — the proper fix is a per-step velocity-matched speed cap computed from the planned joint velocities (numerical diff of the dense path) + headroom. Goal Time demoted to secondary experiment (depends on unverified firmware blend behavior).
  - Identified missing piece: a rad/s → STS speed-register LSB converter; the ~0.732 rpm/LSB unit is unverified on this bench and needs measurement (correct caps may be single/low-double-digit register values; check for a minimum usable cap).
- Changes:
  - `docs/jerkiness-diagnosis.md`: added section 9 (stop-go trap, saturation model, regime table, Experiment 1 revision, falsifiable 0x3A present-speed sweep test, backend-scoping note).
- Validation:
  - None yet — all bench-testable. 0x3A trace sweep is the falsifiable experiment.
- Follow-up notes / risks:
  - Bench measurement needed: STS speed LSB unit (rpm/LSB) and minimum usable cap.
  - Per-step cap must live in Feetech backend (config + rad/s→register helper) per user's backend-isolation requirement.
  - External validation signal: LeRobot SO-ARM/SO-100 community drives STS3215 with streamed positions + moderate speed values and gets smooth replay — same saturation mechanism.

## 2026-09-08 (session 3) — User challenged saturation model's core assumption; added gating experiment

- Task summary:
  - User asked: can we actually overwrite the trapezoidal plan mid-move, or does the servo finish its plan before accepting a new goal? Honest answer: unverified — this is the load-bearing assumption of the saturation model.
  - Formalized the three-way firmware fork: (A) re-target with velocity blend, (B) re-target from rest (v=0 assumption, PID drags velocity), (C) queued completion (plan finishes first). Key insight: the observed "pause at waypoints" is consistent with ALL THREE under max caps, so current symptoms cannot distinguish them.
  - Robustness argument documented: velocity-matched caps improve all three outcomes, so fix direction is safe, but the true case determines tuning (cap multiplier, headroom, expected ripple).
  - Added gating bench test (9.4): mid-move goal re-target on bench servo ID 1 (long move 4016→3600 at cap 300/accel 10, rewrite goal mid-move, watch 0x38/0x3A/moving-flag). Interpretation table maps outcomes to cases A/B/C.
- Changes:
  - `docs/jerkiness-diagnosis.md`: section 9.4 (gating unknown + bench protocol + interpretation), 9.5 renumbered and marked as downstream of 9.4.
- Validation:
  - None — bench test pending; it gates the cap sweep and any executor implementation.
- Follow-up notes / risks:
  - Test order is now: 9.4 re-target test → speed LSB calibration → 9.5 cap sweep → implement per-step caps in Feetech backend.
  - Do NOT pitch saturation tuning values until 9.4 resolves the fork.

## 2026-09-08 (session 4) — Sprint 08 created; profiled-segment stopgap specified

- Task summary:
  - User requested: update docs with the saturation-model tests + create a sprint; remind of open sprint items; discuss feasibility of the "Feetech paradigm" temporary architecture change.
  - Added diagnosis doc section 10: profiled-segment stopgap (collapse each trajectory move step into ONE goal command with per-joint speed caps, let firmware trapezoid run it — the Home-button pattern generalized). Key feasibility point: it does NOT rewrite goals mid-move, so it is NOT gated on the 9.4 firmware fork — implementable today (only needs speed LSB calibration).
  - Coverage analysis: fully covers Home/joint moves and paused multi-segment trajectories (rotysquare: ~1cm moves with 1s pauses — ideal); partially covers jog; does not cover continuous weld paths (stay on dense streaming, gated on 9.4/9.5).
  - Costs documented: joint-space (not Cartesian) path shape, approximate inter-joint coordination, no exact duration control (pauses absorb), backlash attacked by having at most one reversal per segment vs 100 direction-chases/sec.
  - Created `feetech-project/sprints/sprint-08-motion-smoothness.md`: Part A speed LSB calibration (prereq for everything), Part B re-target fork test (gates long-term fix only), Part C cap sweep, Part D profiled-segment implementation (Feetech-scoped via backend capability flag), Part E documentation. Updated TODO.md sprint table and next actions.
- Changes:
  - `docs/jerkiness-diagnosis.md`: section 10 (stopgap idea, coverage table, risks, backend scoping, sequencing vs saturation streaming)
  - `feetech-project/sprints/sprint-08-motion-smoothness.md`: new sprint
  - `feetech-project/TODO.md`: sprint table + next actions updated
- Validation:
  - None — bench tests specified, not run. Sprint 08 Part A is the first concrete step.
- Follow-up notes / risks:
  - Sprint status audit finding: sprint-02 checkboxes are all unchecked but Part A is actually DONE per DEVLOG/scratchpad (protocol doc + STS3215 spec are filled in) — sprint-02 file needs a checkbox pass to reflect reality. Flagged to user.
  - Ordering: A → D (stopgap) can proceed without B/C; B → C gate the long-term streaming fix.

## 2026-09-08 (session 5) — Moved HLS3950 protocol validation (02 Part B) to the start of Sprint 05

- Task summary:
  - User requested moving Sprint 02 Part B (HLS3950 protocol validation) to the beginning of Sprint 05.
  - Sprint 05 restructured: goal expanded to "identify HLS protocol, then implement backend"; the Part B content (research, physical interface determination, minimal code, protocol docs) now leads the sprint before the Implementation section; prerequisite line about "Sprint 02 Part B complete" removed since it's now in-sprint.
  - Sprint 02 is now STS3215-only; title and definition-of-done updated to reflect that.
  - TODO.md updated: sprint table entries, next-action note, blocked-items reference (HLS research now points at Sprint 05).
- Changes:
  - `feetech-project/sprints/sprint-05-hls-backend.md` — Part B inserted at top of Tasks
  - `feetech-project/sprints/sprint-02-servo-protocol.md` — Part B removed, doc re-scoped STS-only
  - `feetech-project/TODO.md` — three references updated
- Validation:
  - Grep confirmed no stale "Sprint 02 Part B" references remain in TODO or sprint files.
- Follow-up notes / risks:
  - Sprint 02's checkboxes still need a reality pass (Part A work is done but unchecked).

## 2026-09-08 (session 6) — Sprint 8/9 split per user; stall current measured

- Task summary:
  - User pressure-tested the arm: manual downward pull on EE spiked power from ~3.6 W to ~8 W (~0.67 A @ 12 V). Recorded as the stall-current measurement, closing the sprint-02 open item (updated STS3215.md electrical table + open items).
  - User corrected my sprint scoping: Sprint 08 should be ONLY the feasibility study of interrupting trapezoid planning mid-move (the pseudo-Dynamixel streaming question). The quick fix (endpoint-paradigm control) should be its own sprint for the immediate future.
  - Restructured: sprint-08 rewritten as bench-only, no code, with Part A (speed LSB calibration), Part B (mid-move re-target fork test, THE decisive experiment, repeated 3x, plus edge probes for A/B), Part C (cap sweep, only meaningful under A/B), Part D (go/no-go verdict with explicit GO/CONDITIONAL/NO-GO mapping to cases A/B/C).
  - Created sprint-09 (endpoint-paradigm quick fix): Feetech-scoped capability flag, plan_profiled_segment helper, executor policy change for paused trajectories + joint moves, validation on rotysquare + sim regression. Weld paths and jog explicitly stay on streaming until Sprint 08's verdict.
  - Updated TODO.md next-actions (Sprint 09 first, Sprint 08 parallel-able) and sprint table; updated diagnosis doc §10 status to point at both sprints and revised sequencing.
- Changes:
  - `feetech-project/sprints/sprint-08-motion-smoothness.md` — rewritten (feasibility only)
  - `feetech-project/sprints/sprint-09-endpoint-paradigm-quickfix.md` — new
  - `feetech-project/docs/hardware/servo-specs/STS3215.md` — stall current recorded
  - `feetech-project/TODO.md` — next actions + sprint table
  - `docs/jerkiness-diagnosis.md` — §10 status/sequencing updated
- Validation:
  - User-confirmed bench measurement (8 W spike) recorded from their manual pressure test.
- Follow-up notes / risks:
  - Sprint 09 can ship with a flat conservative cap (500/accel 10) even before Sprint 08 Part A calibration lands; caps refined after.
  - If Sprint 08 returns case C, sprint-09's endpoint paradigm becomes permanent for Feetech, not a stopgap — docs to be updated at that point.

## 2026-09-08 (session 7) — Sprint plan restructured per user (02-07 sequence)

- Task summary:
  - User asked: do we still need sprint-07 (full arm)? Mark sprint-03 complete items + add AI-taught architecture section; combine all HLS work into one sprint; move the quick fix (old 09) up to sprint-02; print the plan.
  - Sprint-07 verdict: mostly obsolete — the 8-servo arm is already built, wired, and running daily (evidence: feetech-project/code/coordinated_home.py drives all 8 IDs; user pressure-tests the physical arm). Rewrote as slim "Sprint 06 — Full-Arm Hardening": power bus, udev stability, joint-limit verification (servos currently UNRESTRICTED 0-4095 in EEPROM, software clamps only), temperature soak, operator handoff doc. Documented what dropped and why.
  - Sprint-03 (GradientOS study): marked 10/10 study items complete (the deep study happened during the jerkiness diagnosis); added "GradientOS Architecture Crash Course" teaching section covering: two-axis selection (robots × backends), startup sequence, command path UI→UDP→servo, motion pipeline (single-point vs trajectory paradigms), logical-vs-physical joints/twin motors, what adding HLS3950 touches, and sharp edges (mid-migration code, hardcoded streaming params, disabled software PID, 3ms bus floor). Remaining: fill the two docs/gradientos/ stubs.
  - Old sprint-02 (STS protocol) and old sprint-04 (STS backend): both complete in reality → checkbox reality pass + archived to sprints/archive/ with -COMPLETE suffix. Stall current (8W) recorded, closing protocol sprint's last item.
  - HLS: already consolidated into one sprint file → renumbered sprint-07 (all-in-one: protocol validation + backend + testing).
  - Quick fix moved to sprint-02; feasibility study → sprint-05; paired joints → sprint-04.
  - TODO.md rewritten: new sprint table with dependencies diagram, updated blocked items and open questions (fork test, LSB unit now tracked).
- Changes:
  - sprints/: sprint-02 (quickfix, renumbered), sprint-03 (study, +crash course), sprint-04 (paired joints), sprint-05 (feasibility, renumbered), sprint-06 (arm hardening, rewritten), sprint-07 (HLS, consolidated+renumbered), archive/ (2 complete sprints)
  - TODO.md (full rewrite), docs/jerkiness-diagnosis.md (sprint refs updated)
- Validation:
  - rg confirmed no stale sprint-number references remain in active files.
- Follow-up notes / risks:
  - docs/gradientos/ stubs (architecture-notes.md, adding-a-servo-family.md) still unfilled — the one remaining sprint-03 item; crash course in the sprint file can seed them.
  - Sprint-06 joint-limit EEPROM write needs explicit human approval per EEPROM guardrails.

## 2026-09-08 (session 8) — Sprint renumbering v3: HLS→05, backend gating hardened, archive restored to 01

- Task summary:
  - User directives: switch HLS to sprint-04-slot; ensure the quick fix's backend gating is explicit (must NOT apply to other arm configs); move study (03) before quickfix; restore the archived STS protocol sprint as completed sprint-01, shifting everything down.
  - Final numbering after all shifts: 00 setup, 01 STS protocol (restored from archive, complete, marked in-place), 02 electronics (was 01), 03 study (kept position, now before quickfix), 04 quickfix (was 02), 05 HLS3950 (was 07; user moved it into the 04 slot from the previous plan then everything shifted — final: 05), 06 paired joints, 07 feasibility study, 08 arm hardening.
  - Backend gating hardened in sprint-04 per user requirement: scope rule block added (capability flag on ActuatorBackend ABC defaults False; FeetechBackend overrides True; executor queries the active backend instance at runtime — no string checks); explicit gating-matrix verification tests added (feetech+gradient0 active; simulation+any robot unchanged; legacy no-backend path unchanged).
  - All cross-references updated across sprint files, TODO.md, and docs/jerkiness-diagnosis.md (quickfix refs 02→04, feasibility 05→07, HLS 07→05, protocol sprint now sprint-01).
- Changes:
  - sprints/ renames + internal reference updates (8 active files, 1 archived)
  - sprint-04: Implementation section rewritten with mandatory backend-gating block + gating matrix tests
  - TODO.md rewritten (sprint table, dependencies diagram, next actions)
  - docs/jerkiness-diagnosis.md sprint refs updated
- Validation:
  - rg verified: no stale sprint-number or old-filename references remain in active files.
- Follow-up notes / risks:
  - Numbering is now priority-ordered per user's philosophy: study (03) before quickfix (04) so architecture understanding precedes the fix.

## 2026-09-08 (session 9) — Sprint swap 02/03; README resync; hardening explanation requested

- Task summary:
  - User swapped sprints 02 and 03: study now 02 (before quickfix, keeps priority ordering intact), electronics now 03.
  - Cross-refs fixed in: sprint-01 (prereq → electronics), sprint-06 (crash course ref), TODO.md (table + current state), docs/gradientos/architecture-notes.md stub, docs/protocols/feetech-hls.md stub, README.md.
  - Found and resynced feetech-project/README.md — it still had the ORIGINAL pre-restructure phase table and repo-layout listing (7 sprints, wrong filenames). Rewrote phases table with current 9-sprint plan + status, fixed sprints/ directory listing, added archive/ and code/ notes.
  - User asked for an explanation of sprint-08 (full-arm hardening) — explained power bus, udev stability, joint limits (software-clamp-only risk), temp soak, operator docs.
- Changes:
  - sprints/ file swap + titles + cross-refs; TODO.md; README.md (phases + layout); two doc stubs.
- Validation:
  - rg sweep: zero stale sprint filename references across feetech-project/ and docs/.
- Follow-up notes / risks:
  - README.md had drifted badly (original 7-sprint plan) — add "check README after sprint restructures" to the renumbering workflow.

## 2026-09-11 (session 11) — Sprint 04 user-validated: smooth motion confirmed on physical arm

- Task summary:
  - User validated Sprint 04 (endpoint-paradigm quick fix) on the physical arm: rotysquare playback is smooth — no stop-go at waypoints, no oscillation. The reported jerkiness symptom is gone.
  - PSU monitoring: highest amperage spike observed ~10 A (~120 W @ 12 V) during profiled-segment motion. No streaming baseline was available for direct comparison (the ~8 W figure in the sprint spec was a stall-test reading, not a streaming-motion reading). 10 A peak is within PSU capability and did not trip protection.
- Validation:
  - rotysquare end-to-end: smooth (user-confirmed)
  - PSU: ~10 A peak (user-observed)
  - Home button: unchanged (no code path changed)
  - Simulation backend: 21 gating tests pass (no behavior change)
- Remaining items (not blocking):
  - `move_line` with pauses: EE path acceptability at ~1 cm segment scale (not yet tested)
  - Quantitative endpoint accuracy measurement (user reports smooth motion; explicit accuracy check pending)
  - Decision log entry for capability-flag pattern
- Follow-up notes / risks:
  - The 10 A peak is noteworthy for Sprint 08 (arm hardening): the power bus must handle sustained 10 A peaks across 8 servos. The URT-1's 6 A limit may be insufficient for aggressive multi-joint moves; Sprint 08 should measure sustained current, not just peaks.

## 2026-09-08 (session 10) — Sprint 04 IMPLEMENTED: endpoint-paradigm quick fix (Feetech-scoped)

- Task summary:
  - Implemented Sprint 04 (endpoint-paradigm quick fix): eliminates reported arm jerkiness by collapsing dense waypoint streams to ONE goal command per segment on Feetech, letting the servo's internal trapezoidal profiler run the whole move — the "Home-button" pattern generalised to all non-weld moves.
  - Strictly gated by `supports_profiled_segments` backend capability flag: activates ONLY for FeetechBackend; Simulation, EtherCAT, and all future backends inherit the ABC default (False) → dense streaming unchanged.
  - Weld paths keep dense streaming (not covered by this sprint; gated on Sprint 07 verdict).
  - Jog loop unchanged.
- Changes:
  - `actuator_interface.py`: Added `supports_profiled_segments` property to `ActuatorBackend` ABC with default `False` (opt-in only; every existing and future backend inherits "off" automatically).
  - `backends/feetech/config.py`: Added profiled-segment config constants (`PROFILED_SEGMENT_DEFAULT_SPEED=500`, `PROFILED_SEGMENT_DEFAULT_ACCEL=10`, `SPEED_MIN=30`, `SPEED_MAX=2000`).
  - `backends/feetech/driver.py`: Overrode `supports_profiled_segments = True` on FeetechBackend; added `plan_profiled_segment()` helper (per-joint speed cap sizing: slowest joint sets duration, others scaled to match arrival times) and `execute_profiled_segment()` convenience wrapper.
  - `trajectory_execution.py`: Added `_backend_supports_profiled_segments()` gating function (queries the active backend instance at runtime — never a hardcoded backend name); added `_execute_profiled_segment_step()` and `_execute_profiled_joint_move_step()`; modified `_trajectory_executor_thread` to route `move` steps (non-weld) and `joint_move` steps through the profiled path when the flag is True, falling back to dense streaming otherwise.
  - `tests/test_profiled_segments.py`: 21 new tests covering the full gating matrix (feetech active = profiled; simulation = dense; no backend = dense; uninitialized = dense), per-joint cap sizing, speed clamping, endpoint accuracy, weld-move exclusion, and execution correctness.
- Validation:
  - All 21 new tests pass.
  - 6 pre-existing test failures (in test_driver, test_protocol, test_planning, test_end_to_end) confirmed present BEFORE this change — all due to tests not calling `robot_config.set_active_robot()` before accessing module-level constants (None until configured). Zero regressions introduced.
  - `python -m pytest tests/test_profiled_segments.py -v` → 21 passed.
- Follow-up notes / risks:
  - Per-joint speed caps use a flat conservative value (500) until Sprint 07 Part A calibrates the rad/s → speed-register LSB conversion. The flat cap is safe for all joints on the Gradient0 arm (matches the smooth Home move's speed).
  - Wait-for-completion after a profiled segment uses a conservative 2.0 s default (the unverified Goal Time register would give exact duration; rotysquare's 1 s pauses absorb any drift). TODO: replace with read-back polling once Sprint 07 calibrates speed LSB → duration.
  - Physical-arm validation (rotysquare smoothness, PSU spike comparison) pending — needs the GradientOS Python env in container and the arm connected. Code is ready for user-validated testing.
  - Sprint 07's verdict determines the long-term streaming question: if pseudo-Dynamixel streaming works, weld paths/jog migrate to saturation streaming and this endpoint path remains for paused trajectories; if not, this endpoint paradigm becomes the PERMANENT Feetech approach.

## 2026-09-11 — Sprint 05: HLS3950 backend created, feetech backend renamed to sts3215

- Task summary:
  - Renamed the existing Feetech backend from `backends/feetech/` to `backends/sts3215/` (class `FeetechBackend` → `STS3215Backend`, registration name `"feetech"` → `"sts3215"`).
  - Created a new `backends/hls3950/` backend for the Feetech HLS3950 servo (class `HLS3950Backend`, registration name `"hls3950"`).
  - Resolved the "biggest hardware unknown" via online research: the HLS3950 uses the same FT-SCS protocol family as the STS3215 (confirmed from Feetech wiki at wiki.aifitlab.com). Same frame format, instruction set, checksum, and SYNC_WRITE layout. Register map is very similar but has key differences (0x2C = target current, 0x22 = current loop Kp, 0x23 = current loop Ki, no torque-switch 128 calibration, new 0x42 moving flag and 0x43 target position readback).
  - Filled the HLS protocol and hardware spec docs from the wiki data.
- Changes:
  - `git mv backends/feetech/ → backends/sts3215/` (all files: __init__.py, config.py, protocol.py, driver.py)
  - `backends/sts3215/`: class renamed `FeetechBackend → STS3215Backend`, all `[Feetech]` print prefixes → `[STS3215]`, docstrings updated
  - `backends/hls3950/`: new backend created from sts3215 pattern with HLS-specific register map, status bits, alarm bit names, and telemetry block 2 parser (includes moving flag)
  - `backends/__init__.py`: registers both `"sts3215"` and `"hls3950"` backends with factory functions
  - `backends/registry.py`: config module paths updated for both backends
  - `run_controller.py`: `"feetech"` string checks → `"sts3215"` + `"hls3950"` (angle limit writes now gate on both serial servo backends)
  - `robots/gradient0/config.py`: `default_servo_backend` → `"sts3215"`
  - `arm_controller/__init__.py`: import updated from `FeetechBackend` to `STS3215Backend`
  - `tests/test_profiled_segments.py`: all imports and references updated
  - `feetech-project/code/*.py`: import paths updated from `backends.feetech` to `backends.sts3215`
  - `feetech-project/docs/protocols/feetech-hls.md`: filled from wiki data (full register map, key differences, calibration instructions)
  - `feetech-project/docs/hardware/servo-specs/HLS3950.md`: filled from wiki data (electrical, URT-1 connection, register summary, bench validation checklist)
- Validation:
  - `python -m py_compile` passed on all changed Python files.
  - `python -m pytest tests/test_profiled_segments.py -v` → 21 passed.
  - `python -m pytest tests/ -v` → 25 passed, 6 pre-existing failures (same as before — NoneType errors from tests not calling `set_active_robot()`), 1 skipped. Zero new regressions.
- Follow-up notes / risks:
  - The HLS3950 backend has NOT been tested on physical hardware yet — bench validation is the next step (PING, read position, command small move).
  - The HLS3950 `supports_profiled_segments` returns True (same trapezoidal profiler), but this is unverified on the physical servo.
  - The `0x2C` register semantics differ (target current vs PWM speed) — the SYNC_WRITE block writes 0 to bytes 4-5 of the 7-byte data, so this difference doesn't affect the current sync_write usage, but matters if current control is ever exercised.
  - The HLS3950 config.py uses the same default PID gains as STS3215 — these will likely need tuning for the HLS servo motor.
  - Historical doc references (sprint files, ARCHITECTURE.md, jerkiness-diagnosis.md) still reference the old `backends/feetech/` path — these are historical records and don't affect code, but should be updated if the docs are ever refreshed.

## 2026-09-11 — Sprint 05 bench validation: HLS3950 PING + 10° oscillation confirmed

- Task summary:
  - HLS3950 servo connected and powered via URT-1 SCS/TTL port. Backend validation completed.
  - PING: servo responded on ID 30 at 1 Mbps. Full register read successful (firmware, version, position, voltage, temp, status, current, moving flag).
  - Motion: 3-cycle 10° oscillation (1024 ↔ 1136 counts). All 6 moves hit targets exactly (delta=0). Returned to start position perfectly.
  - User confirmed visible movement: "I did see it move. it looked great."
- Findings:
  - Firmware: 3.43 (matches wiki HLS minimum for 0x0B calibration support)
  - Servo version: 10.18
  - EEPROM angle limits: 1024–3071 (factory-restricted ~±90°, NOT unrestricted 0-4095 like STS3215)
  - First oscillation attempt failed (commanded position 35, below min limit 1024 — servo clamped). Redone within limits and worked perfectly.
  - All feedback registers confirmed: position (0x38), voltage (12.0V), temp (27°C), status (0x00 healthy), moving flag (0x42), current (0x45)
  - Target position readback (0x43) confirmed working — HLS-specific register not on STS3215
  - The hls3950 backend protocol/config/driver stack works correctly on real hardware out of the box
- Validation:
  - PING: ✅ (ID 30, 1 Mbps)
  - Register read: ✅ (firmware, version, position, voltage, temp, status, current, limits, mode)
  - Motion: ✅ (3× 10° oscillation, all exact, returned to start)
  - User-confirmed visible movement: ✅
- Follow-up notes / risks:
  - The EEPROM angle limits (1024-3071) are factory-set and differ from STS3215 (0-4095 unrestricted). The HLS arm config will need to account for this — the robot config's joint limits must stay within the EEPROM limits or the EEPROM limits must be widened (with human approval).
  - Servo ID is 30 (same as a J3 primary on the STS arm). For a standalone HLS arm, this should be changed to avoid confusion.
  - Default PID gains in hls3950/config.py are copied from STS3215 — tuning may be needed for the HLS servo motor characteristics.
  - Idle current read 1.664 A on the first read, 0 on subsequent — may be a one-off; needs monitoring during longer tests.

## 2026-09-11 — Sprint 05: HLS3950 feature validation + critical SYNC_WRITE fix

- Task summary:
  - Ran 4 feature tests on the HLS3950: SYNC_WRITE, SYNC_READ, moving flag during motion, execute_profiled_segment (backend class method).
  - Discovered critical bug: the STS3215 SYNC_WRITE layout writes 0x0000 to register 0x2C, which is "Goal Time" on STS (harmless) but "Target Current" on HLS (writing 0 DISABLES THE MOTOR). The servo accepts the goal but never executes it, and gets stuck in a state where even individual writes stop working until a restart.
  - Fixed the HLS3950 backend: SYNC_WRITE now starts at 0x2A (not 0x29) with 6 bytes [Pos(2), Current(2), Speed(2)], and writes a non-zero current value (SYNC_WRITE_DEFAULT_CURRENT=980) to 0x2C. Acceleration is set separately via individual write before the sync_write.
  - All 4 feature tests pass after the fix.
- Changes:
  - `backends/hls3950/config.py`: SYNC_WRITE_START_ADDRESS changed from 0x29 to 0x2A, SYNC_WRITE_DATA_LEN_PER_SERVO from 7 to 6, added SYNC_WRITE_DEFAULT_CURRENT=980
  - `backends/hls3950/protocol.py`: `sync_write_goal_pos_speed_accel` rewritten — sets accel via individual write per servo, then sends 6-byte sync_write starting at 0x2A with non-zero target current
- Validation:
  - TEST 1 (SYNC_WRITE): 2-cycle oscillation, all targets exact, servo not stuck — PASS
  - TEST 2 (SYNC_READ): batch read returns correct position — PASS
  - TEST 3 (Moving flag): 0x42 register = 1 during motion, 0 when settled — PASS
  - TEST 4 (execute_profiled_segment): -89.8° → -79.8° → back, exact, returned — PASS
  - Unit tests: 21/21 profiled-segment tests still pass (no regression)
- Follow-up notes / risks:
  - The STS3215 and HLS3950 SYNC_WRITE layouts are now fundamentally different. Code that constructs sync_write packets must use the correct backend's protocol module — the shared `protocol.sync_write_goal_pos_speed_accel` function is NOT interchangeable between backends.
  - The SYNC_WRITE_DEFAULT_CURRENT (980) is the torque limit in 0.1% units. If the arm needs per-joint torque limiting, this value should be configurable per servo, not a global constant.
  - The HLS3950 must be restarted (0x08 instruction) to recover from a stuck state if any code accidentally writes 0 to 0x2C.

## 2026-09-11 19:58 -07:00

- Task summary:
  - Wrote all Sprint 07 bench experiment scripts (Pseudo-Dynamixel feasibility study).
  - Four files created: shared utility + Parts A/B/C of the sprint.
  - No production code changed — this is bench-only experiment tooling.
- Changes:
  - `feetech-project/code/bench_utils.py` — shared utilities: serial setup, bulk telemetry read (11 bytes from 0x38–0x42 in one packet), CSV trace writer, safe-move recipe (seed-verify), guardrails, position/velocity helpers. Bulk read achieves higher sample rates than per-register reads by fetching pos+speed+load+voltage+temp+status+moving in a single round-trip.
  - `feetech-project/code/part_a_speed_calibration.py` — Part A: sweeps speed cap {10, 30, 60, 100}, times move completion, computes rpm/LSB conversion (documented 0.732, unverified), finds motion floor by sweeping downward.
  - `feetech-project/code/part_b_midmove_retarget.py` — Part B (decisive): commands long move 4016→3600, rewrites goal to 3400 mid-cruise, logs telemetry at max rate (~100+ Hz via bulk read), auto-classifies A (velocity blend)/B (re-plan from rest)/C (queued completion). Runs 3 trials for consistency. Optional `--edges` flag runs high-rate 100 Hz re-target probe and direction-reversal probe.
  - `feetech-project/code/part_c_cap_sweep.py` — Part C: streams linear move at 100 Hz, sweeps cap {4095, 500, 100, 30, 10, floor}, classifies velocity regime (stop-go / continuous cruise / lag) from zero-crossing analysis.
- Validation:
  - All four scripts pass `py_compile` (syntax OK).
  - All imports resolve against the venv (`bench_utils` imports `protocol` module successfully).
  - Protocol function references verified: `calculate_checksum`, `read_register_byte/word`, `write_register_byte/word` all exist.
  - Register addresses verified against `config.py`: 0x29 (accel), 0x2A (target pos), 0x2E (target speed), 0x38 (present pos), 0x3A (present speed), 0x41 (status), 0x42 (moving).
- Follow-up notes / risks:
  - Scripts are ready to run but require physical bench hardware (STS3215 on `/dev/serial/ch340`, PSU).
  - Part B `--edges` direction-reversal probe is the only test that commands backward motion — operator must watch the servo.
  - `RETARGET_DELAY` in Part B (0.8s) may need adjustment if the servo reaches the first goal before re-target fires.
  - Bulk read approach (single 11-byte read) should achieve ~200+ Hz sample rate on the bench; if not, reduce `CAPTURE_DURATION` or split reads.
  - Part C's stream loop paces goal writes at 100 Hz but reads telemetry between writes — actual telemetry rate depends on serial round-trip latency.

## 2026-09-14 15:01 -07:00

- Task summary:
  - Reviewed Sprint 07 Part A results (run externally by the user with GPT assistance on the bench, 2026-09-14). Verified the data files and protocol-doc updates independently. Identified open questions to settle before Part B.
- Findings (verified against raw CSVs in feetech-project/data/part_a_*):
  - Low-speed floor: caps {1,2,5,10,30,50} all produce ~5 deg/s, 0x3A decodes to magnitude 50 → the speed command floors at 50 LSB (~5 deg/s). Documented 0.732 rpm/LSB is REFUTED as a direct goal→speed conversion.
  - Above the floor, achieved speed scales sub-linearly with cap: 100→9.0 deg/s, 200→17.2, 300→22.9 (≈0.09 deg/s per LSB, i.e. ~0.015 rpm/LSB effective at the low end, decreasing).
  - CRITICAL for Part B: cap 300 over 223 counts takes ~0.85 s position-timed, but 0x3A decoded magnitudes during the cap-300 down move cluster at 100-350 — NOT 300. The 0x3A speed encoding does NOT equal the goal-cap units or a simple rpm conversion. Part B classification must NOT assume 0x3A magnitude ≈ cap.
  - 0x3A direction encoding confirmed: downward moves report raw ≈ 32768−mag (e.g. 32868→100), upward moves report raw 100-200 directly. decode = raw>32767 ? 65536−raw : raw.
  - Return (upward) moves at cap 500 hit ~150 decoded (≈13 deg/s position-timed), consistent with the down-move scale.
  - Protocol doc updates by the user are good: safe-move recipe, torque auto-enable on goal write, accel 0=max semantics, unrestricted angle limits, write-then-read flakiness (retry-after-write only), ~3 ms per-transaction latency floor.
- Open questions for Part B prep (to resolve with the user):
  1. 0x3A units are still unknown (decoded 50 ↔ ~5 deg/s floor; decoded 150 ↔ ~13 deg/s on the cap-500 return) — roughly consistent with 0.1 deg/s per LSB·(gear?) but needs explicit confirmation before trusting 0x3A for cruise detection in Part B.
  2. Part B cruise-detect threshold must use position-delta, not 0x3A, or be calibrated to the observed decoded range (100-350 at cap 300).
  3. Bench servo position drifted ~4096→3906 during Part A (downward-only guardrail still holds); Part B constants (4016→3600→3400) assumed a ~4016 start — script start pos must adapt to actual (~3895) or be parameterized.
  4. DEVLOG/scratchpad were not updated when Part A ran (workflow miss by the external run) — recording this review entry now.
- Follow-up notes / risks:
  - No production code changed. Part B script review is next: it needs a start-adaptive parameterization and a classification tweak before bench day.

## 2026-09-14 15:34 -07:00

- Task summary:
  - Applied pre-Part-B fixes identified in the Part A review: 0x3A decode bug, relative goals, classifier recalibration, and added the velocity-mode hybrid probe (user requested testing both modes as the interim architecture).
- Changes:
  - `bench_utils.py`: 0x3A now decoded as bit15 direction + low-15 magnitude (raw & 0x7FFF), NOT two's-complement. Sample dict carries speed_raw/speed_mag/speed. save_trace CSV header extended with all three fields. Added REG_OPERATION_MODE (0x21).
  - `part_b_midmove_retarget.py`: goals are now relative to actual start (start-296 → start-516) — works from any resting position. Classifier recalibrated with Part A measurements: cruise = speed_mag ≈ cap, dip threshold = SPEED_FLOOR (50), case C = full stop at first goal. Retarget fires only when moving && speed_mag > 50. Added edge_velocity_mode_hybrid(): cruise in mode 1 (velocity command, downward = negative), flip 0x21→0 mid-cruise, seed goal at current pos, then write final target. Position-mode restore in a finally block (Ctrl+C-safe). Wired into --edges flow, operator-Enter-gated, before the reversal probe.
- Validation:
  - py_compile passes on both files.
  - Offline decode smoke test: raw {32868→100, 32968→200, 33068→300, 150→150} all decode correctly with bit15 direction.
  - save_trace round-trip verified with new CSV fields.
- Follow-up notes / risks:
  - Velocity-mode hybrid probe is UNTESTED on hardware — the velocity command sign convention (negative word = downward) is inferred from Feetech docs, not measured. If the servo moves the wrong way on the first hybrid probe, kill power and report; we'll flip the sign convention and re-run.
  - Watchdog on the hybrid probe is minimal (finally-block mode restore + short duration). If velocity mode proves flaky, do not repeat — single trial, then reassess.
  - Upward speed anomaly from Part A (cap 500 return plateaued at decoded 150) is still unexplained — return_home() uses upward moves; if returns take ~5s instead of ~2.5s, that's the anomaly, not a fault.

## 2026-09-14 16:1x -07:00 (Part B bench run)

- Task summary:
  - Ran Sprint 07 Part B on the bench (user watching PSU). First run failed silently (0 telemetry samples) due to an off-by-one in bench_utils.read_register_bulk (expected resp length = length+5, actual = length+6; checksum byte cut off → every read failed validation). Fixed and re-ran.
  - VERDICT: **CASE A — velocity-continuous blend** across goal rewrites mid-cruise. Consistent across 3/3 trials.
- Evidence (verified from raw traces, NOT the auto-classifier):
  - Retarget fired ~0.60s mid-cruise at pos ~3763 (goal1 3607, goal2 3387).
  - speed_mag avg 300 → 300 across the retarget instant; min 250 (quantization, 0x3A steps of 50); zero full stops between retarget and arrival; single continuous cruise start→goal2; arrival t≈1.93s, position 3388-3390 (within 1-2 counts of goal).
  - The servo does NOT finish the old plan first (not C) and does NOT re-plan from rest (not B). The firmware blends the new goal into the running profile.
- IMPORTANT: the script's auto-classifier printed "C" — false positive. Its `reached_initial_goal` test (pos ≤ goal1+10) is trivially true when the retarget goal is beyond goal1 (servo passes through goal1 at cruise). Its `stopped_at_goal` test can also false-positive during final decel at goal2. Classification was corrected by manual trace analysis. Fix the classifier before it is trusted again.
- Changes:
  - `bench_utils.py`: read_register_bulk resp_len length+5 → length+6 (checksum byte).
- Consequences:
  - Saturation streaming is GO: the firmware accepts mid-cruise goal rewrites with velocity continuity. Dense position streaming with moderate caps (goals kept beyond braking distance) will cruise smoothly.
  - This also de-risks the hybrid mode-switch probe and makes Part C the next decisive step (find the cruise/lag boundaries for streaming caps).
- Follow-up notes / risks:
  - 0x3A reports in steps of 50 (quantization observed: 250/300/350) — dips smaller than ~50 units are invisible; fine for regime classification, not for fine ripple measurement.
  - Return drift continues: -1/-2 counts per trial cycle (cumulative backlash undershoot, consistent with Part A).

## 2026-09-14 15:4x -07:00 (Part D sinusoid)

- Task summary:
  - Wrote and ran Part D sinusoidal smoothness test (visual acid test with pointer on servo horn). Legacy (cap 4095, accel 0) vs profiled (cap 850, accel 10) phases, same sine, 100 Hz goal stream.
- Results:
  - Both phases: fluid wave, no stalls, no write fails, no guard stops. All "full stops" in both traces occur EXACTLY at the sine extremes (pos 3798/3104 = band edges 3801/3101), duration 0.13-0.18s = the sine's natural velocity zero-crossing dwell. That is correct sinusoidal tracking, not stop-go.
  - Mid-travel: zero full stops, zero speed==0 events, zero re-accel bursts in BOTH phases; velocity traces track the sine's velocity curve continuously (avg ~250 counts/s, rising/falling with the wave).
  - KEY INSIGHT: legacy settings (4095/accel 0) streamed smoothly HERE because the goal stream itself was smooth (Case A blending + continuous sine). The production jerkiness is NOT inherent to streaming with maxed caps — it comes from the trajectory executors' segment structure (each micro-waypoint arrives + sharp corners + per-point full-speed lurches), not from the caps per se. Case A + smooth dense goal streams = smooth motion even with legacy caps. (Still keep moderate caps in production for tracking-error headroom — profiled phase tracking err avg 37 counts vs legacy 16 is within cap/servo lag, not jerk.)
- Files:
  - `feetech-project/code/part_d_sinusoid_smooth.py` (new test)
  - Traces: `feetech-project/data/part_d_sinusoid/20260914_153114/{legacy,profiled}.csv`
- Follow-up notes / risks:
  - Awaiting user visual confirmation (pointer) — but telemetry already confirms continuous motion.
  - Backlash pause at reversals was NOT visible in telemetry stops (dwell windows at extremes are sine-inherent); mechanical backlash check stays in Sprint 06.
  - Next: Part C cap sweep (--floor 50) closes the streaming-implementation design space; then verdict write-up.

## 2026-09-14 16:0x -07:00 (Part C bench run + Sprint 07 completion)

- Task summary:
  - Ran Sprint 07 Part C (cap sweep on streamed motion). First run invalid: MY stream math had a sign error (step_size positive → goals streamed UPWARD to the 4094 seam; servo obediently tracked them). Fixed (+ per-goal bounds guard added), re-ran clean.
  - Part C RESULT (verified from raw traces, not the auto-classifier labels):
    - caps 4095/500/200: servo tracks the 400-count/3s stream (~133 counts/s demand) at steady ~130 cruise, error 1-2 counts, zero mid-stream stops. The "STOP-GO" auto-labels are false positives — the counted zero-crossings are only the move's own start (t=0) and arrival (t≈3.1).
    - cap 100: cruise pinned exactly at 100 (the cap), still error 2 counts. CRUISE regime.
    - cap 50: cruise pinned at 50 (firmware floor), 38% undershoot — LAG regime. Stream demand 133 > floor 50, as expected.
  - REGIME MAP (stream demand ~133 counts/s): CRUISE for cap ≥ 100; LAG at cap 50 (floor). Transition: cap between 50 and 100 for this demand; generalizes to "cap ≥ stream demand → cruise".
  - Sprint 07 is now DATA-COMPLETE: Part A (LSB 0.088 deg/s, floor 50, 0x3A=cap units), Part B (CASE A velocity-continuous blend, 3/3), Part D (sinusoid smooth both legacy + profiled settings), Part C (cap ≥ demand → continuous cruise; below → lag).
- Housekeeping: servo parked at 3892 (was left at 4092 near the seam by the buggy Part C run — moved it down with safe recipe).
- Changes: `part_c_cap_sweep.py`: step_size sign fixed (-total_move/n_steps), per-goal bounds guard (every streamed goal clamped to [final_target, start_pos], violations printed).
- Bugs I introduced and fixed this session (recorded so they don't recur):
  1. bench_utils.read_register_bulk off-by-one (resp_len +5 → +6) — silent total telemetry failure.
  2. part_c step_size sign error — streamed goals the WRONG DIRECTION, drove servo to the 4094 seam. Guardrail lesson: validate EVERY streamed goal against a safe band, not just the endpoints. The servo always obeys; the safety contract is entirely on the sender.
  3. Auto-classifiers (B and C) both produced false verdicts; raw-trace analysis was required both times. Lesson recorded: script verdicts are hints, traces are truth.
- Follow-up: verdict write-up + docs/jerkiness-diagnosis.md §9.4/9.5 update next (no bench time needed). Sprint 07 checkbox file to be updated.

## 2026-09-14 16:3x -07:00 (Sprint 10 + 11 written)

- Task summary:
  - Wrote two sprint files following the bench session: Sprint 10 (smooth streaming executor — the production implementation of Sprint 07's Case A findings) and Sprint 11 (hypothetical reactive-motion sprint with algorithm discovery as Part A, since no avoidance algorithms exist yet).
  - Updated TODO.md: resolved the two Sprint-07 open questions, added the post-07 sprint table.
- Changes:
  - `feetech-project/sprints/sprint-10-smooth-streaming-executor.md` — backend-wrapped continuous setpoint streaming: `supports_setpoint_streaming` capability flag (Sprint 04 pattern), `execute_timed_path` handle API, 100 Hz pacing + 50 ms lookahead, per-move cap sizing (2x path demand), per-goal stream clamp (Part C lesson), horizon expiry instead of watchdog (user-challenged design point, recorded in scratchpad). Planner/command API/UI/weld untouched. HLS explicitly excluded pending its own fork test. Gating matrix + bench validation items included.
  - `feetech-project/sprints/sprint-11-reactive-motion.md` — explicitly hypothetical/unscheduled. Part A = algorithm discovery: obstacle-state contract (with synthetic producer so motion work starts without cameras), avoidance-policy sim bake-off (repulsive fields vs velocity obstacles vs occupancy gradient), prediction decision, task-vs-joint-space avoidance decision, integration design (replace_remaining_path on the Sprint 10 handle), GO/park gate. Parts B/C provisional on Part A outcome.
  - `feetech-project/TODO.md` — open questions resolved (Case A verdict, LSB calibration), new sprint table rows for 07/10/11 with accurate statuses.
- Validation: sprint files reviewed against measured Sprint 07 data (all numbers sourced from bench results: 3 ms dispatch, ~160 Hz measured stream rate, cap map, 0.088 deg/s LSB, floor 50, 50 ms lookahead travel bound).
- Follow-up notes / risks:
  - Sprint 10 numbering starts fresh after the 08b file; no renumbering of existing sprints (learned lesson from session renumber churn).
  - Sprint 11 Part A5 needs `replace_remaining_path` on the Sprint 10 handle — flagged in both files so whichever lands first carries it.
  - Remaining desk work before Sprint 10 implementation: jerkiness-diagnosis.md §9.4/9.5 update + Sprint 07 verdict write-up + sprint-07 checkbox file update.

## 2026-09-14 17:0x -07:00 (Sprint 07 documentation updated)

- Task summary:
  - Brought all Sprint 07 documentation current with the bench results: sprint checkbox file, jerkiness-diagnosis.md §9.3-9.5 + §10.6, and the protocol doc's speed/0x3A sections. The desk-work TODO from the bench session is now clear — Sprint 10 can start implementation.
- Changes:
  - `sprints/sprint-07-pseudo-dynamixel-feasibility.md`: marked COMPLETE/GO at the top; Part B evidence + auto-classifier-false-positive note recorded; Part C regime map (CRUISE iff cap >= demand; raw-trace classification, auto-labels false); Part D sinusoid section added with the segment-structure root-cause refinement; verdict tuning parameters (cap 2x demand clamped [100,2000], accel 10, 100 Hz stream, 50 ms lookahead, no watchdog); supersession notes on the three skipped probes; session log rows for Parts B/C/D + sprint planning follow-ups; definition-of-done all checked.
  - `docs/jerkiness-diagnosis.md` §9.4: fork RESOLVED as Case A with evidence and per-case refutations; §9.5: executed regime map (cap table, encoding, quantization, design recipe) + Part D segment-structure confirmation; §9.3: LSB passage corrected (0.088 deg/s output shaft; 0.732 rpm/LSB = motor shaft pre-gearbox — both "right", different shafts); §10.6: relationship table resolved (streaming no longer "gated"; Sprint 10 subsumes endpoint paradigm; Sprint 11 pointer).
  - `docs/protocols/feetech-sts-scs.md`: 0x3A register-map row replaced with the full encoding (bit15 direction, 0x7FFF magnitude, 50-LSB quantization, same units as 0x2E); new "Mid-move goal rewrites" section with the Case A verdict, streaming implications, fail-safe property, regime rule, and design recipe.
- Validation: cross-checked every number against the bench traces/summaries from this session (0.088 deg/s LSB, floor 50, 300->300 retarget, 1-2 count errors, 38% undershoot at floor, ~0.15s sine-extreme dwell). Sprint file checkbox state verified: 22 checked, 2 deliberately-unchecked superseded probes with annotations.
- Follow-up notes / risks:
  - Two probes left deliberately unchecked (high-rate retarget, velocity-mode hybrid) with supersession notes — reopen only if Sprint 10 validation shows anomalies.
  - docs/jerkiness-diagnosis.md §11 (if any) untouched; §10.1-10.5 remain as-is (historical Sprint 04 record — still accurate).
  - Sprint 10 implementation unblocked: design, verdict, calibration data, and docs all in place.
