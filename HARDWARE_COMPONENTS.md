# CryNet — Hardware Components and Purchasing Specification

**Revision:** 2 November 2026  
**System:** three cot nodes, one central hub and one caregiver wearable  
**Purpose:** replace the earlier `HARDWARE_COMPONENTS_DETAILED_SPECIFICATION.pdf` for planning and purchasing.

This is a **planning bill of materials for the complete system**, including a proposed independent rechargeable battery supply and battery/status indication for each unit. The battery circuits, indicators and wearable have not been designed and validated yet: component quantities below are planning quantities, **not a verified schematic or a final purchasing guarantee**. Modules are purchased assembled: their onboard microscopic components are not listed as separate purchases. Quantities are **total system quantities**, not necessarily quantities still to buy; subtract parts already owned. The user has confirmed a **2.8-inch**, not 2.4-inch, hub display.

> **Safety:** This is an academic prototype, not a certified medical device or a substitute for an adult caregiver. Detection, range, radio delivery, battery life and alarms have not been established to a safety-critical standard. Keep electronics, cords, batteries and small parts out of an infant's reach.

## 1. System overview and verification

Three ESP32-C3 microphone nodes transmit audio via ESP-NOW to an ESP32-S3 hub. The hub runs the cry classifier, shows status on an ILI9341 display and exposes a BLE alert service. A planned ESP32-C3 wearable will receive alerts and use an OLED and haptic motor.

- **Verified:** one real node, one hub, the display and a BLE phone client together; the cry classifier and radio burst transfer have run on the boards.
- **Not yet verified:** multiple nodes in the same room, the actual wearable, its haptics and its battery runtime. The final battery-powered versions have not been validated.
- **Not needed:** a separate PSRAM module; the hub board already has PSRAM. A colour-check photo is no longer required by the user.

## 2. Cot nodes — three identical units

| Item | Per node | System total | Specification and purchasing guidance |
|---|---:|---:|---|
| ESP32-C3 node board | 1 | **3** | Working prototype uses an ESP32-C3 SuperMini; planned production boards are the user's ESP32-C3 **Pro Mini** stock (verify native USB, 4 MB flash and the GPIO3/4/5/6/7/10 pins on the actual board). The radio is built in. |
| INMP441 digital I²S microphone breakout | 1 | **3** | Use a 3.3 V-compatible INMP441 breakout. Keep the acoustic opening unobstructed. |
| USB data/power cable | 1 | **3** | Match the board connector; data-capable cables support programming. Existing cables can be shared for programming if all three nodes are otherwise powered. |
| Regulated 5 V USB supply | 1 | **3** | One per simultaneously operating node, or an adequately rated multiport supply. Use a reputable supply with current headroom; verify connector and board power input. |
| Stripboard / vero board | As needed | As needed | Cut into three assemblies, with sufficient spacing and insulated underside. |
| Hook-up wire, headers and connectors | As needed | As needed | Suitable for power and I²S; mount the mic without covering its sound port. |
| Enclosure and mounting hardware | 1 set | **3 sets** | Insulated, with sound access, secure mounting and cable strain relief. |
| 100 nF ceramic capacitor, marked 104 | Optional | Up to **3** | Supplemental mic-supply decoupling close to VDD/GND if needed; check whether the breakout already includes it. Not an established fix for the observed radio/audio interference. |

**Current firmware microphone pins:** INMP441 SCK → GPIO4, WS → GPIO5, SD → GPIO6; L/R → ground for the tested left channel, and use the module's 3.3 V supply and ground. The old PDF's GPIO5/6/7 assignments do **not** match the current node firmware. Confirm the actual board labels before soldering.

### Proposed rechargeable power and indicators — per node

The original document's battery arrangement is restored as a **planning design**, not as working firmware or a validated wiring diagram. For the three nodes, multiply each per-node quantity by three. The 5 V output must be regulated and connected only to the board's appropriate 5 V/USB input; verify the actual board and peak load first.

