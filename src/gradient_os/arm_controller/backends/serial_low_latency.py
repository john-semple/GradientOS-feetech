# backends/serial_low_latency.py
#
# CH340 USB-serial latency-timer fix.
#
# The CH340 (and most USB-serial adapters) buffer received bytes in the kernel
# and deliver them to userspace only after the latency timer expires (default
# 16 ms) or the buffer fills — whichever comes first.  A servo sync-read that
# takes ~0.1 ms of wire time therefore costs the application 16-30 ms of wall
# time waiting for delivery.  This was measured in production logs
# (2026-09-15): 6-servo sync reads averaged 29.8 ms, max 64.1 ms.
#
# Setting the latency timer to 1 ms makes the driver deliver after at most
# 1 ms, cutting read wall-time to ~2-5 ms.  The setting resets on USB replug,
# so it is applied every time a port is opened.
#
# Two methods are attempted (both are harmless if they fail):
#   1. sysfs file: /sys/bus/usb-serial/devices/<devname>/latency_timer
#      (needs write permission; udev rules can make this permanent)
#   2. TIOCGSERIAL ioctl with ASYNC_LOW_LATENCY flag (also sets the
#      latency timer to 1 on the CH340 driver)

import errno
import fcntl
import os
import struct

# From <linux/serial.h> — not importable portably, so defined here
TIOCGSERIAL = 0x541E
TIOCSSERIAL = 0x541F
ASYNC_LOW_LATENCY = 0x2000
SERIAL_STRUCT_NPORTS = 8  # as in struct serial_struct


def _try_sysfs_latency(port_path: str, value_ms: int) -> bool:
    """Write the latency timer via sysfs. Returns True on success."""
    dev_name = None
    # /dev/ttyUSB0 -> ttyUSB0 ; /dev/serial/by-id/... -> resolve first
    base = os.path.basename(port_path)
    # Try direct basename first
    candidates = [base]
    # Also try the realpath basename (by-id symlinks)
    try:
        candidates.append(os.path.basename(os.path.realpath(port_path)))
    except OSError:
        pass

    for name in candidates:
        sysfs = f"/sys/bus/usb-serial/devices/{name}/latency_timer"
        try:
            with open(sysfs, "w") as fp:
                fp.write(str(value_ms))
            return True
        except OSError:
            continue
    return False


def _try_ioctl_low_latency(ser) -> bool:
    """Set ASYNC_LOW_LATENCY via TIOCGSERIAL/TIOCSSERIAL ioctl.

    struct serial_struct layout (only the flags field matters; the
    kernel tolerates a get-then-set roundtrip with the same struct):
      int type, line, port, irq, flags, xmit_fifo_size, ...
    """
    try:
        fd = ser.fileno()
    except (ValueError, OSError):
        return False

    # serial_struct is a series of ints + some larger fields; 36 ints covers
    # it safely for the roundtrip (kernel copies field-by-field).
    try:
        buf = bytearray(36 * 4)
        # TIOCGSERIAL
        fcntl.ioctl(fd, TIOCGSERIAL, buf, True)
        flags = struct.unpack_from("@i", buf, 16)[0]  # flags is 5th int
        if flags & ASYNC_LOW_LATENCY:
            return True  # already set
        struct.pack_into("@i", buf, 16, flags | ASYNC_LOW_LATENCY)
        fcntl.ioctl(fd, TIOCSSERIAL, buf, True)
        return True
    except OSError:
        return False


def apply_low_latency(ser, port_path: str, verbose: bool = True) -> None:
    """Apply CH340 low-latency settings to an open serial port.

    Call immediately after serial.Serial() opens the port.  Both methods
    are attempted; failures are logged (unless verbose=False) but never
    raised — missing permissions degrade to default latency, not an error.

    Args:
        ser: An open serial.Serial instance (or None — no-op).
        port_path: Device path used to open the port (for sysfs lookup).
        verbose: Print what was applied / why not.
    """
    if ser is None:
        return
    if os.name != "posix":
        return

    sysfs_ok = _try_sysfs_latency(port_path, 1)
    ioctl_ok = _try_ioctl_low_latency(ser)

    if verbose:
        if sysfs_ok or ioctl_ok:
            methods = []
            if sysfs_ok:
                methods.append("sysfs=1ms")
            if ioctl_ok:
                methods.append("ioctl LOW_LATENCY")
            print(f"[SerialLatency] Low-latency mode applied ({', '.join(methods)}) on {port_path}")
        else:
            print(
                "[SerialLatency] Could not set low-latency mode (no permission "
                "for sysfs and ioctl unavailable). Reads will use the default "
                "16 ms USB latency. Consider a udev rule: "
                'ACTION=="add", SUBSYSTEM=="usb-serial", DRIVERS=="ch341", '
                'ATTR{latency_timer}="1"'
            )