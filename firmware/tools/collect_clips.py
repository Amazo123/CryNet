#!/usr/bin/env python3
"""Collect in-domain audio from the CryNet node over the USB serial link.

The deployed model was trained on corpora that this room's microphone has
never produced.  This tool runs the `node_capture` sketch, writes the
stream to a continuous WAV, records the per-record RMS so the loud parts
can be found, and cuts the session into fixed-length clips that match the
training format (16 kHz, mono, 16-bit).

Usage:
    python firmware/tools/collect_clips.py --out research/in_domain/session1
    python firmware/tools/collect_clips.py --port COM32 --seconds 60 \
        --out research/in_domain/session1 --note "cot, baby crying"
    python firmware/tools/collect_clips.py --list

The node prints `CRY-CAPTURE-LIVE` when it is ready; the tool waits for it
so the banner never ends up inside the audio.
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
import time
from pathlib import Path

MAGIC = b"CRY1"
HEADER = struct.Struct("<4sHHI")
SAMPLE_RATE = 16000

ESP32_VID_PIDS = {
    (0x1A86, 0x55D3): "CH343",
    (0x1A86, 0x7523): "CH340",
    (0x10C4, 0xEA60): "CP210x",
    (0x0403, 0x6001): "FTDI",
    (0x303A, 0x1001): "Espressif native USB",
}


def find_port() -> str | None:
    import serial.tools.list_ports as list_ports

    for p in list_ports.comports():
        if (p.vid, p.pid) in ESP32_VID_PIDS:
            print(f"  found {p.device}: {p.description} ({ESP32_VID_PIDS[(p.vid, p.pid)]})")
            return p.device
    return None


def write_wav_header(fh, data_bytes: int) -> bytes:
    """A 44-byte canonical WAV header with the sizes left at zero."""
    hdr = b"RIFF" + struct.pack("<I", 0) + b"WAVE"
    hdr += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE,
                                 SAMPLE_RATE * 2, 2, 16)
    hdr += b"data" + struct.pack("<I", 0)
    return hdr


def patch_wav_size(path: Path) -> None:
    data = path.stat().st_size - 44
    if data < 0:
        return
    with path.open("r+b") as fh:
        fh.seek(4)
        fh.write(struct.pack("<I", 36 + data))
        fh.seek(40)
        fh.write(struct.pack("<I", data))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port; auto-detected if omitted")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this many seconds (0 = until Ctrl-C)")
    ap.add_argument("--clip-seconds", type=float, default=5.0,
                    help="length of the cut clips, in seconds")
    ap.add_argument("--note", default="", help="note stored with the session")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        print("pyserial is not installed: pip install pyserial", file=sys.stderr)
        return 1

    if args.list:
        import serial.tools.list_ports as list_ports
        for p in list_ports.comports():
            print(f"{p.device:<10} {p.description}")
        return 0

    port = args.port or find_port()
    if not port:
        print("No ESP32 serial port found.", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    clips_dir = out / "clips"
    clips_dir.mkdir(exist_ok=True)

    wav_path = out / "session.wav"
    csv_path = out / "records.csv"
    meta_path = out / "session.txt"

    print(f"Listening on {port} at {args.baud} baud ...")
    ser = serial.Serial(port, args.baud, timeout=0.2)
    ser.dtr = False
    ser.rts = False

    buf = bytearray()
    total_samples = 0
    total_bytes = 0
    clip_index = 0
    clip_buf = bytearray()
    clip_samples = 0
    clip_target = int(args.clip_seconds * SAMPLE_RATE)
    records = 0
    started = time.time()
    ready = False

    with wav_path.open("wb") as wav, csv_path.open("w", newline="") as csvf:
        wav.write(write_wav_header(wav, 0))
        writer = csv.writer(csvf)
        writer.writerow(["index", "seconds", "rms", "rms_milli"])

        try:
            while True:
                chunk = ser.read(4096)
                if chunk:
                    buf += chunk

                # The banner is plain text; wait for the ready marker so it
                # never lands inside the audio.
                if not ready:
                    if b"CRY-CAPTURE-LIVE" in buf:
                        ready = True
                        buf = bytearray()
                        print("node is live")
                    elif b"FATAL" in buf:
                        print("the node reported a fatal error:\n"
                              + buf.decode("utf-8", "replace"), file=sys.stderr)
                        return 1
                    else:
                        if len(buf) > 4096:
                            buf = buf[-64:]
                        continue

                # Pull records out of the buffer.
                while True:
                    start = buf.find(MAGIC)
                    if start < 0:
                        # Keep the last 3 bytes: a magic may straddle two
                        # reads.
                        if len(buf) > 3:
                            del buf[:-3]
                        break
                    if start:
                        del buf[:start]
                    if len(buf) < HEADER.size:
                        break
                    magic, seq, nsamples, rms_milli = HEADER.unpack(buf[:HEADER.size])
                    if magic != MAGIC or nsamples == 0 or nsamples > 4096:
                        del buf[:1]
                        continue
                    need = HEADER.size + nsamples * 2
                    if len(buf) < need:
                        break
                    payload = bytes(buf[HEADER.size:need])
                    del buf[:need]

                    wav.write(payload)
                    total_bytes += len(payload)
                    total_samples += nsamples
                    records += 1
                    writer.writerow([seq, f"{total_samples / SAMPLE_RATE:.3f}",
                                     f"{rms_milli / 1000.0:.5f}", rms_milli])

                    clip_buf += payload
                    clip_samples += nsamples
                    while clip_samples >= clip_target:
                        take = clip_target * 2
                        chunk_bytes = bytes(clip_buf[:take])
                        del clip_buf[:take]
                        clip_samples -= clip_target
                        clip_path = clips_dir / f"clip_{clip_index:04d}.wav"
                        with clip_path.open("wb") as cf:
                            cf.write(write_wav_header(cf, 0))
                            cf.write(chunk_bytes)
                        patch_wav_size(clip_path)
                        clip_index += 1

                    if records % 50 == 0:
                        wav.flush()
                        print(f"  {total_samples / SAMPLE_RATE:7.1f} s "
                              f"({total_bytes / 1024:.0f} KiB, {clip_index} clips)")

                if args.seconds and (time.time() - started) > args.seconds:
                    break
        except KeyboardInterrupt:
            print("\nstopped")
        finally:
            ser.close()

    patch_wav_size(wav_path)
    meta_path.write_text(
        f"port: {port}\n"
        f"sample_rate: {SAMPLE_RATE}\n"
        f"channels: 1\n"
        f"bits: 16\n"
        f"seconds: {total_samples / SAMPLE_RATE:.3f}\n"
        f"records: {records}\n"
        f"clips: {clip_index} x {args.clip_seconds} s\n"
        f"note: {args.note}\n"
        f"recorded: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    )

    print(f"\nwrote {wav_path} ({total_samples / SAMPLE_RATE:.1f} s)")
    print(f"wrote {csv_path} ({records} records)")
    print(f"wrote {clips_dir} ({clip_index} clips of {args.clip_seconds} s)")
    print(f"wrote {meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
