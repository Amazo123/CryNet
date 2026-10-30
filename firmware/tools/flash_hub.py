#!/usr/bin/env python3
"""Flash the CryNet hub to an ESP32-S3 and print its boot log.

Everything this needs is already on the machine — there is nothing to
download and nothing to install. It finds the board by itself, writes the
three images at the offsets the partition table expects, and then prints
the verification report the firmware prints on boot.

The images must exist; build them first with:

    cd firmware/hub_infer && python -m platformio run

With --merged the three images are combined into a single file first and
written at 0x0, which is what a graphical flasher such as the Arduino
IDE's "ESP32 Flash Tools" extension expects. The combination MUST use
DIO flash mode: the ROM on this board cannot read the flash in QIO
before the bootloader has set up its own timing, and a QIO image makes
the chip watchdog-reset in a loop right after power-on. The bootloader
switches the chip to QIO by itself once it is running, so nothing is
lost.

Usage:
    python firmware/tools/flash_hub.py                # flash, then show the log
    python firmware/tools/flash_hub.py --merged        # one combined file
    python firmware/tools/flash_hub.py --flash-only
    python firmware/tools/flash_hub.py --log-only --seconds 30
    python firmware/tools/flash_hub.py --port COM32
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "firmware" / "hub_infer" / ".pio" / "build" / "esp32s3"

# (file, offset) — the offsets come from firmware/hub_infer/partitions_16mb.csv
IMAGES = [
    (BUILD / "bootloader.bin", 0x0),
    (BUILD / "partitions.bin", 0x8000),
    (BUILD / "firmware.bin", 0x10000),
]

ESP32_VID_PIDS = {
    (0x1A86, 0x55D3): "CH343 (CH343P/CH9102 USB-serial, common on ESP32-S3 boards)",
    (0x1A86, 0x7523): "CH340",
    (0x10C4, 0xEA60): "Silicon Labs CP210x",
    (0x0403, 0x6001): "FTDI FT232",
    (0x303A, 0x1001): "Espressif native USB",
}


def find_esptool() -> str | None:
    """Prefer the esptool that ships with PlatformIO; fall back to PATH."""
    candidates = [
        Path.home() / ".platformio" / "packages" / "tool-esptool" / "esptool.exe",
        Path.home() / ".platformio" / "packages" / "tool-esptool" / "esptool",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ("esptool", "esptool.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def find_port() -> str | None:
    try:
        import serial.tools.list_ports as list_ports
    except ImportError:
        return None
    for p in list_ports.comports():
        if (p.vid, p.pid) in ESP32_VID_PIDS:
            print(f"  found {p.device}: {p.description}")
            return p.device
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port; auto-detected if omitted")
    ap.add_argument("--baud", type=int, default=921600, help="flashing baud")
    ap.add_argument("--seconds", type=float, default=20.0, help="how long to listen")
    ap.add_argument("--flash-only", action="store_true")
    ap.add_argument("--log-only", action="store_true")
    ap.add_argument("--merged", action="store_true",
                    help="flash one combined file at 0x0 instead of three files")
    args = ap.parse_args()

    missing = [str(p) for p, _ in IMAGES if not p.is_file()]
    if missing and not args.log_only:
        print("Missing build artefacts:", file=sys.stderr)
        for m in missing:
            print("  ", m, file=sys.stderr)
        print("\nBuild them first:  cd firmware/hub_infer && python -m platformio run",
              file=sys.stderr)
        return 1

    port = args.port or find_port()
    if not port:
        print("No ESP32 serial port found. Plug the board in, or pass --port COMx.",
              file=sys.stderr)
        return 1

    if not args.log_only:
        esptool = find_esptool()
        if esptool is None:
            print("esptool not found (looked in ~/.platformio/packages/tool-esptool "
                  "and on PATH).", file=sys.stderr)
            return 1

        print(f"Flashing {port} at {args.baud} baud:")
        cmd = [esptool, "--chip", "esp32s3", "--port", port, "--baud", str(args.baud),
               "write-flash"]
        if args.merged:
            merged = BUILD / "crynet_hub_merged.bin"
            if not merged.is_file():
                print("  building the combined image ...")
                subprocess.run([esptool, "--chip", "esp32s3", "merge-bin",
                                "-o", str(merged),
                                "--flash-mode", "dio", "--flash-freq", "80m",
                                "--flash-size", "16MB",
                                "0x0", str(IMAGES[0][0]),
                                "0x8000", str(IMAGES[1][0]),
                                "0x10000", str(IMAGES[2][0])], check=True)
            print(f"   0x00000000  {merged.name}  (one file)")
            cmd += ["0x0", str(merged)]
        else:
            for path, offset in IMAGES:
                print(f"   {offset:#08x}  {path.name}")
                cmd += [f"{offset:#x}", str(path)]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            print("Flashing failed.", file=sys.stderr)
            return result.returncode
        print("Flash OK.\n")
        if args.flash_only:
            return 0
        time.sleep(1.0)

    # --- capture the boot log ----------------------------------------------
    try:
        import serial
    except ImportError:
        print("pyserial is not installed: pip install pyserial", file=sys.stderr)
        return 1

    print(f"Listening on {port} for {args.seconds:.0f} s ...")
    try:
        ser = serial.Serial(port, 115200, timeout=0.2)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open {port}: {exc}", file=sys.stderr)
        return 1

    with ser:
        ser.dtr = False
        ser.rts = True       # pulse EN so the boot log is captured
        time.sleep(0.15)
        ser.rts = False
        deadline = time.time() + args.seconds
        while time.time() < deadline:
            chunk = ser.read(4096)
            if chunk:
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()
    print("\n--- done ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
