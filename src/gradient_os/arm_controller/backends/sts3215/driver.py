# backends/sts3215/driver.py
#
# Feetech STS3215 servo backend implementation for GradientOS.
# This class implements the ActuatorBackend interface for Feetech STS3215 servos.
#
# The driver handles:
# - Serial port management and auto-detection
# - Mapping between logical joints and physical servos
# - Angle-to-raw-value conversion (including servo orientation)
# - PID gain configuration
# - Calibration and limit setting

import math
import os
import time
import json
import glob
from typing import Optional, Callable
import serial
import numpy as np

from ...actuator_interface import ActuatorBackend
from . import config
from . import protocol


class STS3215Backend(ActuatorBackend):
    """
    Feetech STS3215 servo backend for GradientOS.
    
    This class provides hardware control for Feetech STS3215 serial bus servos
    using the SCS/STS protocol.  It implements the ActuatorBackend interface,
    allowing GradientOS to use STS3215 servos for robot control.
    
    Configuration is provided at initialization time, making this class
    reusable for different robot configurations.
    
    Example usage:
    ```python
    # Define robot configuration
    robot_config = {
        'servo_ids': [10, 20, 21, 30, 31, 40, 50, 60],
        'logical_to_physical_map': {
            0: [0],      # J1 -> servo index 0 (ID 10)
            1: [1, 2],   # J2 -> servo indices 1, 2 (IDs 20, 21)
            2: [3, 4],   # J3 -> servo indices 3, 4 (IDs 30, 31)
            3: [5],      # J4 -> servo index 5 (ID 40)
            4: [6],      # J5 -> servo index 6 (ID 50)
            5: [7],      # J6 -> servo index 7 (ID 60)
        },
        'inverted_servo_ids': {10, 20, 30, 40, 50, 60},
        'joint_limits_rad': [
            [-3.14, 3.14],  # J1
            [-1.57, 1.57],  # J2
            # ... etc
        ],
        'gripper_servo_id': 100,  # Optional
    }
    
    backend = STS3215Backend(robot_config)
    backend.initialize()
    ```
    """
    
    def __init__(
        self,
        robot_config: dict,
        serial_port: Optional[str] = None,
        baud_rate: int = config.DEFAULT_BAUD_RATE,
    ):
        """
        Initialize the STS3215 backend with robot configuration.
        
        Args:
            robot_config: Dictionary containing robot-specific configuration:
                - servo_ids: List of physical servo IDs in order
                - logical_to_physical_map: Dict mapping logical joint index to list of physical servo indices
                - inverted_servo_ids: Set of servo IDs that use inverted mapping
                - joint_limits_rad: List of [min, max] limits for each logical joint
                - master_offsets_rad: Optional list of calibration offsets per logical joint
                - gripper_servo_id: Optional ID for gripper servo
                - gripper_limits_rad: Optional [min, max] for gripper
                - pid_gains: Optional dict mapping servo_id to (kp, ki, kd) tuple
            serial_port: Serial port path. If None, will attempt auto-detection.
            baud_rate: Serial baud rate.
        """
        # Store configuration
        self._servo_ids: list[int] = robot_config['servo_ids']
        self._logical_to_physical_map: dict[int, list[int]] = robot_config['logical_to_physical_map']
        self._inverted_servo_ids: set[int] = set(robot_config.get('inverted_servo_ids', []))
        self._joint_limits_rad: list[list[float]] = robot_config['joint_limits_rad']
        self._master_offsets_rad: list[float] = robot_config.get(
            'master_offsets_rad', 
            [0.0] * len(robot_config['joint_limits_rad'])
        )
        self._gripper_servo_id: Optional[int] = robot_config.get('gripper_servo_id')
        self._gripper_limits_rad: list[float] = robot_config.get('gripper_limits_rad', [0, math.pi])
        self._default_pid_gains: dict[int, tuple[int, int, int]] = robot_config.get('pid_gains', {})
        
        # Serial configuration
        self._serial_port_path = serial_port
        self._baud_rate = baud_rate
        
        # Runtime state
        self._ser: Optional[serial.Serial] = None
        self._initialized = False
        self._present_servo_ids: set[int] = set()
        self._gripper_present = False
        self._current_positions_rad: list[float] = [0.0] * self.num_joints
        self._current_gripper_rad: float = 0.0
        
        # Build mapping ranges for each physical servo
        # Default: -π to +π for all servos
        self._mapping_ranges_rad: list[tuple[float, float]] = [
            (-math.pi, math.pi) for _ in self._servo_ids
        ]
        
        # Alert callback (can be set by user for error reporting)
        self._alert_callback: Optional[Callable] = None
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def num_joints(self) -> int:
        """Number of logical joints this backend controls."""
        return len(self._logical_to_physical_map)
    
    @property
    def is_initialized(self) -> bool:
        """Check if the backend has been initialized."""
        return self._initialized
    
    @property
    def has_gripper(self) -> bool:
        """Check if a gripper is present and detected."""
        return self._gripper_present
    
    @property
    def gripper_actuator_id(self) -> Optional[int]:
        """Get the gripper servo ID."""
        return self._gripper_servo_id if self._gripper_present else None
    
    @property
    def serial_port(self) -> Optional[serial.Serial]:
        """Get the serial port handle (for advanced usage)."""
        return self._ser
    
    @property
    def encoder_resolution(self) -> int:
        """
        Returns the encoder resolution for Feetech STS3215 servos.
        
        Feetech STS3215 and similar servos use 12-bit encoders with
        a maximum value of 4095.
        
        Returns:
            int: 4095 (12-bit encoder max value)
        """
        return 4095
    
    @property
    def supports_profiled_segments(self) -> bool:
        """
        Feetech STS3215 servos have an internal trapezoidal profiler.
        
        When True, the trajectory executor collapses dense waypoint streams
        into ONE goal command per segment (endpoint position + moderate
        speed/accel caps), letting the firmware profile the whole move — the
        "Home-button" pattern generalised to all moves.  This eliminates the
        stop-go backlash oscillation caused by streaming 50-100 goals/sec
        with speed=4095, accel=0.
        
        See: docs/jerkiness-diagnosis.md §10
             feetech-project/sprints/sprint-04-endpoint-paradigm-quickfix.md
        
        Returns:
            bool: True — profiled-segment motion is supported and desired.
        """
        return True
    
    def set_alert_callback(self, callback: Callable) -> None:
        """
        Set a callback function for error/warning alerts.
        
        Args:
            callback: Function with signature (servo_id, error_code, error_names)
        """
        self._alert_callback = callback
    
    # =========================================================================
    # Initialization & Shutdown
    # =========================================================================
    
    def initialize(self) -> bool:
        """
        Initialize the STS3215 servo system.
        
        This method:
        1. Opens the serial port (with auto-detection if needed)
        2. Pings all configured servos to detect presence
        3. Sets default PID gains for present servos
        
        Returns:
            bool: True if initialization was successful.
        """
        print("[STS3215] Initializing servo backend...")
        
        # Clear protocol-level cache
        protocol.clear_present_servo_ids()
        
        # Resolve and open serial port
        resolved_port = self._resolve_serial_port()
        if not resolved_port:
            print("[STS3215] ERROR: Could not find a valid serial port.")
            return False
        
        try:
            self._ser = serial.Serial(resolved_port, self._baud_rate, timeout=0.1)
            print(f"[STS3215] Serial port {resolved_port} opened at {self._baud_rate} baud.")
        except serial.SerialException as e:
            print(f"[STS3215] ERROR: Could not open serial port {resolved_port}: {e}")
            return False
        
        # Ping all configured servos
        print("[STS3215] Pinging configured servos...")
        all_servo_ids = list(self._servo_ids)
        if self._gripper_servo_id and self._gripper_servo_id not in all_servo_ids:
            all_servo_ids.append(self._gripper_servo_id)
        
        for servo_id in all_servo_ids:
            if protocol.ping(self._ser, servo_id):
                self._present_servo_ids.add(servo_id)
                print(f"[STS3215]   - Servo {servo_id}: PRESENT")
            else:
                print(f"[STS3215]   - Servo {servo_id}: ABSENT")
        
        # Check gripper presence
        if self._gripper_servo_id and self._gripper_servo_id in self._present_servo_ids:
            self._gripper_present = True
            print(f"[STS3215] Gripper (ID {self._gripper_servo_id}) is present.")
        
        # Set PID gains for present servos
        print("[STS3215] Setting PID gains for present servos...")
        for servo_id in self._present_servo_ids:
            kp, ki, kd = self._default_pid_gains.get(
                servo_id, 
                (config.DEFAULT_KP, config.DEFAULT_KI, config.DEFAULT_KD)
            )
            self.set_pid_gains(servo_id, kp, ki, kd)
            time.sleep(0.02)
        
        self._initialized = True
        print("[STS3215] Backend initialization complete.")
        return True
    
    def shutdown(self) -> None:
        """Close the serial port and clean up."""
        if self._ser and self._ser.is_open:
            self._ser.close()
            print("[STS3215] Serial port closed.")
        self._initialized = False
        self._present_servo_ids = set()
    
    # =========================================================================
    # Position Control
    # =========================================================================
    
    def set_joint_positions(
        self,
        positions_rad: list[float],
        speed: float,
        acceleration: float,
    ) -> None:
        """
        Command all joints to specified positions.
        
        Args:
            positions_rad: Target positions in radians for each logical joint.
            speed: Speed value (0-4095 for servo register).
            acceleration: Acceleration in deg/s² (converted to register value).
        """
        if not self._initialized:
            print("[STS3215] ERROR: Backend not initialized.")
            return
        
        if len(positions_rad) != self.num_joints:
            raise ValueError(f"Expected {self.num_joints} positions, got {len(positions_rad)}")
        
        # Store commanded positions
        self._current_positions_rad = list(positions_rad)
        
        # Build sync write commands
        commands = self.prepare_sync_write_commands(
            positions_rad,
            speed=int(speed),
            accel=self._deg_s2_to_accel_reg(acceleration),
        )
        
        # Execute sync write
        self.sync_write(commands)
    
    def get_joint_positions(self, verbose: bool = False) -> list[float]:
        """
        Read current positions of all logical joints.
        
        Args:
            verbose: If True, print debug information.
        
        Returns:
            List of joint positions in radians.
        """
        if not self._initialized:
            return [0.0] * self.num_joints
        
        # Get IDs for arm servos (excluding gripper)
        arm_servo_ids = [
            sid for sid in self._servo_ids 
            if sid in self._present_servo_ids and sid != self._gripper_servo_id
        ]
        
        # Sync read positions
        raw_positions = protocol.sync_read_positions(
            self._ser, 
            arm_servo_ids,
            alert_callback=self._alert_callback,
        )
        
        # Convert to logical joint angles
        positions = self.raw_to_joint_positions(raw_positions)
        
        # Update internal state
        self._current_positions_rad = positions
        
        if verbose:
            angles_deg = np.rad2deg(positions)
            print(f"[STS3215] Current positions (deg): {np.round(angles_deg, 2)}")
        
        return positions
    
    # =========================================================================
    # High-Speed Batch Operations
    # =========================================================================
    
    def prepare_sync_write_commands(
        self,
        positions_rad: list[float],
        speed: int = 4095,
        accel: int = 0,
    ) -> list[tuple]:
        """
        Pre-compute sync write commands for given joint positions.
        
        Args:
            positions_rad: Target positions in radians.
            speed: Speed value (0-4095).
            accel: Acceleration register value (0-254).
        
        Returns:
            List of (servo_id, position, speed, accel) tuples.
        """
        commands = []
        
        for logical_idx, physical_indices in self._logical_to_physical_map.items():
            # Apply master offset
            angle_with_offset = positions_rad[logical_idx] + self._master_offsets_rad[logical_idx]
            
            for physical_idx in physical_indices:
                servo_id = self._servo_ids[physical_idx]
                
                # Skip absent servos
                if servo_id not in self._present_servo_ids:
                    continue
                
                # Convert angle to raw value
                raw_pos = self._angle_to_raw(angle_with_offset, physical_idx)
                commands.append((servo_id, raw_pos, speed, accel))
        
        return commands
    
    def sync_write(self, commands: list[tuple]) -> None:
        """Execute a batch write with pre-computed commands."""
        if not self._initialized or not commands:
            return
        protocol.sync_write_goal_pos_speed_accel(self._ser, commands)
    
    # =========================================================================
    # Profiled-Segment Helper (Sprint 04 — endpoint-paradigm quick fix)
    # =========================================================================
    
    def plan_profiled_segment(
        self,
        start_q: list[float],
        end_q: list[float],
        per_joint_velocities: Optional[list[float]] = None,
        flat_speed: Optional[int] = None,
    ) -> list[tuple[int, int, int, int]]:
        """
        Plan a single profiled-segment goal command for all logical joints.
        
        Computes ONE sync_write command list (endpoint position + per-joint
        speed cap + fixed moderate accel) that lets the Feetech firmware's
        internal trapezoidal profiler run the whole segment.  This is the
        "Home-button" pattern generalised to every move — eliminates the
        stop-go backlash oscillation from dense streaming.
        
        Per-joint speed caps are sized so the slowest joint (largest |Δq|)
        runs at the flat conservative cap and faster joints are scaled down
        to match arrival times, so all joints finish together.  This requires
        the rad/s → speed-register LSB conversion (Sprint 07 Part A); until
        that lands, a flat cap is used for all joints.
        
        Args:
            start_q: Starting logical joint angles (radians).  Not used in
                     the command itself (the servo knows its current position),
                     but reserved for future per-joint cap sizing that needs
                     the per-joint Δq.
            end_q: Target logical joint angles (radians), one per logical joint.
            per_joint_velocities: Optional per-joint max velocities in rad/s.
                                  If None or not yet calibrated, the flat
                                  conservative cap from config is used.
            flat_speed: Optional override for the baseline speed register value
                        (0-4095).  If None, uses config.PROFILED_SEGMENT_DEFAULT_SPEED.
        
        Returns:
            list[tuple[int, int, int, int]]: Sync-write commands in the format
            (servo_id, raw_position, speed_register, accel_register), ready
            to pass to backend.sync_write().
        """
        if len(end_q) != self.num_joints:
            raise ValueError(
                f"Expected {self.num_joints} target positions, got {len(end_q)}"
            )
        
        base_speed = flat_speed if flat_speed is not None else config.PROFILED_SEGMENT_DEFAULT_SPEED
        base_speed = max(
            config.PROFILED_SEGMENT_SPEED_MIN,
            min(config.PROFILED_SEGMENT_SPEED_MAX, base_speed),
        )
        fixed_accel = config.PROFILED_SEGMENT_DEFAULT_ACCEL
        
        # --- Per-joint cap sizing (slowest joint sets duration) ---
        # Compute per-joint |Δq|, pick the slowest joint as the duration-setter,
        # then scale other joints' speed caps down proportionally so all
        # joints arrive together.  Uses the flat cap as the baseline speed
        # for the slowest joint.
        speeds_per_logical: list[int] = [base_speed] * self.num_joints
        if start_q is not None and len(start_q) == self.num_joints:
            deltas = [abs(end_q[j] - start_q[j]) for j in range(self.num_joints)]
            max_delta = max(deltas) if deltas else 0.0
            if max_delta > 1e-9:
                for j in range(self.num_joints):
                    # Scaled speed: proportional to this joint's share of the
                    # total travel, so all joints finish in the same time.
                    ratio = deltas[j] / max_delta
                    scaled = int(round(base_speed * ratio))
                    speeds_per_logical[j] = max(
                        config.PROFILED_SEGMENT_SPEED_MIN,
                        min(config.PROFILED_SEGMENT_SPEED_MAX, scaled),
                    )
        
        # --- Build sync_write commands ---
        commands: list[tuple[int, int, int, int]] = []
        
        for logical_idx, physical_indices in self._logical_to_physical_map.items():
            angle_with_offset = end_q[logical_idx] + self._master_offsets_rad[logical_idx]
            speed_reg = speeds_per_logical[logical_idx]
            
            for physical_idx in physical_indices:
                servo_id = self._servo_ids[physical_idx]
                
                if servo_id not in self._present_servo_ids:
                    continue
                
                raw_pos = self._angle_to_raw(angle_with_offset, physical_idx)
                commands.append((servo_id, raw_pos, speed_reg, fixed_accel))
        
        return commands
    
    def execute_profiled_segment(
        self,
        start_q: list[float],
        end_q: list[float],
        per_joint_velocities: Optional[list[float]] = None,
    ) -> None:
        """
        Plan and execute a single profiled-segment move (blocking).
        
        Convenience wrapper around plan_profiled_segment() + sync_write().
        Commands all joints to their endpoint with per-joint speed caps and
        a moderate fixed accel, letting the firmware trapezoidal profiler run
        the whole segment.  The caller is responsible for waiting for the
        move to complete (the firmware profiles autonomously).
        
        Args:
            start_q: Starting logical joint angles (radians).
            end_q: Target logical joint angles (radians).
            per_joint_velocities: Optional per-joint max velocities (rad/s).
        """
        if not self._initialized:
            print("[STS3215] ERROR: Backend not initialized.")
            return
        
        commands = self.plan_profiled_segment(start_q, end_q, per_joint_velocities)
        self._current_positions_rad = list(end_q)
        self.sync_write(commands)
    
    def sync_read_positions(self, timeout_s: Optional[float] = None) -> dict[int, int]:
        """
        Batch read positions from all arm servos.
        
        Returns:
            Dict mapping servo_id to raw position value.
        """
        if not self._initialized:
            return {}
        
        arm_servo_ids = [
            sid for sid in self._servo_ids 
            if sid in self._present_servo_ids and sid != self._gripper_servo_id
        ]
        
        return protocol.sync_read_positions(
            self._ser,
            arm_servo_ids,
            timeout_s=timeout_s,
            alert_callback=self._alert_callback,
        )

    def sync_read_block(
        self,
        servo_ids: list[int],
        start_address: int,
        data_len: int,
        timeout_s: Optional[float] = None,
        poll_delay_s: float = 0.0,
        diagnostics: bool = False,
    ) -> dict[int, bytes]:
        """
        Batch read a contiguous register block from specified servos.
        
        Args:
            servo_ids: Servo IDs to read from.
            start_address: Register start address.
            data_len: Number of bytes to read per servo.
            timeout_s: Optional timeout for the read operation in seconds.
            poll_delay_s: Optional delay after issuing the read before collecting responses.
            diagnostics: Whether to record timing diagnostics.
        
        Returns:
            dict[int, bytes]: Mapping of servo_id to raw bytes.
        """
        if not self._initialized:
            return {}

        filtered_ids = [sid for sid in servo_ids if sid in self._present_servo_ids]
        if not filtered_ids:
            return {}

        return protocol.sync_read_block(
            self._ser,
            filtered_ids,
            start_address=start_address,
            data_len=data_len,
            timeout_s=timeout_s,
            poll_delay_s=poll_delay_s,
            diagnostics=diagnostics,
        )
    
    def raw_to_joint_positions(self, raw_positions: dict[int, int]) -> list[float]:
        """
        Convert raw servo values to logical joint angles.
        
        Args:
            raw_positions: Dict mapping servo_id to raw value.
        
        Returns:
            List of joint angles in radians.
        """
        positions = [0.0] * self.num_joints
        
        for logical_idx, physical_indices in self._logical_to_physical_map.items():
            angles = []
            for physical_idx in physical_indices:
                servo_id = self._servo_ids[physical_idx]
                if servo_id in raw_positions:
                    raw = raw_positions[servo_id]
                    angle = self._raw_to_angle(raw, physical_idx)
                    angles.append(angle)
            
            if angles:
                # Average angles for multi-servo joints
                avg_angle = np.mean(angles)
                # Remove master offset
                positions[logical_idx] = avg_angle - self._master_offsets_rad[logical_idx]
        
        return positions
    
    # =========================================================================
    # Single Actuator Control
    # =========================================================================
    
    def set_single_actuator_position(
        self,
        actuator_id: int,
        position_rad: float,
        speed: int,
        accel: int,
    ) -> None:
        """Command a single actuator to a position."""
        if not self._initialized:
            return
        
        if actuator_id not in self._present_servo_ids:
            print(f"[STS3215] Cannot command absent servo {actuator_id}")
            return
        
        # Find config index for this servo
        try:
            config_idx = self._servo_ids.index(actuator_id)
        except ValueError:
            # Might be gripper
            if actuator_id == self._gripper_servo_id:
                config_idx = len(self._servo_ids)  # Use a placeholder index
            else:
                print(f"[STS3215] Unknown servo ID {actuator_id}")
                return
        
        # Convert angle to raw
        if actuator_id == self._gripper_servo_id:
            raw_pos = self._gripper_angle_to_raw(position_rad)
        else:
            raw_pos = self._angle_to_raw(position_rad, config_idx)
        
        accel_reg = self._deg_s2_to_accel_reg(accel) if accel > 0 else 0
        
        # Send via sync write for consistency
        protocol.sync_write_goal_pos_speed_accel(
            self._ser,
            [(actuator_id, raw_pos, speed, accel_reg)]
        )
    
    def read_single_actuator_position(self, actuator_id: int) -> Optional[int]:
        """Read the raw position of a single actuator."""
        if not self._initialized:
            return None
        return protocol.read_position(self._ser, actuator_id, self._alert_callback)
    
    # =========================================================================
    # Calibration & Configuration
    # =========================================================================
    
    def set_current_position_as_zero(self, actuator_id: int) -> bool:
        """
        Set the current position of an actuator as its zero point.
        
        Args:
            actuator_id: The servo ID to calibrate.
        
        Returns:
            bool: True on success.
        """
        if not self._initialized:
            return False
        
        if actuator_id not in self._present_servo_ids:
            print(f"[STS3215] Cannot calibrate absent servo {actuator_id}")
            return False
        
        print(f"[STS3215] Calibrating servo {actuator_id} - setting current position as zero...")
        result = protocol.calibrate_middle_position(self._ser, actuator_id)
        
        if result:
            time.sleep(0.1)  # Wait for EEPROM write
            print(f"[STS3215] Servo {actuator_id} calibrated successfully.")
        else:
            print(f"[STS3215] Failed to calibrate servo {actuator_id}.")
        
        return result
    
    def set_pid_gains(self, actuator_id: int, kp: int, ki: int, kd: int) -> bool:
        """
        Set PID gains for a servo.
        
        Args:
            actuator_id: The servo ID.
            kp: Proportional gain (0-254).
            ki: Integral gain (0-254).
            kd: Derivative gain (0-254).
        
        Returns:
            bool: True on success.
        """
        if not self._initialized:
            return False
        
        # Clamp values
        kp = max(0, min(254, int(kp)))
        ki = max(0, min(254, int(ki)))
        kd = max(0, min(254, int(kd)))
        
        success = True
        if not protocol.write_register_byte(self._ser, actuator_id, config.SERVO_ADDR_POS_KP, kp):
            success = False
        time.sleep(0.01)
        
        if not protocol.write_register_byte(self._ser, actuator_id, config.SERVO_ADDR_POS_KI, ki):
            success = False
        time.sleep(0.01)
        
        if not protocol.write_register_byte(self._ser, actuator_id, config.SERVO_ADDR_POS_KD, kd):
            success = False
        time.sleep(0.01)
        
        if success:
            print(f"[STS3215] Set PID for servo {actuator_id}: Kp={kp}, Ki={ki}, Kd={kd}")
        
        return success
    
    def apply_joint_limits(self) -> bool:
        """
        Apply joint limits to all servos.
        
        Returns:
            bool: True if all limits were set successfully.
        """
        if not self._initialized:
            return False
        
        print("[STS3215] Applying joint limits to servos...")
        all_ok = True
        
        for logical_idx, physical_indices in self._logical_to_physical_map.items():
            limits = self._joint_limits_rad[logical_idx]
            
            for physical_idx in physical_indices:
                servo_id = self._servo_ids[physical_idx]
                
                if servo_id not in self._present_servo_ids:
                    continue
                
                # Convert limits to raw values
                min_raw = self._angle_to_raw(limits[0], physical_idx)
                max_raw = self._angle_to_raw(limits[1], physical_idx)
                
                # Ensure min < max for the register
                final_min = min(min_raw, max_raw)
                final_max = max(min_raw, max_raw)
                
                if not protocol.write_angle_limits(self._ser, servo_id, final_min, final_max):
                    all_ok = False
                    print(f"[STS3215] Failed to set limits for servo {servo_id}")
                
                time.sleep(0.02)
        
        # Handle gripper limits
        if self._gripper_present and self._gripper_servo_id:
            min_raw = self._gripper_angle_to_raw(self._gripper_limits_rad[0])
            max_raw = self._gripper_angle_to_raw(self._gripper_limits_rad[1])
            final_min = min(min_raw, max_raw)
            final_max = max(min_raw, max_raw)
            
            if not protocol.write_angle_limits(self._ser, self._gripper_servo_id, final_min, final_max):
                all_ok = False
        
        return all_ok
    
    # =========================================================================
    # Gripper Support
    # =========================================================================
    
    def set_gripper_position(self, position_rad: float, speed: int = 50, accel: int = 0) -> None:
        """Set the gripper position."""
        if not self._gripper_present or not self._gripper_servo_id:
            print("[STS3215] No gripper present.")
            return
        
        # Clamp to limits
        min_rad, max_rad = self._gripper_limits_rad
        position_rad = max(min_rad, min(max_rad, position_rad))
        
        self.set_single_actuator_position(
            self._gripper_servo_id,
            position_rad,
            speed,
            accel
        )
        self._current_gripper_rad = position_rad
    
    def get_gripper_position(self) -> Optional[float]:
        """Get current gripper position."""
        if not self._gripper_present or not self._gripper_servo_id:
            return None
        
        raw = protocol.read_position(self._ser, self._gripper_servo_id, self._alert_callback)
        if raw is not None:
            angle = self._gripper_raw_to_angle(raw)
            self._current_gripper_rad = angle
            return angle
        return None
    
    # =========================================================================
    # Diagnostics
    # =========================================================================
    
    def get_present_actuator_ids(self) -> set[int]:
        """Get the set of detected servo IDs."""
        return self._present_servo_ids.copy()
    
    def ping_actuator(self, actuator_id: int) -> bool:
        """Check if a servo responds to ping."""
        if not self._ser or not self._ser.is_open:
            return False
        return protocol.ping(self._ser, actuator_id)
    
    def factory_reset_actuator(self, actuator_id: int) -> bool:
        """Factory reset a servo."""
        if not self._initialized:
            return False
        return protocol.factory_reset(self._ser, actuator_id)
    
    def restart_actuator(self, actuator_id: int) -> bool:
        """Restart a servo."""
        if not self._initialized:
            return False
        return protocol.restart(self._ser, actuator_id)
    
    # =========================================================================
    # Internal Helper Methods
    # =========================================================================
    
    def _is_servo_inverted(self, physical_idx: int) -> bool:
        """Check if a servo uses inverted mapping."""
        servo_id = self._servo_ids[physical_idx]
        return servo_id in self._inverted_servo_ids
    
    def _angle_to_raw(self, angle_rad: float, physical_idx: int) -> int:
        """
        Convert an angle in radians to a raw servo value (0-4095).
        
        Args:
            angle_rad: Angle in radians.
            physical_idx: Index in the servo_ids list.
        
        Returns:
            int: Raw servo value (0-4095).
        """
        min_rad, max_rad = self._mapping_ranges_rad[physical_idx]
        
        # Clamp angle to range
        angle_clamped = max(min_rad, min(max_rad, angle_rad))
        
        # Normalize to 0-1
        normalized = (angle_clamped - min_rad) / (max_rad - min_rad)
        
        # Apply inversion if needed
        if self._is_servo_inverted(physical_idx):
            raw = (1.0 - normalized) * 4095.0
        else:
            raw = normalized * 4095.0
        
        return int(round(max(0, min(4095, raw))))
    
    def _raw_to_angle(self, raw_value: int, physical_idx: int) -> float:
        """
        Convert a raw servo value to an angle in radians.
        
        Args:
            raw_value: Raw servo value (0-4095).
            physical_idx: Index in the servo_ids list.
        
        Returns:
            float: Angle in radians.
        """
        raw_clamped = max(0, min(4095, raw_value))
        min_rad, max_rad = self._mapping_ranges_rad[physical_idx]
        
        # Normalize raw to 0-1
        normalized = raw_clamped / 4095.0
        
        # Apply inversion if needed
        if self._is_servo_inverted(physical_idx):
            normalized = 1.0 - normalized
        
        # Convert to angle
        angle = normalized * (max_rad - min_rad) + min_rad
        return angle
    
    def _gripper_angle_to_raw(self, angle_rad: float) -> int:
        """Convert gripper angle to raw value."""
        # Assume gripper uses same mapping as arm servos
        min_rad, max_rad = -math.pi, math.pi
        angle_clamped = max(min_rad, min(max_rad, angle_rad))
        normalized = (angle_clamped - min_rad) / (max_rad - min_rad)
        
        # Check if gripper is inverted
        if self._gripper_servo_id in self._inverted_servo_ids:
            raw = (1.0 - normalized) * 4095.0
        else:
            raw = normalized * 4095.0
        
        return int(round(max(0, min(4095, raw))))
    
    def _gripper_raw_to_angle(self, raw_value: int) -> float:
        """Convert raw value to gripper angle."""
        raw_clamped = max(0, min(4095, raw_value))
        min_rad, max_rad = -math.pi, math.pi
        normalized = raw_clamped / 4095.0
        
        if self._gripper_servo_id in self._inverted_servo_ids:
            normalized = 1.0 - normalized
        
        return normalized * (max_rad - min_rad) + min_rad
    
    def _deg_s2_to_accel_reg(self, accel_deg_s2: float) -> int:
        """Convert deg/s² to acceleration register value."""
        if accel_deg_s2 <= 0:
            return 0  # Max acceleration
        reg_val = int(round(accel_deg_s2 / config.ACCELERATION_SCALE_FACTOR))
        return max(1, min(254, reg_val))
    
    # =========================================================================
    # Serial Port Auto-Detection
    # =========================================================================
    
    def _resolve_serial_port(self) -> Optional[str]:
        """
        Determine the serial port to use.
        
        Priority:
        1. Explicitly provided port
        2. SERIAL_PORT environment variable
        3. Auto-detection
        
        Returns:
            Optional[str]: Path to serial port, or None if not found.
        """
        # 1. Explicit port
        if self._serial_port_path:
            if os.path.exists(self._serial_port_path):
                return self._serial_port_path
            print(f"[STS3215] WARNING: Specified port {self._serial_port_path} does not exist.")
        
        # 2. Environment variable
        env_port = os.environ.get("SERIAL_PORT")
        if env_port and os.path.exists(env_port):
            print(f"[STS3215] Using serial port from SERIAL_PORT env var: {env_port}")
            return env_port
        
        # 3. Auto-detect
        return self._auto_detect_serial_port()
    
    def _auto_detect_serial_port(self) -> Optional[str]:
        """
        Auto-detect the serial port with connected STS3215 servos.
        
        Returns:
            Optional[str]: Detected port path, or None if not found.
        """
        # USB serial patterns to try
        patterns = [
            "/dev/serial/by-id/usb-*",
            "/dev/ttyUSB*",
            "/dev/ttyACM*",
        ]
        
        candidates = []
        seen = set()
        
        for pattern in patterns:
            for path in sorted(glob.glob(pattern)):
                try:
                    realpath = os.path.realpath(path)
                    if realpath in seen:
                        continue
                    seen.add(realpath)
                    candidates.append(path)
                except OSError:
                    continue
        
        if not candidates:
            print("[STS3215] No candidate serial devices found.")
            return None
        
        # Probe each candidate
        responsive = []
        for path in candidates:
            if self._probe_serial_port(path):
                responsive.append(path)
        
        if len(responsive) == 1:
            print(f"[STS3215] Auto-detected servo serial port: {responsive[0]}")
            return responsive[0]
        elif len(responsive) > 1:
            print(f"[STS3215] WARNING: Multiple responsive ports found: {responsive}")
            return responsive[0]
        
        print("[STS3215] No responsive serial port found.")
        return None
    
    def _probe_serial_port(self, path: str) -> bool:
        """
        Probe a serial port for connected servos.
        
        Args:
            path: Serial port path to probe.
        
        Returns:
            bool: True if servos respond on this port.
        """
        # Try a few servo IDs
        probe_ids = self._servo_ids[:4]  # First 4 servos
        if self._gripper_servo_id:
            probe_ids.append(self._gripper_servo_id)
        
        try:
            with serial.Serial(path, self._baud_rate, timeout=0.1) as test_ser:
                time.sleep(0.05)
                for _ in range(2):
                    for servo_id in probe_ids:
                        if protocol.ping(test_ser, servo_id):
                            return True
                return False
        except Exception as e:
            print(f"[STS3215] Probe skipped {path}: {e}")
            return False

