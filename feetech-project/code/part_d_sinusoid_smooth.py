"""
part_d_sinusoid_smooth.py — Sprint 07 Part D (visual smoothness test)

Streams a sinusoidal position trajectory and lets the operator VISUALLY verify
smoothness (pointer taped to the servo horn). This is the acid test for the
Case A finding: a sine wave has no cruise plateaus, continuously varying
velocity, and a direction reversal every half-cycle — any stop-go firmware
behavior shows up instantly as stepping/stutter instead of a fluid wave.

Two phases (back-to-back visual A/B):

  1. LEGACY phase (optional, --legacy-ab): streams the SAME sinusoid using
     today's production settings (speed cap 4095, accel 0 = MAX accel).
     Expected: stuttering/hopping pointer — this is the jerkiness the
     production arm exhibits today.
  2. PROFILED phase: same sinusoid, moderate cap (auto-sized ~2.5x the
     profile's peak velocity), accel 10, goals streamed 100 Hz with a small
     lookahead offset (goals always slightly ahead in time).
     Expected under Case A: fluid wave, natural decel into the extremes,
     smooth reversal. Tiny hesitation at extremes = gear backlash (mechanical,
     not firmware — Sprint 06 territory).

Safety:
  - Oscillation band is computed from the actual start position and kept
    entirely BELOW the rest position (never approaches 4095 seam).
  - Center = start - amplitude - 100; band = center +/- amplitude.
  - Hard bounds guard every cycle: if position leaves center +/- 1.3*amp,
    immediately command goal = current position (stop in place).
  - Safe-move recipe to reach the oscillation center.
  - Ctrl+C safe: finally block stops the servo where it is.
  - PSU current watched by operator; ~30-45s total motion.

Usage:
  python part_d_sinusoid_smooth.py --sid 1 [--legacy-ab]
  python part_d_sinusoid_smooth.py --sid 1 --freq 0.25 --amplitude 300

Output:
  - Console: phase cues ("WATCH NOW"), live telemetry every ~1s, end summary
  - CSV: feetech-project/data/part_d_sinusoid/<timestamp>/{legacy,profiled}.csv
"""

import argparse
import csv
import math
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from bench_utils import (
    open_serial, safe_setup, seed_goal, assert_safe_target, read_pos,
    read_telemetry_sample, REG_TARGET_ACCEL, REG_TARGET_POSITION, REG_TARGET_SPEED,
)
from gradient_os.arm_controller.backends.sts3215 import protocol as P


def safe_move_to(ser, sid, target, cap=500, accel=10):
    """Safe recipe move: seed, verify, command, wait for arrival."""
    current = read_pos(ser, sid)
    assert_safe_target(target)
    safe_setup(ser, sid, accel=accel, speed=cap)
    seed_goal(ser, sid, current)
    P.write_register_word(ser, sid, REG_TARGET_POSITION, target)
    for _ in range(100):
        time.sleep(0.05)
        pos = read_pos(ser, sid)
        mov = None
        for _ in range(3):
            from bench_utils import read_moving
            mov = read_moving(ser, sid)
            if mov is not None:
                break
        if mov == 0 and pos is not None and abs(pos - target) <= 5:
            return pos
    return read_pos(ser, sid)


def run_sinusoid(ser, sid, center, amplitude, freq, cycles, rate_hz,
                 cap, accel, lookahead_s, label, out_dir):
    """
    Stream one sinusoid phase. Returns (trace, stats).
    trace rows: (t, commanded_goal, pos, speed_mag, speed_raw, moving, load, voltage, temp)
    """
    interval = 1.0 / rate_hz
    duration = cycles / freq
    lo_bound = center - int(1.3 * amplitude)
    hi_bound = center + int(1.3 * amplitude)

    print(f"\n  --- {label} phase ---")
    print(f"  WATCH NOW: {cycles} sine cycles @ {freq} Hz "
          f"(band {center - amplitude}..{center + amplitude}, cap {cap}, accel {accel})")
    print(f"  Watch the pointer for: stepping/stutter (BAD) vs fluid wave (GOOD).")

    safe_setup(ser, sid, accel=accel, speed=cap)
    seed_goal(ser, sid, read_pos(ser, sid))

    trace = []
    write_fails = 0
    guard_stops = 0
    t0 = time.perf_counter()

    try:
        while True:
            t = time.perf_counter() - t0
            if t >= duration:
                break

            # Commanded goal: sinusoid evaluated slightly AHEAD in time
            phase = 2.0 * math.pi * freq * (t + lookahead_s)
            goal = int(round(center + amplitude * math.sin(phase)))
            goal = max(lo_bound, min(hi_bound, goal))

            ok = P.write_register_word(ser, sid, REG_TARGET_POSITION, goal)
            if not ok:
                write_fails += 1

            sample = read_telemetry_sample(ser, sid)
            if sample is not None:
                trace.append((t, goal, sample["pos"], sample["speed_mag"],
                              sample["speed_raw"], sample["moving"], sample["load"],
                              sample["voltage"], sample["temp"]))

                # Runaway guard: outside 1.3x band -> stop in place NOW
                if sample["pos"] < lo_bound or sample["pos"] > hi_bound:
                    P.write_register_word(ser, sid, REG_TARGET_POSITION, sample["pos"])
                    guard_stops += 1
                    print(f"  !! GUARD STOP at t={t:.2f}s pos={sample['pos']} "
                          f"(bounds {lo_bound}..{hi_bound})")

            # pace to stream rate
            elapsed = time.perf_counter() - t0
            target_t = (len(trace) + 1) * interval if False else elapsed
            sleep = interval - (time.perf_counter() - t0 - t)
            if sleep > 0:
                time.sleep(sleep)
    finally:
        # Stop cleanly wherever we are: seed goal at current position
        pos = read_pos(ser, sid)
        if pos is not None:
            seed_goal(ser, sid, pos)
        print(f"  {label} phase done (stopped at {pos}).")

    # ── Stats ────────────────────────────────────────────────────────────────
    if trace:
        actual_rate = len(trace) / duration
        tracking_err = [abs(g - p) for (_, g, p, *_rest) in trace]
        max_err = max(tracking_err)
        avg_err = sum(tracking_err) / len(tracking_err)
        mags = [m for (_, _, _, m, _, _, *_r) in trace if m > 0]
        # stall detection: servo stopped while goal stream active and far away
        stalls = sum(1 for (t, g, p, m, _raw, mov, *_r) in trace
                     if mov == 0 and abs(g - p) > 20 and t > 0.3
                     and t < duration - 0.3)
        peak_cmd_vel = amplitude * 2 * math.pi * freq
        print(f"  Stats: {len(trace)} samples ({actual_rate:.0f} Hz stream), "
              f"tracking err avg {avg_err:.1f} / max {max_err:.0f} counts, "
              f"mid-move stalls {stalls}, write fails {write_fails}, guard stops {guard_stops}")
        print(f"  Commanded peak velocity ~{peak_cmd_vel:.0f} counts/s vs cap {cap}")
    else:
        print("  !! NO TELEMETRY — check bench_utils bulk read!")

    # Save CSV
    os.makedirs(out_dir, exist_ok=True)
    fn = os.path.join(out_dir, f"{label}.csv")
    with open(fn, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "goal", "pos", "speed_mag", "speed_raw", "moving",
                    "load", "voltage", "temp"])
        for row in trace:
            w.writerow(row)
    print(f"  Trace saved: {fn}")

    return trace


