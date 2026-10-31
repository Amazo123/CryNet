"""Measure a photograph of the panel against the firmware's own palette.

A photograph of the LCD is not a picture of the colours the firmware
asked for: the glass, the room light and the phone's white balance all
lie on top of it.  So the colours are *measured* instead of guessed.

The script does four things:

  1. finds the screen in the photograph (the blue-lit rectangle),
  2. rectifies it back to the 320x240 the firmware drew,
  3. prints the median colour of a set of known regions, next to the
     palette entry the firmware used there,
  4. fits a per-channel straight line  photo = a * expected + b  over
     the whole screen, so a residual that is bigger than the veil
     (a *colour* fault) can be told apart from the veil itself
     (a *brightness* fault).

Run:  python research/measure_photo.py <photo.jpg> [more photos ...]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "research" / "out"

W, H = 320, 240

# The palette, straight out of hub_display.c.
PALETTE = {
    "C_BG": (12, 20, 32),
    "C_SURFACE": (21, 32, 45),
    "C_SURFACE_HI": (29, 42, 57),
    "C_BORDER": (88, 112, 136),
    "C_TEXT": (228, 236, 245),
    "C_DIM": (122, 142, 163),
    "C_ACCENT": (45, 212, 191),
    "C_ACCENT_DIM": (24, 122, 110),
    "C_GREEN": (52, 211, 153),
    "C_AMBER": (251, 191, 36),
    "C_ALERT": (251, 113, 133),
}

# (name, x, y, w, h) in the firmware's 320x240 coordinates.  These are
# flat areas of the screen: no glyph strokes inside them.
REGIONS = [
    ("bg (left of the cards)", 2, 200, 6, 14, "C_BG"),
    ("bg (right of the cards)", 313, 200, 5, 14, "C_BG"),
    ("header bar", 150, 22, 30, 6, "C_SURFACE"),
    ("accent underline", 150, 30, 40, 2, "C_ACCENT_DIM"),
    ("banner fill", 150, 42, 60, 4, None),
    ("card 1 fill", 200, 96, 60, 6, None),
    ("RADIO square", 197, 14, 5, 5, "C_GREEN"),
    ("PHONE square", 259, 14, 5, 5, "C_AMBER"),
]


# --------------------------------------------------------------- the screen
def find_corners(img: Image.Image):
    """The four corners of the lit screen, in photo pixels.

    The screen is the big blue-lit region.  It is found by its colour
    (blue, and brighter than the desk) and then reduced to a
    quadrilateral by taking the extremes along the diagonals of its own
    principal axes - for a rectangle, those extremes *are* the corners.
    """
    # the search runs on a copy scaled down to 600 px: the blob walk is
    # a plain Python flood fill, and a 2000x1500 image would take
    # minutes.
    scale = 600.0 / max(img.size)
    small = img.convert("RGB").resize(
        (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
        Image.LANCZOS)
    a = np.asarray(small).astype(np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]

    mask = (b - r > 25) & (b > 55) & (g < b - 10)

    # Keep only the biggest blob: the blue PCB next to the screen is
    # blue too, and it is not the screen.
    mask = biggest_blob(mask)

    ys, xs = np.nonzero(mask)
    if len(xs) < 500:
        raise SystemExit("no screen found in the photograph")

    pts = np.stack([xs, ys], axis=1).astype(np.float64)
    centre = pts.mean(axis=0)
    centred = pts - centre
    # principal axes
    cov = centred.T @ centred / len(centred)
    vals, vecs = np.linalg.eigh(cov)
    u = vecs[:, np.argmax(vals)]
    v = vecs[:, np.argmin(vals)]
    a_ = centred @ u
    b_ = centred @ v
    corners = []
    for sa, sb in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        score = sa * a_ + sb * b_
        k = int(np.argmax(score))
        corners.append(pts[k])
    corners = np.array(corners)

    # the panel is landscape, so the left-most corner pair is the top
    tl = corners[np.argmin(corners[:, 0] + corners[:, 1])]
    br = corners[np.argmax(corners[:, 0] + corners[:, 1])]
    tr = corners[np.argmin(corners[:, 1] - corners[:, 0])]
    bl = corners[np.argmax(corners[:, 1] - corners[:, 0])]
    out = np.array([tl, tr, br, bl], dtype=np.float64)
    return out / scale          # back to the photo's own pixels


def biggest_blob(mask: np.ndarray) -> np.ndarray:
    """The largest connected region of True in the mask."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    current = 0
    best, best_size = 0, 0
    for y0 in range(h):
        for x0 in range(w):
            if mask[y0, x0] and labels[y0, x0] == 0:
                current += 1
                stack = [(y0, x0)]
                labels[y0, x0] = current
                size = 0
                while stack:
                    y, x = stack.pop()
                    size += 1
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] \
                                and labels[ny, nx] == 0:
                            labels[ny, nx] = current
                            stack.append((ny, nx))
                if size > best_size:
                    best_size, best = size, current
    return labels == best


