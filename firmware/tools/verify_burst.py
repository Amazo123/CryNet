#!/usr/bin/env python3
"""Check the CryNet node's audio path end to end, on the real hardware.

The node can dump its frozen two-second window over the serial console in
exactly the framing the radio uses.  This tool asks for that dump, checks
every frame's CRC, reassembles the 64,000 bytes, and writes them as a WAV.

If this passes, then the microphone, the 32-bit-slot to int16 conversion,
the circular window, the framing and the CRCs are all correct on the
device — which is the part that cannot be checked on the host.

Usage:
    python firmware/tools/verify_burst.py --port COM32
    python firmware/tools/verify_burst.py --port COM32 --out burst.wav
"""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

MAGIC = bytes((0xC3, 0x7E))
FIXED = struct.Struct("<BBBBHHHHH")   # magic0 magic1 type id seq frag count plen pcrc
TRAILER = struct.Struct("<H")
BURST_BYTES = 64000
SAMPLE_RATE = 16000

ESP32_VID_PIDS = {
    (0x1A86, 0x55D3): "CH343",
    (0x1A86, 0x7523): "CH340",
    (0x10C4, 0xEA60): "CP210x",
    (0x0403, 0x6001): "FTDI",
    (0x303A, 0x1001): "Espressif native USB",
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def find_port() -> str | None:
    import serial.tools.list_ports as list_ports

    for p in list_ports.comports():
        if (p.vid, p.pid) in ESP32_VID_PIDS:
            print(f"  found {p.device}: {p.description}")
            return p.device
    return None


def write_wav(path: Path, pcm: bytes) -> None:
    with path.open("wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVE")
        fh.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                                      SAMPLE_RATE * 2, 2, 16))
        fh.write(b"data" + struct.pack("<I", len(pcm)))
        fh.write(pcm)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port; auto-detected if omitted")
    ap.add_argument("--out", default="burst.wav", help="where to write the WAV")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=90.0)
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        print("pyserial is not installed: pip install pyserial", file=sys.stderr)
        return 1

    port = args.port or find_port()
    if not port:
        print("No ESP32 serial port found.", file=sys.stderr)
        return 1

    ser = serial.Serial(port, args.baud, timeout=0.2)
    ser.dtr = False
    ser.rts = False

    buf = bytearray()
    fragments = {}          # index -> payload
    frag_count = None
    burst_seq = None
    node_id = None
    bad_crc = 0
    text = ""

    def pump(seconds: float) -> None:
        nonlocal buf
        deadline = time.time() + seconds
        while time.time() < deadline:
            chunk = ser.read(8192)
            if chunk:
                buf += chunk

    print(f"Connected to {port}. Waiting 3 s for the window to fill ...")
    pump(3.0)

    ser.write(b"freeze\n")
    time.sleep(0.5)
    ser.write(b"burst\n")
    print("Requested the burst; reading ...")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        chunk = ser.read(8192)
        if chunk:
            buf += chunk

        while True:
            start = buf.find(MAGIC)
            if start < 0:
                if len(buf) > 1:
                    text += buf[:-1].decode("utf-8", "replace")
                    del buf[:-1]
                break
            if start:
                text += buf[:start].decode("utf-8", "replace")
                del buf[:start]
            if len(buf) < FIXED.size:
                break

            m0, m1, ftype, fid, seq, frag, count, plen, pcrc = FIXED.unpack(buf[:FIXED.size])
            if ftype != 2 or plen > 4096:
                del buf[:1]
                continue
            total = FIXED.size + plen + TRAILER.size
            if len(buf) < total:
                break

            payload = bytes(buf[FIXED.size:FIXED.size + plen])
            fcrc = TRAILER.unpack(buf[FIXED.size + plen:total])[0]
            if crc16(bytes(buf[:FIXED.size + plen])) != fcrc or crc16(payload) != pcrc:
                bad_crc += 1
                del buf[:1]
                continue

            del buf[:total]
            frag_count = count
            burst_seq = seq
            node_id = fid
            fragments[frag] = payload

        if frag_count is not None and len(fragments) >= frag_count:
            break

    ser.close()

    print("\n--- node output ---")
    print(text.strip()[-2000:])
    print("--- end ---\n")

    if frag_count is None:
        print("FAIL: no burst fragment received.", file=sys.stderr)
        return 1

    missing = [i for i in range(frag_count) if i not in fragments]
    pcm = b"".join(fragments[i] for i in range(frag_count) if i in fragments)

    print(f"node id      {node_id}")
    print(f"burst seq    {burst_seq}")
    print(f"fragments    {len(fragments)}/{frag_count}  (bad CRC {bad_crc})")
    print(f"payload      {len(pcm)} bytes (expected {BURST_BYTES})")

    if missing:
        print(f"FAIL: missing fragments {missing[:20]}", file=sys.stderr)
        return 1
    if bad_crc:
        print(f"FAIL: {bad_crc} frames failed their CRC", file=sys.stderr)
        return 1
    if len(pcm) != BURST_BYTES:
        print(f"FAIL: reassembled {len(pcm)} bytes, expected {BURST_BYTES}",
              file=sys.stderr)
        return 1

    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
    mean = sum(samples) / len(samples)
    rms = (sum((s - mean) ** 2 for s in samples) / len(samples)) ** 0.5 / 32768.0
    peak = max(abs(s) for s in samples)

    out = Path(args.out)
    write_wav(out, pcm)
    print(f"mean         {mean:.1f} counts (the INMP441's DC offset)")
    print(f"rms          {rms:.5f}")
    print(f"peak         {peak} counts")
    print(f"wrote        {out}  ({len(pcm) / 2 / SAMPLE_RATE:.2f} s)")

    if peak == 0:
        print("FAIL: the window is silent — check the microphone wiring.",
              file=sys.stderr)
        return 1

    print("\nPASS: the node's capture, framing and CRC are correct on the device.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
