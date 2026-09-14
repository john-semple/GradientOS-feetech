"""
part_a_speed_calibration.py — Sprint 07 Part A

Speed-unit calibration for the STS3215.

Measures the speed register LSB unit (documented ~0.732 rpm/LSB — UNVERIFIED)
by commanding a known rotation at various speed caps and timing completion.

Protocol:
  1. Read current position (should be ~4016 resting).
  2. For each speed cap in {10, 30, 60, 100}:
     a. Set accel=10, speed=cap.
     b. Seed goal to current position.
     c. Command a downward move of ~112 counts (~9.84°).
     d. Poll position at 100 Hz, detect motion completion (moving flag clears).
     e. Compute achieved velocity from the plateau of the trace.
  3. Fit achieved velocity (deg/s) vs cap value → rpm/LSB conversion.
  4. Sweep down from cap=10 to find the motion floor (stall threshold).

Safety:
  - Downward-only moves from ~4016 (toward lower counts).
  - Move size = 112 counts (~10°), well within range.
  - accel=10 (gentle), moderate speed caps.
  - Goal-seed-then-verify recipe before every move.
  - PSU current should be monitored by the operator.

Usage:
  python part_a_speed_calibration.py [--sid 10] [--port /dev/serial/ch340]

Output:
  - Console: per-cap timing + velocity table, fit result, floor estimate
  - CSV: traces saved to feetech-project/data/part_a_traces/
  - Summary: feetech-project/data/part_a_summary.csv
"""

import argparse
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bench_utils import (
    open_serial, safe_setup, seed_goal, assert_safe_target,
    read_pos, read_moving, read_status, capture_telemetry, save_trace,
    deg, rpm_per_lsb,
    REG_TARGET_SPEED, REG_TARGET_ACCEL, REG_TARGET_POSITION,
    REG_PRESENT_POSITION, REG_PRESENT_SPEED,
)
from gradient_os.arm_controller.backends.sts3215 import protocol as P

# ── Config ───────────────────────────────────────────────────────────────────

SERVO_ID = 10          # J1 Base — default bench servo
MOVE_COUNTS = 112      # ~9.84° downward
ACCEL = 10             # gentle accel (safe-move recipe)
SPEED_CAPS = [10, 30, 60, 100]
FLOOR_SEARCH = [10, 8, 6, 5, 4, 3, 2, 1]
CAPTURE_DURATION = 3.0  # seconds per cap run
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "part_a_traces")
SUMMARY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "part_a_summary.csv")


def measure_cap(ser, sid, cap, move_counts):
    """
    Run a single speed-cap measurement.
    Returns dict with cap, start_pos, end_pos, duration_s, achieved_deg_s, trace.
    """
    start_pos = read_pos(ser, sid)
    if start_pos is None:
        raise RuntimeError(f"Cannot read position for servo {sid}")

    target = start_pos - move_counts  # downward (toward lower counts)
    assert_safe_target(target)

    print(f"\n  Cap={cap:>4}  start={start_pos}  target={target}  "
          f"({deg(-move_counts):.2f}°)")

    # Safe recipe: set accel + speed, seed goal, verify
    safe_setup(ser, sid, accel=ACCEL, speed=cap)
    seed_goal(ser, sid, start_pos)

    # Command the move
    t0 = time.perf_counter()
    P.write_register_word(ser, sid, REG_TARGET_POSITION, target)

    # Capture telemetry for the whole move
    trace = capture_telemetry(ser, sid, duration_s=CAPTURE_DURATION)

    # Find end position
    end_pos = read_pos(ser, sid)
    duration_s = time.perf_counter() - t0

    # Compute achieved velocity from the plateau
    # Filter to samples where moving == 1 and speed is non-zero
    moving_speeds = [s["speed"] for t, s in trace if s["moving"] == 1 and s["speed"] != 0]
    if moving_speeds:
        avg_speed_raw = sum(moving_speeds) / len(moving_speeds)
        # Speed register is in the same unit as the cap — but this is the
        # PRESENT speed (0x3A), which reports actual velocity.
        # We want achieved deg/s: if we knew the LSB unit we wouldn't need this.
        # So we measure time-to-complete instead.
        pass

    # Time-to-complete: find when moving flag first clears after t0
    completion_t = None
    for t, s in trace:
        if s["moving"] == 0 and t > 0.05:
            completion_t = t
            break

    actual_move = end_pos - start_pos  # negative (downward)
    if completion_t and completion_t > 0.1:
        achieved_deg_s = abs(deg(actual_move)) / completion_t
    else:
        # Fallback: use total capture duration
        achieved_deg_s = abs(deg(actual_move)) / CAPTURE_DURATION

    print(f"    End={end_pos}  moved={actual_move} ({deg(actual_move):.2f}°)  "
          f"t_complete={completion_t:.3f}s  v={achieved_deg_s:.1f}°/s")

    return {
        "cap": cap,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "actual_move": actual_move,
        "duration_s": duration_s,
        "completion_t": completion_t,
        "achieved_deg_s": achieved_deg_s,
        "trace": trace,
    }


