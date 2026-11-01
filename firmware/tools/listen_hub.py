#!/usr/bin/env python3
"""Listen to the hub and report what it does with a sound.

This script plays nothing.  It only reads the hub's log on COM32 and
prints the chain, so that a sound the user makes by hand - a cry from a
phone next to the node - can be watched as it travels:

  asking for the window   the trigger fired
  286/286 fragments in X  the burst arrived
  P(cry)=...              the model's answer
  ALERT - cry             the cry was confirmed

Usage:
    python firmware/tools/listen_hub.py --seconds 90
    python firmware/tools/listen_hub.py --seconds 90 --warmup 10
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time

LINE_RE = re.compile(r"^I \((\d+)\) (\w+): (.*)$")

# The lines that matter, in the order they matter.
MARKERS = (
    ("asking for the window", "ask"),
    ("fragments in", "burst"),
    ("window rms", "window"),
    ("front end", "model"),
    ("P(cry)=", "model"),
    ("ALERT", "verdict"),
    ("no cry", "verdict"),
    ("silent", "verdict"),
    ("cry (", "maybe"),
    ("stalled", "problem"),
    ("timed out", "problem"),
    ("missing", "problem"),
    ("bad crc", "problem"),
    ("resend", "problem"),
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM32")
    ap.add_argument("--seconds", type=float, default=90.0,
                    help="how long to listen for")
    ap.add_argument("--warmup", type=float, default=10.0,
                    help="seconds of quiet before the sound is expected")
    ap.add_argument("--reset", action="store_true",
                    help="reset the hub before listening")
    args = ap.parse_args()

    import serial

    print(f"=== listening on {args.port} for {args.seconds:.0f} s "
          f"(the sound is expected after {args.warmup:.0f} s)", flush=True)

    ser = serial.Serial(args.port, 115200, timeout=0.3)
    if args.reset:
        ser.dtr = False
        ser.rts = True
        time.sleep(0.15)
        ser.rts = False

    marks: list[tuple[str, int, str]] = []
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
            m = LINE_RE.match(line)
            if not m:
                continue
            ts = int(m.group(1))
            body = m.group(3)
            for needle, kind in MARKERS:
                if needle in body:
                    marks.append((kind, ts, body))
                    print(f"  [{time.time() - start:6.2f}s] {body[:90]}", flush=True)
                    break

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    if args.warmup > 0:
        print(f"--- quiet for {args.warmup:.0f} s: **play the cry now** ---",
              flush=True)
        time.sleep(args.warmup)
        print("--- the sound is expected from here ---", flush=True)

    t.join(timeout=args.seconds + 5)
    try:
        ser.close()
    except Exception:
        pass

    verdicts = [m for m in marks if m[0] == "verdict"]
    cries = [m for m in verdicts if "ALERT" in m[2] or "cry (held)" in m[2]]
    print(f"\n=== {len(marks)} marks, {len(verdicts)} verdicts, "
          f"{len(cries)} cry verdicts", flush=True)
    for kind, ts, body in verdicts:
        print(f"  {body[:100]}")
    sys.stdout.flush()
    # The reader thread is still blocked in a read when the interpreter
    # wants to shut down; that prints a traceback that has nothing to do
    # with the listening.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
