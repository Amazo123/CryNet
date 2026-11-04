#!/usr/bin/env python3
"""Play a clip and grab the node's frozen window the instant it forms.

The hub's log says what the model made of a window; this says what was
*in* it.  The node's console `burst` command writes the frozen two
seconds out over USB, so the window can be scored on the host with the
notebook's own front end and compared with the hub's verdict.

The race to win: the hub asks for the window the moment the node
advertises it, and after that the node has nothing left to dump.  So
the dump is sent as soon as the freeze is due -- the stop-capped rule
freezes about half a second after the sound stops.

Usage:
    python research/dump_during_play.py --clip research/out/short_yelps/yelp_2.0s.wav
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

import serial

ROOT = Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(ROOT / "firmware" / "tools"))
import dump_node_window as d  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clip", required=True)
    ap.add_argument("--port", default="COM31")
    ap.add_argument("--out", default="research/out/yelp_window.wav")
    ap.add_argument("--after", type=float, default=0.8,
                    help="seconds to wait after the clip ends before the dump")
    ap.add_argument("--boot", type=float, default=3.0,
                    help="seconds to let the node boot and fill its window")
    args = ap.parse_args()

    port = serial.Serial(args.port, 115200, timeout=0.2)
    port.reset_input_buffer()
    log = []
    try:
        time.sleep(args.boot)          # the node reboots on the open
        port.reset_input_buffer()

        import winsound
        winsound.PlaySound(str(Path(args.clip).resolve()), winsound.SND_FILENAME)
        print(f"played {args.clip}")
        time.sleep(args.after)

        port.write(b"burst\n")
        port.flush()
        buf = d.read_until(port, b"BURST-END", 20.0)
        # keep whatever the node printed around it
        try:
            while port.in_waiting:
                log.append(port.read(port.in_waiting).decode("utf-8", "replace"))
        except Exception:
            pass
    finally:
        port.close()

    Path(args.out + ".node.log").write_text("".join(log), encoding="utf-8")

    marker = buf.find(b"BURST seq=")
    if marker < 0:
        print("the node did not send a burst (the hub probably took it)",
              file=sys.stderr)
        print(buf[-300:].decode("utf-8", "replace"), file=sys.stderr)
        return 1
    head = buf[marker:marker + 40].decode("utf-8", "replace")
    print(f"node said: {head}")
    frames = d.parse_frames(buf, marker)
    if not frames:
        print("no fragment frames came back", file=sys.stderr)
        return 1
    by_index = {frag: payload for frag, payload in frames}
    count = max(by_index) + 1
    missing = [i for i in range(count) if i not in by_index]
    data = bytearray()
    for i in range(count):
        data += by_index.get(i, b"\x00" * 224)
    if missing:
        print(f"missing fragment(s): {missing} -- filled with silence")
    if len(data) < d.WINDOW_BYTES:
        print("not enough bytes came back", file=sys.stderr)
        return 1

    import numpy as np
    samples = (np.frombuffer(bytes(data[:d.WINDOW_BYTES]), dtype="<i2")
               .astype(np.float32) / 32768.0)
    centred = samples - samples.mean()
    rms = float(np.sqrt((centred ** 2).mean()))
    peak = float(np.abs(samples).max())
    print(f"rms {rms:.6f}  peak {peak:.6f}  crest {peak / rms if rms else 0:.1f}")
    d.spectrum_report(samples)
    d.wave_out(str(Path(args.out).resolve()), samples)
    print(f"wrote {args.out}")
    return d.score(str(Path(args.out).resolve()))


if __name__ == "__main__":
    raise SystemExit(main())
