"""Page 5 - LX-LCBST-TC-001 pad map and bench procedure."""

from diagram_lib import Page

W, H = 1000, 470


def build():
    p = Page(W, H, "5 / LX-LCBST-TC-001 - pad map and bench procedure",
             "From the user's front-and-back photograph - Chinese silk text translated")

    # ------------------------------------------------------------ FRONT ---
    front = p.box(60, 60, 330, 228, "FRONT", cls="proposed", container=True)
    usbc = p.box(150, 95, 90, 30, None, cls="part")
    p.label(160, 115, "USB-C", size=11, cls="small", owner=usbc)
    chg = p.box(110, 160, 80, 40, None, cls="part")
    p.label(116, 185, "charger IC", size=10.5, cls="small", owner=chg)
    trim = p.box(220, 155, 55, 45, None, cls="part")
    p.label(226, 182, "trimpot", size=10.5, cls="small", owner=trim)
    p100 = p.box(300, 160, 70, 40, None, cls="part")
    p.label(308, 185, "100", size=11, cls="small", owner=p100)
    for name, x in (("B-", 100), ("B+", 170)):
        p.label(x, 240, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=front)
    p.label(80, 260, "battery", size=10.5, cls="small", owner=front)
    p.label(300, 240, "-", size=12.5, cls="pin", anchor="middle", mono=True,
            owner=front)
    p.label(350, 240, "+", size=12.5, cls="pin", anchor="middle", mono=True,
            owner=front)
    p.label(280, 260, "unlabelled pair", size=10.5, cls="small", owner=front)
    p.label(280, 274, "verify with meter", size=10.5, cls="small", owner=front)

    # ------------------------------------------------------------- BACK ---
    back = p.box(560, 60, 340, 228, "BACK", cls="proposed", container=True)
    for name, x in (("VO+", 580), ("VO-", 645), ("IN-", 730), ("IN+", 795)):
        p.label(x, 110, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=back)
    p.label(575, 128, "output", size=10.5, cls="small", owner=back)
    p.label(725, 128, "input", size=10.5, cls="small", owner=back)
    p.label(600, 165, "LX-LCBST", size=15, cls="title", owner=back)
    for name, x in (("VO+", 580), ("VO-", 645), ("B+", 730), ("B-", 795)):
        p.label(x, 230, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=back)
    p.label(575, 248, "output (2 pairs)", size=10.5, cls="small", owner=back)
    p.label(725, 248, "battery", size=10.5, cls="small", owner=back)

    # ---------------------------------------------------- the procedure ---
    p.label(60, 310, "Bench procedure, before any ESP32 is connected:",
            size=13, cls="note")
    steps = [
        "1 - Cell on B+/B-: turn the trimpot until VO+/VO- reads 5.1 V on a meter, no load.",
        "2 - USB-C in: measure the charge current with a series meter - the cell must allow it.",
        "3 - Confirm the charge ends at 4.2 V.",
        "4 - Switch off: confirm the load is dead and measure the battery drain (boost quiescent unknown).",
        "5 - Run one node and compare it with the USB baseline.",
    ]
    y = 332
    for s in steps:
        p.label(60, y, s, size=12, cls="note")
        y += 20
    p.label(60, y + 6, "No T pad on this board - the listing's T-shorting notes belong to "
                       "other variants. Never short anything.",
            size=11, cls="small")

    notes = (
        '<div class="warning">Unknown until measured: the actual charge current (the '
        'program resistor is unreadable in the photo), the boost quiescent drain when off, '
        'the protection thresholds, and what the front - / + pair connects to. Buy ONE '
        'module for validation; only then buy the remaining three (plus the wearable\'s, '
        'pending the same check).</div>'
    )
    foot = ("Pad map from the user's photograph, 2026-11-02. Photo evidence over listing "
            "claims: the listing omitted the charge current, the output rating and the "
            "efficiency. The trimpot sets the boost output, 4.2-28 V.")
    return p, notes, foot
