#!/usr/bin/env python3
"""Play a recorded cry near node 3 and time the whole chain.

Three things are watched at once:
  * the hub's log  -- when it asked for the window, when the burst
                     landed, and what the model said
  * node 3's log  -- when it heard the cry, when it froze a window
  * the clock      -- the cry starts at a known instant

The cry is played from a clip recorded on a phone, so the sound is the
real thing rather than a sine wave.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUB_RE = re.compile(r"^I \((\d+)\) (\w+): (.*)$")
NODE_MARKERS = ("froze window", "request: seq", "served ", "resent ", "resend request")


def play_wav(path: Path, times: int, gap: float) -> list[float]:
    """Play the clip `times` times; return the start times."""
    import winsound

    # PlaySound wants a whole WAV file, header and all.
    blob = path.read_bytes()
    with wave.open(str(path)) as w:
        assert w.getsampwidth() == 2 and w.getnchannels() == 1

    starts = []
    for _ in range(times):
        winsound.PlaySound(blob, winsound.SND_MEMORY | winsound.SND_SYNC)
        starts.append(time.time())
        time.sleep(gap)
    return starts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default=str(
        ROOT / "research" / "in_domain" / "session9" / "clips" / "clip_0000.wav"))
    ap.add_argument("--hub-port", default="COM32")
    ap.add_argument("--node-port", default="COM38")
    ap.add_argument("--times", type=int, default=3)
    ap.add_argument("--gap", type=float, default=6.0)
    ap.add_argument("--lead", type=float, default=4.0)
    ap.add_argument("--tail", type=float, default=8.0)
    args = ap.parse_args()

    import serial

    hub = serial.Serial(args.hub_port, 115200, timeout=0.2)
    node = serial.Serial(args.node_port, 115200, timeout=0.2)
    time.sleep(0.3)
    hub.reset_input_buffer()
    node.reset_input_buffer()

    hub_lines: list[tuple[float, str]] = []
    node_lines: list[tuple[float, str]] = []
    stop = threading.Event()

    def reader(port, sink, tag):
        buf = b""
        while not stop.is_set():
            try:
                chunk = port.read(port.in_waiting or 1)
            except Exception:
                break
            if chunk:
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    sink.append((time.time(), ln.decode("utf-8", "replace").rstrip()))

    th = threading.Thread(target=reader, args=(hub, hub_lines, "hub"), daemon=True)
    tn = threading.Thread(target=reader, args=(node, node_lines, "node"), daemon=True)
    th.start()
    tn.start()

    time.sleep(args.lead)
    starts = play_wav(Path(args.clip), args.times, args.gap)
    time.sleep(args.tail)
    stop.set()
    th.join(timeout=2)
    tn.join(timeout=2)
    hub.close()
    node.close()

    out = ROOT / "research" / "out" / "cry_test_node3.log"
    out.parent.mkdir(parents=True, exist_ok=True)

    with out.open("w", encoding="utf-8") as fh:
        fh.write("=== the cry was played at these wall-clock instants ===\n")
        for s in starts:
            fh.write(f"  {s:.3f}\n")
        fh.write("\n=== node 3 ===\n")
        t0 = node_lines[0][0] if node_lines else time.time()
        for t, ln in node_lines:
            if any(m in ln for m in NODE_MARKERS):
                fh.write(f"  [{t - t0:7.2f}s] {ln}\n")
        fh.write("\n=== the hub ===\n")
        h0 = hub_lines[0][0] if hub_lines else time.time()
        for t, ln in hub_lines:
            if ("node 3" in ln or "node 2" in ln or "node 1" in ln) and (
                    "asking for" in ln or "fragments in" in ln or "P(cry)" in ln
                    or "ALERT" in ln or "cry (" in ln or "no cry" in ln
                    or "stalled" in ln):
                fh.write(f"  [{t - h0:7.2f}s] {ln}\n")

    print(out)
    for s in starts:
        print(f"played at {s:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
