#!/usr/bin/env python3
"""Measure node 3's link to the hub from several positions.

The hub prints the RSSI of every burst it receives.  A cry playing on
the laptop speakers keeps node 3 freezing windows, so the hub keeps
pulling them, so every pull gives a fresh RSSI reading.

Node 1 reads -20 dBm at the hub and node 3 reads -55 to -61 dBm.  That
is 35-40 dB between two cots in the same house.  This script holds the
cry going and asks the operator to move node 3 between positions; the
RSSI at each position says whether the gap is distance, orientation or
a faulty antenna.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RSSI_RE = re.compile(r"node (\d+): (\d+)/(\d+) fragments.*?signal (-?\d+) dBm")


def main() -> int:
    import serial
    import winsound

    hub_port = sys.argv[1] if len(sys.argv) > 1 else "COM32"
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 100.0
    positions = int(sys.argv[3]) if len(sys.argv) > 3 else 4

    clip = ROOT / "research" / "in_domain" / "session9" / "clips" / "clip_0000.wav"
    blob = clip.read_bytes()

    hub = serial.Serial(hub_port, 115200, timeout=0.2)
    time.sleep(0.2)
    hub.reset_input_buffer()

    readings: list[tuple[float, int, int, int]] = []
    stop = threading.Event()

    def reader():
        buf = b""
        while not stop.is_set():
            chunk = hub.read(hub.in_waiting or 1)
            if chunk:
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    text = ln.decode("utf-8", "replace")
                    m = RSSI_RE.search(text)
                    if m:
                        readings.append((time.time(), int(m.group(1)),
                                         int(m.group(3)), int(m.group(4))))

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # Keep the cry going for the whole run.
    def player():
        while not stop.is_set():
            winsound.PlaySound(blob, winsound.SND_MEMORY | winsound.SND_SYNC)

    p = threading.Thread(target=player, daemon=True)
    p.start()

    print("Move node 3 to the next position and press Enter.  "
          "Ctrl-C to stop.", flush=True)
    slot = seconds / positions
    for i in range(positions):
        t0 = time.time()
        try:
            input(f"[position {i + 1}/{positions}] press Enter when node 3 is placed > ")
        except EOFError:
            break
        while time.time() - t0 < slot:
            time.sleep(0.2)
    stop.set()
    t.join(timeout=2)
    hub.close()

    out = ROOT / "research" / "out" / "rssi_walk.log"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ts, node, total, rssi in readings:
            fh.write(f"{ts:.3f}  node {node}  signal {rssi} dBm\n")
    for node in sorted({r[1] for r in readings}):
        vals = [r[3] for r in readings if r[1] == node]
        if vals:
            fh.write(f"node {node}: {len(vals)} bursts, "
                     f"RSSI {min(vals)}..{max(vals)} dBm, "
                     f"mean {sum(vals) / len(vals):.1f}\n")
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
