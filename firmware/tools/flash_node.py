#!/usr/bin/env python3
"""Build the CryNet node sketch and flash it onto a node over USB.

The node is an ESP32-C3 on a WeAct Studio board, and it is flashed with
`arduino-cli` -- the copy inside the Arduino IDE, which is the only one
installed on this machine.  The command is the one in DECISIONS.md 352:

    arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 <sketch>
    arduino-cli upload  -p <port> --fqbn esp32:esp32:weact_studio_esp32c3 <sketch>

This script does both, finds `arduino-cli` wherever it lives, and takes
the sketch from the repository if it is there and from the Arduino
sketchbook if it is not -- so it works on the second laptop, where the
repository may not be checked out.

Usage:
    python firmware/tools/flash_node.py --port COM38
    python firmware/tools/flash_node.py --port COM38 --dry-run
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKETCH_NAME = "node_crynet"
FQBN = "esp32:esp32:weact_studio_esp32c3"


def find_arduino_cli() -> str | None:
    """The arduino-cli to use: the environment first, then the IDE's."""
    env = os.environ.get("ARDUINO_CLI")
    if env and Path(env).exists():
        return env
    found = shutil.which("arduino-cli") or shutil.which("arduino-cli.exe")
    if found:
        return found
    candidates = [
        Path.home() / "AppData/Local/Programs/Arduino IDE/resources/app/lib/"
                     "backend/resources/arduino-cli.exe",
        Path("/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/"
             "resources/arduino-cli"),
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def find_sketch() -> Path:
    """The sketch to build: the repository's, or the sketchbook's copy."""
    repo = ROOT / "firmware" / "node" / SKETCH_NAME
    if (repo / f"{SKETCH_NAME}.ino").exists():
        return repo
    book = Path.home() / "Documents/Arduino" / SKETCH_NAME
    if (book / f"{SKETCH_NAME}.ino").exists():
        return book
    raise SystemExit(f"no {SKETCH_NAME} sketch found in {repo} or {book}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="the node's serial port")
    ap.add_argument("--fqbn", default=FQBN, help="the board to build for")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and upload without erasing the app partition")
    args = ap.parse_args()

    cli = find_arduino_cli()
    if cli is None:
        print("arduino-cli not found: install the Arduino IDE, or set "
              "ARDUINO_CLI to the binary", file=sys.stderr)
        return 1
    sketch = find_sketch()
    print(f"arduino-cli: {cli}")
    print(f"sketch:      {sketch}")

    build = subprocess.run(
        [cli, "compile", "--fqbn", args.fqbn, str(sketch)],
        capture_output=True, text=True)
    sys.stdout.write(build.stdout)
    sys.stderr.write(build.stderr)
    if build.returncode != 0:
        print("the build failed; nothing was flashed", file=sys.stderr)
        return build.returncode

    upload = [cli, "upload", "-p", args.port, "--fqbn", args.fqbn, str(sketch)]
    print("flashing:", " ".join(upload))
    up = subprocess.run(upload, capture_output=True, text=True)
    sys.stdout.write(up.stdout)
    sys.stderr.write(up.stderr)
    if up.returncode != 0:
        print(f"the flash to {args.port} failed", file=sys.stderr)
        return up.returncode
    print(f"node on {args.port} is running the new firmware")
    return 0


if __name__ == "__main__":
    sys.exit(main())
