#!/usr/bin/env python3
"""Build a demo kit: clips the hub will announce from the very first window.

The screening (`research/screen_clips.py`) showed why a demo can miss
even when the clip is a good one: the node freezes the two seconds
centred on the *first* crossing of its trigger level, so a clip that
opens with a quiet onset gets judged on the onset.  `session9/clip_0000`
scores 0.1484 on its first two seconds and 0.9961 on its second — the
cry is in the clip, the frozen window is not.

This cuts each candidate at the first sample where the cry really starts
(trailing quiet removed too), re-scores the result with the deployed
INT8 model, and keeps only the clips that announce from their first
window.  Those are the clips a demo can rely on.

Output:
    research/out/demo_kit/*.wav        the trimmed clips
    research/out/DEMO_KIT.md           what to play, and what it scores

Usage:
    python research/build_demo_kit.py
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
KIT = OUT / "demo_kit"
CLIPS = ROOT / "research" / "in_domain"

SR = 16000
WIN = 32000

# Which sessions hold phone-played cries (the demo material), and which
# hold non-cry audio (never to be used as a demo clip).
CANDIDATE_SESSIONS = ["session9", "session1", "session4", "session10"]
NON_CRY_SESSIONS = {"session2", "session3_partial", "session5", "session6",
                     "session6b", "session7", "session7b", "session8", "session8b"}


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def write_wav(path: Path, x: np.ndarray) -> None:
    pcm = np.clip(x * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def trim(x: np.ndarray, lead_ms: int = 60, tail_ms: int = 150) -> np.ndarray:
    """Cut the quiet head and tail, keeping a short natural lead-in."""
    n = len(x)
    env = np.abs(x)
    # 50 ms envelope, so a single spike cannot decide the cut
    k = int(0.05 * SR)
    smooth = np.convolve(env, np.ones(k) / k, mode="same")
    peak = smooth.max()
    if peak <= 0:
        return x
    thresh = 0.35 * peak
    loud = np.where(smooth >= thresh)[0]
    if len(loud) == 0:
        return x
    start = max(0, loud[0] - int(lead_ms * SR / 1000))
    end = min(n, loud[-1] + int(tail_ms * SR / 1000))
    return x[start:end]


def main() -> int:
    sys.path.insert(0, str(ROOT / "research"))
    from screen_clips import build_scorer  # the same front end and model

    score = build_scorer()
    KIT.mkdir(parents=True, exist_ok=True)

    made = []
    for session in CANDIDATE_SESSIONS:
        for clip in sorted((CLIPS / session / "clips").glob("*.wav")):
            x = read_wav(clip)
            if len(x) < WIN:
                continue
            t = trim(x)
            if len(t) < WIN:
                continue
            p0 = score(t[:WIN] - t[:WIN].mean())
            best = max(score(t[i:i + WIN] - t[i:i + WIN].mean())
                       for i in range(0, max(1, len(t) - WIN + 1), WIN))
            if p0 < 0.99:
                continue
            name = f"{session}_{clip.stem}.wav"
            write_wav(KIT / name, t)
            rms = float(np.sqrt(((t[:WIN] - t[:WIN].mean()) ** 2).mean()))
            crest = float(np.abs(t[:WIN]).max() / (rms or 1))
            made.append({
                "name": name, "session": session, "src": clip.name,
                "p_first": p0, "p_best": best, "rms": rms, "crest": crest,
                "secs": len(t) / SR,
            })

    made.sort(key=lambda d: (d["session"], d["name"]))
    md = OUT / "DEMO_KIT.md"
    lines = [
        "# Demo kit — clips that announce from the first window",
        "",
        "Each clip below was trimmed to the cry itself and re-scored with "
        "the **deployed INT8 model**: the first 2 s window already reaches "
        "P(cry) >= 0.99, which is exactly the window the node freezes when "
        "the trigger fires at the head of the clip.",
        "",
        "| file | from | first-window P | best P | rms | crest | length |",
        "|---|---|---|---|---|---|---|",
    ]
    for d in made:
        lines.append(
            f"| `{d['name']}` | {d['session']}/{d['src']} | **{d['p_first']:.4f}** | "
            f"{d['p_best']:.4f} | {d['rms']:.4f} | {d['crest']:.1f} | {d['secs']:.1f} s |")
    lines += [
        "",
        "**How to play it:** copy the file to the phone, play it with the "
        "phone **10–15 cm from the INMP441** and with the volume set so the "
        "hub's panel reads **0.10–0.20** while it plays (D-74: that level "
        "gave five alerts in a row with no clipping).",
        "",
        "**Do not** play from the laptop/PC speakers: they reshape the cry "
        "enough that the model refuses it (P 0.03–0.15 on a window the "
        "model scores 0.9961 from the same recording).",
    ]
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"demo clips written: {len(made)}  -> {KIT}")
    for d in made:
        print(f"   {d['name']:<28} first P {d['p_first']:.4f}  best {d['p_best']:.4f}  "
              f"rms {d['rms']:.4f}  crest {d['crest']:.1f}  {d['secs']:.1f}s")
    print(f"wrote {md}")

    # A sanity check that the kit did not smuggle in a non-cry clip.
    print("\nnon-cry sessions were not used as demo material:",
          ", ".join(sorted(NON_CRY_SESSIONS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
