"""Download the shards the speech work needs.

    python -I get_shards.py

FSD50K 16 kHz: the **dev** partition (the official training half — the
mirror calls it `train-*` and `validation-*`) and the **eval** partition
(never trained on).  Common Voice 16 kHz: the test split of the mirror,
which is split in half by a hash of the clip id — one half goes into the
training corpus, the other half is kept for measurement, so no clip is
ever both.
"""

from pathlib import Path

from huggingface_hub import hf_hub_download

DEST = Path(__file__).resolve().parent / "raw"
DEST.mkdir(parents=True, exist_ok=True)

FSD = "quinnlue/FSD50K-16k"
CV = "DTU54DL/common-voice-test16k"

WANT = [
    # FSD50K eval (measurement only)
    (FSD, "data/test-00000-of-00005.parquet", "fsd"),
    (FSD, "data/test-00001-of-00005.parquet", "fsd"),
    (FSD, "data/test-00002-of-00005.parquet", "fsd"),
    # FSD50K dev (training)
    (FSD, "data/validation-00000-of-00002.parquet", "fsd"),
    (FSD, "data/validation-00001-of-00002.parquet", "fsd"),
    *[(FSD, f"data/train-{i:05d}-of-00013.parquet", "fsd") for i in range(13)],
    # Common Voice (split in half: training / measurement)
    (CV, "data/test-00000-of-00002-f6adb388287d5d09.parquet", "cv"),
    (CV, "data/test-00001-of-00002-d49b1986b290159e.parquet", "cv"),
]

for repo, name, sub in WANT:
    target = DEST / sub
    target.mkdir(parents=True, exist_ok=True)
    if (target / name).exists():
        print(f"have {sub}/{name}", flush=True)
        continue
    try:
        p = hf_hub_download(repo, name, repo_type="dataset", local_dir=str(target))
        print(f"ok   {sub}/{name:52s} {Path(p).stat().st_size/1e6:8.1f} MB", flush=True)
    except Exception as e:
        print(f"FAIL {sub}/{name:52s} {e}", flush=True)
print("done")
