"""
part_b_midmove_retarget.py — Sprint 07 Part B

THE decisive experiment: mid-move re-target fork test.

Determines which firmware behavior the STS3215 exhibits when the goal
position is rewritten mid-move:

  A: Re-target with velocity blend → continuous cruise. Verdict: GO
  B: Re-plan from rest (v=0 re-plan) → velocity sawtooth. Verdict: CONDITIONAL
  C: Queued completion (finishes current plan first) → NO-GO for streaming

Protocol (from diagnosis §9.4):
  1. Long move: 4016 → 3600 (cap 300, accel 10).
  2. While cruising (0x3A shows nonzero velocity), rewrite goal to 3400.
  3. Log 0x38 (pos), 0x3A (speed), moving flag (0x42), status (0x41) at ≥100 Hz.
  4. Classify A/B/C from the velocity trace.
  5. Repeat 3× for consistency.

Optional edge probes (if A or B confirmed):
  - High-rate re-target at 100 Hz with cap ≈ stream velocity
  - Direction reversal mid-move (rewrite goal behind current position)

Safety:
  - Downward-only moves from ~4016 (toward lower counts).
  - Move targets within safe range (100 < target < 4090).
  - accel=10, speed=300 (moderate).
  - Goal-seed-then-verify recipe.
  - Direction reversal is the ONLY test that commands backward motion.
  - PSU current should be monitored by the operator.

Usage:
  python part_b_midmove_retarget.py [--sid 10] [--port /dev/serial/ch340]
  python part_b_midmove_retarget.py --edges    # also run edge probes

Output:
  - Console: per-trial classification + verdict
  - CSV: traces saved to feetech-project/data/part_b_traces/
  - Summary: feetech-project/data/part_b_summary.csv
"""

import argparse
import time
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bench_utils import (
    open_serial, safe_setup, seed_goal, assert_safe_target,
    read_pos, read_moving, read_status, capture_telemetry, save_trace,
    read_telemetry_sample, deg,
    REG_TARGET_ACCEL, REG_TARGET_POSITION, REG_TARGET_SPEED,
    REG_PRESENT_POSITION, REG_PRESENT_SPEED,
)
from gradient_os.arm_controller.backends.sts3215 import protocol as P

# ── Config ───────────────────────────────────────────────────────────────────

SERVO_ID = 10
ACCEL = 10
SPEED_CAP = 300
INITIAL_GOAL = 3600    # first target (long move from ~4016)
RETARGET_GOAL = 3400   # rewritten goal mid-move
N_TRIALS = 3
CAPTURE_DURATION = 4.0
RETARGET_DELAY = 0.8   # seconds after move start to rewrite goal (adjust if needed)

# Edge probe config
EDGE_RATE_HZ = 100
EDGE_DURATION = 3.0
EDGE_CAP = 100

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "part_b_traces")
SUMMARY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "part_b_summary.csv")


# ── Trial runner ────────────────────────────────────────────────────────────

def run_trial(ser, sid, trial_num):
    """
    Run one mid-move re-target trial.
    Returns dict with trace, retarget_t, classification hints.
    """
    start_pos = read_pos(ser, sid)
    if start_pos is None:
        raise RuntimeError("Cannot read position")

    print(f"\n  Trial {trial_num}: start={start_pos} → {INITIAL_GOAL} → retarget to {RETARGET_GOAL}")

    # Safety checks
    assert_safe_target(INITIAL_GOAL)
    assert_safe_target(RETARGET_GOAL)
    assert start_pos > INITIAL_GOAL, f"Start {start_pos} must be above {INITIAL_GOAL} (downward move)"

    # Safe recipe
    safe_setup(ser, sid, accel=ACCEL, speed=SPEED_CAP)
    seed_goal(ser, sid, start_pos)

    # Command initial move
    P.write_register_word(ser, sid, REG_TARGET_POSITION, INITIAL_GOAL)
    t0 = time.perf_counter()

    # Capture telemetry at max rate, rewrite goal mid-move
    trace = []
    retarget_t = None
    retarget_pos = None
    retarget_speed = None

    while True:
        t = time.perf_counter() - t0
        if t >= CAPTURE_DURATION:
            break

        sample = read_telemetry_sample(ser, sid)
        if sample is not None:
            trace.append((t, sample))

        # Rewrite goal at the scheduled delay
        if retarget_t is None and t >= RETARGET_DELAY:
            # Check we're actually moving (cruising)
            if sample and sample["moving"] == 1:
                retarget_t = t
                retarget_pos = sample["pos"]
                retarget_speed = sample["speed"]
                P.write_register_word(ser, sid, REG_TARGET_POSITION, RETARGET_GOAL)
                print(f"    Retarget at t={t:.3f}s  pos={retarget_pos}  speed={retarget_speed}")
            else:
                # Move finished too fast — extend delay check
                pass

    end_pos = read_pos(ser, sid)
    print(f"    End pos={end_pos}")

    return {
        "trial": trial_num,
        "start_pos": start_pos,
        "end_pos": end_pos,
        "retarget_t": retarget_t,
        "retarget_pos": retarget_pos,
        "retarget_speed": retarget_speed,
        "trace": trace,
    }


