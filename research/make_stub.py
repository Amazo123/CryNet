"""Build tiny stand-in ICD archives so the whole pipeline can be exercised locally."""
import csv, io, os, shutil, zipfile, wave
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
STUB = ROOT / "_stub_cache"
(STUB / "audio").mkdir(parents=True, exist_ok=True)
(STUB / "metadata").mkdir(parents=True, exist_ok=True)

rows = list(csv.DictReader(open(ROOT / "_cache" / "metadata" / "all28479.csv",
                                encoding="utf-8-sig")))
pos = [r for r in rows if r["class_string"] == "positive"]
neg = [r for r in rows if r["class_string"] == "negative"]
pos = pos[::max(1, len(pos)//250)][:250]
neg = neg[::max(1, len(neg)//250)][:250]

SR = 16000
rng = np.random.default_rng(0)


def synth(kind, dur=5.0):
    n = int(SR * dur)
    t = np.arange(n) / SR
    if kind == "cry":
        f0 = rng.uniform(300, 520)
        sig = sum((1.0 / (h + 1)) * np.sin(2 * np.pi * f0 * (h + 1) * t + rng.uniform(0, 6))
                  for h in range(7))
        sig = sig + 0.25 * rng.standard_normal(n)
        sig *= (0.5 + 0.5 * np.sin(2 * np.pi * rng.uniform(2, 5) * t))
        return np.clip(sig * 0.25, -1, 1).astype(np.float32)
    # non-cry: broadband / tonal but not cry-like
    if rng.random() < 0.5:
        sig = rng.standard_normal(n)
        sig = np.convolve(sig, np.ones(64) / 64, mode="same")
    else:
        sig = np.sin(2 * np.pi * rng.uniform(80, 600) * t) * 0.4 + 0.05 * rng.standard_normal(n)
    return np.clip(sig * 0.3, -1, 1).astype(np.float32)


def write_wav(zf, arcname, x):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    zf.writestr(arcname, buf.getvalue())


for name, subset, kind in (("positive", pos, "cry"), ("negative", neg, "non")):
    out = STUB / "audio" / f"{name}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in subset:
            stem = Path(r["wav"]).stem
            write_wav(zf, f"{name}/{stem}.wav", synth(kind))
    print(name, out.stat().st_size // 1024, "KB", len(subset), "clips")

with open(STUB / "metadata" / "all28479.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    for r in pos + neg:
        w.writerow(r)
print("stub manifest rows:", len(pos) + len(neg))

# reuse the real Kaggle corpora
for src, dst in ((ROOT / "_cache" / "cry4__karimeletriby_infant-cry-classification-4-classes.zip",
                  STUB / "cry4__karimeletriby_infant-cry-classification-4-classes.zip"),
                 (ROOT / "_cache" / "esc50__akaliutau_esc-50.zip", STUB / "esc50__akaliutau_esc-50.zip"),
                 (ROOT / "_cache" / "snore__tareqkhanemu_snoring.zip", STUB / "snore__tareqkhanemu_snoring.zip")):
    if src.exists() and not dst.exists():
        shutil.copyfile(src, dst)
print("stub cache ready:", sorted(p.name for p in STUB.iterdir()))
