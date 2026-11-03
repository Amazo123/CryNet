#!/usr/bin/env python3
"""Which recorded clips will the deployed model actually announce?

The demo failed on 2026-11-03 because the clip played was one the model
does not accept: it scored P(cry)=0.148 on its own, clean, and the
model is judged per 2 s window, so a clip is only as good as its best
window.

This screens every clip in the in-domain sessions against the *deployed*
INT8 model with the *notebook's own* front end, so the numbers here are
the numbers the hub will print.  For each clip it reports, per 2 s
window, the model's P(cry) as it stands and with the low-frequency
rumble taken out (a 100 Hz high-pass), plus the level and crest the
hub's gates will see.

Output:
    research/out/clip_screening.csv    one row per window
    research/out/clip_screening.md     the ranked, human-usable summary

Usage:
    python research/screen_clips.py
    python research/screen_clips.py --sessions session9 session10
"""

from __future__ import annotations

import argparse
import csv
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
CLIPS = ROOT / "research" / "in_domain"

# The notebook's frozen front end (build_notebook.py, CELL 1 and CELL 4).
SR = 16000
WIN_SEC = 2.0
N_SAMPLES = int(SR * WIN_SEC)
N_FFT = 512
HOP = 400
N_MELS = 64
FMIN = 20.0
FMAX = 8000.0
CENTER_PAD = 256
TAIL_PAD = 512
DB_FLOOR = -80.0
LOG_EPS = 1e-10
CMVN = True

ANNOUNCE = 0.99       # one window may announce on its own
MAYBE = 0.95          # a maybe must be confirmed by the next window
NEAR = 0.60           # "the model can see it but will not announce it"


def log_mel(x: np.ndarray) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view

    x = np.asarray(x, dtype=np.float32)
    assert x.shape[0] == N_SAMPLES, x.shape
    x = x - x.mean()
    xp = np.concatenate([np.zeros(CENTER_PAD, np.float32), x,
                         np.zeros(TAIL_PAD, np.float32)])
    frames = sliding_window_view(xp, N_FFT)[::HOP]
    hann = np.hanning(N_FFT).astype(np.float32)
    spec = np.fft.rfft(frames * hann, axis=-1)
    power = spec.real ** 2 + spec.imag ** 2
    mel = power @ MEL_BANK.T
    db = 10.0 * np.log10(np.maximum(mel, LOG_EPS))
    db = np.maximum(db, DB_FLOOR)
    if CMVN:
        db = (db - db.mean()) / (db.std() + 1e-6)
    return db.astype(np.float32)


