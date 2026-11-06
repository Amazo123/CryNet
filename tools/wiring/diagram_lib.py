"""Tiny SVG layout library for the CryNet wiring diagrams.

Why a generator instead of hand-written SVG: the previous
SYSTEM_WIRING_DIAGRAMS.html had wires crossing text and text sitting on
components.  Hand-placed coordinates cannot be checked; these can.

Coordinates are in "diagram units".  Every page uses a 1000-wide viewBox.
Text is measured with an approximate Arial/Consolas metric so the
collision checker can guarantee that no two labels overlap and that no
wire runs through an unrelated label.

API
---
    d = Page(1000, 560, "Cot node - complete wiring")
    d.box(30, 60, 210, 260, "LX-LCBST-TC-001", cls="mod")
    d.label(40, 90, "B+", size=13, mono=True)
    d.wire([(240, 100), (330, 100)], color="red")
    d.check()          # raises LayoutError on any overlap
    print(d.svg())
"""

import html as _html

# ---------------------------------------------------------------- metrics ---

_SANS = 0.545   # average glyph width as a fraction of font size, Arial
_MONO = 0.600   # Consolas


def text_width(s, size, mono=False):
    """Approximate rendered width of *s* in diagram units."""
    per = _MONO if mono else _SANS
    # bold text is a touch wider
    return len(s) * size * per


def text_height(size):
    return size * 1.22


def text_box(x, y, s, size, anchor="start", mono=False):
    """Bounding box of a text item, given its baseline anchor point."""
    w = text_width(s, size, mono)
    if anchor == "middle":
        x0 = x - w / 2.0
    elif anchor == "end":
        x0 = x - w
    else:
        x0 = x
    # baseline y: box spans roughly from y-0.8*size to y+0.25*size
    return (x0, y - 0.82 * size, x0 + w, y + 0.26 * size)


def boxes_overlap(a, b, pad=0.0):
    return not (a[2] + pad <= b[0] or b[2] + pad <= a[0]
                or a[3] + pad <= b[1] or b[3] + pad <= a[1])


def _inside(a, b):
    """True if box *a* lies fully within box *b*."""
    return (a[0] >= b[0] and a[1] >= b[1]
            and a[2] <= b[2] and a[3] <= b[3])


class LayoutError(Exception):
    pass


# ----------------------------------------------------------------- canvas ---