def find_floor(ser, sid, move_counts):
    """
    Sweep speed cap downward until motion is obviously slower than expected
    or stalls.  Returns the floor cap value.
    """
    print("\n  --- Floor sweep ---")
    prev_achieved = None
    floor_cap = None

    for cap in FLOOR_SEARCH:
        result = measure_cap(ser, sid, cap, move_counts)

        # If the servo barely moved (or didn't move), that's the floor
        if abs(result["actual_move"]) < move_counts * 0.5:
            floor_cap = cap
            print(f"    *** Floor detected at cap={cap} "
                  f"(only moved {result['actual_move']} counts)")
            break

        if prev_achieved is not None:
            # If achieved velocity didn't scale linearly (much slower than expected),
            # we're below the usable floor
            expected_ratio = cap / prev_cap
            actual_ratio = result["achieved_deg_s"] / prev_achieved
            if actual_ratio < expected_ratio * 0.5:
                floor_cap = cap
                print(f"    *** Nonlinear drop at cap={cap} "
                      f"(expected ~{expected_ratio:.2f}x, got {actual_ratio:.2f}x)")
                break

        prev_achieved = result["achieved_deg_s"]
        prev_cap = cap
        time.sleep(0.5)

    if floor_cap is None:
        floor_cap = 1
        print(f"    Floor not found above cap=1; setting floor=1")

    return floor_cap


def main():
    parser = argparse.ArgumentParser(description="Sprint 07 Part A: Speed calibration")
    parser.add_argument("--sid", type=int, default=SERVO_ID, help="Servo ID (default: 10)")
    parser.add_argument("--port", type=str, default="/dev/serial/ch340", help="Serial port")
    args = parser.parse_args()

    sid = args.sid
    print(f"=== Sprint 07 Part A — Speed-unit calibration ===")
    print(f"  Servo ID: {sid}")
    print(f"  Move: -{MOVE_COUNTS} counts ({deg(-MOVE_COUNTS):.2f}° downward)")
    print(f"  Accel: {ACCEL}")
    print(f"  Speed caps: {SPEED_CAPS}")

    ser = open_serial(args.port)
    time.sleep(0.1)

    # Read initial position
    start = read_pos(ser, sid)
    print(f"  Initial position: {start} ({deg(start):.1f}°)")
    if start is None:
        print("ERROR: Cannot read servo position. Check connection.")
        ser.close()
        return

    results = []
    os.makedirs(DATA_DIR, exist_ok=True)

    for cap in SPEED_CAPS:
        result = measure_cap(ser, sid, cap, MOVE_COUNTS)
        results.append(result)

        # Save trace
        trace_file = os.path.join(DATA_DIR, f"cap_{cap}.csv")
        save_trace(trace_file, result["trace"])

        # Move back up for the next run
        back_target = start
        assert_safe_target(back_target)
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, back_target)
        time.sleep(2.0)

        # Verify we're back
        current = read_pos(ser, sid)
        print(f"    Returned to {current} (drift: {current - start})")
        time.sleep(0.5)

    # ── Floor sweep ──────────────────────────────────────────────────────────
    floor_cap = find_floor(ser, sid, MOVE_COUNTS)

    # Return to start
    safe_setup(ser, sid, accel=ACCEL, speed=500)
    seed_goal(ser, sid, read_pos(ser, sid))
    P.write_register_word(ser, sid, REG_TARGET_POSITION, start)
    time.sleep(2.0)

    # ── Compute calibration ──────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("=== Part A Results ===")
    print(f"{'Cap':>6}  {'Achieved °/s':>12}  {'rpm/LSB':>10}  {'t_complete':>10}")
    print("-" * 50)

    summary_rows = []
    for r in results:
        rlsb = rpm_per_lsb(r["achieved_deg_s"], r["cap"])
        tc = r["completion_t"] if r["completion_t"] else 0
        print(f"{r['cap']:>6}  {r['achieved_deg_s']:>12.1f}  {rlsb:>10.4f}  {tc:>10.3f}")
        summary_rows.append({
            "cap": r["cap"],
            "achieved_deg_s": r["achieved_deg_s"],
            "rpm_per_lsb": rlsb,
            "completion_t": tc,
        })

    # Average rpm/LSB (excluding outliers)
    rpm_lsbs = [rpm_per_lsb(r["achieved_deg_s"], r["cap"]) for r in results if r["cap"] >= 10]
    avg_rpm_lsb = sum(rpm_lsbs) / len(rpm_lsbs) if rpm_lsbs else 0

    print(f"\n  Average rpm/LSB: {avg_rpm_lsb:.4f}  (documented: 0.732)")
    print(f"  Floor cap: {floor_cap}")

    if abs(avg_rpm_lsb - 0.732) / 0.732 < 0.10:
        print(f"  VERDICT: Confirms 0.732 rpm/LSB (within 10%)")
    elif avg_rpm_lsb > 0:
        print(f"  VERDICT: Refutes 0.732 rpm/LSB — measured {avg_rpm_lsb:.4f}")
    else:
        print(f"  VERDICT: Could not calibrate — check data")

    # Save summary CSV
    summary_file = os.path.join(os.path.dirname(__file__), "..", "data", "part_a_summary.csv")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)
    import csv
    with open(summary_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cap", "achieved_deg_s", "rpm_per_lsb", "completion_t_s"])
        for row in summary_rows:
            w.writerow([row["cap"], f"{row['achieved_deg_s']:.2f}",
                        f"{row['rpm_per_lsb']:.4f}", f"{row['completion_t']:.3f}"])
        w.writerow([])
        w.writerow(["avg_rpm_per_lsb", f"{avg_rpm_lsb:.4f}"])
        w.writerow(["documented_rpm_per_lsb", "0.732"])
        w.writerow(["floor_cap", floor_cap])
    print(f"\n  Summary saved: {summary_file}")

    ser.close()
    print("\nPart A complete.")


if __name__ == "__main__":
    main()