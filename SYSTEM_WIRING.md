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

**This diagram deliberately does not name charger terminals**: TP4056 boards vary, and `BAT`, `OUT`, and protection pins are not universally interchangeable. A common charger/protection module is not necessarily a load-sharing circuit. Choosing terminal-by-terminal wiring without a specific module, current rating and charging-use requirement could cause incorrect charging, backfeeding, resets or fire.

For each of the three nodes and the hub, the BOM proposes a protected 1-cell battery and a 5 V boost if the selected board uses its 5 V input. The wearable's suitable voltage/converter remains undecided. A lithium cell can be **4.2 V fully charged**, so do not connect it to a 3.3 V rail or GPIO; do not apply 5 V to 3V3. The converter's output must remain within the board input specifications under measured peak loads and low cell voltage. A 100 µF bulk capacitor is a **candidate**, not an unconditional connection: confirm location, voltage rating and stability requirements in the actual converter datasheet, then connect + to the intended rail and − to local GND only if appropriate. Do not connect bench USB and a battery supply simultaneously without a designed, verified power path preventing backfeed.

### 3.3 Node battery voltage measurement — proposed

Only after confirming the selected C3 ADC pin, its voltage/attenuation limits and firmware:

```text
 battery positive (cell side) ── 100 kΩ ──┬── selected ADC pin
                                          ├── 100 kΩ ── GND
                                          └── 100 nF ── GND
```

At 4.2 V cell voltage the nominal ADC voltage is 2.1 V. Account for component tolerances, absolute/operating limits and calibration. The divider continuously draws current; consider a switched design. **No GPIO is assigned here:** GPIO4–6 are occupied by the microphone, and strapping/USB pins require care. Battery measurement and low-battery reporting are not implemented in the current node firmware.

### 3.4 Node status LEDs — proposed

For each LED, a common active-high arrangement is `selected GPIO → 330 Ω → LED anode; LED cathode → GND`, but **do not solder to a specific pin yet**. Select two free GPIOs after checking the particular board's boot-strapping, USB and other functions and implement the corresponding firmware. The old PDF's GPIO4 red LED conflicts with SCK; its GPIO9 blue LED uses a strapping pin and must not be copied without a boot-state analysis. Verify LED current and resistor value for the selected parts.

### 3.5 Wearable battery and haptics

The planned DRV2605L motor output and I²C connections are as in section 2.3, subject to selection of compatible actual boards and motor. Its battery, charger, protection, load-sharing, conversion and switch must be designed as one circuit. The proposed 500 mAh is only a capacity idea: measure current and choose the charge rate per the actual cell. Never assume a 1 A TP4056 default is suitable. The IRLML2502 and its gate resistors/diode belong to the alternative MOSFET drive and are **not wired into the DRV2605L path**.

## 4. Checks before power-up

1. With power disconnected, check continuity and make sure no 3.3 V or 5 V rail is shorted to ground. Inspect vero-board copper tracks, intentional cuts and solder bridges.
2. Confirm the exact module labels, voltage ratings, polarity, cell protection and regulator settings. Check converter output with a meter **before** connecting its load.
3. For initial testing use a current-limited bench supply where possible. Test one assembly at a time; avoid unattended charging.
4. Test the known USB node-to-hub setup first. The wearable and additional nodes require their own implementation and verification.
5. Before using battery and USB together, verify the actual charger/load-sharing and backfeed behaviour. Secure cells against puncture/shorts and use appropriate enclosures.

## 5. Information needed to finish exact battery wiring

Obtain the manufacturer/model and clear front/back labels or schematics of the five selected charger/power-path modules, converters, cells and board variants; the exact OLED, DRV2605L breakout and motor; and whether operation while charging is required. Measure peak hub and node currents. Then select the battery and charge currents, free GPIOs and pull-ups, produce a module-specific point-to-point schematic and validate before assembly. Until then, this guide cannot honestly claim exact full-system battery wiring.

**Evidence:** `firmware/node/node_crynet/node_crynet.ino` (GPIO4/5/6); `firmware/hub_infer/components/hub_display/hub_display.c` (TFT pins); `SYSTEM_UPDATE.md` (working display wiring and hardware tests); `HARDWARE_COMPONENTS.md` (proposed BOM).