class Page:
    def __init__(self, width, height, title, subtitle=None, heading=None):
        self.width = width
        self.height = height
        self.title = title
        self.subtitle = subtitle
        self.heading = heading
        self.items = []       # (kind, payload)
        self.labels = []      # dicts for the checker
        self.boxes = []       # component rects
        self.wires = []       # dicts for the checker
        self._label_id = 0
        self._wire_id = 0

    # -- primitives ---------------------------------------------------------

    def label(self, x, y, s, size=13, cls="note", anchor="start",
              mono=False, color=None, exempt_from=(), owner=None):
        """Place a text label.  *exempt_from* is a set of wire ids that may
        touch this label (usually the wires the label annotates)."""
        self._label_id += 1
        item = {"kind": "text", "x": x, "y": y, "s": s, "size": size,
                "cls": cls, "anchor": anchor, "mono": mono, "color": color}
        self.items.append(item)
        self.labels.append({
            "id": self._label_id, "box": text_box(x, y, s, size, anchor, mono),
            "s": s, "exempt": set(exempt_from), "owner": owner, "cls": cls,
        })
        return self._label_id

    def box(self, x, y, w, h, title=None, cls="mod", sub=None, radius=10,
            sub_size=11.5, container=False):
        """A component rectangle.  *title* is drawn at the top-left inside.

        *container* marks a region (e.g. a board photograph) that other
        components are drawn inside; labels of contained components are
        allowed to sit on it."""
        self.items.append({"kind": "box", "x": x, "y": y, "w": w, "h": h,
                           "cls": cls, "radius": radius})
        self.boxes.append({"id": len(self.boxes), "rect": (x, y, x + w, y + h),
                            "title": title, "container": container})
        if title:
            self.label(x + 12, y + 24, title, size=15, cls="title",
                       owner=len(self.boxes) - 1)
        if sub:
            for i, line in enumerate(sub):
                self.label(x + 12, y + 44 + i * 17, line, size=sub_size,
                           cls="small", owner=len(self.boxes) - 1)
        return len(self.boxes) - 1

    def part(self, x, y, w, h, text, cls="part", size=11.5, mono=False):
        """A small discrete part (resistor, capacitor, diode...)."""
        self.items.append({"kind": "box", "x": x, "y": y, "w": w, "h": h,
                           "cls": cls, "radius": 4})
        self.boxes.append({"id": len(self.boxes), "rect": (x, y, x + w, y + h),
                            "title": text})
        self.label(x + w / 2.0, y + h / 2.0 + size * 0.36, text, size=size,
                   cls="small", anchor="middle", mono=mono,
                   owner=len(self.boxes) - 1)
        return len(self.boxes) - 1

    def dot(self, x, y):
        self.items.append({"kind": "dot", "x": x, "y": y})

    def ground(self, x, y, label=None, dir="down"):
        """Earth symbol attached at (x, y).

        *dir* is the direction the stub runs: "down" (default), "left",
        "right" or "up".  A sideways symbol lets a device's ground pin
        point into an empty gutter instead of dropping through the rows
        below it."""
        self.items.append({"kind": "gnd", "x": x, "y": y, "dir": dir})
        if label:
            self.label(x + 8, y + 4, label, size=11, cls="small", mono=True)
        return self

    def vpart(self, x, y, w, h, text, cls="part", size=11.5, label_dx=10,
              anchor="start"):
        """Vertical discrete part: narrow box, label set beside it."""
        self.items.append({"kind": "box", "x": x, "y": y, "w": w, "h": h,
                           "cls": cls, "radius": 3})
        self.boxes.append({"id": len(self.boxes), "rect": (x, y, x + w, y + h),
                            "title": text})
        owner = len(self.boxes) - 1
        lx = x + w + label_dx if anchor == "start" else x + label_dx
        self.label(lx, y + h / 2.0 + size * 0.36, text,
                   size=size, cls="small", mono=True, owner=owner,
                   anchor=anchor)
        return owner

    def wire(self, points, color="black", width=2.5, dash=None):
        """Polyline wire.  Returns the wire id."""
        self._wire_id += 1
        self.items.append({"kind": "wire", "points": points, "color": color,
                           "width": width, "dash": dash})
        self.wires.append({"id": self._wire_id, "points": points,
                           "color": color, "width": width})
        return self._wire_id

    def link(self, a, b, color="black", width=2.5, dash=None, label=None,
             label_dy=-7, label_size=11, label_anchor="middle", label_x=None,
             label_cls="small", mono=False):
        """Straight horizontal wire between two x positions on one y, with an
        optional label placed just above the line."""
        y = a[1]
        wid = self.wire([a, b], color=color, width=width, dash=dash)
        if label:
            lx = label_x if label_x is not None else (a[0] + b[0]) / 2.0
            self.label(lx, y + label_dy, label, size=label_size,
                       cls=label_cls, anchor=label_anchor, mono=mono,
                       exempt_from=(wid,), color=color if color != "black" else None)
        return wid

    def vlink(self, a, b, color="black", width=2.5, dash=None, label=None,
              label_dx=6, label_size=11, label_cls="small", mono=False):
        """Vertical wire between two y positions on one x."""
        x = a[0]
        wid = self.wire([a, b], color=color, width=width, dash=dash)
        if label:
            self.label(x + label_dx, (a[1] + b[1]) / 2.0, label,
                       size=label_size, cls=label_cls, mono=mono,
                       exempt_from=(wid,))
        return wid

    # -- reusable sub-circuits ----------------------------------------------

    def battery_sense(self, bx, by, sx, sy, label="1.31 V"):
        """Battery-sense divider, drawn in the band below the boards.

        (bx, by) is the module's B+ pad; (sx, sy) is the board's ADC pin.
        The 220 k top resistor and the 100 k / 100 nF shunt pair make the
        usual 100 k/300 k divider: about 1.31 V at a 4.2 V cell.
        """
        self.wire([(bx, by), (232, by), (232, 375), (250, 375)], color="red")
        self.part(250, 362, 76, 26, "220 kΩ")
        self.wire([(326, 375), (345, 375)], color="red")
        self.dot(345, 375)
        self.label(352, 366, label, size=11, cls="small", mono=True)
        self.label(250, 352, "sense divider", size=11, cls="small")
        # shunt pair
        self.wire([(345, 375), (345, 398)], color="black")
        self.wire([(345, 398), (320, 398)], color="black")
        self.wire([(345, 398), (370, 398)], color="black")
        self.vpart(308, 400, 24, 44, "100 kΩ", anchor="end", label_dx=-4)
        self.vpart(358, 400, 24, 44, "100 nF", label_dx=4)
        self.wire([(320, 444), (320, 456)], color="black")
        self.ground(320, 456)
        self.wire([(370, 444), (370, 456)], color="black")
        self.ground(370, 456)
        # sense node out to the ADC pin
        self.wire([(345, 375), (sx, 375), (sx, sy)], color="black")
        return self

    # -- checks -------------------------------------------------------------

    def check(self):
        problems = []
        # text vs text
        for i in range(len(self.labels)):
            for j in range(i + 1, len(self.labels)):
                a, b = self.labels[i], self.labels[j]
                if boxes_overlap(a["box"], b["box"], pad=1.0):
                    problems.append(
                        "text overlap: %r at %s vs %r at %s"
                        % (a["s"], _fmt(a["box"]), b["s"], _fmt(b["box"])))
        # text vs foreign component box
        for lab in self.labels:
            for bx in self.boxes:
                if lab["owner"] == bx["id"]:
                    continue
                if bx.get("container") and _inside(lab["box"], bx["rect"]):
                    continue
                if boxes_overlap(lab["box"], bx["rect"], pad=0.5):
                    problems.append(
                        "text %r %s sits on component %r"
                        % (lab["s"], _fmt(lab["box"]), bx["title"]))
        # wire vs text
        for w in self.wires:
            for lab in self.labels:
                if w["id"] in lab["exempt"]:
                    continue
                if _poly_hits_box(w["points"], lab["box"]):
                    problems.append(
                        "wire %s crosses text %r at %s"
                        % (w["id"], lab["s"], _fmt(lab["box"])))
        if problems:
            raise LayoutError(
                "%s: %d layout problem(s)\n  %s"
                % (self.title, len(problems), "\n  ".join(problems)))
        return True

    # -- output -------------------------------------------------------------

    def svg(self):
        out = ['<svg viewBox="0 0 %d %d" class="diagram">' % (self.width, self.height)]
        for it in self.items:
            k = it["kind"]
            if k == "box":
                out.append(
                    '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" class="%s"/>'
                    % (it["x"], it["y"], it["w"], it["h"], it["radius"], it["cls"]))
            elif k == "dot":
                out.append('<circle cx="%.1f" cy="%.1f" r="4" class="dot"/>'
                           % (it["x"], it["y"]))
            elif k == "gnd":
                x, y = it["x"], it["y"]
                d = it.get("dir", "down")
                if d == "down":
                    stub = "M%.1f %.1f v8" % (x, y)
                    bars = ("M%.1f %.1f h18 M%.1f %.1f h12 M%.1f %.1f h6"
                            % (x - 9, y + 8, x - 6, y + 13, x - 3, y + 18))
                elif d == "up":
                    stub = "M%.1f %.1f v-8" % (x, y)
                    bars = ("M%.1f %.1f h18 M%.1f %.1f h12 M%.1f %.1f h6"
                            % (x - 9, y - 8, x - 6, y - 13, x - 3, y - 18))
                elif d == "left":
                    stub = "M%.1f %.1f h-8" % (x, y)
                    bars = ("M%.1f %.1f v18 M%.1f %.1f v12 M%.1f %.1f v6"
                            % (x - 8, y - 9, x - 13, y - 6, x - 18, y - 3))
                else:  # right
                    stub = "M%.1f %.1f h8" % (x, y)
                    bars = ("M%.1f %.1f v18 M%.1f %.1f v12 M%.1f %.1f v6"
                            % (x + 8, y - 9, x + 13, y - 6, x + 18, y - 3))
                out.append('<path d="%s" class="wire black" stroke-width="2.5"/>'
                           % stub)
                out.append('<path d="%s" class="wire black" stroke-width="2.5"/>'
                           % bars)
            elif k == "wire":
                pts = " ".join("%.1f,%.1f" % (p[0], p[1]) for p in it["points"])
                dash = ' stroke-dasharray="%s"' % it["dash"] if it["dash"] else ""
                out.append('<polyline points="%s" class="wire %s" stroke-width="%.1f"%s/>'
                           % (pts, it["color"], it["width"], dash))
            else:
                cls = it["cls"]
                if it["mono"]:
                    cls += " mono"
                style = ' style="fill:%s"' % it["color"] if it["color"] else ""
                out.append('<text x="%.1f" y="%.1f" class="%s" text-anchor="%s"%s>%s</text>'
                           % (it["x"], it["y"], cls, it["anchor"], style,
                              _html.escape(it["s"])))
        out.append("</svg>")
        return "\n".join(out)


def _fmt(box):
    return "(%.0f,%.0f)-(%.0f,%.0f)" % box


def _seg_hits_box(p, q, box, pad=0.0):
    x1, y1 = p
    x2, y2 = q
    bx0, by0, bx1, by1 = box
    bx0 -= pad; by0 -= pad; bx1 += pad; by1 += pad
    if abs(x1 - x2) < 1e-9:                      # vertical
        lo, hi = sorted((y1, y2))
        return bx0 <= x1 <= bx1 and not (hi <= by0 or lo >= by1)
    if abs(y1 - y2) < 1e-9:                      # horizontal
        lo, hi = sorted((x1, x2))
        return by0 <= y1 <= by1 and not (hi <= bx0 or lo >= bx1)
    # diagonal: sample
    steps = 24
    for i in range(steps + 1):
        t = i / float(steps)
        xx = x1 + (x2 - x1) * t
        yy = y1 + (y2 - y1) * t
        if bx0 <= xx <= bx1 and by0 <= yy <= by1:
            return True
    return False


def _poly_hits_box(points, box):
    for i in range(len(points) - 1):
        if _seg_hits_box(points[i], points[i + 1], box):
            return True
    return False