| Individual item | Per node | All nodes | Selection / purpose |
|---|---:|---:|---|
| Protected rechargeable 1-cell Li-ion/Li-Po battery | 1 | **3** | 3.7 V nominal, 4.2 V full. Original target 2000 mAh each; select genuine cells with appropriate protection, discharge rating and connectors. Runtime not yet measured. |
| 1-cell charger module | 1 | **3** | TP4056-based module is a candidate; ensure suitable cell protection and **load sharing/power-path**, and set a charge current appropriate for the actual cell. A common TP4056 protection board alone does not guarantee safe simultaneous operation and charging. |
| 5 V boost converter | 1 | **3** | MT3608 module is a candidate; select a converter with adequate **continuous** output at the lowest cell voltage and transient headroom, not merely its advertised peak figure. Verify shutdown, efficiency and actual ripple. |
| On/off switch | 1 | **3** | Rated for the chosen power-path current; final placement depends on charger/load-sharing design. |
| 100 µF electrolytic capacitor | 1 | **3** | Initial bulk-capacitor allowance for the 5 V rail, voltage rating at least 10 V; respect polarity. Confirm value and placement with the selected converter. |
| 100 nF ceramic capacitor, marked 104 | 1 | **3** | Additional allowance for battery-voltage ADC filtering, separate from optional mic decoupling above. |
| 100 kΩ, 1% resistors | 2 | **6** | Proposed battery-voltage divider: two per node. With a 4.2 V fully charged cell, nominal divided voltage is 2.1 V. Confirm ADC pin, ESP32-C3 attenuation/calibration and tolerances; consider divider power drain or switched sensing. |
| Red LED | 1 | **3** | Proposed battery indicator; current firmware does not implement it. |
| Blue LED | 1 | **3** | Proposed link indicator; current firmware does not implement it. |
| 330 Ω, ¼ W resistor | 2 | **6** | One per indicator LED as an initial 3.3 V design value. Verify actual LED current and selected GPIOs. |
| Battery connector pair | 1 | **3 pairs** | Match cell and charger; check polarity physically, not by colour alone. |

**Pin and firmware warning:** the old PDF assigns the red LED to GPIO4, which is now used by the microphone. GPIO9 is a boot-strapping pin, so do not assume its old LED circuit is safe. New available pins and boot behaviour must be checked, and battery readings, low-battery handling and LED behaviour must be implemented and tested. The complete charger/power-path design must be selected before ordering or connecting these parts.

## 3. Central hub — one unit

| Item | Total | Specification and purchasing guidance |
|---|---:|---|
| ESP32-S3-DevKitC-1 with PSRAM | **1** | Existing hub, reported as N16R8: 16 MB flash and 8 MB PSRAM. ESP-NOW, BLE and model inference use the same board. Confirm markings when replacing it. |
| **2.8-inch ILI9341 SPI colour TFT** | **1** | Existing user-confirmed size; 240 × 320 pixels. Match the actual module and its power/backlight requirements rather than assuming all 2.8-inch boards are wired alike. |
| USB data/power cable | **1** | Match the actual hub USB connector; data capability is useful for flashing and logs. |
| Regulated 5 V USB power supply | **1** | Stable, suitably rated supply for the hub and display; assess actual current and the module's power arrangement before final assembly. |
| Stripboard, wire, headers and connectors | As needed | For secure signal and supply wiring. |
| Insulated enclosure and mounting hardware | **1 set** | Provide a TFT opening, secure fixings and cable strain relief. |

**Firmware signal assignments:** TFT MOSI → GPIO11, SCK → GPIO12, CS → GPIO10, DC → GPIO13, reset → GPIO14 and backlight control → GPIO4. Verify the particular display module's power and backlight circuit before connecting it; GPIO4 is a control signal, not an instruction to power an unknown backlight directly.

**Display backlight:** module circuits differ. Do not automatically add the old document's 100 Ω series resistor or apply 5 V to an unidentified TFT pin. Verify the specific board's schematic/markings and the actual tested backlight wiring before permanent assembly.

### Proposed rechargeable hub power — planning quantities

| Individual item | Qty | Selection / purpose |
|---|---:|---|
| Protected single-cell Li-ion/Li-Po battery | **1** | Original proposal: about 3000 mAh; capacity, discharge rating, protection and physical format require selection based on measured hub/display current. Use a holder if the selected cell requires one. |
| Single-cell charger with suitable protection and power-path/load sharing | **1** | Select for the actual battery and simultaneous-load requirements. A basic TP4056 is not automatically a load-sharing solution. |
| Regulated 5 V boost converter | **1** | MT3608 is a candidate only if verified for the actual continuous and peak hub/display loads over the full battery range. |
| Power switch | **1** | Rated and placed for the final power path. |
| 100 µF electrolytic capacitor | **1** | Initial 5 V rail bulk-capacitor allowance; ≥10 V rating, observe polarity, verify against converter requirements. |
| 100 nF ceramic capacitor, marked 104 | **1** | Supplemental local decoupling allowance; confirm existing board components and placement. |
| Battery connector pair | **1 pair** | Match the cell and charger; verify polarity. |

These are a proposed design, not verified hub wiring. A portable power system needs measurement, a reviewed schematic and test before permanent assembly. The existing ESP32-S3 board already contains its own supporting circuitry; do not automatically add a separate TFT backlight resistor.

## 4. Caregiver wearable — one planned unit

The hub's BLE service has been exercised with a phone, but **the wearable itself and its firmware have not yet been implemented or tested**. The following is the recommended architecture, not a claim of a completed circuit.

