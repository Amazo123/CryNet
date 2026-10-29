"""Run the generated notebook locally (cell by cell) — used to validate it end to end.

    CRYNET_FAST=1 python run_notebook_local.py
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "crynet_training.ipynb"

CACHE = ROOT / "research" / "_cache"
WORK = ROOT / "research" / "_work"
OUT = ROOT / "research" / "_out"
for d in (CACHE, WORK, OUT):
    d.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("CRYNET_FAST", "1")
os.environ.setdefault("CRYNET_CACHE", str(CACHE))
os.environ.setdefault("CRYNET_WORK", str(WORK))
os.environ.setdefault("CRYNET_OUT", str(OUT))

nb = json.loads(NB.read_text(encoding="utf-8"))
ns = {"__name__": "__main__", "__file__": str(NB)}

only = os.environ.get("CRYNET_ONLY")
for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    if only and str(i) not in only.split(","):
        continue
    src = "\n".join(cell["source"])
    print(f"\n{'='*70}\n== CELL {i}\n{'='*70}", flush=True)
    t0 = time.time()
    try:
        exec(compile(src, f"<cell {i}>", "exec"), ns)
    except Exception:
        traceback.print_exc()
        print(f"\n!!! cell {i} FAILED after {time.time()-t0:.1f}s", flush=True)
        sys.exit(1)
    print(f"-- cell {i} ok ({time.time()-t0:.1f}s)", flush=True)

print("\nlocal run complete")
