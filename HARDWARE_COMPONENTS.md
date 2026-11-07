# CryNet — Hardware Components and Purchasing Specification

**Revision:** 7 November 2026  
**System:** three cot nodes, one central hub and one caregiver wearable  
**Purpose:** replace the earlier `HARDWARE_COMPONENTS_DETAILED_SPECIFICATION.pdf` for planning and purchasing.

This is a **planning bill of materials for the complete system**, including a proposed independent rechargeable battery supply for each unit. **There is no battery indication and no status LED anywhere in the system (D-83):** the battery-sense divider and every indicator LED have been removed, so this list carries no divider resistors, no divider filter capacitor and no LEDs. The battery circuits and the wearable have not been designed and validated yet: component quantities below are planning quantities, **not a verified schematic or a final purchasing guarantee**. Modules are purchased assembled: their onboard microscopic components are not listed as separate purchases. Quantities are **total system quantities**, not necessarily quantities still to buy; subtract parts already owned. The user has confirmed a **2.8-inch**, not 2.4-inch, hub display.

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

### Proposed rechargeable power — per node

The original document's battery arrangement is restored as a **planning design**, not as working firmware or a validated wiring diagram. For the three nodes, multiply each per-node quantity by three. The 5 V output must be regulated and connected only to the board's appropriate 5 V/USB input; verify the actual board and peak load first.

| Individual item | Per node | All nodes | Selection / purpose |
|---|---:|---:|---|
| Protected 18650 Li-ion cell (3.7 V nominal, 4.2 V full) | 1 | **3** | 3000 mAh or better, with protection. **Never LiFePO4.** Runtime not yet measured — see the runtime note in §3. |
| 18650 cell holder with leads | 1 | **3** | Soldered or bayonet type, sized for the cell. The holder must survive a cot rail being knocked; the cell must not be able to move. |
| 1-cell charger module | 1 | **3** | TP4056-based module is a candidate; ensure suitable cell protection and **load sharing/power-path**, and set a charge current appropriate for the actual cell. A common TP4056 protection board alone does not guarantee safe simultaneous operation and charging. |
| 5 V boost converter | 1 | **3** | MT3608 module is a candidate; select a converter with adequate **continuous** output at the lowest cell voltage and transient headroom, not merely its advertised peak figure. Verify shutdown, efficiency and actual ripple. |
| On/off switch | 1 | **3** | Rated for the chosen power-path current; final placement depends on charger/load-sharing design. |
| 100 µF electrolytic capacitor | 1 | **3** | Initial bulk-capacitor allowance for the 5 V rail, voltage rating at least 10 V; respect polarity. Confirm value and placement with the selected converter. |
| Battery connector pair | 1 | **3 pairs** | Match cell and charger; check polarity physically, not by colour alone. |

**Pin warning:** the old PDF assigns a red status LED to GPIO4, which is now used by the microphone — **do not wire the old LED circuit**. GPIO9 is a boot-strapping pin. The complete charger/power-path design must be selected before ordering or connecting these parts.

**There are no indicators on a node (D-83).** No link LED, no SOC LED, no LED at all: the hub's panel is the only place the system shows anything. The pins that would have carried them — GPIO10 for the link LED, GPIO7 for the SOC LED, GPIO3 for the battery ADC — are free, and nothing on the board drives them. (GPIO3 *was* read once: this repository's node firmware carried the divider read and its serial `battery` line until D-83 took it out.)

**The battery sense is not in this bill of materials (D-83).** The 220 kΩ / 100 kΩ divider, its 100 nF filter and the indicator LEDs were designed, costed and then withdrawn: the cots do not measure their cells and the hub's panel already shows the caregiver what matters. The reasoning for the design — a fixed 1 % pair rather than a potentiometer, the ×3.2 ratio, the 100 nF being load-bearing at the divider's 68.75 kΩ source impedance, the SOC curve rather than a linear voltage map, and the reading sagging 100–200 mV under the boost and radio load — is kept in `DECISIONS.md` (D-81 in the two-node repository, withdrawn by D-83) and is not repeated here. **Do not buy the divider resistors, the divider capacitor or the indicator LEDs.**

