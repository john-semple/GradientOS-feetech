import serial, time
from gradient_os.arm_controller.backends.sts3215 import protocol as P

ser = serial.Serial("/dev/serial/ch340", 1000000, timeout=0.1)
IDS = [10, 20, 21, 30, 31, 40, 50, 60]

def rw(sid, a, tries=2):
    for _ in range(tries):
        v = P.read_register_word(ser, sid, a); time.sleep(0.01)
        if v is not None: return v
    return None

# Read initial positions
prev = {}
for sid in IDS:
    prev[sid] = rw(sid, 0x38)
    time.sleep(0.005)

print("Move the arm! Watching for position changes... (Ctrl+C to stop)")
print()
print("  ID      start    current   delta    deg")
print("-" * 55)

try:
    while True:
        for sid in IDS:
            pos = rw(sid, 0x38)
            time.sleep(0.005)
            if pos is None:
                continue
            if pos != prev[sid]:
                delta = pos - prev[sid]
                deg = delta * 360 / 4096
                sign = "+" if delta > 0 else ""
                print(f"  {sid:>2}   {prev[sid]:>6}   {pos:>6}   {sign}{delta:>5}   {sign}{deg:>6.1f}°")
                prev[sid] = pos
except KeyboardInterrupt:
    print("\nStopped.")
ser.close()