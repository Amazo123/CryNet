"""Page 4 - caregiver wearable: power, OLED, LEDs, battery sense.

The haptic drive itself (BC547 low-side switch) is drawn in full on the
next page, so this page stays readable.
"""

from diagram_lib import Page

W, H = 1000, 480


def build():
    p = Page(W, H, "4 / Caregiver wearable - complete wiring (x1)",
             "ESP32-C3 SuperMini + SSD1306 OLED + LX-LCBST + switch + battery-sense divider + 2 LEDs")

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
    board = p.box(390, 45, 195, 285, "ESP32-C3 wearable", cls="board",
                  sub=["GPIO0/2/8/9 strapping: unused"])
    p.label(398, 124, "5V", size=12.5, cls="pin", mono=True, owner=board)
    for name, y in (("3V3", 105), ("GPIO5", 140), ("GPIO6", 170),
                    ("GPIO1", 215), ("GPIO4", 245)):
        p.label(577, y + 5, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=board)
    for name, x in (("GPIO3", 420), ("GPIO7", 470), ("3V3", 520), ("GND", 555)):
        p.label(x, 347, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=board)

    # --------------------------------------------------------------- OLED --
    oled = p.box(690, 55, 180, 140, "SSD1306 OLED", cls="mod")
    for name, y in (("VCC", 105), ("SDA", 140), ("SCL", 170)):
        p.label(698, y + 5, name, size=12.5, cls="pin", mono=True, owner=oled)

    # ------------------------------------------------------- power chain --
    p.wire([(200, 120), (245, 120)], color="red")
    p.label(204, 133, "5.1 V", size=11, cls="small", color="#c43e39")
    p.wire([(320, 120), (390, 120)], color="red")
    p.label(330, 111, "5 V", size=11, cls="small", color="#c43e39")
    p.wire([(200, 165), (225, 165)], color="black")
    p.ground(225, 165, dir="right")
    # B- goes to ground, B+ feeds the divider - same pad order as the
    # node and hub pages (see page 6 for the physical pad map)
    p.wire([(200, 270), (225, 270)], color="black")
    p.ground(225, 270, dir="right")

    # ------------------------------------------------- battery sense ------
    p.battery_sense(200, 225, 420, 355)

    # -------------------------------------------------------------- OLED --
    p.wire([(585, 105), (690, 105)], color="red")
    p.label(600, 96, "3.3 V", size=11, cls="small", color="#c43e39")
    p.wire([(585, 140), (690, 140)], color="blue")
    p.wire([(585, 170), (690, 170)], color="green")
    p.wire([(780, 195), (780, 212)], color="black")
    p.ground(780, 212)

    # ------------------------------------------------------------ LEDs ---
    p.wire([(585, 215), (660, 215), (660, 395), (700, 395)], color="blue")
    p.part(700, 382, 72, 26, "1 kΩ")
    p.wire([(772, 395), (790, 395)], color="blue")
    p.part(790, 382, 70, 26, "BLUE LED")
    p.wire([(860, 395), (880, 395)], color="blue")
    p.ground(880, 395, dir="right")
    p.label(906, 399, "link", size=11, cls="small")

    p.wire([(585, 245), (630, 245), (630, 440), (700, 440)], color="orange")
    p.part(700, 427, 72, 26, "1 kΩ")
    p.wire([(772, 440), (790, 440)], color="orange")
    p.part(790, 427, 70, 26, "RED LED")
    p.wire([(860, 440), (880, 440)], color="orange")
    p.ground(880, 440, dir="right")
    p.label(906, 444, "SOC", size=11, cls="small")

    # ------------------------------------------- off to the haptic page --
    # the three stubs drop from the board's GPIO7 / 3V3 / GND pins
    hap = p.box(440, 395, 160, 62, "haptic drive", cls="mod")
    p.label(452, 436, "see page 5", size=11, cls="small", owner=hap)
    p.wire([(470, 352), (470, 395)], color="purple")
    p.wire([(520, 352), (520, 395)], color="red")
    p.wire([(555, 352), (555, 395)], color="black")

    notes = (
        '<div class="warning">Proposed, nothing built: the OLED + haptic path. The OLED '
        'runs from the SuperMini 3V3 pin, never from 5 V - I2C pull-ups ride on VCC and '
        '5 V there would push 5 V levels into the C3 GPIOs. The motor is on its own '
        'switch, drawn in full on page 5 - it is not powered from the 3V3 pin here. '
        'Divider on GPIO3; BLUE LED GPIO1 (BLE link), RED LED GPIO4 (SOC).</div>'
    )
    foot = ("Every &#9169; symbol is the same net: the module's VO-. Wires join only where "
            "a dot is drawn. Pin names, not header positions. The haptic drive continues "
            "on page 5.")
    return p, notes, foot
