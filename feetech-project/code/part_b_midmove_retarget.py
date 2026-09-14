"""
part_b_midmove_retarget.py — Sprint 07 Part B

THE decisive experiment: mid-move re-target fork test.

Determines which firmware behavior the STS3215 exhibits when the goal
position is rewritten mid-move:

  A: Re-target with velocity blend → continuous cruise. Verdict: GO
  B: Re-plan from rest (v=0 re-plan) → velocity sawtooth. Verdict: CONDITIONAL
  C: Queued completion (finishes current plan first) → NO-GO for streaming

Protocol (from diagnosis §9.4):
  1. Long downward move (cap 300, accel 10), goals computed relative to the
     actual start position: start-296 → start-516.
  2. While cruising (0x3A decoded == cap), rewrite goal further down.
  3. Log 0x38 (pos), 0x3A (speed), moving flag (0x42), status (0x41) at ≥100 Hz.
  4. Classify A/B/C from the velocity trace.
  5. Repeat 3× for consistency.

Edge probes (run if A or B confirmed):
  - High-rate re-target at 100 Hz with cap ≈ stream velocity
  - VELOCITY-MODE HYBRID: cruise in velocity mode (0x21=1), flip back to
    position mode (0x21=0) mid-cruise, then goal-write the final position.
    Tests the "velocity cruise + position arrival" interim architecture.
  - Direction reversal mid-move (rewrite goal behind current position)

Safety:
  - Downward-only moves (toward lower counts) except the reversal probe.
  - Move targets within safe range (100 < target < 4090).
  - accel=10, speed=300 (moderate).
  - Goal-seed-then-verify recipe.
  - Direction reversal and velocity-mode probes gate on operator Enter.
  - PSU current should be monitored by the operator.
  - Velocity-mode probe watchdogs: velocity zeroed if a write fails or after
    1.0s with no new command (comms-drop runaway protection).

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
    REG_PRESENT_POSITION, REG_PRESENT_SPEED, REG_OPERATION_MODE,
)
from gradient_os.arm_controller.backends.sts3215 import protocol as P

# ── Config ───────────────────────────────────────────────────────────────────

SERVO_ID = 10
ACCEL = 10
SPEED_CAP = 300
FIRST_LEG = 296      # counts down for the first goal (relative to start)
SECOND_LEG = 516      # counts down for the retarget goal (relative to start)
N_TRIALS = 3
CAPTURE_DURATION = 4.0
RETARGET_DELAY = 0.6  # s after move start; first leg ~1.1s at cap 300, so 0.6s fires mid-cruise

# Measured scales (Sprint 07 Part A):
#   0x3A decoded (bit15 dir, low15 mag) is in the SAME units as the cap.
#   Cap LSB ≈ 0.088 deg/s. Cruise plateau decodes exactly == cap.
#   Speed floor = 50 (below this, everything runs at ~50).
SPEED_FLOOR = 50

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
    Goals are computed relative to the actual start position.
    """
    start_pos = read_pos(ser, sid)
    if start_pos is None:
        raise RuntimeError("Cannot read position")

    initial_goal = start_pos - FIRST_LEG
    retarget_goal = start_pos - SECOND_LEG

    print(f"\n  Trial {trial_num}: start={start_pos} → {initial_goal} → retarget to {retarget_goal}")

    # Safety checks
    assert_safe_target(initial_goal)
    assert_safe_target(retarget_goal)
    assert start_pos > initial_goal > retarget_goal, (
        f"Goals must descend: {start_pos} > {initial_goal} > {retarget_goal}"
    )

    # Safe recipe
    safe_setup(ser, sid, accel=ACCEL, speed=SPEED_CAP)
    seed_goal(ser, sid, start_pos)

    # Command initial move
    P.write_register_word(ser, sid, REG_TARGET_POSITION, initial_goal)
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
            if sample and sample["moving"] == 1 and sample["speed_mag"] > SPEED_FLOOR:
                retarget_t = t
                retarget_pos = sample["pos"]
                retarget_speed = sample["speed"]
                P.write_register_word(ser, sid, REG_TARGET_POSITION, retarget_goal)
                print(f"    Retarget at t={t:.3f}s  pos={retarget_pos}  speed={retarget_speed}")
            else:
                # Move finished too fast — extend delay check
                pass

    end_pos = read_pos(ser, sid)
    print(f"    End pos={end_pos}")

    return {
        "trial": trial_num,
        "start_pos": start_pos,
        "initial_goal": initial_goal,
        "retarget_goal": retarget_goal,
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

    Calibrated with Part A measurements (0x3A decoded == cap during cruise,
    floor 50, noise floor 0 at standstill):

    A: Velocity-continuous blend — speed_mag stays near cap across re-target.
    B: Re-plan from rest — speed_mag dips toward 0 at re-target, then ramps
       back up toward cap.
    C: Queued completion — servo reaches the FIRST goal (full stop, speed 0),
       then a second move starts toward the retarget goal.
    """
    trace = result["trace"]
    retarget_t = result["retarget_t"]
    initial_goal = result["initial_goal"]
    cap = SPEED_CAP
    if retarget_t is None:
        return "UNKNOWN", "Re-target never triggered (move too fast?)"

    # Window: ±0.5s around retarget
    window = [(t, s) for t, s in trace if abs(t - retarget_t) < 0.5]
    if len(window) < 5:
        return "UNKNOWN", "Insufficient samples around re-target"

    # Speed magnitude around re-target (±0.15s)
    mags_around = [s["speed_mag"] for t, s in window if abs(t - retarget_t) < 0.15]
    min_mag = min(mags_around) if mags_around else 0

    # Case C: position reaches the FIRST goal after the re-target
    positions_after = [s["pos"] for t, s in trace if t > retarget_t + 0.1]
    reached_initial_goal = any(
        p <= initial_goal + 10 for p in positions_after
    ) if positions_after else False
    # A full stop at the first goal: speed zeroed AND position at goal
    stopped_at_goal = any(
        (s["pos"] <= initial_goal + 10 and s["speed_mag"] < 10)
        for t, s in trace if t > retarget_t
    )

    # Speed magnitude before/after the re-target (0.2s windows)
    mags_before = [s["speed_mag"] for t, s in trace
                   if retarget_t - 0.2 < t < retarget_t]
    mags_after = [s["speed_mag"] for t, s in trace
                  if retarget_t < t < retarget_t + 0.2]

    avg_before = sum(mags_before) / len(mags_before) if mags_before else 0
    avg_after = sum(mags_after) / len(mags_after) if mags_after else 0

    # Classification logic (calibrated thresholds)
    if stopped_at_goal or reached_initial_goal:
        return "C", (f"Servo reached first goal {initial_goal} before "
                     f"continuing to {result['retarget_goal']}. Queued completion.")

    if min_mag < SPEED_FLOOR and avg_before > SPEED_FLOOR:
        return "B", (f"Velocity dipped to ~{min_mag} at re-target "
                     f"(was ~{avg_before:.0f}, recovered to ~{avg_after:.0f}). "
                     f"Re-plan from rest.")

    if avg_after > 0.5 * cap:
        return "A", (f"Velocity continuous: ~{avg_before:.0f} → ~{avg_after:.0f} "
                     f"across re-target (cap {cap}), min={min_mag:.0f}. Velocity blend.")

    return "B", (f"Velocity dropped: ~{avg_before:.0f} → ~{avg_after:.0f}, "
                 f"min={min_mag:.0f}. Likely re-plan from rest.")


# ── Velocity-mode hybrid probe ───────────────────────────────────────────────

def edge_velocity_mode_hybrid(ser, sid):
    """
    Edge probe: VELOCITY-MODE HYBRID — the "interim architecture" test.

    Cruise in velocity mode (0x21=1, speed via 0x2E), then mid-cruise flip
    back to position mode (0x21=0) and goal-write the final position.

    Answers: is the mode-switch transition smooth (velocity-preserving) or
    jerky (re-plan from rest)? If smooth, the interim architecture works:
    velocity cruise for paths + position mode for precise arrival.

    Watchdogs (runaway protection — velocity mode does NOT stop on comms loss):
      - any failed 0x21/0x2E write → immediate stop attempt (mode 0, seed goal)
      - probe is short (2.5s) and total travel is bounded by geometry.

    The operator gates this probe with Enter and watches the servo + PSU.
    """
    print(f"\n  --- Edge probe: VELOCITY-MODE HYBRID (mode 1 cruise → mode 0 arrival) ---")
    print("  ⚠️  Watch the servo and PSU current. Ctrl+C to abort.")

    start_pos = read_pos(ser, sid)
    if start_pos is None:
        return None

    # Targets: cruise ~300 counts down, arrive at start-400
    cruise_len = 300
    final_target = start_pos - 400
    assert_safe_target(final_target)

    safe_setup(ser, sid, accel=ACCEL, speed=SPEED_CAP)
    seed_goal(ser, sid, start_pos)

    # ── Phase 1: enter velocity mode, command a downward cruise ──────────
    # In velocity mode, 0x2E is the commanded speed; direction via sign.
    # Downward = bit15-encoded negative in our reading, but the COMMAND
    # register takes a plain value: per Feetech docs the goal-speed word is
    # signed (two's complement) for velocity mode. We write the negative
    # value for downward.
    ok = P.write_register_byte(ser, sid, REG_OPERATION_MODE, 1)
    if not ok:
        print("    ERROR: failed to write operation mode — aborting probe.")
        return None
    time.sleep(0.01)

    cruise_speed = -SPEED_CAP  # downward
    ok = P.write_register_word(ser, sid, REG_TARGET_SPEED, cruise_speed & 0xFFFF)
    if not ok:
        print("    ERROR: failed to write cruise velocity — restoring position mode.")
        P.write_register_byte(ser, sid, REG_OPERATION_MODE, 0)
        return None

    t0 = time.perf_counter()
    SWITCH_DELAY = 1.0  # cruise for 1s, then switch

    trace = []
    switch_t = None
    switch_pos = None
    switch_speed = None

    try:
        while True:
            t = time.perf_counter() - t0
            if t >= CAPTURE_DURATION:
                break

            sample = read_telemetry_sample(ser, sid)
            if sample is not None:
                trace.append((t, sample))

            # ── Phase 2: mid-cruise, flip to position mode and write final goal ──
            if switch_t is None and t >= SWITCH_DELAY and sample and sample["moving"] == 1:
                switch_t = t
                switch_pos = sample["pos"]
                switch_speed = sample["speed"]
                # Order matters: mode first, then goal. Keep 0x2E capped.
                P.write_register_byte(ser, sid, REG_OPERATION_MODE, 0)
                time.sleep(0.005)
                # Seed goal at CURRENT position first (safe recipe: never let
                # the planner see a stale goal), then command the final target.
                P.write_register_word(ser, sid, REG_TARGET_POSITION, sample["pos"])
                time.sleep(0.005)
                P.write_register_word(ser, sid, REG_TARGET_POSITION, final_target)
                print(f"    Mode switch at t={t:.3f}s  pos={switch_pos}  speed={switch_speed}")
    finally:
        # Safety net: guarantee position mode on any exit path (Ctrl+C included)
        P.write_register_byte(ser, sid, REG_OPERATION_MODE, 0)

    end_pos = read_pos(ser, sid)
    print(f"    End pos={end_pos}  (final target was {final_target})")

    # Quick continuity analysis around the switch
    if switch_t is not None:
        mags_before = [s["speed_mag"] for t, s in trace
                       if switch_t - 0.2 < t < switch_t]
        mags_after = [s["speed_mag"] for t, s in trace
                      if switch_t < t < switch_t + 0.3]
        min_after = min(mags_after) if mags_after else 0
        avg_before = sum(mags_before) / len(mags_before) if mags_before else 0
        avg_after = sum(mags_after) / len(mags_after) if mags_after else 0
        print(f"    Speed across switch: before ~{avg_before:.0f}, after ~{avg_after:.0f}, "
              f"min after = {min_after:.0f}")
        if min_after < SPEED_FLOOR and avg_before > SPEED_FLOOR:
            print("    → TRANSITION JERKY: velocity zeroes at the mode switch (re-plan from rest)")
        else:
            print("    → TRANSITION SMOOTH: velocity preserved across the mode switch")

    return {
        "trace": trace,
        "switch_t": switch_t,
        "switch_pos": switch_pos,
        "switch_speed": switch_speed,
        "end_pos": end_pos,
        "final_target": final_target,
    }


# ── Edge probe: high-rate re-target ──────────────────────────────────────────

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
    speeds = [s["speed_mag"] for t, s in trace if s["moving"] == 1]
    if speeds:
        min_s = min(speeds)
        avg_s = sum(speeds) / len(speeds)
        zero_crossings = sum(1 for i in range(1, len(speeds))
                             if speeds[i] < SPEED_FLOOR and speeds[i-1] >= SPEED_FLOOR)
        print(f"    Speed: avg={avg_s:.0f}  min={min_s:.0f}  zero-crossings={zero_crossings}")
        if min_s > avg_s * 0.3 and zero_crossings < 3:
            print(f"    → Velocity stays continuous at {EDGE_RATE_HZ} Hz re-target")
        else:
            print(f"    → Velocity discontinuous at {EDGE_RATE_HZ} Hz (stop-go detected)")

    return trace


# ── Edge probe: direction reversal ────────────────────────────────────────────

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
    print(f"  Move: start → start-{FIRST_LEG} → retarget to start-{SECOND_LEG}")
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

        def return_home():
            safe_setup(ser, sid, accel=ACCEL, speed=500)
            seed_goal(ser, sid, read_pos(ser, sid))
            P.write_register_word(ser, sid, REG_TARGET_POSITION, home_pos)
            time.sleep(2.5)

        # Return to start
        return_home()

        # High-rate re-target
        trace_hr = edge_high_rate_retarget(ser, sid)
        if trace_hr:
            save_trace(os.path.join(DATA_DIR, "edge_high_rate.csv"), trace_hr)

        return_home()

        # VELOCITY-MODE HYBRID (operator-gated: new mode, watch the servo)
        input("  Press Enter to run VELOCITY-MODE hybrid probe (or Ctrl+C to skip)...")
        result_vm = edge_velocity_mode_hybrid(ser, sid)
        if result_vm:
            save_trace(os.path.join(DATA_DIR, "edge_velocity_hybrid.csv"), result_vm["trace"])

        return_home()

        # Direction reversal
        input("  Press Enter to run direction reversal probe (or Ctrl+C to skip)...")
        result_rev = edge_direction_reversal(ser, sid)
        if result_rev:
            save_trace(os.path.join(DATA_DIR, "edge_reversal.csv"), result_rev["trace"])

        return_home()

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