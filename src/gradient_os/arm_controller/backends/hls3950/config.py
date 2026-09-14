# backends/hls3950/config.py
#
# Feetech HLS3950 servo-specific configuration constants.
# These values are specific to the Feetech HLS3950 servo (FT-SCS protocol).
#
# The HLS3950 uses the same FT-SCS frame format and instruction set as the
# STS3215, but the register map has important differences:
#   - 0x2C is "Target Current" (not PWM open-loop speed as on STS)
#   - 0x22 is "Current Loop Kp" (not Holding Torque as on STS)
#   - 0x23 is "Current Loop Ki" (not Protection Time as on STS)
#   - 0x07 is "Sub ID" (secondary bus ID, write-only)
#   - 0x21 Operating Mode 2 = "constant current" (not PWM as on STS)
#   - 0x28 Torque Switch does NOT accept 128 for calibration (use 0x0B instruction)
#   - 0x42 Moving Flag and 0x43 Target Position readback are available
#
# This module contains:
# - Protocol constants (headers, instruction codes, register addresses)
# - Communication parameters (baud rate, timeouts)
# - Default tuning values (PID gains, acceleration scaling)
# - Telemetry block definitions and parsers
#
# Robot-specific configuration (joint limits, servo IDs, etc.) should be
# defined elsewhere and passed to the HLS3950Backend during initialization.

import math

# =============================================================================
# Serial Communication
# =============================================================================

# Default baud rate for HLS3950 servo communication (same as STS3215)
DEFAULT_BAUD_RATE = 1000000

# Default serial read timeout in seconds
SERIAL_READ_TIMEOUT = 0.05

# =============================================================================
# FT-SCS Protocol Constants
# =============================================================================

# Packet header bytes (all FT-SCS packets start with 0xFF 0xFF)
SERVO_HEADER = 0xFF

# Broadcast ID for sync commands (affects all servos on the bus)
SERVO_BROADCAST_ID = 0xFE

# -----------------------------------------------------------------------------
# Instruction Codes (same as STS3215 — both use FT-SCS)
# -----------------------------------------------------------------------------

SERVO_INSTRUCTION_PING = 0x01           # Check if servo is present
SERVO_INSTRUCTION_READ = 0x02           # Read from register(s)
SERVO_INSTRUCTION_WRITE = 0x03          # Write to register(s)
SERVO_INSTRUCTION_RESET = 0x06          # Factory reset / parameter restore (preserves ID)
SERVO_INSTRUCTION_RESTART = 0x08        # Reboot servo
SERVO_INSTRUCTION_CALIBRATE_MIDDLE = 0x0B  # Set current position as center
SERVO_INSTRUCTION_SYNC_READ = 0x82      # Read multiple servos at once
SERVO_INSTRUCTION_SYNC_WRITE = 0x83     # Write multiple servos at once

# -----------------------------------------------------------------------------
# Register Addresses - EEPROM Area (values persist after power cycle)
# -----------------------------------------------------------------------------

SERVO_ADDR_MIN_ANGLE_LIMIT = 0x09       # Minimum angle limit (2 bytes)
SERVO_ADDR_MAX_ANGLE_LIMIT = 0x0B       # Maximum angle limit (2 bytes)
SERVO_ADDR_POS_KP = 0x15                # Position PID - Proportional gain
SERVO_ADDR_POS_KD = 0x16                # Position PID - Derivative gain
SERVO_ADDR_POS_KI = 0x17                # Position PID - Integral gain
SERVO_ADDR_POSITION_CORRECTION = 0x1F  # Hardware zero offset (calibration)
SERVO_ADDR_WRITE_LOCK = 0x37            # EEPROM write lock (0=unlocked, 1=locked)

# -----------------------------------------------------------------------------
# Register Addresses - RAM Area (values reset on power cycle)
# -----------------------------------------------------------------------------

SERVO_ADDR_TARGET_ACCELERATION = 0x29   # Target acceleration (1 byte)
SERVO_ADDR_TARGET_POSITION = 0x2A       # Target position (2 bytes)
# Note: 0x2C-0x2D is "Target Current" on HLS (was "Goal Time" on STS, semantics differ)
SERVO_ADDR_PRESENT_POSITION = 0x38      # Current position feedback (2 bytes)

