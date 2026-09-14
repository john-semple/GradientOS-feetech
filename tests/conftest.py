"""
Shared pytest fixtures/setup for the GradientOS test suite.

The controller runtime (run_controller.py) initializes the active robot
configuration and servo backend at startup. Tests that import
gradient_os.arm_controller.utils or servo_protocol need the same constants
populated, otherwise module-level constants (SERVO_IDS,
SYNC_WRITE_START_ADDRESS, ...) are None and tests fail with TypeErrors.

This conftest mirrors the startup sequence of run_controller.py without
touching any hardware:

    1. get_robot_config("gradient0")        -> the default robot
    2. robot_config.set_active_robot(...)   -> populates robot constants
    3. backend_registry.set_active_backend("sts3215")  -> loads backend config
    4. utils._populate_servo_constants()    -> populates protocol constants

Note: we set the sts3215 backend even for tests that run against other
backends, because the shared protocol tests (checksums, SYNC_WRITE packet
structure) are defined against the Feetech/STS family packet format, which
is what the physical arm uses. Backend-specific behavior is tested in the
backend's own tests.
"""

import pytest


def _init_robot_and_backend() -> None:
    from gradient_os.arm_controller.robots import get_robot_config
    from gradient_os.arm_controller import robot_config, utils
    from gradient_os.arm_controller.backends import registry as backend_registry

    selected_robot = get_robot_config("gradient0")
    robot_config.set_active_robot(selected_robot)
    backend_registry.set_active_backend("sts3215")
    utils._populate_servo_constants()


@pytest.fixture(scope="session", autouse=True)
def robot_backend_initialized():
    """Initialize robot config + servo backend constants once per test session."""
    _init_robot_and_backend()
    yield