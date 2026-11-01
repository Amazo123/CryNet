#!/usr/bin/env python3
"""Listen to the node and report what it hears.

The node owns the noise floor and the trigger level (D-63).  Its log is
the record of *why* it froze a window, so it has to be read alongside
the hub's log - otherwise a "no cry" verdict has nothing to explain it.

  rms 0.0063  floor 0.0028  level 0.0083     the room, and the level
  froze window, burst seq 15  level 0.0120  win rms 0.0100

Usage:
    python firmware/tools/listen_node.py --seconds 90
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time

MARKERS = (
    ("froze window", "freeze"),
    ("rms ", "level"),
    ("request: seq", "request"),
    ("resend", "problem"),
    ("served ", "served"),
    ("FATAL", "problem"),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM30")
    ap.add_argument("--seconds", type=float, default=90.0)
    ap.add_argument("--warmup", type=float, default=0.0)
    args = ap.parse_args()

    import serial

    print(f"=== node on {args.port} for {args.seconds:.0f} s", flush=True)
    ser = serial.Serial(args.port, 115200, timeout=0.3)
    time.sleep(0.2)
    ser.reset_input_buffer()

    marks: list[tuple[str, str]] = []
    start = time.time()

    def reader():
        end = start + args.seconds
        while time.time() < end:
            try:
                raw = ser.readline()
            except Exception:
                return
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").rstrip()
            if not line:
                continue
            for needle, kind in MARKERS:
                if needle in line:
                    marks.append((kind, line))
                    print(f"  [{time.time() - start:6.2f}s] {line[:100]}", flush=True)
                    break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    if args.warmup > 0:
        print(f"--- quiet for {args.warmup:.0f} s ---", flush=True)
        time.sleep(args.warmup)

    t.join(timeout=args.seconds + 5)
    try:
        ser.close()
    except Exception:
        pass

    freezes = [m for m in marks if m[0] == "freeze"]
    print(f"\n=== {len(marks)} marks, {len(freezes)} frozen windows", flush=True)
    for kind, line in marks:
        if kind in ("freeze", "problem"):
            print(f"  {line[:110]}")
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
