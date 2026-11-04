"""Fetch just the Common Voice shards (in parallel with the FSD50K fetch).

    python -I get_cv_shards.py
"""
from pathlib import Path

from huggingface_hub import hf_hub_download

DEST = Path(__file__).resolve().parent / "raw" / "cv"
DEST.mkdir(parents=True, exist_ok=True)
CV = "DTU54DL/common-voice-test16k"

for name in ("data/test-00000-of-00002-f6adb388287d5d09.parquet",
             "data/test-00001-of-00002-d49b1986b290159e.parquet"):
    try:
        p = hf_hub_download(CV, name, repo_type="dataset", local_dir=str(DEST))
        print(f"ok {name} {Path(p).stat().st_size/1e6:.1f} MB", flush=True)
    except Exception as e:
        print(f"FAIL {name}: {e}", flush=True)
print("done")
