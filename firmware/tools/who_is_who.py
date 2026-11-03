#!/usr/bin/env python3
"""Say which node is on which port.

Node id is kept in NVS, so it survives a reflash -- but only if the
flash tool does not erase the partition.  This script does not flash at
all: it opens each port, resets the board over RTS/EN, and reads the
banner the firmware prints at boot, which names the node and its MAC.

Usage:
    python firmware/tools/who_is_who.py COM37 COM38
"""

import sys
import time

import serial


def read_banner(port: str, settle: float = 0.6, listen: float = 4.0) -> str:
    """Open the port, reset the board, and return what it says at boot."""
    s = serial.Serial(port, 115200, timeout=0.2)
    try:
        # The board may be mid-boot; drain whatever is buffered.
        time.sleep(0.3)
        s.reset_input_buffer()
        # ESP32: RTS drives EN, DTR drives GPIO0.  RTS alone resets.
        s.dtr = False
        s.rts = True
        time.sleep(0.15)
        s.rts = False
        time.sleep(settle)

        out = []
        deadline = time.time() + listen
        while time.time() < deadline:
            chunk = s.read(s.in_waiting or 1)
            if chunk:
                out.append(chunk.decode("utf-8", "replace"))
        return "".join(out)
    finally:
        s.close()


def main() -> int:
    ports = sys.argv[1:]
    if not ports:
        print(__doc__)
        return 1
    for p in ports:
        print(f"===== {p} =====")
        try:
            print(read_banner(p))
        except Exception as exc:  # noqa: BLE001 -- report, do not crash
            print(f"could not read {p}: {exc}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
