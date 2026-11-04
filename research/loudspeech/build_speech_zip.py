"""Build the speech corpus the retrain will use.

    python -I build_speech_zip.py [--limit 6000]

Reads the FSD50K 16 kHz shards in research/loudspeech/raw/fsd/ (the
**dev** partition — the official training half) and the Common Voice
shards in research/loudspeech/raw/cv/, and writes the speech clips into
one zip of 16 kHz mono WAV files under research/_cache/:

    speech/Speech__fsd12345.wav             FSD50K, dev partition
    speech/CV_canadian_english__cv_00000_000123.wav   Common Voice

The class is in the file name, so the notebook can read it off the name
and report per-class numbers.  Common Voice is split in half by a hash of
the clip id (see speech_common.cv_half): only the training half goes in
here, and the other half is left for measurement, so no clip is ever both
trained on and measured on.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import numpy as np

os.environ.setdefault("ARROW_NUM_THREADS", "1")

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "research" / "loudspeech" / "raw"
CACHE = ROOT / "research" / "_cache"

sys.path.insert(0, str(ROOT / "research" / "loudspeech"))
from speech_common import (AMBIGUOUS_CLASSES, FSD_TRAIN_PARTITIONS,  # noqa: E402
                           SPEECH_CLASSES, cv_half, cv_id)

import soundfile as sf  # noqa: E402


def _wav_bytes(x, sr=16000):
    pcm = (np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    sf.write(buf, pcm, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def fsd_clips():
    """Every speech clip of the FSD50K dev partition."""
    import pyarrow.parquet as pq

    for shard in sorted((RAW / "fsd").rglob("*.parquet")):
        tbl = pq.read_table(shard, columns=["audio", "labels", "source_partition",
                                            "freesound_id", "duration_seconds"],
                            use_threads=False)
        labels = tbl.column("labels").to_pylist()
        parts = tbl.column("source_partition").to_pylist()
        audio = tbl.column("audio").to_pylist()
        dur = tbl.column("duration_seconds").to_pylist()
        fids = tbl.column("freesound_id").to_pylist()
        for i, ls in enumerate(labels):
            if parts[i] not in FSD_TRAIN_PARTITIONS:
                continue
            keep = [l for l in ls if l in SPEECH_CLASSES]
            if not keep:
                continue
            blob = audio[i]["bytes"]
            if blob is None:
                continue
            yield (f"fsd{int(fids[i])}", keep[0], blob, float(dur[i]))


def cv_clips():
    """Every Common Voice clip of the training half."""
    import pyarrow.parquet as pq

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
            if cv_half(cid) != "train":
                continue
            acc = (accents[i] or "unspecified").lower().replace(" ", "_")
            yield (cid, f"CV_{acc}", blob, 0.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = all of them")
    ap.add_argument("--fsd-limit", type=int, default=0,
                    help="cap on the FSD50K clips (the nursery-relevant classes)")
    ap.add_argument("--cv-limit", type=int, default=0,
                    help="cap on the Common Voice clips (breadth of real speech)")
    ap.add_argument("--min-rms", type=float, default=0.0)
    ap.add_argument("--max-seconds", type=float, default=10.0,
                    help="clip a long recording; a nursery recording is not 3 minutes")
    ap.add_argument("--out", default=str(CACHE / "speech__fsd50k_speech.zip"))
    args = ap.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    kept = 0
    manifest = []
    counts = {}
    per_source = {"fsd50k": 0, "common_voice": 0}
    caps = {"fsd50k": args.fsd_limit, "common_voice": args.cv_limit}

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for source, gen in (("fsd50k", fsd_clips()), ("common_voice", cv_clips())):
            for cid, cls, blob, dur in gen:
                if args.limit and kept >= args.limit:
                    break
                if caps[source] and per_source[source] >= caps[source]:
                    break
                try:
                    x, sr = sf.read(io.BytesIO(blob), dtype="float32", always_2d=False)
                except Exception:
                    continue
                if x.ndim > 1:
                    x = x.mean(axis=1)
                if sr != 16000:
                    # The Common Voice mirror ships 32 and 48 kHz audio
                    # whatever its card says.  The front end wants 16 kHz,
                    # and resampling is what the notebook's own decoder
                    # does, so the two agree.
                    import librosa
                    x = librosa.resample(x, orig_sr=sr, target_sr=16000,
                                         res_type="soxr_hq")
                    sr = 16000
                if x.size < 16000:          # a second at least
                    continue
                if x.size > args.max_seconds * 16000:
                    x = x[: int(args.max_seconds * 16000)]
                rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
                if rms < args.min_rms:
                    continue
                name = f"speech/{cls}__{cid}.wav"
                z.writestr(name, _wav_bytes(x))
                manifest.append({"file": name, "class": cls, "source": source,
                                 "rms": rms, "duration": dur})
                counts[cls] = counts.get(cls, 0) + 1
                per_source[source] += 1
                kept += 1
                if kept % 500 == 0:
                    print(f"  {kept} clips", flush=True)
            if args.limit and kept >= args.limit:
                break

    meta = out.with_suffix(".json")
    meta.write_text(json.dumps({"clips": kept, "by_class": counts,
                                 "by_source": per_source,
                                 "manifest": manifest}, indent=2))
    print(f"wrote {out} ({out.stat().st_size/1e6:.1f} MB, {kept} clips)")
    for c, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"   {c:44s} {n:6d}")
    print(f"wrote {meta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
