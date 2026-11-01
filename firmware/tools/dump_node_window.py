#!/usr/bin/env python3
"""Dump the node's frozen window over its serial console and look at it.

The node's `burst` console command writes the frozen two-second window as
fragment frames in the same wire format the radio uses, so this reads them
back, reassembles the audio, writes it as a WAV, and says what is in it:
the level, the largest peaks, and how the energy sits across the spectrum.

This is the instrument for the question the hub's log cannot answer: the
hub says *that* a window was judged a cry, not *what was in it*.

Usage:
    python firmware/tools/dump_node_window.py --out research/out/node_window.wav
    python firmware/tools/dump_node_window.py --port COM30 --score
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import time

import numpy as np
import serial

MAGIC = b"\xC3\x7E"
HEADER_BYTES = 14
FRAME_TYPE_FRAGMENT = 2
SAMPLE_RATE = 16000
WINDOW_SAMPLES = 32000
WINDOW_BYTES = WINDOW_SAMPLES * 2


def crc16_ccitt(data: bytes) -> int:
    """The same CRC the firmware uses: CCITT-FALSE, poly 0x1021, init 0xFFFF."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def read_until(port: serial.Serial, marker: bytes, timeout: float) -> bytes:
    """Drain the port as fast as it arrives.

    The dump is 68 kB at 115200 baud — about six seconds — and the
    driver's own buffer is 4 kB, so a reader that waits for a full block
    loses the frames that arrive in between.  Take whatever is there.
    """
    buf = bytearray()
    end = time.time() + timeout
    while time.time() < end:
        waiting = port.in_waiting
        if waiting:
            buf += port.read(waiting)
            if marker in buf:
                return bytes(buf)
        else:
            time.sleep(0.002)
    return bytes(buf)


def parse_frames(buf: bytes, start: int) -> list[tuple[int, bytes]]:
    """Every fragment frame in the buffer, in order."""
    frames = []
    i = start
    while i + HEADER_BYTES <= len(buf):
        if buf[i:i + 2] != MAGIC:
            i += 1
            continue
        (_type, _node, seq, frag, count, plen) = struct.unpack_from("<BBHHHH", buf, i + 2)
        total = HEADER_BYTES + plen + 2
        if i + total > len(buf):
            break
        payload = buf[i + HEADER_BYTES:i + HEADER_BYTES + plen]
        fcrc = struct.unpack_from("<H", buf, i + HEADER_BYTES + plen)[0]
        if crc16_ccitt(buf[i:i + HEADER_BYTES + plen]) != fcrc:
            print(f"frame {frag}: the frame CRC failed", file=sys.stderr)
            i += total
            continue
        if _type == FRAME_TYPE_FRAGMENT:
            frames.append((frag, payload))
        i += total
    return frames


