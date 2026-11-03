#!/usr/bin/env python3
"""Play a cry, then dump node 3's own frozen window and score it.

The hub's log says *that* a window was judged a cry.  This says *what
was in it*: the node's frozen window is read back over its own USB
console, exactly as the node would have sent it, and the deployed INT8
model scores it on the host.

Two things are compared:
  * the host's score for the node's window
  * the hub's score for the window it reassembled from the air

If they agree, the node's microphone path and the radio transfer are
faithful and any "no cry" is the acoustic source, not the link.  If the
host's score is much higher, the link is losing something.
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
OUT = ROOT / "research" / "out"


def play(path: Path, times: int, gap: float) -> None:
    import winsound

    blob = path.read_bytes()
    for _ in range(times):
        winsound.PlaySound(blob, winsound.SND_MEMORY)
        time.sleep(gap)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", default=str(
        ROOT / "research" / "in_domain" / "session9" / "clips" / "clip_0000.wav"))
    ap.add_argument("--node-port", default="COM38")
    ap.add_argument("--hub-port", default="COM32")
    ap.add_argument("--times", type=int, default=3)
    ap.add_argument("--gap", type=float, default=3.0)
    args = ap.parse_args()

    import serial

    OUT.mkdir(parents=True, exist_ok=True)
    hub = serial.Serial(args.hub_port, 115200, timeout=0.2)
    time.sleep(0.2)
    hub.reset_input_buffer()
    hub_lines: list[str] = []
    stop = threading.Event()

    def reader():
        buf = b""
        while not stop.is_set():
            chunk = hub.read(hub.in_waiting or 1)
            if chunk:
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for ln in lines:
                    hub_lines.append(ln.decode("utf-8", "replace").rstrip())

    th = threading.Thread(target=reader, daemon=True)
    th.start()

    print("playing the cry...", flush=True)
    play(Path(args.clip), args.times, args.gap)
    time.sleep(1.0)
    print("dumping node 3's frozen window...", flush=True)

    dump = subprocess.run(
        [sys.executable, str(ROOT / "firmware" / "tools" / "dump_node_window.py"),
         "--port", args.node_port,
         "--out", str(OUT / "node3_cry_window.wav")],
        capture_output=True, text=True, timeout=120)
    print(dump.stdout)
    if dump.stderr.strip():
        print(dump.stderr, file=sys.stderr)

    time.sleep(2.0)
    stop.set()
    th.join(timeout=2)
    hub.close()

    (OUT / "hub_during_cry.log").write_text("\n".join(hub_lines) + "\n",
                                             encoding="utf-8")

    print("--- the hub's own log for the same period ---")
    for ln in hub_lines:
        if ("node 3" in ln) and ("P(cry)" in ln or "window rms" in ln
                                 or "asking for" in ln or "fragments in" in ln
                                 or "ALERT" in ln):
            print("   ", ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())
