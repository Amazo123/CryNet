#!/usr/bin/env python3
"""Check the CryNet node's audio path end to end, on the real hardware.

The node can dump its frozen two-second window over the serial console in
exactly the framing the radio uses.  This tool asks for that dump, checks
every frame's CRC, reassembles the 64,000 bytes, and writes them as a WAV.

If this passes, then the microphone, the 32-bit-slot to int16 conversion,
the circular window, the framing and the CRCs are all correct on the
device — which is the part that cannot be checked on the host.

Usage:
    python firmware/tools/verify_burst.py --port COM30
    python firmware/tools/verify_burst.py --port COM30 --out burst.wav
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
    (0x303A, 0x1001): "Espressif native USB (the C3 SuperMini's own USB)",
}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build_frame(node_id: int, ftype: int, seq: int, frag: int, count: int,
                payload: bytes) -> bytes:
    """The same layout the firmware's build_frame() produces."""
    frame = bytearray(14 + len(payload) + 2)
    frame[0], frame[1], frame[2], frame[3] = 0xC3, 0x7E, ftype, node_id
    frame[4:6] = struct.pack("<H", seq)
    frame[6:8] = struct.pack("<H", frag)
    frame[8:10] = struct.pack("<H", count)
    frame[10:12] = struct.pack("<H", len(payload))
    frame[12:14] = struct.pack("<H", crc16(payload) if payload else 0)
    frame[14:14 + len(payload)] = payload
    frame[14 + len(payload):] = struct.pack(
        "<H", crc16(bytes(frame[:14 + len(payload)])))
    return bytes(frame)


class FrameParser:
    """Pulls burst fragments out of a byte stream, checking every CRC.

    The node's console mixes text and binary frames, so the parser has to
    resynchronise on the magic.  A frame that fails its CRC is skipped
    one byte at a time, which is what lets it recover from a dropped
    byte instead of giving up.
    """

    def __init__(self) -> None:
        self.buf = bytearray()
        self.fragments: dict[int, bytes] = {}
        self.frag_count = None
        self.burst_seq = None
        self.node_id = None
        self.bad_crc = 0

    def feed(self, data: bytes) -> str:
        """Add bytes and return whatever text was in between the frames."""
        self.buf += data
        out = ""
        while True:
            start = self.buf.find(MAGIC)
            if start < 0:
                # Keep the last byte: a magic may straddle two reads.
                if len(self.buf) > 1:
                    out += self.buf[:-1].decode("utf-8", "replace")
                    del self.buf[:-1]
                break
            if start:
                out += self.buf[:start].decode("utf-8", "replace")
                del self.buf[:start]
            if len(self.buf) < FIXED.size:
                break

            _, _, ftype, fid, seq, frag, count, plen, pcrc = FIXED.unpack(
                self.buf[:FIXED.size])
            if ftype != 2 or plen > 4096:
                del self.buf[:1]
                continue
            total = FIXED.size + plen + TRAILER.size
            if len(self.buf) < total:
                break

            payload = bytes(self.buf[FIXED.size:FIXED.size + plen])
            fcrc = TRAILER.unpack(self.buf[FIXED.size + plen:total])[0]
            if (crc16(bytes(self.buf[:FIXED.size + plen])) != fcrc
                    or crc16(payload) != pcrc):
                self.bad_crc += 1
                del self.buf[:1]
                continue

            del self.buf[:total]
            self.frag_count = count
            self.burst_seq = seq
            self.node_id = fid
            self.fragments[frag] = payload
        return out

    def done(self) -> bool:
        return (self.frag_count is not None
                and len(self.fragments) >= self.frag_count)

    def assemble(self) -> bytes:
        if self.frag_count is None:
            return b""
        return b"".join(self.fragments[i] for i in range(self.frag_count)
                         if i in self.fragments)


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
    ap.add_argument("--settle", type=float, default=5.0,
                    help="seconds to wait before asking for the window")
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

    parser = FrameParser()

    def drain() -> str:
        """Read whatever the device has sent, without ever waiting long.

        The node's CDC transmit buffer is small, so a reader that waits
        for a fixed block size will let the device overflow it and lose
        bytes.  Asking for exactly what has arrived keeps the link drained.
        """
        waiting = ser.in_waiting
        chunk = ser.read(waiting if waiting else 1)
        return parser.feed(chunk) if chunk else ""

    def pump(seconds: float) -> str:
        deadline = time.time() + seconds
        out = ""
        while time.time() < deadline:
            out += drain()
        return out

    print(f"Connected to {port}. Waiting {args.settle:.0f} s for the node to boot "
          f"and its window to fill ...")
    pump(args.settle)

    # The node refuses to freeze until its two-second window is complete,
    # so ask again until it answers.
    frozen = False
    for _ in range(12):
        ser.write(b"freeze\n")
        text = pump(1.0)
        if text.strip():
            print(text.strip()[-300:])
        if "frozen seq=" in text:
            frozen = True
            break
    if not frozen:
        print("The node never froze its window — is it running node_crynet?",
              file=sys.stderr)

    ser.write(b"burst\n")
    print("Requested the burst; reading ...")

    deadline = time.time() + args.timeout
    while time.time() < deadline:
        text = drain()
        # The node prints BURST-END once it has sent every fragment, so
        # there is no point waiting for the timeout after that.
        if "BURST-END" in text:
            break
        if parser.done():
            break

    ser.close()

    if parser.frag_count is None:
        print("FAIL: no burst fragment received.", file=sys.stderr)
        return 1

    missing = [i for i in range(parser.frag_count) if i not in parser.fragments]
    pcm = parser.assemble()

    print()
    print(f"node id      {parser.node_id}")
    print(f"burst seq    {parser.burst_seq}")
    print(f"fragments    {len(parser.fragments)}/{parser.frag_count}  "
          f"(bad CRC {parser.bad_crc})")
    print(f"payload      {len(pcm)} bytes (expected {BURST_BYTES})")

    if missing:
        print(f"FAIL: missing fragments {missing[:20]}", file=sys.stderr)
        return 1
    if parser.bad_crc:
        print(f"FAIL: {parser.bad_crc} frames failed their CRC", file=sys.stderr)
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
