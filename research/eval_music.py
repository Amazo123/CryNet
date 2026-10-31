#!/usr/bin/env python3
"""Does the deployed model mistake music for a cry?

The training corpus has no music in it at all: ICD brings cries, VoxCeleb
speech, DASEE domestic noise, human non-speech, cat meows and silence;
the supplementary sets are cries, ESC-50 and snoring.  ESC-50 itself has
no music either.  So the model's behaviour on music was neither trained
nor measured — and a nursery with a radio or a television is exactly the
case the demo will contain.

This script measures it.  It runs the *deployed* INT8 model — the very
file that is flashed onto the hub — over a music corpus (GTZAN, ten
genres), through the notebook's own frozen front end, and reports, per
genre and overall:

  * the peak RMS of each clip and whether it would reach the classifier
    (the hub only pulls a window when the node's 100 ms RMS reaches
    CRYNET_TRIGGER_RMS, 0.030),
  * the model's P(cry),
  * whether the model would have raised an alarm (P >= the deployed
    threshold, 0.95).

The same numbers, for the same reason, are the ones the hub produces.

Usage:
    python research/eval_music.py
    python research/eval_music.py --max-clips 200
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
CACHE = ROOT / "research" / "_cache"

DEFAULT_ZIPS = [
    CACHE / "gtzan__carlthome_gtzan-genre-collection.zip",
]

sys.path.insert(0, str(ROOT / "research"))
from verify_int8_parity import notebook_namespace  # noqa: E402


def find_corpus() -> Path | None:
    for p in DEFAULT_ZIPS:
        if p.is_file():
            return p
    return None


def members_of(path: Path):
    """Every clip in the archive, with the genre read off the folder name.

    GTZAN ships as Sun/NeXT AU (libsndfile reads it), some copies as WAV.
    """
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if name.lower().endswith((".wav", ".au")):
                    genre = Path(name).parent.name.lower()
                    yield name, genre, z.read(name)
    else:
        import tarfile
        with tarfile.open(path) as t:
            for m in t.getmembers():
                if m.isfile() and m.name.lower().endswith((".wav", ".au")):
                    f = t.extractfile(m)
                    if f is None:
                        continue
                    yield m.name, Path(m.name).parent.name.lower(), f.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", help="the archive to read; auto-detected if omitted")
    ap.add_argument("--max-clips", type=int, default=0)
    ap.add_argument("--windows-per-clip", type=int, default=2)
    ap.add_argument("--threshold", type=float, default=0.95)
    ap.add_argument("--trigger-rms", type=float, default=0.030)
    ap.add_argument("--report", default=str(OUT / "eval_music.json"))
    args = ap.parse_args()

    corpus = Path(args.corpus) if args.corpus else find_corpus()
    if corpus is None or not corpus.is_file():
        print(f"no music corpus found; looked for {DEFAULT_ZIPS}")
        return 1

    t_start = time.time()
    ns = notebook_namespace()
    log_mel = ns["log_mel"]
    take_windows = ns["take_windows"]
    decode = ns["decode"]

    feats, clips, skipped = [], [], 0
    for name, genre, raw in members_of(corpus):
        if args.max_clips and len(clips) >= args.max_clips:
            break
        x = decode(raw)
        if x is None:
            skipped += 1
            continue
        windows = take_windows(x, args.windows_per_clip, None, mode="center")
        first = len(feats)
        for w in windows:
            feats.append(log_mel(w))
        clips.append({
            "genre": genre,
            "file": Path(name).name,
            "rms": float(np.sqrt(np.mean(x.astype(np.float64) ** 2))),
            "windows": list(range(first, len(feats))),
        })
        if len(clips) % 100 == 0:
            print(f"  {len(clips)} clips", flush=True)
    if skipped:
        print(f"warning: {skipped} clip(s) skipped")

    X = np.stack(feats).astype(np.float32)
    print(f"clips: {len(clips)}  windows: {X.shape[0]}  "
          f"({time.time() - t_start:.0f}s of features)")

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

    per_clip = []
    for c in clips:
        ps = [float(p[i]) for i in c["windows"]]
        pmax = max(ps)
        per_clip.append({
            "genre": c["genre"],
            "file": c["file"],
            "rms": c["rms"],
            "p_cry": pmax,
            "p_cry_mean": float(np.mean(ps)),
            "alarm": bool(pmax >= args.threshold),
            "reaches_model": bool(c["rms"] >= args.trigger_rms),
        })

    def stats(rows):
        reach = [c for c in rows if c["reaches_model"]]
        alarms = [c for c in reach if c["alarm"]]
        return {
            "clips": len(rows),
            "mean_p_cry": float(np.mean([c["p_cry"] for c in rows])) if rows else 0.0,
            "max_p_cry": float(np.max([c["p_cry"] for c in rows])) if rows else 0.0,
            "clips_reaching_model": len(reach),
            "alarms": len(alarms),
            "alarm_rate_over_reached": (len(alarms) / len(reach) if reach else 0.0),
            "alarm_rate_over_all": (len(alarms) / len(rows) if rows else 0.0),
        }

    by_genre = {}
    for genre in sorted({c["genre"] for c in per_clip}):
        by_genre[genre] = stats([c for c in per_clip if c["genre"] == genre])

    overall = stats(per_clip)
    # the loudest tenth of the corpus — the music that would sit above the
    # hub's trigger most easily
    order = sorted(per_clip, key=lambda c: -c["rms"])
    loud = order[: max(1, len(order) // 10)]
    loud_stats = stats(loud)

    report = {
        "source": "research/eval_music.py",
        "corpus": corpus.name,
        "caveat": ("no music was in the training corpus at all, so these "
                   "numbers are the model's behaviour on music it has never "
                   "seen — neither trained nor tuned for it"),
        "threshold": args.threshold,
        "trigger_rms": args.trigger_rms,
        "windows_per_clip": args.windows_per_clip,
        "clips": len(per_clip),
        "windows": int(X.shape[0]),
        "overall": overall,
        "loudest_decile": loud_stats,
        "by_genre": by_genre,
        "per_clip": per_clip,
    }
    Path(args.report).write_text(json.dumps(report, indent=2))

    print(f"\n=== music, by genre ===")
    print(f"{'genre':<18}{'clips':>7}{'reached':>9}{'alarms':>8}"
          f"{'alarm/reached':>15}{'max P(cry)':>12}")
    for g, r in by_genre.items():
        print(f"{g:<18}{r['clips']:>7}{r['clips_reaching_model']:>9}"
              f"{r['alarms']:>8}{r['alarm_rate_over_reached']:>15.3f}"
              f"{r['max_p_cry']:>12.4f}")
    print(f"\noverall: {overall['alarms']} alarms out of "
          f"{overall['clips_reaching_model']} that reached the model "
          f"({overall['alarm_rate_over_reached'] * 100:.2f} %)")
    print(f"loudest tenth: {loud_stats['alarms']}/{loud_stats['clips_reaching_model']} "
          f"({loud_stats['alarm_rate_over_reached'] * 100:.2f} %)")
    print(f"wrote {args.report}")
    print(f"total {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
