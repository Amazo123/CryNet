#!/usr/bin/env python3
"""Independently verify the deployed CryNet artifacts on the host.

The full Kaggle run reported `int8_val_auc` and `float_val_auc` as NaN,
because the parity cell took a *prefix* of the validation fold. The ICD
manifest lists every positive clip before every negative one, and the
validation fold's positive clips alone contribute more windows than the
4000-window cap, so that prefix contained only cry audio and its AUC was
undefined. The model itself is unaffected — every headline metric is
computed over the whole split — but the INT8-versus-float numbers for
these weights were never produced.

This script closes that gap without a 40-minute Kaggle re-run. It:

  * rebuilds the ICD validation fold (fold 4) straight from the cached
    archives and the shipped manifest;
  * extracts features with the notebook's own front end;
  * runs BOTH the exported INT8 TFLite model and the float32 Keras model
    over them;
  * reports the AUC of each, their difference, and the decision agreement
    at the calibrated threshold.

It deliberately uses its own centre-cropped windows rather than the
notebook's random ones, so the check is independent of that run.

Usage:  python research/verify_int8_parity.py [--max-clips N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "notebooks" / "crynet_training.ipynb"
OUT = ROOT / "research" / "out"
CACHE = ROOT / "research" / "_cache"
REPORT = OUT / "verify_int8_parity.json"

CELL_MARKERS = [
    "CELL 1 — Environment",
    "CELL 2 — Dependencies",
    "CELL 3 — Dataset acquisition",
    "CELL 4 — The audio front end",
    "CELL 5 — Archive readers",
    "CELL 6 — Corpus manifests",
]

VAL_FOLD = "4"


def notebook_namespace():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    srcs = {}
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        text = "\n".join(cell["source"])
        for marker in CELL_MARKERS:
            if marker in text:
                srcs[marker] = text

    missing = [m for m in CELL_MARKERS if m not in srcs]
    if missing:
        raise SystemExit(f"markers not found in the notebook: {missing}")

    import librosa  # noqa: E402  (the notebook imports it in its dependency cell)

    ns = {"__name__": "__main__", "librosa": librosa, "np": np}

    # The configuration cell resolves its directories from the environment.
    os.environ["CRYNET_CACHE"] = str(CACHE)
    os.environ["CRYNET_WORK"] = str(ROOT / "research" / "_verify_work")
    os.environ["CRYNET_OUT"] = str(OUT)
    for sub in ("_verify_work",):
        (ROOT / "research" / sub).mkdir(parents=True, exist_ok=True)

    for marker in CELL_MARKERS:
        print(f">>> {marker}")
        exec(compile(srcs[marker], f"<{marker}>", "exec"), ns)
    return ns


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-clips", type=int, default=0,
                    help="limit the number of clips (0 = the whole fold)")
    args = ap.parse_args()

    t_start = time.time()
    ns = notebook_namespace()

    log_mel = ns["log_mel"]
    take_windows = ns["take_windows"]
    decode = ns["decode"]
    READERS = ns["READERS"]
    icd_entries = ns["icd_entries"]

    val_entries = [e for e in icd_entries if str(e[3]) == VAL_FOLD]
    if args.max_clips:
        val_entries = val_entries[: args.max_clips]
    n_cry = sum(e[1] for e in val_entries)
    print(f"\nvalidation fold {VAL_FOLD}: {len(val_entries)} clips "
          f"({n_cry} cry, {len(val_entries) - n_cry} non-cry)")

    # ---- feature extraction -------------------------------------------------
    failures = {"missing": 0, "decode": 0, "ok": 0}

    def features_for(entry):
        stem, label, sub, fold, key = entry
        reader = READERS[key]
        member = reader.index_by_stem().get(stem)
        if member is None:
            failures["missing"] += 1
            return None
        try:
            x = decode(reader.read(member))
        except Exception:
            x = None
        if x is None:
            failures["decode"] += 1
            return None
        feats = [log_mel(w) for w in take_windows(x, 2, None, mode="center")]
        failures["ok"] += 1
        return np.stack(feats).astype(np.float32), label

    t0 = time.time()
    X, y = [], []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(features_for, val_entries):
            if res is None:
                continue
            feats, label = res
            X.append(feats)
            y.extend([label] * feats.shape[0])

    if not X:
        raise SystemExit(
            f"no features were extracted: {failures['missing']} clips were not "
            f"found in the archives and {failures['decode']} failed to decode. "
            f"Check that the cached archives match the manifest."
        )
    X = np.concatenate(X, axis=0)
    y = np.asarray(y, dtype=np.int32)
    print(f"features: {X.shape}  ({time.time() - t0:.0f}s)  "
          f"[ok {failures['ok']}, missing {failures['missing']}, "
          f"undecodable {failures['decode']}]")

    # ---- models -------------------------------------------------------------
    import tensorflow as tf  # noqa: E402

    threshold = float(ns.get("THRESHOLD", 0.95))

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

    # ---- comparison ---------------------------------------------------------
    from sklearn.metrics import roc_auc_score  # noqa: E402

    a_int8 = float(roc_auc_score(y, p_int8[:, 1]))
    a_float = float(roc_auc_score(y, p_float[:, 1]))
    delta_p = np.abs(p_int8[:, 1] - p_float[:, 1])
    agree = float(((p_int8[:, 1] >= threshold) == (p_float[:, 1] >= threshold)).mean())

    def at_threshold(p):
        yh = (p >= threshold).astype(int)
        tp = int(((yh == 1) & (y == 1)).sum())
        fn = int(((yh == 0) & (y == 1)).sum())
        fp = int(((yh == 1) & (y == 0)).sum())
        tn = int(((yh == 0) & (y == 0)).sum())
        recall = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)
        return {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
                "recall": recall, "fpr": fpr,
                "precision": tp / max(tp + fp, 1)}

    m_int8 = at_threshold(p_int8[:, 1])
    m_float = at_threshold(p_float[:, 1])

    report = {
        "source": "research/verify_int8_parity.py",
        "model_sha256_note": "the SHA-256 of crynet_int8.tflite is checked by "
                             "firmware/tools/check_artifact_drift.py",
        "fold": VAL_FOLD,
        "clips": int(len(val_entries)),
        "windows": int(len(X)),
        "cry_windows": int(y.sum()),
        "threshold": threshold,
        "auc_int8": a_int8,
        "auc_float32": a_float,
        "auc_delta": a_int8 - a_float,
        "max_abs_delta_p": float(delta_p.max()),
        "mean_abs_delta_p": float(delta_p.mean()),
        "decision_agreement": agree,
        "int8_at_threshold": m_int8,
        "float32_at_threshold": m_float,
        "elapsed_s": time.time() - t_start,
    }

    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n" + "=" * 66)
    print("INT8 vs float32 on the ICD validation fold")
    print("=" * 66)
    print(f"  windows              : {len(X)} ({int(y.sum())} cry)")
    print(f"  AUC   int8           : {a_int8:.6f}")
    print(f"  AUC   float32        : {a_float:.6f}")
    print(f"  AUC   delta          : {a_int8 - a_float:+.6f}")
    print(f"  max |delta p|        : {delta_p.max():.6f}")
    print(f"  mean |delta p|       : {delta_p.mean():.6f}")
    print(f"  decision agreement   : {agree:.4%}")
    print(f"  int8    recall {m_int8['recall']:.4f}  FPR {m_int8['fpr']:.4f}")
    print(f"  float32 recall {m_float['recall']:.4f}  FPR {m_float['fpr']:.4f}")
    print(f"\n  wrote {REPORT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
