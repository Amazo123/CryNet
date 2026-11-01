#!/usr/bin/env python3
"""Look at what is in a window, and what the model makes of it.

The hub's log says *that* a window was judged a cry; this says *what was
in it*: where its energy sits, how much of it is below the band a cry
lives in, and how the deployed model scores the window as it stands and
with the low-frequency drift taken out.

The front end removes the window's mean and then normalises each window's
own mean and variance (CMVN), so a quiet window is stretched to the same
scale as a loud one and only its shape is left.  A window whose energy
sits in the bottom few bands — the microphone's bias drifting, a supply
hum — becomes, after that stretching, a pattern with a strong low
fundamental.  This measures whether that is what is happening.

Usage:
    python research/analyze_window.py research/out/node_window_quiet.wav
    python research/analyze_window.py --no-model <file.wav>
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "out")
SR = 16000


def read_wav(path: str) -> np.ndarray:
    import wave

    with wave.open(path, "rb") as f:
        n = f.getnframes()
        raw = f.readframes(n)
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    return x


def band_share(x: np.ndarray, lo: float, hi: float) -> float:
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    freqs = np.fft.rfftfreq(len(x), 1.0 / SR)
    m = (freqs >= lo) & (freqs < hi)
    return float(spec[m].sum() / (spec.sum() or 1.0))


def high_pass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """Remove everything below the cutoff, with a simple linear-phase FIR."""
    from scipy.signal import firwin, lfilter

    n_taps = 513
    taps = firwin(n_taps, cutoff, pass_zero=False, fs=SR)
    return lfilter(taps, 1.0, x)


def drift(x: np.ndarray, seconds: float = 0.5) -> np.ndarray:
    """The slow wander of the signal: a moving average of half a second."""
    n = int(seconds * SR)
    kernel = np.ones(n) / n
    return np.convolve(x, kernel, mode="same")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--start", type=float, default=0.0,
                    help="how many seconds into the file to start at")
    ap.add_argument("--no-model", action="store_true")
    args = ap.parse_args()

    x = read_wav(args.wav)
    off = int(args.start * SR)
    x = x[off:]
    if len(x) < 2 * SR:
        print(f"{args.wav}: only {len(x)} samples from {args.start:.1f} s")
        return 1
    x = x[: 2 * SR]
    centred = x - x.mean()

    print(f"file          : {args.wav}")
    print(f"samples       : {len(x)}  ({len(x) / SR:.2f} s)")
    print(f"mean          : {x.mean():+.6f}   ({x.mean() * 32768:+.0f} counts)")
    print(f"rms           : {np.sqrt((centred ** 2).mean()):.6f}")
    print(f"peak          : {np.abs(x).max():.6f}")
    print(f"peak/rms      : {np.abs(x).max() / (np.sqrt((centred ** 2).mean()) or 1):.1f}")

    # How much of the signal is the slow wander, and how much is left
    # once it is taken away?
    d = drift(centred)
    rest = centred - d
    print(f"slow wander   : rms {np.sqrt((d ** 2).mean()):.6f}  "
          f"({100 * (d ** 2).sum() / (centred ** 2).sum():.0f} % of the energy)")
    print(f"without it    : rms {np.sqrt((rest ** 2).mean()):.6f}")

    print("energy by band:")
    for lo, hi in [(0, 30), (30, 100), (100, 300), (300, 1000),
                   (1000, 2500), (2500, 4000), (4000, 8000)]:
        share = band_share(centred, lo, hi)
        print(f"  {lo:>5}-{hi:<5} Hz  {share * 100:5.1f} %  " + "#" * int(share * 60))

    if args.no_model:
        return 0

    sys.path.insert(0, os.path.join(ROOT, "research"))
    from eval_indomain import notebook_namespace  # type: ignore
    import tensorflow as tf

    ns = notebook_namespace()
    log_mel = ns["log_mel"]
    interp = tf.lite.Interpreter(model_path=os.path.join(OUT, "crynet_int8.tflite"))
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

    variants = [("as it stands", centred)]
    try:
        variants.append(("high-passed at 100 Hz", high_pass(centred, 100.0)))
    except Exception as exc:
        print(f"(no high-pass: {exc})")
    variants.append(("wander removed", rest))

    print("\nthe model's verdict:")
    for name, sig in variants:
        print(f"  {name:<22} P(cry) = {score(sig):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
