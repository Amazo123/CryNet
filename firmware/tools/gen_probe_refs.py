#!/usr/bin/env python3
"""Generate the on-device verification references for the CryNet front end.

Runs the *notebook's own* log-Mel front end (extracted from
notebooks/crynet_training.ipynb) over four closed-form probes, quantises
the result exactly as the firmware does, and writes

    firmware/hub_infer/components/crynet_dsp/include/crynet_probe_refs.h

The firmware then reproduces the same probes on the ESP32-S3 and compares
its quantised features against these. This is the on-device half of the
host parity test in research/test_c_parity.py.

The probe definitions here must stay in step with firmware/hub_infer/src/
probes.c — the generated header records the PCM CRC of each probe so a
mismatch is visible immediately.

Usage:  python firmware/tools/gen_probe_refs.py
"""

from __future__ import annotations

import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
NB = ROOT / "notebooks" / "crynet_training.ipynb"
TABLES = ROOT / "research" / "out" / "crynet_tables.h"
DEST = ROOT / "firmware" / "hub_infer" / "components" / "crynet_dsp" / "include" / "crynet_probe_refs.h"

SR = 16000
N_SAMPLES = 32000
N_FRAMES = 81
N_MELS = 64

PROBE_NAMES = ["silence", "dc_bias", "tone", "noise"]


def load_front_end():
    """Pull the front-end cell out of the notebook and return its log_mel."""
    if not NB.exists():
        raise SystemExit(f"notebook not found: {NB}")

    nb = json.loads(NB.read_text(encoding="utf-8"))
    markers = {
        "config": "CELL 1 — Environment",
        "frontend": "CELL 4 — The audio front end",
    }
    srcs = {}
    for cell in nb["cells"]:
        if cell.get("cell_type") != "code":
            continue
        text = "\n".join(cell["source"])
        for key, marker in markers.items():
            if marker in text:
                srcs[key] = text
    missing = set(markers) - set(srcs)
    if missing:
        raise SystemExit(f"markers not found in {NB.name}: {missing}")

    import librosa  # noqa: E402  (the notebook imports it in its dependency cell)

    ns = {"__name__": "__main__", "librosa": librosa, "np": np}

    # The configuration cell resolves its directories from the environment,
    # so point it at a scratch directory before executing it.
    import os

    work = ROOT / "research" / "_probe"
    work.mkdir(parents=True, exist_ok=True)
    os.environ["CRYNET_OUT"] = str(work / "out")
    os.environ["CRYNET_WORK"] = str(work / "work")
    os.environ["CRYNET_CACHE"] = str(work / "cache")
    for sub in ("out", "work", "cache"):
        (work / sub).mkdir(parents=True, exist_ok=True)

    for key in ("config", "frontend"):
        exec(compile(srcs[key], f"<{key}>", "exec"), ns)

    if "log_mel" not in ns:
        raise SystemExit("the notebook's front end does not define log_mel()")
    return ns["log_mel"], ns


def quantisation():
    """Read the input scale / zero point from the generated tables."""
    text = TABLES.read_text(encoding="utf-8")
    if not TABLES.exists():
        raise SystemExit(f"missing {TABLES} — run the notebook and place its out/ here")
    scale = float(re.search(r"#define\s+CRYNET_IN_SCALE\s+([0-9.eE+-]+)", text).group(1))
    zp = int(re.search(r"#define\s+CRYNET_IN_ZP\s+(-?\d+)", text).group(1))
    return scale, zp


def clip(v):
    return max(-1.0, min(1.0, v))


def to_pcm(sig):
    """float in [-1, 1] -> int16, truncating toward zero (matches the C)."""
    pcm = (np.clip(sig, -1.0, 1.0) * 32767.0).astype(np.int16)
    return pcm


def probe_pcm(index):
    if index == 0:
        return np.zeros(N_SAMPLES, dtype=np.int16)
    if index == 1:
        return np.full(N_SAMPLES, 18000, dtype=np.int16)
    if index == 2:
        t = np.arange(N_SAMPLES) / SR
        x = 0.35 * np.sin(2.0 * math.pi * 420.0 * t) + 0.12 * np.sin(2.0 * math.pi * 1350.0 * t)
        return to_pcm(x)
    if index == 3:
        # 32-bit LCG, 24 high bits -> uniform [0, 1)
        state = np.uint32(12345)
        out = np.empty(N_SAMPLES, dtype=np.float64)
        for i in range(N_SAMPLES):
            state = np.uint32(1103515245) * state + np.uint32(12345)
            out[i] = (float((state >> np.uint32(8)) & np.uint32(0x00FFFFFF))) / 16777216.0
        return to_pcm(0.05 * (2.0 * out - 1.0))
    raise ValueError(index)


