#!/usr/bin/env python3
"""A dry run of the demonstration day, with no sound.

What the demonstration will do is play a *sustained* cry from a phone
and expect the hub to name the cot.  The demo kit (research/out/demo_kit)
is the set of clips that were trimmed so that the first two seconds of
the clip already reach P(cry) >= 0.99 -- but that promise was measured
under the OLD freeze rule, the one that put the peak in the middle of
the window.  The node on the bench now runs the hybrid stop-capped rule,
so the kit's scores have to be derived again before they can be trusted
on the day.

This script derives them, the way the firmware actually works:

  1. a real quiet room (a stretch of the recorded quiet-room session)
     with the clip played into it at a given gain;
  2. the node's own 100 ms records over that: the mean of the two-second
     window, the rms of the newest 100 ms around it, the adaptive floor,
     the event level, the loud streak;
  3. the hybrid stop-capped freeze, exactly as the sketch writes it --
     and EVERY freeze, not just the first, because the room itself can
     freeze a window before the clip has even started;
  4. the window the node would hand the hub, scored with the deployed
     INT8 model;
  5. the hub's gates, including the refusal of a clipped window.

The gain sweep answers the question the demo depends on: the phone has
to be loud enough for the cry to cross the trigger and reach the
announce floor, and not so loud that the microphone's fixed gain
saturates -- a clipped window is now refused rather than trusted.

Output:
    research/out/demo_rehearsal.md    the table for the demonstration
    research/out/demo_rehearsal.csv   the same, one row per clip and gain

Usage:
    python research/simulate_demo.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
KIT = OUT / "demo_kit"
CLIPS = ROOT / "research" / "in_domain"

sys.path.insert(0, str(ROOT / "research"))
from screen_clips import build_scorer          # noqa: E402
from simulate_freeze import (                   # noqa: E402
    SR, WINDOW_SAMPLES, read_pcm, node_records, freeze_events, window_stats,
    CRYNET_CLIP_PEAK,
)

# The hub's gates, as firmware/hub_infer/src/link_stage.h has them.
CRYNET_SILENCE_RMS_GATE = 0.0015
CRYNET_ANNOUNCE_MIN_RMS = 0.006
CRYNET_MAYBE_MIN_RMS = 0.020
CRYNET_LOUD_ANNOUNCE_RMS = 0.080
CRYNET_LOUD_ANNOUNCE_P = 0.9900
CRYNET_CLEAR_CRY = 0.9900
CRYNET_CONFIRM_P = 0.9900
CRYNET_QUIET_CREST = 3.5

# The gains the phone is turned through: the level the clip was recorded
# at, and louder.
GAINS = (1.0, 1.5, 2.0)

# Where the clip is played into the room, and how long the room runs.
PLAY_AT_SEC = 8.0
BED_SEC = 20.0


def hub_decision(rms: float, crest: float, peak: int, p_cry: float):
    """(announces, refused, maybe) -- the hub's rule, as flashed."""
    if peak >= CRYNET_CLIP_PEAK:
        return False, True, False
    if rms < CRYNET_SILENCE_RMS_GATE or rms < CRYNET_ANNOUNCE_MIN_RMS:
        return False, False, False
    unmistakable = (
        (rms >= CRYNET_LOUD_ANNOUNCE_RMS and p_cry >= CRYNET_LOUD_ANNOUNCE_P)
        or (rms < CRYNET_LOUD_ANNOUNCE_RMS and p_cry >= CRYNET_CLEAR_CRY)
    ) and (rms >= CRYNET_MAYBE_MIN_RMS or crest >= CRYNET_QUIET_CREST)
    if unmistakable:
        return True, False, False
    maybe = p_cry >= CRYNET_CONFIRM_P and rms >= CRYNET_MAYBE_MIN_RMS
    return False, False, bool(maybe)


def quiet_bed(seconds: float) -> np.ndarray:
    """The quietest stretch of the recorded quiet room.

    The room's own drift is kept: the node sees it, and the demo will
    happen in a room that drifts too.
    """
    wav = CLIPS / "session5" / "session.wav"
    x = read_pcm(wav).astype(np.float64)
    need = int(seconds * SR)
    if len(x) <= need:
        return x.astype(np.int16)
    # The node's own measure: the rms of each 100 ms around the mean of
    # the two-second window.  The quietest stretch is the one whose
    # loudest such reading is lowest.
    best, best_i = None, 0
    step = SR // 10
    win = 20 * step
    for i in range(0, len(x) - need, step):
        seg = x[i:i + need]
        m = seg.mean()
        r = float(np.sqrt(((seg[i:i + win] - m) ** 2).mean()) / 32768.0)
        if best is None or r < best:
            best, best_i = r, i
    return x[best_i:best_i + need].astype(np.int16)


def play(room: np.ndarray, clip: np.ndarray, gain: float, at_sec: float):
    out = room.astype(np.float64).copy()
    start = int(at_sec * SR)
    played = np.clip(clip.astype(np.float64) * gain, -32768.0, 32767.0)
    end = min(len(out), start + len(played))
    out[start:end] += played[: end - start]
    return np.clip(out, -32768.0, 32767.0).astype(np.int16)


