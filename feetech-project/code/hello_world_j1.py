import serial, time
from gradient_os.arm_controller.backends.sts3215 import protocol as P

ser = serial.Serial("/dev/serial/ch340", 1000000, timeout=0.1)
SID = 10

def rb(a, tries=3):
    for _ in range(tries):
        v = P.read_register_byte(ser, SID, a); time.sleep(0.01)
        if v is not None: return v
    return None

def rw(a, tries=3):
    for _ in range(tries):
        v = P.read_register_word(ser, SID, a); time.sleep(0.01)
        if v is not None: return v
    return None

start = rw(0x38)
print(f"ID {SID} (J1 Base) start position: {start}")

step = 57  # ~5 degrees
target = start + step  # toward center (2048), safe direction
assert 100 < target < 4090, f"unsafe target {target}"
print(f"Moving +{step} counts ({step*360/4096:.1f} deg) -> target {target}")

# safe recipe: limits before torque, goal seeded to present
P.write_register_byte(ser, SID, 0x29, 10);   time.sleep(0.01)   # gentle accel
P.write_register_word(ser, SID, 0x2E, 300);  time.sleep(0.01)   # speed limit
P.write_register_word(ser, SID, 0x2A, start); time.sleep(0.01)  # goal := present

goal_readback = rw(0x2A)
assert abs(goal_readback - start) <= 3, f"goal readback wrong: {goal_readback} vs {start} - STOP"
print(f"Goal seeded OK ({goal_readback})")

# move
print("Commanding move...")
P.write_register_word(ser, SID, 0x2A, target)

for i in range(10):
    time.sleep(0.2)
    pos = rw(0x38)
    load = rw(0x3C)
    print(f"  t={0.2*(i+1):.1f}s  pos={pos}  load={load}")

time.sleep(0.5)
pos1 = rw(0x38)
print(f"Arrived: {start} -> {pos1} ({(pos1-start)*360/4096:.2f} deg)")
print(f"Status: {hex(rb(0x41) or 0)}")

# move back
print(f"\nMoving back -{step} counts -> target {start}")
P.write_register_word(ser, SID, 0x2A, start)
for i in range(10):
    time.sleep(0.2)
    pos = rw(0x38)
    print(f"  t={0.2*(i+1):.1f}s  pos={pos}")

time.sleep(0.5)
pos2 = rw(0x38)
print(f"Back: {pos1} -> {pos2} ({(pos2-pos1)*360/4096:.2f} deg)")
print(f"Final: {pos2} (start was {start}, drift: {pos2-start})")
print(f"Status: {hex(rb(0x41) or 0)}")
ser.close()