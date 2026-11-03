#!/usr/bin/env python3
"""Was a cot's frozen window ever left un-pulled while it was loud enough?

The hub pulls a window when the node is *live* loud (a streak of
telemetry readings above the node's own level) and the *frozen* window
is above the pull gate.  Those are two different numbers, measured at
two different times: the live reading is what the room is doing now,
the frozen level is what the window the node is offering contains.

This reads the hub's log and, for every cot, finds every moment where
the frozen window was above the pull gate but the live reading was not
loud.  Those are the moments where a window worth classifying was
sitting on the node with the radio free, and the hub did not ask for
it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# "node 3: rms 0.0150  seq 103  flags 0x06  crc 0x...  level 0.0090  streak 2  win 0.0170"
TEL = re.compile(
    r"node (\d+): rms ([\d.]+)\s+seq (\d+)\s+flags 0x([0-9A-F]+)\s+crc 0x([0-9A-F]+)"
    r"\s+level ([\d.]+)\s+streak (\d+)\s+win ([\d.]+)")
PULL = re.compile(r"node (\d+): asking for the window \(seq (\d+)")
FRAG = re.compile(r"node (\d+): (\d+)/(\d+) fragments in ([\d.]+) s")
VERDICT = re.compile(r"node (\d+): (ALERT — cry|cry \(held\)|cry \(unconfirmed\)|"
                     r"cry \(too quiet to announce\)|no cry|silent)")

PULL_GATE = 0.8 * 0.020     # worth_pulling in link_stage.c
ANNOUNCE_MIN = 0.020        # CRYNET_MAYBE_MIN_RMS


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/hub_now.log")
    text = path.read_text(errors="replace")

    tel: list[dict] = []
    pulls: list[tuple[float, int, int]] = []
    frags: list[tuple[float, int, int, int, float]] = []
    verdicts: list[tuple[float, int, str]] = []

    def ts(line: str) -> float:
        m = re.match(r"^[IW] \((\d+)\)", line)
        return int(m.group(1)) / 1000.0 if m else 0.0

    for line in text.splitlines():
        m = TEL.search(line)
        if m:
            tel.append({
                "t": ts(line), "node": int(m.group(1)),
                "rms": float(m.group(2)), "seq": int(m.group(3)),
                "flags": int(m.group(4), 16), "crc": m.group(5),
                "level": float(m.group(6)), "streak": int(m.group(7)),
                "win": float(m.group(8)),
            })
            continue
        m = PULL.search(line)
        if m:
            pulls.append((ts(line), int(m.group(1)), int(m.group(2))))
            continue
        m = FRAG.search(line)
        if m:
            frags.append((ts(line), int(m.group(1)), int(m.group(2)),
                          int(m.group(3)), float(m.group(4))))
            continue
        m = VERDICT.search(line)
        if m:
            verdicts.append((ts(line), int(m.group(1)), m.group(2)))

    print(f"{path}")
    print(f"  telemetry {len(tel)}  pulls {len(pulls)}  "
          f"bursts {len(frags)}  verdicts {len(verdicts)}")
    print()

    # --- how many pulls did each cot get, and how long did each take? ---
    print("per cot:")
    for node in sorted({t["node"] for t in tel}):
        p = [x for x in pulls if x[1] == node]
        f = [x for x in frags if x[1] == node]
        v = [x for x in verdicts if x[1] == node]
        wins = [t["win"] for t in tel if t["node"] == node]
        above = [w for w in wins if w >= PULL_GATE]
        print(f"  node {node}: {len(p)} pulls, {len(f)} bursts, {len(v)} verdicts")
        print(f"      frozen level: min {min(wins):.4f}  max {max(wins):.4f}  "
              f"above the pull gate ({PULL_GATE:.3f}): {len(above)}/{len(wins)}")
        if f:
            times = sorted(x[4] for x in f)
            print(f"      burst time: {times[0]:.2f}..{times[-1]:.2f} s "
                  f"(mean {sum(times) / len(times):.2f})")
    print()

    # --- the starvation test ---
    # For every telemetry line whose frozen window was above the pull
    # gate, was that sequence number ever pulled?  And was the live
    # reading loud at the time?
    pulled_seqs = {(n, s) for _, n, s in pulls}
    stuck: list[dict] = []
    for t in tel:
        if t["win"] < PULL_GATE:
            continue
        if (t["node"], t["seq"]) in pulled_seqs:
            continue
        live_loud = (t["streak"] >= 2) or (t["rms"] >= 3.0 * t["level"])
        if not live_loud:
            stuck.append(t)

    print(f"windows above the pull gate that were never pulled while the "
          f"live reading was NOT loud: {len(stuck)}")
    for t in stuck[:25]:
        print(f"  t={t['t']:9.3f}s  node {t['node']}  seq {t['seq']}  "
              f"frozen win {t['win']:.4f}  live rms {t['rms']:.4f}  "
              f"level {t['level']:.4f}  streak {t['streak']}")
    print()

    # --- how long from the freeze to the pull, per cot? ---
    print("freeze -> pull, per pull:")
    for t, node, seq in pulls:
        # the telemetry line that advertised this sequence
        ads = [x for x in tel if x["node"] == node and x["seq"] == seq]
        if ads:
            first = ads[0]["t"]
            print(f"  node {node} seq {seq}: advertised at {first:.3f}, "
                  f"pulled at {t:.3f}  (+{t - first:.3f} s)")
    print()

    # --- the announce gate against the pull gate ---
    print(f"the pull gate is {PULL_GATE:.3f} but a window needs "
          f"{ANNOUNCE_MIN:.3f} rms to be announced:")
    between = [t for t in tel
               if PULL_GATE <= t["win"] < ANNOUNCE_MIN
               and (t["node"], t["seq"]) in pulled_seqs]
    print(f"  windows pulled that could never have been announced: {len(between)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