# ── Classification ───────────────────────────────────────────────────────────

def classify_trial(result):
    """
    Classify firmware behavior from the velocity trace around the re-target point.

    A: Velocity-continuous blend — speed stays nonzero across re-target,
       no dip to zero.
    B: Re-plan from rest — velocity dips toward zero at re-target, then
       ramps back up.
    C: Queued completion — servo reaches INITIAL_GOAL first (full stop),
       then moves to RETARGET_GOAL.

    Heuristic:
    - Find speed values in a window around retarget_t.
    - Check if speed hits zero at/near retarget_t.
    - Check if position reaches INITIAL_GOAL before heading to RETARGET_GOAL.
    """
    trace = result["trace"]
    retarget_t = result["retarget_t"]
    if retarget_t is None:
        return "UNKNOWN", "Re-target never triggered (move too fast?)"

    # Window: ±0.3s around retarget
    window = [(t, s) for t, s in trace if abs(t - retarget_t) < 0.5]
    if len(window) < 5:
        return "UNKNOWN", "Insufficient samples around re-target"

    # Speed around re-target
    speeds_around = [s["speed"] for t, s in window if abs(t - retarget_t) < 0.15]
    min_speed = min(abs(s) for s in speeds_around) if speeds_around else 0

    # Check if position reached INITIAL_GOAL (case C: full stop at old goal)
    positions_after = [s["pos"] for t, s in trace if t > retarget_t + 0.1]
    reached_initial_goal = any(
        abs(p - INITIAL_GOAL) < 20 for p in positions_after
    ) if positions_after else False

    # Check for velocity dip (case B)
    speeds_before = [abs(s["speed"]) for t, s in trace
                     if retarget_t - 0.2 < t < retarget_t]
    speeds_after = [abs(s["speed"]) for t, s in trace
                    if retarget_t < t < retarget_t + 0.2]

    avg_before = sum(speeds_before) / len(speeds_before) if speeds_before else 0
    avg_after = sum(speeds_after) / len(speeds_after) if speeds_after else 0

    # Classification logic
    if reached_initial_goal:
        return "C", (f"Servo reached initial goal {INITIAL_GOAL} before "
                     f"continuing to {RETARGET_GOAL}. Queued completion.")

    if min_speed < 5 and avg_before > 20:
        return "B", (f"Velocity dipped to ~{min_speed} at re-target "
                     f"(was ~{avg_before:.0f}, recovered to ~{avg_after:.0f}). "
                     f"Re-plan from rest.")

    if avg_after > 0.3 * avg_before:
        return "A", (f"Velocity continuous: ~{avg_before:.0f} → ~{avg_after:.0f} "
                     f"across re-target, min={min_speed:.0f}. Velocity blend.")

    return "B", (f"Velocity dropped: ~{avg_before:.0f} → ~{avg_after:.0f}, "
                 f"min={min_speed:.0f}. Likely re-plan from rest.")


# ── Edge probes ─────────────────────────────────────────────────────────────

