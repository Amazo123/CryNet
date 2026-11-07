"""Page 1 - system overview: the power chain and the wireless links."""

from diagram_lib import Page

W, H = 1000, 430


def build():
    p = Page(W, H, "1 / CryNet system - power chain and links",
             "Every unit has its own battery and its own ground. No wire ever joins two units.")

    # ------------------------------------------------------- power chain --
    p.box(30, 55, 165, 95, "Cell", cls="proposed",
          sub=["3.7 V nominal, 4.2 V full", "18650 on node + hub,",
               "Li-Po pouch on wearable"])
    p.box(255, 55, 190, 95, "LX-LCBST-TC-001", cls="proposed",
          sub=["charger + protection + boost", "USB-C = charging input"])
    p.box(505, 55, 150, 95, "SPST switch", cls="proposed",
          sub=[">= 1 A, in the VO+ line"])
    p.box(715, 55, 255, 95, "ESP32 board + its loads", cls="board",
          sub=["5 V pin after the switch", "GND from VO-"])

    p.wire([(195, 102), (255, 102)], color="red")
    p.label(200, 78, "B+ / B-", size=11, cls="small", color="#c43e39")
    p.wire([(445, 102), (505, 102)], color="red")
    p.label(450, 78, "VO+ / VO-", size=11, cls="small", color="#c43e39")
    p.wire([(655, 102), (715, 102)], color="red")
    p.label(660, 78, "5 V", size=11, cls="small", color="#c43e39")

    p.label(30, 182, "One chain in all four units - only the loads differ:", size=13,
            cls="note")

    # -------------------------------------------------------- the units ---
    p.box(30, 205, 250, 95, "Cot node  x3", cls="mod",
          sub=["ESP32-C3 + INMP441 mic", "no battery sense, no LEDs"])
    p.box(375, 205, 250, 95, "Main hub  x1", cls="mod",
          sub=["ESP32-S3 + 2.8\" ILI9341", "no battery sense, no LEDs"])
    p.box(720, 205, 250, 95, "Caregiver wearable  x1", cls="mod",
          sub=["ESP32-C3 + SSD1306 OLED", "haptic motor; no LEDs, no sense"])

    p.wire([(280, 252), (375, 252)], color="teal", width=2, dash="7 5")
    p.label(292, 242, "ESP-NOW", size=11, cls="small", color="#15979c")
    p.wire([(625, 252), (720, 252)], color="teal", width=2, dash="7 5")
    p.label(640, 242, "BLE", size=11, cls="small", color="#15979c")

    p.label(30, 330, "Rules every unit follows:", size=13, cls="note")
    p.label(30, 352, "1 - Switch OFF before charging. The cell still charges on B+/B-.",
            size=12, cls="note")
    p.label(30, 371, "2 - Set the boost trimpot to 5.1 V with a meter before any board.",
            size=12, cls="note")
    p.label(30, 390, "3 - Never power a board from USB and the boost at the same time.",
            size=12, cls="note")
    p.label(30, 413, "Dashed teal = wireless link, no wire.  Solid = a real conductor.",
            size=11, cls="small")

    notes = (
        '<div class="warning">Proposed, bench-validation pending: the whole battery chain, '
        'the wearables and the LEDs. The node and hub signal wiring is the verified part. '
        '<b>No unit has a battery sense or a status LED (D-83)</b> - the node\'s divider '
        'and its GPIO10 blue link LED, the node\'s GPIO7 amber SOC LED, the hub\'s GPIO1 '
        'divider, the hub\'s GPIO2 BLE LED and the hub\'s GPIO17 SOC LED have all been '
        'removed. The hub\'s panel is the only display in the system, so nothing anywhere '
        'will warn the caregiver that a cell is nearly flat.</div>'
        '<div class="ok"><b>Cells (D-81):</b> an 18650 (3.7 V, 4.2 V full, 3000 mAh) on each '
        'node and the hub, because a node sits on a cot frame within a baby&#39;s reach and '
        'needs a cell that cannot be punctured; a 1000 mAh Li-Po pouch on the wearable, '
        'because an 18650 is 18 x 65 mm and 48 g and cannot go on a wrist. '
        '<b>Never LiFePO4</b> - the module charges to 4.2 V and an LFP cell tops out at '
        '3.65 V. The module&#39;s ~1 A charger must come down to ~400-500 mA for the '
        'wearable&#39;s pouch (1 C is too high for it).</div>'
        '<div class="warning"><b>Runtime (D-82):</b> the chain boosts to 5.1 V and the '
        'board drops that to 3.3 V through a <i>linear</i> regulator, which passes current '
        'rather than power - so the cell supplies roughly 1.8x the 3.3 V load current. '
        'That projects to about six hours for the wearable on a 1000 mAh pouch. These are '
        'projections, not measurements. Feeding the 3V3 pin from a 3.3 V buck-boost would '
        'roughly double it - a change to the power chain, deferred to the bench.</div>'
    )
    foot = ("No signal wire exists between the nodes and the hub - the link is wireless. "
            "Each unit is electrically independent; never join their batteries or grounds. "
            "Read with SYSTEM_WIRING.md sections 5 and 6.")
    return p, notes, foot
