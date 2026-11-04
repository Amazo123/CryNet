#!/usr/bin/env python3
"""Does the deployed model mistake a room full of talking for a cry?

The corpus the model was trained on holds speech — 4,963 VoxCeleb clips
that came in with the ICD negatives — but **no loud speech**: the room
where the bench lives is quiet, and the one measured conversation
window scored 0.9727 (see SYSTEM_UPDATE.md), which is below the
saturation the hub announces on (0.9900) but not by much.

The user has nobody around to record a conversation, so the speech is
**sourced online** instead:

  * **FSD50K (16 kHz mirror)** — real-world recordings with class labels.
    The speech classes are the point: `Speech`, `Child_speech_and_kid_
    speaking`, `Conversation`, `Chatter`, `Crowd`, `Human_voice`,
    `Male_speech_and_man_speaking`, `Female_speech_and_woman_speaking`,
    `Laughter`, `Giggle`, `Singing`, `Human_group_actions`.  A nursery has
    all of these, and a child's voice is the closest thing to a baby's
    cry that a real room contains.
  * **Common Voice (16 kHz)** — real read speech from thousands of
    speakers with accents, recorded close to the microphone in quiet
    rooms: the closest thing to a person talking in the next room.

Both are read from the **eval / validation / test** partitions, which the
model has never seen, so these numbers are the model's behaviour on
speech it has not been trained on.

This script runs the *deployed* INT8 model — the very file flashed onto
the hub — through the notebook's own frozen front end and reports:

  * the peak RMS of each clip and whether it would reach the classifier
    (the hub pulls a window when the node's 100 ms RMS reaches 0.030),
  * the model's P(cry) on the loudest window of the clip,
  * whether the model would have raised an alarm at the deployed
    threshold (0.95) and at the hub's saturation (0.99).

Usage:
    python research/eval_speech.py
    python research/eval_speech.py --max-clips 400 --windows-per-clip 3
"""

from __future__ import annotations

import os

# One thread for the parquet reads: this machine runs the bench, the
# downloads and the model at the same time, and pyarrow's worker pool
# fails with "resource unavailable" when the machine is busy.
os.environ.setdefault("ARROW_NUM_THREADS", "1")

import argparse
import io
import json
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research" / "out"
RAW = ROOT / "research" / "loudspeech" / "raw"

sys.path.insert(0, str(ROOT / "research"))
from verify_int8_parity import notebook_namespace  # noqa: E402

sys.path.insert(0, str(ROOT / "research" / "loudspeech"))
from speech_common import (AMBIGUOUS_CLASSES, FSD_MEASURE_PARTITIONS,  # noqa: E402
                           SPEECH_CLASSES, cv_half, cv_id)


def fsd50k_rows(partitions):
    """Every clip of the given FSD50K partitions, with its class labels."""
    import pyarrow.parquet as pq

    rows = []
    for shard in sorted((RAW / "fsd").rglob("*.parquet")):
        tbl = pq.read_table(shard, columns=["audio", "labels", "duration_seconds",
                                            "source_partition", "freesound_id", "title"],
                           use_threads=False)
        labels = tbl.column("labels").to_pylist()
        parts = tbl.column("source_partition").to_pylist()
        audio = tbl.column("audio").to_pylist()
        dur = tbl.column("duration_seconds").to_pylist()
        fids = tbl.column("freesound_id").to_pylist()
        titles = tbl.column("title").to_pylist()
        for i, ls in enumerate(labels):
            if parts[i] not in partitions:
                continue
            keep = [l for l in ls if l in SPEECH_CLASSES or l in AMBIGUOUS_CLASSES]
            if not keep:
                continue
            blob = audio[i]["bytes"]
            if blob is None:
                continue
            rows.append({
                "source": "fsd50k",
                "raw": blob,
                "group": keep[0] if len(keep) == 1 else "+".join(sorted(keep)),
                "cls": keep[0],
                "partition": parts[i],
                "id": f"fsd{int(fids[i])}",
                "duration": float(dur[i]),
                "title": titles[i],
            })
    return rows


