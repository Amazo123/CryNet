#!/usr/bin/env python3
"""Turn a captured session into labelled 5-second clips.

`collect_clips.py` records a session and cuts it into fixed-length clips,
but a fixed cut is not a label: a clip that happens to straddle the start
of a cry is neither "cry" nor "not cry".  This tool cuts the session on a
fixed grid and labels each clip by *what the clip contains*, measured from
the per-100 ms RMS that the capture sketch reports (records.csv) — or, if
that file is missing or truncated, from the audio itself.

The rules are deliberately simple and auditable:

  * the quiet floor is the 10th percentile of the record RMS;
  * a record counts as "signal" when its RMS is at or above the threshold,
    which defaults to max(3x the quiet floor, --threshold);
  * a clip is "cry" when at least --cry-share of its records are signal,
    "no_cry" when at most --quiet-share are, and anything in between is
    "uncertain" — reported, but not used for training.

Usage:
    python firmware/tools/label_session.py --session research/in_domain/session1
    python firmware/tools/label_session.py --session research/in_domain/session1 \
        --threshold 0.02 --clip-seconds 5.0 --stride 2.5

Outputs, inside the session directory:
    clips_labeled/    the cut clips (16 kHz mono 16-bit, the training format)
    manifest.csv      one row per clip: file, label, start, end, rms stats
    summary.txt       the thresholds, the percentiles and a per-10-second
                      timeline of the session, so the levels can be checked
                      by eye without listening.
"""

from __future__ import annotations

import argparse
import csv
import math
import statistics
import struct
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 16000
RECORD_SECONDS = 0.1
PER_RECORD = int(RECORD_SECONDS * SAMPLE_RATE)   # samples in one record


