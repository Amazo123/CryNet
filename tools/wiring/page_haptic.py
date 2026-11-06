"""Page 5 - the haptic drive: BC547 low-side switch for the coin motor.

This replaces the DRV2605L breakout the project docs used to plan.
The user owns BC547 parts, so the drive is a single NPN transistor plus
three resistors and one Schottky flyback diode.
"""

from diagram_lib import Page

W, H = 1000, 480


def build():
    p = Page(W, H, "5 / Wearable haptic drive - BC547 low-side switch",
             "One transistor, one coin motor, one flyback diode - no I2C driver module")

    # ------------------------------------------------------------- board --
    board = p.box(30, 250, 140, 110, "ESP32-C3", cls="board")

    # ------------------------------------------------------- motor + rail --
    mot = p.box(330, 90, 200, 100, "ERM coin motor", cls="mod",
                sub=["3 V - 85 mA running"])

    # 3V3 rail: board 3V3 pin up and over to the motor
    w_rail = p.wire([(60, 250), (60, 60), (300, 60)], color="red")
    p.label(56, 244, "3V3", size=12.5, cls="pin", mono=True, anchor="end",
            owner=board, exempt_from=(w_rail,))
    p.label(66, 66, "3V3", size=11, cls="small", mono=True, color="#c43e39",
            exempt_from=(w_rail,))
    p.part(300, 47, 70, 26, "10 Ω")
    w_in = p.wire([(370, 60), (430, 60), (430, 90)], color="red")
    p.label(426, 84, "+", size=13, cls="pin", mono=True, anchor="end",
            owner=mot, exempt_from=(w_in,))
    p.label(430, 186, "-", size=13, cls="pin", mono=True, owner=mot)
    # the same + net continues to the flyback diode
    p.wire([(430, 60), (620, 60), (620, 85)], color="red")

    # --------------------------------------------------------- flyback ----
    p.vpart(608, 85, 24, 80, "1N5819", anchor="end", label_dx=-8)
    p.label(636, 118, "cathode", size=10.5, cls="small")
    p.label(636, 133, "up", size=10.5, cls="small")
    p.wire([(620, 165), (620, 205), (430, 205)], color="black")
    p.dot(430, 205)

    # ------------------------------------------------------ transistor -----
    bc = p.box(300, 240, 140, 110, "BC547", cls="mod", sub=["NPN - low side"])
    p.label(308, 344, "E", size=12.5, cls="pin", mono=True, owner=bc)
    p.label(308, 302, "B", size=12.5, cls="pin", mono=True, owner=bc)

    # collector up to the motor's negative terminal
    w_c = p.wire([(370, 240), (370, 205), (430, 205)], color="black")
    p.dot(370, 205)
    p.label(370, 234, "C", size=12.5, cls="pin", mono=True, anchor="middle",
            owner=bc, exempt_from=(w_c,))
    p.wire([(430, 190), (430, 205)], color="black")

    # ------------------------------------------------------- base drive ---
    p.label(42, 300, "GPIO7", size=12.5, cls="pin", mono=True, owner=board)
    p.wire([(170, 300), (190, 300)], color="purple")
    p.part(190, 287, 76, 26, "2.2 kΩ")
    p.wire([(266, 300), (300, 300)], color="purple")
    p.dot(285, 300)
    # base-emitter pulldown keeps the motor off while the C3 boots
    p.wire([(285, 300), (285, 345)], color="purple")
    p.vpart(273, 345, 24, 60, "100 kΩ", label_dx=8)
    p.wire([(285, 405), (285, 420)], color="purple")
    p.ground(285, 420)

    # emitter to ground
    p.wire([(370, 350), (370, 380)], color="black")
    p.ground(370, 380)

    # ------------------------------------------------------ notes panel ---
    panel = p.box(680, 55, 295, 400, None, cls="panel")
    p.label(694, 78, "Why these values", size=13, cls="note", owner=panel)
    lines = [
        ("3 V coin ERM, typical:", 0),
        ("running 80-90 mA, start-up", 0),
        ("and stall 120-200 mA", 0),
        ("", 0),
        ("BC547 is rated 100 mA, so", 0),
        ("the 10 Ω in the motor's + lead", 0),
        ("caps the stall current near", 0),
        ("75 mA and keeps the transistor", 0),
        ("inside its rating.", 0),
        ("", 0),
        ("Base: 2.2 kΩ gives 1.2 mA of", 0),
        ("base current. A BC547A (hFE", 0),
        (">= 110) then drives 130 mA -", 0),
        ("saturated, no base-emitter leak.", 0),
        ("", 0),
        ("100 kΩ base-emitter holds the", 0),
        ("motor off while the C3 boots,", 0),
        ("when GPIO7 floats.", 0),
        ("", 0),
        ("1N5819 catches the back-EMF", 0),
        ("when the transistor switches off.", 0),
        ("", 0),
        ("Firmware drives GPIO7 high for", 0),
        ("about 250 ms per cry alert and", 0),
        ("low the rest of the time.", 0),
    ]
    y = 102
    for text, _ in lines:
        if text:
            p.label(694, y, text, size=11, cls="small", owner=panel)
        y += 14

    notes = (
        '<div class="warning">Check the motor before soldering: if its stall current '
        'exceeds 100 mA, the 10 Ω resistor must grow (22 Ω for a 200 mA motor) or the '
        'BC547 must be swapped for a 2N2222A. Measure the motor\'s stall current with a '
        'bench supply and a meter in series - do not guess.</div>'
        '<div class="ok">One buzz per cry: the alert notify characteristic carries the '
        'event id, and the sketch only fires haptic_trigger() when the alert type '
        'changes to a cry, so a louder cot joining a cry does not re-buzz.</div>'
    )
    foot = ("The BC547 emitter is the motor's ground: the motor's negative terminal goes "
            "to the collector, its positive terminal to 3V3. Keep the flyback diode "
            "across the motor itself, cathode to the + terminal.")
    return p, notes, foot
