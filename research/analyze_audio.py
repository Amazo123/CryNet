"""Audio-level forensics on candidate zips: SR, duration, RMS, F0, spectral shape, real-vs-synthetic."""
import collections
import io
import os
import re
import zipfile

import numpy as np
import soundfile as sf

DL = r"C:\Users\HP\.t3\projects\fp-2\research\dl"
N_PER_CLASS = 12


def analyze_bytes(data):
    try:
        x, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=False)
    except Exception:
        return None
    if x.ndim > 1:
        x = x.mean(axis=1)
    n = len(x)
    if n < 1600:
        return None
    dur = n / sr
    rms = float(np.sqrt(np.mean(x**2)))
    peak = float(np.max(np.abs(x)))
    # dominant F0 via autocorrelation on 40ms frames, 100-1200 Hz
    f0s = []
    fl = int(sr * 0.04)
    hop = fl
    for i in range(0, max(1, n - fl), hop):
        seg = x[i : i + fl]
        if len(seg) < fl or rms < 1e-4:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[fl - 1 :]
        lo, hi = int(sr / 1200), int(sr / 100)
        if hi >= len(ac):
            continue
        peakidx = lo + int(np.argmax(ac[lo:hi]))
        if ac[peakidx] > 0:
            f0s.append(sr / peakidx)
    f0 = float(np.median(f0s)) if f0s else float("nan")
    # spectral centroid + flatness (noise vs tonal)
    S = np.abs(np.fft.rfft(x[: min(n, 65536)] * np.hanning(min(n, 65536))))
    freqs = np.fft.rfftfreq(min(n, 65536), 1 / sr)
    centroid = float((S * freqs).sum() / (S.sum() + 1e-12))
    psd = S**2 + 1e-12
    flatness = float(np.exp(np.mean(np.log(psd))) / (np.mean(psd) + 1e-12))
    return dict(sr=sr, dur=dur, rms=rms, peak=peak, f0=f0, centroid=centroid, flatness=flatness)


def class_key(name):
    parts = name.split("/")
    return "/".join(parts[:-1]) if len(parts) > 1 else "(root)"


def analyze_zip(path, max_classes=14):
    print("\n" + "#" * 80)
    print(os.path.basename(path))
    print("#" * 80)
    z = zipfile.ZipFile(path)
    names = [n for n in z.namelist() if not n.endswith("/") and n.lower().endswith((".wav", ".ogg", ".flac"))]
    by_class = collections.defaultdict(list)
    for n in names:
        by_class[class_key(n)].append(n)
    classes = sorted(by_class, key=lambda c: -len(by_class[c]))[:max_classes]
    for c in classes:
        files = sorted(by_class[c])
        step = max(1, len(files) // N_PER_CLASS)
        sample = files[::step][:N_PER_CLASS]
        rows = []
        for f in sample:
            r = analyze_bytes(z.read(f))
            if r:
                r["name"] = os.path.basename(f)
                rows.append(r)
        if not rows:
            continue
        arr = {k: np.array([r[k] for r in rows], dtype=float) for k in rows[0] if k != "name"}
        srs = collections.Counter(int(r["sr"]) for r in rows)
        print(f"\n  [{c}]  n={len(by_class[c])} sampled={len(rows)}  sr={dict(srs)}")
        print(
            f"     dur  med={np.median(arr['dur']):.2f}s  min={arr['dur'].min():.2f} max={arr['dur'].max():.2f}"
        )
        print(
            f"     rms  med={np.median(arr['rms']):.4f}  peak med={np.median(arr['peak']):.3f}"
        )
        f0s = arr["f0"][~np.isnan(arr["f0"])]
        if len(f0s):
            print(
                f"     f0   med={np.median(f0s):.0f}Hz  p10={np.percentile(f0s,10):.0f} "
                f"p90={np.percentile(f0s,90):.0f}"
            )
        print(
            f"     cent med={np.median(arr['centroid']):.0f}Hz  flat med={np.median(arr['flatness']):.4f}"
        )
        print("     eg:", ", ".join(r["name"][:34] for r in rows[:4]))


for f in sorted(os.listdir(DL)):
    if f.endswith(".zip") and f != "test.zip":
        analyze_zip(os.path.join(DL, f))
