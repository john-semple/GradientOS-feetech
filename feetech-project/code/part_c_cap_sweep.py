"""
part_c_cap_sweep.py — Sprint 07 Part C

Cap sweep on streamed motion: quantify the saturation regime.

Streams a known linear move at 100 Hz, sweeping the speed cap to classify
the velocity behavior regime:

  - stop-go: velocity zero-crossings at stream rate (start/stop per command)
  - continuous cruise: velocity stays nonzero, servo never decelerates
  - lag: position error grows (servo can't keep up with stream)

Protocol:
  1. Stream a linear downward move at 100 Hz (goal updated every 10ms).
  2. Sweep cap: {4095, 500, 100, 30, 10, floor} (floor from Part A).
  3. Log present speed (0x3A) at max feasible read rate.
  4. Classify per-cap regime from velocity traces.

Safety:
  - Downward-only moves from ~4016.
  - Total move bounded (~400 counts, ~35°).
  - accel=10 on all runs.
  - PSU current monitored by operator.

Usage:
  python part_c_cap_sweep.py [--sid 10] [--port /dev/serial/ch340] [--floor 3]
  python part_c_cap_sweep.py --floor 3   # pass floor from Part A

Output:
  - Console: per-cap regime classification
  - CSV: traces saved to feetech-project/data/part_c_traces/
  - Summary: feetech-project/data/part_c_summary.csv
"""

import argparse
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bench_utils import (
    open_serial, safe_setup, seed_goal, assert_safe_target,
    read_pos, read_moving, read_status, save_trace,
    read_telemetry_sample, deg,
    REG_TARGET_ACCEL, REG_TARGET_POSITION, REG_TARGET_SPEED,
    REG_PRESENT_POSITION, REG_PRESENT_SPEED,
)
from gradient_os.arm_controller.backends.sts3215 import protocol as P

# ── Config ───────────────────────────────────────────────────────────────────

SERVO_ID = 10
ACCEL = 10
STREAM_RATE_HZ = 100
STREAM_INTERVAL = 1.0 / STREAM_RATE_HZ
TOTAL_MOVE_COUNTS = 400  # ~35° downward
CAPTURE_DURATION = 5.0   # seconds per cap run
DEFAULT_CAPS = [4095, 500, 200, 100, 50]
DEFAULT_FLOOR = 50  # measured in Part A: caps below 50 all run at the same ~50-LSB floor

# Measured in Part A: 0x3A decoded == commanded cap during cruise; LSB ≈ 0.088 deg/s;
# speed quantizes in steps of 50. Regime thresholds calibrated to that scale.
SPEED_FLOOR = 50

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "part_c_traces")
SUMMARY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "part_c_summary.csv")


# ── Streamed move runner ────────────────────────────────────────────────────