def edge_high_rate_retarget(ser, sid):
    """
    Edge probe: re-target at 100 Hz with cap ≈ stream velocity.
    Does velocity stay continuous across many consecutive re-targets?
    """
    print(f"\n  --- Edge probe: high-rate re-target ({EDGE_RATE_HZ} Hz) ---")

    start_pos = read_pos(ser, sid)
    if start_pos is None:
        return None

    # Target a point ~600 counts down, stream goals toward it
    final_target = start_pos - 600
    assert_safe_target(final_target)

    safe_setup(ser, sid, accel=ACCEL, speed=EDGE_CAP)
    seed_goal(ser, sid, start_pos)

    # Start initial move
    P.write_register_word(ser, sid, REG_TARGET_POSITION, start_pos - 50)
    t0 = time.perf_counter()

    trace = []
    interval = 1.0 / EDGE_RATE_HZ

    while True:
        t = time.perf_counter() - t0
        if t >= EDGE_DURATION:
            break

        sample = read_telemetry_sample(ser, sid)
        if sample is not None:
            trace.append((t, sample))

        # Re-target toward final_target at 100 Hz
        current = sample["pos"] if sample else None
        if current is not None:
            # Keep goal ahead of current position by 200 counts
            new_goal = max(final_target, current - 200)
            P.write_register_word(ser, sid, REG_TARGET_POSITION, new_goal)

        time.sleep(interval)

    end_pos = read_pos(ser, sid)
    print(f"    Start={start_pos}  End={end_pos}  Target was {final_target}")

    # Check velocity continuity
    speeds = [abs(s["speed"]) for t, s in trace if s["moving"] == 1]
    if speeds:
        min_s = min(speeds)
        avg_s = sum(speeds) / len(speeds)
        zero_crossings = sum(1 for i in range(1, len(speeds))
                             if speeds[i] < 5 and speeds[i-1] >= 5)
        print(f"    Speed: avg={avg_s:.0f}  min={min_s:.0f}  zero-crossings={zero_crossings}")
        if min_s > avg_s * 0.3 and zero_crossings < 3:
            print(f"    → Velocity stays continuous at {EDGE_RATE_HZ} Hz re-target")
        else:
            print(f"    → Velocity discontinuous at {EDGE_RATE_HZ} Hz (stop-go detected)")

    return trace


