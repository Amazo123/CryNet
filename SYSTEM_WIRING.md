# CryNet — USB Test and Complete-System Wiring Guide

**Revision:** 7 November 2026. Read alongside `HARDWARE_COMPONENTS.md`.

> **Important:** The node + hub signal wiring in section 2 reflects the working prototype. The wearable and battery power are **not implemented or verified**. There are **no status LEDs anywhere in the system** (D-83): the node's planned connection LED, the node's planned SOC LED, the hub's planned BLE-status LED and the hub's planned SOC LED have all been removed, and the battery sense divider has been removed with them. Their exact part-to-part power wiring and GPIO choices cannot safely be finalised until the actual board and charger modules, cell and motor are selected. Section 3 is a proposed connection architecture, not permission to wire an unspecified lithium charger. This academic prototype is not a certified infant-monitoring device and must not replace supervision. Keep cables, cells, modules and small parts out of reach of the infant.

## 1. System picture

```text
  Cot 1: INMP441 → C3  ── ESP-NOW ──┐
  Cot 2: INMP441 → C3  ── ESP-NOW ──┼→ ESP32-S3 hub → 2.8-inch TFT
  Cot 3: INMP441 → C3  ── ESP-NOW ──┘        │
                                             └── BLE → phone (tested)
                                                  or → C3 wearable (planned)
                                                           ├→ SSD1306 OLED
                                                           └→ BC547 → motor
```

No audio or signal wires connect the cot nodes to the hub: the link is wireless. Each assembly has its own local power and ground. The node, hub and wearable do not need grounds connected to each other.

## 2. Wiring A — USB-powered bench test

**Before wiring:** disconnect power; identify actual board/module pin labels; use a multimeter to check for shorts and verify the display module voltage. These are board pin labels, not physical header positions. Do not assume every breakout uses the same pin order.

### 2.1 Cot node: ESP32-C3 + INMP441