def run_streamed_move(ser, sid, cap, total_move=TOTAL_MOVE_COUNTS):
    """
    Stream a linear downward move at 100 Hz with a given speed cap.
    Returns dict with trace, start_pos, end_pos, final_pos_error.
    """
    start_pos = read_pos(ser, sid)
    if start_pos is None:
        raise RuntimeError("Cannot read position")

    final_target = start_pos - total_move
    assert_safe_target(final_target)

    print(f"\n  Cap={cap:>4}  start={start_pos}  final_target={final_target}  "
          f"({deg(-total_move):.1f}°)")

    # Safe recipe
    safe_setup(ser, sid, accel=ACCEL, speed=cap)
    seed_goal(ser, sid, start_pos)

    # Linear interpolation: goal steps down evenly across the stream duration.
    # DOWNWARD move: step_size is NEGATIVE (toward lower counts).
    stream_duration = 3.0
    n_steps = int(stream_duration * STREAM_RATE_HZ)
    step_size = -total_move / n_steps  # counts per step (negative = downward)

    # Start streaming
    t0 = time.perf_counter()
    trace = []
    step_idx = 0

    while True:
        t = time.perf_counter() - t0
        if t >= CAPTURE_DURATION:
            break

        # Read telemetry
        sample = read_telemetry_sample(ser, sid)
        if sample is not None:
            trace.append((t, sample))

        # Update goal at stream rate
        if t < stream_duration:
            expected_t = step_idx * STREAM_INTERVAL
            if t >= expected_t:
                goal = int(start_pos + step_size * step_idx)
                goal = max(goal, final_target)
                # Per-goal guardrail: every streamed goal must stay inside the
                # safe band [final_target, start_pos]. Never command above start.
                if goal > start_pos or goal < final_target:
                    print(f"    !! STREAM GOAL OUT OF BAND: {goal} "
                          f"(band {final_target}..{start_pos}) — clamping")
                    goal = max(final_target, min(start_pos, goal))
                P.write_register_word(ser, sid, REG_TARGET_POSITION, goal)
                step_idx += 1
        else:
            # Ensure final target is set
            if step_idx <= n_steps:
                P.write_register_word(ser, sid, REG_TARGET_POSITION, final_target)
                step_idx = n_steps + 1

        # Pace the loop (try to hit ~100 Hz for goal writes, but read
        # telemetry as fast as possible between writes)
        # Actually — read_telemetry_sample already takes ~1-2ms per call,
        # so the loop naturally paces. No extra sleep needed.

    end_pos = read_pos(ser, sid)
    pos_error = end_pos - final_target  # positive = undershoot

    print(f"    End={end_pos}  error={pos_error} ({deg(pos_error):.1f}°)  "
          f"trace_samples={len(trace)}")

    return {
        "cap": cap,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "final_target": final_target,
        "pos_error": pos_error,
        "trace": trace,
    }


# ── Regime classification ────────────────────────────────────────────────────