The one thing that stays true whatever else changes: **the battery voltage must never reach an ADC pin directly** — the C3's IO is 3.3 V only, and a full cell is 4.2 V.

If a battery readout is ever wanted back, the honest part is a **MAX17048** fuel gauge on I²C, not a divider: it reports a model-based SOC with no calibration table and does not care how much the terminal sags under load. The hub and the wearable have a spare I²C bus; the node's microphone occupies I²S, so a node would need the gauge part on another interface.

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
| Protected 18650 Li-ion cell (3.7 V nominal, 4.2 V full) | **1** | 3000 mAh or better, with protection. **Never LiFePO4.** The hub draws the most current of any unit, so this is the cell most worth sizing carefully. Use a holder if the selected cell requires one. |
| 18650 cell holder with leads | **1** | Sized for the cell; the cell must not be able to move in its holder. |
| Single-cell charger with suitable protection and power-path/load sharing | **1** | Select for the actual battery and simultaneous-load requirements. A basic TP4056 is not automatically a load-sharing solution. |
| Regulated 5 V boost converter | **1** | MT3608 is a candidate only if verified for the actual continuous and peak hub/display loads over the full battery range. |
| Power switch | **1** | Rated and placed for the final power path. |
| 100 µF electrolytic capacitor | **1** | Initial 5 V rail bulk-capacitor allowance; ≥10 V rating, observe polarity, verify against converter requirements. |
| 100 nF ceramic capacitor, marked 104 | **1** | Supplemental local decoupling allowance; confirm existing board components and placement. |
| Battery connector pair | **1 pair** | Match the cell and charger; verify polarity. |

These are a proposed design, not verified hub wiring. A portable power system needs measurement, a reviewed schematic and test before permanent assembly. The existing ESP32-S3 board already contains its own supporting circuitry; do not automatically add a separate TFT backlight resistor.

**Runtime is the open question on every battery-powered unit, and the power chain is why (D-82).** The chain is **cell → boost to 5.1 V → the board's 5 V pin → the board's own linear regulator → 3.3 V**. A linear regulator passes *current*, not power, so the current the cell must supply is set by the 3.3 V load while the difference between 5.1 V and 3.3 V is burned as heat. If the load draws 100 mA at 3.3 V, the cell is supplying roughly **160 mA** — about 1.8× the load current. A 1000 mAh pouch would therefore last on the order of **six hours**, and a 3000 mAh 18650 rather less than a day, at the hub's heavier load. *These are projections from the regulator's behaviour, not measurements — no runtime has been measured on this system.* The largest single lever on runtime is to skip the 5 V→3.3 V linear stage: feeding the board's **3V3 pin** from a 3.3 V buck-boost converter would roughly double the runtime for the same cell. That changes the power architecture, so it is recorded as an option to evaluate at the bench (D-82), not something to rewire before the current build is finished.

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
| Protected rechargeable 1-cell **Li-Po pouch** battery | **1** | **The opposite choice to the node's 18650 (D-81), and deliberately so.** An 18650 is 18 × 65 mm and 48 g — it will not sit on a wrist. A flat pouch cell is the right form factor here. Target **1000 mAh** (the original 500 mAh was too small to survive a night shift). Same chemistry as an 18650: 3.7 V nominal, 4.2 V full. **Never LiFePO4** — the module charges to 4.2 V. |
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
| Protected 18650 Li-ion cells, 3000 mAh | **4** | 3 nodes + 1 hub. **Never LiFePO4.** Buy protected cells. |
| 18650 cell holders with leads | **4** | One per 18650; the cell must not move in its holder. |
| Protected 1-cell Li-Po pouch cell, 1000 mAh | **1** | The wearable only — an 18650 is too large and heavy for a wrist (D-81). |
| On/off power switches | **5** | One per unit; match the actual current and power-path placement. |
| 100 µF electrolytic capacitors | **4 + 1 candidate** | Proposed 3 node and 1 hub rail capacitors; wearable candidate. |
| 100 nF ceramic capacitors, marked 104 | **up to 4 candidates** | Supplemental mic-supply decoupling near a node's VDD/GND (up to 3) and a wearable supply capacitor (1), if needed. The node ADC filter, the hub decoupling allowance's battery duty and the wearable divider filter are gone with the battery sense (D-83). |
| 4.7 kΩ resistors | **up to 2** | Wearable I²C pull-ups only if module pull-ups are inadequate. |
| Matching battery connector pairs | **5** | One per unit; verify connector type and polarity. |
| Node enclosures / hub enclosure / wearable enclosure and strap | **3 / 1 / 1** | Select after layouts and power arrangements are known. |

