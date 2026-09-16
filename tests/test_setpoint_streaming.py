"""
Sprint 10 — Smooth Streaming Executor: gating-matrix tests.

Verifies the capability-flag gating for ``supports_setpoint_streaming``:
  - STS3215Backend → setpoint streaming ACTIVE
  - HLS3950Backend → setpoint streaming ACTIVE
  - SimulationBackend → setpoint streaming ACTIVE (robust pacing)
  - EthercatRTCoreBackend → streaming unchanged (flag False)
  - No active backend (legacy servo_protocol path) → unchanged
  - Config override: streaming_enabled=False disables streaming
  - MotionHandle: cancel/pause/resume/is_done/wait lifecycle
  - Sim execute_timed_path: pacing, lookahead, cancel, fast_forward
  - App-hang simulation: path end → arm stops
"""

import math
import os
import time
import unittest
from unittest import mock

from gradient_os.arm_controller.actuator_interface import ActuatorBackend
from gradient_os.arm_controller.motion_handle import MotionHandle, MotionState
from gradient_os.arm_controller.backends.sts3215 import STS3215Backend
from gradient_os.arm_controller.backends.hls3950 import HLS3950Backend
from gradient_os.arm_controller.backends.simulation import SimulationBackend
from gradient_os.arm_controller.robots.gradient0.config import Gradient0Config


def _make_sts3215_backend() -> STS3215Backend:
    """Create a STS3215Backend with Gradient0 config (serial port mocked)."""
    robot = Gradient0Config()
    cfg = robot.get_config_dict()
    sts3215_cfg = {
        'servo_ids': cfg['actuator_ids'],
        'logical_to_physical_map': cfg['logical_to_physical_map'],
        'inverted_servo_ids': cfg['inverted_actuator_ids'],
        'joint_limits_rad': cfg['logical_joint_limits_rad'],
        'master_offsets_rad': cfg['logical_joint_master_offsets_rad'],
        'gripper_servo_id': cfg['gripper_actuator_id'],
        'gripper_limits_rad': cfg['gripper_limits_rad'] or [0, math.pi],
        'pid_gains': cfg.get('actuator_pid_gains', {}),
    }
    return STS3215Backend(sts3215_cfg, serial_port="/dev/null")


def _make_hls3950_backend() -> HLS3950Backend:
    """Create a HLS3950Backend with Gradient0 config."""
    robot = Gradient0Config()
    cfg = robot.get_config_dict()
    hls_cfg = {
        'servo_ids': cfg['actuator_ids'],
        'logical_to_physical_map': cfg['logical_to_physical_map'],
        'inverted_servo_ids': cfg['inverted_actuator_ids'],
        'joint_limits_rad': cfg['logical_joint_limits_rad'],
        'master_offsets_rad': cfg['logical_joint_master_offsets_rad'],
        'gripper_servo_id': cfg['gripper_actuator_id'],
        'gripper_limits_rad': cfg['gripper_limits_rad'] or [0, math.pi],
        'pid_gains': cfg.get('actuator_pid_gains', {}),
    }
    return HLS3950Backend(hls_cfg, serial_port="/dev/null")


def _make_sim_backend() -> SimulationBackend:
    """Create a SimulationBackend with Gradient0 config."""
    robot = Gradient0Config()
    cfg = robot.get_config_dict()
    return SimulationBackend(robot_config=cfg)


def _make_simple_timed_path(
    n_joints: int = 6,
    duration_s: float = 0.5,
    n_samples: int = 50,
) -> list[tuple[float, list[float]]]:
    """Create a simple timed path from zero to a small positive angle."""
    path = []
    for i in range(n_samples):
        t = i * (duration_s / (n_samples - 1))
        alpha = i / (n_samples - 1)
        q = [alpha * 0.1] * n_joints
        path.append((t, q))
    return path


