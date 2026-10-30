#!/usr/bin/env python3
"""Read the CryNet hub's serial log and optionally reset the board first.

The Stage 2a firmware prints its verification report over UART at 115200
baud: the platform summary, the four probe comparisons against the host
reference, P(cry), the front-end and inference latency, and the tensor
arena usage. This script opens the port, optionally pulses EN to restart
the board so the whole boot sequence is captured, and prints everything
it receives.

Usage:
    python firmware/tools/capture_serial.py --port COM32
    python firmware/tools/capture_serial.py --port COM32 --reset --seconds 30
    python firmware/tools/capture_serial.py --list
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
    import serial.tools.list_ports as list_ports
except ImportError:  # pragma: no cover
    print("pyserial is not installed: pip install pyserial", file=sys.stderr)
    sys.exit(1)


def list_serial_ports() -> int:
    ports = list(list_ports.comports())
    if not ports:
        print("no serial ports found")
        return 0
    for p in ports:
        print(f"{p.device:<10} {p.description}")
    return 0


def pulse_reset(ser: serial.Serial) -> None:
    """Reset the board into the application.

    On the ESP32-S3 DevKitC the auto-reset circuit drives EN from RTS and
    GPIO0 from DTR, both through inverting transistors: RTS high pulls EN
    low (reset), and DTR low leaves GPIO0 high (boot the application, not
    the ROM download mode).
    """
    ser.dtr = False       # GPIO0 high — do not enter the bootloader
    ser.rts = True        # EN low — reset
    time.sleep(0.15)
    ser.rts = False       # EN high — release the reset
    time.sleep(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port, e.g. COM32")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--reset", action="store_true",
                    help="pulse EN first so the boot log is captured")
    ap.add_argument("--list", action="store_true", help="list serial ports and exit")
    args = ap.parse_args()

    if args.list:
        return list_serial_ports()

    if not args.port:
        print("no --port given; available ports:", file=sys.stderr)
        list_serial_ports()
        return 2

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.2)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot open {args.port}: {exc}", file=sys.stderr)
        return 1

    with ser:
        if args.reset:
            pulse_reset(ser)
        else:
            # Opening the port with DTR/RTS asserted would hold the chip in
            # reset; make sure both lines are released.
            ser.dtr = False
            ser.rts = False

        deadline = time.time() + args.seconds
        received = 0
        while time.time() < deadline:
            chunk = ser.read(4096)
            if chunk:
                received += len(chunk)
                sys.stdout.write(chunk.decode("utf-8", errors="replace"))
                sys.stdout.flush()

    print(f"\n--- captured {received} bytes from {args.port} "
          f"at {args.baud} baud ---")
    return 0 if received else 1


if __name__ == "__main__":
    sys.exit(main())
