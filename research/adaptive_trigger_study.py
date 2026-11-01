#!/usr/bin/env python3
"""Choose the adaptive trigger's multiple from the recorded sessions.

The hub's trigger is a fixed RMS level (0.030), and the in-room confusion
session (D-60) found the consequence: a cry played at one metre from the
node reaches a median RMS of 0.0070 and never crosses 0.030, so it is never
offered to the model at all.

The remedy is an adaptive trigger: the hub watches each node's own noise
floor and triggers at a multiple of it.  The multiple is a number, and this
script picks it from the data already on disk rather than by taste.

For every recorded session it reports the RMS distribution, and for a grid
of thresholds it reports how many *trigger events* the fixed rule would
produce - an event being two consecutive readings above the level, which is
what the firmware counts (`loud_streak >= 2`).

The two numbers to compare are:

  * the number of trigger events in a non-cry session (the false alarms the
    model would have been asked about), and
  * the number of trigger events in a cry session (the chances the model
    would have been given the cry at all).

Usage:
    python research/adaptive_trigger_study.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSIONS = ROOT / "research" / "in_domain"

# What each session was, from the session notes.
TRUTH = {
    "session5": "quiet room",
    "session6": "speech, desk distance",
    "session6b": "speech, 30 cm",
    "session7": "music, 1 m",
    "session7b": "music, 30 cm",
    "session8": "film, 1 m",
    "session8b": "film, 30 cm",
    "session9": "phone cry, 15 cm",
    "session10": "phone cry, 1 m",
}
CRY_SESSIONS = {"session9", "session10"}


def read_rms(name: str) -> list[float]:
    path = SESSIONS / name / "records.csv"
    if not path.is_file():
        return []
    out = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                out.append(float(row["rms"]))
            except (KeyError, ValueError):
                continue
    return out


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def trigger_events(values: list[float], level: float) -> int:
    """How many times the firmware's rule would fire: two consecutive
    readings at or above the level start an event, and the event ends when
    a reading falls back below it."""
    events = 0
    streak = 0
    for v in values:
        if v >= level:
            streak += 1
            if streak == 2:
                events += 1
        else:
            streak = 0
    return events


def simulate(values: list[float], mult: float, rise: float,
              lo: float, hi: float) -> tuple[int, float]:
    """Run the adaptive rule over a session's readings.

    The floor tracker is the one the firmware will use: it falls at once
    when the room gets quieter and rises very slowly, so that a long cry
    does not drag the floor up to the cry's own level and switch the
    trigger off in the middle of an episode.

    Returns the number of trigger events and the median trigger level the
    session ran at.
    """
    if not values:
        return 0, 0.0
    floor = values[0]
    events = 0
    streak = 0
    levels = []
    for v in values:
        if v < floor:
            floor = v
        else:
            floor += (v - floor) * rise
        level = max(lo, min(hi, mult * floor))
        levels.append(level)
        if v >= level:
            streak += 1
            if streak == 2:
                events += 1
        else:
            streak = 0
    return events, percentile(levels, 0.50)


def main() -> int:
    names = [n for n in sorted(TRUTH) if (SESSIONS / n / "records.csv").is_file()]
    if not names:
        print("no recorded sessions found", file=sys.stderr)
        return 1

    data = {n: read_rms(n) for n in names}

    print("=== the RMS of every recorded session (the node's own telemetry)\n")
    print(f"{'session':<10} {'what it was':<24} {'n':>5} {'p10':>8} {'p25':>8} "
          f"{'median':>8} {'p90':>8} {'max':>8}")
    for n in names:
        v = data[n]
        print(f"{n:<10} {TRUTH[n]:<24} {len(v):>5} "
              f"{percentile(v, 0.10):>8.4f} {percentile(v, 0.25):>8.4f} "
              f"{percentile(v, 0.50):>8.4f} {percentile(v, 0.90):>8.4f} "
              f"{max(v):>8.4f}")

    # The quiet room is the reference: it is the floor the adaptive rule
    # would measure.
    quiet = data.get("session5") or []
    floor = percentile(quiet, 0.10) if quiet else 0.002

    print(f"\n=== the noise floor of the quiet room: {floor:.4f} (p10)\n")
    print("The adaptive rule would trigger at 3x that, i.e. "
          f"{3 * floor:.4f}.\n")

    levels = [0.004, 0.005, 0.006, 0.007, 0.008, 0.010, 0.012, 0.015,
              0.020, 0.025, 0.030]

    print("=== trigger events per session at each level "
          "(two consecutive readings above it)\n")
    header = f"{'level':>7} " + " ".join(f"{n.replace('session', 's'):>6}"
                                          for n in names)
    print(header)
    for lv in levels:
        row = f"{lv:>7.3f} "
        for n in names:
            row += f"{trigger_events(data[n], lv):>7} "
        print(row)

    print("\n=== the same, as the number of non-cry events and cry events\n")
    print(f"{'level':>7} {'non-cry events':>16} {'cry events':>12} "
          f"{'cry s9':>8} {'cry s10':>8}")
    for lv in levels:
        noncry = sum(trigger_events(data[n], lv) for n in names
                     if n not in CRY_SESSIONS)
        cry = sum(trigger_events(data[n], lv) for n in names
                  if n in CRY_SESSIONS)
        s9 = trigger_events(data.get("session9", []), lv)
        s10 = trigger_events(data.get("session10", []), lv)
        print(f"{lv:>7.3f} {noncry:>16} {cry:>12} {s9:>8} {s10:>8}")

    # The adaptive rule, simulated over each session's own readings.
    print("\n=== the adaptive rule, simulated over each session "
          "(the floor tracker, then the trigger)\n")
    for rise in (0.002, 0.005):
        print(f"--- the floor rises by {rise:.3f} of the way to the reading "
              f"each time (a {1.0 / (rise * 10):.0f} s time constant)")
        for mult in (2.0, 3.0, 4.0, 5.0):
            row = f"  {mult:.0f}x floor: "
            noncry = 0
            cry = 0
            for n in names:
                ev, lv = simulate(data[n], mult, rise, 0.005, 0.030)
                row += f"{n.replace('session', 's')}={ev:>3}"
                if n in CRY_SESSIONS:
                    cry += ev
                else:
                    noncry += ev
            row += f"   non-cry {noncry:>4}  cry {cry:>4}"
            print(row)
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
