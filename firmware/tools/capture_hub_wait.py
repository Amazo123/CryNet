"""Wait for the hub to be plugged in, then raw-log its serial for a window.

Writes research/out/hub_node1_fullchain.log with [t] timestamped lines.
Exits 0 when the capture finished, 1 when the wait timed out.
"""
import sys, time
sys.path.insert(0, r"C:\Users\HP\.t3\projects\fp-2\firmware\tools")
import serial
from serial.tools import list_ports

OUT = r"C:\Users\HP\.t3\projects\fp-2\research\out\hub_node1_fullchain.log"
CAPTURE_S = 420
WAIT_LIMIT_S = 900


def hub_port():
    for p in list_ports.comports():
        if (p.vid == 0x1A86) or p.device == "COM32":  # CH343, the S3 hub
            return p.device
    return None


t0 = time.time()
port = None
while time.time() - t0 < WAIT_LIMIT_S:
    port = hub_port()
    if port:
        break
    time.sleep(2)

if not port:
    print("TIMEOUT: hub never appeared")
    sys.exit(1)

print(f"hub found on {port}, capturing {CAPTURE_S}s")
with open(OUT, "w", encoding="utf-8", errors="replace") as f, \
     serial.Serial(port, 115200, timeout=1) as s:
    s.setDTR(False); s.setRTS(False)
    start = time.time()
    while time.time() - start < CAPTURE_S:
        line = s.readline().decode("utf-8", "replace").rstrip()
        if line:
            f.write(f"[{time.time() - start:7.2f}s] {line}\n")
            f.flush()
print("capture complete:", OUT)