def rectify(img: Image.Image, corners: np.ndarray) -> np.ndarray:
    """The photograph, mapped back onto the 320x240 the firmware drew."""
    a = np.asarray(img.convert("RGB")).astype(np.float64)
    tl, tr, br, bl = corners
    sx = np.linspace(0, W - 1, W)
    sy = np.linspace(0, H - 1, H)
    u, v = np.meshgrid(sx, sy)
    u = u / (W - 1)
    v = v / (H - 1)
    top = tl + u[..., None] * (tr - tl)
    bot = bl + u[..., None] * (br - bl)
    pts = top + v[..., None] * (bot - top)
    x = np.clip(pts[:, :, 0], 0, a.shape[1] - 1)
    y = np.clip(pts[:, :, 1], 0, a.shape[0] - 1)
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    x1 = np.clip(x0 + 1, 0, a.shape[1] - 1)
    y1 = np.clip(y0 + 1, 0, a.shape[0] - 1)
    fx = x - x0
    fy = y - y0
    out = (a[y0, x0] * (1 - fx)[..., None] * (1 - fy)[..., None]
           + a[y0, x1] * fx[..., None] * (1 - fy)[..., None]
           + a[y1, x0] * (1 - fx)[..., None] * fy[..., None]
           + a[y1, x1] * fx[..., None] * fy[..., None])
    return out


def median_of(rect: np.ndarray, x, y, w, h):
    patch = rect[y:y + h, x:x + w]
    return np.median(patch.reshape(-1, 3), axis=0)


def measure(path: Path):
    img = Image.open(path)
    corners = find_corners(img)
    rect = rectify(img, corners)
    print(f"\n=== {path.name}  ({img.width} x {img.height}) ===")
    print("corners:", np.round(corners).astype(int).tolist())

    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(rect, 0, 255).astype(np.uint8)).save(
        OUT / f"photo_{path.stem[:8]}.png")

    measured = {}
    print(f"{'region':26s} {'measured (r,g,b)':>22s}   {'palette':>16s}")
    for name, x, y, w, h, pal in REGIONS:
        m = median_of(rect, x, y, w, h)
        measured[name] = (m, pal)
        want = f"{PALETTE[pal]}" if pal else "-"
        print(f"{name:26s} {str(tuple(int(v) for v in m)):>22s}   {want:>16s}")

    # ---- the veil: a per-channel straight line over the flat areas ----
    pairs = [(m, PALETTE[p]) for m, p in measured.values() if p]
    if len(pairs) >= 3:
        print("\nper-channel fit  photo = a * expected + b  (flat areas)")
        for ch, cname in enumerate("rgb"):
            xs = np.array([p[1][ch] for p in pairs], dtype=np.float64)
            ys = np.array([p[0][ch] for p in pairs], dtype=np.float64)
            a, b = np.polyfit(xs, ys, 1)
            print(f"  {cname}: a = {a:5.3f}   b = {b:7.1f}")
        # the same fit with red and blue exchanged in the *expected*
        print("\nsame fit, but with the expected red and blue exchanged")
        for ch, cname in enumerate("rgb"):
            other = [2, 1, 0][ch]
            xs = np.array([p[1][other] for p in pairs], dtype=np.float64)
            ys = np.array([p[0][ch] for p in pairs], dtype=np.float64)
            a, b = np.polyfit(xs, ys, 1)
            resid = ys - (a * xs + b)
            print(f"  {cname}: a = {a:5.3f}   b = {b:7.1f}"
                  f"   rms residual {np.sqrt((resid ** 2).mean()):6.1f}")
    return rect


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    for arg in argv[1:]:
        measure(Path(arg))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
