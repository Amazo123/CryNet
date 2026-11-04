#!/usr/bin/env python3
"""Score the demo kit's clips with the deployed INT8 model on the host.

The bench run announced nothing.  This asks the question that decides
where the fault is: does the deployed model, on the host, still call
these clips a cry?  If it does, the clip is good and the fault is in
the link; if it does not, the clip itself is not what the model was
trained on.

Every two-second window of the clip is scored, the way the hub scores
the window it pulls off the air.
"""
from __future__ import annotations

import os
import sys
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "research", "out")
SR = 16000
N = 32000  # two seconds at 16 kHz, the node's window


def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as f:
        raw = f.readframes(f.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def main(argv: list[str]) -> int:
    paths = argv[1:] or [os.path.join(ROOT, "research", "out", "demo_kit",
                                     "session9_clip_0005.wav")]
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

    for path in paths:
        x = read_wav(path)
        print(f"\n{os.path.basename(path)}  ({len(x)/SR:.2f} s)")
        worst = 1.0
        best = 0.0
        for i in range(0, max(1, len(x) - N + 1), N // 2):
            w = x[i:i + N]
            if len(w) < N:
                break
            p = score(w)
            rms = float(np.sqrt(np.mean(w * w)))
            best = max(best, p)
            worst = min(worst, p)
            print(f"  t={i/SR:5.1f}s  rms {rms:.4f}  P(cry) = {p:.4f}")
        print(f"  best P(cry) = {best:.4f}   worst = {worst:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
