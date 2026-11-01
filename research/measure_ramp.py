"""Measure the dark ramp and the swatches in a photograph of the colour check.

The dark ramp along the bottom of the colour-check page is six steps of
one hue, from black up.  In a photograph they come out as six measured
colours, and comparing them with the steps the firmware asked for says
two things at once:

  * which step the *reader* likes (they name it), and
  * how the panel renders that step - which is the number the palette
    has to be built around.

Run:  python research/measure_ramp.py <photo.jpg>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_photo import find_corners, rectify, median_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research" / "out"

W, H = 320, 240

# The ramp the firmware draws (hub_display.c, draw_colour_check).
RAMP = [(0, 0, 0), (2, 4, 4), (4, 8, 8), (7, 15, 16), (12, 26, 28),
        (24, 52, 56)]

# The swatches, in the order the page draws them.
SWATCHES = [
    ("BLACK", (0, 0, 0)),
    ("WHITE", (255, 255, 255)),
    ("TEAL", (45, 212, 191)),
    ("NAVY", (12, 20, 32)),
    ("GREEN", (52, 211, 153)),
    ("AMBER", (251, 191, 36)),
    ("ROSE", (251, 113, 133)),
    ("GREY", (122, 150, 146)),
]


def sample(rect, x, y, w, h):
    m = median_of(rect, x, y, w, h)
    return tuple(int(round(v)) for v in m)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    path = Path(argv[1])
    img = Image.open(path)
    corners = find_corners(img)
    rect = rectify(img, corners)
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rect, 0, 255).astype(np.uint8)).save(
        OUT / f"ramp_{path.stem[:8]}_rect.png")
    print(f"=== {path.name} ===")
    print("corners:", np.round(corners).astype(int).tolist())

    # ---- the page background ----
    bg = sample(rect, 0, 168, 3, 18)
    print(f"\n{'page background':22s} {bg}")

    # ---- the ramp ----
    rw = (W - 8) // len(RAMP)
    print(f"\n{'ramp step':22s} {'asked':>14s} {'measured':>18s} {'hue':>6s}")
    for i, asked in enumerate(RAMP):
        x = 4 + i * rw
        m = sample(rect, x + 6, 192, rw - 12, 10)
        mx, mn = max(m), min(m)
        sat = 0 if mx == 0 else (mx - mn) / mx
        print(f"{'ramp ' + str(i + 1) + ' ' + str(asked):22s} "
              f"{str(asked):>14s} {str(m):>18s} {sat:6.2f}")

    # ---- the swatches ----
    cols, w, h, gap = 4, 74, 56, 6
    x0 = (W - (cols * w + (cols - 1) * gap)) // 2
    print(f"\n{'swatch':22s} {'asked':>16s} {'measured':>18s}")
    for i, (name, asked) in enumerate(SWATCHES):
        cx = x0 + (i % cols) * (w + gap)
        cy = 40 + (i // cols) * (h + 24)
        m = sample(rect, cx + 10, cy + 8, w - 20, h - 16)
        print(f"{name:22s} {str(asked):>16s} {str(m):>18s}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