def main() -> int:
    log_mel, ns = load_front_end()
    in_scale, in_zp = quantisation()

    n_frames = int(ns.get("N_FRAMES", N_FRAMES))
    n_mels = int(ns.get("N_MELS", N_MELS))
    if (n_frames, n_mels) != (N_FRAMES, N_MELS):
        raise SystemExit(f"unexpected feature geometry {n_frames}x{n_mels}")

    lines = []
    lines.append("/*")
    lines.append(" * CryNet — expected probe features (GENERATED, do not edit).")
    lines.append(" *")
    lines.append(" * Produced by firmware/tools/gen_probe_refs.py from the training")
    lines.append(" * notebook's own log-Mel front end, quantised exactly as the")
    lines.append(" * firmware quantises. The ESP32-S3 reproduces the same probes and")
    lines.append(" * compares against these bytes, which is the on-device half of the")
    lines.append(" * host parity test.")
    lines.append(" *")
    lines.append(f" * input quantisation: scale {in_scale!r}, zero point {in_zp}")
    lines.append(" */")
    lines.append("")
    lines.append("#ifndef CRYNET_PROBE_REFS_H")
    lines.append("#define CRYNET_PROBE_REFS_H")
    lines.append("")
    lines.append("#include <stdint.h>")
    lines.append("")
    lines.append(f"#define CRYNET_PROBE_REF_COUNT      {len(PROBE_NAMES)}")
    lines.append(f"#define CRYNET_PROBE_REF_BYTES       {N_FRAMES * N_MELS}")
    lines.append("")

    crc_rows = []
    for idx, name in enumerate(PROBE_NAMES):
        pcm = probe_pcm(idx)
        pcm_crc = zlib.crc32(pcm.tobytes()) & 0xFFFFFFFF

        mel = np.asarray(log_mel(pcm.astype(np.float32) / 32768.0), dtype=np.float32)
        if mel.shape != (N_FRAMES, N_MELS):
            raise SystemExit(f"probe {name}: unexpected feature shape {mel.shape}")

        q = np.round(mel / in_scale) + in_zp
        q = np.clip(q, -128, 127).astype(np.int8).reshape(-1)
        feat_crc = zlib.crc32(q.tobytes()) & 0xFFFFFFFF
        crc_rows.append((name, pcm_crc, feat_crc, float(mel.min()), float(mel.max())))

        values = [str(int(v)) for v in q]
        lines.append(f"/* {name}: pcm_crc32 0x{pcm_crc:08x}, feature_crc32 0x{feat_crc:08x} */")
        lines.append(f"static const int8_t crynet_probe_ref_{name}[CRYNET_PROBE_REF_BYTES] = {{")
        for i in range(0, len(values), 64):
            lines.append("    " + ", ".join(values[i:i + 64]) + ",")
        lines.append("};")
        lines.append("")

    lines.append("static const int8_t *const crynet_probe_refs[CRYNET_PROBE_REF_COUNT] = {")
    for name in PROBE_NAMES:
        lines.append(f"    crynet_probe_ref_{name},")
    lines.append("};")
    lines.append("")
    lines.append("static const uint32_t crynet_probe_ref_pcm_crc[CRYNET_PROBE_REF_COUNT] = {")
    lines.append("    " + ", ".join(f"0x{crc:08x}" for _, crc, _, _, _ in crc_rows))
    lines.append("};")
    lines.append("")
    lines.append("static const uint32_t crynet_probe_ref_feature_crc[CRYNET_PROBE_REF_COUNT] = {")
    lines.append("    " + ", ".join(f"0x{crc:08x}" for _, _, crc, _, _ in crc_rows))
    lines.append("};")
    lines.append("")
    lines.append("#endif /* CRYNET_PROBE_REFS_H */")

    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {DEST.relative_to(ROOT)}  ({DEST.stat().st_size} bytes)")
    print(f"  input quantisation: scale {in_scale}, zero point {in_zp}")
    for name, pcm_crc, feat_crc, lo, hi in crc_rows:
        print(f"  {name:8s} pcm_crc 0x{pcm_crc:08x}  feature_crc 0x{feat_crc:08x}  "
              f"mel [{lo:+.2f}, {hi:+.2f}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