def edge_direction_reversal(ser, sid):
    """
    Edge probe: direction reversal mid-move.
    Rewrite goal behind current position while cruising.

    ⚠️  THIS IS THE ONLY TEST THAT COMMANDS BACKWARD MOTION.
    The operator should have eyes on the servo and PSU.
    """
    print(f"\n  --- Edge probe: direction reversal mid-move ---")
    print("  ⚠️  WARNING: This test reverses direction mid-cruise.")
    print("  ⚠️  Watch the servo and PSU current. Ctrl+C to abort.")

    start_pos = read_pos(ser, sid)
    if start_pos is None:
        return None

    # Move down 300 counts, then reverse to 200 counts above current
    down_target = start_pos - 300
    reverse_target = start_pos + 200
    assert_safe_target(down_target)
    assert_safe_target(reverse_target)

    safe_setup(ser, sid, accel=ACCEL, speed=SPEED_CAP)
    seed_goal(ser, sid, start_pos)

    # Start downward move
    P.write_register_word(ser, sid, REG_TARGET_POSITION, down_target)
    t0 = time.perf_counter()

    trace = []
    reversal_t = None
    reversal_pos = None
    reversal_speed = None

    while True:
        t = time.perf_counter() - t0
        if t >= CAPTURE_DURATION:
            break

        sample = read_telemetry_sample(ser, sid)
        if sample is not None:
            trace.append((t, sample))

        # After ~1.0s cruising, reverse direction
        if reversal_t is None and t >= 1.0 and sample and sample["moving"] == 1:
            reversal_t = t
            reversal_pos = sample["pos"]
            reversal_speed = sample["speed"]
            P.write_register_word(ser, sid, REG_TARGET_POSITION, reverse_target)
            print(f"    Reversal at t={t:.3f}s  pos={reversal_pos}  speed={reversal_speed}")

    end_pos = read_pos(ser, sid)
    print(f"    End pos={end_pos}")

    return {
        "trace": trace,
        "reversal_t": reversal_t,
        "reversal_pos": reversal_pos,
        "reversal_speed": reversal_speed,
        "end_pos": end_pos,
    }


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sprint 07 Part B: Mid-move re-target test")
    parser.add_argument("--sid", type=int, default=SERVO_ID, help="Servo ID")
    parser.add_argument("--port", type=str, default="/dev/serial/ch340", help="Serial port")
    parser.add_argument("--edges", action="store_true", help="Also run edge probes")
    args = parser.parse_args()

    sid = args.sid
    print(f"=== Sprint 07 Part B — Mid-move re-target fork test ===")
    print(f"  Servo ID: {sid}")
    print(f"  Move: ~4016 → {INITIAL_GOAL} → retarget to {RETARGET_GOAL}")
    print(f"  Accel: {ACCEL}  Speed cap: {SPEED_CAP}")
    print(f"  Retarget delay: {RETARGET_DELAY}s")
    print(f"  Trials: {N_TRIALS}")

    ser = open_serial(args.port)
    time.sleep(0.1)

    # Verify initial position
    start = read_pos(ser, sid)
    print(f"  Initial position: {start}")
    if start is None:
        print("ERROR: Cannot read servo position. Check connection.")
        ser.close()
        return

    # Return-to-start position for between trials
    home_pos = start

    os.makedirs(DATA_DIR, exist_ok=True)
    trial_results = []

    for i in range(1, N_TRIALS + 1):
        result = run_trial(ser, sid, i)
        trial_results.append(result)

        # Save trace
        trace_file = os.path.join(DATA_DIR, f"trial_{i}.csv")
        save_trace(trace_file, result["trace"])

        # Return to start
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, home_pos)
        time.sleep(2.5)
        current = read_pos(ser, sid)
        print(f"    Returned to {current} (drift: {current - home_pos})")
        time.sleep(0.5)

    # ── Classification ────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("=== Part B Classification ===")

    classifications = []
    for r in trial_results:
        cls, reason = classify_trial(r)
        classifications.append(cls)
        print(f"\n  Trial {r['trial']}: → {cls}")
        print(f"    {reason}")

    # Consistency check
    unique = set(classifications)
    if len(unique) == 1:
        verdict = unique.pop()
        print(f"\n  *** Consistent across all {N_TRIALS} trials: {verdict} ***")
    else:
        verdict = "INCONSISTENT"
        print(f"\n  *** INCONSISTENT: {classifications} — re-run needed ***")

    # Verdict
    print(f"\n{'='*60}")
    print("=== Verdict ===")
    if verdict == "A":
        print("  GO — Velocity-continuous blend confirmed.")
        print("  Profile saturation streaming is viable.")
        print("  Implementation becomes a future sprint.")
    elif verdict == "B":
        print("  CONDITIONAL — Re-plan from rest.")
        print("  Streaming may work with cap ×2 and known velocity ripple.")
        print("  Quantify ripple amplitude from traces before deciding.")
    elif verdict == "C":
        print("  NO-GO — Queued completion (servo finishes current plan first).")
        print("  Streaming requires different hardware.")
        print("  Endpoint-paradigm path is PERMANENT for Feetech.")
    else:
        print(f"  {verdict} — cannot reach a verdict from the data.")

    # ── Edge probes ──────────────────────────────────────────────────────────
    if args.edges and verdict in ("A", "B"):
        print(f"\n{'='*60}")
        print("=== Edge probes ===")

        # Return to start
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, home_pos)
        time.sleep(2.5)

        # High-rate re-target
        trace_hr = edge_high_rate_retarget(ser, sid)
        if trace_hr:
            save_trace(os.path.join(DATA_DIR, "edge_high_rate.csv"), trace_hr)

        # Return to start
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, home_pos)
        time.sleep(2.5)

        # Direction reversal
        input("  Press Enter to run direction reversal probe (or Ctrl+C to skip)...")
        result_rev = edge_direction_reversal(ser, sid)
        if result_rev:
            save_trace(os.path.join(DATA_DIR, "edge_reversal.csv"), result_rev["trace"])

        # Return to start
        safe_setup(ser, sid, accel=ACCEL, speed=500)
        seed_goal(ser, sid, read_pos(ser, sid))
        P.write_register_word(ser, sid, REG_TARGET_POSITION, home_pos)
        time.sleep(2.5)

    # Save summary
    import csv
    summary_file = os.path.join(os.path.dirname(__file__), "..", "data", "part_b_summary.csv")
    os.makedirs(os.path.dirname(summary_file), exist_ok=True)
    with open(summary_file, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trial", "classification", "retarget_t", "retarget_pos",
                     "retarget_speed", "end_pos"])
        for i, r in enumerate(trial_results):
            w.writerow([
                r["trial"],
                classifications[i],
                f"{r['retarget_t']:.3f}" if r["retarget_t"] else "",
                r["retarget_pos"] if r["retarget_pos"] else "",
                r["retarget_speed"] if r["retarget_speed"] else "",
                r["end_pos"],
            ])
        w.writerow([])
        w.writerow(["verdict", verdict])
    print(f"\n  Summary saved: {summary_file}")

    ser.close()
    print("\nPart B complete.")


if __name__ == "__main__":
    main()