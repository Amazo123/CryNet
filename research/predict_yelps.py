#!/usr/bin/env python3
"""What each freeze rule would score on a short yelp.

The after-peak freeze puts the two seconds AFTER the peak in the
window, so a yelp that is over before the delay elapses is frozen over
the room instead of over the cry.  The stop-capped rule freezes when
the cry stops instead, so the window holds the yelp itself.

This scores the three placements on the same yelp, so the bench test
knows what to look for:

    after-peak   [peak, peak + 2 s]
    stop-capped  [end - 2 s, end]        (the hybrid rule)
    peak-centred [peak - 1.5 s, peak + 0.5 s]   (the rule it replaced)

Output: research/out/yelp_predictions.md
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
sys.path.insert(0, str(ROOT / "research"))
from screen_clips import build_scorer  # noqa: E402

SR = 16000
N = 32000          # the two-second window the model is shown


def read(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def window(x: np.ndarray, start: float) -> np.ndarray:
    """The two seconds starting `start` seconds into the clip."""
    a = int(start * SR)
    w = x[a:a + N]
    if len(w) < N:
        w = np.concatenate([w, np.zeros(N - len(w), np.float32)])
    return w


def stats(w: np.ndarray) -> tuple[float, int, float]:
    centred = w - w.mean()
    rms = float(np.sqrt((centred ** 2).mean()))
    peak = int(np.abs(centred).max() * 32768)
    crest = (peak / 32768.0) / rms if rms > 0 else 0.0
    return rms, peak, crest


def main() -> int:
    score = build_scorer()
    files = sorted((OUT / "short_yelps").glob("*.wav"))
    files += [OUT / "demo_kit" / "session9_clip_0005.wav"]
    lines = ["# What each freeze rule scores on a yelp", ""]
    lines.append("The window is padded with silence where the clip is shorter "
                 "than two seconds -- that is what the node's ring holds "
                 "when the room is quiet.")
    lines.append("")
    lines.append("| clip | placement | rms | peak | crest | P(cry) | announces (quiet rule 0.99) |")
    lines.append("|---|---|---|---|---|---|---|")
    for path in files:
        x = read(path)
        dur = len(x) / SR
        peak_at = float(np.argmax(np.abs(x)))
        peak_t = peak_at / SR
        placements = {
            "after-peak": (peak_t, peak_t),
            "stop-capped": (max(0.0, dur - 2.0), max(0.0, dur - 2.0)),
            "peak-centred": (max(0.0, peak_t - 1.5), max(0.0, peak_t - 1.5)),
        }
        for name, (start, _anchor) in placements.items():
            w = window(x, start)
            rms, pk, crest = stats(w)
            p = score(w)
            ann = "yes" if p >= 0.99 else ("loud rule" if p >= 0.95 else "no")
            lines.append(f"| {path.name} | {name} | {rms:.4f} | {pk} | {crest:.1f} | "
                         f"{p:.4f} | {ann} |")
        lines.append("")
    (OUT / "yelp_predictions.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
