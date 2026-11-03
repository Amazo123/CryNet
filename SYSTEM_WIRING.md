# CryNet — USB Test and Complete-System Wiring Guide

**Revision:** 2 November 2026. Read alongside `HARDWARE_COMPONENTS.md`.

> **Important:** The node + hub signal wiring in section 2 reflects the working prototype. The wearable, battery power, node LEDs and battery sensing are **not implemented or verified**. Their exact part-to-part power wiring and GPIO choices cannot safely be finalised until the actual board and charger modules, cell and motor are selected. Section 3 is a proposed connection architecture, not permission to wire an unspecified lithium charger. This academic prototype is not a certified infant-monitoring device and must not replace supervision. Keep cables, cells, modules and small parts out of reach of the infant.

## 1. System picture

```text
  Cot 1: INMP441 → C3  ── ESP-NOW ──┐
  Cot 2: INMP441 → C3  ── ESP-NOW ──┼→ ESP32-S3 hub → 2.8-inch TFT
  Cot 3: INMP441 → C3  ── ESP-NOW ──┘        │
                                             └── BLE → phone (tested)
                                                  or → C3 wearable (planned)
                                                           ├→ SSD1306 OLED
                                                           └→ DRV2605L → motor
```

No audio or signal wires connect the cot nodes to the hub: the link is wireless. Each assembly has its own local power and ground. The node, hub and wearable do not need grounds connected to each other.

## 2. Wiring A — USB-powered bench test

**Before wiring:** disconnect power; identify actual board/module pin labels; use a multimeter to check for shorts and verify the display module voltage. These are board pin labels, not physical header positions. Do not assume every breakout uses the same pin order.

### 2.1 Cot node: ESP32-C3 + INMP441

Repeat the same connections for each node. The current real-board test used one node; three-node simultaneous operation is not yet verified.

| From | To | Note |
|---|---|---|
| C3 **3V3** | INMP441 **VDD / 3V3** | 3.3 V only; not USB 5 V. |
| C3 **GND** | INMP441 **GND** | Common local ground. |
| C3 **GND** | INMP441 **L/R** | Select left I²S channel. |
| C3 **GPIO4** | INMP441 **SCK** | I²S bit clock. |
| C3 **GPIO5** | INMP441 **WS** | I²S word select. |
| C3 **GPIO6** | INMP441 **SD** | Microphone data to C3. |
| Regulated USB supply or computer | C3 **USB connector** | Use a compatible data cable for flashing/serial. |
| Optional 100 nF capacitor | Between mic **VDD and GND** | As close as practical to microphone; check existing breakout decoupling. Ceramic is non-polar. |

```text
 C3 3V3 ───────────── VDD   INMP441
 C3 GND ─────┬─────── GND
             └─────── L/R
 C3 GPIO4 ─────────── SCK
 C3 GPIO5 ─────────── WS
 C3 GPIO6 ─────────── SD
 USB source ───────── C3 USB socket
```

The old PDF's GPIO5/6/7 microphone assignment does **not** match the current firmware. C3 GPIO4 is already used by SCK and must not also be connected to the old red status LED.

### 2.2 Hub: ESP32-S3 + 2.8-inch ILI9341

The project log records the following signal and 3.3 V connections on the existing display. Match the actual module's labels and confirm its supply and backlight circuit before copying it to a different TFT.

| From S3 | To display | Note |
|---|---|---|
| **3V3** | **VCC** | Recorded working connection for the existing module; do not assume another module has identical power requirements. |
| **GND** | **GND** | Local common ground. |
| **GPIO10** | **CS** | Chip select. |
| **GPIO11** | **MOSI / SDI** | SPI data to TFT. |
| **GPIO12** | **SCK / CLK** | SPI clock. |
| **GPIO13** | **DC / D-C** | Data/command. |
| **GPIO14** | **RST / RESET** | Display reset. |
| **GPIO4** | **BL / LED control** | Recorded on the existing board. Check the module's backlight drive current and circuit; do not drive an unknown bare LED backlight from a GPIO. |
| Not connected | **MISO / SDO** | The current driver does not read TFT data. |
| Regulated USB supply or computer | S3 **USB connector** | Match the actual connector used for programming. |

No external 100 Ω backlight resistor should be added blindly; use the specific module's circuit. Touchscreen and SD-card pins, if present, are not used by the current display firmware. The S3's BOOT button is used by the existing UI; it is already on the development board.

