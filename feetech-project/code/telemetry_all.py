import serial, time
from gradient_os.arm_controller.backends.sts3215 import protocol as P

ser = serial.Serial("/dev/serial/ch340", 1000000, timeout=0.1)
IDS = [10, 20, 21, 30, 31, 40, 50, 60]

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

print("  ID  model    fw     pos  torque  voltage   temp   status    load")
print("-" * 78)
for sid in IDS:
    model = rw(sid, 0x03)
    fw_maj = rb(sid, 0x00)
    fw_min = rb(sid, 0x01)
    pos = rw(sid, 0x38)
    torque = rb(sid, 0x28)
    voltage = rb(sid, 0x3E)
    temp = rb(sid, 0x3F)
    status = rb(sid, 0x41)
    load = rw(sid, 0x3C)
    fw_str = f"{fw_maj}.{fw_min}" if fw_maj is not None else "?"
    v_str = f"{voltage/10:.1f}V" if voltage is not None else "?"
    s_str = hex(status) if status is not None else "?"
    pos_str = str(pos) if pos is not None else "?"
    torque_str = str(torque) if torque is not None else "?"
    load_str = str(load) if load is not None else "?"
    model_str = str(model) if model else "?"
    temp_str = str(temp) if temp is not None else "?"
    print(f"  {sid:>2}  {model_str:>6}  {fw_str:>5}  {pos_str:>6}  {torque_str:>6}   {v_str:>6}  {temp_str:>5}  {s_str:>8}  {load_str:>6}")

ser.close()