## 7. Differences from the old specification

1. Hub TFT corrected from **2.4 inches to the user's 2.8 inches**; the ILI9341 and 240 × 320 resolution remain relevant to the existing implementation.
2. Rechargeable power is included as a complete-system **proposal**, with individual quantities; unlike the USB prototype it is not yet implemented or validated. **There are no battery ADC parts and no indicator LEDs in the list** (D-83). A fixed TFT backlight resistor is not assumed.
3. The wearable's haptic drive is the **BC547 low-side switch** the user owns (with a 1N5819 flyback, a 10 Ω stall cap, a 2.2 kΩ base resistor and a 100 kΩ pulldown); the DRV2605L breakout is dropped from the bill of materials, and the discrete MOSFET with its gate resistors is not used either.
4. **Battery cells are 18650 for the nodes and the hub, and a Li-Po pouch for the wearable** (D-81, decided in the two-node repository and applied here because the hardware is the same). The old document named one generic pouch cell for all five units, which was wrong on both counts: a pouch cell is mechanically wrong for a unit sitting on a cot within a baby's reach, and an 18650 is physically wrong for a wrist strap. **LiFePO4 cells must not be used anywhere in this system** — the module charges to 4.2 V and an LFP cell tops out at 3.65 V.
5. **There is no battery sense and no status LED anywhere in the system (D-83).** The fixed 220 kΩ / 100 kΩ divider that D-81 designed — chosen over a variable resistor for good reasons — and its 100 nF filter have been withdrawn before they were fitted, together with the node's divider and its `battery` serial line, the node's planned link and SOC LEDs, the hub's planned BLE-status and SOC LEDs, and the wearable's planned divider. The reason is that the hub's panel already shows which cots are answering, and the battery figure was always an estimate. The cost is that nothing in the system will warn the caregiver that a cell is nearly flat.
6. Wearable charging, protection and regulation are acknowledged as necessary **if battery powered**, but remain to be selected together rather than copied as an unverified circuit.
7. Vero board, power supplies, enclosures, mounting and safety considerations are included. Bench breadboards are optional rather than required for the finished build.
8. The current model already runs using the hub's existing PSRAM; an extra memory component is not required.

## References and project evidence

- User-supplied original: `HARDWARE_COMPONENTS_DETAILED_SPECIFICATION.pdf`, five pages, October 2026; reviewed as the superseded specification.
- Project status: `SYSTEM_UPDATE.md`; implementation and project decisions: `DECISIONS.md` and `firmware/`.
- The battery-sense and cell decisions (D-81) and the runtime projection (D-82) are recorded in the **two-node** repository's `DECISIONS.md` §1.9, because that is the system on the bench; D-83 (the withdrawal of the battery sense and the status LEDs, recorded here too) supersedes the divider half of D-81.
- [Infineon IRLML2502 datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-irlml2502-datasheet-en.pdf): existing MOSFET package and electrical ratings.
- [MAX17048 fuel-gauge data sheet](https://www.analog.com/media/en/technical-documentation/data-sheets/max17048-max17049.pdf): the I²C alternative if a true SOC percentage is wanted later (D-81, D-83).
