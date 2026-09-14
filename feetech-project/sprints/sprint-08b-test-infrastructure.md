# Sprint 08b — Test Infrastructure Baseline

> Created 2026-09-14.
> Prerequisite for Sprint 09 (GUI Improvements). The goal is to get a minimal test
> harness in place *before* building new UI screens, so every new component gets
> tests written alongside it rather than retrofitted after.

## Goal

Establish a minimal-but-real test framework for both the web UI and the backend API
contract layer, with working patterns that Sprint 09 work can follow. Focus on the
smallest set of tests that catch actual regressions — not comprehensive coverage.

## Prerequisites

- Backend pytest suite passing (`python -m pytest tests/`) ✅ (existing, ~30 tests)
- Web UI builds (`npm run build`) ✅ (existing)

## What this sprint is NOT

- Not a full 4-layer test pyramid (unit → component → integration → E2E)
- Not Playwright or browser automation
- Not 100% coverage or CI pipeline setup
- Not testing physical arm motion (impossible without hardware-in-loop)

## Tasks

### Backend — extend existing pytest suite

- [ ] Audit existing `tests/test_api_endpoints.py` — confirm all current endpoints
      have at least one happy-path and one error-path test
- [ ] Document the existing mock pattern (the `patch_send` context manager in
      `test_api_endpoints.py` lines 14-153) as the canonical pattern for new
      endpoint tests. Write a brief note in `tests/README.md`
- [ ] Identify any existing endpoints with no test coverage (grep `@app.post` /
      `@app.get` in `api/main.py` vs tested endpoints) and add smoke tests for the
      gaps — only if they're simple (status + shape), not deep behavior

### Frontend — set up vitest + minimal component tests

- [ ] Install dev dependencies: `vitest`, `@testing-library/react`,
      `@testing-library/jest-dom`, `jsdom`
- [ ] Add `vitest.config.ts` (jsdom environment, React plugin, path aliases matching
      `vite.config.ts`)
- [ ] Add `npm run test` and `npm run test:run` scripts to `package.json`
- [ ] Write a smoke test for `ControlPanel.tsx` — renders without crash, jog buttons
      exist, STOP button exists. This establishes the component-test pattern.
- [ ] Write a smoke test for `SidebarDrawer.tsx` — renders, opens, closes
- [ ] Write a smoke test for `TelemetryCharts.tsx` — renders with empty data and
      with sample data. **Requires a `ResizeObserver` polyfill** (jsdom does not
      implement it; the component instantiates one at `TelemetryCharts.tsx:273`
      and will crash on mount without it). Add the polyfill to the test setup file
      (`src/test/setup.ts` or equivalent) so all tests get it.
- [ ] Create a mock for the API client / `fetch` layer so component tests don't need
      a running backend. Store in `web-ui/src/test/apiMock.ts` (or similar). This is
      the reusable piece Sprint 09 tests will depend on. **Derive the mock response
      shapes from the actual FastAPI response models in `api/main.py`** (the same
      shapes asserted in `tests/test_api_endpoints.py`) — not from assumptions about
      what the endpoints return.

### Frontend — build verification

- [ ] Confirm `npm run test:run` passes with zero failures
- [ ] Confirm `npm run build` still passes (vitest config doesn't break the build)
- [ ] Confirm `python -m pytest tests/` still passes (no backend changes that break)

### Document

- [ ] Add a "Testing" section to `web-ui/README.md` (or create one) with:
  - How to run frontend tests (`npm run test`)
  - How to run backend tests (`python -m pytest tests/`)
  - The mock pattern for API endpoints
  - The component-test pattern (render → query → assert)
- [ ] Append DEVLOG and AGENT_SCRATCHPAD entries

## Definition of done

- `npm run test:run` passes (at least 3 component smoke tests, 0 failures)
- `npm run build` passes
- `python -m pytest tests/` passes (existing + any new API smoke tests, 0 failures)
- A documented mock pattern exists for both frontend (API client mock) and backend
  (controller command mock) that Sprint 09 tests can reuse
- Testing instructions written in `web-ui/README.md`

## Notes

- **Verified constraints (checked in-repo 2026-09-14, not assumed):**
  - `ControlPanel.tsx`, `SidebarDrawer.tsx`, and `TelemetryCharts.tsx` do **not**
    import three.js/`@react-three/fiber` — they are safe to smoke-test in jsdom.
  - `App.tsx` **does** pull in Three.js via `ArmVisualizer`. Therefore: **test files
    must import components directly, never via `App.tsx`** — any test that imports
    `App.tsx` will pull the Three.js/WebGL chain into jsdom and crash. Do not write
    an App-level smoke test in this sprint.
  - `TelemetryCharts.tsx` uses `ResizeObserver` (line 273) — jsdom lacks it; a
    polyfill in the test setup is mandatory, not optional.
  - Tailwind is a non-issue for tests (vitest does not process CSS by default);
    drop any planned effort around CSS transforms in tests.
- Keep the frontend test count low (target 3-5 smoke tests). The goal is the
  *pattern*, not the coverage. Sprint 09 adds tests as it adds screens.
- If vitest + Vite config friction exceeds ~1 hour, fall back to a minimal
  `vitest.config.ts` with just the React plugin and jsdom.
- This sprint can be done by an AI agent autonomously (see risk assessment below)
  but the results should be reviewed by a human before Sprint 09 builds on top.
  Human review checklist:
  1. Run `npm run test:run` and `npm run build` yourself once
  2. Spot-check that the API mock shapes match `tests/test_api_endpoints.py`
     assertions (they encode the real contract)
  3. Confirm no test imports `App.tsx` (grep the test files)