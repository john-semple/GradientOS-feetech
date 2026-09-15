# Robotic Arm Controller Tests

This directory contains the unit, integration, and end-to-end tests for the `mini-arm` controller software.

## Running the Tests

To run the full test suite, you first need to install the required testing framework and mocks.

### 1. Install Dependencies

Navigate to the root directory of the project (`mini-arm`) and run the following command to install `pytest` and `pytest-mock`:

```bash
pip install pytest pytest-mock
```

### 2. Execute the Test Suite

Once the dependencies are installed, you can run all tests by executing the following command from the project's root directory:

```bash
python -m pytest tests/
```

Pytest will automatically discover and run all test files (files named `test_*.py` or `*_test.py`) within the `tests/` directory and its subdirectories.

### Web UI tests

The web UI has its own vitest suite (see `web-ui/src/test/`). Run it from `web-ui/`:

```bash
npm run test        # watch mode
npm run test:run    # single run (CI-style)
```

### Test session initialization (conftest.py)

`tests/conftest.py` runs once per pytest session and performs the same
startup initialization that `run_controller.py` does at boot (no hardware):

1. `get_robot_config("gradient0")` + `robot_config.set_active_robot(...)` — populates robot constants (`SERVO_IDS`, mapping ranges, joint limits, ...)
2. `backend_registry.set_active_backend("sts3215")` + `utils._populate_servo_constants()` — populates protocol constants (`SYNC_WRITE_START_ADDRESS`, instruction codes, ...)

Without this, module-level constants in `utils.py` are `None` and tests fail
with `TypeError`. Any new test file that imports servo/driver/protocol modules
gets this initialization automatically; do not re-initialize per-test.

### Adding new API endpoint tests (the canonical pattern)

New FastAPI endpoint tests should extend `tests/test_api_endpoints.py`,
which uses the `patch_send` context manager (lines 14-153) to stub the
UDP controller interface:

- Mock `_send_controller_command` with canned UDP replies (the strings the
  controller actually returns, e.g. `"CURRENT_POSE,..."`)
- Mock `_probe_controller` to report the controller as available
- Mock `controller_command_api` and `topology_service` where the endpoint
  uses them
- Assert on the FastAPI response JSON **and** the UDP command strings that
  were sent (`client.command_calls`)

This tests the real API contract (request → UDP command string → response
shape) without hardware. The web UI's fetch mock (`web-ui/src/test/apiMock.ts`)
mirrors the same response shapes — when you add an endpoint test here, keep
the corresponding mock shape in `apiMock.ts` in sync.

## Test Descriptions

-   `test_protocol.py`: Contains low-level unit tests for the `servo_protocol.py` module. It verifies the correctness of fundamental operations like checksum calculation and the byte-level structure of `SYNC_WRITE` packets, ensuring that communication with the servos is formatted correctly.

-   `test_driver.py`: Includes unit tests for the `servo_driver.py` module, which acts as the hardware abstraction layer. These tests validate the conversion logic between abstract units (like radians) and raw servo values, and check the logical-to-physical joint mapping for the active robot config (gradient0: 1:1 mapping, no gear ratio).

-   `test_planning.py`: Focuses on unit testing the core algorithms within `trajectory_execution.py`. It specifically tests the path unwrapping and smoothing logic to ensure that generated joint-space trajectories are continuous and do not contain unnecessary "wrap-around" jumps.

-   `test_solver.py`: An integration test for the C++ IKFast wrapper (`ikfast_wrapper.py`). It performs sanity checks to ensure that Forward Kinematics (FK) and Inverse Kinematics (IK) are consistent and that the batch IK solver can process a sequence of poses correctly.

-   `test_api_endpoints.py`: Integration tests for the FastAPI layer (`src/gradient_os/api/main.py`). Uses FastAPI's TestClient with the UDP controller interface fully mocked (`patch_send` context manager), so no controller or hardware is needed. Verifies both the HTTP response shapes and the exact UDP command strings sent to the controller. NOTE: requires `httpx` installed (FastAPI TestClient dependency); if missing, the whole file silently skips — install with `uv pip install httpx` (it is part of the `[dev]` extra).

-   `test_end_to_end.py`: Provides high-level integration tests that simulate the full control loop. It tests the system's behavior from receiving a UDP command to the final data being sent to the (mocked) serial port, verifying that all components work together as expected.