def spectrum_report(x: np.ndarray) -> None:
    """Where the energy is, and whether it is periodic."""
    win = np.hanning(len(x))
    spec = np.abs(np.fft.rfft(x * win))
    freqs = np.fft.rfftfreq(len(x), 1.0 / SAMPLE_RATE)
    total = spec.sum() or 1.0

    # The energy in the bands a cry lives in, against the rest.
    bands = [(0, 300), (300, 1000), (1000, 2500), (2500, 4000), (4000, 8000)]
    print("  band energy:")
    for lo, hi in bands:
        m = (freqs >= lo) & (freqs < hi)
        share = float(spec[m].sum() / total)
        bar = "#" * int(round(share * 40))
        print(f"    {lo:>5}-{hi:<5} Hz  {share * 100:5.1f}%  {bar}")

    # The strongest partials: a voiced cry has a clear harmonic series.
    top = np.argsort(spec)[::-1][:400]
    peaks = []
    for idx in top:
        f = float(freqs[idx])
        if any(abs(f - p) < 30 for p in peaks):
            continue
        peaks.append(f)
        if len(peaks) >= 6:
            break
    peaks.sort()
    if peaks:
        print("  strongest partials: " + ", ".join(f"{p:.0f} Hz" for p in peaks))
        if len(peaks) >= 2:
            gaps = [b - a for a, b in zip(peaks, peaks[1:]) if b - a > 0]
            if gaps:
                print(f"  spacing between them: {['%.0f' % g for g in gaps]} Hz")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="COM30")
    ap.add_argument("--out", default="research/out/node_window.wav")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--score", action="store_true",
                    help="also score the window with the deployed INT8 model")
    args = ap.parse_args()

    port = serial.Serial(args.port, 115200, timeout=0.2)
    try:
        port.reset_input_buffer()
        port.write(b"burst\n")
        port.flush()
        buf = read_until(port, b"BURST-END", args.timeout)
    finally:
        port.close()

    marker = buf.find(b"BURST seq=")
    if marker < 0:
        print("the node did not send a burst", file=sys.stderr)
        print(buf[-400:].decode("utf-8", "replace"), file=sys.stderr)
        return 1

    # The sequence number is the node's own name for the window, and it is
    # the number the hub's log uses, so a dump and a verdict can be
    # matched to each other.
    head = buf[marker:marker + 40].decode("utf-8", "replace")
    seq = None
    try:
        seq = int(head.split("seq=")[1].split()[0])
    except (IndexError, ValueError):
        pass

    frames = parse_frames(buf, marker)
    if not frames:
        print("no fragment frames came back", file=sys.stderr)
        return 1

    # The USB driver drops the odd frame from a 68 kB burst.  A fragment
    # is 224 bytes of 64000, so one lost fragment is a hole in the audio
    # and not a reason to throw the window away: fill the hole with
    # silence and say which one it was.
    by_index = {frag: payload for frag, payload in frames}
    count = max(by_index) + 1
    missing = [i for i in range(count) if i not in by_index]
    data = bytearray()
    for i in range(count):
        data += by_index.get(i, b"\x00" * 224)
    if missing:
        print(f"missing fragment(s): {missing} — filled with silence")

    if len(data) < WINDOW_BYTES:
        print(f"only {len(data)} of {WINDOW_BYTES} bytes came back "
              f"({len(frames)} fragments)", file=sys.stderr)
        return 1

    samples = np.frombuffer(bytes(data[:WINDOW_BYTES]), dtype="<i2").astype(np.float32) / 32768.0
    mean = float(samples.mean())
    centred = samples - mean
    rms = float(np.sqrt((centred ** 2).mean()))
    peak = float(np.abs(samples).max())
    print(f"fragments: {len(frames)}  bytes: {len(data)}  seq: {seq}")
    print(f"mean {mean:+.6f}  rms {rms:.6f}  peak {peak:.6f}  "
          f"peak/rms {(peak / rms if rms else 0):.1f}")
    spectrum_report(samples)

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    wave_out(out, samples)
    print(f"wrote {out}")

    if args.score:
        return score(out)
    return 0


def wave_out(path: str, samples: np.ndarray):
    """Write 16 kHz mono int16 WAV."""
    import wave

    pcm = np.clip(samples * 32768.0, -32768, 32767).astype("<i2")
    f = wave.open(path, "wb")
    f.setnchannels(1)
    f.setsampwidth(2)
    f.setframerate(SAMPLE_RATE)
    f.writeframes(pcm.tobytes())
    f.close()
    return path


def score(path: str) -> int:
    """Score the window with the deployed INT8 model, the same way the hub does."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "research"))
    try:
        from eval_indomain import notebook_namespace, read_wav  # type: ignore
    except Exception as exc:  # pragma: no cover
        print(f"could not load the notebook helpers: {exc}", file=sys.stderr)
        return 1

    import tensorflow as tf

    ns = notebook_namespace()
    x = read_wav(path)
    f = ns["log_mel"](x)[None, ...].astype(np.float32)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "research", "out")
    interp = tf.lite.Interpreter(model_path=os.path.join(out_dir, "crynet_int8.tflite"))
    interp.allocate_tensors()
    i_d = interp.get_input_details()[0]
    o_d = interp.get_output_details()[0]
    s, z = i_d["quantization"]
    q = np.clip(np.round(f / s) + z, -128, 127).astype(np.int8)
    interp.set_tensor(i_d["index"], q[..., None])
    interp.invoke()
    o = interp.get_tensor(o_d["index"])[0].astype(np.float32)
    p = (o - o_d["quantization"][1]) * o_d["quantization"][0]
    print(f"model: P(no_cry)={p[0]:.4f}  P(cry)={p[1]:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