### 2.3 USB wearable bench wiring — proposed, not yet built

The firmware and exact GPIO assignments do not yet exist. The following is a **connection list**, not a tested pin map. Select free C3 I²C pins after checking the actual board, USB and boot-strapping constraints; use the same two bus lines for both modules.

| From | To | Condition |
|---|---|---|
| C3 **GND** | OLED **GND** and DRV2605L **GND** | Common local ground. |
| C3 **3V3** | OLED **VCC** | Only if the specific OLED breakout accepts 3.3 V. |
| Appropriate regulated supply | DRV2605L breakout **VIN/VDD** | Follow the actual breakout's voltage requirements; do not assume its VIN and logic pins are identical to the IC pins. |
| Selected C3 I²C SDA | OLED **SDA** and driver **SDA** | Bus pull-ups must go to a safe 3.3 V logic rail. Check existing pull-ups before adding any. |
| Selected C3 I²C SCL | OLED **SCL** and driver **SCL** | Same. Verify address compatibility. |
| Driver **OUT+ / OUT−** | Compatible motor's two terminals | Use the specific breakout's labels and motor requirements. Do not connect either motor lead to 3V3 or ground as in the old MOSFET circuit. |
| USB source | C3 USB socket | Supply capability and driver power arrangement must be checked. |

Use the selected breakout's documentation for EN, I/O supply, power, pull-ups and any other control pins; these vary by board. DRV2605L uses an H-bridge, unlike the old low-side MOSFET design. No separate MOSFET or old motor flyback-diode wiring is used for this driver. See [TI DRV2605L datasheet](https://www.ti.com/lit/ds/symlink/drv2605l.pdf). Test firmware is needed before this wearable can receive BLE alerts.

## 3. Wiring B — proposed battery-powered complete system

### 3.1 Connections that remain the same

For each of the three nodes, retain **all six microphone connections** in section 2.1. For the hub, retain the TFT signal and ground connections in section 2.2. For the wearable, use only a finalised and tested version of section 2.3. Only the **power source** and proposed indicators/battery sensing change; never join all five batteries together.

### 3.2 Power architecture for each separate unit

```text
 USB charging input
        │
        ▼
 [charger + properly designed power-path/load sharing] ←→ [protected 1-cell battery]
        │ regulated/selected system output, as the module specifies
        ▼
 [suitable regulated converter, if needed] → [power switch as designed]
        │                                      │
        ├── appropriate board power input      └── local loads, if designed
        └── local ground / return
```

**Concrete pad names, from the photographed board (§6):** the charging input is the module's **USB-C socket**; the battery lands on **B+/B−** (printed 电池); the load chain starts at **VO+ / VO−** (printed 输出). IN+/IN− (printed 输入) stay unconnected.

For each of the three nodes and the hub, the BOM proposes a protected 1-cell battery and a 5 V boost if the selected board uses its 5 V input. The wearable's suitable voltage/converter remains undecided. A lithium cell can be **4.2 V fully charged**, so do not connect it to a 3.3 V rail or GPIO; do not apply 5 V to 3V3. The converter's output must remain within the board input specifications under measured peak loads and low cell voltage. A 100 µF bulk capacitor is a **candidate**, not an unconditional connection: confirm location, voltage rating and stability requirements in the actual converter datasheet, then connect + to the intended rail and − to local GND only if appropriate. Do not connect bench USB and a battery supply simultaneously without a designed, verified power path preventing backfeed.

### 3.3 Node battery voltage measurement and LEDs

Superseded by the concrete plan in §5.1: B+ → 220 kΩ → sense node; sense node → 100 kΩ ∥ 100 nF → B−; sense node → GPIO3 (ADC1_CH3). At 4.2 V the ADC sees ≈ 1.31 V and the divider draws ≈ 13 µA continuously. The status LEDs land on GPIO10 (link, ACK-driven) and GPIO7 (SOC) through 1 kΩ resistors. Firmware for the divider, the LED patterns and the heartbeat ACK is **not yet implemented**; all of it goes to a branch first.

### 3.4 Wearable battery and haptics

The wearable's power follows the same LX-LCBST pattern as the nodes (§5.3): VO+ → switch → SuperMini 5V pin; OLED and DRV2605L VIN from the SuperMini's 3V3 output so the I²C bus stays at 3.3 V; the motor on the DRV2605L's OUT+/OUT−. The proposed 1,000 mAh cell only buys runtime if the module's measured charge current suits it — confirm during bench validation. The IRLML2502 and its gate resistors/diode belong to the alternative MOSFET drive and are **not wired into the DRV2605L path**.

