#!/usr/bin/env python3
"""Watch several boards at once.

The bench has the hub and all three cot nodes on one machine now, so the
questions that matter are the ones that need every board at the same
time: does the hub hear all three cots, does one board's transmit
starve the others, does the wearable stay connected.  The tools that
existed could only hold one port open at a time, which cannot answer
any of those.

This opens every port at once -- one thread each -- and writes every
line it sees to its own file, stamped with the time since the capture
started.  A command can be sent to a port after the boards have settled
(`--send-after`), which is how the node counters are read.

Opening a port resets an ESP32-C3 (its USB Serial/JTAG does the reset
on the DTR/RTS edge), so every board reboots when the capture starts.
That is deliberate here: the capture wants to see the boot banners, and
the hub's radio comes back up by itself.

Usage:
    python firmware/tools/capture_multi.py --ports COM31 COM32 COM37 COM38
    python firmware/tools/capture_multi.py --ports COM31 COM37 COM38 \\
        --labels node1 node2 node3 --send-after 10 COM31:stats COM37:stats
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

try:
    import serial
except ImportError:  # pragma: no cover
    print("pyserial is not installed: pip install pyserial", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[2]

# The lines worth knowing about without reading the whole file.
INTERESTING = re.compile(
    r"ALERT|alert|Brownout|brownout|panic|abort|rst:|Guru|watchdog|"
    r"cry|cot |node |hub |win\(|P\(cry\)|decoded|BLE|ble\]|state:",
    re.IGNORECASE,
)


class Port:
    """One board on one port."""

    def __init__(self, port: str, label: str, out_dir: Path):
        self.port = port
        self.label = label
        self.path = out_dir / f"{label}_{port}.log"
        self.fh = None
        self.serial = None
        self.lines = 0
        self.interesting: list[str] = []
        self.lock = threading.Lock()
        self.error: str | None = None

    def open(self) -> None:
        # Build the port by hand so that DTR and RTS are never asserted:
        # on the S3 hub those lines reach EN and GPIO0, and a stray
        # assertion would put the board in the bootloader.
        s = serial.Serial()
        s.port = self.port
        s.baudrate = 115200
        s.timeout = 0.2
        s.dtr = False
        s.rts = False
        s.open()
        try:
            s.dtr = False
            s.rts = False
        except Exception:  # noqa: BLE001 -- not every driver has them
            pass
        self.serial = s
        self.fh = self.path.open("w", encoding="utf-8", errors="replace")

    def write(self, line: str, t0: float) -> None:
        stamp = f"{time.time() - t0:8.2f}"
        with self.lock:
            self.lines += 1
            self.fh.write(f"[{stamp}] {line}")
            self.fh.flush()
            if INTERESTING.search(line):
                self.interesting.append(line.rstrip())

    def close(self) -> None:
        if self.serial is not None:
            try:
                self.serial.close()
            except Exception:  # noqa: BLE001
                pass
        if self.fh is not None:
            self.fh.close()


def reader(p: Port, t0: float, stop: threading.Event) -> None:
    """Read one port until the capture ends."""
    try:
        p.open()
    except Exception as exc:  # noqa: BLE001
        p.error = str(exc)
        return
    buf = bytearray()
    try:
        while not stop.is_set():
            try:
                chunk = p.serial.read(p.serial.in_waiting or 1)
            except Exception as exc:  # noqa: BLE001
                p.error = str(exc)
                break
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, _, rest = bytes(buf).partition(b"\n")
                buf = bytearray(rest)
                p.write(raw.decode("utf-8", "replace").rstrip() + "\n", t0)
    finally:
        p.close()


def send(p: Port, command: str, t0: float) -> None:
    """Send one console command to a port."""
    try:
        p.serial.write((command + "\n").encode("ascii", "replace"))
        p.serial.flush()
        p.write(f"<< sent: {command} >>\n", t0)
    except Exception as exc:  # noqa: BLE001
        p.write(f"<< could not send {command}: {exc} >>\n", t0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ports", nargs="+", required=True,
                    help="the serial ports to watch")
    ap.add_argument("--labels", nargs="+", default=None,
                    help="a name for each port (default: the port name)")
    ap.add_argument("--seconds", type=float, default=120.0,
                    help="how long to watch")
    ap.add_argument("--outdir", default=None,
                    help="where to put the logs (default: research/out/capture_*)")
    ap.add_argument("--send-after", type=float, default=0.0,
                    help="seconds to wait before sending the commands")
    ap.add_argument("--send", nargs="*", default=[],
                    help="PORT:command pairs, sent after --send-after seconds")
    args = ap.parse_args()

    labels = args.labels or [p.replace("COM", "port") for p in args.ports]
    if len(labels) != len(args.ports):
        print("--labels must have one name per port", file=sys.stderr)
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.outdir) if args.outdir else \
        ROOT / "research" / "out" / f"capture_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ports = [Port(p, l, out_dir) for p, l in zip(args.ports, labels)]
    stop = threading.Event()
    t0 = time.time()
    threads = []
    for p in ports:
        th = threading.Thread(target=reader, args=(p, t0, stop), daemon=True)
        th.start()
        threads.append(th)

    # let the boards boot before anything is said to them
    pending = list(args.send)
    if pending:
        time.sleep(max(0.0, args.send_after))
        for item in pending:
            port, _, command = item.partition(":")
            if not command:
                command = port
                port = None
            for p in ports:
                if port is None or p.port == port or p.label == port:
                    send(p, command, t0)

    time.sleep(max(0.0, args.seconds - (time.time() - t0)))
    stop.set()
    for th in threads:
        th.join(timeout=3.0)

    print(f"logs in {out_dir}")
    for p in ports:
        note = f"  ({p.error})" if p.error else ""
        print(f"  {p.label:<10} {p.port:<8} {p.lines:>6} lines{note}")
        for line in p.interesting[-12:]:
            print(f"      {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
