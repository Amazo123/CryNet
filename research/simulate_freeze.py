#!/usr/bin/env python3
"""What the deployed pipeline does with the AFTER-PEAK freeze.

The corpus was screened once (research/screen_clips.py) with every 2 s
position of every clip treated as a candidate window.  That was fair
before the freeze rule changed; it is not fair now, because the node no
longer hands over an arbitrary window -- it freezes *the two seconds
after the peak* (PEAK_DELAY_MS 500 -> 2000) and the hub announces
whatever window arrives.

So this script simulates the real chain over the corpus:

  1. the node's own 100 ms records over the continuous session
     recording (mean of the 2 s window, rms of the newest 100 ms around
     that mean, the adaptive floor and level, the loud streak);
  2. the freeze rule -- a window is frozen two seconds after the loud
     streak began (the old rule: half a second after, which put the
     peak in the middle of the window);
  3. the hub's announcement gates on the window that arrives: the
     silence gate, the audible floor, the loud rule (a window from
     0.08 rms may announce on P(cry) >= 0.95), the quiet saturation
     requirement (P(cry) >= 0.99) and the crest/level condition;
  4. the labels: every freeze is marked by whether the window it froze
     lands on a cry clip or on a room clip of that session (the clip
     offsets are recovered by matching the clips against the session
     waveform).

Both rules are run, so the fix can be judged against what it replaced.

Output:
    research/out/freeze_simulation.csv    one row per frozen window
    research/out/freeze_simulation.md     the summary

Usage:
    python research/simulate_freeze.py
"""

from __future__ import annotations

import csv
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
CLIPS = ROOT / "research" / "in_domain"
sys.path.insert(0, str(ROOT / "research"))

from screen_clips import build_scorer  # noqa: E402

# --- the firmware's constants (firmware/node/node_crynet/node_crynet.ino
# --- and firmware/hub_infer/src/link_stage.h)
SR = 16000
WINDOW_SAMPLES = 32000        # the node's 2 s window
RMS_SAMPLES = 1600            # one 100 ms record
TELEMETRY_MS = 100
TRIGGER_MULT = 3.0
TRIGGER_MIN = 0.005
TRIGGER_MAX = 0.030
FLOOR_RISE = 0.002
PEAK_DELAY_NEW_MS = 2000      # the rule now on the boards
PEAK_DELAY_OLD_MS = 500       # the rule it replaced
PEAK_EXPIRE_MS = 4000
CLEAR_CRY_MS = 0.010          # the room goes quiet below this
PREEMPT_FACTOR = 3.0

CRYNET_THRESHOLD = 0.95
CRYNET_CLEAR_CRY = 0.99
CRYNET_ANNOUNCE_MIN_RMS = 0.006
CRYNET_MAYBE_MIN_RMS = 0.020
CRYNET_LOUD_ANNOUNCE_RMS = 0.080
CRYNET_QUIET_CREST = 3.5
CRYNET_SILENCE_RMS_GATE = 0.0015
CRYNET_CRY_RUN = 2