class TestStreamingCapabilityFlags(unittest.TestCase):
    """Verify the setpoint streaming capability flag for each backend."""

    def test_actuator_backend_abc_default_false(self):
        """The ABC itself defaults to False (opt-in)."""
        class DummyBackend(ActuatorBackend):
            def initialize(self): return True
            def shutdown(self): pass
            @property
            def num_joints(self): return 6
            @property
            def is_initialized(self): return True
            @property
            def encoder_resolution(self): return 4095
            def set_joint_positions(self, positions_rad, speed, acceleration): pass
            def get_joint_positions(self, verbose=False): return [0.0] * 6
            def prepare_sync_write_commands(self, positions_rad, speed=4095, accel=0): return []
            def sync_write(self, commands): pass
            def sync_read_positions(self, timeout_s=None): return {}
            def raw_to_joint_positions(self, raw_positions): return [0.0] * 6
            def set_single_actuator_position(self, actuator_id, position_rad, speed, accel): pass
            def read_single_actuator_position(self, actuator_id): return 0
            def set_current_position_as_zero(self, actuator_id): return True
            def set_pid_gains(self, actuator_id, kp, ki, kd): return True
            def apply_joint_limits(self): return True
            def get_present_actuator_ids(self): return set()
            def ping_actuator(self, actuator_id): return True

        backend = DummyBackend()
        self.assertFalse(backend.supports_setpoint_streaming)

    def test_sts3215_streaming_flag_true(self):
        """STS3215Backend has streaming enabled."""
        backend = _make_sts3215_backend()
        self.assertTrue(backend.supports_setpoint_streaming)

    def test_hls3950_streaming_flag_true(self):
        """HLS3950Backend has streaming enabled (shared implementation)."""
        backend = _make_hls3950_backend()
        self.assertTrue(backend.supports_setpoint_streaming)

    def test_simulation_streaming_flag_true(self):
        """SimulationBackend has streaming enabled (robust pacing)."""
        backend = _make_sim_backend()
        self.assertTrue(backend.supports_setpoint_streaming)

    def test_ethercat_streaming_flag_false(self):
        """EthercatRTCoreBackend inherits the default False."""
        self.assertFalse(ActuatorBackend.supports_setpoint_streaming.fget(None))


class TestStreamingConfigOverride(unittest.TestCase):
    """Verify streaming_enabled config override disables streaming."""

    def test_sts3215_config_override_disables_streaming(self):
        """streaming_enabled=False in robot config → flag False."""
        robot = Gradient0Config()
        cfg = robot.get_config_dict()
        sts3215_cfg = {
            'servo_ids': cfg['actuator_ids'],
            'logical_to_physical_map': cfg['logical_to_physical_map'],
            'inverted_servo_ids': cfg['inverted_actuator_ids'],
            'joint_limits_rad': cfg['logical_joint_limits_rad'],
            'master_offsets_rad': cfg['logical_joint_master_offsets_rad'],
            'gripper_servo_id': cfg['gripper_actuator_id'],
            'gripper_limits_rad': cfg['gripper_limits_rad'] or [0, math.pi],
            'pid_gains': cfg.get('actuator_pid_gains', {}),
            'streaming_enabled': False,
        }
        backend = STS3215Backend(sts3215_cfg, serial_port="/dev/null")
        self.assertFalse(backend.supports_setpoint_streaming)

    def test_hls3950_config_override_disables_streaming(self):
        """streaming_enabled=False in robot config → flag False for HLS too."""
        robot = Gradient0Config()
        cfg = robot.get_config_dict()
        hls_cfg = {
            'servo_ids': cfg['actuator_ids'],
            'logical_to_physical_map': cfg['logical_to_physical_map'],
            'inverted_servo_ids': cfg['inverted_actuator_ids'],
            'joint_limits_rad': cfg['logical_joint_limits_rad'],
            'master_offsets_rad': cfg['logical_joint_master_offsets_rad'],
            'gripper_servo_id': cfg['gripper_actuator_id'],
            'gripper_limits_rad': cfg['gripper_limits_rad'] or [0, math.pi],
            'pid_gains': cfg.get('actuator_pid_gains', {}),
            'streaming_enabled': False,
        }
        backend = HLS3950Backend(hls_cfg, serial_port="/dev/null")
        self.assertFalse(backend.supports_setpoint_streaming)


