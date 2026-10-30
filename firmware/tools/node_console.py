#!/usr/bin/env python3
"""Talk to the CryNet node's serial console.

The node firmware (firmware/node/node_crynet) listens for one-line
commands at 115200 baud and prints its state in reply:

    status   the window, the RMS, the mean and the frozen window's CRC-32
    stats    the counters (telemetry, frames sent and lost, requests)
    freeze   freeze the live window now, so it becomes the upload target
    burst    dump the frozen window in the radio's framing
    id <n>   set the node id
    help     the list of commands

`freeze` is the one that matters for testing the radio: it makes the node
hold a specific two-second window and advertise its CRC-32 in the
telemetry, so the hub can check that the audio it reassembles from ESP-NOW
is the audio the node froze.

Usage:
    python firmware/tools/node_console.py --port COM30 --send status
    python firmware/tools/node_console.py --port COM30 --send freeze --seconds 15
    python firmware/tools/node_console.py --list
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="COM30", help="the node's serial port")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--send", action="append", default=[],
                    help="a console command to send (repeatable)")
    ap.add_argument("--seconds", type=float, default=10.0,
                    help="how long to keep reading")
    ap.add_argument("--list", action="store_true", help="list the serial ports")
    args = ap.parse_args()

    if args.list:
        return list_serial_ports()

    try:
        port = serial.Serial(args.port, args.baud, timeout=0.2)
    except serial.SerialException as exc:
        print(f"cannot open {args.port}: {exc}", file=sys.stderr)
        return 1

    # The node prints its banner when it boots, but it does not need a
    # reset: open the port, send whatever was asked for, and read.
    deadline = time.time() + args.seconds
    pending = list(args.send)

    with port:
        while time.time() < deadline:
            if pending and time.time() > deadline - args.seconds + 0.5:
                command = pending.pop(0)
                print(f"> {command}")
                port.write((command + "\n").encode("ascii", "replace"))
                port.flush()

            line = port.readline()
            if line:
                sys.stdout.write(line.decode("utf-8", "replace"))
                sys.stdout.flush()

    return 0


if __name__ == "__main__":
    sys.exit(main())
