"""A host-side preview of the hub's display.

This script is the design loop for the panel: it draws the screen the
firmware draws, on the host, in a second, so the layout can be looked at
and changed without flashing the board.

It reads three things out of the firmware, so the preview cannot quietly
drift away from what the hardware shows:

  * firmware/hub_infer/components/hub_display/font5x7.h  - the glyphs
  * firmware/hub_infer/components/hub_display/hub_display.c - the palette
    and the layout constants
  * the page layouts below, which mirror the drawing code in hub_display.c
    one for one.  When the firmware's layout changes, change it here too.

Run:  python research/ui_mock.py     ->  research/out/ui_*.png
"""
import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
DISPLAY_DIR = ROOT / "firmware" / "hub_infer" / "components" / "hub_display"
OUT = ROOT / "research" / "out"

W, H = 320, 240


# ---------------------------------------------------------------- the font
def load_font() -> dict[str, list[int]]:
    """The 5x7 glyphs, as columns of seven rows.

    The data is Adafruit's glcdfont, in which **bit 0 is the top row**
    and the glyphs use rows 0..6.  Adafruit_GFX::drawChar reads the
    bytes the same way - `for (j = 0; j < 8; j++, line >>= 1) if (line
    & 1)` - so bit 0 is the first row drawn.  Reading bit 7 as the top
    row instead turns every glyph upside down, which is what the first
    photograph of the panel showed.
    """
    txt = (DISPLAY_DIR / "font5x7.h").read_text(encoding="utf-8")
    body = txt.split("s_font5x7[][5] = {", 1)[1].split("};", 1)[0]
    out: dict[str, list[int]] = {}
    for i, row in enumerate(re.findall(r"\{([^}]*)\}", body)):
        vals = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{2})", row)]
        out[chr(0x20 + i)] = vals
    return out


FONT = load_font()
FONT_H = 7


def text_width(s: str, scale: int = 1) -> int:
    if not s:
        return 0
    return len(s) * 6 * scale - scale


def draw_text(d: ImageDraw.ImageDraw, x: int, y: int, s: str, colour, scale: int = 1):
    cursor = x
    for ch in s:
        glyph = FONT.get(ch, FONT["?"])
        for col in range(5):
            bits = glyph[col]
            for row in range(FONT_H):
                if bits & (1 << row):
                    d.rectangle(
                        [cursor + col * scale, y + row * scale,
                         cursor + col * scale + scale - 1, y + row * scale + scale - 1],
                        fill=colour)
        cursor += 6 * scale
    return cursor


def draw_text_centre(d, y: int, s: str, colour, scale: int = 1):
    draw_text(d, (W - text_width(s, scale)) // 2, y, s, colour, scale)


# ------------------------------------------------------------ the palette
def load_palette() -> dict[str, tuple]:
    """The colours, read out of the firmware so the two cannot drift."""
    txt = (DISPLAY_DIR / "hub_display.c").read_text(encoding="utf-8")
    out = {}
    for name, r, g, b in re.findall(
            r"#define\s+(C_\w+)\s+DISPLAY_RGB\((\d+),\s*(\d+),\s*(\d+)\)", txt):
        out[name] = (int(r), int(g), int(b))
    if not out:
        raise SystemExit("no palette found in hub_display.c")
    return out


def load_layout() -> dict[str, int]:
    txt = (DISPLAY_DIR / "hub_display.c").read_text(encoding="utf-8")
    out = {}
    for name, value in re.findall(r"#define\s+(\w+)\s+(\d+)\b", txt):
        out[name] = int(value)
    return out


def blend(a, b, t):
    """The firmware blends in RGB565; this is close enough to preview."""
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ---------------------------------------------------------------- drawing
def fill(d, x, y, w, h, colour):
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=colour)


def rect(d, x, y, w, h, colour):
    d.rectangle([x, y, x + w - 1, y + h - 1], outline=colour)


def round_fill(d, x, y, w, h, r, colour):
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=colour)


def round_rect(d, x, y, w, h, r, colour):
    d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, outline=colour)


def draw_pill(d, x, y, label, colour):
    fill(d, x, y + 2, 6, 6, colour)
    draw_text(d, x + 10, y, label, colour, 1)


def level_bar(d, x, y, w, h, level, colour, track, border):
    fill(d, x, y, w, h, track)
    fill_w = int((max(level, 0.0) ** 0.5) * (w - 2) + 0.5)
    if fill_w > 0:
        fill(d, x + 1, y + 1, fill_w, h - 2, colour)
    rect(d, x, y, w, h, border)


