"""Page 4 - caregiver wearable: the complete unit on one page.

Power chain, OLED, LEDs, battery sense and the BC547 haptic drive all
live here.  The haptic drive used to be a separate page; the user wants
one wearable diagram they can follow with the parts in their hand.
"""

from diagram_lib import Page

W, H = 1000, 540


def build():
    p = Page(W, H, "4 / Caregiver wearable - complete wiring (x1)",
             "ESP32-C3 SuperMini + SSD1306 OLED + LX-LCBST + switch + battery-sense "
             "divider + 2 LEDs + BC547 haptic drive")

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
    p.label(398, 320, "GND", size=12.5, cls="pin", mono=True, owner=board)
    for name, y in (("3V3", 110), ("GPIO5", 145), ("GPIO6", 175),
                    ("GPIO1", 220), ("GPIO4", 250)):
        p.label(577, y, name, size=12.5, cls="pin", anchor="end", mono=True,
                owner=board)
    for name, x in (("GPIO3", 420), ("GPIO7", 470), ("3V3", 520)):
        p.label(x, 347, name, size=12.5, cls="pin", anchor="middle", mono=True,
                owner=board)

    # --------------------------------------------------------------- OLED --
    oled = p.box(690, 55, 180, 140, "SSD1306 OLED", cls="mod")
    for name, y in (("VCC", 110), ("SDA", 145), ("SCL", 175)):
        p.label(698, y, name, size=12.5, cls="pin", mono=True, owner=oled)
    p.label(852, 190, "GND", size=12.5, cls="pin", anchor="end", mono=True,
            owner=oled)

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
    # the board's own ground
    p.wire([(390, 320), (360, 320)], color="black")
    p.ground(360, 320, dir="left")

    # ------------------------------------------------- battery sense ------
    # B+ feeds the divider, the tap lands on GPIO3 (ADC)
    p.battery_sense(200, 229, 420, 355)

    # ------------------------------------------------------------- OLED ---
    p.wire([(585, 110), (690, 110)], color="red")
    p.label(600, 101, "3.3 V", size=11, cls="small", color="#c43e39")
    p.wire([(585, 145), (690, 145)], color="blue")
    p.wire([(585, 175), (690, 175)], color="green")
    p.wire([(780, 195), (780, 212)], color="black")
    p.ground(780, 212)

    # ------------------------------------------------------------ LEDs ---
    # BLUE LED on GPIO1 (BLE link), RED LED on GPIO4 (SOC)
    p.wire([(585, 220), (610, 220), (610, 240), (650, 240)], color="blue")
    p.part(650, 227, 72, 26, "1 kΩ")
    p.wire([(722, 240), (740, 240)], color="blue")
    p.part(740, 227, 70, 26, "BLUE LED")
    p.wire([(810, 240), (830, 240)], color="blue")
    p.ground(830, 240, dir="right")
    p.label(856, 244, "link", size=11, cls="small")

    p.wire([(585, 250), (600, 250), (600, 300), (650, 300)], color="orange")
    p.part(650, 287, 72, 26, "1 kΩ")
    p.wire([(722, 300), (740, 300)], color="orange")
    p.part(740, 287, 70, 26, "RED LED")
    p.wire([(810, 300), (830, 300)], color="orange")
    p.ground(830, 300, dir="right")
    p.label(856, 304, "SOC", size=11, cls="small")

    # =================================================== haptic drive ====
    # BC547 low-side switch: GPIO7 -> 2.2 k -> base, motor in the collector
    # leg, 1N5819 across the motor with the cathode up.

    # 3V3 rail to the motor's + terminal, through the 10 ohm stall cap
    p.wire([(520, 352), (520, 356), (660, 356)], color="red")
    p.part(660, 343, 60, 26, "10 Ω")
    p.wire([(720, 356), (932, 356)], color="red")
    p.dot(780, 356)

    # ------------------------------------------------------------- motor --
    mot = p.box(740, 368, 150, 72, "ERM coin motor", cls="mod",
                sub=["3 V, 85 mA"])
    w_tap = p.wire([(780, 356), (780, 368)], color="red")
    p.label(770, 373, "+", size=12.5, cls="pin", anchor="middle", mono=True,
            owner=mot, exempt_from=(w_tap,))
    p.label(848, 432, "-", size=12.5, cls="pin", anchor="middle", mono=True,
            owner=mot)

    # ---------------------------------------------------------- flyback ---
    # cathode up to the + net, anode down to the collector node
    p.vpart(920, 368, 24, 60, "1N5819", label_dx=6)
    p.wire([(932, 356), (932, 368)], color="red")
    p.label(950, 425, "cathode", size=10.5, cls="small")
    p.label(950, 440, "up", size=10.5, cls="small")

    # the motor's negative terminal and the flyback anode meet here
    p.wire([(860, 440), (860, 448)], color="black")
    p.dot(860, 448)
    p.wire([(860, 448), (932, 448)], color="black")
    p.wire([(932, 428), (932, 448)], color="black")

    # -------------------------------------------------------- transistor --
    bc = p.box(780, 455, 140, 62, None, cls="mod")
    p.label(792, 510, "BC547 NPN", size=15, cls="title", owner=bc)
    p.label(788, 475, "B", size=12.5, cls="pin", mono=True, owner=bc)
    p.label(912, 475, "E", size=12.5, cls="pin", anchor="end", mono=True,
            owner=bc)
    p.label(852, 453, "C", size=12.5, cls="pin", anchor="end", mono=True,
            owner=bc)
    # collector up to the motor's negative terminal
    p.wire([(860, 448), (860, 455)], color="black")

    # ------------------------------------------------------- base drive ---
    p.wire([(470, 352), (470, 475)], color="purple")
    p.wire([(470, 475), (630, 475)], color="purple")
    p.part(630, 462, 64, 26, "2.2 kΩ")
    p.wire([(694, 475), (780, 475)], color="purple")
    p.dot(720, 475)
    # base-emitter pulldown keeps the motor off while the C3 boots
    p.wire([(720, 475), (720, 503)], color="purple")
    p.vpart(708, 503, 24, 22, "100 kΩ", anchor="end", label_dx=-4)
    p.wire([(720, 525), (745, 525)], color="purple")
    p.ground(745, 525, dir="right")

    # emitter to ground
    p.wire([(920, 475), (950, 475)], color="black")
    p.ground(950, 475, dir="right")

    notes = (
        '<div class="warning">Divider confirmed: 220 k&#937; from B+ and 100 k&#937; to '
        'ground give 4.2 V &#215; 100/320 = 1.31 V at the ADC (the 100 nF filters it), '
        '13 uA of divider current; the node firmware already uses this ratio '
        '(reading &#215; 3.2). Motor: the 10 &#937; caps the stall current at '
        '3.3 V &#247; (R + 10 &#937;) - about 69 mA for a 37 &#937; coin ERM, inside '
        'the BC547\'s 100 mA; a lower-impedance motor needs 22 &#937; or a 2N2222A. '
        'Firmware gap: haptic_trigger() still blinks the LED - it must hold GPIO7 high '
        '~250 ms per cry alert.</div>'
    )
    foot = ("Every &#9169; symbol is the same net; wires join only where a dot is "
            "drawn. The BC547 emitter is the motor's ground, and the flyback sits "
            "across the motor with the cathode up.")
    return p, notes, foot
