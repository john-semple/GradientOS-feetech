# Agent Scratchpad

Use this file as persistent, repo-local execution memory.

## File Policy

- Current policy: `COMMITTED`
- Rationale:
  - The user explicitly asked for persistent use of scratchpad/devlog skills and visible top-level references.

## How To Use

1. Read latest entries before starting meaningful work.
2. Build a short preflight checklist from recurring mistakes and preferences.
3. Re-read before risky operations (migrations, broad refactors, unfamiliar tooling, destructive commands).
4. Log high-signal learnings immediately during the task.
5. Append one new session entry before handoff.
6. Keep entries concrete, concise, and testable.

## Entry Rules

- Tag operational notes with source: `[self]`, `[user]`, or `[tool]`.
- Prefer facts tied to files, commands, and outcomes.
- Do not log low-signal reminders.

## Retained Lessons

- [user] Prefer implementation over discussion; "do it, do not only explain."
- [user] UI preferences are specific and iterative; keep changes minimal and visual hierarchy clean.
- [tool] Build and lint checks (`npm run build`, `ReadLints`) catch regressions quickly in the web-ui workflow.
- [self] When creating a mixin for near-identical classes (STS3215/HLS3950), verify the MRO doesn't shadow backend-specific properties. StreamingMixin goes first in the MRO: `class STS3215Backend(StreamingMixin, ActuatorBackend)`.
- [self] SimulationBackend's `prepare_sync_write_commands` returns float angles, not raw ints — use `set_joint_positions()` for sim streaming writes, not `sync_write()`.
- [self] In fast-forward sim mode, use a virtual clock (`cycle * period`) instead of `time.monotonic()` — wall clock barely advances when sleeps are skipped, so `t_now > path_end` never triggers and the loop hangs.
- [self] When unpacking path tuples `(t, q)`, remember `t` is a float, not a tuple — `t1[0]` is a TypeError, use `t1` directly.
- [self] `handle_stop_command()` must check for and cancel the active streaming handle (`trajectory_state["streaming_handle"]`) before falling back to the legacy brake command.
- [self] **Per-joint speed caps are critical for streaming.** Using `max(caps)` (the fastest joint's cap) for ALL servos causes backlash hunt oscillation on J1/J2 — the low-velocity joints aggressively chase each micro-goal across the backlash gap at 100 Hz. Must use per-joint caps via a custom `_prepare_streaming_commands()` that builds per-servo speed register values. The `prepare_sync_write_commands()` method only accepts a single flat speed — don't use it for streaming.
- [self] `_backend_supports_setpoint_streaming()` must check `_use_backend()` first, not just `backend.is_initialized`. The end-to-end test patches `_use_backend` to return False (forcing legacy servo_protocol path); without that check, streaming activates even when the test expects legacy behavior.
- [self] **Count the dots in relative imports.** `from ... import utils` (3 dots) from `backends/_streaming_mixin.py` resolves to `gradient_os.utils` (doesn't exist). `from .. import utils` (2 dots) resolves to `gradient_os.arm_controller.utils` (correct). A bare `except ImportError: pass` silently swallows the error — the GUI never updated during moves and it took a full debugging cycle to find a one-dot bug.
- [self] **Bus contention on single-wire protocols is the silent killer.** Two threads independently reading/writing the CH340 half-duplex bus causes unpredictable collisions that manifest as motion jerk, not errors. One thread must own the bus during motion; all reads happen inside the write loop on a controlled schedule.
- [self] **Cap multiplier should be close to 1×, not high.** 3× gives racing room that causes overshoot-stall vibration on slow moves. 1.2× is enough to track the stream. The bogging-down was bus contention, not insufficient cap — so lowering after fixing contention was safe.
- [self] **Don't make design decisions without user approval.** Implemented variable pacing + interleaved reads without presenting options first. User called this out. Present options, explain trade-offs, implement what they choose.
- [self] **Don't edit motion code while the controller is running.** It picks up new code on the next motion command and moves the arm unexpectedly. Always ask user to stop controller first.
- [self] **Test on hardware early and often.** All 93 sim tests passed but multiple issues only appeared on real hardware (bus contention, backlash oscillation, cap sizing). Sim verifies logic; only hardware validates dynamics.
- [self] **Read logs carefully.** `[STS3215 SyncRead] WARNING: No response from IDs` messages were the key diagnostic for bus contention. They appeared before motion problems were reported but weren't recognized until the user reported jerkiness.

## Session Entries

### 2026-09-15 — Sprint 10: Smooth Streaming Executor implementation

- Implemented Sprint 10 setpoint streaming in one session.
- User approved design changes to sprint doc first (HLS shared impl + config
  override, robust sim with fast_forward, MotionHandle with pause/resume),
  then said "go".
- Created MotionHandle, StreamingMixin, sim streaming, executor migration,
  36 new tests. All 93 backend tests pass, web UI tests + build pass.
- Bench validation (physical arm) left flagged as needs-hardware per user's
  request — they don't have a servo set up yet but will validate later.
- Key gotcha: sim pacing loop with fast_forward needs a virtual clock, not
  wall-clock time. Caught by test_fast_forward_completes_quickly timeout.
- Key gotcha: sim `prepare_sync_write_commands` returns float angles, not
  raw encoder values. Use `set_joint_positions()` for sim streaming.

### 2026-09-14 (session 2) - Sprint 08b doc pass: httpx silent-skip discovery

- **Critical lesson (the biggest of this sprint)**: `pytest.importorskip` at module
  level fails SILENTLY. `tests/test_api_endpoints.py` skipped entirely because
  httpx was missing from the venv — collecting as one harmless-looking "1 skipped"
  in the summary. I misread that as "intentional hardware-only skip" and reported
  the suite green. **Always run `pytest -rs` or investigate ANY skip count > 0.
  A skip can hide a whole untested subsystem.** (The user's own AGENTS.md even had
  this warning written into it afterwards — this is exactly the failure mode the
  "expect 0 skipped" note guards.)
- **Mistakes made (avoid repeating)**:
  - While updating docs, I checked off the "audit endpoint coverage" task as if it
    had been done, then realized I'd never actually run the audit. Doing the audit
    is what surfaced the httpx problem. Don't mark a task done because it "should
    have been covered" — verify first.
  - Wrote 4 test assertions against my assumptions of endpoint behavior instead of
    reading the handler code first. All 4 were wrong (REST → CSV not literal;
    rotate is relative; float serialization; /health shape). Tests written against
    assumed behavior prove nothing — read the handler, then assert what it does.
  - In tests/README.md editing, my edit accidentally REPLACED the test_end_to_end.py
    description instead of adding a new one (oldString matched the wrong entry).
    After structural edits, grep for the surrounding entries to confirm nothing
    was consumed.
- **Guardrails established**:
  - httpx is required for the API test file and is part of `[dev]` extra. New venvs
    must `uv pip install -e '.[dev]'` or the API tests silently vanish.
  - AGENTS.md now documents the three test gates + the 0-skipped expectation.
  - When endpoints change signatures (e.g. plan_preview_trajectory_points gained
    `sections`), their mocks in test_api_endpoints.py must be updated in the same
    commit — otherwise the mock rotted silently while skipped.
- **Verified facts**:
  - `/control/rest` sends a 6-float joint-angle CSV command, not the literal "REST".
  - `/control/rotate` reads current orientation then writes SET_ORIENTATION with
    axis+angle (relative, not absolute).
  - `/health` returns {status, detail, controller:{host, port}}.
  - Final backend suite: 57 passed, 0 skipped (31 → 57 because the 26-test API file
    now actually runs).

### 2026-09-14 - Sprint 08b: Test infrastructure baseline (vitest + backend suite repair)

- **Context**: Implemented Sprint 08b as prerequisite for Sprint 09 (GUI improvements). User runs servo bench tests directly over USB in parallel; verified the test work touches no serial/USB paths (frontend-only + fully-mocked pytest).
- **Mistakes made (avoid repeating)**:
  - Used `vi.stubGlobal` in apiMock.ts without importing `vi` — vitest config has `globals: false`, so the global `vi` doesn't exist. Always `import { vi } from "vitest"` in helper files.
  - `vi.useFakeTimers()` + async fetch/userEvent deadlocked a 5s-timeout test. Don't enable fake timers unless the test specifically exercises timer-driven behavior (jog interval etc.); the smoke tests don't need them.
  - Wrote a TelemetryCharts assertion on servo-id text ("10") — servo ids only render in SVG hover tooltips, not the DOM. Assert on section titles ("J1 (deg)", "Voltage (V)") instead. When writing DOM assertions, grep the component's JSX for what actually renders first.
  - First DEVLOG edit consumed the following entry's header (`oldString` included the next header). When prepending entries, anchor on the *first line of the previous top entry* and re-add it in `newString`.
- **Guardrails established**:
  - Web-UI tests must import components directly, never via `App.tsx` (Three.js/WebGL chain crashes jsdom). Documented in web-ui/README.md + sprint doc.
  - `src/test/setup.ts` must polyfill `ResizeObserver` before any TelemetryCharts test runs.
  - Backend tests depend on `tests/conftest.py` to run the run_controller.py-style init (set_active_robot + set_active_backend + _populate_servo_constants). If that startup sequence changes, conftest must mirror it. Without it, `utils` constants are None → TypeError (the sprint-05 restructure made module constants None until init).
  - The e2e test pins the legacy write path via `@patch(... _use_backend, return_value=False)` in both servo_driver and trajectory_execution — controller startup creates a real backend instance, and OL executor prefers `backend.sync_write()`. If the legacy servo_protocol path is ever removed, this test must be rewritten against the backend path.
  - Mock-shape drift risk: `web-ui/src/test/apiMock.ts` and `tests/test_api_endpoints.py` encode the same FastAPI contract; change both together.
- **Verified facts**:
  - gradient0 has NO software 2:1 gear on J1 — logical→physical is 1:1 (servo_driver.py set_servo_positions + robots/gradient0/config.py). The old test_driver gear-ratio expectation was stale from the pre-gradient0 mini-arm.
  - The 6 backend failures pre-dated this sprint (confirmed via `git stash` on pristine tree).
  - Tailwind is a non-issue in vitest (`css: false`); don't spend time on CSS-transform config.
- **Test gates for this repo** (run before considering frontend/backend work done):
  - `npm run test:run` (web-ui) — 8 smoke tests
  - `npm run build` (web-ui)
  - `python -m pytest tests/` (repo root, venv active) — 31 passed, 1 skipped

### 2026-02-16 00:14 +11:00 - Sidebar UX refinement and workflow persistence

#### Task Summary

- Adjusted drawer close-button placement and panel framing behavior per user screenshot feedback.
- Kept robot control right-docked and collapsible.
- Added explicit top-level workflow pointers and persistent memory files.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Initial close-button placement still appeared outside the panel because drawer width did not match panel width behavior.
- Detection:
  - User screenshot showed the close icon floating outside the card boundary.
- Fix:
  - Synchronized drawer width to panel scale and repositioned close button offsets.
- Preventive rule:
  - When overlay controls must align with a child card, validate parent width/position assumptions before tweaking z-index/offsets.

#### User Preferences

- New or reinforced preference:
  - Keep close controls on the same line as the panel title area.
  - Remove redundant visual framing (no duplicate outer border effect).
  - Keep robot control aligned on the right and collapsible.
  - Always maintain devlog/scratchpad workflow and keep `.cursor/skills` references visible.
- How it changed execution:
  - Prioritized layout simplification and added top-level workflow references.

#### What Worked

- Pattern/check that worked:
  - Small targeted CSS/class updates in drawer wrapper and deterministic build verification.

#### What Did Not Work

- Failed attempt and why:
  - Width-only tweak without checking `w-full max-w-*` interactions can leave floating controls misaligned.

#### Guardrails For Next Session

- Preflight rule:
  - Read this scratchpad + `DEVLOG.md` first, then align any overlay control to the actual rendered panel width before finalizing.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Confirm visual alignment at multiple viewport sizes after future panel style changes.

### 2026-02-16 00:20 +11:00 - Prevent tab lock from tree sync

#### Task Summary

- Fixed behavior where loading STEP or existing tree selection auto-forced Weld tab.
- Restored manual tab switching while preserving weld/tree selection sync.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Program-tree synchronization effect controlled `activePanel`, unintentionally overriding user tab changes.
- Detection:
  - User reported automatic tab jump to Weld and inability to switch tabs afterward.
- Fix:
  - Removed panel-forcing from tree-sync effect; moved panel-open behavior to explicit tree click handler.
- Preventive rule:
  - Keep sync effects state-specific (selection-to-selection), and keep view-navigation state controlled only by explicit user actions.

#### User Preferences

- New or reinforced preference:
  - Loading a STEP model must not auto-navigate to Weld.
  - User must be able to switch tabs freely at all times.
- How it changed execution:
  - Prioritized decoupling `activePanel` from background sync logic.

#### What Worked

- Pattern/check that worked:
  - Isolating tree sync side effects and validating with build quickly confirmed fix stability.

#### What Did Not Work

- Failed attempt and why:
  - Coupling panel navigation to derived tree focus caused repeated tab override loops.

#### Guardrails For Next Session

- Preflight rule:
  - Before adding `useEffect` state sync, verify it cannot override explicit user UI navigation state.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If new tree node types introduce `openPanel`, ensure only direct selection handlers apply that field.

### 2026-02-16 21:51 +11:00 - Multi-select edge flicker and panel-control placement

#### Task Summary

- Moved STEP Import `Reset Pose` control to the bottom of the panel.
- Fixed tree/weld synchronization conflict that could cause active segment flicker when two edges were selected.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Bidirectional sync lacked interaction-source gating, allowing tree and weld selection effects to fight each other.
- Detection:
  - User reported flickering behavior when two lines/segments were selected.
- Fix:
  - Added `panelSelectionOriginRef` and only applied tree->weld active-segment sync when selection originated from tree clicks.
- Preventive rule:
  - For bidirectional UI sync, always track source-of-truth per interaction to prevent feedback loops.

#### User Preferences

- New or reinforced preference:
  - Keep key panel actions (e.g. `Reset Pose`) at intuitive positions near related transform controls.
- How it changed execution:
  - Repositioned control directly in `StepImportPanel` footer.

#### What Worked

- Pattern/check that worked:
  - Interaction-origin refs are a lightweight, reliable way to stop cross-effect oscillation in React state sync.

#### What Did Not Work

- Failed attempt and why:
  - Pure dependency-based effects without origin markers were insufficient for multi-source selection flows.

#### Guardrails For Next Session

- Preflight rule:
  - When implementing two-way sync between panels/tree/scene, define and enforce a source tag before writing effects.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If GPU-specific flicker remains, replace selected line rendering with a single authoritative overlay layer and suppress base-line rendering for selected edges.

### 2026-02-17 10:32 +11:00 - Enforce automatic scratchpad and devlog context

#### Task Summary

- Added a repo-level Cursor rule to make scratchpad/devlog workflow mandatory for all meaningful tasks.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Relying on optional workflow habits instead of enforcing them through an always-apply project rule.
- Detection:
  - User explicitly requested both loops be automatic in every agent session.
- Fix:
  - Added `.cursor/rules/agent-memory-loops.md` with start/during/end requirements for both files.
  - Updated `.cursor/rules/agent-gated-checklist.md` to require scratchpad/devlog read at Gate 0 and writeback at Gate 7.
- Preventive rule:
  - When the user asks for persistent agent behavior, encode it in `.cursor/rules` instead of relying on ad-hoc reminders.

#### User Preferences

- New or reinforced preference:
  - Always use and update both `AGENT_SCRATCHPAD.md` and `DEVLOG.md`.
- How it changed execution:
  - Implemented an always-apply rule and logged this change in both memory files immediately.

#### What Worked

- Pattern/check that worked:
  - Converting skill guidance into a concise always-apply rule provides durable enforcement across sessions.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this task.

#### Guardrails For Next Session

- Preflight rule:
  - Before substantial edits, read `AGENT_SCRATCHPAD.md` + `DEVLOG.md`; before handoff, append both.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Existing active sessions may need a fresh prompt/turn to fully align with newly added rule text.

### 2026-02-17 10:45 +11:00 - Explicit skill-to-file pointers for memory loops

#### Task Summary

- Added explicit references linking each memory file to its owning skill and template.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Previous rule text enforced the workflow but did not explicitly map the exact skill files and templates.
- Detection:
  - User asked to point to the specific skills and files.
- Fix:
  - Updated `.cursor/rules/agent-memory-loops.md` with required skill/template/file mapping.
  - Updated `QUICK_START.md` workflow pointers with direct skill-to-file paths.
- Preventive rule:
  - When documenting persistent behavior from skills, always include concrete source-skill paths and destination files.

#### User Preferences

- New or reinforced preference:
  - Keep explicit references to the exact skills and the files they manage.
- How it changed execution:
  - Added direct path mapping in both the always-apply rule and top-level quick-start docs.

#### What Worked

- Pattern/check that worked:
  - Short path mapping bullets remove ambiguity and make compliance auditable in one glance.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this task.

#### Guardrails For Next Session

- Preflight rule:
  - If a process is skill-driven, verify docs include both `SKILL.md` path and target file path.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None identified for this documentation update.

### 2026-02-17 00:12 +11:00 - Duplicate skill mapping across all always-on rules

#### Task Summary

- Added explicit scratchpad/devlog skill-to-file mapping blocks to all `alwaysApply: true` rule files.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Mapping existed in only part of the rule set, leaving room for inconsistent context anchoring.
- Detection:
  - User explicitly requested this be added to the rules (plural) so it is always in context.
- Fix:
  - Updated `.cursor/rules/agent-gated-checklist.md`, `.cursor/rules/agent-ambiguity-triggers.md`, `.cursor/rules/agent-subagents.md`, and `.cursor/rules/rtos-ethercat-readme.md` with the same required mapping block.
- Preventive rule:
  - For mandatory context anchors, mirror the same source-of-truth mapping across every `alwaysApply` rule file.

#### User Preferences

- New or reinforced preference:
  - Keep scratchpad/devlog skill links explicitly present across the entire always-on rule surface.
- How it changed execution:
  - Applied a repeated mapping section to each always-apply rule, not just memory-focused docs.

#### What Worked

- Pattern/check that worked:
  - Uniform, copy-identical mapping sections reduce ambiguity and audit time.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this task.

#### Guardrails For Next Session

- Preflight rule:
  - When user says "always in context," verify all `alwaysApply` rules carry the same mandatory pointers.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If new `alwaysApply` rules are added later, they must include the same mapping block.

### 2026-02-17 00:41 +11:00 - Weld Motion + Tree UX delivery and checklist compliance fix

#### Task Summary

- Delivered full requested pass:
  - compact + chronological Program Tree UX
  - weld section planning with transitions
  - torch-angle controls (UI -> API -> planner)
  - planner robustness and diagnostics.
- Closed workflow loop by writing explicit session entries to both `DEVLOG.md` and `AGENT_SCRATCHPAD.md`.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Completed feature implementation but initially missed the two trailing checklist items (memory writeback + future backlog todo creation).
- Detection:
  - User called it out directly ("last 2 on the list ... didn't touch").
- Fix:
  - Immediately added memory-loop writeback entry to both files and created explicit future backlog tracking todo.
- Preventive rule:
  - Before handoff, verify every visible checklist/todo item (including process tasks) is handled, not just code tasks.

#### User Preferences

- New or reinforced preference:
  - Process tasks are first-class requirements; do not skip memory/devlog updates when explicitly listed.
  - Strong preference for direct execution over explanation-only updates.
- How it changed execution:
  - Added explicit final pass for process compliance and backlog traceability in the same turn.

#### What Worked

- Pattern/check that worked:
  - Section-based weld planning model (`weld` vs `transition`) made it practical to implement contiguous weld continuation and safe-lift transitions without a full collision engine.
  - Runtime fallback from torch-angle orientation solve to orientation-lock avoided planner hard-fails.

#### What Did Not Work

- Failed attempt and why:
  - Strict torch-angle orientation path can be IK-infeasible on some geometries; required fallback behavior to keep planning usable.

#### Guardrails For Next Session

- Preflight rule:
  - Track implementation to-dos and workflow to-dos separately, and do a final checklist sweep that includes both.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Full collision-aware transition planner is still pending and should replace heuristic safe-lift logic in a future phase.

### 2026-02-17 00:47 +11:00 - Viewport-clamped sidebar drawer

#### Task Summary

- Fixed menu overflow issue where left drawer panels could exceed the viewport height.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Drawer container allowed unconstrained vertical growth when panel content (especially Weld panel with long waypoint lists) got tall.
- Detection:
  - User screenshot and explicit feedback: "can't let menus grow larger than window size."
- Fix:
  - Added viewport max-height and internal scroll behavior in `web-ui/src/components/SidebarDrawer.tsx`.
- Preventive rule:
  - Any absolute overlay panel should define a viewport max-height and internal scrolling before adding content-heavy sections.

#### User Preferences

- New or reinforced preference:
  - Keep side menus fully contained within the visible window.
- How it changed execution:
  - Prioritized layout containment fix over feature additions.

#### What Worked

- Pattern/check that worked:
  - Applying max-height at the shared drawer wrapper fixed all drawer-hosted panels at once.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this task.

#### Guardrails For Next Session

- Preflight rule:
  - For UI overlays, validate worst-case content height against viewport before handoff.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If non-drawer floating panels are expanded in future, they may need the same containment pattern.

### 2026-02-17 00:50 +11:00 - Drawer header overlap guard band

#### Task Summary

- Fixed a visual overlap where the drawer close button covered panel header controls on the right side.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - The close button was absolutely positioned over content with insufficient reserved horizontal space.
- Detection:
  - User reported overlap and shared screenshot showing Weld badge collision near the close icon.
- Fix:
  - Added a right-side content guard band in `web-ui/src/components/SidebarDrawer.tsx` by increasing inner wrapper padding to `pr-10`.
- Preventive rule:
  - Any persistent overlay control (close/help/action) must reserve explicit layout space rather than relying on visual luck.

#### User Preferences

- New or reinforced preference:
  - UI controls must never overlap; title/header actions must remain readable and clickable.
- How it changed execution:
  - Prioritized spacing/layout correction over adding new interactions.

#### What Worked

- Pattern/check that worked:
  - Shared-container spacing fixes in one wrapper corrected multiple panel variants without touching feature-specific components.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this task.

#### Guardrails For Next Session

- Preflight rule:
  - For absolute-positioned controls, verify both vertical and horizontal guard space at smallest supported drawer width.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If header content density increases (more badges/buttons), migrate to an explicit shared drawer header row to keep spacing deterministic.

### 2026-02-17 00:53 +11:00 - Escalation handoff note for next model

#### Task Summary

- Added a high-priority takeover TODO in `QUICK_START.md` so a new model can continue unresolved UI overlap cleanup immediately.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Prior spacing fix did not meet user quality expectations.
- Detection:
  - Direct user feedback: overlap still unacceptable.
- Fix:
  - Wrote explicit handoff requirements + acceptance criteria at the top of `QUICK_START.md` to avoid context loss across model handoff.
- Preventive rule:
  - When user asks for takeover, document exact failure mode + required end-state in a top-level onboarding doc.

#### User Preferences

- New or reinforced preference:
  - Do not paper over visual defects; require robust layout fixes.
- How it changed execution:
  - Prioritized cross-model continuity and clear ownership transfer instructions.

#### What Worked

- Pattern/check that worked:
  - A concrete handoff checklist in `QUICK_START.md` gives immediate actionability for the next model.

#### What Did Not Work

- Failed attempt and why:
  - Padding-only overlap mitigation was not perceived as a complete fix.

#### Guardrails For Next Session

- Preflight rule:
  - For overlay/header defects, prefer structural layout changes (shared header row) over spacing-only adjustments.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - The actual UI fix is still pending; this entry only captures handoff context.

### 2026-02-17 19:27 +11:00 - Shared drawer header row implementation

#### Task Summary

- Implemented structural drawer-header fix from `QUICK_START.md` to prevent overlap between header content and close control.
- Moved weld title/badge into shared drawer header surface and removed duplicate in-panel title rows.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Earlier workaround depended on right-side padding (`pr-10`) while keeping close action absolutely positioned.
- Detection:
  - User screenshot + takeover note confirmed overlap remained unacceptable in real weld-header content.
- Fix:
  - Replaced overlay close action with a dedicated `SidebarDrawer` header row (`headerContent` + close button) so layout guarantees non-overlap.
- Preventive rule:
  - For any dismiss/action control near dynamic header content, use structural row layout with flex constraints (`min-w-0`, `shrink-0`) instead of padding buffers.

#### User Preferences

- New or reinforced preference:
  - UI fixes should be robust by structure, not spacing hacks.
  - "Implement, do not only explain" remains the default execution style.
- How it changed execution:
  - Applied direct component refactor and validation in the same turn instead of proposing-only guidance.

#### What Worked

- Pattern/check that worked:
  - Centralizing header composition in `SidebarDrawer` allowed one fix to cover all panel types while keeping panel body logic unchanged.
  - Immediate `npm run build` + `ReadLints` checks caught regressions quickly.

#### What Did Not Work

- Failed attempt and why:
  - Keeping titles in both drawer header and panel cards created duplicated heading surfaces; removed duplicated panel titles where appropriate.

#### Guardrails For Next Session

- Preflight rule:
  - If a shared container now owns a title area, remove duplicate in-panel titles unless they carry unique controls.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Perform visual verification at narrow window widths to confirm spacing and interaction feel for all drawer panels in live UI.

### 2026-02-17 20:34 +11:00 - Drawer bottom inset alignment + AGENTS skill catalog refresh

#### Task Summary

- Corrected left drawer vertical sizing so it keeps a bottom inset instead of visually running to the edge.
- Updated `AGENTS.md` to reflect the rename from `QUICK_START.md` and documented all installed skills with usage triggers.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Previous drawer height model used viewport-based max-height math, which could feel mismatched with sibling overlays in a header+main layout.
- Detection:
  - User screenshot highlighted asymmetry between the left drawer and right robot-control panel bottom spacing.
- Fix:
  - Refactored drawer container to inset-based vertical layout (`inset-y-6`) with `flex` + `min-h-0`; retained scroll using `flex-1 overflow-y-auto`.
- Preventive rule:
  - For overlay alignment across a shared surface, prefer consistent positional insets (`top/bottom`) over independent max-height calculations.

#### User Preferences

- New or reinforced preference:
  - Visually related overlays should have matching baseline/inset behavior.
  - Agent docs must stay current when top-level onboarding files are renamed.
  - Design-oriented skill usage should be explicit and discoverable.
- How it changed execution:
  - Applied layout fix first, then codified full skill relevance in `AGENTS.md`.

#### What Worked

- Pattern/check that worked:
  - `inset-y-*` + `flex-1` scroll gives deterministic alignment while preserving long-content usability.
  - Using `frontend-design` guidance for implementation direction and `web-design-guidelines` guidance for post-change review framing kept UI decisions intentional.

#### What Did Not Work

- Failed attempt and why:
  - Treating drawer max-height independent of main container created perceived edge contact even when scroll technically worked.

#### Guardrails For Next Session

- Preflight rule:
  - If two overlay panels are expected to align, compare both vertical anchors (`top`, `bottom`, internal scroll shell) before finalizing styles.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Confirm final visual balance during live interaction at very small window heights and high content density.

### 2026-02-17 20:41 +11:00 - Themed drawer scrollbar styling

#### Task Summary

- Replaced default browser-style drawer scrollbar with a custom theme-matched scrollbar.
- Kept behavior cross-browser by styling both Firefox and WebKit engines.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Previously left the primary drawer scroller unstyled, which looked inconsistent with the polished panel visual design.
- Detection:
  - User feedback with screenshot: "scrollbar is ugly" and requested UI-consistent styling.
- Fix:
  - Added reusable `.gradient-scrollbar` utility in `web-ui/src/index.css` and applied it to the drawer scroll shell in `SidebarDrawer.tsx`.
- Preventive rule:
  - Any prominent always-visible scrollbar in core UI panels should receive explicit theme styling and not rely on OS defaults.

#### User Preferences

- New or reinforced preference:
  - Styling details (including scrollbars) must match the overall interface quality bar.
- How it changed execution:
  - Prioritized direct visual polish in production code with immediate build/lint validation.

#### What Worked

- Pattern/check that worked:
  - Utility-class approach (`gradient-scrollbar`) makes it easy to reuse consistent scrollbar styling across other scrollable panel sections.
  - Combining Firefox and WebKit declarations ensures broad browser coverage.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this change.

#### Guardrails For Next Session

- Preflight rule:
  - For UI polish requests, inspect for native browser defaults (scrollbars, focus rings, select arrows) and theme them where they are visually dominant.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If users request thicker or subtler scrollbar contrast, tune width/color alpha in `.gradient-scrollbar` rather than duplicating new classes.

### 2026-02-17 20:49 +11:00 - Scrollbar integrated into rounded drawer shell

#### Task Summary

- Integrated header and scroll body into a single drawer shell so the scrollbar appears inside the panel.
- Ensured rounded bottom corners remain visible regardless of scroll position.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Scroll region still sat outside the main framed shell, making the scrollbar appear detached and corners feel inconsistent.
- Detection:
  - User screenshot highlighted scrollbar placement and requested persistent rounded bottom corners while scrolling.
- Fix:
  - Reworked `SidebarDrawer` to a single `rounded-xl overflow-hidden` container with internal header and body scroller.
- Preventive rule:
  - If users ask for persistent corner shape during scrolling, clipping must happen at the outermost rounded container.

#### User Preferences

- New or reinforced preference:
  - Scrollbar should feel like part of the panel, not adjacent to it.
  - Rounded geometry should remain stable at all scroll offsets.
- How it changed execution:
  - Prioritized container hierarchy/layout over color-only styling tweaks.

#### What Worked

- Pattern/check that worked:
  - One-shell layout with `border-b` header divider gives cleaner structure and deterministic corner clipping.

#### What Did Not Work

- Failed attempt and why:
  - Styling the scrollbar alone without container clipping did not fully solve the visual integration request.

#### Guardrails For Next Session

- Preflight rule:
  - For any scrollable card/panel, confirm the scroll container is nested inside the same rounded element that defines the visual frame.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Optional future polish: reduce nested card framing inside drawer bodies if a flatter visual style is desired.

### 2026-02-17 21:28 +11:00 - Weld typography consistency normalization

#### Task Summary

- Applied a consistent font-size system to the Weld panel (labels, metadata, section headings, inputs, and action text).
- Kept CTA emphasis while reducing random micro-size jumps in the rest of the panel.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Weld UI accumulated mixed ad-hoc text sizes (`text-xs`, `text-[11px]`, `text-[10px]`) without shared typography tokens.
- Detection:
  - User requested consistent styling/sizing and screenshot showed uneven typography rhythm.
- Fix:
  - Added shared weld typography class constants in `App.tsx` and refactored key Weld panel elements to use them.
- Preventive rule:
  - For dense forms, define reusable typographic tokens first, then apply them consistently instead of per-control one-off sizing.

#### User Preferences

- New or reinforced preference:
  - Typography should feel intentionally consistent, not piecemeal.
- How it changed execution:
  - Prioritized text hierarchy cleanup (label/meta/control consistency) immediately after structural layout fixes.

#### What Worked

- Pattern/check that worked:
  - Local constants for panel typography made broad consistency changes safer and easier to review.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this update.

#### Guardrails For Next Session

- Preflight rule:
  - When touching any large panel, run a quick typography pass to ensure no unnecessary size variants remain.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - STEP and Trajectory panels may still contain independent typography choices and can be normalized in a dedicated follow-up.

### 2026-02-17 21:31 +11:00 - Text hierarchy correction for section title vs field label

#### Task Summary

- Adjusted typography hierarchy so `Weld Program` (section title) and `Program Name` (field label) are visually distinct.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Initial typography normalization still left section title and label weights too close, reading as both bold in practice.
- Detection:
  - User feedback called out both lines appearing bold despite hierarchy intent.
- Fix:
  - Set `WELD_LABEL_CLASS` to normal weight and strengthened `WELD_SECTION_TITLE_CLASS` size/contrast for clearer hierarchy.
- Preventive rule:
  - After typographic refactors, verify key adjacent text pairs (section title vs label) in rendered UI, not just by class names.

#### User Preferences

- New or reinforced preference:
  - Visual hierarchy should be obvious; labels should not compete with section headings.
- How it changed execution:
  - Applied immediate token-level correction instead of adding more one-off local class overrides.

#### What Worked

- Pattern/check that worked:
  - Centralized typography constants enabled a quick, low-risk hierarchy adjustment.

#### What Did Not Work

- Failed attempt and why:
  - Equalized sizing pass alone did not guarantee perceived hierarchy when both styles still had elevated weight.

#### Guardrails For Next Session

- Preflight rule:
  - For dense forms, reserve stronger weight/color for section titles and keep field labels at regular weight unless emphasis is intentional.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Consider applying the same heading-vs-label hierarchy tokens to STEP and Trajectory drawers for full consistency.

### 2026-02-17 21:34 +11:00 - Cross-panel typography alignment + living design doc

#### Task Summary

- Extended typography consistency work from Weld to STEP and Trajectory panels.
- Added `web-ui/design.md` as the living design-system document and referenced it from `AGENTS.md`.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Typography tokenization was initially panel-local (`WELD_*`) and not clearly positioned as a shared drawer system.
- Detection:
  - User approved extending hierarchy consistency across all drawer tabs and requested a persistent living design doc.
- Fix:
  - Introduced shared `DRAWER_*` tokens in `App.tsx` and aligned STEP/Trajectory class usage with those tokens.
  - Created `web-ui/design.md` with rules/checklist and linked it from `AGENTS.md`.
- Preventive rule:
  - When UI consistency request spans multiple panels, establish or update a repo-local design source-of-truth before further styling changes.

#### User Preferences

- New or reinforced preference:
  - Consistency should be systematic and documented, not just fixed one screen at a time.
- How it changed execution:
  - Combined implementation changes with living documentation in the same turn.

#### What Worked

- Pattern/check that worked:
  - Shared token strategy (`DRAWER_*`) allowed quick normalization without major component rewrites.
  - A living doc with checklist creates durable guardrails for future UI edits.

#### What Did Not Work

- Failed attempt and why:
  - N/A for this update.

#### Guardrails For Next Session

- Preflight rule:
  - Before editing drawer panel styles, read `web-ui/design.md` and use existing `DRAWER_*` tokens unless intentionally evolving the design system.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Global typography outside drawer panels still may not fully match the new panel system and can be standardized later.

### 2026-02-17 21:43 +11:00 - Hard requirement language for memory-loop completion

#### Task Summary

- Strengthened `AGENTS.md` so updating both `DEVLOG.md` and `AGENT_SCRATCHPAD.md` is explicitly non-optional.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Existing wording listed both files but was not strong enough to prevent potential omission.
- Detection:
  - User explicitly requested stronger emphasis that these tasks must never be left undone.
- Fix:
  - Added MUST language on both workflow bullets and a non-negotiable blocker rule in `AGENTS.md`.
- Preventive rule:
  - If user says "every time", encode it with explicit "MUST" + "blocker" phrasing in the top-level onboarding doc.

#### User Preferences

- New or reinforced preference:
  - Memory-loop updates are mandatory on every meaningful task with zero exceptions.
- How it changed execution:
  - Immediately hardened policy text in `AGENTS.md` and logged the change in both memory files.

#### What Worked

- Pattern/check that worked:
  - Converting soft guidance into explicit completion criteria reduces ambiguity and missed process steps.

#### What Did Not Work

- Failed attempt and why:
  - Soft descriptive wording ("maintain these files") did not clearly communicate non-negotiable enforcement.

#### Guardrails For Next Session

- Preflight rule:
  - Treat absent updates in either `DEVLOG.md` or `AGENT_SCRATCHPAD.md` as a stop condition before final handoff.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None for this doc-policy reinforcement; now explicitly codified.

### 2026-02-17 21:46 +11:00 - Remove nested drawer shell for more usable width

#### Task Summary

- Removed the extra inner full-card shell from drawer panel content to eliminate the double-layer frame.
- Increased usable content room in the drawer without changing the outer shell behavior.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Panel content still had a nested full-shell wrapper (rounded/border/bg/shadow) inside the drawer shell, causing visual duplication.
- Detection:
  - User screenshot highlighted unnecessary double layer and requested more content room.
- Fix:
  - Removed root shell classes from drawer panel roots in `App.tsx` and reduced shelling in `TelemetryCharts.tsx`.
  - Added a permanent "no nested outer shell" rule to `web-ui/design.md`.
- Preventive rule:
  - In drawer UIs, keep one primary shell only; use section cards for grouping, not another full wrapper.

#### User Preferences

- New or reinforced preference:
  - Avoid double framing; prioritize cleaner visual hierarchy and usable space.
- How it changed execution:
  - Applied structural class removal instead of spacing-only patching.

#### What Worked

- Pattern/check that worked:
  - Removing duplicated shell classes immediately reduced visual noise and reclaimed width.

#### What Did Not Work

- Failed attempt and why:
  - Prior refinements (scrollbar, typography) improved polish but did not remove the underlying duplicated-shell structure.

#### Guardrails For Next Session

- Preflight rule:
  - Before finalizing drawer visuals, verify only one full-shell container exists in the panel stack.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Fine-tune section card spacing if certain panel states appear too sparse after shell removal.

### 2026-02-17 21:50 +11:00 - Adaptive drawer height + wider telemetry panel

#### Task Summary

- Changed drawer sizing behavior so short-content panels no longer stretch to full-height.
- Added a wider drawer width variant for telemetry/charts to avoid horizontal overflow.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Forcing drawer to `inset-y` full height made sparse panels (STEP/Trajectory/Telemetry idle) look mostly empty.
- Detection:
  - User screenshots showed excessive empty vertical space and horizontal scrollbar in charts panel.
- Fix:
  - Switched drawer to content-driven height with viewport max-height cap and internal scroll.
  - Added panel-specific width prop and set telemetry to wider width.
  - Added `overflow-x-hidden` in drawer body to suppress unintended sideways scroll.
- Preventive rule:
  - Drawer height should be content-first with max-height constraints; reserve full-height overlays only for intentionally immersive panels.

#### User Preferences

- New or reinforced preference:
  - Keep max-height safety, but avoid unnecessary empty space in light-content tabs.
  - Charts panel should prioritize readable layout over strict shared-width parity.
- How it changed execution:
  - Implemented adaptive layout plus targeted width override rather than a single global sizing rule.

#### What Worked

- Pattern/check that worked:
  - Width variant via prop (`widthClassName`) cleanly supports per-panel layout needs without duplicating drawer component logic.

#### What Did Not Work

- Failed attempt and why:
  - Earlier one-size full-height behavior suited long Weld content but degraded sparse tabs.

#### Guardrails For Next Session

- Preflight rule:
  - Validate each tab in both sparse and dense states before finalizing shared container sizing.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If telemetry charts add more columns/cards, add responsive width tiers rather than reintroducing horizontal scroll.

### 2026-02-17 22:10 +11:00 - Weld drawer baseline + tooltip clipping regression fix

#### Task Summary

- Fixed Weld drawer vertical sizing so its bottom baseline stays aligned with Robot Control.
- Fixed angle-help tooltip clipping by moving it out of the scroll container into a fixed portal overlay.
- Codified these constraints in `web-ui/design.md`.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Drawer sizing logic shifted between content-driven and max-height variants, causing bottom misalignment and visible clipping near footer-adjacent controls.
  - Tooltip was rendered inside an overflowed panel region, so it got clipped/cut off.
- Detection:
  - User screenshots clearly showed the panel extending into terminal/footer region and tooltip content cut off by panel bounds.
- Fix:
  - Anchored drawer with explicit `top-6` + `bottom-6` and `h-full` shell.
  - Rendered angle explainer tooltip via `createPortal(document.body)` with fixed positioning and viewport clamping.
  - Set tooltip to open on the right by default with left fallback only when viewport space is constrained.
- Preventive rule:
  - Never place explainer popovers inside scrolling/clipped containers; use portal overlays for any panel-help UI.
  - For consistency-critical overlays, align by shared anchor insets rather than mixing content-height and max-height modes.

#### User Preferences

- New or reinforced preference:
  - Strong preference for consistent panel baselines and no clipped UI.
  - When regressions are reported with screenshots, prioritize direct fixes over exploratory redesign.
- How it changed execution:
  - Moved from incremental class tweaks to hard layout anchoring + portalized overlay behavior.

#### What Worked

- Pattern/check that worked:
  - Using `absolute top-6 bottom-6` + internal scroll gives stable, predictable panel bounds across dense Weld content.
  - Portal + fixed positioning immediately removed tooltip clipping from drawer overflow constraints.

#### What Did Not Work

- Failed attempt and why:
  - Intermediate max-height-only tuning was not robust; it still produced inconsistent bottoms in real viewport states.

#### Guardrails For Next Session

- Preflight rule:
  - For all floating panels, verify top and bottom anchors against adjacent UI baselines before finalizing.
  - For tooltips/popovers inside drawers, require portal rendering and viewport-bound checks by default.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If additional help popovers are added, they must reuse the same portal + clamp pattern to avoid repeat clipping regressions.

### 2026-02-17 22:24 +11:00 - Weld end-action semantics correction

#### Task Summary

- Corrected weld post-action behavior so `return_to_start` means return to trajectory start/home-start pose (not weld start).
- Added new post-action mode `lift` for a small vertical retract from weld end.
- Synced backend planner semantics, API normalization, and UI enum/options.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Existing `return_to_start` behavior returned to the first weld point, which is semantically wrong for full-trajectory flow.
- Detection:
  - User provided explicit behavior definition + annotated image showing desired home-start target.
- Fix:
  - Removed frontend section-level weld-start return insertion.
  - Implemented backend post-action planning in `command_api.py`:
    - `return_to_start` now routes from weld end back to trajectory start pose (captured at planning start), using a lifted transition.
    - `lift` now performs a vertical retract by transition clearance.
  - Added `lift` normalization in `main.py` and UI type/select handling in `App.tsx`.
- Preventive rule:
  - End-action semantics must be owned by backend planner state (which has true start pose), not pre-baked by frontend geometry assumptions.

#### User Preferences

- New or reinforced preference:
  - "Return to start" must always refer to trajectory/program start, not local weld segment start.
  - Add practical post-weld finishing action(s) like lift for safer motion behavior.
- How it changed execution:
  - Prioritized behavior semantics over UI-only labeling and implemented planner-level logic.

#### What Worked

- Pattern/check that worked:
  - Centralizing end-action logic in backend keeps preview/execution behavior consistent and source-of-truth aligned.

#### What Did Not Work

- Failed attempt and why:
  - Previous frontend-only return transition generation could not represent trajectory start correctly because it lacked planner start-pose context.

#### Guardrails For Next Session

- Preflight rule:
  - For any motion semantic label (`return`, `home`, `safe`), verify mapping against planner/control definitions before shipping UI text.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If a dedicated configurable "home" waypoint is introduced later, `return_to_start` should explicitly choose between recorded trajectory start vs configured home target.

### 2026-02-17 22:57 +11:00 - Weld-program load must clear stale preview state

#### Task Summary

- Fixed stale path rendering when loading saved weld programs that do not include a planned trajectory payload.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Loading `test_0` could leave the previous preview path visible because restore logic only set new preview when present, but did not clear old preview when missing.
- Detection:
  - User reported loaded program retained prior plan/path visuals.
- Fix:
  - In weld-program restore path, explicitly clear `previewPlan` + `plannerPoints` when `pendingWeldProgramRestore.previewPlan` is null.
  - Also clear `previewPlan` + `plannerPoints` immediately after successful program payload validation so stale geometry is removed during restore.
- Preventive rule:
  - Any optional payload restore must include explicit "else clear" handling for stateful visuals.

#### User Preferences

- New or reinforced preference:
  - Loading a saved program must never retain stale path overlays from previous sessions/plans.
- How it changed execution:
  - Prioritized deterministic state reset behavior over preserving transient UI visuals between loads.

#### What Worked

- Pattern/check that worked:
  - Clearing both source states (`previewPlan` and `plannerPoints`) ensures visual path fallback logic cannot display old geometry.

#### What Did Not Work

- Failed attempt and why:
  - Implicit state replacement only on "truthy new plan" left stale values alive in null-plan restore cases.

#### Guardrails For Next Session

- Preflight rule:
  - For every restore/load flow, enumerate each visual state and handle both "present" and "absent" payload branches explicitly.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If additional derived visual states are added (e.g., cached highlight ranges), ensure they are reset alongside preview state on load.

### 2026-02-17 23:29 +11:00 - Weld-run visual flicker spike filtering

#### Task Summary

- Added runtime telemetry filtering to prevent single-frame snap-back/flicker artifacts in arm visualization during weld execution.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Visualization occasionally jumped to a stale weld-start-like pose for one frame while actual motion continued, creating star-like flicker trails.
- Detection:
  - User screenshot showed repeated visual spokes from a fixed point during weld run.
- Fix:
  - Added telemetry guards in `web-ui/src/App.tsx`:
    - drop out-of-order packets using source telemetry timestamp (`t`),
    - reject implausible one-frame joint spikes (`maxJump > 0.8 rad` within `<=0.25s`) likely caused by stale/outlier packets.
  - Reset telemetry filter refs on disconnect.
- Preventive rule:
  - Treat UI pose stream as potentially noisy/reordered; enforce monotonic timestamp acceptance and outlier rejection before rendering.

#### User Preferences

- New or reinforced preference:
  - Weld execution visualization must remain stable and trustworthy; no transient “teleport” artifacts.
- How it changed execution:
  - Added ingestion-layer robustness rather than only tuning rendering interpolation.

#### What Worked

- Pattern/check that worked:
  - Filtering at message-ingest stage avoids contaminating both immediate and smoothed pose updates.

#### What Did Not Work

- Failed attempt and why:
  - Relying on smoothing alone cannot prevent stale packet flashes because stale targets still get applied instantly.

#### Guardrails For Next Session

- Preflight rule:
  - For realtime robot UI streams, always define packet-order and spike-handling policy explicitly.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If a second legitimate telemetry source is intentionally mixed in future, add explicit source tagging/selection instead of relying on timestamp-only arbitration.

### 2026-02-18 00:08 +11:00 - Weld program run gating + start-from-current execution

#### Task Summary

- Fixed inability to run loaded weld programs when draft restoration is missing/invalid but a runnable preview trajectory exists.
- Enforced run-time re-planning from current robot state for weld preview execution.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Run button in Weld panel was gated on `draft` existence instead of actual runnable preview presence, blocking execution for some loaded programs.
  - Weld preview run path used cached planning (`use_cache: true`), which can execute stale joint paths not guaranteed to reflect current robot state.
- Detection:
  - User loaded `test_02` and observed run action unavailable despite loaded trajectory/waypoints.
- Fix:
  - Updated Weld panel run gating to use `canRunPreview` (`Boolean(previewPlan?.name)`) rather than `draft`.
  - Switched preview run request to `use_cache: false` so backend re-plans from current state, naturally including current->start motion.
- Preventive rule:
  - UI action enablement must track actual execution prerequisites (runnable plan), not adjacent editor state (draft availability).

#### User Preferences

- New or reinforced preference:
  - Loaded weld programs should be runnable even when edge-edit context is unavailable.
  - Execution should start from current robot pose with an explicit approach to program start.
- How it changed execution:
  - Prioritized run-time correctness and operability over cache-first speed.

#### What Worked

- Pattern/check that worked:
  - Decoupling run enablement from `draft` immediately restores operability for loaded plans.
  - Re-plan from current state guarantees start approach behavior without additional special-case injection.

#### What Did Not Work

- Failed attempt and why:
  - Previous cache-first preview execution assumed planning-time and run-time robot state equivalence.

#### Guardrails For Next Session

- Preflight rule:
  - For any "Run" control, verify its disabled condition maps exactly to runtime required data, then confirm loaded-from-file flows satisfy that condition.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If run latency becomes noticeable due to re-planning, introduce an explicit "replan-on-run" toggle with clear UX semantics.

### 2026-02-18 00:18 +11:00 - Panel-aware drawer height mode (keep weld full, un-stretch others)

#### Task Summary

- Fixed the drawer height regression where STEP / Trajectory / Telemetry looked stretched to the bottom with large empty space.
- Preserved Weld Planning as full-height because that dense workflow benefits from a stable full overlay band.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - A global full-height drawer shell (`h-full` inside `top-6 bottom-6`) was applied to all tabs, which regressed sparse panels into visibly stretched empty containers.
- Detection:
  - User screenshots showed STEP / Trajectory / Live Charts extending to the bottom while Weld looked acceptable.
- Fix:
  - Added `heightMode` to `SidebarDrawer`:
    - `full` for Weld (`h-full`),
    - `content` for STEP / Trajectory / Telemetry (`max-h-full` with internal scrolling preserved).
  - Kept common overlay lane (`top-6 bottom-6`) and moved pointer-event handling to panel shell so empty transparent lane area does not block workspace interaction.
  - Updated `web-ui/design.md` rules to codify mixed-mode behavior.
- Preventive rule:
  - Do not apply one global drawer height strategy across panels with different content density; explicitly model panel height intent (content-fit vs full-height).

#### User Preferences

- New or reinforced preference:
  - Weld panel baseline/behavior is acceptable and should remain unchanged when fixing other tabs.
  - Sparse panels should not appear stretched to the viewport bottom.
- How it changed execution:
  - Used panel-specific height mode instead of another global class toggle.

#### What Worked

- Pattern/check that worked:
  - Shared wrapper + per-panel shell height mode is a low-risk way to preserve weld behavior while fixing sparse tabs.
  - Keeping internal scroll inside the same shell retained dense-content safety without reintroducing clipping.

#### What Did Not Work

- Failed attempt and why:
  - Previous "all panels full-height" rule solved weld alignment but caused immediate UX regressions for sparse tabs.

#### Guardrails For Next Session

- Preflight rule:
  - For shared drawer/container refactors, validate all tabs in both sparse and dense states before finalizing.
  - If one panel is intentionally different, encode that in props rather than ad-hoc class forks.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Confirm in live UI that click-through around non-full-height drawer shell feels natural at narrow and wide viewport sizes.

### 2026-02-18 01:13 +11:00 - Local repo skill installation into Codex home

#### Task Summary

- Installed all local skills from `.cursor/skills` into `C:\Users\angus\.codex\skills`.
- Verified destination skill set matches source local skills and complies with AGENTS workflow logging requirements.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Initial assumption from AGENTS list suggested `.cursor/skills-cursor` might also require installation.
- Detection:
  - Repository inspection showed `.cursor` contains only `rules` and `skills`; no `.cursor/skills-cursor` directory exists in this workspace.
- Fix:
  - Scoped installation to `.cursor/skills` folders that contain `SKILL.md`, then audited source-vs-destination skill names.
- Preventive rule:
  - Before bulk install/sync operations, verify referenced directories exist in the current repo snapshot rather than relying only on docs.

#### User Preferences

- New or reinforced preference:
  - Use `AGENTS.md` as startup context and install all repo-local skills when requested.
- How it changed execution:
  - Followed skill-installer guidance for workflow framing, then performed local copy/install for all `.cursor/skills` folders.

#### What Worked

- Pattern/check that worked:
  - Filtering source directories by existence of `SKILL.md` prevents copying non-skill folders.
  - Compare-object audit after install quickly confirms there are no missing skill names.

#### What Did Not Work

- Failed attempt and why:
  - None in this task; install path and audit succeeded on first pass.

#### Guardrails For Next Session

- Preflight rule:
  - For skill installation requests, check both `.cursor/skills` and any AGENTS-referenced paths, but install only paths present in the active workspace.
  - Always finish by updating both `DEVLOG.md` and `AGENT_SCRATCHPAD.md` before handoff.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Codex usually loads skills at startup; restart Codex after installation to ensure all newly installed skills are available.

### 2026-02-18 01:17 +11:00 - Weld preview run should use high-fidelity cache, not sparse endpoint re-plan

#### Task Summary

- Fixed mismatch where weld preview execution diverged from previewed/interpolated path because run used endpoint re-planning.
- Added explicit cache-readiness handling for weld runs and clarified UI wording around editable weld points.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Run path used `/trajectory/run` with `use_cache: false` globally, so weld trajectories were rebuilt from sparse `trajectory.moves` endpoints (few `move_absolute` nodes) instead of using the high-fidelity cached weld path.
- Detection:
  - User screenshot + report showed large gap between expected weld curve and simulated run path, while Program Tree showed only a handful of moves.
- Fix:
  - In `web-ui/src/App.tsx`:
    - added `weldPreviewCacheReady` tracking,
    - made weld runs use `use_cache: true` so backend executes full planned steps cache,
    - when weld cache is stale, auto-refresh preview via `requestWeldPreview` before run,
    - reset cache readiness on clear/disconnect/load transitions.
  - Added UI copy update (`Editable Control Points`) to avoid implying that the list is every interpolated sample.
  - In `web-ui/src/previewUtils.ts`, surfaced path sample count in Program Tree subtitle for better operator visibility.
- Preventive rule:
  - For trajectory systems with both coarse declarative moves and dense cached execution plans, never treat them as interchangeable at run time for weld/high-fidelity workflows.

#### User Preferences

- New or reinforced preference:
  - Displayed/selected weld path and executed weld path must match; no hidden downsampling that changes robot motion.
  - If a mismatch is suspected, prioritize run-time correctness over prior convenience assumptions.
- How it changed execution:
  - Weld run path is now anchored to planned cache validity, with explicit stale-cache refresh.

#### What Worked

- Pattern/check that worked:
  - Keeping non-weld behavior unchanged while branching weld execution policy minimized regression risk.
  - Cache readiness flag cleanly coordinates plan/run state across clear/load/restore flows.

#### What Did Not Work

- Failed attempt and why:
  - Earlier global `use_cache: false` approach improved “start from current pose” semantics but broke weld trajectory fidelity by collapsing to endpoint commands.

#### Guardrails For Next Session

- Preflight rule:
  - If Program Tree move count is far smaller than expected path complexity, verify whether run path uses cached planned steps or endpoint re-planning.
  - For weld runs, treat cache freshness as a first-class precondition.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Program Tree still emphasizes operation-level moves; consider adding a dedicated interpolated-path inspector node if operators need per-sample introspection.

### 2026-02-18 01:28 +11:00 - Exact path visibility: remove planner payload downsampling + tree from path samples

#### Task Summary

- Implemented full-fidelity path visibility so Program Tree can show exact planned path samples instead of trimmed endpoint-derived approximations.
- Removed planner payload downsampling that previously hid intermediate cartesian samples.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - UI path inspection relied on lower-resolution representations (coarse move endpoints and downsampled cartesian payload), creating a trust gap for weld motion verification.
- Detection:
  - User explicitly rejected trimmed output and required exact movement visibility in Program Tree.
- Fix:
  - In `src/gradient_os/arm_controller/command_api.py`, removed `sample_stride` downsampling in `_append_cartesian_samples` so payload carries full planned cartesian samples.
  - In `web-ui/src/previewUtils.ts`, rewired `buildProgramTree` to use `plan.pathPoints` as primary execution tree content:
    - `Exact Path Samples` in grouped mode,
    - `Execution Path (Exact)` in chronological mode,
    - preserved control-point and controller-command groups as secondary views.
- Preventive rule:
  - For robotics inspection UIs, never downsample the authoritative displayed path unless user explicitly opts into a performance mode.

#### User Preferences

- New or reinforced preference:
  - Program Tree must reflect exactly where robot will move; no hidden trimming.
  - Coarse representations are acceptable only as supplemental metadata, not as the primary motion truth.
- How it changed execution:
  - Prioritized operator-trust visibility over payload compactness by default.

#### What Worked

- Pattern/check that worked:
  - Maintaining dual views (exact path + command metadata) preserved debugging utility without compromising motion fidelity visibility.

#### What Did Not Work

- Failed attempt and why:
  - Prior “show move count + path sample count” transparency helped diagnostics but did not satisfy requirement for exact per-sample tree inspection.

#### Guardrails For Next Session

- Preflight rule:
  - If a user asks for exact robot path visibility, ensure both backend payload and frontend tree model are fidelity-preserving end-to-end.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Extremely long paths can create large tree DOMs; prefer virtualization if performance issues appear, not sample trimming.

### 2026-02-18 01:42 +11:00 - Remove approximate segment highlighting when exact mapping is unavailable

#### Task Summary

- Removed approximate weld-segment path highlighting from Program Tree to keep display semantics strictly truthful.
- Preserved command-level tree data only as reference metadata when exact path samples already exist.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Weld segment nodes were still assigning proportional `pathRange` guesses, which could imply false precision even after exact-path sample support was added.
- Detection:
  - User requirement emphasized exact reflection between Program Tree and rendered path; inferred ranges violate that constraint.
- Fix:
  - Removed weld segment `pathRange` inference from `web-ui/src/previewUtils.ts`.
  - Weld segment nodes now only target weld-edge focus (`weldSegmentEdgeId`) without claiming exact path subset.
  - Simplified command grouping so command nodes are clearly labeled as reference when exact path nodes are present.
- Preventive rule:
  - If exact mapping data is not available, do not synthesize approximate range overlays in robotics inspection views.

#### User Preferences

- New or reinforced preference:
  - Program Tree must never imply precision it does not actually have.
  - Exact path truth takes precedence over convenience grouping.
- How it changed execution:
  - Removed inferred path focus fields unless backed by exact sample indices.

#### What Worked

- Pattern/check that worked:
  - Separating "exact execution samples" from "controller command metadata" keeps debugging utility while preserving trust.

#### What Did Not Work

- Failed attempt and why:
  - Earlier proportional segment-range mapping was useful visually but not acceptable for exactness-critical inspection.

#### Guardrails For Next Session

- Preflight rule:
  - Any tree node that highlights path must be backed by explicit deterministic indices from planner output; otherwise omit the highlight mapping.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If per-weld-segment exact highlighting is required later, backend should return section-to-sample index spans as part of planner payload.

### 2026-02-18 01:53 +11:00 - Waypoint editing migrated from Weld drawer into Program Tree

#### Task Summary

- Removed the `Editable Control Points` editor block from Weld drawer UI.
- Implemented Program Tree-native control-point editing flow so waypoint edits are driven from selected tree nodes.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Drawer-local waypoint editor duplicated editing context and conflicted with requirement that tree/path inspection be the source of truth.
- Detection:
  - User explicitly requested complete removal from drawer and routing edits through Program Tree.
- Fix:
  - In `web-ui/src/App.tsx`, removed Weld panel waypoint-edit props/UI and added tree-driven handlers:
    - edit selected control point coordinates,
    - add/remove control point,
    - apply edits via weld replan (or generic point replan for non-weld).
  - In `web-ui/src/components/ProgramFeatureTree.tsx`, added an inline editor section that appears when a `control_point_*` node is selected.
- Preventive rule:
  - Avoid duplicated edit surfaces for the same motion data; keep one primary editing interaction path tied to the inspection model.

#### User Preferences

- New or reinforced preference:
  - Waypoint editing should be centralized in Program Tree, not scattered in panel forms.
  - The path/tree workflow must remain coherent and trustworthy for motion changes.
- How it changed execution:
  - Shifted from drawer-local form controls to selection-driven tree editing.

#### What Worked

- Pattern/check that worked:
  - Reusing existing waypoint state and planner callbacks minimized risk while moving the UI interaction surface.

#### What Did Not Work

- Failed attempt and why:
  - Keeping both drawer and tree editors would continue UX ambiguity and contradict user’s “single source” editing requirement.

#### Guardrails For Next Session

- Preflight rule:
  - When a user requests “drive from X only,” remove parallel controls in other panels rather than trying to keep them synchronized ad hoc.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If users miss discoverability, add small guidance text in Program Tree when no control point is selected.

### 2026-02-18 01:54 +11:00 - Tree node panel focus should follow weld context

#### Task Summary

- Adjusted Program Tree node focus target so selecting control/path nodes in weld plans keeps interaction in weld context.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - After moving editing to Program Tree, control-point nodes still targeted trajectory panel by default, which could feel inconsistent for weld-first workflows.
- Detection:
  - Post-change review of `ProgramNode.focus.openPanel` mapping in `previewUtils.ts`.
- Fix:
  - Set default tree-node focus panel dynamically:
    - weld plan (`trajectory.weld` present) -> `"weld"`,
    - otherwise -> `"trajectory"`.
- Preventive rule:
  - When relocating an editing surface, re-check navigation/focus semantics so node selection context matches the new workflow.

#### User Preferences

- New or reinforced preference:
  - Program Tree should be the primary interaction context for waypoint edits.
- How it changed execution:
  - Ensured tree node selection supports weld-context editing rather than bouncing users to trajectory panel unintentionally.

#### What Worked

- Pattern/check that worked:
  - Deriving a `defaultFocusPanel` once in tree builder avoided repeated branching and kept node focus consistent.

#### What Did Not Work

- Failed attempt and why:
  - Static `openPanel: "trajectory"` across all plans was too rigid once weld editing moved to tree.

#### Guardrails For Next Session

- Preflight rule:
  - Any time node semantics change, validate both data fidelity and panel-navigation behavior together.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - If users want tree selection decoupled from panel switching, add a toggle for “selection-only mode” in settings.

### 2026-02-18 02:00 +11:00 - Preview waypoint marker size reduced to 1mm

#### Task Summary

- Reduced yellow preview waypoint sphere radius to 1mm for less visual clutter in the scene.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Waypoint spheres were oversized for dense weld-path inspection.
- Detection:
  - User requested “much smaller, maybe 1mm radius.”
- Fix:
  - Updated marker mesh radius in `web-ui/src/ArmVisualizer.tsx` from `0.008` to `0.001` meters in the preview path marker block.
- Preventive rule:
  - For dense robot path overlays, keep default markers small enough to avoid obscuring the path geometry.

#### User Preferences

- New or reinforced preference:
  - Preview waypoint markers should be visually subtle and not dominate the path view.
- How it changed execution:
  - Applied a direct geometry-radius change instead of additional styling complexity.

#### What Worked

- Pattern/check that worked:
  - Single-parameter radius change in the marker geometry cleanly addressed the request.

#### What Did Not Work

- Failed attempt and why:
  - None in this task.

#### Guardrails For Next Session

- Preflight rule:
  - When adjusting 3D markers, treat units as meters and validate requested real-world sizing directly in geometry values.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Tiny markers may be hard to pick out at very wide zoom; consider optional user-adjustable marker scale if requested.

### 2026-02-18 02:04 +11:00 - Weld return_to_start must replan from current pre-run pose every run

#### Task Summary

- Fixed critical weld end-action regression where `return_to_start` could resolve to stale/wrong targets (including weld start) if an old preview plan cache was reused.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Weld run path could execute cached plan without guaranteed per-run replan from current robot state, so `return_to_start` target was not always the actual pre-weld run start pose.
- Detection:
  - User reported repeated return to weld start despite selecting `Return to trajectory start`.
- Fix:
  - In `web-ui/src/App.tsx`, updated weld run logic in `handleRunPreview`:
    - always call `requestWeldPreview(weldDraft)` immediately before running weld preview,
    - then execute with `use_cache: true` against the just-refreshed plan.
  - This forces backend planner to recapture current start pose each run and regenerate post-action transitions accordingly.
- Preventive rule:
  - For semantics that depend on runtime start context (like `return_to_start`), never allow weld execution to skip replan on run.

#### User Preferences

- New or reinforced preference:
  - `Return to trajectory start` must mean “the robot pose right before this weld run starts,” never weld-start fallback.
- How it changed execution:
  - Prioritized semantic correctness and determinism over cache-only run latency.

#### What Worked

- Pattern/check that worked:
  - Replan-then-run for weld previews preserves high-fidelity path execution while guaranteeing correct start-context capture.

#### What Did Not Work

- Failed attempt and why:
  - Conditional cache refresh based on stale flags was insufficient for strict runtime start semantics.

#### Guardrails For Next Session

- Preflight rule:
  - If an end-action references “start” and operator intent is per-run, enforce replan-at-run regardless of prior cache freshness.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Additional replan time before each weld run is expected; optimize only if needed, without compromising start-context correctness.

### 2026-02-18 02:19 +11:00 - Stabilize weld run-state lifecycle and isolate jog loop

#### Task Summary

- Fixed a backend execution-state bug that could clear motion state mid-trajectory and allow control-loop contention.
- Added trajectory-start guard to stop active jog mode before weld/trajectory playback.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Nested step execution in `trajectory_execution._execute_joint_path` reused `_open_loop_executor_thread` which could clear `trajectory_state` (`is_running`, `thread`) during a still-active multi-step weld run.
- Detection:
  - User-reported jitter/snap behavior during weld execution; code audit showed executor cleanup was tied only to thread identity, which matches nested step execution.
- Fix:
  - Added `owns_trajectory_state` parameter to open/closed executors and disabled state cleanup for nested step calls.
  - Updated `handle_run_trajectory` to stop jog mode before run and abort if jog remains active.
- Preventive rule:
  - Any low-level executor used both standalone and nested must have explicit lifecycle ownership; never let nested calls mutate global run flags.

#### User Preferences

- New or reinforced preference:
  - Execution correctness and deterministic robot behavior are higher priority than convenience/background control loops.
  - User expects direct fixes, not speculative discussion.
- How it changed execution:
  - Focused on controller run-state/jog isolation, implemented concrete backend patches first, then validated syntax/lints.

#### What Worked

- Pattern/check that worked:
  - Tracing end-to-end from UI symptom to controller state transitions exposed the lifecycle race quickly.

#### What Did Not Work

- Failed attempt and why:
  - Looking only at weld planning math was insufficient; the dominant issue was runtime executor/jog interaction, not weld geometry sampling itself.

#### Guardrails For Next Session

- Preflight rule:
  - For motion bugs with "random snaps/jitter," inspect global motion flags (`is_running`, `is_jogging`, `thread`) and thread cleanup points before tuning planners.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Validate with live weld run in simulator to confirm no residual jitter under active UI polling and no unintended return-to-weld-start behavior.

### 2026-02-18 02:26 +11:00 - Runtime confirmation: execution-state fix is primary root cause

#### Task Summary

- Recorded user confirmation that weld execution now behaves correctly after the controller patch.
- Captured that the issue previously occurred even with jog disabled, reinforcing execution-state lifecycle as primary fault domain.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Earlier suspicion that jog could be the sole cause was incomplete.
- Detection:
  - User explicitly reported prior reproduction with jog disabled.
- Fix:
  - Keep execution-state lifecycle fix as the core resolution.
  - Retain jog-stop guard as non-invasive protection against future control-loop contention.
- Preventive rule:
  - For motion jitter/snap bugs, prioritize controller state lifecycle and thread ownership analysis before attributing solely to UI-side control streams.

#### User Preferences

- New or reinforced preference:
  - Preserve practical safety guards if they do not add downside, even when not the primary fix.
- How it changed execution:
  - Kept jog isolation check in place as defense-in-depth rather than removing it after root-cause confirmation.

#### What Worked

- Pattern/check that worked:
  - Combining code-level race fix with runtime user validation quickly converged on true root cause.

#### What Did Not Work

- Failed attempt and why:
  - Treating jog contention as the only likely source would have underexplained the jog-disabled reproductions.

#### Guardrails For Next Session

- Preflight rule:
  - If a bug reproduces with a suspected subsystem disabled, immediately elevate investigation to shared/global state and thread-lifecycle paths.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None immediate; monitor for recurrence under long runs or repeated run/stop cycles.

### 2026-02-18 11:47 +11:00 - README refresh for merge readiness

#### Task Summary

- Added a root repository `README.md` and refreshed `web-ui/README.md` to reflect current product behavior.
- Prepared branch-level merge commit message guidance.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake:
  - Assuming a root README existed would have left the “main repo readme” request partially done.
- Detection:
  - File check showed no `README.md` at repository root.
- Fix:
  - Created root `README.md` and updated `web-ui/README.md` with current architecture/workflow notes.
- Preventive rule:
  - For docs requests, verify file existence first and create missing canonical docs rather than only editing submodule docs.

#### User Preferences

- New or reinforced preference:
  - Wants merge-ready artifacts: clear commit messaging plus up-to-date top-level and UI docs.
- How it changed execution:
  - Prioritized practical documentation updates and concise merge messaging over deep code changes.

#### What Worked

- Pattern/check that worked:
  - Pairing root + feature-area README updates keeps main-branch handoff clearer for maintainers/operators.

#### What Did Not Work

- Failed attempt and why:
  - None in this step.

#### Guardrails For Next Session

- Preflight rule:
  - When asked for "main repo README," explicitly confirm root-level presence and update/create accordingly.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - Consider later consolidation between `README.md`, `AGENTS.md`, and `docs/README.md` to reduce duplicated startup guidance.

### 2026-02-18 11:55 +11:00 - Main README clarification: docs/README is canonical

#### Task Summary

- Updated `docs/README.md` after user clarified this is the canonical "main README" for repo-level documentation.
- Built a comprehensive commit-message draft based on full branch diff context rather than only current unstaged files.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Initial README update targeted root-level docs first; user clarified canonical main README is `docs/README.md`.
- Detection:
  - Direct user correction in follow-up message.
- Fix:
  - Added a dedicated `STEP_LOADER Branch Highlights` section in `docs/README.md` with end-to-end scope summary.
- Preventive rule:
  - In this repo, treat `docs/README.md` as the primary documentation entrypoint unless user asks otherwise.

#### User Preferences

- New or reinforced preference:
  - Wants branch merge materials to be comprehensive and grounded in the full branch scope.
- How it changed execution:
  - Used `master..HEAD` log/stat context before drafting commit message language.

#### What Worked

- Pattern/check that worked:
  - Pairing user clarification with git-range analysis produced accurate high-level change framing.

#### What Did Not Work

- Failed attempt and why:
  - A root-only README update was insufficient for this repository's doc convention.

#### Guardrails For Next Session

- Preflight rule:
  - For merge/prep requests, confirm canonical docs path and summarize against `base..HEAD` rather than local unstaged delta only.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None immediate.

### 2026-02-18 11:59 +11:00 - docs/README rewritten as true onboarding entrypoint

#### Task Summary

- Replaced `docs/README.md` content with newcomer-first documentation: features, system function, and usage workflow.
- Removed release-note style sectioning that did not match the file's purpose.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Prior update style emphasized branch-change summaries instead of serving as a practical start guide.
- Detection:
  - Explicit user correction on expected README role and tone.
- Fix:
  - Full rewrite of `docs/README.md` around onboarding flow and operational usage.
- Preventive rule:
  - For canonical README files, optimize for "what it is / how it works / how to use it" before changelog-style content.

#### User Preferences

- New or reinforced preference:
  - README must function as the primary onboarding document for new repo users.
- How it changed execution:
  - Shifted from patching sections to a complete structure reset aligned to onboarding intent.

#### What Worked

- Pattern/check that worked:
  - Rebuilding the file from scratch avoided carrying over conflicting structure and tone.

#### What Did Not Work

- Failed attempt and why:
  - Incremental edits against prior structure kept reintroducing non-onboarding framing.

#### Guardrails For Next Session

- Preflight rule:
  - Before editing a "main README", define target reader and first-use journey explicitly, then shape sections around that path.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None immediate.

### 2026-02-18 12:28 +11:00 - Diagram renderer compatibility fix only

#### Task Summary

- Applied targeted fixes to Mermaid blocks in `docs/README.md` so diagrams render in the repo preview environment.

#### Mistakes And Fixes

- Source: `[user]`
- Mistake:
  - Diagram syntax was too permissive/complex for the active markdown renderer and produced "No diagram type detected" errors.
- Detection:
  - User screenshots showed Mermaid parser failures in rendered README sections.
- Fix:
  - Rewrote Mermaid blocks with strict `flowchart TD` and simplified `sequenceDiagram` content.
  - Removed HTML line breaks and complex quoted labels from diagram text.
- Preventive rule:
  - For README diagrams, prefer conservative Mermaid syntax over decorative labels.

#### User Preferences

- New or reinforced preference:
  - Scope must stay exactly on requested fix when user asks for a targeted patch.
- How it changed execution:
  - Limited edits to diagram blocks only.

#### What Worked

- Pattern/check that worked:
  - Re-typing diagram blocks from scratch prevented hidden syntax issues from surviving.

#### What Did Not Work

- Failed attempt and why:
  - None in this step.

#### Guardrails For Next Session

- Preflight rule:
  - When diagrams fail, first simplify to minimal valid Mermaid syntax before broader doc edits.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - None immediate.

### 2026-09-05 — Sprint 01 electronics + container USB passthrough

#### Environment
- Working inside the OpenChamber container on `pi5-sbc-01` (aarch64, Ubuntu 24.04, 4 GB RAM).
- Repo at `/home/ubuntu/workspaces/GradientOS` (mounted from host `/dev/mmcblk0p2`).
- Container runs as `uid=1000(ubuntu) gid=1000(ubuntu) groups=1000(ubuntu),20(dialout)`, non-privileged.
- No `.venv`, no `pip`, no `uv`, no build tools inside the container. The repo has a C++ IK solver (scikit-build-core + pybind11) that needs `build-essential cmake python3-dev`.

#### Mistakes / Near-Misses
- Initially assumed I was in a sandboxed environment without USB access. I was actually inside the target container with the passthrough already working. Lesson: run `ls -l /dev/serial/ch340 && hostname && id` early to verify environment when USB passthrough is involved.
- The sprint doc estimated idle current at 50-200mA; actual was 299mA. Not a mistake, but the estimate range in the docs is low for a 12V STS3215.

#### User Preferences
- User wants to run GradientOS inside the container (not on the Pi host). Chose to rebuild the Dockerfile rather than run on the host.
- User asks for explanations of hardware controls (OCP vs amperage, signal level slider) — provide concrete, practical guidance, not just definitions.
- User wants Cursor to handle the Dockerfile rebuild — provide complete, copy-pasteable instructions.
- User declined to pick Design A vs B without explanation; wanted help deciding. Recommendation given (Design B), user accepted.

#### What Worked
- Design B USB passthrough: udev mirror to `/dev/openchamber` (devtmpfs, not `/run` which is `nodev`), bind-mounted as `/dev/serial`. Container sees `/dev/serial/ch340` (stable alias). No PTY/shm overlay risk.
- `device_cgroup_rules: c 188:* rwm` is load-bearing on cgroup v2 — the node is visible without it but every open() fails with EACCES.
- `group_add: ["20"]` kept as belt-and-braces even though mirrored node is owned `1000:1000`.
- pyserial 3.5 installed as `python3-serial` in the last RUN layer — 19s cache hit, no node/npm/opencode layer invalidation.

#### Guardrails For Next Session
- The container has no build tools. Before trying to run GradientOS, the Dockerfile must be rebuilt with `build-essential cmake python3-dev` + `uv`. Instructions are in the Cursor handoff (this session's earlier message).
- `SERIAL_PORT=/dev/serial/ch340` env var is required — pyserial `list_ports.comports()` returns empty inside the container because the node is in `/dev/serial/` not `/dev/ttyUSB*`.
- Do not move the udev mirror directory back to `/run` or `/tmp` — they are mounted `nodev` and device nodes will fail to open with EACCES.
- Do not change `ports:` lines in docker-compose.yml — the boot script greps the tailnet IP by regex.
- `OPENCODE_VERSION` and `OPENCHAMBER_VERSION` are unpinned in `.env` — any cache miss on node/npm layers would upgrade them. Pin to 1.18.25 / 1.21.1 before a full rebuild.

#### Follow-Ups / Risks
- Physical USB unplug/replug test still pending.
- Reboot test pending (tmpfiles recreation of `/dev/openchamber`).
- GradientOS venv setup in container blocked on Dockerfile rebuild.
- Sprint 02 (Servo Protocol Validation) is next — needs the venv working first.

## Sprint 02 Part A — servo motion + docs (2026-09-05)

#### Context
- User created `SERVO-NOTES.md` at `/home/ubuntu/workspaces/SERVO-NOTES.md` (outside the repo checkout, but inside the workspace parent). Container CAN read it — it lives at the workspace parent, not a host mount.
- Notes are authoritative for driving this specific servo. Container paths, measured values, safe-move recipe, gotchas all confirmed.

#### What Happened
- User reported amperage change but no visible movement from the first session's 5° move (~55 counts). Suspicion: move too small to see, or encoder moved but shaft didn't.
- Ran safe reads first (no motion): confirmed servo healthy at 4016, torque 0, status 0x0.
- Ran a single 10° downward move with 200ms telemetry sampling: position changed in real-time (3995 -> 3927 -> 3905), load peaked at 96, settled at 24. User confirmed visible movement.
- Ran 3× back-and-forth 10° moves: all six legs succeeded at 9.84°/112 counts, zero errors, returned to start exactly. User confirmed all six visible.
- This was after an unplug + replug — confirms safe-move recipe works cold (RAM defaults, torque off at start).

#### Mistakes / Near-Misses
- Initial "done" claim (from prior session) was premature — user hadn't seen movement. The 5° move was real (encoder moved 55 counts) but too small to be visually confirmable. Lesson: for first motion validation, use a move large enough to be unambiguous (>=10°), not the minimum the sprint doc suggests.
- The SERVO-NOTES.md status section claimed Part A code was done. It was — but "done" should mean "user-confirmed visible movement", not just "register changed". 

#### User Preferences
- User wants to see motion before trusting it. Always ask before commanding motion, and use a visible move size (>=10°) for validation.
- User confirmed they watched the bench PSU during moves. Continue to ask before motion.

#### What Worked
- Safe-move recipe (seed goal to present, set accel/speed first, verify goal readback, then move) works reliably including from cold start.
- 200ms telemetry sampling during the move gives a clear motion trace (position + load + speed + torque) that distinguishes "real move" from "register nudged".
- Live `print` with `python -u` gives real-time output during moves — essential for watching motion in progress.

#### Guardrails For Next Session
- `SERVO-NOTES.md` lives at `/home/ubuntu/workspaces/SERVO-NOTES.md` (workspace parent, NOT in the GradientOS checkout). It is readable from the container. Trust it over datasheets for this specific servo.
- Always move downward (toward 2048). Resting position is ~4016-4072; only ~7° upward headroom.
- Use >=10° moves for visual validation; 5° is too small to confirm physically.
- Register `0x45` (current) is not trustworthy on firmware 3.10. Use bench PSU for current readings.
- Part A docs are now filled in. Part B (HLS3950) is next — need to find the HLS protocol, determine physical interface (TTL vs RS485), and run the same validation sequence.

#### Follow-Ups / Risks
- PSU current figures still needed (idle/move/stall) — must come from bench PSU readout, not register.
- HLS3950 protocol entirely unknown — Part B may require logic analyzer capture if no docs exist.
- The full arm needs 9 servos (IDs 10,20,21,30,31,40,50,60,100); only ID 1 exists on this bench.

#### Jerkiness Diagnosis Session (2026-09-08)

**Root cause found (high confidence):** Trajectory executors stream setpoints at speed=4095 (MAX), accel=0 (MAX). Home button works because it sends a single command at speed=500, accel=500, letting the Feetech servo's internal trapezoidal planner handle the motion. The streaming path bypasses the servo's planner entirely, causing micro-jolts 100×/sec that excite backlash and create oscillation/spring behavior.

**Key code locations:**
- `trajectory_execution.py:744-746` — open-loop precompute with `ENCODER_RESOLUTION, 0`
- `trajectory_execution.py:1061` — closed-loop command with `encoder_max, 0`
- `trajectory_execution.py:1041-1043` — software PID intentionally disabled (commands raw target)
- `run_controller.py:997` — Home path uses `DEFAULT_SERVO_SPEED=500, DEFAULT_SERVO_ACCEL=500`

**Guardrails for next session:**
- User wants to work through theories together, not just have fixes applied. Pitch theories, discuss, then implement.
- The `docs/jerkiness-diagnosis.md` document is the field reference — update it as experiments are run.
- Experiment 1 (moderate speed/accel) is the one-liner highest-impact test. Do this first when user is ready.
- Don't change PID gains until after Experiment 1 — current gains (Kp=50-65, Ki=0-1, Kd=10-30) are probably fine for Paradigm A and may be fine for moderate-speed streaming.

**What NOT to do:**
- Don't enable software PID correction in closed-loop until after testing moderate speed/accel — the comment says it was intentionally disabled "during tuning", so re-enabling without understanding why it was disabled could regress.
- Don't increase loop frequency above 100 Hz — Python timing jitter makes it counterproductive. If anything, go lower (50 Hz) with moderate speed to let servo interpolate.

#### Saturation Model Refinement (2026-09-08, session 2)

**User challenged Goal Time idea** — correctly: chained per-waypoint trapezoids still stop at every waypoint (v=0 endpoints). Don't pitch per-segment profiles as fixes again; the escape is *profile saturation*, not smarter per-segment profiles.

**Refined model (section 9 of docs/jerkiness-diagnosis.md):**
- Feetech planner only decelerates within braking distance of the goal.
- Keep goals perpetually ahead → servo never decelerates → continuous cruise.
- Three regimes: cap>>stream (stop-go, current bug) / cap≈stream+15% (cruise) / cap<stream (lag, dangerous).
- The speed register becomes the velocity controller on position-only hardware.
- User's question also exposed that jog jerkiness is the same mechanism (25 Hz stream, speed=800 cap >> tiny per-step velocity).

**New facts to remember:**
- STS speed unit ~0.732 rpm/LSB is UNVERIFIED on this bench — needs a calibration move test. Correct per-step caps may be single/low-double-digit register values; check for a minimum usable cap.
- Present speed register 0x3A (bit 15 = direction) gives velocity feedback — use it for the cap sweep experiment. It's the falsifiable test.
- A rad/s → speed-register converter does NOT exist in the repo yet. It belongs in the Feetech backend.
- LeRobot SO-ARM/SO-100 community uses the same STS3215 with streamed positions + moderate speeds — external validation of the saturation approach.

**User preferences reinforced:**
- Wants theory pitched with mechanisms and falsifiable tests, not just "trust me."
- Keeps catching over-simplified claims (flat speed=500). Be more careful before pitching fixes — walk through second-order consequences first.
- Strong preference: all fixes backend-scoped (Feetech only), other servo configs unaffected.

#### Saturation Model Challenge 2 (2026-09-08, session 3)

**User caught the load-bearing assumption:** does a mid-move goal write actually overwrite the in-flight trapezoidal plan, or does the servo finish its plan first? UNKNOWN. I had presented Case A (velocity blend) as established; it is the optimistic branch of a three-way fork.

**The fork (docs/jerkiness-diagnosis.md section 9.4):**
- A: re-target w/ velocity blend → continuous cruise
- B: re-target from rest (v=0 re-plan, PID drags velocity) → velocity sawtooth, avg ≈ ½ cap
- C: queued completion → motion lags one segment, jitter starves queue
- CRITICAL: "pause at waypoints" under max caps is consistent with ALL THREE. Current symptoms cannot discriminate.

**Gating test (9.4, run before everything else):** mid-move goal rewrite on bench servo (4016→3600 at cap 300/accel 10, rewrite goal to 3400 mid-move, log 0x38/0x3A/moving flag). Outcomes map directly to A/B/C.

**Robustness claim to remember:** velocity-matched caps improve all three outcomes — fix direction safe, tuning fork-dependent (A: cap+headroom; B: cap×2 expect ripple; C: cap=planned, need stream-rate headroom).

**Lessons for pitching theories to this user:**
- They probe load-bearing assumptions. Present confidence honestly: known / extrapolated / unknown.
- Fork the hypothesis space explicitly with discriminating experiments BEFORE pitching implementation values.
- Test order now: 9.4 re-target fork → speed LSB calibration → 9.5 cap sweep → Feetech backend per-step caps.

#### Sprint 08 Created + Stopgap Feasibility (2026-09-08, session 4)

**Sprint state audit (accurate as of today):**
- sprint-00, 01: complete. sprint-02 Part A (STS3215 protocol): DONE in reality, but its checkbox file still shows all 28 boxes unchecked — the sprint file lags the DEVLOG. Part B (HLS3950): genuinely open, biggest unknown.
- sprint-03: open (15 boxes) — study GradientOS arch; largely superseded, we've already done deep study for the jerkiness diagnosis; the docs/gradientos/ stubs remain unfilled.
- sprint-04: open (15) — STS backend in GradientOS (fork/branch setup boxes are stale, we ARE editing the fork in place).
- sprint-05: open (12) — HLS backend, blocked on sprint-02 Part B.
- sprint-06: open (15) — paired-joint backlash offset. NOTE: user's reported oscillation is backlash-related; sprint-06 (preload offset on twin motors 20/21, 30/31) is a direct mechanical complement to the motion fix.
- sprint-07: open (25) — full arm build-out.
- NEW sprint-08: motion smoothness (created this session).

**Profiled-segment stopgap key insight:** it sidesteps the 9.4 firmware fork entirely — one goal per segment, never rewritten mid-move (rotysquare has 1s pauses between moves, so segments always complete). Only prereq is the speed LSB calibration. This is why it's the recommended immediate action over saturation streaming.

**Sequencing recommendation recorded in sprint-08:** A (LSB cal) → D (stopgap impl) gives smooth paused-trajectories now; B (fork test) → C (cap sweep) unlock continuous-path streaming later. Jog stays streaming either way for now.

**Repo hygiene notes:**
- feetech-project/TODO.md updated with sprint-08 and corrected sprint-02 status.
- Sprint-02 checkbox file needs a reality pass (Part A done but unchecked).

#### Sprint Reorg (2026-09-08, session 5)

**User decision:** HLS3950 protocol validation (old sprint-02 Part B) now lives at the START of sprint-05, gating the HLS backend implementation in the same sprint. Sprint 02 is now STS3215-only.

**Rationale worth remembering:** protocol validation and backend implementation for a given servo belong in the same sprint — the user is consolidating by hardware, not by activity type. If a new servo type is added later, expect its protocol validation to be the opening part of ITS backend sprint, not a separate protocol sprint.

**Sprint 08's Part B note:** careful — "Part B" in sprint-08 means the mid-move re-target fork test, NOT HLS (old sprint-02 Part B). Renaming happened to create two different "Part B"s; watch for confusion in future sessions.

#### Sprint 8/9 Split + Stall Data (2026-09-08, session 6)

**User's correction (remember this preference):** keep sprints focused — Sprint 08 = ONE question (can trapezoid planning be interrupted mid-move → pseudo-Dynamixel feasibility), bench-only, no code. The quick fix is a SEPARATE sprint (09) for the immediate future. I had bundled characterization + stopgap implementation into one sprint; user split it. Don't bundle implementation into feasibility studies again.

**Stall current now measured:** 8 W spike (~0.67 A @ 12 V) during manual downward pull on the arm EE, vs ~3.6 W idle. Recorded in STS3215.md. Sprint-02's last open bench item is closed. Note: it's a brief manual-pull spike — a sustained jam against a higher PSU current limit could read higher.

**Sprint map now:**
- 09 = endpoint-paradigm quick fix (code, immediate, fixes user's jerkiness; flat cap 500/accel 10 ships first, LSB-refined later)
- 08 = feasibility bench study (A: LSB cal → B: re-target fork 3x + edge probes → C: cap sweep → D: verdict GO/CONDITIONAL/NO-GO)
- 08's verdict decides: streaming migration for weld/jog (new sprint later) vs endpoint paradigm permanent for Feetech

**Sprint 08 Part B edge probes worth remembering:** high-rate 100 Hz re-targets with cap≈stream velocity (tests A/B under realistic streaming), and mid-move direction reversal (backlash-relevant). Only run these if A or B confirmed.

**Sequencing guidance given to user:** 09 first (uptime), 08 parallel-able (architecture answer). They share only one dependency: Part A LSB calibration refines 09's caps later.

#### Sprint Plan Restructure (2026-09-08, session 7)

**New sprint map (user-directed):**
- 00, 01 complete. 02 = quick fix (endpoint paradigm). 03 = GradientOS study (crash course written). 04 = paired joints. 05 = pseudo-Dynamixel feasibility (bench only). 06 = full-arm hardening (slimmed). 07 = HLS3950 all-in-one.
- Complete sprints archived to sprints/archive/ with -COMPLETE suffix instead of deleted (user preference: preserve history, don't destroy).

**Key evidence found:** feetech-project/code/ contains coordinated_home.py + hello_world_all_joints.py driving ALL 8 servo IDs — the arm was brought up organically, which is why old sprint-04/07 (backend, full-arm bring-up) were complete-in-reality but unchecked. Always check code/ and DEVLOG for actual progress before trusting sprint checkboxes.

**Sprint-03 crash course lives in the sprint file** (sprint-03-gradientos-study.md) — covers two-axis selection, startup sequence, command path, motion pipeline paradigms, twin motors, HLS extension path, sharp edges. The docs/gradientos/ stubs (architecture-notes.md, adding-a-servo-family.md) remain the only unfilled items; the crash course can seed them when the user asks.

**Safety flag carried into sprint-06:** servo EEPROM angle limits are UNRESTRICTED (0/4095 confirmed on bench); arm relies on software clamps only. Sprint-06 includes mechanical limit audit + optional EEPROM write (needs human approval per guardrails).

**User's sprint philosophy observed:** sprints should be short/focused, one question or one deliverable each; feasibility studies never bundled with implementation; completed sprints archived not deleted; numbering = priority order (quick fix at 02).

#### Sprint Renumbering v3 (2026-09-08, session 8)

**Final sprint map (user-directed, third restructure today):**
- 00 setup ✅ | 01 STS protocol ✅ (restored from archive per user request, marked complete in-place) | 02 electronics ✅ (was 01) | 03 study (~90%, crash course) | 04 quickfix (READY, next action) | 05 HLS3950 all-in-one | 06 paired joints | 07 pseudo-Dynamixel feasibility | 08 arm hardening.

**User's hard requirement on sprint-04 (repeated twice — treat as invariant):** the endpoint-paradigm fix must activate ONLY via the backend capability flag. Never keyed off backend-name strings or global constants. Explicit gating-matrix tests required: feetech+gradient0 = active; simulation+any robot = unchanged; no-backend legacy path = unchanged. If future sprints touch motion code, preserve this gating.

**Renumbering hazard learned:** shifting sprint numbers by sed is error-prone when old numbers overlap new ones (02→04 while 05→07 etc.) — always: (1) mv files to tmp names first, (2) fix titles, (3) fix cross-refs per file, (4) rg for stale old filenames/numbers as final gate. The "no stale refs" rg check is now part of the workflow.

**HLS sprint final number is 05** (user asked "switch the HLS sprint to sprint 04" based on the plan where quickfix was 02; after restoring the archive sprint to 01 everything shifted down one, landing HLS at 05, quickfix at 04).

#### Sprint Swap + README Resync (2026-09-08, session 9)

**Final map:** 00 setup ✅ | 01 STS protocol ✅ | 02 study 📖 | 03 electronics ✅ | 04 quickfix ⏳NEXT | 05 HLS | 06 paired | 07 feasibility | 08 hardening.

**New workflow rule:** after ANY sprint renumbering, rg-sweep README.md too — it had drifted to the original 7-sprint plan and wasn't in my reference-fix list until this session. Sweep list is now: sprints/*.md, TODO.md, README.md, docs/**, GradientOS/docs/jerkiness-diagnosis.md.

**Sprint-08 (arm hardening) rationale to remember:** exists because the arm was brought up organically — the safety/operational work a staged bring-up would have done never happened. Five buckets: (1) power bus (8 servos vs URT-1's 6A limit, bench PSU not mountable), (2) udev stable naming + real replug test, (3) joint limits — CRITICAL: servo EEPROM limits confirmed UNRESTRICTED 0/4095, arm relies on software clamps only; mechanical audit + optional EEPROM write (human approval), (4) temperature soak under continuous duty, (5) operator handoff doc. Recommended AFTER sprint-04 so motion is clean before wiring changes (avoid two debugging variables).

#### Sprint 04 Implementation (2026-09-08, session 10)

**Sprint 04 (endpoint-paradigm quick fix) is now IMPLEMENTED in code.** The capability-flag gating pattern from the sprint spec is live:

- `ActuatorBackend.supports_profiled_segments` property defaults to `False` in the ABC → every backend inherits "off" automatically (opt-in only).
- `FeetechBackend` overrides to `True` → profiled segments active for Feetech only.
- `SimulationBackend`, `EthercatRTCoreBackend` inherit `False` → dense streaming unchanged.
- The trajectory executor queries the flag at runtime via `_backend_supports_profiled_segments()` which calls `getattr(backend, 'supports_profiled_segments', False)` — never a string check or global constant. If no backend is active (legacy servo_protocol path), returns False → unchanged.

**Key implementation details to remember:**
- `plan_profiled_segment(start_q, end_q, per_joint_velocities=None, flat_speed=None)` computes per-joint speed caps: slowest joint (largest |Δq|) gets the flat cap (default 500), others scaled down proportionally so all joints arrive together. Zero-Δq joints get `SPEED_MIN` (30). Flat cap is clamped to [30, 2000]. Fixed moderate accel = 10 (bench safe-move recipe).
- `_execute_profiled_segment_step(step)` and `_execute_profiled_joint_move_step(step)` send ONE sync_write and then wait (interruptible, 2.0 s default). The wait is conservative because the Goal Time register is unverified; rotysquare's 1 s pauses absorb drift. TODO: read-back polling after Sprint 07 calibrates speed LSB → duration.
- Weld moves (`step.get("weld_active", False)`) keep dense streaming even on Feetech — the sprint explicitly excludes continuous weld paths (path shape degrades; gated on Sprint 07 verdict).
- `joint_move` steps use the step's `speed` field as the baseline flat cap override if provided.

**Test coverage (21 tests, all passing):** `tests/test_profiled_segments.py` — capability-flag defaults per backend type, full gating matrix (feetech/sim/no-backend/uninitialized), per-joint cap scaling, speed clamping, endpoint accuracy, weld-move exclusion, execution correctness (one sync_write, global state update).

**Pre-existing test failures (NOT caused by this change):** 6 tests in test_driver, test_protocol, test_planning, test_end_to_end fail with `TypeError: 'NoneType'` because they don't call `robot_config.set_active_robot()` before accessing `utils.SERVO_IDS` etc. These are pre-existing — confirmed by stashing my changes and re-running. Don't mistake them for Sprint 04 regressions.

**Flat cap rationale:** 500 matches the smooth Home move's speed. The sprint spec says a flat conservative cap can ship first and be refined when Sprint 07 Part A calibrates the rad/s → LSB conversion. The `per_joint_velocities` parameter in `plan_profiled_segment` is reserved for that future calibration but not yet used.

**What remains for Sprint 04 to be fully "done":** `move_line` with pauses test, quantitative endpoint accuracy measurement, and decision log entry. The core fix is user-validated — the reported jerkiness symptom is gone. Remaining items are non-blocking refinements.

**PSU observation (2026-09-11 user validation):** ~10 A peak (~120 W @ 12 V) during profiled-segment motion. No streaming baseline was available for comparison. This is relevant to Sprint 08 (arm hardening): the power bus must handle 10 A peaks across 8 servos; the URT-1's 6 A limit may be insufficient for aggressive multi-joint moves. Sprint 08 should measure sustained current, not just peaks.

### 2026-09-11 — Sprint 05: Backend rename (feetech → sts3215) + HLS3950 backend creation

#### Task Summary

- Researched the HLS3950 protocol (the project's biggest hardware unknown) via the Feetech wiki at `wiki.aifitlab.com`. Found full memory table and protocol documentation.
- Key finding: the HLS3950 uses the same FT-SCS protocol as the STS3215 — same frame format, instruction set, checksum, SYNC_WRITE layout. Register map is very similar with specific differences.
- Renamed the existing backend from `backends/feetech/` to `backends/sts3215/` and class `FeetechBackend` to `STS3215Backend`, registration name `"feetech"` to `"sts3215"`.
- Created `backends/hls3950/` with `HLS3950Backend`, registered as `"hls3950"`.
- Filled the HLS protocol and hardware spec docs from wiki data.

#### Mistakes And Fixes

- Source: `[self]`
- Mistake: none during this session — the rename and new backend creation went cleanly on the first pass.
- Detection: tests confirmed — 21/21 profiled-segment tests pass, 6 pre-existing failures unchanged.

#### User Preferences

- New or reinforced preference:
  - Backend names should use the actual model number (`sts3215`, `hls3950`), not a generic family name (`feetech`). This makes it explicit which servo hardware is active.
  - User confirmed: "it is definitely the same single wire setup and should work running through the URT-1" — no adapter concern.
- How it changed execution:
  - Used `git mv` for the directory rename to preserve history.
  - Created HLS3950 as a separate backend directory (not extending the STS3215 backend) per user request.

#### What Worked

- Pattern/check that worked:
  - `sed` bulk renames for print statements (`[Feetech]` → `[STS3215]` / `[HLS3950]`) and class names across driver/protocol/config files.
  - Copying the sts3215 directory as a base for hls3950, then modifying only the config.py (register map) and keeping protocol.py identical (same frame format).
  - Online research via wiki.aifitlab.com resolved the protocol question before writing any code — the wiki has full memory table analysis for both STS and HLS servos.

#### Key Technical Knowledge

- The HLS3950 register map differs from STS3215 in these registers:
  - 0x07 = Sub ID (not on STS)
  - 0x21 mode 2 = constant current (STS = PWM)
  - 0x22 = Current loop Kp (STS = Holding torque)
  - 0x23 = Current loop Ki (STS = Protection time)
  - 0x28 = Torque switch (0/1/2 only — STS also accepts 128 for calibration)
  - 0x2C = Target current (STS = PWM open-loop speed)
  - 0x42 = Moving flag (not on STS)
  - 0x43 = Target position readback (not on STS)
- Calibration: HLS3950 uses 0x0B instruction only. The STS3215 torque-switch shortcut (write 128 to 0x28) does NOT work on HLS.
- Both servos have the same internal trapezoidal profiler, so `supports_profiled_segments = True` for both.

#### Guardrails For Next Session

- Preflight rule:
  - When renaming a backend, grep for ALL references (Python imports, string literals in run_controller.py, registry config modules, test files, and bench scripts in feetech-project/code/).
  - The `run_controller.py` angle-limit write gate checks `servo_backend in ("sts3215", "hls3950")` — both serial servo backends need EEPROM angle limit writes. If a third serial backend is added, add it to this tuple.
  - The simulation backend falls back to `"sts3215"` config module for constants — this is in `run_controller.py:166` and `backends/__init__.py:112`. If the sts3215 config is ever removed or renamed, this fallback must be updated.

#### Follow-Ups / Risks

- Remaining risk or pending check:
  - The HLS3950 backend has NOT been tested on physical hardware — bench validation (PING, read position, command small move) is the next step.
  - Default PID gains in hls3950/config.py are copied from STS3215 — will need tuning for the HLS servo.
  - Historical doc references in sprint files and ARCHITECTURE.md still reference `backends/feetech/` — they're historical records, not code-affecting.
  - The "Dockerfile rebuild" mentioned in TODO.md refers to the OpenChamber container image needing build-essential/python3-dev/cmake for the IK solver C++ extension — not HLS-specific. Pure Python backend needs no new system packages.

### 2026-09-11 — Sprint 07: Bench experiment scripts written (not yet run)

#### Task Summary

- Wrote all four Sprint 07 bench experiment scripts (Pseudo-Dynamixel feasibility study). No production code changed — bench-only tooling under `feetech-project/code/`.

#### Files Created

- `bench_utils.py` — shared utility: serial setup, bulk telemetry read (11 bytes 0x38–0x42 in one packet for max sample rate), CSV trace writer, safe-move recipe (seed-verify), guardrails (assert_safe_target, downward-only).
- `part_a_speed_calibration.py` — Part A: sweeps cap {10,30,60,100}, times move completion, computes rpm/LSB, finds motion floor by sweeping downward. Outputs summary CSV.
- `part_b_midmove_retarget.py` — Part B (decisive): long move 4016→3600, rewrites goal to 3400 mid-cruise, logs at max bulk-read rate (~100+ Hz), auto-classifies A/B/C from velocity trace. 3 trials. Optional `--edges` for high-rate 100 Hz re-target probe + direction-reversal probe.
- `part_c_cap_sweep.py` — Part C: streams linear move at 100 Hz, sweeps cap {4095,500,100,30,10,floor}, classifies regime (stop-go/cruise/lag) from zero-crossing analysis.

#### Key Technical Decisions

- Used bulk register read (11 bytes from 0x38–0x42) instead of individual register reads to maximize telemetry sample rate. One round-trip captures pos+speed+load+voltage+temp+status+moving.
- Part B classification is automated: checks velocity continuity around re-target point, detects position reaching initial goal (case C), detects velocity dip (case B). Reports per-trial + overall verdict.
- Part B `--edges` flag is opt-in: high-rate re-target and direction-reversal probes only run if Part B verdict is A or B. Direction reversal is the only backward-motion test — operator must be present.
- Part C's stream loop writes goals at 100 Hz but reads telemetry between writes (no explicit pacing needed — serial round-trip naturally paces the loop).

#### Guardrails For Next Session

- Scripts are ready to run but require physical bench hardware. User should run them in order: A → B → C.
- `RETARGET_DELAY` (0.8s) in Part B may need tuning if the servo reaches the first goal before re-target fires — check the trace.
- Part C accepts `--floor` from Part A's result; default is 3 if not provided.
- All traces save to `feetech-project/data/part_{a,b,c}_traces/`. Summary CSVs save to `feetech-project/data/`.
- After running, the operator should send the CSV traces for analysis. I can parse them and write the verdict + update `docs/jerkiness-diagnosis.md` §9.4-9.5.

#### Sprint 07 Part A review + Part B prep (2026-09-14, session review)

**Part A was run externally (user + GPT on the bench).** Data landed in `feetech-project/data/part_a_{traces,floor_probe,extended_slope}/`. Key measured facts to carry into all future STS3215 work:

- **Speed command floor = cap 50** (~5 deg/s). Caps below 50 are all the same motion. Never command below 50.
- **0.732 rpm/LSB is refuted** for direct goal→achieved-speed interpretation. Effective scale above the floor: ~0.09 deg/s per cap LSB (100→9, 200→17.2, 300→22.9 deg/s), mildly sub-linear.
- **0x3A present-speed ≠ goal-cap units.** At cap 300, decoded 0x3A clusters 100-350 (mostly 300); floor moves decode to exactly 50. Downward = raw ≈ 32768−mag (two's-complement style); upward = raw mag directly. Decode: `raw>32767 ? 65536-raw : raw`.
- **3 ms per serial transaction is a hard floor** (CH340 USB scheduling, not wire time). Bulk reads don't help beyond one transaction. Retry only after writes; reads are reliable.
- **Goal write auto-enables torque** (0x28 0→1). Never write 0x28=1 directly at rest — goal reads 0 near position 4095 → instant full-range max-accel swing hazard. Always seed goal first.
- **Accel 0x29=0 means MAXIMUM.** Bench recipe: write 10 before moving.
- **Angle limits unrestricted (0/4095)** — software guardrails are the only protection.

**Part B script issues found in review (fix before bench):**
1. Script hardcodes start≈4016 → INITIAL_GOAL 3600 / RETARGET_GOAL 3400. Bench servo now sits at ~3895. Must parameterize from actual read position: e.g. start→start−296→start−516, or just `--start-goal`/`--retarget-goal` args.
2. Classification uses 0x3A magnitudes with fixed thresholds (5, 20) — but decoded 0x3A at cap 300 clusters 100-350 and the noise floor at standstill is 0. Thresholds need recalibration: cruise detect via position delta (counts/sample ≈ 263 counts/s at cap 300 → ≥1 count/sample at ~300 Hz sample rate is safe), velocity-dip detect via decoded 0x3A dropping below ~50% of pre-retarget median.
3. RETARGET_DELAY=0.8s at cap 300: 416-count first leg at ~263 counts/s takes ~1.6 s, so 0.8 s fires mid-cruise — OK. But verify with the new relative goals.
4. Sample rate: bulk read ≈ 3 ms/txn → ~300 Hz achievable. Good for the ≥100 Hz requirement.
5. bench_utils decode bug: read_telemetry_sample parses 0x3A as signed little-endian (32868 → −2868), but the traces show the user's runs decoded via two's-complement to 100. The signed parse happens to give the right magnitude after abs() only for raw values 32768..65535 — abs(−2868)=2868≠100. MUST fix decode to `raw>32767 ? 65536-raw : raw` before Part B, or Part B classification will misread every downward speed.

**User wants to think through all options before Part B** — options on the table: (a) run Part B as written, (b) fix decode + parameterize first, (c) hybrid mode-switch probe (velocity mode cruise → position mode arrival) as an additional edge probe, (d) velocity-mode path discussed as long-term architecture. My recommendation: (b) is mandatory regardless; (c) is cheap to add and answers the hybrid question with the same bench session.

#### 0x3A encoding CLOSED with Part A data (2026-09-14, no bench needed)

**The 0x3A unit question is answered from existing Part A traces:**
- **0x3A IS in the same units as the goal speed cap (0x2E)** — not a separate scale. Verified: cruise plateau decoded == commanded cap exactly (cap 100→decoded 100, 200→200, 300→300), across 528/286/124 samples.
- **The LSB scale is ~0.088 deg/s per unit (both registers)**: position-timed slopes were −100.5/−199.4/−300.1 counts/s = −8.83/−17.53/−26.37 deg/s at decoded 100/200/300 → 0.0879 deg/s per LSB, consistent across all three caps and the floor (50→4.53 deg/s measured vs 4.40 predicted).
- **So: cap LSB = 0x3A LSB ≈ 0.088 deg/s ≈ 0.0147 rpm/LSB.** The documented 0.732 rpm/LSB likely refers to the *motor shaft* before the ~50:1 gearbox (0.0147 × 50 ≈ 0.73). Mystery solved — both docs were "right", different shafts.
- **Direction encoding on 0x3A: bit15 (0x8000) is the direction bit, low 15 bits are magnitude.** Downward = bit15 SET (raw 32868→100, 32968→200, 33068→300); upward = bit15 clear (raw 150 reads as 150). NOT two's-complement — mask with 0x7FFF. (A two's-complement parse gives −2868 for raw 32868: wrong magnitude AND wrong sign. bench_utils.py must fix this.)
- **Upward moves are SLOWER than downward at the same cap**: returns (up, cap 500 commanded) plateaued at decoded 150 (12.77 deg/s) vs downward cap 300 → decoded 300 (26.37 deg/s). Gravity load on this joint? Or cap 500's return was actually run at a lower cap by the Part A script (check: return used speed=500 → decoded 150 ≈ 13.2 deg/s — the servo ran at ~⅓ of commanded cap upward). UNRESOLVED: is 150 an upward speed ceiling, or did the script set a different cap? Check part_a script's return code before Part B; do not assume symmetric caps up/down.

**Consequences for Part B script fixes:**
1. bench_utils.read_telemetry_sample: decode 0x3A as `(raw & 0x7FFF) * (1 if raw & 0x8000 else -1)`-style bit15 direction + low15 magnitude. (Sign convention: down = bit15 set. Confirm sign mapping in Part B trials.)
2. Part B cruise detect: decoded 0x3A plateau == cap (verified exact equality in cruise) → `dec == cap` is a robust cruise detector at cap 300, simpler than position-delta.
3. Classification thresholds now trivial: cruise = dec≈300; dip-to-zero = dec < 50 (floor); case C stop = dec hits 0 with pos at first goal.
4. Part C quantitative: deg/s = dec × 0.088.

#### Part B bench-day readiness (2026-09-14, pre-bench)

**All Part A review fixes landed + hybrid probe added. Ready for bench.**
- bench_utils 0x3A decode = bit15 dir + 0x7FFF mask (verified offline against raw trace values).
- Part B goals relative: start-296 → start-516, works from ~3895 rest.
- Classifier: A = speed_mag stays >50% cap across retarget; B = dips <50 (floor); C = speed 0 + pos ≤ first goal+10.
- Hybrid probe order inside probe: mode→0 FIRST, seed goal at current pos, THEN final target. finally-block restores mode 0 on any exit.
- Edge probe order: high-rate retarget → hybrid (Enter-gated) → reversal (Enter-gated).
- OPEN RISK: velocity command sign convention unverified (negative = downward assumed from docs). First hybrid run: if wrong direction, power off, flip sign, retry once.
- OPEN RISK: upward speed plateau ~150 at cap 500 unexplained — watch return_home durations.
- Bench flow for user: run trials first (no --edges), review verdict, THEN --edges if A/B. Part C same session with --floor 50.

#### PART B VERDICT: CASE A (2026-09-14 bench session)

**CASE A CONFIRMED — velocity-continuous mid-move re-target blend, 3/3 trials.**
This is the GO outcome for saturation streaming. Details:

- Retarget at t≈0.60s, mid-cruise, speed_mag 300 → 300 across the rewrite (min 250 = quantization step). No stops. One continuous cruise through both goals.
- **The auto-classifier LIED — it printed "C".** Root cause: `reached_initial_goal` checks `pos <= goal1 + 10` which is trivially true when goal2 is BELOW goal1 (servo passes through goal1 at cruise speed). Always classify from raw traces; treat script auto-verdicts as hints, not truth. Fix classifier before any rerun: case C must require a speed-zero window at/near goal1 (e.g. speed_mag < 10 sustained ≥0.1s while pos within ±10 of goal1), not mere passage.
- **bench_utils.read_register_bulk had an off-by-one** (resp_len = length+5, needs +6 — the checksum byte). Symptom: 100% of telemetry reads return None while read_register_word works. Fixed 2026-09-14. Lesson: the first Part B "run" produced 0 samples and a plausible-looking UNKNOWN verdict — a silent failure mode. Always sanity-check sample count ≠ 0 before trusting a bench run.
- 0x3A quantization: steps of 50 (observed 250/300/350). Ripple below 50 units is unmeasurable via 0x3A; use position-delta slope for fine ripple if ever needed.
- Drift: -1..-2 counts per down-up cycle (backlash undershoot, consistent with Part A). Servo rest now ~3901.
- **Sprint 07 status:** Part A done (LSB 0.088 deg/s, floor 50). Part B done (CASE A = GO). Remaining: Part C cap sweep (with --floor 50), edge probes (high-rate 100 Hz retarget now VERY interesting — case A predicts continuous cruise at stream rate; velocity-mode hybrid probe still worth one run as the interim-architecture comparison; reversal probe optional), verdict write-up + jerkiness-diagnosis.md §9.4 update.

#### PART C + SPRINT 07 COMPLETE (2026-09-14 bench session)

**Part C result (raw traces, auto-labels were false):** cap ≥ stream demand (~133 counts/s) → continuous cruise, error 1-2 counts (caps 4095/500/200/100 all CRUISE; cap 50 = firmware floor → LAG 38%). The "STOP-GO" auto-verdicts counted only the move's own start/stop decelerations. Regime boundary: cruise iff cap ≥ demand. Simple rule.

**MY BUGS THIS SESSION (3 total — all bench-critical, all mine, all fixed):**
1. `read_register_bulk` resp_len off-by-one (+5 vs +6) → 100% telemetry read failure, SILENT. First Part B run produced 0 samples + plausible UNKNOWN verdict.
2. Part C `step_size` sign error → streamed goals UPWARD; servo tracked to the 4094 wraparound seam. The servo is never wrong — it obeys exactly. Safety contract is 100% on the sender: validate every streamed goal, not just endpoints. Added per-goal band guard.
3. Both auto-classifiers produced false verdicts (Part B printed C, truth was A; Part C printed STOP-GO, truth was CRUISE). Root pattern: classifier heuristics that are trivially satisfied by normal trajectory structure. RULE: script verdicts are hints; raw traces are truth. Before trusting any bench verdict, spot-check the trace slices by hand.

**Servo parked at 3892** (buggy run left it at 4092 — 4 counts from the wrap seam; re-parked via safe recipe).

**SPRINT 07 FINAL RESULTS (all bench questions answered):**
- Part A: 0x2E/0x3A same units, LSB ≈ 0.088 deg/s (output shaft; documented 0.732 rpm/LSB = motor shaft pre-gearbox ~50:1). Floor 50. 0x3A = bit15 direction + 0x7FFF magnitude, quantized in steps of 50.
- Part B: CASE A — velocity-continuous blend on mid-cruise goal rewrites, 3/3 trials. Saturation streaming GO.
- Part D: sinusoid (±31°, 0.15 Hz, 100 Hz stream): smooth in BOTH legacy (4095/0) and profiled (850/10) settings; user visual: both smooth, profiled slightly smoother. All stops are the sine's own zero-velocity extremes. Production jerkiness root cause is the EXECUTORS' SEGMENT STRUCTURE (arrive-and-stop micro-waypoints), not the caps.
- Part C: cruise iff cap ≥ stream demand; below → lag. No stop-go at any cap when the goal stream is smooth+dense.
- IMPLICATIONS for production streaming implementation: (1) stream dense smooth goals, never sparse corners; (2) cap ≈ 1.5-2.5x expected segment velocity demand; (3) accel 10; (4) no need for velocity-mode hybrid as interim — position-mode streaming works once executors feed it smooth goals. Hybrid probe never ran (superseded by results — position streaming already achieves the goal).
- REMAINING: verdict write-up, jerkiness-diagnosis.md §9.4/9.5 update, sprint-07 checkbox file update, scratchpad sweep. All desk work.

#### Velocity estimation note (2026-09-14, from Sprint 07 data)

**Position differencing at 100 Hz — the recommended velocity estimator for STS3215.**
- 0x3A quantizes in steps of 50 LSB (~4.4 deg/s) — too coarse for closed-loop correction.
- Position differencing resolution is set by the window: noise floor = 1 count / window.
  - adjacent samples (10 ms): ~8.8 deg/s resolution (coarse, noisy)
  - 50 ms window (5 samples): ~1.8 deg/s resolution — recommended default
  - 100 ms window: ~0.9 deg/s but adds ~50 ms lag to the estimate
- Zero added latency IF position is already being read (the 11-byte bulk read includes 0x38; differencing is pure software on data in hand). No extra bus traffic.
- Implementation: rolling deque of (t, pos), slope over last ~5 samples, in servo_driver as a get_velocity() helper. Few lines.
- Use for: damped stream correction, monitoring. NOT needed for streaming itself (open-loop setpoint stream doesn't require velocity feedback).

**Cap policy (simple form for future docs):** the 0x2E cap is a speed CEILING, not a target. Set it ~2x the fastest the motion should ever go. The goal stream steers; the cap bounds. Too low → servo lags the stream (Part C, cap 50). Too high → no bound on a bad goal (production today, 4095). 2x demand = tracking headroom + safety ceiling in one number.

**Backend wrapping conclusion:** smooth-streaming recipe CAN be wrapped in the backend behind a capability flag (Sprint 04 pattern): executor hands backend a timed (t, position) path; backend-owned 100 Hz pacing thread streams it with 50 ms lookahead + per-segment cap sizing + accel 10. Planner/app untouched above the handoff. Design requirement: backend stream thread needs a watchdog (stop + hold-position if the app stops refreshing the path) — copy the jog loop's timeout-zeroing pattern. One architectural decision: timing ownership moves into the backend.

**Watchdog correction (user challenged it, 2026-09-14):** for POSITION-mode streaming, a watchdog is NOT a design requirement. Structural fail-safes: (1) servo stops at last written goal on stream interruption — with 50 ms lookahead that is ~50-100 ms of travel, by physics not by timer; (2) sliding-horizon path handoff (~200-300 ms of future) bounds any app hang to horizon-time of motion. Keep only as one line in the pacing loop ("stop writing when t > path_end") for buffer-replay bug containment. Watchdog becomes MANDATORY only if velocity mode is ever introduced (comms loss = continued rotation — different hazard class). Original watchdog note was velocity-mode thinking applied to position mode.

#### Sprint 10 + 11 authored (2026-09-14)

- Sprint 10 = backend-wrapped Case A streaming. Key design points baked in: capability flag pattern (4th use of it — Sprint 04 precedent), timing ownership moves into backend, no watchdog (horizon expiry + physics), per-goal stream clamp from my Part C sign-error lesson, HLS excluded until it gets its own fork test.
- Sprint 11 = hypothetical, explicitly labeled. The important structural choice: Part A IS the algorithm work (obstacle contract, policy bake-off with sim evidence, prediction decision, integration design, GO/park gate) — no implementation debt before the algorithm is proven on paper/sim. Synthetic obstacle producer decouples motion work from camera availability.
- Cross-sprint dependency: `replace_remaining_path` on the streaming handle is specced in 11 but noted as buildable in 10.
- TODO.md updated: sprint-07 open questions resolved; post-07 sprint table added. Numbering continues at 10 (no renumbering — session lesson held).
- STILL PENDING (desk work, no bench): diagnosis §9.4/9.5 update with measured results, sprint-07 checkbox file update, decision log entries. These are prerequisites for Sprint 10 implementation start but not for its design review.

#### Sprint 07 docs complete (2026-09-14)

All three doc surfaces updated in one pass: sprint-07 checkbox file (COMPLETE/GO banner, evidence + auto-classifier caveats + supersession notes), diagnosis §9.3-9.5/§10.6 (fork resolved, regime map in, LSB "both right different shafts" resolution), protocol doc (0x3A encoding row + new mid-move-rewrite section). Numbers cross-checked against traces. Two probes deliberately unchecked with supersession notes — a new model of "done" for this repo: superseded items stay unchecked but annotated, so checkbox counts alone never mislead. Sprint 10 is fully unblocked (docs + calibration + design all current).