| Item | Total | Status / selection |
|---|---:|---|
| ESP32-C3 development board | **1** | Planned BLE client — **the existing SuperMini is reassigned here** (the node role moves to the Pro Minis). Check physical size, supply requirements and power consumption before final wearable assembly. |
| SSD1306 OLED module | **1** | Planned **0.96-inch, 128 × 64, I²C** display. Choose a module compatible with 3.3 V power and 3.3 V I²C logic; verify the actual pin labels and pull-ups. |
| BC547 transistor | **1** | **Chosen haptic drive** (the user's own part): low-side switch for the coin motor. GPIO7 → 2.2 kΩ → base, collector → motor's − terminal, emitter → GND. Page 4 of `SYSTEM_WIRING_DIAGRAMS.pdf`. |
| 1N5819 flyback diode | **1** | Across the motor, **cathode up** to the + terminal. |
| 10 Ω resistor | **1** | In the motor's + lead: caps the stall current at 3.3 V ÷ (R_motor + 10 Ω), about 69 mA for a 37 Ω coin ERM, inside the BC547's 100 mA rating. Use 22 Ω instead if the motor is much lower impedance (or fit a 2N2222A). |
| 2.2 kΩ resistor | **1** | BC547 base resistor: 1.2 mA of base current at 3.3 V, so a BC547A saturates. |
| 100 kΩ resistor | **1** | Base-emitter pulldown, so the motor stays off while the C3 boots with GPIO7 floating. |
| Compatible vibration actuator | **1** | A small ERM coin vibration motor is a practical candidate; select its rated voltage, startup/operating current and mechanical mounting to suit the driver, supply and intended vibration. Exact part is not yet selected. **Measure its stall current with a bench supply and a meter in series before soldering — do not guess.** |
| Protected rechargeable 1-cell Li-ion/Li-Po battery | **1** | Original proposal about 500 mAh; choose actual capacity, dimensions, protection, discharge rating and connector after the wearable current and runtime are measured. |
| 1-cell charger with protection and load-sharing/power-path | **1** | Select charge current for the chosen cell; a typical 1 A TP4056 module is not automatically suitable for a 500 mAh cell. |
| Regulated 5 V boost converter | **1 candidate** | Only if the selected C3 board is powered via its 5 V input; alternatively a properly specified 3.3 V regulator may be designed. Do not fit both by default; final architecture is undecided. |
| On/off switch | **1** | Rated and positioned for the selected power path. |
| 100 µF electrolytic capacitor | **1 candidate** | Bulk supply allowance, ≥10 V; final value and necessity depend on the converter. |
| 100 nF ceramic capacitor | **1 candidate** | Local supply decoupling allowance; check what is already on the modules. |
| Battery connector pair | **1 pair** | Match the cell and charger and verify polarity. |
| 4.7 kΩ resistors | **2 candidates** | One SDA and one SCL pull-up to 3.3 V **only if** adequate I²C pull-ups are not already fitted to the OLED module. Check combined resistance and voltage before adding. |
| Vero board, wires, headers and connectors | As needed | Small enough for the chosen enclosure; use insulation and secure all connections. |
| Wearable enclosure and strap | **1 set** | Secure, insulated, comfortable and appropriate for the chosen battery and motor. |

**Motor-drive choice:** the haptic drive is now the user's own **BC547** low-side switch — the DRV2605L breakout is **not** part of the bill of materials, and neither is the IRLML2502/AO3400 MOSFET with its 100 Ω / 10 kΩ gate resistors. Those belonged to an earlier direct-drive alternative. What is needed instead: one BC547, one 1N5819 (cathode up, across the motor), one 10 Ω (motor's + lead), one 2.2 kΩ (base) and one 100 kΩ (base-emitter pulldown). The user already owns an IRLML2502TR; retain it as a spare, or adapt it to a through-hole board if a MOSFET drive is chosen later.

**Power development:** a suitable regulated USB supply may be used during bench development if compatible with the selected ESP32 board. It is not a substitute for the eventual portable battery circuit. A nominal 3.7 V lithium cell is about 4.2 V when fully charged; never assume it is safe to connect directly to a 3.3 V input or GPIO. Match charger current to the actual cell and use an appropriate protection solution; charging/power-path behaviour must be verified rather than assumed from a generic module name.

## 5. Assembly and development supplies

