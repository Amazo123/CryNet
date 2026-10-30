#!/usr/bin/env python3
"""Measure the domain gap: run the deployed model over the in-domain clips.

The deployed model was trained on Kaggle corpora.  This script runs the
*exported* INT8 model — the very file that is flashed onto the hub — over
the clips recorded from this room's microphone, using the notebook's own
front end, so the numbers are what the hub would actually produce.

It answers two questions:

  1. Would the hub even ask the model?  The hub only pulls a window when
     the node's telemetry RMS reaches CRYNET_TRIGGER_RMS (0.030), so a clip
     quieter than that never reaches the classifier at all.
  2. If it did, what would the model say?  AUC and the confusion matrix
     over the labelled clips, at the deployed threshold of 0.95.

Usage:
    python research/eval_indomain.py --session research/in_domain/session1
    python research/eval_indomain.py --session research/in_domain/session1 \
        --threshold 0.95 --window-seconds 2
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"

sys.path.insert(0, str(ROOT / "research"))
from verify_int8_parity import notebook_namespace  # noqa: E402


def read_wav(path: Path) -> np.ndarray:
    """A 16-bit PCM WAV as float32 in [-1, 1] — the scale soundfile gives."""
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError(f"{path} is not 16-bit mono")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True)
    ap.add_argument("--threshold", type=float, default=0.95,
                    help="the deployed decision threshold")
    ap.add_argument("--trigger-rms", type=float, default=0.030,
                    help="the hub's trigger level (CRYNET_TRIGGER_RMS)")
    ap.add_argument("--windows-per-clip", type=int, default=2)
    ap.add_argument("--report", default=str(OUT / "eval_indomain.json"))
    args = ap.parse_args()

    session = Path(args.session)
    manifest_path = session / "manifest.csv"
    if not manifest_path.is_file():
        print(f"no manifest in {session} — run firmware/tools/label_session.py first")
        return 1

    rows = list(csv.DictReader(manifest_path.open(newline="")))
    if not rows:
        print("the manifest is empty")
        return 1

    ns = notebook_namespace()
    log_mel = ns["log_mel"]
    take_windows = ns["take_windows"]

    # ---- features -----------------------------------------------------------
    feats, labels, per_clip = [], [], []
    skipped = 0
    for row in rows:
        path = session / "clips_labeled" / row["file"]
        if not path.is_file():
            skipped += 1
            continue
        x = read_wav(path)
        label = 1 if row["label"] == "cry" else 0
        windows = take_windows(x, args.windows_per_clip, None, mode="center")
        f = np.stack([log_mel(w) for w in windows]).astype(np.float32)
        feats.append(f)
        labels.extend([label] * f.shape[0])
        per_clip.append((row["file"], label, float(row["rms_mean"]),
                         float(row["rms_peak"])))
    if skipped:
        print(f"warning: {skipped} clip(s) named in the manifest are missing")
    X = np.concatenate(feats, axis=0)
    y = np.asarray(labels, dtype=np.int32)
    print(f"\nclips: {len(per_clip)}  windows: {X.shape[0]}  "
          f"cry windows: {int(y.sum())}")

    # ---- the deployed INT8 model -------------------------------------------
    import tensorflow as tf  # noqa: E402

    interp = tf.lite.Interpreter(model_path=str(OUT / "crynet_int8.tflite"))
    interp.allocate_tensors()
    i_d = interp.get_input_details()[0]
    o_d = interp.get_output_details()[0]
    s, z = i_d["quantization"]

    p_int8 = np.zeros((len(X), 2), np.float32)
    for i in range(len(X)):
        q = np.clip(np.round(X[i].astype(np.float32) / s) + z, -128, 127).astype(np.int8)
        interp.set_tensor(i_d["index"], q[None, ..., None])
        interp.invoke()
        o = interp.get_tensor(o_d["index"])[0].astype(np.float32)
        p_int8[i] = (o - o_d["quantization"][1]) * o_d["quantization"][0]

    keras_model = tf.keras.models.load_model(str(OUT / "crynet.keras"))
    p_float = keras_model.predict(X, verbose=0).astype(np.float32)

    # ---- metrics -----------------------------------------------------------
    from sklearn.metrics import roc_auc_score  # noqa: E402

    def confusion(p):
        yh = (p >= args.threshold).astype(int)
        tp = int(((yh == 1) & (y == 1)).sum())
        fn = int(((yh == 0) & (y == 1)).sum())
        fp = int(((yh == 1) & (y == 0)).sum())
        tn = int(((yh == 0) & (y == 0)).sum())
        return {
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "accuracy": (tp + tn) / max(len(y), 1),
            "recall": tp / max(tp + fn, 1),
            "fpr": fp / max(fp + tn, 1),
        }

    auc = float(roc_auc_score(y, p_int8[:, 1])) if len(set(y.tolist())) > 1 else float("nan")
    conf_int8 = confusion(p_int8[:, 1])
    conf_float = confusion(p_float[:, 1])

    # ---- the trigger --------------------------------------------------------
    cry_clips = [c for c in per_clip if c[1] == 1]
    quiet_clips = [c for c in per_clip if c[1] == 0]
    above = sum(1 for c in cry_clips if c[2] >= args.trigger_rms)
    below = sum(1 for c in quiet_clips if c[2] >= args.trigger_rms)

    report = {
        "source": "research/eval_indomain.py",
        "session": str(session),
        "clips": len(per_clip),
        "windows": int(X.shape[0]),
        "cry_windows": int(y.sum()),
        "threshold": args.threshold,
        "trigger_rms": args.trigger_rms,
        "auc_int8": auc,
        "int8": conf_int8,
        "float32": conf_float,
        "trigger": {
            "cry_clips_above_trigger": above,
            "cry_clips": len(cry_clips),
            "no_cry_clips_above_trigger": below,
            "no_cry_clips": len(quiet_clips),
        },
        "per_clip": [
            {"file": f, "label": l, "rms_mean": rm, "rms_peak": rp}
            for f, l, rm, rp in per_clip
        ],
    }
    Path(args.report).write_text(json.dumps(report, indent=2))

    print(f"\nAUC (INT8, the deployed model): {auc:.4f}")
    print(f"at P >= {args.threshold}:")
    print(f"  INT8    acc {conf_int8['accuracy']:.3f}  "
          f"recall {conf_int8['recall']:.3f}  fpr {conf_int8['fpr']:.3f}  "
          f"(tp {conf_int8['tp']} fn {conf_int8['fn']} fp {conf_int8['fp']} "
          f"tn {conf_int8['tn']})")
    print(f"  float32 acc {conf_float['accuracy']:.3f}  "
          f"recall {conf_float['recall']:.3f}  fpr {conf_float['fpr']:.3f}")
    print(f"\ntrigger at RMS >= {args.trigger_rms}:")
    print(f"  {above}/{len(cry_clips)} cry clips would reach the model")
    print(f"  {below}/{len(quiet_clips)} no-cry clips would also reach it "
          f"(false triggers)")
    print(f"\nwrote {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
