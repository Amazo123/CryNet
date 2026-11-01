#!/usr/bin/env python3
"""Measure the hub's end-to-end latency, and whether it calls the cry.

The chain, from the log:

  asking for the window   the trigger fired
  286/286 fragments in X  the burst arrived
  P(cry)=...              the model's answer
  ALERT - cry             the cry was confirmed

The script plays the recorded cry through the laptop's speakers near the
node and prints the chain, so the latency from the sound to the verdict
is visible rather than assumed.

Usage:
    python firmware/tools/measure_latency.py --runs 3
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRY_WAV = ROOT / "research" / "in_domain" / "session9" / "session.wav"

LINE_RE = re.compile(r"^I \((\d+)\) (\w+): (.*)$")


def one_run(port: str, warmup: float, sound: float, tail: float):
    import serial
    import winsound

    ser = serial.Serial(port, 115200, timeout=0.3)
    lines: list[str] = []

    def reader():
        end = time.time() + warmup + sound + tail
        while time.time() < end:
            try:
                raw = ser.readline()
            except Exception:
                return
            if raw:
                lines.append(raw.decode("utf-8", "replace").rstrip())

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    time.sleep(warmup)
    winsound.PlaySound(str(CRY_WAV), winsound.SND_FILENAME | winsound.SND_ASYNC)
    time.sleep(sound)
    winsound.PlaySound(None, winsound.SND_PURGE)
    time.sleep(tail)
    t.join(timeout=3)
    try:
        ser.close()
    except Exception:
        pass

    out = []
    for l in lines:
        m = LINE_RE.match(l)
        if not m:
            continue
        ts = int(m.group(1))
        body = m.group(3)
        if "asking for the window" in body:
            out.append(("ask", ts, body))
        elif "fragments in" in body:
            out.append(("burst", ts, body))
        elif "P(cry)=" in body:
            out.append(("model", ts, body))
        elif re.search(r"node \d+: (ALERT|cry \(held\)|no cry|silent)", body):
            out.append(("verdict", ts, body))
        elif "stalled" in body or "timed out" in body:
            out.append(("stall", ts, body))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM32")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--warmup", type=float, default=6.0)
    ap.add_argument("--sound", type=float, default=16.0)
    ap.add_argument("--tail", type=float, default=18.0)
    args = ap.parse_args()

    print(f"=== {args.runs} run(s): the cry played from the laptop's speakers\n")
    totals = []
    for i in range(args.runs):
        marks = one_run(args.port, args.warmup, args.sound, args.tail)
        print(f"--- run {i + 1}")
        ask = burst = model = verdict = None
        for kind, ts, body in marks:
            if kind == "ask":
                ask = ts
                print(f"  {ts / 1000:9.3f}s  {body[:64]}")
            elif kind == "burst":
                burst = ts
                secs = re.search(r"in ([0-9.]+) s", body)
                print(f"  {ts / 1000:9.3f}s  {body[:64]}")
                if ask and secs:
                    print(f"                 (the burst took {secs.group(1)} s)")
            elif kind == "model":
                model = ts
                print(f"  {ts / 1000:9.3f}s  {body[:64]}")
            elif kind == "verdict":
                verdict = ts
                print(f"  {ts / 1000:9.3f}s  {body[:64]}")
            elif kind == "stall":
                print(f"  {ts / 1000:9.3f}s  !! {body[:64]}")
        if ask and verdict:
            total = (verdict - ask) / 1000.0
            totals.append(total)
            print(f"                 ==> request to verdict: {total:.2f} s")
        if burst and model:
            print(f"                 ==> burst to model: {(model - burst) / 1000.0:.2f} s")
        print()

    if totals:
        print(f"request to verdict: min {min(totals):.2f} s  "
              f"max {max(totals):.2f} s  mean {sum(totals) / len(totals):.2f} s")
    sys.stdout.flush()
    # The reader thread is a daemon and is still blocked in a read when
    # the interpreter wants to shut down; leaving it that way prints a
    # traceback that has nothing to do with the measurement.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
