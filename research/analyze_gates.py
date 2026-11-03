#!/usr/bin/env python3
"""Which gate is stopping the hub from pulling a cot's window?

The hub pulls a window when six conditions all hold at once.  This reads
the hub's log and, for every *distinct* window a cot offered, works out
which condition was the one that failed.  The answer is the difference
between "the radio was busy" and "the hub never wanted this window".
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

TEL = re.compile(
    r"node (\d+): rms ([\d.]+)\s+seq (\d+)\s+flags 0x([0-9A-F]+)\s+crc 0x([0-9A-F]+)"
    r"\s+level ([\d.]+)\s+streak (\d+)\s+win ([\d.]+)")
PULL = re.compile(r"node (\d+): asking for the window \(seq (\d+)")
WINDOW = re.compile(r"node (\d+): window rms ([\d.]+)\s+mean (-?\d+)\s+peak (\d+)\s+crest ([\d.]+)")

FLAG_BURST_READY = 0x01
FLAG_EVENT = 0x02
FLAG_WINDOW_FULL = 0x04

PULL_GATE = 0.8 * 0.020     # worth_pulling
ANNOUNCE_MIN = 0.020        # CRYNET_MAYBE_MIN_RMS
QUIET_CREST = 3.5           # CRYNET_QUIET_CREST


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/hub_now.log")
    text = path.read_text(errors="replace")

    # The last telemetry line for each (node, seq) — that is the state
    # the cot was actually offering when the hub decided.
    offered: dict[tuple[int, int], dict] = {}
    order: list[tuple[int, int]] = []
    pulled: set[tuple[int, int]] = set()
    windows: dict[tuple[int, int], dict] = {}

    for line in text.splitlines():
        m = TEL.search(line)
        if m:
            key = (int(m.group(1)), int(m.group(3)))
            if key not in offered:
                order.append(key)
            offered[key] = {
                "rms": float(m.group(2)), "flags": int(m.group(4), 16),
                "level": float(m.group(6)), "streak": int(m.group(7)),
                "win": float(m.group(8)),
            }
            continue
        m = PULL.search(line)
        if m:
            pulled.add((int(m.group(1)), int(m.group(2))))
            continue
        m = WINDOW.search(line)
        if m:
            windows[(int(m.group(1)), 0)] = {
                "rms": float(m.group(2)), "crest": float(m.group(5))}

    print(f"{path}")
    print(f"distinct windows offered: {len(offered)}   pulled: {len(pulled)}")
    print()

    blockers = Counter()
    for key in order:
        if key in pulled:
            blockers["pulled"] += 1
            continue
        o = offered[key]
        why = []
        if not (o["flags"] & FLAG_BURST_READY):
            why.append("no frozen window")
        if not (o["flags"] & FLAG_WINDOW_FULL):
            why.append("live window incomplete")
        if o["win"] < PULL_GATE:
            why.append(f"frozen level {o['win']:.4f} < {PULL_GATE:.3f}")
        if not ((o["streak"] >= 2) or (o["rms"] >= 3.0 * o["level"])):
            why.append("not live-loud")
        blockers[", ".join(why) or "eligible (radio busy or starved)"] += 1

    print("why each offered window was not pulled:")
    for why, n in blockers.most_common():
        print(f"  {n:5d}  {why}")
    print()

    # The waste: windows the hub DID pull that the announce rule could
    # never have announced.
    pulled_keys = [k for k in order if k in pulled]
    print(f"the pull gate is {PULL_GATE:.3f}; a window needs {ANNOUNCE_MIN:.3f} rms")
    print(f"(or crest {QUIET_CREST}) to be announced:")
    waste = [k for k in pulled_keys if offered[k]["win"] < ANNOUNCE_MIN]
    print(f"  windows pulled below the announce floor: {len(waste)} of {len(pulled_keys)}")
    for k in waste:
        print(f"    node {k[0]} seq {k[1]}: frozen level {offered[k]['win']:.4f}")
    print()

    # What the hub actually measured on the wire.
    print("the window as the hub measured it:")
    for (node, _), w in windows.items():
        announce = (w["rms"] >= ANNOUNCE_MIN) or (w["crest"] >= QUIET_CREST)
        print(f"  node {node}: rms {w['rms']:.4f}  crest {w['crest']:.1f}  "
              f"-> {'announceable' if announce else 'REFUSED (too quiet)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