## 4. Checks before power-up

1. With power disconnected, check continuity and make sure no 3.3 V or 5 V rail is shorted to ground. Inspect vero-board copper tracks, intentional cuts and solder bridges.
2. Confirm the exact module labels, voltage ratings, polarity, cell protection and regulator settings. Check converter output with a meter **before** connecting its load.
3. For initial testing use a current-limited bench supply where possible. Test one assembly at a time; avoid unattended charging.
4. Test the known USB node-to-hub setup first. The wearable and additional nodes require their own implementation and verification.
5. Before using battery and USB together, verify the actual charger/load-sharing and backfeed behaviour. Secure cells against puncture/shorts and use appropriate enclosures.

## 5. Proposed safe GPIO and component plan

This is the proposed design for the next firmware/hardware branch. It deliberately avoids the documented boot-strapping pins and the pins already used by the microphone, TFT or native USB. It is a **pin plan**, not yet flashed or measured.

### 5.1 Cot node — three identical units

| Function | GPIO / connection | Components |
|---|---|---|
| I²S BCLK | GPIO4 | Existing INMP441 SCK |
| I²S WS | GPIO5 | Existing INMP441 WS |
| I²S data | GPIO6 | Existing INMP441 SD |
| Battery ADC | **GPIO3 / ADC1_CH3** | Divider across the module's battery pads: **B+ → 220 kΩ → sense node; sense node → 100 kΩ → B−; sense node → 100 nF → B−**. B+/B− are the pads printed 电池 (battery) on the board photo. |
| Connection LED | **GPIO10**, active high | GPIO10 → 1 kΩ → blue LED anode; LED cathode → GND. 1 kΩ keeps LED current modest and reduces radio/power impact. |
| SOC LED | **GPIO7**, active high | GPIO7 → 1 kΩ → red/amber LED anode; LED cathode → GND. |
| Power switch | **VO+ → switch → C3 5V pin** | SPST switch rated ≥1 A. VO+ / VO− are the pads printed 输出 (output). B+/B− stay connected for charging while the node is off. Do not switch the battery side. |