def main() -> int:
    score = build_scorer()
    room = quiet_bed(BED_SEC)
    clips = sorted(KIT.glob("*.wav"))
    if not clips:
        print("no demo kit clips", file=sys.stderr)
        return 1

    rows = []
    for path in clips:
        clip = read_pcm(path)
        clip_end = PLAY_AT_SEC + len(clip) / SR
        for gain in GAINS:
            signal = play(room, clip, gain, at_sec=PLAY_AT_SEC)
            state = {"frozen_served": False, "frozen_rms": 0.0, "cry_mode": False}
            events = list(freeze_events(node_records(signal), "hybrid", state))

            # Only the freezes whose window overlaps the clip are the
            # ones the clip caused; the room freezes windows of its own.
            rows_for_clip = []
            for ev in events:
                end = ev["end"]
                lo = max(0, end - WINDOW_SAMPLES)
                win = signal[lo:end]
                if len(win) < WINDOW_SAMPLES:
                    continue
                win_end_sec = end / SR
                if win_end_sec < PLAY_AT_SEC - 0.5 or lo / SR > clip_end:
                    continue
                rms, peak, crest, _ = window_stats(win)
                p = score(win.astype(np.float32) / 32768.0)
                announces, refused, maybe = hub_decision(rms, crest, peak, p)
                if refused:
                    verdict = "CLIPPED (refused)"
                elif announces:
                    verdict = "ANNOUNCES"
                elif maybe:
                    verdict = "maybe (needs a second window)"
                else:
                    verdict = "no cry"
                rows_for_clip.append({
                    "clip": path.name,
                    "gain": gain,
                    "t_sec": round(win_end_sec, 2),
                    "rms": round(rms, 4),
                    "peak": peak,
                    "crest": round(crest, 2),
                    "p_cry": round(p, 4),
                    "verdict": verdict,
                    "latency_s": round(win_end_sec - PLAY_AT_SEC, 2),
                })

            if not rows_for_clip:
                rows.append({
                    "clip": path.name, "gain": gain, "t_sec": "", "rms": "",
                    "peak": "", "crest": "", "p_cry": "",
                    "verdict": "no window frozen over the clip",
                    "latency_s": "",
                })
            else:
                rows.extend(rows_for_clip)

    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["clip", "gain", "t_sec", "rms", "peak", "crest", "p_cry",
              "verdict", "latency_s"]
    with (OUT / "demo_rehearsal.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = ["# The demonstration, dry run", ""]
    lines.append("Every clip in the demo kit, played into a quiet room by "
                 "the node's own trigger, frozen by the hybrid stop-capped "
                 "rule that is flashed on the bench, and judged by the "
                 "deployed INT8 model and the hub's gates -- with no sound "
                 "anywhere.")
    lines.append("")
    lines.append("`gain` is the phone's volume: 1.0 is the level the clip "
                 "was recorded at, 1.5 and 2.0 are louder.  Only the "
                 "freezes whose window overlaps the clip are listed; the "
                 "room freezes windows of its own, and those are not what "
                 "the demonstration is waiting for.")
    lines.append("")
    lines.append("| clip | gain | frozen at | rms | peak | crest | P(cry) | verdict | after the clip started |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        lines.append(
            f"| {r['clip']} | {r['gain']} | "
            f"{r['t_sec'] if r['t_sec'] != '' else '--'} | "
            f"{r['rms'] if r['rms'] != '' else '--'} | "
            f"{r['peak'] if r['peak'] != '' else '--'} | "
            f"{r['crest'] if r['crest'] != '' else '--'} | "
            f"{r['p_cry'] if r['p_cry'] != '' else '--'} | "
            f"**{r['verdict']}** | "
            f"{r['latency_s'] if r['latency_s'] != '' else '--'} |")

    # Per clip, at the recorded level, the verdict that matters.
    summary = []
    for path in clips:
        rs = [r for r in rows if r["clip"] == path.name and r["gain"] == 1.0]
        best = None
        for r in rs:
            if r["verdict"] == "ANNOUNCES":
                best = r
                break
        summary.append((path.name, best, rs))

    good = [n for n, b, _ in summary if b]
    bad = [(n, rs) for n, b, rs in summary if not b]

    lines.append("")
    lines.append(f"## At the recorded level: **{len(good)} of {len(clips)} "
                 f"clips announce** under the rule that is on the boards.")
    if bad:
        lines.append("")
        lines.append("The clips that do not:")
        lines.append("")
        for n, rs in bad:
            for r in rs:
                lines.append(f"- `{n}` — {r['verdict']} "
                             f"(rms {r['rms']}, peak {r['peak']}, "
                             f"P {r['p_cry']})")
    lines.append("")
    lines.append("## The gain sweep")
    lines.append("")
    lines.append("| clip | 1.0 | 1.5 | 2.0 |")
    lines.append("|---|---|---|---|")
    for path in clips:
        cells = []
        for g in GAINS:
            rs = [r for r in rows if r["clip"] == path.name and r["gain"] == g]
            if not rs:
                cells.append("no window")
                continue
            if any(r["verdict"] == "ANNOUNCES" for r in rs):
                cells.append("**announces**")
            elif any(r["verdict"].startswith("CLIPPED") for r in rs):
                cells.append("clipped")
            elif any(r["verdict"].startswith("maybe") for r in rs):
                cells.append("maybe")
            else:
                cells.append("no cry")
        lines.append(f"| {path.name} | " + " | ".join(cells) + " |")

    (OUT / "demo_rehearsal.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
