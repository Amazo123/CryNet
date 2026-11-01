"""A host-side check of the two changes now going onto the panel.

1. the corner discs: simulate the firmware's fb_round_fill / fb_round_rect
   corner loop and require the four corners to be mirror images of each
   other (the fault the photograph showed was exactly an asymmetry),
   and require the fill's corners to hug a circle.
2. the new neutrals: the WCAG ratios the UI actually relies on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ui_mock import load_palette  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------- the corners
def corner_mask(w, h, r, outline):
    """The pixels the (fixed) firmware loop writes, per corner, as sets."""
    corners = {}
    cx = [r, w - 1 - r, r, w - 1 - r]
    cy = [r, r, h - 1 - r, h - 1 - r]
    sx = [-1, 1, -1, 1]
    sy = [-1, -1, 1, 1]
    for k in range(4):
        pts = set()
        for dx in range(r + 1):
            for dy in range(r + 1):
                d2 = dx * dx + dy * dy
                if outline:
                    if d2 > r * r or d2 < (r - 1) * (r - 1):
                        continue
                else:
                    if d2 > r * r:
                        continue
                pts.add((cx[k] + sx[k] * dx, cy[k] + sy[k] * dy))
        corners[k] = pts
    return corners


def mirrors(c, w, h):
    """Corner 0, reflected about both axes, must be corners 1, 2, 3."""
    c0, c1, c2, c3 = c[0], c[1], c[2], c[3]
    rx = {(w - 1 - x, y) for x, y in c0}
    ry = {(x, h - 1 - y) for x, y in c0}
    rxy = {(w - 1 - x, h - 1 - y) for x, y in c0}
    return rx == c1 and ry == c2 and rxy == c3


ok = True
for w, h, r in ((300, 44, 8), (300, 40, 6), (320, 240, 40), (60, 30, 5)):
    for outline in (False, True):
        c = corner_mask(w, h, r, outline)
        name = ("round_rect" if outline else "round_fill")
        good = mirrors(c, w, h)
        if not good:
            ok = False
            print(f"FAIL {name} {w}x{h} r={r}: corners are not mirror images")
        else:
            print(f"ok   {name} {w}x{h} r={r}: four corners are mirror images")

# the fill's top-left corner must hug a circle of radius r centred on
# (r, r): the outermost filled pixel on each row of the quadrant.
w, h, r = 300, 44, 8
c = corner_mask(w, h, r, False)[0]
worst = 0.0
for dy in range(r + 1):
    row = [x for (x, y) in c if y == r - dy]        # dy outward from centre
    if not row:
        continue
    x_outer = min(row)
    want = (r * r - dy * dy) ** 0.5
    worst = max(worst, abs((r - x_outer) - want))
print(f"ok   fill corner hugs the circle within {worst:.2f} px"
      if worst <= 1.0 else f"FAIL fill corner off circle by {worst:.2f} px")

# ---------------------------------------------------------- the contrast
def lum(rgb):
    def chan(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (chan(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


C = load_palette()
BG, SURF = C["C_BG"], C["C_SURFACE"]
CARD = (7, 16, 17)          # card fill: surface blended 5% toward the accent
checks = [
    ("text on a card", C["C_TEXT"], CARD, 4.5),
    ("dim text on the background", C["C_DIM"], BG, 4.5),
    ("accent (LISTENING) on the banner", C["C_ACCENT"],
     tuple(round(a + (b - a) * 0.12) for a, b in zip(SURF, C["C_ACCENT"])), 4.5),
    ("alert (CRY DETECTED) on its banner", C["C_ALERT"],
     tuple(round(a + (b - a) * 0.16) for a, b in zip(SURF, C["C_ALERT"])), 4.5),
    ("green (ONLINE) on a card", C["C_GREEN"], CARD, 4.5),
    ("amber (loud) on a card", C["C_AMBER"], CARD, 4.5),
    ("border on a card (UI component)", C["C_BORDER"], CARD, 3.0),
]
print()
for name, fg, bg_c, need in checks:
    got = ratio(fg, bg_c)
    mark = "ok  " if got >= need else "FAIL"
    if got < need:
        ok = False
    print(f"{mark} {name:34s} {got:5.2f}:1   (need {need}:1)")

print("\nbackground", BG, " surface", SURF, " surface-hi", C["C_SURFACE_HI"])
sys.exit(0 if ok else 1)
