"""
bench_utils.py — Shared utilities for Sprint 07 bench experiments.

Provides:
  - Serial port setup
  - High-speed telemetry capture (single bulk read of 11 bytes from 0x38-0x42)
  - CSV trace writer
  - Safe-move recipe (seed goal, set accel/speed, verify readback)
  - Guardrails (range checks, downward-only moves from ~4016)

All bench scripts import from here to keep consistent telemetry parsing and
safety guardrails.
"""

import serial
import time
import csv
import os
from gradient_os.arm_controller.backends.sts3215 import protocol as P

# ── Register addresses ──────────────────────────────────────────────────────
REG_TARGET_ACCEL = 0x29       # 1 byte (0 = max accel)
REG_TARGET_POSITION = 0x2A    # 2 bytes (goal)
REG_TARGET_SPEED = 0x2E      # 2 bytes (speed cap, 0-4095)
REG_PRESENT_POSITION = 0x38   # 2 bytes (signed)
REG_PRESENT_SPEED = 0x3A     # 2 bytes (signed)
REG_PRESENT_LOAD = 0x3C      # 2 bytes
REG_PRESENT_VOLTAGE = 0x3E    # 1 byte
REG_PRESENT_TEMP = 0x3F      # 1 byte
REG_STATUS = 0x41             # 1 byte
REG_MOVING = 0x42             # 1 byte (0=stopped, 1=moving)

# Bulk read: 0x38 to 0x42 inclusive = 11 bytes
TELEMETRY_BULK_ADDR = 0x38
TELEMETRY_BULK_LEN = 11

# Position conversion
COUNTS_PER_REV = 4096
DEG_PER_COUNT = 360.0 / COUNTS_PER_REV

# Default serial port (match existing bench scripts)
DEFAULT_PORT = "/dev/serial/ch340"
DEFAULT_BAUD = 1000000


# ── Serial ──────────────────────────────────────────────────────────────────

def open_serial(port=DEFAULT_PORT, baud=DEFAULT_BAUD, timeout=0.05):
    ser = serial.Serial(port, baud, timeout=timeout)
    return ser


# ── Bulk register read ──────────────────────────────────────────────────────

def read_register_bulk(ser, sid, addr, length):
    """
    Read `length` bytes starting at `addr` using standard READ instruction.
    Returns a bytes object of length `length`, or None on failure.
    """
    if ser is None or not ser.is_open:
        return None

    cmd = bytearray(8)
    cmd[0] = 0xFF
    cmd[1] = 0xFF
    cmd[2] = sid
    cmd[3] = 4  # length
    cmd[4] = 0x02  # READ
    cmd[5] = addr
    cmd[6] = length
    cmd[7] = P.calculate_checksum(cmd[2:7])

    resp_len = length + 5  # header(2) + id(1) + len(1) + error(1) + data + checksum(1)
    try:
        ser.reset_input_buffer()
        ser.write(cmd)
        resp = ser.read(resp_len)
        if len(resp) < resp_len:
            return None
        if resp[0] != 0xFF or resp[1] != 0xFF or resp[2] != sid:
            return None
        if resp[4] != 0:  # error byte
            return None
        if resp[-1] != P.calculate_checksum(resp[2:-1]):
            return None
        return resp[5:5 + length]
    except Exception:
        return None


# ── Telemetry capture ───────────────────────────────────────────────────────

def read_telemetry_sample(ser, sid):
    """
    Single telemetry sample via one bulk read.
    Returns dict: {t, pos, speed, load, voltage, temp, status, moving}
    or None on read failure.
    """
    data = read_register_bulk(ser, sid, TELEMETRY_BULK_ADDR, TELEMETRY_BULK_LEN)
    if data is None or len(data) < TELEMETRY_BULK_LEN:
        return None

    pos = int.from_bytes(data[0:2], "little", signed=True)
    speed = int.from_bytes(data[2:4], "little", signed=True)
    load = int.from_bytes(data[4:6], "little", signed=False)
    voltage = data[6]
    temp = data[7]
    # data[8] = 0x40 (unknown/reserved)
    status = data[9]   # 0x41
    moving = data[10]  # 0x42

    return {
        "pos": pos,
        "speed": speed,
        "load": load,
        "voltage": voltage,
        "temp": temp,
        "status": status,
        "moving": moving,
    }


