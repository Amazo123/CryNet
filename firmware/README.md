# CryNet firmware

Two firmwares live here, and they are built with two different tools on
purpose.

| | Hub | Cot nodes / wearable |
|---|---|---|
| Board | ESP32-S3-DevKitC-1 (N16R8) | ESP32-C3 |
| Build | ESP-IDF (PlatformIO) | Arduino (`.ino` sketches) |
| Where | `hub_infer/` | `node/` (Stage 2b), `wearable/` (Stage 2d) |
| Does | DSP front end, TFLite Micro inference, radio, TFT, BLE | I2S capture, RMS telemetry, ESP-NOW burst, BLE notify |

The hub runs TensorFlow Lite Micro with the ESP-NN SIMD kernels, which is
an ESP-IDF-level component with its own build requirements; the nodes are
ordinary Arduino sketches. Keeping them apart means each one is built the
way that suits it, and the Arduino IDE stays the tool for the boards you
touch most often.

---

## Hub: build it

The vendored dependencies (the Espressif TFLite Micro port and ESP-NN)
are not tracked in git — they are pinned by commit and fetched on demand.
Do this once after cloning:

```bash
bash firmware/tools/fetch_deps.sh
```

It clones two repositories at fixed revisions and applies
`firmware/tools/patch_deps.py`, which points the TFLite Micro port at the
vendored ESP-NN instead of the component registry so the build stays
offline and reproducible.

Then build:

```bash
cd firmware/hub_infer
python -m platformio run
```

## Hub: flash it

Three ways, all offline, all equivalent.

**1 — one command, no arguments**

```bash
python firmware/tools/flash_hub.py
```

Finds the board, writes the three images, then prints the boot log.

**2 — PlatformIO**

```bash
cd firmware/hub_infer
python -m platformio run -t upload
python -m platformio device monitor
```

**3 — a graphical flasher (Arduino IDE, or anything that takes a .bin and
an offset)**

```bash
python firmware/tools/flash_hub.py --merged --flash-only
```

writes one combined file to
`firmware/hub_infer/.pio/build/esp32s3/crynet_hub_merged.bin`. Select it
in the flasher and flash it at offset **0x0**. The Arduino IDE has no
built-in binary flasher; the **"ESP32 Flash Tools"** extension adds one.

> **The combined image must use DIO flash mode.** The ROM on this board
> cannot read the flash in QIO before the bootloader has set up its own
> timing, and a QIO image makes the chip watchdog-reset in a loop right
> after power-on — the classic symptom is `rst:0x7 (TG0WDT_SYS_RST)`
> repeating on the serial log with no application output. The whole build
> is in fact DIO (`CONFIG_ESPTOOLPY_FLASHMODE "dio"`, and both
> `bootloader.bin` and `firmware.bin` carry flash-mode byte `0x02`), so
> the application runs in DIO too — which costs nothing at this workload.
> `flash_hub.py --merged` forces DIO when it combines the images.

If you flash the three images separately instead, the offsets are:

| File | Offset |
|---|---|
| `bootloader.bin` | `0x0` |
| `partitions.bin` | `0x8000` |
| `firmware.bin` | `0x10000` |

## Hub: read the log

The firmware prints a verification report on every boot: the platform
summary, then for each of four probes the PCM checksum, the front-end
latency, the feature comparison against the host reference, the inference
latency, the class probabilities and the alert decision.

```bash
python firmware/tools/capture_serial.py --port COM32 --reset
```

`--reset` pulses EN so the whole boot sequence is captured. The Arduino
IDE's Serial Monitor works too — 115200 baud, any COM port.

## Nodes: build and flash them

The node sketches are Arduino sketches and live in `node/`; they are
covered in **[`node/README.md`](node/README.md)** — the wiring, the
console commands, the ESP-NOW framing, and how to collect in-domain audio
from the INMP441.

In short:

```bash
python firmware/tools/install_sketches.py     # copy them into the sketchbook
# then compile and upload from the Arduino IDE
```

## Tools

| Script | What it does |
|---|---|
| `tools/fetch_deps.sh` | clones the pinned TFLite Micro port and ESP-NN, applies the patches |
| `tools/patch_deps.py` | points the port at the vendored ESP-NN (`--check` to verify) |
| `tools/flash_hub.py` | finds the board, flashes it, prints the boot log |
| `tools/capture_serial.py` | reads the serial log, optionally resetting the board first |
| `tools/check_artifact_drift.py` | verifies the model, the quantisation constants and the thresholds against `deploy_config.json` |
| `tools/gen_probe_refs.py` | regenerates the on-device probe reference features from the notebook's own front end |
| `tools/install_sketches.py` | copies the node sketches into the Arduino sketchbook |
| `tools/collect_clips.py` | records in-domain audio from the node and cuts it into clips |
| `tools/verify_burst.py` | checks the node's capture, framing and CRC on the real hardware |

## Layout

```
firmware/
├── hub_infer/                     the ESP-IDF hub project
│   ├── components/
│   │   ├── crynet_model/          the INT8 model as a C array + the constants
│   │   ├── crynet_dsp/            the log-Mel front end
│   │   ├── crynet_infer/          the TFLite Micro wrapper
│   │   ├── esp-tflite-micro/      vendored (not in git)
│   │   └── esp-nn/                vendored (not in git)
│   └── src/                       the application: the Stage 2a probes
├── node/                          the ESP32-C3 node sketches (Arduino)
│   ├── node_crynet/               the node firmware
│   └── node_capture/              the PC data collector
├── tools/                         the scripts listed above
└── README.md
```
