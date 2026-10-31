"""Compare a photograph of the panel with the picture the firmware drew.

`measure_photo.py` says *what* colour the glass shows in a few places.
This asks the harder question: *which* colour is it showing, given that
the photograph is veiled and blurred and a few pixels out of place.

It renders the expected screen with `ui_mock.py` (the same layout the
firmware draws), aligns it to the rectified photograph, and then asks,
for every palette entry, what the photograph shows where the firmware
put that entry.  It also fits the two rival hypotheses - the colours as
drawn, and the colours with red and blue exchanged - and reports the
residual of each.

Run:  python research/compare_photo.py <photo.jpg>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_mock                                        # noqa: E402
from measure_photo import PALETTE, find_corners, rectify   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research" / "out"


def expected_screen(path: Path) -> np.ndarray:
    """The screen the firmware drew for the state in the photograph.

    One cot answering, two quiet, the radio up, and no caregiver
    phone attached - which is why the PHONE square is amber.
    """
    cots = [
        {"online": True, "crying": False, "rms": 0.010, "conf": 0},
        {"online": False, "crying": False, "rms": 0.0, "conf": 0},
        {"online": False, "crying": False, "rms": 0.0, "conf": 0},
    ]
    ui_mock.dashboard(path, cots, True, False, 0, 0, 0.010, 0, True, 23)
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


def align(photo: np.ndarray, expected: np.ndarray) -> tuple[np.ndarray, int, int]:
    """Slide the expected screen over the photograph to the best fit."""
    best = None
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            ys = slice(max(0, dy), 240 + min(0, dy))
            xs = slice(max(0, dx), 320 + min(0, dx))
            p = photo[ys, xs]
            e = expected[max(0, -dy):240 - max(0, dy),
                         max(0, -dx):320 - max(0, dx)]
            if p.shape != e.shape:
                continue
            score = -np.abs(p - e).mean()
            if best is None or score < best[0]:
                best = (score, dx, dy)
    _, dx, dy = best
    out = np.zeros_like(photo)
    ys = slice(max(0, dy), 240 + min(0, dy))
    xs = slice(max(0, dx), 320 + min(0, dx))
    out[ys, xs] = expected[max(0, -dy):240 - max(0, dy),
                           max(0, -dx):320 - max(0, dx)]
    return out, dx, dy


def main(argv):
    photo_path = Path(argv[1])
    img = Image.open(photo_path)
    corners = find_corners(img)
    photo = rectify(img, corners)

    exp_path = OUT / "_expected.png"
    exp_path.parent.mkdir(parents=True, exist_ok=True)
    expected = expected_screen(exp_path)
    aligned, dx, dy = align(photo, expected)
    print(f"aligned the expected screen at dx={dx}, dy={dy}")

    print("\nwhat the glass shows where the firmware put each colour")
    print(f"{'palette entry':12s} {'wanted (r,g,b)':>20s} {'measured':>20s}"
          f"   px")
    for name, (r, g, b) in PALETTE.items():
        want = np.array([r, g, b], dtype=np.float64)
        d = np.abs(aligned - want).max(axis=2)
        mask = d < 12
        n = int(mask.sum())
        if n < 30:
            continue
        got = photo[mask].mean(axis=0)
        print(f"{name:12s} {str((r, g, b)):>20s} "
              f"{str(tuple(int(v) for v in got)):>20s}   {n}")

    print("\nhypothesis tests over every pixel")
    variants = {
        "as drawn (RGB)": expected,
        "red and blue exchanged (BGR)": expected[:, :, ::-1],
    }
    for label, variant in variants.items():
        rms = []
        for ch in range(3):
            x = variant[:, :, ch].ravel()
            y = photo[:, :, ch].ravel()
            a, b = np.polyfit(x, y, 1)
            rms.append(float(np.sqrt(((y - (a * x + b)) ** 2).mean())))
        print(f"  {label:30s} rms residual  r {rms[0]:6.1f}  "
              f"g {rms[1]:6.1f}  b {rms[2]:6.1f}   (mean {np.mean(rms):5.1f})")

    # ---- the veil, fitted with the colours as drawn ----
    print("\nthe veil, per channel, with the colours as drawn")
    for ch, cname in enumerate("rgb"):
        x = expected[:, :, ch].ravel()
        y = photo[:, :, ch].ravel()
        a, b = np.polyfit(x, y, 1)
        print(f"  {cname}: photo = {a:5.3f} * expected + {b:6.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