# ---------------------------------------------------------------- the pages
def dashboard(path: Path, cots, linked, crying, cot_id, confidence, level,
              clients, ble_ready, uptime_s, heading=None):
    """The dashboard, mirroring draw_dashboard() in hub_display.c."""
    C = load_palette()
    L = load_layout()

    header_h = L.get("HEADER_H", 30)
    banner_x, banner_y = L.get("BANNER_X", 10), L.get("BANNER_Y", 40)
    banner_w, banner_h = L.get("BANNER_W", 300), L.get("BANNER_H", 44)
    card_x, card_w = L.get("CARD_X", 10), L.get("CARD_W", 300)
    card_y0, card_h = L.get("CARD_Y0", 92), L.get("CARD_H", 40)
    card_step = L.get("CARD_STEP", 44)
    foot_y = L.get("FOOT_Y", 226)

    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    # ---- the header ----
    fill(d, 0, 0, W, header_h, C["C_SURFACE"])
    draw_text(d, 12, 8, "CRYNET", C["C_ACCENT"], 2)
    draw_text(d, 90, 12, "S3 HUB", C["C_DIM"], 1)
    draw_pill(d, 196, 11, "RADIO", C["C_GREEN"] if linked else C["C_DIM"])
    phone_col = (C["C_GREEN"] if clients > 0
                 else C["C_AMBER"] if ble_ready else C["C_DIM"])
    draw_pill(d, 258, 11, "PHONE", phone_col)
    fill(d, 0, header_h, W, 2, C["C_ACCENT_DIM"])

    # ---- the banner: what the system is doing ----
    banner_col = C["C_DIM"]
    banner = heading or "SEARCHING FOR THE COTS"
    if crying:
        banner, banner_col = "CRY DETECTED", C["C_ALERT"]
    elif linked:
        banner, banner_col = "LISTENING", C["C_ACCENT"]
    round_fill(d, banner_x, banner_y, banner_w, banner_h, 8,
               blend(C["C_SURFACE"], banner_col, 0.12))
    round_rect(d, banner_x, banner_y, banner_w, banner_h, 8,
               blend(C["C_BORDER"], banner_col, 0.85 if crying else 0.25))
    fill(d, banner_x + 3, banner_y + 10, 3, banner_h - 20, banner_col)
    draw_text(d, banner_x + 16, banner_y + 9, banner, banner_col, 2)

    if crying:
        right = f"COT {cot_id}  {confidence}%"
    elif linked:
        right = f"{level:.3f}"
    else:
        right = "--"
    draw_text(d, banner_x + banner_w - 12 - text_width(right), banner_y + 26,
              right, C["C_DIM"], 1)
    if crying and clients == 0:
        draw_text(d, banner_x + 16, banner_y + 26, "ALERT NOT DELIVERED",
                  C["C_AMBER"], 1)

    # ---- a card for every cot ----
    for i, cot in enumerate(cots):
        y = card_y0 + i * card_step
        known = cot["online"]
        accent = (C["C_ALERT"] if cot["crying"]
                  else C["C_ACCENT"] if known else C["C_BORDER"])
        round_fill(d, card_x, y, card_w, card_h, 6,
                   blend(C["C_SURFACE"], accent, 0.16 if cot["crying"] else 0.05))
        round_rect(d, card_x, y, card_w, card_h, 6,
                   blend(C["C_BORDER"], accent, 0.45 if known else 0.0))
        draw_text(d, card_x + 14, y + 8, f"COT {i + 1}",
                  C["C_TEXT"] if known else C["C_DIM"], 2)
        if cot["crying"]:
            state, state_col = f"CRY {cot['conf']}%", C["C_ALERT"]
        elif known:
            state, state_col = "ONLINE", C["C_GREEN"]
        else:
            state, state_col = "NO SIGNAL", C["C_DIM"]
        draw_text(d, card_x + card_w - 14 - text_width(state), y + 11,
                  state, state_col, 1)
        bar_col = (C["C_ALERT"] if cot["crying"]
                   else C["C_AMBER"] if cot["rms"] >= 0.030 else C["C_GREEN"])
        level_bar(d, card_x + 14, y + 28, card_w - 28, 7,
                  cot["rms"] if known else 0.0, bar_col,
                  C["C_SURFACE_HI"], C["C_BORDER"])

    # ---- the footer ----
    # The firmware counts the cots that are *answering*, not the cards
    # on the screen: a card for a quiet cot says NO SIGNAL, so a
    # "3 cots linked" above two NO SIGNAL cards would be a lie.
    count = sum(1 for cot in cots if cot["online"])
    label = ("no cots linked" if count == 0
             else f"{count} cot{'' if count == 1 else 's'} linked")
    draw_text(d, 12, foot_y, label, C["C_DIM"], 1)
    up = f"up {uptime_s // 60}:{uptime_s % 60:02d}"
    draw_text(d, W - 12 - text_width(up), foot_y, up, C["C_DIM"], 1)

    img.save(path)
    return path


