#!/usr/bin/env python3
"""Make the vendored TFLite Micro port build against the vendored esp-nn.

The Espressif TFLite Micro port declares its ESP-NN dependency in
`idf_component.yml`:

    dependencies:
      idf:
        version: ">=5.1"
      espressif/esp-nn:
        version: ">=1.3.0"

That declaration makes the IDF **component manager** download esp-nn from
the component registry. We vendor esp-nn instead, pinned to a commit in
`firmware/tools/fetch_deps.sh`, for three reasons:

  * the build stays offline and reproducible — no registry version drift;
  * the exact revision is visible in the repository rather than hidden in a
    lock file;
  * ESP-NN is worth having: it is the difference between roughly 40 ms and
    roughly 2.3 s for a convnet invoke on an ESP32-S3.

A local component named `esp-nn` and a registry-installed `esp-nn` in the
same build is a duplicate-component error, and the manager's injected
requirement would be redundant. So this script:

  1. removes the `espressif/esp-nn` entry from the port's
     `idf_component.yml`, leaving the `idf` version requirement intact;
  2. adds `esp-nn` to the port's own component requirements, which is what
     actually puts `esp_nn.h` on the include path and links the library.

Both edits are idempotent: running the script twice changes nothing the
second time. `fetch_deps.sh` calls it after every checkout.

Usage:  python firmware/tools/patch_deps.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The vendored components live inside the ESP-IDF project itself (see the
# note in firmware/hub_infer/CMakeLists.txt about why that matters).
TFLM = ROOT / "hub_infer" / "components" / "esp-tflite-micro"

YML_OLD = """  espressif/esp-nn:
    # >=1.3.0: grouped-conv support the conv wrapper now relies on
    version: ">=1.3.0"
"""

YML_NEW = """  # espressif/esp-nn is vendored alongside this port (see
  # firmware/tools/fetch_deps.sh) and added by firmware/tools/patch_deps.py,
  # so it is deliberately not requested from the component registry here.
"""

CMAKE_OLD = "set(priv_req)\n"
CMAKE_NEW = "set(priv_req esp-nn)\n"


def patch_yml(text: str) -> tuple[str, bool]:
    if YML_NEW in text:
        return text, False
    if YML_OLD not in text:
        raise SystemExit(
            "patch_deps: the ESP-NN block in esp-tflite-micro/idf_component.yml "
            "is not the expected one — refusing to guess."
        )
    return text.replace(YML_OLD, YML_NEW), True


def patch_cmake(text: str) -> tuple[str, bool]:
    if CMAKE_NEW in text:
        return text, False
    if CMAKE_OLD not in text:
        raise SystemExit(
            "patch_deps: `set(priv_req)` not found in "
            "esp-tflite-micro/CMakeLists.txt — refusing to guess."
        )
    return text.replace(CMAKE_OLD, CMAKE_NEW, 1), True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report whether the patches are applied; change nothing")
    args = ap.parse_args()

    yml = TFLM / "idf_component.yml"
    cmake = TFLM / "CMakeLists.txt"
    for f in (yml, cmake):
        if not f.is_file():
            raise SystemExit(
                f"patch_deps: {f} is missing — run firmware/tools/fetch_deps.sh first."
            )

    yml_text = yml.read_text(encoding="utf-8")
    cmake_text = cmake.read_text(encoding="utf-8")

    new_yml, yml_changed = patch_yml(yml_text)
    new_cmake, cmake_changed = patch_cmake(cmake_text)

    if args.check:
        ok = not yml_changed and not cmake_changed
        print("patch_deps: patches applied" if ok else
              "patch_deps: patches MISSING — run firmware/tools/fetch_deps.sh")
        return 0 if ok else 1

    if yml_changed:
        yml.write_text(new_yml, encoding="utf-8")
        print("patch_deps: esp-nn registry dependency removed from idf_component.yml")
    if cmake_changed:
        cmake.write_text(new_cmake, encoding="utf-8")
        print("patch_deps: esp-nn added to the port's component requirements")

    if not (yml_changed or cmake_changed):
        print("patch_deps: already patched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