# -----------------------------------------------------------------------------
# Sync Write Configuration (HLS-specific — different from STS3215)
# -----------------------------------------------------------------------------
# The STS3215 uses SYNC_WRITE starting at 0x29 with 7 bytes:
#   [Accel(1), Pos(2), Time(2), Speed(2)]
# On the HLS3950, register 0x2C is "Target Current" (not "Goal Time" as on STS).
# Writing 0 to 0x2C DISABLES THE MOTOR (zero current = zero torque).  The STS3215
# sync_write writes 0x0000 to bytes 4-5, which kills the HLS motor.
#
# FIX: HLS SYNC_WRITE starts at 0x2A (skip accel), 6 bytes:
#   [Pos(2), TargetCurrent(2), Speed(2)]
# Acceleration is set separately via an individual write before the sync_write.
# Target Current is set to SYNC_WRITE_DEFAULT_CURRENT (the torque limit) so the
# motor has torque to move.

SYNC_WRITE_START_ADDRESS = SERVO_ADDR_TARGET_POSITION  # 0x2A (not 0x29)

# Length of data block per servo: Pos(2) + Current(2) + Speed(2) = 6 bytes
SYNC_WRITE_DATA_LEN_PER_SERVO = 6

# Default target current for sync_write (use max torque, 0-1000 in 0.1% units).
# This is written to 0x2C on every sync_write so the motor has torque.
# The servo's torque limit (0x30) defaults to 980 on this servo.
SYNC_WRITE_DEFAULT_CURRENT = 980

# =============================================================================
# Motion Control Defaults
# =============================================================================

# Default servo speed if not specified (0-4095 scale)
DEFAULT_SERVO_SPEED = 500

# Default acceleration in deg/s² (converted to register value when written)
DEFAULT_SERVO_ACCELERATION_DEG_S2 = 500

# Scale factor for converting deg/s² to register value
# Register value = deg/s² / ACCELERATION_SCALE_FACTOR
# The servo register accepts 0-254, where 0 = max acceleration
ACCELERATION_SCALE_FACTOR = 100

# =============================================================================
# Profiled-Segment Defaults (same as STS3215 — HLS has the same trapezoidal profiler)
# =============================================================================

PROFILED_SEGMENT_DEFAULT_SPEED = 500
PROFILED_SEGMENT_DEFAULT_ACCEL = 10
PROFILED_SEGMENT_SPEED_MIN = 30
PROFILED_SEGMENT_SPEED_MAX = 2000

# =============================================================================
# Default PID Gains
# =============================================================================

# Reasonable starting values for Feetech HLS3950 servos.
# May need tuning for the specific arm geometry and load.
DEFAULT_KP = 50     # Proportional gain (0-254)
DEFAULT_KI = 1      # Integral gain (0-254)
DEFAULT_KD = 30     # Derivative gain (0-254)

# =============================================================================
# Servo Value Mapping (same as STS3215)
# =============================================================================

# HLS3950 uses a 12-bit position value (0-4095)
# Center position is typically 2048
# Full range is typically ±π radians (±180°) around center

SERVO_VALUE_MIN = 0
SERVO_VALUE_MAX = 4095
SERVO_VALUE_CENTER = 2048

# Default angle range in radians (assuming ±π from center)
DEFAULT_ANGLE_RANGE_RAD = (-math.pi, math.pi)

# =============================================================================
# Telemetry Register Addresses (same addresses as STS3215)
# =============================================================================

# Block 1: Position, Speed, Load/Duty, Voltage, Temperature (8 bytes @ 0x38)
TELEMETRY_BLOCK1_ADDRESS = 0x38
TELEMETRY_BLOCK1_LENGTH = 8

# Block 2: Status, Moving flag, reserved, reserved, Current (5 bytes @ 0x41)
# HLS adds 0x42 Moving Flag (BIT0=moving, BIT1=reached) — not on STS
TELEMETRY_BLOCK2_ADDRESS = 0x41
TELEMETRY_BLOCK2_LENGTH = 5

# Block 3: Unloading condition, LED alarm condition (2 bytes @ 0x13)
TELEMETRY_BLOCK3_ADDRESS = 0x13
TELEMETRY_BLOCK3_LENGTH = 2

# Current sensing scale factor: raw_value * CURRENT_SCALE_FACTOR = amps
CURRENT_SCALE_FACTOR = 0.0065

# Load bit mask: direction bit is bit 10 (0x400), magnitude is bits 0-9 (0x3FF)
LOAD_DIRECTION_BIT = 0x400
LOAD_MAGNITUDE_MASK = 0x3FF

# =============================================================================
# Error/Status Bit Masks (HLS-specific — different bit names than STS3215)
# =============================================================================
# HLS status byte (0x41) bit meanings:
#   BIT0 (1): voltage status
#   BIT1 (2): magnetic encoder status
#   BIT2 (4): temperature status
#   BIT3 (8): current status
#   BIT4 (16): reserved
#   BIT5 (32): load status
#   BIT6 (64): reserved
#   BIT7 (128): reserved