def read_pcm(path: Path) -> np.ndarray:
    """A tolerant 16 kHz mono 16-bit reader.

    The session recordings were written by a streaming writer, so their
    RIFF and data chunk sizes are zero -- python's wave module refuses
    them.  The chunks are walked by hand instead.
    """
    raw = path.read_bytes()
    if raw[0:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a WAVE file")
    off = 12
    fmt = None
    data = None
    while off + 8 <= len(raw):
        cid = raw[off:off + 4]
        size = int.from_bytes(raw[off + 4:off + 8], "little")
        body = off + 8
        if cid == b"fmt ":
            fmt = struct.unpack("<HHIIHH", raw[body:body + 16])
        elif cid == b"data":
            end = len(raw) if size == 0 else min(body + size, len(raw))
            data = raw[body:end]
            if size != 0:
                off = body + size + (size & 1)
                continue
        off = body + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError(f"{path}: no fmt/data chunk")
    audio_format, ch, rate, _br, _al, bits = fmt
    if rate != SR or ch != 1 or bits != 16 or audio_format != 1:
        raise ValueError(f"{path}: {rate} Hz, {ch} ch, {bits} bit")
    return np.frombuffer(data, dtype="<i2")


def find_offset(session: np.ndarray, clip: np.ndarray) -> int | None:
    """Where the clip sits in the session, by exact sample match."""
    if len(clip) > len(session):
        return None
    probe = clip[:64].tobytes()
    # candidates: places where the first 64 samples could start
    first = clip[0]
    cand = np.where(session[: len(session) - 64] == first)[0]
    for off in cand:
        if not np.array_equal(session[off:off + 64], clip[:64]):
            continue
        # confirm with a sample from the middle of the clip
        mid = len(clip) // 2
        if (mid + 32 <= len(clip) and mid + 32 <= len(session) - off
                and np.array_equal(session[off + mid:off + mid + 32],
                                   clip[mid:mid + 32])):
            return int(off)
    return None


def node_records(sess: np.ndarray):
    """The node's 100 ms records: rms of the newest 100 ms around the
    mean of the whole 2 s window, the adaptive floor and level, and the
    loud streak.  Yields (t_ms, rms, level, streak)."""
    x = sess.astype(np.float64)
    csum = np.concatenate([[0.0], np.cumsum(x)])
    floor = -1.0
    level = 0.006
    streak = 0
    for k in range(RMS_SAMPLES, len(x), RMS_SAMPLES):
        end = k                       # samples [k-RMS_SAMPLES, k) are new
        win_lo = max(0, end - WINDOW_SAMPLES)
        n_win = end - win_lo
        if n_win < RMS_SAMPLES:
            continue
        mean = (csum[end] - csum[win_lo]) / n_win
        lo = end - RMS_SAMPLES
        seg = x[lo:end] - mean
        rms = float(np.sqrt((seg ** 2).mean()) / 32768.0)
        if floor < 0.0:
            floor = rms
        elif rms < floor:
            floor = rms
        else:
            floor += (rms - floor) * FLOOR_RISE
        level = min(max(TRIGGER_MULT * floor, TRIGGER_MIN), TRIGGER_MAX)
        if rms >= level:
            streak += 1
        else:
            streak = 0
        t_ms = (end / SR) * 1000.0
        yield t_ms, end, rms, level, streak


def freeze_events(records, mode: str, state: dict):
    """The freezes the node would make: a window is frozen `delay_ms`
    after the loud streak began, and the window is the last 2 s.

    Mirrors the firmware: the peak marker survives the streak dropping
    (so the freeze still fires two seconds later, on silence), the live
    window must refill for two seconds after the hub pulls the last one,
    and a loud window puts the node into cry mode -- it may not freeze
    again until the room goes quiet, unless a much louder event
    preempts it.

    `state` carries what the caller learns after scoring a window (its
    rms), because the firmware only knows it once the window is read.
    """
    peak_pending = False
    peak_ms = 0.0
    refill_until = 0.0
    delay_ms = PEAK_DELAY_NEW_MS if mode in ("new", "hybrid") else PEAK_DELAY_OLD_MS

    for t_ms, end, rms, level, streak in records:
        if state["cry_mode"] and rms < CLEAR_CRY_MS and streak == 0:
            state["cry_mode"] = False
        frozen_rms = state["frozen_rms"]
        if (state["frozen_served"] and frozen_rms > 0.0
                and rms >= PREEMPT_FACTOR * frozen_rms and streak >= 2):
            state["frozen_served"] = False
        allow_freeze = (not state["cry_mode"]) or (
            frozen_rms > 0.0 and rms >= PREEMPT_FACTOR * frozen_rms)
        if not allow_freeze or t_ms < refill_until:
            continue
        if not peak_pending:
            if streak < 2:
                continue
            peak_pending = True
            peak_ms = t_ms
            continue
        age = t_ms - peak_ms
        # The hybrid rule: freeze when the cry STOPS (the streak broke),
        # or two seconds after the peak, whichever comes first -- so a
        # short yelp is caught whole, and a sustained cry gets the two
        # seconds that follow its peak.
        stop = (mode == "hybrid" and streak < 2 and age >= PEAK_DELAY_OLD_MS)
        if age >= delay_ms or stop:
            if age < PEAK_EXPIRE_MS:
                yield {
                    "t_ms": t_ms,
                    "end": end,
                    "peak_ms": peak_ms,
                    "live_rms": rms,
                    "level": level,
                }
                # the hub pulls it at once; the live window drops and
                # refills over the next two seconds
                state["frozen_served"] = False
                refill_until = t_ms + 2000.0
            peak_pending = False


def window_stats(x: np.ndarray):
    """The hub's view of a window: rms, peak (counts), crest."""
    mean = x.mean()
    centred = x - mean
    rms = float(np.sqrt((centred ** 2).mean()) / 32768.0)
    peak = int(np.abs(centred).max())
    crest = (peak / 32768.0) / rms if rms > 0 else 0.0
    return rms, peak, crest, float(mean)


def hub_decision(rms: float, crest: float, p_cry: float) -> tuple[bool, bool]:
    """(announces on its own, is a maybe) -- the hub's rule."""
    if rms < CRYNET_SILENCE_RMS_GATE:
        return False, False
    audible = rms >= CRYNET_ANNOUNCE_MIN_RMS
    if not audible:
        return False, False
    unmistakable = (
        (rms >= CRYNET_LOUD_ANNOUNCE_RMS and p_cry >= CRYNET_THRESHOLD)
        or (rms < CRYNET_LOUD_ANNOUNCE_RMS and p_cry >= CRYNET_CLEAR_CRY)
    ) and (rms >= CRYNET_MAYBE_MIN_RMS or crest >= CRYNET_QUIET_CREST)
    if unmistakable:
        return True, False
    maybe = (p_cry >= CRYNET_THRESHOLD) and (rms >= CRYNET_MAYBE_MIN_RMS)
    return False, bool(maybe)


def main() -> int:
    score = build_scorer()
    sessions = sorted(p for p in CLIPS.glob("session*") if p.is_dir())
    rows = []

    for session in sessions:
        wav = session / "session.wav"
        if not wav.exists():
            continue
        sess = read_pcm(wav)
        # where the labelled clips sit in the session
        ranges = []
        lab = session / "clips_labeled"
        if lab.is_dir():
            for clip in sorted(lab.glob("*.wav")):
                cw = read_pcm(clip)
                off = find_offset(sess, cw)
                if off is None:
                    continue
                kind = "room" if clip.name.startswith("room_clip") else "cry"
                ranges.append((off, off + len(cw), kind, clip.name))
        print(f"{session.name}: {len(sess) / SR:.0f} s, {len(ranges)} labelled clips",
              file=sys.stderr)

        records = list(node_records(sess))
        for name in ("new", "hybrid", "old"):
            state = {"frozen_served": False, "frozen_rms": 0.0, "cry_mode": False}
            for ev in freeze_events(records, name, state):
                end = ev["end"]
                lo = max(0, end - WINDOW_SAMPLES)
                win = sess[lo:end]
                if len(win) < WINDOW_SAMPLES:
                    continue
                rms, peak, crest, _ = window_stats(win)
                # what the firmware learns once the window is frozen
                state["frozen_rms"] = rms
                state["frozen_served"] = True
                if rms >= 0.05:
                    state["cry_mode"] = True
                p = score(win.astype(np.float32) / 32768.0)
                announces, maybe = hub_decision(rms, crest, p)
                label = "unlabelled"
                clip_name = ""
                for a, b, kind, nm in ranges:
                    if not (end <= a or lo >= b):
                        label = kind
                        clip_name = nm
                        break
                rows.append({
                    "session": session.name,
                    "rule": name,
                    "t_sec": round(ev["t_ms"] / 1000.0, 2),
                    "peak_at_sec": round(ev["peak_ms"] / 1000.0, 2),
                    "label": label,
                    "clip": clip_name,
                    "rms": round(rms, 6),
                    "peak": peak,
                    "crest": round(crest, 2),
                    "p_cry": round(p, 4),
                    "announce": int(announces),
                    "maybe": int(maybe),
                })

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "freeze_simulation.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- the summary
    lines = ["# The after-peak freeze, simulated over the corpus", ""]
    lines.append("Every frozen window the node would hand over, scored with the "
                 "deployed INT8 model and put through the hub's gates.")
    lines.append("")
    lines.append("| rule | label | windows | announced | rate | loudest P | "
                 "worst rms |")
    lines.append("|---|---|---|---|---|---|---|")
    for rule in ("new", "hybrid", "old"):
        for label in ("cry", "room", "unlabelled"):
            sel = [r for r in rows if r["rule"] == rule and r["label"] == label]
            if not sel:
                continue
            ann = sum(r["announce"] for r in sel)
            best = max(r["p_cry"] for r in sel)
            worst = max(r["rms"] for r in sel)
            lines.append(f"| {rule} | {label} | {len(sel)} | {ann} | "
                         f"{100.0 * ann / len(sel):.1f} % | {best:.4f} | {worst:.4f} |")
    lines.append("")
    lines.append("## Episode level: did the cot that heard the cry say so?")
    lines.append("")
    lines.append("For every cry clip (one cry = one episode) the window the node "
                 "freezes first over that clip is the one that decides the alert.")
    lines.append("")
    lines.append("| rule | cry episodes | first window announced | none announced | "
                 "no window at all |")
    lines.append("|---|---|---|---|---|")
    for rule in ("new", "hybrid", "old"):
        sel = [r for r in rows if r["rule"] == rule and r["label"] == "cry"]
        episodes = {}
        for r in sel:
            key = (r["session"], r["clip"])
            if key not in episodes or r["t_sec"] < episodes[key]["t_sec"]:
                episodes[key] = r
        # every labelled cry clip is an episode, even one with no window
        all_eps = set()
        for r in rows:
            if r["rule"] == rule and r["label"] == "cry":
                all_eps.add((r["session"], r["clip"]))
        missing = set()
        for sess_dir in sessions:
            lab = sess_dir / "clips_labeled"
            if not lab.is_dir():
                continue
            for clip in sorted(lab.glob("clip_*.wav")):
                if find_offset(read_pcm(sess_dir / "session.wav"), read_pcm(clip)) is not None:
                    missing.add((sess_dir.name, clip.name))
        eps = set(missing) | set(episodes)
        first_ann = sum(1 for k in eps
                        if k in episodes and episodes[k]["announce"])
        no_win = len([k for k in eps if k not in episodes])
        lines.append(f"| {rule} | {len(eps)} | {first_ann} | "
                     f"{len(eps) - first_ann - no_win} | {no_win} |")
    lines.append("")
    # the false-alarm question, stated plainly
    for rule in ("new", "hybrid", "old"):
        room = [r for r in rows if r["rule"] == rule and r["label"] == "room"]
        cry = [r for r in rows if r["rule"] == rule and r["label"] == "cry"]
        rann = sum(r["announce"] for r in room)
        cann = sum(r["announce"] for r in cry)
        loud_room = [r for r in room if r["rms"] >= CRYNET_LOUD_ANNOUNCE_RMS]
        lines.append(f"**{rule} rule:** {rann} of {len(room)} room windows announced "
                     f"({len(loud_room)} of those room windows were loud enough for the "
                     f"0.95 rule); {cann} of {len(cry)} cry windows announced.")
        lines.append("")
    (OUT / "freeze_simulation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nwrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