def common_voice_rows():
    """Every clip of the Common Voice **measurement** half.

    The mirror's test split is halved by a hash of the clip id: the other
    half is what the training corpus is built from, so nothing measured
    here was ever trained on.
    """
    import pyarrow.parquet as pq

    rows = []
    for shard in sorted((RAW / "cv").rglob("*.parquet")):
        tbl = pq.read_table(shard, use_threads=False)
        cols = tbl.column_names
        audio_col = "audio" if "audio" in cols else cols[0]
        accent_col = "accent" if "accent" in cols else None
        audio = tbl.column(audio_col).to_pylist()
        accents = tbl.column(accent_col).to_pylist() if accent_col else [""] * len(audio)
        for i, a in enumerate(audio):
            blob = a["bytes"] if isinstance(a, dict) else a
            if blob is None:
                continue
            cid = cv_id(shard.name, i)
            if cv_half(cid) != "measure":
                continue
            acc = accents[i] or "unspecified"
            rows.append({
                "source": "common_voice",
                "raw": blob,
                "group": f"cv_{acc.lower().replace(' ', '_')}",
                "cls": "cv_speech",
                "partition": "measure",
                "id": cid,
                "duration": 0.0,
                "title": "",
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-clips", type=int, default=0, help="0 = all of them")
    ap.add_argument("--windows-per-clip", type=int, default=3)
    ap.add_argument("--threshold", type=float, default=0.95, help="the deployed threshold")
    ap.add_argument("--saturation", type=float, default=0.99, help="the hub's announcement rule")
    ap.add_argument("--trigger-rms", type=float, default=0.030)
    ap.add_argument("--report", default=str(OUT / "eval_speech.json"))
    args = ap.parse_args()

    t_start = time.time()
    ns = notebook_namespace()
    log_mel = ns["log_mel"]
    take_windows = ns["take_windows"]
    decode = ns["decode"]

    rows = []
    for part in sorted(FSD_MEASURE_PARTITIONS):
        rows += fsd50k_rows({part})
    print(f"FSD50K speech-ish clips: {len(rows)}", flush=True)
    rows += common_voice_rows()
    print(f"plus Common Voice: {len(rows)} clips in total", flush=True)

    if args.max_clips:
        rows = rows[: args.max_clips]

    feats, clips, skipped = [], [], 0
    for r in rows:
        x = decode(r["raw"])
        if x is None:
            skipped += 1
            continue
        # the loudest window of the clip is the fairest test: a false alarm
        # is judged by the loudest moment of the speech, not a quiet one.
        # "center" with n windows starts them at the beginning, the middle
        # and the end of the clip.
        wins = take_windows(x, args.windows_per_clip, None, mode="center")
        first = len(feats)
        for w in wins:
            feats.append(log_mel(w))
        clips.append({
            "source": r["source"],
            "group": r["group"],
            "cls": r["cls"],
            "id": r["id"],
            "partition": r["partition"],
            "rms": float(np.sqrt(np.mean(x.astype(np.float64) ** 2))),
            "peak": float(np.max(np.abs(x))),
            "clipped": bool(np.max(np.abs(x)) > 0.999),
            "windows": list(range(first, len(feats))),
        })
        if len(clips) % 500 == 0:
            print(f"  {len(clips)} clips", flush=True)
    if skipped:
        print(f"warning: {skipped} clip(s) skipped")

    X = np.stack(feats).astype(np.float32)
    print(f"clips: {len(clips)}  windows: {X.shape[0]}", flush=True)

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
            **c,
            "p_cry": pmax,
            "p_cry_mean": float(np.mean(ps)),
            "alarm": bool(pmax >= args.threshold),
            "announces": bool(pmax >= args.saturation),
            "reaches_model": bool(c["rms"] >= args.trigger_rms),
            "ambiguous": c["cls"] in AMBIGUOUS_CLASSES,
        })

    def stats(rows_):
        reach = [c for c in rows_ if c["reaches_model"]]
        alarms = [c for c in reach if c["alarm"]]
        announce = [c for c in reach if c["announces"]]
        return {
            "clips": len(rows_),
            "mean_p_cry": float(np.mean([c["p_cry"] for c in rows_])) if rows_ else 0.0,
            "max_p_cry": float(np.max([c["p_cry"] for c in rows_])) if rows_ else 0.0,
            "clips_reaching_model": len(reach),
            "alarms_at_threshold": len(alarms),
            "announces_at_saturation": len(announce),
            "alarm_rate_over_reached": (len(alarms) / len(reach) if reach else 0.0),
            "announce_rate_over_reached": (len(announce) / len(reach) if reach else 0.0),
        }

    clear = [c for c in per_clip if not c["ambiguous"]]
    by_group = {}
    for g in sorted({c["group"] for c in clear}):
        by_group[g] = stats([c for c in clear if c["group"] == g])

    by_source = {}
    for s_ in sorted({c["source"] for c in clear}):
        by_source[s_] = stats([c for c in clear if c["source"] == s_])

    ambiguous = [c for c in per_clip if c["ambiguous"]]
    overall = stats(clear)
    order = sorted(clear, key=lambda c: -c["rms"])
    loud = order[: max(1, len(order) // 10)]

    report = {
        "source": "research/eval_speech.py",
        "corpora": {
            "fsd50k": "quinnlue/FSD50K-16k (eval + validation partitions, CC-BY)",
            "common_voice": "DTU54DL/common-voice-test16k (test split, MIT)",
        },
        "threshold": args.threshold,
        "saturation": args.saturation,
        "trigger_rms": args.trigger_rms,
        "windows_per_clip": args.windows_per_clip,
        "clips": len(per_clip),
        "windows": int(X.shape[0]),
        "overall": overall,
        "by_source": by_source,
        "loudest_decile": stats(loud),
        "ambiguous_cry_adjacent": stats(ambiguous),
        "ambiguous_classes": sorted(AMBIGUOUS_CLASSES),
        "by_group": by_group,
        "per_clip": per_clip,
    }
    Path(args.report).write_text(json.dumps(report, indent=2))

    print(f"\n=== speech, by source ===")
    print(f"{'source':<16}{'clips':>7}{'reached':>9}{'alarms':>8}{'announces':>11}"
          f"{'alarm/reached':>15}{'max P(cry)':>12}")
    for s_, r in by_source.items():
        print(f"{s_:<16}{r['clips']:>7}{r['clips_reaching_model']:>9}"
              f"{r['alarms_at_threshold']:>8}{r['announces_at_saturation']:>11}"
              f"{r['alarm_rate_over_reached']:>15.3f}{r['max_p_cry']:>12.4f}")
    print(f"\noverall (clear negatives): {overall['alarms_at_threshold']} alarms "
          f"and {overall['announces_at_saturation']} announcements out of "
          f"{overall['clips_reaching_model']} clips that reached the model "
          f"({overall['alarm_rate_over_reached']*100:.2f} % / "
          f"{overall['announce_rate_over_reached']*100:.2f} %)")
    print(f"loudest tenth: {stats(loud)['alarms_at_threshold']}/"
          f"{stats(loud)['clips_reaching_model']} "
          f"({stats(loud)['alarm_rate_over_reached']*100:.2f} %)")
    if ambiguous:
        print(f"cry-adjacent (reported separately): "
              f"{stats(ambiguous)['clips']} clips, "
              f"{stats(ambiguous)['alarms_at_threshold']} alarms, "
              f"max P(cry) {stats(ambiguous)['max_p_cry']:.4f}")

    print(f"\n=== per group (the worst 15 by max P(cry)) ===")
    worst = sorted(clear, key=lambda c: -c["p_cry"])[:15]
    print(f"{'group':<44}{'rms':>9}{'P(cry)':>9}{'alarm':>7}")
    for c in worst:
        print(f"{c['group'][:43]:<44}{c['rms']:>9.4f}{c['p_cry']:>9.4f}"
              f"{str(c['alarm']):>7}")
    print(f"\nwrote {args.report}")
    print(f"total {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
