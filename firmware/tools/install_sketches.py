#!/usr/bin/env python3
"""Copy the CryNet sketches into the Arduino sketchbook so the IDE can open them.

The Arduino IDE builds a sketch from its own folder, and the sketches live
in the repository, so they have to be copied into the sketchbook (the
"node_crynet" and "node_capture" folders) before they can be compiled and
uploaded. This copies them and prints what to do next.

Usage:
    python firmware/tools/install_sketches.py
    python firmware/tools/install_sketches.py --list
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKETCHES = ["node_crynet", "node_capture"]


def sketchbook() -> Path:
    return Path.home() / "Documents" / "Arduino"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="list the sketches and exit")
    ap.add_argument("--remove", action="store_true",
                    help="remove the sketches from the sketchbook instead")
    args = ap.parse_args()

    src_root = ROOT / "firmware" / "node"
    dst_root = sketchbook()

    if args.list:
        for name in SKETCHES:
            src = src_root / name
            dst = dst_root / name
            print(f"{name:<14} {'present' if (src / (name + '.ino')).is_file() else 'MISSING'}"
                  f"  ->  {dst}{' (installed)' if dst.is_dir() else ''}")
        return 0

    if not dst_root.is_dir():
        print(f"The sketchbook {dst_root} does not exist. Open the Arduino IDE "
              f"once so it creates it.", file=sys.stderr)
        return 1

    for name in SKETCHES:
        src = src_root / name
        dst = dst_root / name
        if not (src / (name + ".ino")).is_file():
            print(f"missing {src / (name + '.ino')}", file=sys.stderr)
            return 1
        if args.remove:
            if dst.is_dir():
                shutil.rmtree(dst)
            print(f"removed {dst}")
            continue
        if dst.is_dir():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"installed {dst}")

    print("\nIn the Arduino IDE: File > Open, pick the sketch, then select the "
          "board\n(ESP32C3 Dev Module), the right COM port, and press Upload.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
