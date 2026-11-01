#!/usr/bin/env python3
"""Measure the hub's burst time, on the real boards.

The window takes 5.7-7.6 s to arrive at the hub, and the panel shows a
cry about eight seconds after it happened.  The cause is the hub's own
Bluetooth advertising: the ESP32-S3 has one radio and it carries both
Bluetooth and Wi-Fi, so every advertisement is a moment when the Wi-Fi
receiver cannot hear the fragments of the burst.

This script measures the burst the way the system experiences it:

  * it reads the hub's log on COM32,
  * it plays the recorded cry through the laptop's speakers, near the
    node, so the node's telemetry crosses the trigger and the hub asks
    for the window,
  * it reports how long the burst took and how many fragments arrived.

Usage:
    python firmware/tools/measure_burst.py
    python firmware/tools/measure_burst.py --label "after the BLE change"
"""

from __future__ import annotations

import argparse
import re
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CRY_WAV = ROOT / "research" / "in_domain" / "session9" / "session.wav"

# "node 1: 286/286 fragments in 5.71 s"
BURST_RE = re.compile(r"node (\d+): (\d+)/(\d+) fragments in ([0-9.]+) s")
# "node 1: missing fragments:" / "the hub asked for the window"
ASK_RE = re.compile(r"asking for the window \(seq (\d+)")
RESEND_RE = re.compile(r"resend|round", re.I)


def play_cry(path: Path, seconds: float) -> None:
    """Play the recording on the laptop's speakers."""
    import winsound

    if not path.is_file():
        print(f"no recording at {path}", file=sys.stderr)
        return
    print(f"playing {path.name} for {seconds:.0f} s on the laptop's speakers")
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
    time.sleep(seconds)
    winsound.PlaySound(None, winsound.SND_PURGE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM32")
    ap.add_argument("--seconds", type=float, default=45.0,
                    help="how long to listen for the burst")
    ap.add_argument("--warmup", type=float, default=8.0,
                    help="seconds of listening before the sound starts")
    ap.add_argument("--sound-seconds", type=float, default=14.0)
    ap.add_argument("--label", default="")
    args = ap.parse_args()

    import serial

    label = args.label or time.strftime("%H:%M:%S")
    print(f"=== burst measurement: {label}")

    ser = serial.Serial(args.port, 115200, timeout=0.3)
    # The hub prints its banner only at boot; reset it so the log is
    # complete and the radio starts from a known state.
    ser.dtr = False
    ser.rts = True
    time.sleep(0.15)
    ser.rts = False

    lines: list[str] = []

    def reader():
        end = time.time() + args.seconds
        while time.time() < end:
            try:
                raw = ser.readline()
            except Exception:
                break
            if raw:
                lines.append(raw.decode("utf-8", "replace").rstrip())

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    time.sleep(args.warmup)
    player = threading.Thread(target=play_cry,
                              args=(CRY_WAV, args.sound_seconds), daemon=True)
    player.start()
    player.join()
    time.sleep(max(args.seconds - args.warmup - args.sound_seconds, 5.0))
    t.join(timeout=3.0)
    try:
        ser.close()
    except Exception:
        pass

    bursts = []
    asks = 0
    for line in lines:
        m = BURST_RE.search(line)
        if m:
            bursts.append((int(m.group(1)), int(m.group(2)), int(m.group(3)),
                           float(m.group(4))))
        if ASK_RE.search(line):
            asks += 1
        if any(k in line.lower() for k in
               ("missing", "stalled", "timed out", "resend", "bad crc")):
            print("  !", line)

    print(f"\nwindows asked for: {asks}")
    if not bursts:
        print("no burst completed - the sound never crossed the trigger")
        for line in lines[-25:]:
            print("  ", line)
        return 1

    print(f"\nbursts completed: {len(bursts)}")
    for node, have, want, secs in bursts:
        print(f"  node {node}: {have}/{want} fragments in {secs:.2f} s")
    times = [b[3] for b in bursts]
    times_sorted = sorted(times)
    print(f"\nburst time: min {min(times):.2f} s  "
          f"median {times_sorted[len(times) // 2]:.2f} s  max {max(times):.2f} s")
    print(f"fragments complete: {sum(1 for b in bursts if b[1] == b[2])}/"
          f"{len(bursts)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