def splash(path: Path, frame: int = 6):
    """The animated splash, mirroring draw_splash() in hub_display.c."""
    C = load_palette()
    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    bars, step = 36, 7
    x0 = (W - (bars * step - 3)) // 2
    y_mid = 84
    for i in range(bars):
        p = frame * 0.18 + i * 0.42
        a = 0.5 + 0.5 * math.sin(p * 1.7)
        b = 0.5 + 0.5 * math.sin(p * 0.53 + 1.7)
        h = int(26 * (0.18 + 0.82 * a * b))
        x = x0 + i * step
        fill(d, x, y_mid - h, 4, h, C["C_ACCENT"])
        fill(d, x, y_mid + 1, 4, h, C["C_ACCENT_DIM"])

    pulse = 0.5 + 0.5 * math.sin(frame * 0.12)
    title_col = blend(C["C_TEXT"], C["C_ACCENT"], 0.25 + 0.35 * pulse)
    draw_text_centre(d, 126, "CRYNET", title_col, 4)
    draw_text_centre(d, 164, "INFANT CRY MONITOR", C["C_DIM"], 1)
    draw_text_centre(d, 190, "the radio is listening", C["C_ACCENT"], 1)
    fill(d, 90, 206, 140, 6, C["C_SURFACE_HI"])
    fill(d, 90, 206, 87, 6, C["C_ACCENT"])
    rect(d, 89, 205, 142, 8, C["C_BORDER"])
    draw_text_centre(d, 222, "esp32-s3 hub", C["C_DIM"], 1)

    img.save(path)
    return path


def colour_check(path: Path):
    """The colour check, mirroring draw_colour_check() in hub_display.c."""
    C = load_palette()
    L = load_layout()
    header_h = L.get("HEADER_H", 30)

    img = Image.new("RGB", (W, H), C["C_BG"])
    d = ImageDraw.Draw(img)

    fill(d, 0, 0, W, header_h, C["C_SURFACE"])
    draw_text(d, 12, 8, "COLOUR CHECK", C["C_TEXT"], 2)
    fill(d, 0, header_h, W, 2, C["C_ACCENT_DIM"])

    swatches = [
        ("BLACK", (0, 0, 0)),
        ("WHITE", (255, 255, 255)),
        ("TEAL", C["C_ACCENT"]),
        ("NAVY", C["C_BG"]),
        ("GREEN", C["C_GREEN"]),
        ("AMBER", C["C_AMBER"]),
        ("ROSE", C["C_ALERT"]),
        ("GREY", C["C_DIM"]),
    ]
    cols, w, h, gap = 4, 74, 62, 6
    x0 = (W - (cols * w + (cols - 1) * gap)) // 2
    for i, (name, colour) in enumerate(swatches):
        cx = x0 + (i % cols) * (w + gap)
        cy = 46 + (i // cols) * (h + 22)
        fill(d, cx, cy, w, h, colour)
        rect(d, cx, cy, w, h, C["C_BORDER"])
        draw_text(d, cx + (w - text_width(name, 1)) // 2, cy + h + 5,
                  name, C["C_DIM"], 1)

    foot = "backlight 55%  -  press BOOT to go back"
    draw_text_centre(d, H - 16, foot, C["C_DIM"], 1)

    img.save(path)
    return path


COTS_QUIET = [
    {"online": True, "crying": False, "rms": 0.084, "conf": 0},
    {"online": True, "crying": False, "rms": 0.012, "conf": 0},
    {"online": False, "crying": False, "rms": 0.0, "conf": 0},
]

COTS_CRYING = [
    {"online": True, "crying": True, "rms": 0.284, "conf": 97},
    {"online": True, "crying": False, "rms": 0.141, "conf": 0},
    {"online": False, "crying": False, "rms": 0.0, "conf": 0},
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    paths = [
        dashboard(OUT / "ui_dashboard.png", COTS_QUIET, True, False, 0, 0,
                  0.084, 1, True, 12 * 60 + 4),
        dashboard(OUT / "ui_dashboard_alert.png", COTS_CRYING, True, True,
                  1, 97, 0.284, 1, True, 12 * 60 + 4),
        dashboard(OUT / "ui_dashboard_alert_nophone.png", COTS_CRYING, True,
                  True, 1, 97, 0.284, 0, True, 12 * 60 + 4),
        splash(OUT / "ui_splash.png"),
        colour_check(OUT / "ui_colour_check.png"),
    ]
    for p in paths:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
