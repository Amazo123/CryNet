#!/usr/bin/env python3
"""Check that the firmware and the training artifacts agree.

Run this after dropping a new set of Kaggle outputs into research/out/ and
before building the firmware. It catches the failure mode that is easy to
miss: the notebook re-calibrates the threshold and re-derives the
quantisation scales on every run, so the constants mirrored into the
firmware headers go stale silently.

Checks
  1. research/out/crynet_int8.tflite SHA-256 == deploy_config.json model_sha256
  2. model_data.h embeds exactly model_bytes bytes
  3. crynet_tables.h defines == the macros mirrored into crynet_model.h
  4. deploy_config.json agrees with crynet_tables.h on scale/zero-point/threshold
  5. the staged copies under firmware/hub_infer/components are byte-identical
     to the ones in research/out/

Exit code 0 = consistent, 1 = drift found (the message says what moved).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "out"
FW = ROOT / "firmware" / "hub_infer" / "components"

TABLES_H = OUT / "crynet_tables.h"
MODEL_H = OUT / "model_data.h"
TFLITE = OUT / "crynet_int8.tflite"
CONFIG = OUT / "deploy_config.json"

STAGED = {
    FW / "crynet_model" / "include" / "crynet_tables.h": TABLES_H,
    FW / "crynet_model" / "include" / "model_data.h": MODEL_H,
    FW / "crynet_model" / "include" / "deploy_config.json": CONFIG,
    FW / "crynet_dsp" / "reference" / "dsp_crynet.c": OUT / "dsp_crynet.c",
    FW / "crynet_dsp" / "reference" / "dsp_crynet.h": OUT / "dsp_crynet.h",
}

# macro in crynet_tables.h  ->  macro in crynet_model.h
MIRRORED = {
    "CRYNET_THRESHOLD": "CRYNET_THRESHOLD",
    "CRYNET_SILENCE_RMS": "CRYNET_SILENCE_RMS_GATE",
    "CRYNET_IN_SCALE": "CRYNET_INPUT_SCALE",
    "CRYNET_IN_ZP": "CRYNET_INPUT_ZERO_POINT",
    "CRYNET_OUT_SCALE": "CRYNET_OUTPUT_SCALE",
    "CRYNET_OUT_ZP": "CRYNET_OUTPUT_ZERO_POINT",
    "CRYNET_N_SAMPLES": "CRYNET_N_SAMPLES",
    "CRYNET_N_FRAMES": "CRYNET_N_FRAMES",
    "CRYNET_N_MELS": "CRYNET_N_MELS",
}


def fail(problems: list[str], message: str) -> None:
    problems.append(message)


def defines(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for name, value in re.findall(r"#define\s+(CRYNET_\w+)\s+([^\r\n/]+)", text):
        out[name] = value.strip().rstrip(")").strip() if False else value.strip()
    return out


def numeric(value: str) -> float:
    """Evaluate a C constant expression that is just a number (or a negation)."""
    v = value.strip().rstrip("f").strip()
    if v.startswith("(") and v.endswith(")"):
        v = v[1:-1]
    return float(v)


def main() -> int:
    problems: list[str] = []

    for p in (TABLES_H, MODEL_H, TFLITE, CONFIG):
        if not p.exists():
            print(f"FAIL: missing {p}")
            return 1

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    tables = defines(TABLES_H)
    model_header = (FW / "crynet_model" / "include" / "crynet_model.h").read_text(
        encoding="utf-8"
    )
    mirrored = defines(FW / "crynet_model" / "include" / "crynet_model.h")

    # 1. model hash
    digest = hashlib.sha256(TFLITE.read_bytes()).hexdigest()
    if digest != config["model_sha256"]:
        fail(problems, f"crynet_int8.tflite sha256 {digest} != deploy_config {config['model_sha256']}")

    # 2. embedded byte count
    blob = MODEL_H.read_text(encoding="utf-8")
    body = blob.split("crynet_model[] = {", 1)[-1].split("};", 1)[0]
    n_bytes = len(re.findall(r"0x[0-9a-fA-F]{2}", body))
    if n_bytes != config["model_bytes"]:
        fail(problems, f"model_data.h holds {n_bytes} bytes, deploy_config says {config['model_bytes']}")
    if n_bytes != TFLITE.stat().st_size:
        fail(problems, f"model_data.h holds {n_bytes} bytes, tflite file is {TFLITE.stat().st_size}")

    # 3. mirrored macros
    for src, dst in MIRRORED.items():
        if src not in tables:
            fail(problems, f"crynet_tables.h does not define {src}")
            continue
        if dst not in mirrored:
            fail(problems, f"crynet_model.h does not define {dst}")
            continue
        a, b = numeric(tables[src]), numeric(mirrored[dst])
        if abs(a - b) > 1e-9:
            fail(problems, f"{src} = {a} in crynet_tables.h but {dst} = {b} in crynet_model.h")

    # 4. deploy_config vs tables
    inp = config["input"]
    if abs(float(inp["scale"]) - numeric(tables["CRYNET_IN_SCALE"])) > 1e-8:
        fail(problems, "deploy_config input scale disagrees with crynet_tables.h")
    if int(inp["zero_point"]) != int(numeric(tables["CRYNET_IN_ZP"])):
        fail(problems, "deploy_config input zero_point disagrees with crynet_tables.h")
    if abs(float(config["decision"]["threshold"]) - numeric(tables["CRYNET_THRESHOLD"])) > 1e-6:
        fail(problems, "deploy_config threshold disagrees with crynet_tables.h")
    if abs(float(config["decision"]["silence_rms_gate"]) - numeric(tables["CRYNET_SILENCE_RMS"])) > 1e-9:
        fail(problems, "deploy_config silence gate disagrees with crynet_tables.h")
    if list(inp["shape"]) != [1, 81, 64, 1]:
        fail(problems, f"unexpected input shape {inp['shape']}")
    if config["tflm_kernel_check"] != "ok":
        fail(problems, "deploy_config does not confirm the TFLite Micro kernel check")

    # 5. staged copies are current
    for staged, source in STAGED.items():
        if not staged.exists():
            fail(problems, f"staged copy missing: {staged}")
        elif staged.read_bytes() != source.read_bytes():
            fail(problems, f"staged copy is stale: {staged.relative_to(ROOT)} != {source.relative_to(ROOT)}")

    if problems:
        print("ARTIFACT DRIFT DETECTED")
        for p in problems:
            print(f"  - {p}")
        print("\nFix by re-staging research/out/ into firmware/hub_infer/components/ and "
              "updating the mirrored macros in crynet_model.h.")
        return 1

    print("OK  artifacts, firmware constants and deploy_config all agree")
    print(f"    model      : {n_bytes} bytes  sha256 {digest[:16]}...")
    print(f"    threshold  : {numeric(tables['CRYNET_THRESHOLD'])}")
    print(f"    input quant: scale {numeric(tables['CRYNET_IN_SCALE'])} zp {int(numeric(tables['CRYNET_IN_ZP']))}")
    print(f"    staged     : {len(STAGED)} files identical to research/out/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