Repeat the same connections for each node. **Three-node simultaneous operation is now verified:** on 2026-11-04 all three nodes, the hub and the wearable ran on one laptop for twenty-five minutes — the three nodes on a USB hub, the hub and the wearable directly — with **no brownout, no reset and no false alarm** (node 1's own counters: 6 385 frames sent, 0 lost, 0 times the radio had no room).

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

**Where the microphone goes — a placement rule, measured.** The INMP441 is a **fixed-gain** part: it has no gain register and its own output saturates before the node's 16-bit window ever does, so a sound close enough to it arrives flat-topped and the window cannot be trusted. Measured on the bench: node 2 clipped at peak 31 801 of 32 767 on ordinary room sound, and a phone held 10 cm from the microphone clipped the cry it was playing — that window scored 0.9805 instead of 0.9961, and the alert named the wrong cot for 42 seconds. There is no software cure, so the rules for the finished assembly are:

- **Keep the microphone out of the cot's near field.** Mount it on the cot frame or a wall bracket, on a short stiff lead, at least **30 cm** from where the baby's head will be, and out of the mattress's own sound path.
- **Do not point it at a speaker, a radiator or a window.** A reflective surface doubles the level at the mic.
- **Never leave it loose on the mattress.** A soft surface damps the high frequencies the model reads, and the cot frame moves.
- The hub now **refuses a clipped window and says so in its log** (`the window is CLIPPED`), so a bad mount is visible rather than silent. Watch for that line in the hub's log after the first night of use; it is the fastest way to find a microphone that is too close to the sound.

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
| C3 **GND** | OLED **GND**, BC547 **emitter** | Common local ground. |
| C3 **3V3** | OLED **VCC** and the motor's **+ terminal** (through the 10 Ω) | The OLED must accept 3.3 V. The motor is on the 3V3 rail, not the 5 V rail. |
| Selected C3 I²C SDA | OLED **SDA** | Bus pull-ups must go to a safe 3.3 V logic rail. Check existing pull-ups before adding any. |
| Selected C3 I²C SCL | OLED **SCL** | Same. Verify address compatibility. |
| C3 **GPIO7** | 2.2 kΩ → BC547 **base** | The haptic drive is a discrete low-side switch, not an I²C driver. |
| BC547 **collector** | Motor's **− terminal** | The motor's negative terminal goes to the collector; that node also carries the 1N5819 anode. |
| BC547 **emitter** | GND | The transistor's emitter is the motor's ground. |
| USB source | C3 USB socket | Supply capability and driver power arrangement must be checked. |

The haptic drive is the user's own **BC547** low-side switch (the DRV2605L breakout is not used): GPIO7 → 2.2 kΩ → base, 100 kΩ base-emitter pulldown so the motor stays off while the C3 boots with GPIO7 floating, 10 Ω in the motor's + lead to cap the stall current, and a 1N5819 across the motor with the **cathode up**. The full circuit is page 4 of `SYSTEM_WIRING_DIAGRAMS.pdf`. The 2.2 kΩ gives 1.2 mA of base current, so a BC547A (hFE ≥ 110) saturates and can sink the motor's running current; **measure the motor's stall current before soldering** — the 10 Ω caps it at 3.3 V ÷ (R_motor + 10 Ω), about 69 mA for a 37 Ω coin ERM and so inside the BC547's 100 mA rating, but a much lower-impedance motor needs 22 Ω or a 2N2222A. Test firmware is needed before this wearable can receive BLE alerts.

## 3. Wiring B — proposed battery-powered complete system

### 3.1 Connections that remain the same

For each of the three nodes, retain **all six microphone connections** in section 2.1. For the hub, retain the TFT signal and ground connections in section 2.2. For the wearable, use only a finalised and tested version of section 2.3. Only the **power source** changes; never join all five batteries together. **The battery sensing and the status LEDs are gone** (D-83) — there is nothing on B+/B− but the cell, and no indicator of any kind on any unit.

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

### 3.3 No battery sensing, and no status LEDs

**This section used to describe the divider and two LEDs. It does not any more (D-83).**

There is **no battery sense divider on any unit** — not on the nodes, not on the hub, not on the wearable. B+ and B− carry the cell and nothing else. There is **no 220 kΩ, no 100 kΩ and no 100 nF** anywhere in the system, and there is **no LED on any unit**: no connection LED, no SOC LED, no BLE-status LED. The parts on the bill of materials for them are gone; they should not be bought and must not be fitted.

The **battery power itself is unchanged**: the cells, the LX-LCBST modules, the switches and the boost converters are exactly as planned in §3.2, §5.1, §5.2 and §5.3. What has been removed is only the *measurement* of the cell and the *indication* of it.

Why: the hub's panel already shows which cots are answering, and it shows it better than a second, slower LED on a cot could. The battery reading was always an estimate — a resting-voltage curve printed with a tilde — and the owner does not want it. The cost of removing it is that **nothing in the system will warn the caregiver that a cell is nearly flat**; the charge-prompt idea (§7) is gone with it.

**For the record, the divider was designed and then withdrawn.** It was a fixed pair — B+ → 220 kΩ → sense node; sense node → 100 kΩ ∥ 100 nF → B−; sense node → GPIO3 (ADC1_CH3) on the nodes and the wearable, GPIO1 (ADC1_CH0) on the hub — a ratio of ×3.2, so 4.2 V on the cell read as ≈ 1.31 V at the pin, drawing ≈ 13 µA continuously. It was a fixed pair and **not** a potentiometer, on purpose (D-81): a **two-terminal** pot cannot divide at all — the ADC pin's only path to ground is its own high-impedance input, so the pin still sits near 4.2 V — past the C3 IO's 3.6 V absolute maximum. A **three-terminal** pot used as a real divider does work, and the firmware does not need to read the wiper; what it costs is a **per-unit measured ratio**, **silent drift** with heat, vibration and wear, and **magnitude** — the SOC curve moved 100 mV = 20 percentage points around 3.8 V, so 1 % of ratio error is already ~10 points of SOC error, against a pot's 1–5 %. Two 1 % resistors gave a ratio the firmware knew exactly on every unit with no per-unit step. All sound; it simply is not wanted. The reasoning is kept in `DECISIONS.md` (D-81, D-83) and not repeated here.

### 3.4 Wearable battery and haptics

The wearable's power follows the same LX-LCBST pattern as the nodes (§5.3): VO+ → switch → SuperMini 5V pin; the OLED from the SuperMini's 3V3 output so the I²C bus stays at 3.3 V; the motor also from 3V3, switched by the **BC547** low-side drive described in §2.3 (GPIO7 → 2.2 kΩ → base, 10 Ω in the motor's + lead, 100 kΩ base-emitter pulldown, 1N5819 flyback with the cathode up). The proposed 1,000 mAh cell only buys runtime if the module's measured charge current suits it — confirm during bench validation. The cell is a **1000 mAh Li-Po pouch** (D-81) — an 18650 is 18 × 65 mm and 48 g and cannot go on a wrist, while the node and the hub take an 18650 because a cot frame can puncture a pouch; same chemistry either way, 3.7 V nominal and 4.2 V full. **Never LiFePO4**, because the module charges to 4.2 V. At the module's ~1 A the pouch's charge current is too high, so it must come down to ~400–500 mA. The IRLML2502 and its gate resistors belong to the alternative MOSFET drive and are **not wired into the BC547 path**; the DRV2605L breakout is not part of this design.

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
| Battery sense | **none** | The divider is removed (D-83): no 220 kΩ, no 100 kΩ, no 100 nF, nothing on B+/B−. GPIO3 is free. |
| Status LEDs | **none** | The planned GPIO10 connection LED and the planned GPIO7 SOC LED are removed before being fitted (D-83). GPIO7 and GPIO10 are free. |
| Power switch | **VO+ → switch → C3 5V pin** | SPST switch rated ≥1 A. VO+ / VO− are the pads printed 输出 (output). B+/B− stay connected for charging while the node is off. Do not switch the battery side. |

**There is no battery reading on the unit (D-83), and there is no LED of any kind.** The divider and its 100 nF are not fitted; the ADC pin is not read; the telemetry carries no cell voltage; the hub's panel carries no battery text. GPIO3, GPIO7 and GPIO10 are free. The planned heartbeat-and-ACK protocol was never about the LED: the LED was only ever going to *display* the ACK, and it is dropped from the plan with the rest of the indicators. The hub must still track the last telemetry time itself; an ESP-NOW send callback alone is not application delivery confirmation.

### 5.2 Hub — one unit

The current TFT assignments remain fixed: GPIO10 CS, GPIO11 MOSI, GPIO12 SCK, GPIO13 DC, GPIO14 RST and GPIO4 backlight. Proposed additions avoid those pins and the S3 strapping pins:

| Function | GPIO / connection | Components |
|---|---|---|
| Battery sense | **none** | The divider is removed (D-83): no 220 kΩ, no 100 kΩ, no 100 nF, nothing on GPIO1. |
| Status LEDs | **none** | The planned GPIO2 BLE-status LED and the planned GPIO17 SOC LED are removed before being fitted (D-83). GPIO2 and GPIO17 are free. |
| Power switch | **VO+ → switch → S3 5V pin** | Battery remains on module B+/B− while the hub is off. Verify the DevKitC input and converter output under TFT/radio load; the hub's peak draw is the heaviest of the five units and is not yet measured. |

The hub TFT keeps its working assignments (GPIO4 backlight, GPIO10–14 signals) and the hub has **no battery sense and no status LED** (D-83). Avoid GPIO0/3/45/46 (S3 strapping) and GPIO35–37 (Octal PSRAM bus on the N16R8). GPIO1, GPIO2 and GPIO17 are free.

### 5.3 Wearable — one unit

The wearable uses the same C3 board class, but the final board must be checked against its pin labels. Proposed non-strapping assignments are:

| Function | GPIO / connection | Components |
|---|---|---|
| OLED SDA | **GPIO5** | I²C SDA; add no external pull-up until the OLED breakout is checked |
| OLED SCL | **GPIO6** | I²C SCL; pull-ups, if needed, to 3.3 V only |
| **Status LEDs** | **none** | The wearable has **no status LEDs** — and now no battery sense either (D-76, D-83). An earlier revision gave it a blue link LED on GPIO1 and a red SOC LED on GPIO4; neither was ever in firmware, and the OLED already carries LINK/SCAN. The OLED stays the only display on the wrist, and it says nothing about the cell. GPIO3 is free. |
| Haptic drive | **GPIO7** → 2.2 kΩ → BC547 base; collector → motor −; emitter → GND | 10 Ω in the motor's + lead, 100 kΩ base-emitter pulldown, 1N5819 across the motor with the cathode up. Page 4 of `SYSTEM_WIRING_DIAGRAMS.pdf`. |
| Power switch | **VO+ → switch → C3 5V pin** | Same pattern as the node: disconnects the device, battery stays on B+/B− for charging. |

**Wearable power:** the wearable uses the same LX-LCBST pattern as the node: VO+ → switch → the SuperMini's 5V pin, VO− → GND. The OLED and the motor are powered from the SuperMini's **3V3 output pin** — not from 5 V: the OLED's I²C pull-ups ride on its VCC rail, so 5 V there would push 5 V levels into non-5-V-tolerant C3 GPIOs. Check the board's 3.3 V regulator current budget before final assembly: C3 radio peaks (hundreds of mA) + OLED (~25 mA) + motor bursts (~70 mA through the 10 Ω and the BC547) all share it; if it sags or resets during vibration, the motor supply design gets revisited on a branch. ESP32-C3 strapping pins are GPIO0/2/8/9 — the plan above avoids all of them.

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

Two characteristics remain unknown and must come from the bench validation: the **actual charge current** (the charger's program resistor is too small to read in the photo; if it programmes near 1 A, the wearable's 1,000 mAh cell needs its datasheet to permit that), and the boost converter's **quiescent drain while the unit is switched off** (the switch disconnects the load, not the converter — if off-state drain proves significant, the switch moves or the module changes). Note also that B− and VO− connect through the module's protection FET: in normal operation they are effectively the same ground, but at deep-discharge cutoff the battery disconnects and the unit dies — with no battery readout in the system (D-83), the caregiver finds that because a cot goes quiet, not because anything warned her; watch the cells by eye.

### Required one-board validation before buying four more

1. ~~Identify every terminal~~ — done from the photograph (§6 pad map). Remaining unknowns: actual charge current, boost quiescent drain, protection thresholds, the unlabelled front −/+ pair.
2. With no ESP32 attached, measure boost output range, no-load voltage, output under a dummy load and startup behaviour at full and partly discharged cell voltage.
3. Measure charging current and confirm termination at 4.2 V; verify whether the protection circuit disconnects at low voltage and short/overcurrent without deliberately abusing the cell.
4. Confirm that switch OFF disconnects the converter/load but leaves charging connected, and measure switch-off battery drain.
5. Run one node from it: compare reboot count, burst completion, radio range and microphone noise with the known USB baseline.
6. Only then decide whether it is suitable for the hub and whether a separate 3.3 V regulator is needed for the wearable.

## 7. There is no battery readout (D-83)

**This section used to describe an SOC display and a charge prompt. Both are gone.**

There is no battery text on the hub's panel, no battery readout on the wearable's OLED, and no battery LED anywhere. The hub's cot card shows the cot's name, whether it is answering, its sound level and confidence — nothing about the cell. The wearable has no status LEDs (D-76), and the OLED carries LINK or SCAN as the connection state.

**The consequence is worth stating plainly: nothing in the system will tell the caregiver that a cell is nearly flat.** That was the whole point of the feature, and it is the thing being given up. The cells still need watching by eye: charge each unit before it goes back on the cot, and take a unit off the cot when its cell is nearly flat rather than waiting for the protection circuit to disconnect it.

**What was removed, for the record.** The plan was a fixed 220 kΩ / 100 kΩ divider (ratio ×3.2) with a 100 nF across the bottom leg, read on ADC1 and averaged over sixteen samples every four seconds, a trust gate that refused a reading until three of them landed in the expected window, and a banded result on the panel: `BAT ~80 %`, `BAT LOW`, `BAT CRITICAL`, the band moving on hysteresis so one radio-load dip could not flash a warning at the caregiver. The map from voltage to percent was a curve, not a line — **4.20 V = 100 %, 4.05 ≈ 90 %, 3.90 ≈ 65 %, 3.80 ≈ 40 %, 3.70 ≈ 20 %, 3.55 ≈ 8 %, 3.45 ≈ 3 %, 3.30 ≈ 0 %** — because a lithium cell is not linear between 3.0 V and 4.2 V and a straight line reports a genuinely quarter-full cell as "58 %", wrong in the direction that says "fine" when the answer is "not fine". The bottom of the scale was **3.3 V**, because 3.0 V is roughly where a protected cell's protection circuit cuts out: end-of-life, not "empty".

**If it is ever wanted back**, the honest version is not a divider but a real fuel gauge — a **MAX17048** on I²C (the hub and the wearable have spare buses; the node's microphone occupies I²S, so a node would need the gauge part on another interface). A gauge reports the charge in the cell's own coulombs and does not care how much the terminal sags under load, which was the divider's other weakness. The reasoning is in `DECISIONS.md` (D-81 for the divider, D-83 for the withdrawal).

## 8. What is still required before this counts as verified

The LX-LCBST pad map is now known from the photograph; what remains is bench truth. Build **one** node power assembly exactly as in §5.1/§6, measure charge current, set the trimpot to 5.1 V, confirm switch-off behaviour and off-state drain, then run the working node firmware from it and compare with the USB baseline (reboots, bursts, mic noise). In parallel the user plans a **board swap**: ESP32-C3 Pro Mini boards for the three nodes and the existing SuperMini for the wearable — the firmware targets the chip, not the board, but each Pro Mini must prove native USB, 4 MB flash and the needed pins (GPIO4/5/6) before the swap counts; re-verify one node end to end on a branch. The battery sense and the status LEDs have been removed rather than built (D-83), so the pins they would have used — GPIO3, GPIO7, GPIO10 on a node, GPIO1, GPIO2, GPIO17 on the hub — are free and need no verification. No merge into `main` without the user's decision.

**Evidence:** `firmware/node/node_crynet/node_crynet.ino` (GPIO4/5/6); `firmware/hub_infer/components/hub_display/hub_display.c` (TFT pins); `SYSTEM_UPDATE.md` (working display wiring and hardware tests); `HARDWARE_COMPONENTS.md` (proposed BOM).
