import serial, time
from gradient_os.arm_controller.backends.sts3215 import protocol as P

ser = serial.Serial("/dev/serial/ch340", 1000000, timeout=0.1)

ARM_IDS = [10, 20, 21, 30, 31, 40, 50, 60]
# Inverted servos: 10, 20, 30, 40, 50, 60 (encoder decreases when joint angle increases)
INVERTED = {10, 20, 30, 40, 50, 60}

SPEED = 200    # slow, gentle
ACCEL = 10     # gentle acceleration

def rw(sid, a, tries=3):
    for _ in range(tries):
        v = P.read_register_word(ser, sid, a); time.sleep(0.01)
        if v is not None: return v
    return None

def rb(sid, a, tries=3):
    for _ in range(tries):
        v = P.read_register_byte(ser, sid, a); time.sleep(0.01)
        if v is not None: return v
    return None

# Read current positions
current = {}
for sid in ARM_IDS:
    current[sid] = rw(sid, 0x38)
    time.sleep(0.005)

print("Current positions:")
for sid in ARM_IDS:
    inv = "(inv)" if sid in INVERTED else ""
    print(f"  ID {sid:>2}: {current[sid]:>4} {inv}")

# Define a gentle "home" target: move each servo ~30 degrees toward centre (2048)
# For inverted servos, "toward centre" means encoder value toward 2048
# For non-inverted (21, 31), also toward 2048
# Cap the move at 30 deg (341 counts) so nothing swings wildly
MAX_STEP = 341  # ~30 deg

targets = {}
for sid in ARM_IDS:
    pos = current[sid]
    if pos > 2048:
        delta = min(MAX_STEP, pos - 2048)
        target = pos - delta
    else:
        delta = min(MAX_STEP, 2048 - pos)
        target = pos + delta
    targets[sid] = target

print(f"\nGentle home move (max {MAX_STEP*360/4096:.0f} deg toward centre 2048):")
for sid in ARM_IDS:
    delta = targets[sid] - current[sid]
    print(f"  ID {sid:>2}: {current[sid]:>4} -> {targets[sid]:>4}  ({delta:+d} counts, {delta*360/4096:+.1f} deg)")

# Safety checks
for sid in ARM_IDS:
    assert 100 < targets[sid] < 4090, f"ID {sid}: unsafe target {targets[sid]}"

# Phase 1: setup all servos (accel + speed) and seed goals to current position
print("\nSeeding goals to current positions...")
for sid in ARM_IDS:
    P.write_register_byte(ser, sid, 0x29, ACCEL);   time.sleep(0.01)
    P.write_register_word(ser, sid, 0x2E, SPEED);   time.sleep(0.01)

# Seed goals individually (not sync write, to verify each one)
for sid in ARM_IDS:
    P.write_register_word(ser, sid, 0x2A, current[sid]); time.sleep(0.01)

# Verify goal readbacks
for sid in ARM_IDS:
    rb_val = rw(sid, 0x2A)
    assert abs(rb_val - current[sid]) <= 5, f"ID {sid}: goal readback {rb_val} vs {current[sid]} - STOP"

print("All goals seeded. Verifying torque is on...")
for sid in ARM_IDS:
    t = rb(sid, 0x28)
    print(f"  ID {sid:>2}: torque={t}")

# Phase 2: use sync_write to command all servos to their home targets simultaneously
print("\nCommanding coordinated move via sync_write...")
servo_data = [(sid, targets[sid], SPEED, ACCEL) for sid in ARM_IDS]
P.sync_write_goal_pos_speed_accel(ser, servo_data)

# Monitor the move
print("\nMonitoring (position every 0.3s):")
print(f"  {'t':>4}  " + "  ".join(f"ID{sid:>2}" for sid in ARM_IDS) + "  all_status")
for step in range(20):
    time.sleep(0.3)
    positions = {}
    statuses = []
    for sid in ARM_IDS:
        positions[sid] = rw(sid, 0x38)
        time.sleep(0.005)
    for sid in ARM_IDS:
        s = rb(sid, 0x41)
        statuses.append(s if s is not None else 0)
        time.sleep(0.005)
    all_ok = all(s == 0 for s in statuses)
    t = f"{0.3*(step+1):.1f}"
    pos_str = "  ".join(f"{positions[sid]:>5}" if positions[sid] is not None else "  ???" for sid in ARM_IDS)
    status_str = "OK" if all_ok else "ERR:" + ",".join(hex(s) for s in statuses if s != 0)
    print(f"  {t:>4}s  {pos_str}  {status_str}")
    # Check if all servos have settled (no movement in last sample)
    if step > 2:
        all_settled = True
        for sid in ARM_IDS:
            if positions[sid] is None or abs(positions[sid] - targets[sid]) > 3:
                all_settled = False
                break
        if all_settled:
            print(f"  All settled at t={0.3*(step+1):.1f}s")
            break

# Final report
print(f"\n{'='*70}")
print("Final positions vs targets:")
for sid in ARM_IDS:
    final = rw(sid, 0x38)
    target = targets[sid]
    start = current[sid]
    moved = (final - start) * 360 / 4096
    err = (final - target) * 360 / 4096
    status = rb(sid, 0x41)
    print(f"  ID {sid:>2}: {start:>4} -> {final:>4} (target {target:>4})  moved {moved:+.1f} deg  err {err:+.2f} deg  status {hex(status or 0)}")

ser.close()