def main():
    parser = argparse.ArgumentParser(description="Sprint 07 Part D: sinusoidal smoothness test")
    parser.add_argument("--sid", type=int, default=1, help="Servo ID (default 1)")
    parser.add_argument("--port", type=str, default="/dev/serial/ch340")
    parser.add_argument("--amplitude", type=int, default=350, help="Oscillation amplitude, counts (~31 deg)")
    parser.add_argument("--freq", type=float, default=0.15, help="Sine frequency, Hz")
    parser.add_argument("--cycles", type=int, default=3, help="Number of sine cycles in profiled phase")
    parser.add_argument("--rate", type=int, default=100, help="Goal stream rate, Hz")
    parser.add_argument("--lookahead", type=float, default=0.05, help="Goal lookahead, seconds")
    parser.add_argument("--accel", type=int, default=10, help="Accel register (10 = moderate)")
    parser.add_argument("--legacy-ab", action="store_true",
                        help="Run a 1-cycle LEGACY phase (cap 4095, accel 0) first for visual A/B")
    parser.add_argument("--legacy-cycles", type=int, default=1, help="Cycles in legacy phase")
    args = parser.parse_args()

    sid = args.sid
    A = args.amplitude
    f = args.freq

    print(f"=== Sprint 07 Part D — Sinusoidal smoothness test ===")
    print(f"  Servo {sid}: amplitude {A} counts ({A * 360 / 4096:.1f} deg each way), "
          f"freq {f} Hz, {args.cycles} cycles @ {args.rate} Hz stream")

    # Auto cap: ~2.5x the sinusoid peak velocity, rounded up to 50-step units
    peak_vel = A * 2 * math.pi * f
    cap = max(300, int(math.ceil(peak_vel * 2.5 / 50.0)) * 50)
    print(f"  Auto cap: {cap} (peak sine velocity ~{peak_vel:.0f} counts/s)")

    ser = open_serial(args.port)
    time.sleep(0.1)

    start = read_pos(ser, sid)
    print(f"  Start position: {start}")
    if start is None:
        print("ERROR: cannot read servo.")
        ser.close()
        return

    # Oscillation center: safely below the rest position
    center = start - A - 100
    assert_safe_target(center - A)   # lowest extreme
    assert_safe_target(center + A)  # highest extreme (== start - 100)
    print(f"  Oscillation center {center}, band {center - A}..{center + A} "
          f"(entire band is {start - (center + A)} counts below rest)")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "part_d_sinusoid", stamp)

    # Move to center with the safe recipe
    print(f"\n  Moving to oscillation center {center} (safe move, ~2s)...")
    arrived = safe_move_to(ser, sid, center)
    print(f"  At center: {arrived}")

    try:
        if args.legacy_ab:
            run_sinusoid(ser, sid, center, A, f, args.legacy_cycles, args.rate,
                         cap=4095, accel=0, lookahead_s=args.lookahead,
                         label="legacy", out_dir=out_dir)
            time.sleep(1.0)

        run_sinusoid(ser, sid, center, A, f, args.cycles, args.rate,
                     cap=cap, accel=args.accel, lookahead_s=args.lookahead,
                     label="profiled", out_dir=out_dir)
    finally:
        # Return to start position (safe move) and close
        print(f"\n  Returning to start {start}...")
        safe_move_to(ser, sid, start)
        ser.close()

    print("\nPart D complete. Compare the two phases visually + in the CSVs:")
    print(f"  {out_dir}/legacy.csv (if run) vs profiled.csv")
    print("  Look for: legacy = stop-go stepping; profiled = continuous wave,")
    print("  natural decel into extremes, tiny backlash pause at reversal.")


if __name__ == "__main__":
    main()