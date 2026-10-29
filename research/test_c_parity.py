"""Standalone validation of the notebook's C front end.

Executes the real notebook cells (config + frontend + export + C source) with
stubbed training outputs, compiles out/dsp_crynet.c and compares the C log-Mel
against the Python log-Mel on a synthetic probe.

    python test_c_parity.py
"""
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
NB = ROOT / "notebooks" / "crynet_training.ipynb"
WORK = ROOT / "research" / "_parity"
OUT = WORK / "out"
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

MARKERS = {
    "config": "CELL 1 — Environment",
    "frontend": "CELL 4 — The audio front end",
    "export": "CELL 19 — Export the deployment artifacts",
    "csource": "CELL 20 — The C reference implementation",
}

nb = json.loads(NB.read_text(encoding="utf-8"))
srcs = {}
for c in nb["cells"]:
    if c["cell_type"] != "code":
        continue
    s = "\n".join(c["source"])
    for k, m in MARKERS.items():
        if m in s:
            srcs[k] = s

missing = set(MARKERS) - set(srcs)
if missing:
    raise SystemExit(f"markers not found in notebook: {missing}")

ns = {"__name__": "__main__"}
import librosa  # noqa: E402  (the notebook imports it in its dependency cell)
ns["librosa"] = librosa

# the notebook's config cell resolves OUT/WORK from the environment, so point it
# at our sandbox before executing it
os.environ["CRYNET_OUT"] = str(OUT)
os.environ["CRYNET_WORK"] = str(WORK)
os.environ["CRYNET_CACHE"] = str(WORK / "cache")

# ---- stub the training outputs so the export cells run stand-alone ------------
ns["tflite_int8"] = bytes(range(256)) * 4
ns["IN_SCALE"], ns["IN_ZP"] = 0.012345678, 3
ns["OUT_SCALE"], ns["OUT_ZP"] = 0.00390625, -128
ns["THRESHOLD"] = 0.62
ns["BEST_KIND"] = "stub"


class _Model:
    def count_params(self):
        return 12345


ns["BEST_MODEL"] = _Model()
ns["res_val"] = {"auc": 0.9, "test_auc": 0.9, "cross_auc": 0.9, "f1": 0.9,
                 "test_f1": 0.9, "cross_f1": 0.9, "recall": 0.9, "precision": 0.9}
ns["res_test"] = dict(ns["res_val"])
ns["res_cross"] = dict(ns["res_val"])
ns["res_int8"] = dict(ns["res_val"])
ns["res_f32"] = dict(ns["res_val"])
ns["METRICS"] = {"stub": {"kind": "stub", "params": 12345, "val_auc": 0.9,
                          "test_auc": 0.9, "cross_auc": 0.9}}

ns["OUT"] = OUT
ns["WORK"] = WORK

for key in ("config", "frontend", "export", "csource"):
    print(f"\n>>> executing notebook cell: {key}")
    exec(compile(srcs[key], f"<{key}>", "exec"), ns)

N_SAMPLES = ns["N_SAMPLES"]
N_FRAMES = ns["N_FRAMES"]
N_MELS = ns["N_MELS"]
log_mel = ns["log_mel"]

# ---- compile the C -----------------------------------------------------------
CC = [sys.executable, "-m", "ziglang", "cc"]
exe = WORK / "dsp_test.exe"
cmd = CC + ["-O2", "-DCRYNET_SELFTEST", "-I", str(OUT), "-o", str(exe),
            str(OUT / "dsp_crynet.c"), "-lm"]
print("\n>>> compiling:", " ".join(cmd))
env = dict(os.environ)
env.setdefault("ZIG_GLOBAL_CACHE_DIR", str(WORK / "zigcache"))
env.setdefault("ZIG_LOCAL_CACHE_DIR", str(WORK / "zigcache_local"))
r = subprocess.run(cmd, capture_output=True, text=True, env=env)
if r.returncode != 0:
    print(r.stdout[-4000:])
    print(r.stderr[-4000:])
    raise SystemExit("COMPILE FAILED")
print("compiled OK")

# ---- parity on several probes ------------------------------------------------
rs = np.random.default_rng(7)
t = np.arange(N_SAMPLES) / ns["SR"]
probes = {
    "sine+harmonic": (0.35 * np.sin(2 * np.pi * 420 * t)
                      + 0.12 * np.sin(2 * np.pi * 1350 * t)
                      + 0.02 * rs.standard_normal(N_SAMPLES)),
    "noise": 0.05 * rs.standard_normal(N_SAMPLES),
    "dc_offset_cry": (0.3 * np.sin(2 * np.pi * 300 * t) + 0.05 * rs.standard_normal(N_SAMPLES)),
    "silence": np.zeros(N_SAMPLES),
}

worst = 0.0
for name, sig in probes.items():
    pcm16 = (np.clip(sig, -1, 1) * 32767).astype(np.int16)
    if name == "dc_offset_cry":
        pcm16 = (pcm16 + 18000).astype(np.int16)      # emulate the INMP441 bias
    raw = WORK / "probe.s16le"
    raw.write_bytes(pcm16.tobytes())
    r = subprocess.run([str(exe), str(raw)], capture_output=True, text=True, cwd=str(WORK))
    if r.returncode != 0:
        print(r.stderr[:800])
        raise SystemExit("parity binary failed")
    mel_c = np.fromfile(WORK / "mel_c.bin", dtype=np.float32).reshape(N_FRAMES, N_MELS)
    mel_py = log_mel(pcm16.astype(np.float32) / 32768.0)
    d = float(np.abs(mel_c - mel_py).max())
    worst = max(worst, d)
    print(f"  {name:16s} max|C-Python| = {d:.3e}   "
          f"mel range C [{mel_c.min():+.3f},{mel_c.max():+.3f}] "
          f"Py [{mel_py.min():+.3f},{mel_py.max():+.3f}]")

print(f"\nworst deviation over all probes: {worst:.3e}")
print("VERDICT:", "PASS — C front end matches training"
      if worst < 1e-2 else "FAIL — C and Python disagree")
