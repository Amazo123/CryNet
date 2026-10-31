#!/usr/bin/env python3
"""The false-alarm map: what does the *deployed* model say about real speech,
real music and real household noise?

The deployed INT8 model is run over ESC-50 — 2,000 real-world recordings
across 50 categories (speech, music, domestic sounds, animals, human
non-speech, and 40 real "crying_baby" clips).  For every clip the script
reports:

  * the peak RMS and whether the clip would even reach the classifier
    (the hub only pulls a window when the node's 100 ms RMS reaches
    CRYNET_TRIGGER_RMS, 0.030),
  * the model's P(cry),
  * whether the model would have raised an alarm (P >= the deployed
    threshold, 0.95).

and then rolls those up per ESC-50 category and per coarse group, so the
answer to "can it tell a cry from music or speech?" is a table rather
than an opinion.

The front end is the notebook's own, and the model is the very file that
is flashed onto the hub, so the numbers are what the hub produces.

Caveat, stated plainly: ESC-50's non-cry clips were part of the model's
training corpus, so the false-alarm rates here are optimistic for those
categories.  What this buys is the *category map* — which kinds of sound
the model finds cry-like and which it does not — and the end-to-end
number of alarms a room full of clatter would produce.  The honest
in-room number comes from the confusion session recorded with the
INMP441 (research/in_domain/), and it is a separate measurement.

Note also what ESC-50 does *not* contain: it has no music and no
speech, only environmental sound and human non-speech vocalisations.
The model's behaviour on music is therefore measured separately, by
research/eval_music.py.

Usage:
    python research/eval_esc50.py                 # every clip
    python research/eval_esc50.py --max-clips 300
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
CACHE = ROOT / "research" / "_cache"
ESC50_ZIP = CACHE / "esc50__akaliutau_esc-50.zip"

sys.path.insert(0, str(ROOT / "research"))
from verify_int8_parity import notebook_namespace  # noqa: E402

# ESC-50's own five groups (the paper's taxonomy).  Forty clips each,
# except crying_baby which is the cry class.  Note what is *not* here:
# ESC-50 has no music and no speech — it is environmental sound plus
# human non-speech vocalisations.  Speech and music have to come from
# somewhere else.
GROUPS = {
    "animal": [
        "dog", "rooster", "crow", "pig", "cow", "frog", "hen", "cat",
        "sheep", "insects",
    ],
    "nature": [
        "rain", "thunderstorm", "sea_waves", "crackling_fire", "crickets",
        "chirping_birds", "water_drops", "wind", "pouring_water",
        "toilet_flush",
    ],
    "human_non_speech": [
        "crying", "sneezing", "clapping", "breathing", "coughing",
        "footsteps", "laughing", "drinking_sipping",
    ],
    "domestic": [
        "door_wood_creaks", "mouse_click", "keyboard_typing",
        "door_wood_knock", "washing_dishes", "washing_machine",
        "vacuum_cleaner", "clock_alarm", "clock_tick", "glass_breaking",
        "can_opening", "brushing_teeth",
    ],
    "urban": [
        "helicopter", "chainsaw", "siren", "car_horn", "engine", "train",
        "church_bells", "airplane", "fireworks", "hand_saw",
    ],
}

# The categories that are a cry of one kind or another, by ESC-50's own
# names.  ESC-50's `crying_baby` is a stock recording, not an infant cry
# from a cot, and `crying` is an adult sob; both are reported separately
# from the ordinary negatives.
CRY_CATEGORIES = {"crying_baby", "crying"}


def group_of(category: str) -> str:
    if category in ("crying_baby", "crying"):
        return "cry-ish"
    for name, members in GROUPS.items():
        if category in members:
            return name
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-clips", type=int, default=0)
    ap.add_argument("--windows-per-clip", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.95)
    ap.add_argument("--trigger-rms", type=float, default=0.030)
    ap.add_argument("--report", default=str(OUT / "eval_esc50.json"))
    args = ap.parse_args()

    if not ESC50_ZIP.is_file():
        print(f"no ESC-50 archive in the cache: {ESC50_ZIP}")
        return 1

    t_start = time.time()
    ns = notebook_namespace()
    log_mel = ns["log_mel"]
    take_windows = ns["take_windows"]
    decode = ns["decode"]

    with zipfile.ZipFile(ESC50_ZIP) as z:
        meta_name = next(n for n in z.namelist() if n.endswith("meta/esc50.csv"))
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(meta_name),
                                                    encoding="utf-8")))
        print(f"\nESC-50 manifest: {len(rows)} clips")

        # ---- features ------------------------------------------------------
        feats, clips, skipped = [], [], 0
        for row in rows:
            if args.max_clips and len(clips) >= args.max_clips:
                break
            member = f"ESC-50-master/audio/{row['filename']}"
            try:
                raw = z.read(member)
            except KeyError:
                skipped += 1
                continue
            x = decode(raw)
            if x is None:
                skipped += 1
                continue
            windows = take_windows(x, args.windows_per_clip, None, mode="center")
            first = len(feats)
            for w in windows:
                feats.append(log_mel(w))
            clips.append({
                "category": row["category"],
                "filename": row["filename"],
                "rms": float(np.sqrt(np.mean(x.astype(np.float64) ** 2))),
                "windows": list(range(first, len(feats))),
            })
            if len(clips) % 200 == 0:
                print(f"  {len(clips)} clips", flush=True)
    if skipped:
        print(f"warning: {skipped} clip(s) skipped")

    X = np.stack(feats).astype(np.float32)
    print(f"windows: {X.shape[0]}  ({time.time() - t_start:.0f}s of features)")

    # ---- the deployed INT8 model ------------------------------------------
    import tensorflow as tf  # noqa: E402

    interp = tf.lite.Interpreter(model_path=str(OUT / "crynet_int8.tflite"))
    interp.allocate_tensors()
    i_d = interp.get_input_details()[0]
    o_d = interp.get_output_details()[0]
    s, z = i_d["quantization"]

    p = np.zeros(len(X), np.float32)
    for i in range(len(X)):
        q = np.clip(np.round(X[i] / s) + z, -128, 127).astype(np.int8)
        interp.set_tensor(i_d["index"], q[None, ..., None])
        interp.invoke()
        o = interp.get_tensor(o_d["index"]).astype(np.float32).reshape(-1)
        oq = (o - o_d["quantization"][1]) * o_d["quantization"][0]
        p[i] = float(np.asarray(oq).reshape(-1)[1])

    # ---- per clip ----------------------------------------------------------
    # A clip is judged by its most confident window: the hub classifies
    # 2 s windows, so one loud moment inside a 5 s clip is enough to make
    # it raise an alarm.
    per_clip = []
    for c in clips:
        ps = [float(p[i]) for i in c["windows"]]
        pmax = max(ps)
        per_clip.append({
            "category": c["category"],
            "group": group_of(c["category"]),
            "rms": c["rms"],
            "p_cry": pmax,
            "p_cry_mean": float(np.mean(ps)),
            "alarm": bool(pmax >= args.threshold),
            "reaches_model": bool(c["rms"] >= args.trigger_rms),
        })

    # ---- roll-ups ----------------------------------------------------------
    def rollup(keyfn, subset):
        out = {}
        for key in sorted({keyfn(c) for c in subset}):
            rows_k = [c for c in subset if keyfn(c) == key]
            reach = [c for c in rows_k if c["reaches_model"]]
            alarms = [c for c in reach if c["alarm"]]
            out[key] = {
                "clips": len(rows_k),
                "mean_p_cry": float(np.mean([c["p_cry"] for c in rows_k])),
                "max_p_cry": float(np.max([c["p_cry"] for c in rows_k])),
                "clips_reaching_model": len(reach),
                "alarms": len(alarms),
                "alarm_rate_over_reached": (len(alarms) / len(reach)
                                            if reach else 0.0),
                "alarm_rate_over_all": len(alarms) / len(rows_k) if rows_k else 0.0,
            }
        return out

    by_group = rollup(lambda c: c["group"], per_clip)
    by_category = rollup(lambda c: c["category"], per_clip)

    negatives = [c for c in per_clip if c["category"] not in CRY_CATEGORIES]
    n_reach = sum(1 for c in negatives if c["reaches_model"])
    n_alarm = sum(1 for c in negatives
                  if c["reaches_model"] and c["alarm"])

    report = {
        "source": "research/eval_esc50.py",
        "corpus": "ESC-50 (2,000 real-world clips, 50 categories)",
        "caveat": ("ESC-50's non-cry clips were part of the training corpus, "
                   "so these false-alarm rates are optimistic for those "
                   "categories; this is the category map, not the in-room "
                   "number"),
        "threshold": args.threshold,
        "trigger_rms": args.trigger_rms,
        "windows_per_clip": args.windows_per_clip,
        "windows": int(X.shape[0]),
        "clips": len(per_clip),
        "negatives": {
            "clips": len(negatives),
            "reaching_model": n_reach,
            "alarms": n_alarm,
            "alarm_rate_over_reached": (n_alarm / n_reach) if n_reach else 0.0,
        },
        "by_group": by_group,
        "by_category": by_category,
        "per_clip": per_clip,
    }
    Path(args.report).write_text(json.dumps(report, indent=2))

    # ---- print -------------------------------------------------------------
    print(f"\n=== ESC-50, by kind of sound ===")
    print(f"{'group':<18}{'clips':>7}{'reached':>9}{'alarms':>8}"
          f"{'alarm/reached':>15}{'max P(cry)':>12}")
    for g, r in by_group.items():
        print(f"{g:<18}{r['clips']:>7}{r['clips_reaching_model']:>9}"
              f"{r['alarms']:>8}{r['alarm_rate_over_reached']:>15.3f}"
              f"{r['max_p_cry']:>12.4f}")

    print(f"\n=== the ten worst categories by P(cry) ===")
    worst = sorted(by_category.items(), key=lambda kv: -kv[1]["max_p_cry"])[:10]
    for c, r in worst:
        print(f"{c:<24}{r['clips']:>5} clips  reached {r['clips_reaching_model']:>4}"
              f"  alarms {r['alarms']:>3}  max P {r['max_p_cry']:.4f}")

    print(f"\nnegatives: {n_alarm} alarms out of {n_reach} that reached the "
          f"model "
          f"({(n_alarm / n_reach * 100) if n_reach else 0:.2f} %)")
    print(f"wrote {args.report}")
    print(f"total {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