def percentile(values: list[float], q: float) -> float:
    """The q-th percentile (0..1) of a list, by linear interpolation."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def read_wav_samples(path: Path) -> tuple[np.ndarray, int]:
    """The samples of a 16-bit PCM WAV, parsed by hand.

    The collector patches the WAV header's sizes when it finishes, so a run
    that is interrupted leaves a header that claims zero bytes.  Parsing
    the chunks directly means a partial recording is still usable.
    """
    raw = path.read_bytes()
    if raw[:4] != b"RIFF" or raw[8:12] != b"WAVE":
        raise ValueError(f"{path} is not a WAV")
    pos = 12
    rate = SAMPLE_RATE
    data = None
    while pos + 8 <= len(raw):
        cid = raw[pos:pos + 4]
        size = struct.unpack("<I", raw[pos + 4:pos + 8])[0]
        body = raw[pos + 8:pos + 8 + size]
        if cid == b"fmt " and len(body) >= 8:
            rate = struct.unpack("<I", body[4:8])[0]
        elif cid == b"data":
            # A truncated file, or a header whose sizes were never
            # patched: keep the bytes that are actually there.
            remaining = len(raw) - (pos + 8)
            data = raw[pos + 8:] if (size == 0 or remaining < size) else body
            break
        pos += 8 + size + (size & 1)
    if data is None:
        raise ValueError(f"{path} has no data chunk")
    x = np.frombuffer(data[:len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    return x, rate


def envelope(x: np.ndarray, block: int = PER_RECORD) -> list[float]:
    """The RMS of every 100 ms block, each block's own mean removed — the
    same quantity the capture sketch reports."""
    out: list[float] = []
    for i in range(0, len(x) - block + 1, block):
        seg = x[i:i + block]
        d = seg - seg.mean()
        out.append(float(np.sqrt(np.mean(d * d))))
    return out


def read_records(path: Path) -> list[float]:
    """The per-record RMS in the order the records were captured."""
    out: list[float] = []
    with path.open(newline="") as fh:
        for row in csv.DictReader(fh):
            out.append(float(row["rms"]))
    return out


def write_clip(samples: bytes, path: Path, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(samples)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", required=True, help="the session directory")
    ap.add_argument("--threshold", type=float, default=0.012,
                    help="RMS above which a record counts as signal")
    ap.add_argument("--clip-seconds", type=float, default=5.0)
    ap.add_argument("--stride", type=float, default=2.5,
                    help="distance between the starts of two clips")
    ap.add_argument("--cry-share", type=float, default=0.25,
                    help="the share of loud records that makes a clip a cry")
    ap.add_argument("--quiet-share", type=float, default=0.05,
                    help="the share of loud records that makes a clip quiet")
    ap.add_argument("--name", default="", help="a label prefix, e.g. 'cry_near'")
    args = ap.parse_args()

    session = Path(args.session)
    wav_path = session / "session.wav"
    csv_path = session / "records.csv"
    if not wav_path.is_file():
        print(f"{session} does not look like a session directory "
              f"(session.wav is required)", flush=True)
        return 1

    records = read_records(csv_path) if csv_path.is_file() else []
    x, rate = read_wav_samples(wav_path)
    if not records:
        print("records.csv is missing or empty — the RMS envelope is "
              "computed from the audio instead", flush=True)
        records = envelope(x)
    if not records:
        print("the session has no audio at all", flush=True)
        return 1

    floor = percentile(records, 0.10)
    threshold = max(args.threshold, floor * 3.0)

    clip_samples = int(args.clip_seconds * SAMPLE_RATE)
    stride_samples = int(args.stride * SAMPLE_RATE)

    out_dir = session / "clips_labeled"
    out_dir.mkdir(exist_ok=True)
    for old in out_dir.glob("*.wav"):
        old.unlink()

    manifest: list[list] = []
    index = 0
    start = 0
    while start + clip_samples <= len(x):
        first = start
        last = start + clip_samples
        rec_from = first // PER_RECORD
        rec_to = min(len(records), last // PER_RECORD)
        window = records[rec_from:rec_to]
        share = (sum(1 for r in window if r >= threshold) / len(window)
                 if window else 0.0)
        if share >= args.cry_share:
            label = "cry"
        elif share <= args.quiet_share:
            label = "no_cry"
        else:
            label = "uncertain"
        payload = np.clip(np.round(x[first:last] * 32768.0), -32768, 32767
                          ).astype("<i2").tobytes()
        name = f"{args.name + '_' if args.name else ''}clip_{index:04d}.wav"
        write_clip(payload, out_dir / name, rate)
        manifest.append([
            name, label,
            f"{first / SAMPLE_RATE:.1f}", f"{last / SAMPLE_RATE:.1f}",
            f"{statistics.fmean(window):.5f}" if window else "0",
            f"{max(window):.5f}" if window else "0",
            f"{share:.2f}",
        ])
        index += 1
        start += stride_samples

    with (session / "manifest.csv").open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["file", "label", "start_s", "end_s",
                         "rms_mean", "rms_peak", "loud_share"])
        writer.writerows(manifest)

    # The summary: the numbers, and a coarse timeline so the levels can be
    # checked without listening to the audio.
    counts = {"cry": 0, "no_cry": 0, "uncertain": 0}
    for m in manifest:
        counts[m[1]] += 1
    total_s = len(records) * RECORD_SECONDS
    lines = [
        f"session: {session}",
        f"records: {len(records)}  ({total_s:.1f} s)",
        f"threshold: {threshold:.5f}  (floor p10 = {floor:.5f}, "
        f"max = {max(records):.5f})",
        f"percentiles: p10 {percentile(records, 0.10):.5f}  "
        f"p50 {percentile(records, 0.50):.5f}  "
        f"p90 {percentile(records, 0.90):.5f}  "
        f"p99 {percentile(records, 0.99):.5f}",
        f"clips: {len(manifest)}  "
        f"({counts['cry']} cry, {counts['no_cry']} no_cry, "
        f"{counts['uncertain']} uncertain)",
        f"clip length: {args.clip_seconds:.1f} s, stride {args.stride:.1f} s",
        "",
        "timeline (every 10 s: mean RMS, peak RMS, [S]ignal share)",
    ]
    per = int(10 / RECORD_SECONDS)
    for i in range(0, len(records), per):
        window = records[i:i + per]
        if not window:
            continue
        share = sum(1 for r in window if r >= threshold) / len(window)
        mark = "S" if share > 0.5 else ("s" if share > 0 else ".")
        lines.append(f"  {i * RECORD_SECONDS:6.0f}s  mean {statistics.fmean(window):.4f}"
                     f"  peak {max(window):.4f}  [{mark}]")
    (session / "summary.txt").write_text("\n".join(lines) + "\n")

    print("\n".join(lines[:7]))
    print(f"\nwrote {len(manifest)} clips to {out_dir}")
    print(f"wrote {session / 'manifest.csv'}")
    print(f"wrote {session / 'summary.txt'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