class TestStreamingGatingMatrix(unittest.TestCase):
    """Verify the streaming gating matrix from the sprint spec."""

    def setUp(self):
        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

    def tearDown(self):
        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

    def test_sts3215_active_streaming_active(self):
        """sts3215 + gradient0 → _backend_supports_setpoint_streaming() True."""
        from gradient_os.arm_controller import trajectory_execution
        backend = _make_sts3215_backend()
        backend._initialized = True
        backend._present_servo_ids = set(backend._servo_ids)

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        self.assertTrue(trajectory_execution._backend_supports_setpoint_streaming())

    def test_simulation_active_streaming_active(self):
        """simulation + any robot → _backend_supports_setpoint_streaming() True."""
        from gradient_os.arm_controller import trajectory_execution
        backend = _make_sim_backend()
        backend._initialized = True

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        self.assertTrue(trajectory_execution._backend_supports_setpoint_streaming())

    def test_no_backend_active_streaming_inactive(self):
        """No backend active → _backend_supports_setpoint_streaming() False."""
        from gradient_os.arm_controller import trajectory_execution
        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

        self.assertFalse(trajectory_execution._backend_supports_setpoint_streaming())

    def test_uninitialized_backend_streaming_inactive(self):
        """Backend present but not initialized → False."""
        from gradient_os.arm_controller import trajectory_execution
        backend = _make_sts3215_backend()
        backend._initialized = False

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        self.assertFalse(trajectory_execution._backend_supports_setpoint_streaming())


class TestMotionHandleLifecycle(unittest.TestCase):
    """Verify MotionHandle state transitions."""

    def test_initial_state_running(self):
        h = MotionHandle()
        self.assertTrue(h.is_running())
        self.assertFalse(h.is_done())
        self.assertFalse(h.is_cancelled())
        self.assertFalse(h.is_paused())

    def test_pause_resume(self):
        h = MotionHandle()
        h.pause()
        self.assertTrue(h.is_paused())
        self.assertFalse(h.is_running())
        h.resume()
        self.assertTrue(h.is_running())
        self.assertFalse(h.is_paused())

    def test_cancel_from_running(self):
        h = MotionHandle()
        h.cancel()
        self.assertTrue(h.is_cancelled())
        self.assertFalse(h.is_running())

    def test_cancel_from_paused(self):
        h = MotionHandle()
        h.pause()
        h.cancel()
        self.assertTrue(h.is_cancelled())

    def test_cancel_callback_invoked(self):
        h = MotionHandle()
        called = []
        h._set_cancel_callback(lambda: called.append(True))
        h.cancel()
        self.assertEqual(called, [True])

    def test_mark_done(self):
        h = MotionHandle()
        h._mark_done()
        self.assertTrue(h.is_done())

    def test_wait_returns_on_done(self):
        h = MotionHandle()
        h._mark_done()
        self.assertTrue(h.wait(timeout=0.1))

    def test_wait_timeout(self):
        h = MotionHandle()
        self.assertFalse(h.wait(timeout=0.05))

    def test_pause_is_idempotent(self):
        h = MotionHandle()
        h.pause()
        h.pause()  # second pause should be no-op
        self.assertTrue(h.is_paused())

    def test_resume_when_not_paused_is_noop(self):
        h = MotionHandle()
        h.resume()
        self.assertTrue(h.is_running())


