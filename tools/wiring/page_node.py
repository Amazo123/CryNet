"""Page 2 - cot node complete wiring."""

from diagram_lib import Page

W, H = 1000, 480


def build():
    p = Page(W, H, "2 / Cot node - complete wiring (one per node, x3)",
             "ESP32-C3 SuperMini + INMP441 + LX-LCBST + switch + battery-sense divider + 2 LEDs")

    # ---------------------------------------------------------- LX-LCBST --
    mod = p.box(25, 55, 175, 245, "LX-LCBST-TC-001", cls="proposed",
                sub=["charger + protection + boost", "USB-C = charge input",
                     "cell on B+ / B-"])
    for name, y in (("VO+", 124), ("VO-", 169), ("B+", 229), ("B-", 274)):
        p.label(192, y, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=mod)

    # ------------------------------------------------------------ switch --
    sw = p.box(245, 100, 75, 40, None, cls="proposed")
    p.label(255, 118, "SPST", size=12, cls="small", owner=sw)
    p.label(255, 133, ">= 1 A", size=10.5, cls="small", owner=sw)

    # ------------------------------------------------------------- board --
    board = p.box(390, 45, 195, 310, "ESP32-C3 node", cls="board",
                  sub=["GPIO0/2/8/9 strapping: unused"])
    p.label(398, 124, "5V", size=12.5, cls="pin", mono=True, owner=board)
    p.label(398, 324, "GND", size=12.5, cls="pin", mono=True, owner=board)
    for name, y in (("3V3", 105), ("GND", 145), ("GPIO4", 225), ("GPIO5", 265),
                    ("GPIO6", 305)):
        p.label(577, y + 5, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=board)
    for name, x in (("GPIO3", 420), ("GPIO7", 490), ("GPIO10", 545)):
        p.label(x, 347, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=board)

    # --------------------------------------------------------------- mic --
    mic = p.box(690, 55, 180, 270, "INMP441", cls="mod")
    for name, y in (("VDD", 105), ("GND", 145), ("L/R", 185), ("SCK", 225),
                    ("WS", 265), ("SD", 305)):
        p.label(698, y + 5, name, size=12.5, cls="pin", mono=True, owner=mic)

    # ------------------------------------------------------- power chain --
    p.wire([(200, 120), (245, 120)], color="red")
    p.label(204, 133, "5.1 V", size=11, cls="small", color="#c43e39")
    p.wire([(320, 120), (390, 120)], color="red")
    p.label(330, 111, "5 V", size=11, cls="small", color="#c43e39")
    # module VO- and B- are the same net, joined inside the module
    p.wire([(200, 165), (225, 165)], color="black")
    p.ground(225, 165, dir="right")
    p.wire([(200, 274), (225, 274)], color="black")
    p.ground(225, 274, dir="right")
    # board ground
    p.wire([(390, 320), (355, 320)], color="black")
    p.ground(355, 320, dir="left")

    # ------------------------------------------------- battery sense ------
    p.battery_sense(200, 225, 420, 355)

    # ------------------------------------------------------------- mic ---
    p.wire([(585, 105), (690, 105)], color="red")
    p.label(600, 96, "3.3 V", size=11, cls="small", color="#c43e39")
    p.wire([(585, 145), (690, 145)], color="black")
    p.wire([(690, 185), (655, 185)], color="black")
    p.ground(655, 185, dir="left")
    p.wire([(585, 225), (690, 225)], color="blue")
    p.wire([(585, 265), (690, 265)], color="green")
    p.wire([(585, 305), (690, 305)], color="orange")

    # ------------------------------------------------------------ LEDs ---
    p.wire([(545, 355), (545, 395), (650, 395)], color="blue")
    p.part(650, 382, 72, 26, "1 kΩ")
    p.wire([(722, 395), (740, 395)], color="blue")
    p.part(740, 382, 70, 26, "BLUE LED")
    p.wire([(810, 395), (830, 395)], color="blue")
    p.ground(830, 395, dir="right")
    p.label(856, 399, "link", size=11, cls="small")

    p.wire([(490, 355), (490, 440), (650, 440)], color="orange")
    p.part(650, 427, 72, 26, "1 kΩ")
    p.wire([(722, 440), (740, 440)], color="orange")
    p.part(740, 427, 70, 26, "RED LED")
    p.wire([(810, 440), (830, 440)], color="orange")
    p.ground(830, 440, dir="right")
    p.label(856, 444, "SOC", size=11, cls="small")

    notes = (
        '<div class="ok">Verified on the live system: mic wiring (3V3 / GND / L/R&#8594;GND, '
        'GPIO4 SCK, GPIO5 WS, GPIO6 SD) and the node firmware. GPIO1 stays spare.</div>'
        '<div class="warning">Proposed, needs bench validation: the whole battery chain, '
        'the divider and the LEDs. The divider reads about 13 uA. RED LED = SOC '
        '(off / slow / fast), BLUE LED = link (ACK-driven). Firmware for the divider and '
        'the LEDs does not exist yet - branch work.</div>'
    )
    foot = ("Every &#9169; symbol is the same net: the module's VO- (battery negative through "
            "the module's protection FET). Wires join only where a dot is drawn. Pin names, "
            "not header positions. Repeat identically for nodes 2 and 3.")
    return p, notes, foot