STATUS_BIT_INPUT_VOLTAGE = 0x01   # Voltage error
STATUS_BIT_ENCODER = 0x02          # Magnetic encoder error
STATUS_BIT_OVERHEATING = 0x04      # Temperature error
STATUS_BIT_CURRENT = 0x08          # Current error
STATUS_BIT_RESERVED_4 = 0x10       # Reserved
STATUS_BIT_LOAD = 0x20             # Load error
STATUS_BIT_RESERVED_6 = 0x40       # Reserved
STATUS_BIT_RESERVED_7 = 0x80       # Reserved

# Human-readable names for status bits
STATUS_BIT_NAMES = {
    STATUS_BIT_INPUT_VOLTAGE: "Input Voltage",
    STATUS_BIT_ENCODER: "Magnetic Encoder",
    STATUS_BIT_OVERHEATING: "Overheating",
    STATUS_BIT_CURRENT: "Current",
    STATUS_BIT_LOAD: "Load",
}


def names_for_status_bits(status_byte: int) -> list[str]:
    """
    Convert a status byte to a list of human-readable error names.

    Args:
        status_byte: The error/status byte from a servo response packet.

    Returns:
        list[str]: List of error names that are set in the status byte.
    """
    names = []
    for bit, name in STATUS_BIT_NAMES.items():
        if status_byte & bit:
            names.append(name)
    return names


# =============================================================================
# Telemetry Parsing
# =============================================================================

# HLS alarm/condition bit names (different from STS3215)
ALARM_BIT_NAMES = {
    0: "Voltage Protection",
    1: "Magnetic Encoder Protection",
    2: "Overheat Protection",
    3: "Overcurrent Protection",
    4: "Reserved",
    5: "Reserved",
    6: "Reserved",
    7: "Reserved",
}


def names_for_alarm_bits(alarm_byte: int) -> list[str]:
    """
    Convert an alarm byte to a list of human-readable alarm names.
    """
    return [ALARM_BIT_NAMES.get(i, f"b{i}") for i in range(8) if ((alarm_byte >> i) & 1) == 1]


def bits_to_string(byte_val: int) -> str:
    """Convert a byte to a comma-separated string of set bit names."""
    bits = [f"b{i}" for i in range(8) if ((byte_val >> i) & 1) == 1]
    return ",".join(bits)


def parse_telemetry_block1(data: bytes) -> dict:
    """
    Parse telemetry block 1 (position, speed, load, voltage, temp).
    Same layout as STS3215 — the feedback registers are at the same addresses.
    """
    if len(data) != 8:
        return {}

    result = {}

    # Load/drive duty: direction in bit 10, magnitude in bits 0-9 (per-mille, 0-1023)
    load_raw = int.from_bytes(data[4:6], "little", signed=False)
    load_mag_pm = load_raw & LOAD_MAGNITUDE_MASK
    result["drive_duty_per_mille"] = load_mag_pm

    # Voltage: value / 10.0 = volts
    result["voltage_v"] = float(data[6]) / 10.0

    # Temperature: raw value in Celsius
    result["temp_c"] = int(data[7])

    return result


def parse_telemetry_block2(data: bytes) -> dict:
    """
    Parse telemetry block 2 (status, moving, current).

    HLS3950 adds a Moving Flag register at 0x42 (offset 1 in this block):
      BIT0: moving
      BIT1: reached target
    STS3215 does not have this — the block layout is otherwise the same.
    """
    if len(data) != 5:
        return {}

    result = {}

    # Status byte
    status_byte = int(data[0])
    result["status_byte"] = status_byte
    result["status_bits"] = bits_to_string(status_byte)
    result["status_names"] = names_for_alarm_bits(status_byte)

    # Moving flag (HLS-specific — offset 1 in the block, register 0x42)
    moving_byte = int(data[1])
    result["moving_flag"] = moving_byte
    result["is_moving"] = bool(moving_byte & 0x01)
    result["reached_target"] = bool(moving_byte & 0x02)

    # Current: signed 16-bit, scale to amps (offset 3-4, register 0x45)
    current_raw = int.from_bytes(data[3:5], "little", signed=True)
    result["current_a"] = current_raw * CURRENT_SCALE_FACTOR

    return result


def parse_telemetry_block3(data: bytes) -> dict:
    """
    Parse telemetry block 3 (unloading condition, LED alarm).
    Same layout as STS3215.
    """
    if len(data) != 2:
        return {}

    result = {}

    unload = int(data[0])
    led = int(data[1])

    result["unloading_condition"] = unload
    result["led_alarm_condition"] = led
    result["unloading_bits"] = bits_to_string(unload)
    result["led_alarm_bits"] = bits_to_string(led)
    result["unloading_names"] = names_for_alarm_bits(unload)
    result["led_alarm_names"] = names_for_alarm_bits(led)

    return result