The 220 kΩ / 100 kΩ divider reads the battery directly at B+/B− (≈ 13 µA continuous drain, ≈ 13 µA injection into the unpowered GPIO's protection diode when the unit is switched off — negligible next to a 2,000 mAh cell, and accepted deliberately; if bench testing ever shows odd behaviour with the unit off, an isolated switched-sense design replaces it). At 4.2 V cell voltage the ADC sees about 1.31 V; divider current is about 13 µA. The ADC capacitor makes the reading less sensitive to boost/radio pulses. The firmware must average samples while the radio is quiet, calibrate the ADC, and use hysteresis. This gives an estimate and low-battery warning—not an accurate fuel-gauge percentage.

The first firmware thresholds should be conservative and calibrated with the actual cell:

- normal: estimated cell voltage above approximately 3.70 V,
- low: approximately 3.55–3.70 V,
- critical: below approximately 3.45–3.55 V under a rested/light-load sample,
- shut down / charge prompt: at the project-selected cutoff with hysteresis.

Do not convert loaded voltage directly to a precise percentage. Report `battery estimate` and `charge soon`, and only prompt to switch off after repeated low readings. Never intentionally drive the cell to the protection cutoff.

The connection LED is **not** driven from a local transmit-success flag. It is on only while the node has received a valid hub heartbeat/ACK within a timeout. The planned protocol change is:

```text
node → hub: HEARTBEAT(node_id, counter, CRC)
hub → node: HEARTBEAT_ACK(node_id, counter, CRC)
node: connection_ok = matching hub ACK received within the last 3 seconds
```

The node should send the heartbeat to the hub, and the hub should return the matching ACK to that node. The node turns GPIO10 on only after receiving a fresh matching ACK within a timeout, blinks slowly when powered but no recent ACK exists, and turns it off before deep sleep/shutdown. The hub must also track the last heartbeat/telemetry time; an ESP-NOW send callback alone is not application delivery confirmation.

### 5.2 Hub — one unit

The current TFT assignments remain fixed: GPIO10 CS, GPIO11 MOSI, GPIO12 SCK, GPIO13 DC, GPIO14 RST and GPIO4 backlight. Proposed additions avoid those pins and the S3 strapping pins:

| Function | GPIO / connection | Components |
|---|---|---|
| Battery ADC | **GPIO1 / ADC1_CH0** | Proposed 220 kΩ / 100 kΩ divider and 100 nF filter across verified protected battery rails; ADC isolation when switched off and actual module ground topology require design. |
| Connection / BLE status LED | **GPIO2**, active high | GPIO2 → 1 kΩ → blue LED anode; cathode → GND. GPIO2 is a **normal GPIO on the ESP32-S3** (S3 strapping pins are GPIO0/3/45/46 — GPIO2's strap role is on the older ESP32 and the C3, not here). Firmware means "at least one caregiver client connected/subscribed," not merely BLE initialized. |
| SOC LED | **GPIO17**, active high | GPIO17 → 1 kΩ → amber/red LED anode; cathode → GND. GPIO17 is chosen to avoid ESP32-S3 strapping GPIO3. |
| Power switch | **VO+ → switch → S3 5V pin** | Battery remains on module B+/B− while the hub is off. Verify the DevKitC input and converter output under TFT/radio load; the hub's peak draw is the heaviest of the five units and is not yet measured. |

The hub TFT keeps its working assignments (GPIO4 backlight, GPIO10–14 signals). The battery ADC uses **GPIO1 = ADC1_CH0** — ADC1 is the converter that still works while Wi-Fi/BLE are active, which the hub runs constantly. The BLE-status LED lands on **GPIO2** (a normal pin on the S3) and the SOC LED on **GPIO17**. Avoid GPIO0/3/45/46 (S3 strapping) and GPIO35–37 (Octal PSRAM bus on the N16R8). GPIO3 in particular is a strap pin on the S3, which is why the hub's divider goes to GPIO1, not GPIO3 as on the C3 nodes.

### 5.3 Wearable — one unit

The wearable uses the same C3 board class, but the final board must be checked against its pin labels. Proposed non-strapping assignments are:

| Function | GPIO / connection | Components |
|---|---|---|
| Battery ADC | **GPIO3 / ADC1_CH3** | Battery-side divider 220 kΩ / 100 kΩ and 100 nF as above |
| OLED + DRV2605L SDA | **GPIO5** | Shared I²C SDA; add no external pull-up until both breakout boards are checked |
| OLED + DRV2605L SCL | **GPIO6** | Shared I²C SCL; pull-ups, if needed, to 3.3 V only |
| Connection/BLE LED | **GPIO1**, active high | GPIO1 → 1 kΩ → blue LED anode; cathode → GND. It means the wearable has a valid subscribed/connected BLE link, not merely that scanning started. |
| SOC LED | **GPIO4**, active high | GPIO4 → 1 kΩ → amber/red LED anode; cathode → GND. GPIO4 is a free non-strapping pin on the wearable (no microphone there). |
| Haptic output | DRV2605L OUT+ / OUT− | Motor connects across the driver's two output terminals; no IRLML2502 or 1N5819 in this path |
| Power switch | **VO+ → switch → C3 5V pin** | Same pattern as the node: disconnects the device, battery stays on B+/B− for charging. |

**Wearable power:** the wearable uses the same LX-LCBST pattern as the node: VO+ → switch → the SuperMini's 5V pin, VO− → GND. The OLED and the DRV2605L breakout are powered from the SuperMini's **3V3 output pin** — not from 5 V: the DRV2605L breakout's I²C pull-ups ride on its VIN rail, so 5 V there would push 5 V levels into non-5-V-tolerant C3 GPIOs. Check the board's 3.3 V regulator current budget before final assembly: C3 radio peaks (hundreds of mA) + OLED (~25 mA) + motor bursts (100–200 mA through the DRV2605L) all share it; if it sags or resets during vibration, the motor supply design gets revisited on a branch. ESP32-C3 strapping pins are GPIO0/2/8/9 — the plan above avoids all of them.

## 6. LX-LCBST-TC-001: decision and exact conditional wiring

**Pad map confirmed from the user's front-and-back photograph (2026-11-02):**

| Pad group | Printed label | Meaning (Chinese on silk) | Use |
|---|---|---|---|
| B+ / B− (front) / B+ / B− (back) | 电池 | **battery** | Li-Po cell connects here |
| VO+ / VO− (two pairs, back) | 输出 | **output** | Boost output — feeds the power switch |
| IN+ / IN− (back) | 输入 | **input** | Alternate charging input, 4.2–6.5 V; leave **unconnected** (charging runs from USB-C) |
| Front − / + pair (unlabelled) | — | ambiguous | Most likely a paralleled output tap; **verify with a meter before use** — compare it against VO+/VO− and B+/B− with the battery installed |
| Trimpot (front, beside the charger IC) | — | — | Sets the boost output, 4.2–28 V |

No **T** pad is visible on this board — the family listing's T-shorting instructions belong to other variants and **do not apply here**; do not short anything.

```text
Li-Po cell +  → B+   (pad printed 电池)
Li-Po cell −  → B−
USB-C socket  → charging input (nothing wired to IN+/IN−)
VO+ → power switch → ESP32 board 5V pin
VO− → ESP32 board GND pin
```

**Set the trimpot before any ESP32 is connected:** battery attached, meter on VO+/VO−, adjust to ≈ 5.1 V. The module can ship set anywhere in its 4.2–28 V range; connecting a board before setting it can destroy the board. Re-check after the first full charge cycle and occasionally thereafter.

Two characteristics remain unknown and must come from the bench validation: the **actual charge current** (the charger's program resistor is too small to read in the photo; if it programmes near 1 A, the wearable's 1,000 mAh cell needs its datasheet to permit that), and the boost converter's **quiescent drain while the unit is switched off** (the switch disconnects the load, not the converter — if off-state drain proves significant, the switch moves or the module changes). Note also that B− and VO− connect through the module's protection FET: in normal operation they are effectively the same ground, but at deep-discharge cutoff the battery disconnects and the ADC reading collapses — acceptable, since that *is* the dead-battery condition.

### Required one-board validation before buying four more

1. ~~Identify every terminal~~ — done from the photograph (§6 pad map). Remaining unknowns: actual charge current, boost quiescent drain, protection thresholds, the unlabelled front −/+ pair.
2. With no ESP32 attached, measure boost output range, no-load voltage, output under a dummy load and startup behaviour at full and partly discharged cell voltage.
3. Measure charging current and confirm termination at 4.2 V; verify whether the protection circuit disconnects at low voltage and short/overcurrent without deliberately abusing the cell.
4. Confirm that switch OFF disconnects the converter/load but leaves charging connected, and measure switch-off battery drain.
5. Run one node from it: compare reboot count, burst completion, radio range and microphone noise with the known USB baseline.
6. Only then decide whether it is suitable for the hub and whether a separate 3.3 V regulator is needed for the wearable.

## 7. SOC display and charge prompt

The hub's display should show an **estimated battery band** rather than falsely precise percentage. The proposed UI is `BAT ~80%`, `BAT LOW — CHARGE SOON`, and `BAT CRITICAL — SWITCH OFF AND CHARGE`. The wearable OLED may show the same. The node has only LEDs: normal SOC LED off, low slow blink, critical fast blink. Use voltage hysteresis and require repeated samples to prevent radio-current dips from causing a false prompt. SOC percentages need a calibration table for the selected Li-Po chemistry and actual cell; they must not be copied blindly from nominal voltage.

## 8. What is still required before this counts as verified

The LX-LCBST pad map is now known from the photograph; what remains is bench truth. Build **one** node power assembly exactly as in §5.1/§6, measure charge current, set the trimpot to 5.1 V, confirm switch-off behaviour and off-state drain, then run the working node firmware from it and compare with the USB baseline (reboots, bursts, mic noise). In parallel the user plans a **board swap**: ESP32-C3 Pro Mini boards for the three nodes and the existing SuperMini for the wearable — the firmware targets the chip, not the board, but each Pro Mini must prove native USB, 4 MB flash and the needed pins (GPIO3/4/5/6/7/10) before the swap counts; re-verify one node end to end on a branch. Firmware work (divider read, LED patterns, heartbeat ACK, SOC display) is all new and lives on a branch until verified. No merge into `main` without the user's decision.

**Evidence:** `firmware/node/node_crynet/node_crynet.ino` (GPIO4/5/6); `firmware/hub_infer/components/hub_display/hub_display.c` (TFT pins); `SYSTEM_UPDATE.md` (working display wiring and hardware tests); `HARDWARE_COMPONENTS.md` (proposed BOM).
