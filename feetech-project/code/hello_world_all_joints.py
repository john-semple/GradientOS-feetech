import serial, time
from gradient_os.arm_controller.backends.sts3215 import protocol as P

ser = serial.Serial("/dev/serial/ch340", 1000000, timeout=0.1)

STEP = 228  # ~20 degrees

def rb(sid, a, tries=3):
    for _ in range(tries):
        v = P.read_register_byte(ser, sid, a); time.sleep(0.01)
        if v is not None: return v
    return None

def rw(sid, a, tries=3):
    for _ in range(tries):
        v = P.read_register_word(ser, sid, a); time.sleep(0.01)
        if v is not None: return v
    return None

def setup_servo(sid):
    P.write_register_byte(ser, sid, 0x29, 10);   time.sleep(0.01)
    P.write_register_word(ser, sid, 0x2E, 300);  time.sleep(0.01)

def seed_goal(sid, pos):
    P.write_register_word(ser, sid, 0x2A, pos); time.sleep(0.01)
    rb_val = rw(sid, 0x2A)
    assert abs(rb_val - pos) <= 3, f"ID {sid}: goal readback {rb_val} vs {pos} - STOP"

def move_and_back(sid, delta, label):
    start = rw(sid, 0x38)
    target = start + delta
    assert 100 < target < 4090, f"ID {sid}: unsafe target {target}"
    print(f"\n{'='*60}")
    print(f"{label}: ID {sid} at {start}, moving {delta} counts ({delta*360/4096:.1f} deg) -> {target}")
    setup_servo(sid)
    seed_goal(sid, start)
    P.write_register_word(ser, sid, 0x2A, target)
    time.sleep(1.5)
    pos1 = rw(sid, 0x38)
    load1 = rw(sid, 0x3C)
    print(f"  Forward: {start} -> {pos1} ({(pos1-start)*360/4096:.2f} deg)  load={load1}  status={hex(rb(sid,0x41) or 0)}")
    # move back
    P.write_register_word(ser, sid, 0x2A, start)
    time.sleep(1.5)
    pos2 = rw(sid, 0x38)
    print(f"  Back:    {pos1} -> {pos2} ({(pos2-pos1)*360/4096:.2f} deg)  status={hex(rb(sid,0x41) or 0)}")
    print(f"  Drift: {pos2-start} counts ({(pos2-start)*360/4096:.2f} deg)")
    return start, pos1, pos2

def move_twin_and_back(sid_a, sid_b, delta_a, delta_b, label):
    """Move a twin-motor pair. delta_a for sid_a, delta_b for sid_b (mirrored if needed)."""
    start_a = rw(sid_a, 0x38)
    start_b = rw(sid_b, 0x38)
    target_a = start_a + delta_a
    target_b = start_b + delta_b
    assert 100 < target_a < 4090, f"ID {sid_a}: unsafe target {target_a}"
    assert 100 < target_b < 4090, f"ID {sid_b}: unsafe target {target_b}"
    print(f"\n{'='*60}")
    print(f"{label}: ID {sid_a} at {start_a} ({'+' if delta_a>=0 else ''}{delta_a}), ID {sid_b} at {start_b} ({'+' if delta_b>=0 else ''}{delta_b})")
    print(f"  Targets: {sid_a}->{target_a}, {sid_b}->{target_b}")
    setup_servo(sid_a)
    setup_servo(sid_b)
    seed_goal(sid_a, start_a)
    seed_goal(sid_b, start_b)
    # command both simultaneously
    P.write_register_word(ser, sid_a, 0x2A, target_a)
    P.write_register_word(ser, sid_b, 0x2A, target_b)
    time.sleep(1.5)
    pos_a1 = rw(sid_a, 0x38)
    pos_b1 = rw(sid_b, 0x38)
    print(f"  Forward: {sid_a} {start_a}->{pos_a1} ({(pos_a1-start_a)*360/4096:.1f} deg)  {sid_b} {start_b}->{pos_b1} ({(pos_b1-start_b)*360/4096:.1f} deg)")
    print(f"  Loads: {sid_a}={rw(sid_a,0x3C)}  {sid_b}={rw(sid_b,0x3C)}")
    print(f"  Status: {sid_a}={hex(rb(sid_a,0x41) or 0)}  {sid_b}={hex(rb(sid_b,0x41) or 0)}")
    # move back
    P.write_register_word(ser, sid_a, 0x2A, start_a)
    P.write_register_word(ser, sid_b, 0x2A, start_b)
    time.sleep(1.5)
    pos_a2 = rw(sid_a, 0x38)
    pos_b2 = rw(sid_b, 0x38)
    print(f"  Back:    {sid_a} {pos_a1}->{pos_a2}  {sid_b} {pos_b1}->{pos_b2}")
    print(f"  Drift:   {sid_a}={pos_a2-start_a}  {sid_b}={pos_b2-start_b}")

# J1 (Base): ID 10, move +STEP (toward center)
move_and_back(10, +STEP, "J1 Base")

# J2 (Shoulder): IDs 20+21 twin, 20 inverted so mirrored commands
move_twin_and_back(20, 21, -STEP, +STEP, "J2 Shoulder (twin 20+21)")

# J3 (Elbow): IDs 30+31 twin, 30 inverted so mirrored commands
move_twin_and_back(30, 31, -STEP, +STEP, "J3 Elbow (twin 30+31)")

# J4 (Wrist Roll): ID 40, near upper limit (4057) -> move DOWN
move_and_back(40, -STEP, "J4 Wrist Roll")

# J5 (Wrist Pitch): ID 50
move_and_back(50, -STEP, "J5 Wrist Pitch")

# J6 (Wrist Yaw): ID 60
move_and_back(60, -STEP, "J6 Wrist Yaw")

print(f"\n{'='*60}")
print("All joints exercised. Final positions:")
for sid in [10, 20, 21, 30, 31, 40, 50, 60]:
    pos = rw(sid, 0x38)
    status = rb(sid, 0x41)
    print(f"  ID {sid:>2}: pos={pos}  status={hex(status or 0)}")
ser.close()