def high_pass(x: np.ndarray, cutoff: float = 100.0) -> np.ndarray:
    from scipy.signal import firwin, lfilter

    taps = firwin(513, cutoff, pass_zero=False, fs=SR)
    return lfilter(taps, 1.0, x)


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as f:
        if f.getframerate() != SR or f.getnchannels() != 1:
            raise ValueError(f"{path}: {f.getframerate()} Hz, {f.getnchannels()} ch")
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def build_scorer():
    import librosa
    import tensorflow as tf

    global MEL_BANK
    MEL_BANK = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=N_MELS,
                                   fmin=FMIN, fmax=FMAX, htk=False,
                                   norm="slaney").astype(np.float32)

    interp = tf.lite.Interpreter(model_path=str(OUT / "crynet_int8.tflite"))
    interp.allocate_tensors()
    i_d = interp.get_input_details()[0]
    o_d = interp.get_output_details()[0]
    s, z = i_d["quantization"]

    def score(sig: np.ndarray) -> float:
        f = log_mel(sig.astype(np.float32))[None, ...]
        q = np.clip(np.round(f / s) + z, -128, 127).astype(np.int8)
        interp.set_tensor(i_d["index"], q[..., None])
        interp.invoke()
        o = interp.get_tensor(o_d["index"])[0].astype(np.float32)
        p = (o - o_d["quantization"][1]) * o_d["quantization"][0]
        return float(np.asarray(p).reshape(-1)[1])

    return score


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", nargs="*", default=None,
                    help="only these session directories")
    ap.add_argument("--hop-sec", type=float, default=1.0,
                    help="how far the 2 s analysis window slides along a clip")
    args = ap.parse_args()

    score = build_scorer()

    sessions = sorted(p for p in CLIPS.glob("session*") if p.is_dir())
    if args.sessions:
        wanted = set(args.sessions)
        sessions = [p for p in sessions if p.name in wanted]

    rows = []
    for session in sessions:
        for clip in sorted((session / "clips").glob("*.wav")):
            x = read_wav(clip)
            if len(x) < N_SAMPLES:
                print(f"{clip}: too short ({len(x) / SR:.2f} s) — skipped",
                      file=sys.stderr)
                continue
            step = max(1, int(args.hop_sec * SR))
            t = 0
            wi = 0
            while t + N_SAMPLES <= len(x):
                w = x[t:t + N_SAMPLES]
                centred = w - w.mean()
                rms = float(np.sqrt((centred ** 2).mean()))
                peak = float(np.abs(w).max())
                crest = peak / (rms or 1.0)
                p = score(centred)
                p_hp = score(high_pass(centred))
                rows.append({
                    "session": session.name,
                    "clip": clip.name,
                    "window": wi,
                    "start_sec": round(t / SR, 2),
                    "rms": round(rms, 6),
                    "peak": round(peak, 6),
                    "crest": round(crest, 2),
                    "p_cry": round(p, 4),
                    "p_cry_highpassed": round(p_hp, 4),
                    "hub_would_announce": int(p >= ANNOUNCE),
                })
                wi += 1
                t += step

    OUT.mkdir(parents=True, exist_ok=True)
    csv_path = OUT / "clip_screening.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # ---- the ranked summary ------------------------------------------------
    by_clip: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        by_clip.setdefault((r["session"], r["clip"]), []).append(r)

    def best(r: dict) -> float:
        return max(r["p_cry"], r["p_cry_highpassed"])

    ranked = []
    for (session, clip), rs in by_clip.items():
        top = max(rs, key=best)
        ranked.append({
            "session": session,
            "clip": clip,
            "windows": len(rs),
            "best_p": max(r["p_cry"] for r in rs),
            "best_p_hp": max(r["p_cry_highpassed"] for r in rs),
            "best_p_any": best(top),
            "n_announce": sum(1 for r in rs if r["p_cry"] >= ANNOUNCE),
            "n_maybe": sum(1 for r in rs if MAYBE <= r["p_cry"] < ANNOUNCE),
            "rms": top["rms"],
            "crest": top["crest"],
        })
    ranked.sort(key=lambda d: -d["best_p_any"])

    md = OUT / "clip_screening.md"
    lines = [
        "# Clip screening — what the deployed model will announce",
        "",
        "Scored with the deployed INT8 model and the notebook's own front end.",
        "A clip is **demo-ready** when one of its 2 s windows reaches "
        f"P(cry) >= {ANNOUNCE} — that is the hub's single-window announce bar.",
        "",
        f"| session | clip | windows | best P | best P (100 Hz HP) | announce | maybe | rms | crest |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for d in ranked:
        mark = "**" if d["n_announce"] else ""
        lines.append(
            f"| {d['session']} | {mark}{d['clip']}{mark} | {d['windows']} | "
            f"{d['best_p']:.4f} | {d['best_p_hp']:.4f} | {d['n_announce']} | "
            f"{d['n_maybe']} | {d['rms']:.4f} | {d['crest']:.1f} |")
    lines.append("")
    ready = [d for d in ranked if d["n_announce"]]
    near = [d for d in ranked if not d["n_announce"] and d["best_p_any"] >= NEAR]
    lines.append(f"## demo-ready clips (P >= {ANNOUNCE}): {len(ready)} of {len(ranked)}")
    for d in ready:
        lines.append(f"- `{d['session']}/clips/{d['clip']}` — P {d['best_p']:.4f}, "
                     f"{d['n_announce']} announcing window(s)")
    lines.append("")
    lines.append(f"## seen but not announceable (P >= {NEAR} only): {len(near)}")
    for d in near:
        lines.append(f"- `{d['session']}/clips/{d['clip']}` — P {d['best_p']:.4f} "
                     f"(HP {d['best_p_hp']:.4f})")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"windows scored : {len(rows)}")
    print(f"clips          : {len(ranked)}")
    print(f"demo-ready     : {len(ready)} (P >= {ANNOUNCE} in at least one window)")
    print(f"near-miss      : {len(near)} (P >= {NEAR} but < {ANNOUNCE})")
    print(f"wrote {csv_path}")
    print(f"wrote {md}")
    print()
    for d in ranked[:25]:
        flag = "ANNOUNCE" if d["n_announce"] else ("maybe   " if d["n_maybe"] else "        ")
        print(f"  {flag}  {d['session']:<12} {d['clip']:<16} "
              f"P {d['best_p']:.4f}  HP {d['best_p_hp']:.4f}  "
              f"rms {d['rms']:.4f}  crest {d['crest']:.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