def capture_telemetry(ser, sid, duration_s=5.0, min_interval_s=0.0):
    """
    Capture telemetry samples as fast as possible (or at min_interval_s spacing)
    for duration_s seconds.  Returns list of (t, sample_dict) tuples where t
    is seconds since capture start (perf_counter relative).
    """
    trace = []
    t0 = time.perf_counter()
    while True:
        t = time.perf_counter() - t0
        if t >= duration_s:
            break
        sample = read_telemetry_sample(ser, sid)
        if sample is not None:
            trace.append((t, sample))
        if min_interval_s > 0:
            time.sleep(min_interval_s)
    return trace


# ── CSV trace writer ─────────────────────────────────────────────────────────

def save_trace(filename, trace):
    """
    Save a telemetry trace to CSV.
    `trace` is a list of (t, sample_dict) tuples.
    """
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "pos", "speed", "load", "voltage", "temp", "status", "moving"])
        for t, s in trace:
            w.writerow([
                f"{t:.6f}",
                s["pos"],
                s["speed"],
                s["load"],
                s["voltage"],
                s["temp"],
                s["status"],
                s["moving"],
            ])
    print(f"  Trace saved: {filename} ({len(trace)} samples)")


# ── Safe-move recipe ────────────────────────────────────────────────────────

def safe_setup(ser, sid, accel=10, speed=300):
    """Set acceleration and speed cap before any move."""
    P.write_register_byte(ser, sid, REG_TARGET_ACCEL, accel)
    time.sleep(0.01)
    P.write_register_word(ser, sid, REG_TARGET_SPEED, speed)
    time.sleep(0.01)


def seed_goal(ser, sid, pos=None):
    """
    Seed goal register to current position (or a given pos) and verify readback.
    Returns the seeded position, or raises AssertionError on readback mismatch.
    """
    if pos is None:
        pos = P.read_register_word(ser, sid, REG_PRESENT_POSITION)
        time.sleep(0.01)
        if pos is None:
            raise RuntimeError(f"Cannot read present position for servo {sid}")
    P.write_register_word(ser, sid, REG_TARGET_POSITION, pos)
    time.sleep(0.01)
    readback = P.read_register_word(ser, sid, REG_TARGET_POSITION)
    time.sleep(0.01)
    if readback is None or abs(readback - pos) > 3:
        raise AssertionError(
            f"Goal readback mismatch: wrote {pos}, read {readback} — STOP"
        )
    return pos


def assert_safe_target(target):
    """Guardrail: target must be within safe range, never near limits."""
    assert 100 < target < 4090, f"Unsafe target {target} — aborting"


def read_pos(ser, sid, tries=3):
    """Read present position with retries."""
    for _ in range(tries):
        v = P.read_register_word(ser, sid, REG_PRESENT_POSITION)
        time.sleep(0.005)
        if v is not None:
            return v
    return None


def read_speed(ser, sid, tries=3):
    """Read present speed (0x3A) with retries."""
    for _ in range(tries):
        v = P.read_register_word(ser, sid, REG_PRESENT_SPEED)
        time.sleep(0.005)
        if v is not None:
            return v
    return None


def read_moving(ser, sid, tries=3):
    """Read moving flag (0x42) with retries."""
    for _ in range(tries):
        v = P.read_register_byte(ser, sid, REG_MOVING)
        time.sleep(0.005)
        if v is not None:
            return v
    return None


def read_status(ser, sid, tries=3):
    """Read status byte (0x41) with retries."""
    for _ in range(tries):
        v = P.read_register_byte(ser, sid, REG_STATUS)
        time.sleep(0.005)
        if v is not None:
            return v
    return None


def wait_for_stop(ser, sid, timeout_s=5.0):
    """Block until moving flag clears or timeout."""
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < timeout_s:
        m = read_moving(ser, sid)
        if m is not None and m == 0:
            return True
        time.sleep(0.02)
    return False


# ── Convenience ──────────────────────────────────────────────────────────────

def deg(counts):
    """Convert raw counts to degrees."""
    return counts * DEG_PER_COUNT


def rpm_per_lsb(achieved_deg_s, cap_value):
    """Convert achieved deg/s at a given cap to rpm/LSB."""
    achieved_rpm = achieved_deg_s / 6.0
    return achieved_rpm / cap_value if cap_value > 0 else 0.0