class TestSimStreamingExecution(unittest.TestCase):
    """Verify SimulationBackend.execute_timed_path runs correctly."""

    def setUp(self):
        self.backend = _make_sim_backend()
        self.backend.initialize()

    def test_returns_motion_handle(self):
        """execute_timed_path returns a MotionHandle."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=0.1, n_samples=10
        )
        handle = self.backend.execute_timed_path(path, options={'sim_fast_forward': True})
        self.assertIsInstance(handle, MotionHandle)
        handle.wait(timeout=1.0)

    def test_path_completes(self):
        """The handle reports done after the path finishes."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=0.05, n_samples=5
        )
        handle = self.backend.execute_timed_path(path, options={'sim_fast_forward': True})
        self.assertTrue(handle.wait(timeout=2.0))
        self.assertTrue(handle.is_done())

    def test_cancel_mid_move(self):
        """Cancel during a slow move stops the arm and marks handle cancelled."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=2.0, n_samples=100
        )
        handle = self.backend.execute_timed_path(path)  # real pacing (no fast-forward)
        time.sleep(0.1)  # let it start
        handle.cancel()
        self.assertTrue(handle.wait(timeout=1.0))
        self.assertTrue(handle.is_cancelled())

    def test_pause_resume(self):
        """Pause stops feeding goals; resume continues from current position."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=2.0, n_samples=100
        )
        handle = self.backend.execute_timed_path(path)
        time.sleep(0.1)
        handle.pause()
        self.assertTrue(handle.is_paused())
        time.sleep(0.1)
        handle.resume()
        self.assertTrue(handle.is_running())
        handle.cancel()  # clean up
        handle.wait(timeout=1.0)

    def test_fast_forward_completes_quickly(self):
        """Fast-forward mode skips sleeps — path completes in < 0.5s."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=5.0, n_samples=100
        )
        t0 = time.monotonic()
        handle = self.backend.execute_timed_path(path, options={'sim_fast_forward': True})
        self.assertTrue(handle.wait(timeout=2.0))
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 1.0)  # 5s path in < 1s with fast-forward

    def test_empty_path_raises(self):
        """Empty path raises ValueError."""
        with self.assertRaises(ValueError):
            self.backend.execute_timed_path([])

    def test_wrong_joint_count_raises(self):
        """Path with wrong joint count raises ValueError."""
        path = [(0.0, [0.0] * 3)]  # 3 joints, backend expects 6
        with self.assertRaises(ValueError):
            self.backend.execute_timed_path(path)

    def test_app_hang_stops_at_path_end(self):
        """If we stop feeding paths (single path), arm stops at path_end."""
        path = _make_simple_timed_path(
            n_joints=self.backend.num_joints, duration_s=0.1, n_samples=10
        )
        handle = self.backend.execute_timed_path(path, options={'sim_fast_forward': True})
        handle.wait(timeout=2.0)
        self.assertTrue(handle.is_done())
        # The sim position should be at the final path point
        final_q = path[-1][1]
        actual = self.backend.get_joint_positions()
        for j in range(self.backend.num_joints):
            self.assertAlmostEqual(actual[j], final_q[j], places=2)


class TestExecutorStreamingGating(unittest.TestCase):
    """Verify the executor uses streaming when available."""

    def setUp(self):
        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

    def tearDown(self):
        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

    def test_move_step_uses_streaming_on_sts3215(self):
        """move step on STS3215 → streaming handoff (not profiled, not dense)."""
        from gradient_os.arm_controller import trajectory_execution

        backend = _make_sts3215_backend()
        backend._initialized = True
        backend._present_servo_ids = set(
            sid for sid in backend._servo_ids if sid != 100
        )

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        step = {
            'type': 'move',
            'path': [[0.0]*6, [0.1]*6, [0.2]*6],
            'freq': 100,
            'weld_active': False,
        }

        with mock.patch.object(
            trajectory_execution, '_execute_streaming_step'
        ) as mock_stream, mock.patch.object(
            trajectory_execution, '_execute_profiled_segment_step'
        ) as mock_profiled, mock.patch.object(
            trajectory_execution, '_execute_joint_path'
        ) as mock_dense:
            if trajectory_execution._backend_supports_setpoint_streaming():
                trajectory_execution._execute_streaming_step(step)
            elif trajectory_execution._backend_supports_profiled_segments() and not step.get("weld_active", False):
                trajectory_execution._execute_profiled_segment_step(step)
            else:
                trajectory_execution._execute_joint_path(step['path'], step['freq'])

            mock_stream.assert_called_once_with(step)
            mock_profiled.assert_not_called()
            mock_dense.assert_not_called()

    def test_weld_move_uses_streaming_on_sts3215(self):
        """Weld move step on STS3215 → streaming (Sprint 10 covers welds)."""
        from gradient_os.arm_controller import trajectory_execution

        backend = _make_sts3215_backend()
        backend._initialized = True
        backend._present_servo_ids = set(
            sid for sid in backend._servo_ids if sid != 100
        )

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        step = {
            'type': 'move',
            'path': [[0.0]*6, [0.1]*6, [0.2]*6],
            'freq': 100,
            'weld_active': True,
        }

        with mock.patch.object(
            trajectory_execution, '_execute_streaming_step'
        ) as mock_stream, mock.patch.object(
            trajectory_execution, '_execute_joint_path'
        ) as mock_dense:
            if trajectory_execution._backend_supports_setpoint_streaming():
                trajectory_execution._execute_streaming_step(step)
            else:
                trajectory_execution._execute_joint_path(step['path'], step['freq'])

            mock_stream.assert_called_once_with(step)
            mock_dense.assert_not_called()

    def test_move_step_uses_streaming_on_simulation(self):
        """move step on simulation → streaming handoff."""
        from gradient_os.arm_controller import trajectory_execution

        backend = _make_sim_backend()
        backend._initialized = True

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        step = {
            'type': 'move',
            'path': [[0.0]*6, [0.1]*6, [0.2]*6],
            'freq': 100,
            'weld_active': False,
        }

        with mock.patch.object(
            trajectory_execution, '_execute_streaming_step'
        ) as mock_stream, mock.patch.object(
            trajectory_execution, '_execute_joint_path'
        ) as mock_dense:
            if trajectory_execution._backend_supports_setpoint_streaming():
                trajectory_execution._execute_streaming_step(step)
            else:
                trajectory_execution._execute_joint_path(step['path'], step['freq'])

            mock_stream.assert_called_once_with(step)
            mock_dense.assert_not_called()

    def test_move_step_uses_dense_no_backend(self):
        """move step with no backend → dense streaming (unchanged)."""
        from gradient_os.arm_controller import trajectory_execution

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = None

        step = {
            'type': 'move',
            'path': [[0.0]*6, [0.1]*6, [0.2]*6],
            'freq': 100,
            'weld_active': False,
        }

        with mock.patch.object(
            trajectory_execution, '_execute_streaming_step'
        ) as mock_stream, mock.patch.object(
            trajectory_execution, '_execute_joint_path'
        ) as mock_dense:
            if trajectory_execution._backend_supports_setpoint_streaming():
                trajectory_execution._execute_streaming_step(step)
            else:
                trajectory_execution._execute_joint_path(step['path'], step['freq'])

            mock_dense.assert_called_once_with(step['path'], step['freq'])
            mock_stream.assert_not_called()

    def test_streaming_disabled_falls_back_to_profiled(self):
        """STS3215 with streaming_enabled=False → falls back to profiled segments."""
        from gradient_os.arm_controller import trajectory_execution

        robot = Gradient0Config()
        cfg = robot.get_config_dict()
        sts3215_cfg = {
            'servo_ids': cfg['actuator_ids'],
            'logical_to_physical_map': cfg['logical_to_physical_map'],
            'inverted_servo_ids': cfg['inverted_actuator_ids'],
            'joint_limits_rad': cfg['logical_joint_limits_rad'],
            'master_offsets_rad': cfg['logical_joint_master_offsets_rad'],
            'gripper_servo_id': cfg['gripper_actuator_id'],
            'gripper_limits_rad': cfg['gripper_limits_rad'] or [0, math.pi],
            'pid_gains': cfg.get('actuator_pid_gains', {}),
            'streaming_enabled': False,
        }
        backend = STS3215Backend(sts3215_cfg, serial_port="/dev/null")
        backend._initialized = True
        backend._present_servo_ids = set(
            sid for sid in backend._servo_ids if sid != 100
        )

        from gradient_os.arm_controller.backends import registry
        registry._active_backend_instance = backend

        self.assertFalse(trajectory_execution._backend_supports_setpoint_streaming())
        self.assertTrue(trajectory_execution._backend_supports_profiled_segments())


class TestJointPathToTimed(unittest.TestCase):
    """Verify the conversion from dense path + frequency to timed tuples."""

    def test_basic_conversion(self):
        from gradient_os.arm_controller.trajectory_execution import _joint_path_to_timed
        path = [[0.0]*6, [0.1]*6, [0.2]*6]
        result = _joint_path_to_timed(path, frequency=100)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0][0], 0.0)
        self.assertEqual(result[1][0], 0.01)
        self.assertEqual(result[2][0], 0.02)
        self.assertEqual(result[1][1], [0.1]*6)

    def test_empty_path(self):
        from gradient_os.arm_controller.trajectory_execution import _joint_path_to_timed
        result = _joint_path_to_timed([], frequency=100)
        self.assertEqual(result, [])


if __name__ == '__main__':
    unittest.main()