| Item | Recommended amount | Notes |
|---|---|---|
| Vero board / stripboard | Enough for 3 nodes, hub and wearable | Final sizes depend on layout. |
| Insulated hook-up wire, pin headers and appropriate connectors | Assorted | Clearly label power and ground; use secure connections. |
| USB data cables | Up to **5** for simultaneous connection | Four for the three nodes and hub plus one for wearable; fewer suffice if shared or using power-only cables for already programmed units. Confirm each board's connector. |
| Regulated USB power outputs | **4** for three nodes + hub simultaneously | Plus one for wearable bench development if powered independently; a properly rated multiport supply may provide several outputs. |
| Solder and suitable soldering tools | As needed | Observe ventilation and safe soldering practice. |
| Heat-shrink / electrical insulation | Assorted | Cover joints and prevent shorts, especially near power connections. |
| Multimeter | **1** | Verify supply voltage, continuity, polarity and shorts before powering. |
| Breadboard and jumper wires | Optional | Useful during testing, not part of the final soldered build. |
| Fasteners, spacers and strain relief | As needed | Secure each assembly and cable in its enclosure. |

## 6. Consolidated purchasing count

| Main component | Total for complete system | Status |
|---|---:|---|
| ESP32-C3 development boards | **4** | 3 nodes + 1 planned wearable; subtract the node board already owned. |
| INMP441 microphone breakouts | **3** | 1 per node; subtract the microphone already owned. |
| ESP32-S3-DevKitC-1 with PSRAM | **1** | Existing hub. |
| 2.8-inch ILI9341 SPI TFT | **1** | Existing hub display. |
| 0.96-inch SSD1306 I²C OLED | **1** | Planned wearable. |
| BC547 haptic switch | **1** | The user's own part; the wearable's haptic drive. Replaces the DRV2605L breakout. |
| Compatible vibration motor | **1** | Exact model pending selection. |
| LX-LCBST-TC-001 charger + boost modules | **4 + 1 candidate** | Battery pads B+/B−, output VO+/VO−, charging via USB-C — pad map confirmed from the user's photograph. Bench-validate ONE board (charge current, trimpot-set 5.1 V output, off-state drain) before buying the rest; wearable use pending the same check. |
| Protected 1-cell rechargeable Li-Po cells | **5** | 3 nodes, 1 hub, 1 wearable; suggested starting sizes 2,000 / 3,000 / 1,000 mAh; each cell's datasheet must permit the module's measured charge current. |
| On/off power switches | **5** | One per unit; match the actual current and power-path placement. |
| 100 µF electrolytic capacitors | **4 + 1 candidate** | Proposed 3 node and 1 hub rail capacitors; wearable candidate. |
| 100 nF ceramic capacitors, marked 104 | **4 + up to 4 candidates** | 3 node ADC filters and 1 hub decoupling allowance; plus up to 3 supplemental mic capacitors and 1 wearable supply capacitor if needed. |
| 100 kΩ 1% resistors | **6** | Proposed node battery dividers, 2 per node. |
| Red indicator LEDs | **3** | Proposed node battery indicators; firmware and pin selection pending. |
| Blue indicator LEDs | **3** | Proposed node radio indicators; firmware and pin selection pending. |
| 330 Ω ¼ W resistors | **6** | Proposed node LED current limiters. |
| 4.7 kΩ resistors | **up to 2** | Wearable I²C pull-ups only if module pull-ups are inadequate. |
| Matching battery connector pairs | **5** | One per unit; verify connector type and polarity. |
| Node enclosures / hub enclosure / wearable enclosure and strap | **3 / 1 / 1** | Select after layouts and power arrangements are known. |

## 7. Differences from the old specification

1. Hub TFT corrected from **2.4 inches to the user's 2.8 inches**; the ILI9341 and 240 × 320 resolution remain relevant to the existing implementation.
2. Rechargeable power, node battery ADC parts and node indicator LEDs are included as a complete-system **proposal**, with individual quantities; unlike the USB prototype they are not yet implemented or validated. A fixed TFT backlight resistor is not assumed.
3. The wearable's haptic drive is the **BC547 low-side switch** the user owns (with a 1N5819 flyback, a 10 Ω stall cap, a 2.2 kΩ base resistor and a 100 kΩ pulldown); the DRV2605L breakout is dropped from the bill of materials, and the discrete MOSFET with its gate resistors is not used either.
4. Wearable charging, protection and regulation are acknowledged as necessary **if battery powered**, but remain to be selected together rather than copied as an unverified circuit.
5. Vero board, power supplies, enclosures, mounting and safety considerations are included. Bench breadboards are optional rather than required for the finished build.
6. The current model already runs using the hub's existing PSRAM; an extra memory component is not required.

## References and project evidence

- User-supplied original: `HARDWARE_COMPONENTS_DETAILED_SPECIFICATION.pdf`, five pages, October 2026; reviewed as the superseded specification.
- Project status: `SYSTEM_UPDATE.md`; implementation and project decisions: `DECISIONS.md` and `firmware/`.
- [Infineon IRLML2502 datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-irlml2502-datasheet-en.pdf): existing MOSFET package and electrical ratings.