def classify_regime(result):
    """
    Classify per-cap velocity regime from the trace.

    stop-go: frequent zero-crossings in speed (velocity drops to 0 between commands)
    continuous cruise: speed stays nonzero throughout the move
    lag: position error is large (servo can't keep up)

    Returns (regime, description).
    """
    trace = result["trace"]
    pos_error = result["pos_error"]
    cap = result["cap"]

    if len(trace) < 10:
        return "UNKNOWN", "Insufficient samples"

    # Filter to moving samples
    moving_samples = [(t, s) for t, s in trace if s["moving"] == 1]
    if len(moving_samples) < 5:
        return "UNKNOWN", f"Only {len(moving_samples)} moving samples"

    speeds = [s["speed_mag"] for t, s in moving_samples]

    # Zero-crossings: speed drops below the measured quantization floor.
    # (0x3A steps in 50s — anything below SPEED_FLOOR reads as a near-stop.)
    threshold = SPEED_FLOOR
    zero_crossings = 0
    prev_above = speeds[0] >= threshold if speeds else False
    for s in speeds[1:]:
        curr_above = s >= threshold
        if curr_above != prev_above:
            zero_crossings += 1
            prev_above = curr_above

    # Average speed
    avg_speed = sum(speeds) / len(speeds) if speeds else 0
    min_speed = min(speeds) if speeds else 0
    max_speed = max(speeds) if speeds else 0

    # Position error threshold: if undershoot > 15% of total move, it's lag
    lag_threshold = TOTAL_MOVE_COUNTS * 0.15

    # Classification
    if pos_error > lag_threshold:
        return "LAG", (f"Large position error: {pos_error} counts "
                       f"({deg(pos_error):.1f}°, {pos_error/TOTAL_MOVE_COUNTS*100:.0f}% undershoot). "
                       f"Servo can't keep up at cap={cap}.")

    # Zero-crossings per second
    duration = trace[-1][0] - trace[0][0] if len(trace) > 1 else 1
    crossings_per_s = zero_crossings / duration if duration > 0 else 0

    if crossings_per_s > 10:
        return "STOP-GO", (f"Velocity zero-crossings: {zero_crossings} "
                           f"({crossings_per_s:.0f}/s). Stop-go at stream rate. "
                           f"Avg speed={avg_speed:.0f}, min={min_speed:.0f}.")

    if min_speed > avg_speed * 0.3:
        return "CRUISE", (f"Continuous cruise: avg={avg_speed:.0f}, "
                          f"min={min_speed:.0f} ({min_speed/avg_speed*100:.0f}% of avg). "
                          f"Zero-crossings={zero_crossings}.")

    return "STOP-GO", (f"Intermittent: avg={avg_speed:.0f}, min={min_speed:.0f}, "
                       f"zero-crossings={zero_crossings}. Likely stop-go.")


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sprint 07 Part C: Cap sweep on streamed motion")
    parser.add_argument("--sid", type=int, default=SERVO_ID, help="Servo ID")
    parser.add_argument("--port", type=str, default="/dev/serial/ch340", help="Serial port")
    parser.add_argument("--floor", type=int, default=DEFAULT_FLOOR,
                        help="Floor cap from Part A (default: 3)")
    args = parser.parse_args()

    sid = args.sid
    caps = DEFAULT_CAPS + [args.floor]
    print(f"=== Sprint 07 Part C — Cap sweep on streamed motion ===")
    print(f"  Servo ID: {sid}")
    print(f"  Stream rate: {STREAM_RATE_HZ} Hz")
    print(f"  Total move: {TOTAL_MOVE_COUNTS} counts ({deg(-TOTAL_MOVE_COUNTS):.1f}°)")
    print(f"  Accel: {ACCEL}")
    print(f"  Caps: {caps}")

    ser = open_serial(args.port)
    time.sleep(0.1)

    # Read initial position
    start = read_pos(ser, sid)
    print(f"  Initial position: {start}")
    if start is None:
        print("ERROR: Cannot read servo position. Check connection.")
        ser.close()
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    results = []

    for cap in caps:
        result = run_streamed_move(ser, sid, cap)
        results.append(result)

        # Save trace
        trace_file = os.path.join(DATA_DIR, f"cap_{cap}.csv")
        save_trace(trace_file, result["trace"])

        # Return to start
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, start)
        time.sleep(3.0)
        current = read_pos(ser, sid)
        print(f"    Returned to {current} (drift: {current - start})")
        time.sleep(0.5)

    # ── Classification ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("=== Part C Results ===")
    print(f"{'Cap':>6}  {'Regime':>10}  {'Pos Error':>10}  {'Description'}")
    print("-" * 70)

    summary_rows = []
    cruise_transition = None
    lag_floor = None

    for i, r in enumerate(results):
        regime, desc = classify_regime(r)
        print(f"{r['cap']:>6}  {regime:>10}  {r['pos_error']:>10}  {desc}")
        summary_rows.append({
            "cap": r["cap"],
            "regime": regime,
            "pos_error": r["pos_error"],
            "description": desc,
        })

        # Track transitions
        if regime == "CRUISE" and cruise_transition is None:
            cruise_transition = r["cap"]
        if regime == "LAG" and lag_floor is None:
            lag_floor = r["cap"]

    # Summary
    print(f"\n  Cruise transition cap: {cruise_transition}")
    print(f"  Lag floor cap: {lag_floor}")

    # Save summary
    import csv
    os.makedirs(os.path.dirname(SUMMARY_FILE), exist_ok=True)
    with open(SUMMARY_FILE, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cap", "regime", "pos_error", "description"])
        for row in summary_rows:
            w.writerow([row["cap"], row["regime"], row["pos_error"], row["description"]])
        w.writerow([])
        w.writerow(["cruise_transition_cap", cruise_transition or ""])
        w.writerow(["lag_floor_cap", lag_floor or ""])
    print(f"\n  Summary saved: {SUMMARY_FILE}")

    ser.close()
    print("\nPart C complete.")


if __name__ == "__main__":
    main()