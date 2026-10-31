"""Generate the 5x7 font header from Adafruit's glcdfont.c.

The font is the classic one Adafruit's GFX library has used since 1.0:
five column bytes per character, the low seven bits of each byte being
the seven rows of the glyph.  Taking it from the library rather than
typing the glyphs out by hand keeps the display's text exactly the same
as the legacy firmware's.

**The table is indexed by the raw ASCII code, not by ASCII - 0x20.**
Adafruit_GFX::drawChar reads `font[c * 5 + i]` with no subtraction, so
the byte offset of a character is `code * 5`.  The first 32 entries of
the table (ASCII 0x00-0x1F) are decorative icons - hearts and diamonds -
and the printable set starts at 0x20.  An earlier version of this script
assumed the ASCII-0x20 layout, which drew every character 32 glyphs
early: the panel showed hearts and diamonds instead of letters.

The base offset is therefore *detected* rather than assumed: the script
finds the classic exclamation mark (00 00 5F 00 00) in the table and
derives the base from where it lands.  If the font is ever replaced by
one with a different layout, the check below fails loudly instead of
producing a screen full of nonsense.
"""
import io
import os
import re
import sys

CANDIDATES = [
    os.path.expanduser(
        "~/Documents/Arduino/libraries/Adafruit_GFX_Library/glcdfont.c"),
    "research/_cache/glcdfont_api.c",
]

FIRST = 0x20
LAST = 0x7E
# The classic '!' - five columns, a vertical bar in the middle.
BANG = [0x00, 0x00, 0x5F, 0x00, 0x00]


def find_source():
    for path in CANDIDATES:
        if os.path.exists(path):
            return path
    sys.exit("no glcdfont.c found in " + ", ".join(CANDIDATES))


def load(path):
    text = io.open(path, encoding="utf-8", errors="replace").read()
    body = text.split("font[] PROGMEM = {", 1)[1].split("};", 1)[0]
    body = re.sub(r"//[^\n]*", "", body)          # drop the per-glyph comments
    return [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]{2})", body)]


def detect_base(values):
    """Work out where ASCII 0x21 sits in the table."""
    hits = [i for i in range(len(values) - 4)
            if values[i:i + 5] == BANG and i % 5 == 0]
    if len(hits) != 1:
        sys.exit(f"the classic '!' was found at {len(hits)} places; "
                 "cannot work out the table's layout")
    base = hits[0] // 5 - 0x21
    if base < 0:
        sys.exit("the table's printable glyphs do not start where expected")
    return base


def main():
    src = find_source()
    values = load(src)
    base = detect_base(values)
    print(f"source {src}: {len(values)} bytes, printable glyphs at "
          f"index {base} + code")

    rows = []
    for code in range(FIRST, LAST + 1):
        off = (base + code) * 5
        if off + 5 > len(values):
            sys.exit(f"the font is too short for ASCII 0x{code:02X}")
        rows.append("    {" + ", ".join(f"0x{values[off + i]:02X}"
                                        for i in range(5))
                    + f"}},   /* {chr(code)} */")

    out = f"""/*
 * The classic 5x7 bitmap font, as ASCII 0x20 to 0x7E.
 *
 * Generated from Adafruit's glcdfont.c (the font Adafruit's GFX library
 * has used since 1.0) by research/build_font.py.  Five column
 * bytes per character; the low seven bits of each byte are the seven
 * rows of the glyph, the topmost row first - the same order
 * Adafruit_GFX::drawChar reads them in.
 *
 * The table in glcdfont.c is indexed by the raw ASCII code, so the glyph
 * for ASCII c is glcdfont.c's bytes [base + c] * 5 .. +5, where the
 * generator detected the base ({base}) rather than assuming it.
 */

#ifndef FONT5X7_H
#define FONT5X7_H

#define FONT5X7_FIRST 0x{FIRST:02X}
#define FONT5X7_LAST  0x{LAST:02X}
#define FONT5X7_WIDTH 5
#define FONT5X7_HEIGHT 7

static const uint8_t s_font5x7[][5] = {{
{chr(10).join(rows)}
}};

#endif /* FONT5X7_H */
"""

    path = 'firmware/hub_infer/components/hub_display/font5x7.h'
    io.open(path, 'w', encoding='utf-8', newline='\n').write(out)
    print(f"wrote {path} ({len(rows)} glyphs)")


if __name__ == "__main__":
    main()
