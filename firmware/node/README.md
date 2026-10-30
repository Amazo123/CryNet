# CryNet nodes — ESP32-C3 + INMP441

Two sketches for the cot nodes. Both are ordinary Arduino sketches and are
compiled and uploaded with the Arduino IDE, the way the rest of the
project's boards are.

| Sketch | What it is for |
|---|---|
| `node_crynet/` | **The node firmware.** Captures 16 kHz mono, keeps the last 2 s in RAM, reports a 100 ms RMS over ESP-NOW, and uploads the 2 s window in CRC-framed fragments when the hub asks. |
| `node_capture/` | **The data collector.** Streams the microphone to the PC over USB so in-domain audio can be recorded. |

The node never classifies anything. The model lives on the hub, and the
hub's front end consumes exactly the PCM bytes this node sends.

---

## Wiring

The INMP441 is a 3.3 V part — do not put it on 5 V.

| INMP441 | ESP32-C3 SuperMini | Note |
|---|---|---|
| `VCC` | `3V3` | 3.3 V only |
| `GND` | `GND` | |
| `L/R` | `GND` | selects the **left** channel |
| `SCK` | `GPIO4` | I2S bit clock |
| `WS` | `GPIO5` | I2S word select — **must** be connected |
| `SD` | `GPIO6` | data from the microphone |

`WS` is not optional: the INMP441 decides which half of the I2S frame it
drives from the word-select signal, and leaving it floating gives
unsynchronised data.

The pins are at the top of `node_crynet.ino` and `node_capture.ino`; change
them there if your breadboard is wired differently.

### Why the I2S peripheral is 32-bit

The INMP441 puts 24 bits of data into a standard I2S frame of two 32-bit
slots, so the peripheral is configured for 32-bit slots and the samples are
narrowed to int16 in software by keeping the top 16 bits. Narrowing it any
other way would shift the audio by a byte.

---

## Build and upload

```bash
python firmware/tools/install_sketches.py
```

This copies both sketches into the Arduino sketchbook
(`~/Documents/Arduino`), which is where the IDE looks for them. Then in
the Arduino IDE:

1. **File → Open** → `node_crynet` (or `node_capture`).
2. **Tools → Board → ESP32C3 Dev Module**.
3. **Tools → Port** → the CH340's COM port.
4. **Tools → Upload**.

Both sketches were compiled for `esp32:esp32:esp32c3` with the core
3.3.12 that is installed here, and they build with no warnings:

| Sketch | Flash | Static RAM |
|---|---|---|
| `node_crynet` | 977,617 B (74 %) | 165,972 B (50 %) |
| `node_capture` | 311,120 B (23 %) | 18,592 B (5 %) |

The node firmware's RAM is two 64 KB windows: the live one and the frozen
snapshot that gets uploaded.

If the Arduino IDE cannot find the board, the C3's bootloader may be in
the wrong mode: hold **BOOT**, tap **RST**, release **BOOT**, and the
board reappears as a CDC port.

---

## The node firmware

### Console

115200 baud. One command per line:

| Command | What it does |
|---|---|
| `status` | the node id, the window state, the RMS, the free heap |
| `stats` | the counters |
| `freeze` | freeze the live window now |
| `burst` | dump the frozen window as frames, in the radio's framing |
| `id <n>` | set the node id (1..255) |
| `help` | the list |

### Telemetry

Every 100 ms the node sends a telemetry frame over ESP-NOW (broadcast,
channel 1) carrying the RMS of the last 100 ms, the window length, and
flags for "a burst is ready" and "the event level is being crossed".

The RMS is computed over the newest 100 ms with the **mean of the whole
2 s window** removed, so it is the same quantity the hub's front end will
compute for that window — the hub's trigger threshold of 0.03 is
meaningless otherwise.

The mean is an exact integer sum. A float accumulator loses about eight
counts over 32000 samples, and the surviving DC offset is then amplified
by the front end's standardisation; that was one of the four bugs the
hub's on-device probes caught.

### The burst

When the node's RMS crosses the event level (0.10, above the hub's 0.03
trigger so that ordinary room noise does not start an upload) it freezes
the live window and increments the burst sequence number. The hub then
requests a range of fragments, and the node replies with them.

Sending 286 fragments takes a second or two, and the microphone keeps
running into a DMA buffer that is not being read, so the **live** window
is dropped and refilled afterwards. The frozen copy that was sent is not
affected.

### Framing

One framing is used on the radio and on the serial console.

```
 0  0xC3            magic
 1  0x7E            magic
 2  type            1 = telemetry, 2 = burst fragment
 3  node id
 4  u16 burst seq
 6  u16 fragment index
 8  u16 fragment count
10  u16 payload length
12  u16 payload CRC-16/CCITT-FALSE
14  payload
..  u16 frame CRC-16/CCITT-FALSE over everything above
```

A fragment carries 224 bytes of PCM, so a 64,000-byte window is 286
fragments. Requests from the hub are 12 bytes:

```
 0  0xC3  1 0x7E  2 type=3  3 node id
 4  u16 burst seq   6 u16 first fragment   8 u16 fragment count
10  u16 CRC-16/CCITT-FALSE
```

The hub's radio side is Stage 2c.

### Checking it without the hub

```bash
python firmware/tools/verify_burst.py --port COM32
```

This asks the node for its frozen window over the serial console, checks
every frame's CRC, reassembles the 64,000 bytes and writes them as a WAV.
If it passes, then the microphone, the 32-bit-slot conversion, the
circular window, the framing and the CRCs are all correct **on the
device** — the part that cannot be checked on the host.

---

## Collecting in-domain audio

The deployed model was trained on corpora that no microphone in this room
has ever produced: a different capsule, a different pre-amplifier, a
different gain, a different room. Until the model has heard this
microphone, the reported accuracy is an estimate about somebody else's
audio. This is the biggest accuracy gap left.

```bash
python firmware/tools/install_sketches.py     # once
# upload node_capture from the Arduino IDE, then:
python firmware/tools/collect_clips.py --out research/in_domain/session1
```

`collect_clips.py` writes three things into the session folder:

| File | What it is |
|---|---|
| `session.wav` | the whole session, 16 kHz mono 16-bit |
| `records.csv` | the RMS of every 100 ms record, so the loud parts can be found |
| `clips/clip_NNNN.wav` | the session cut into 5 s clips, the format the training corpus uses |

The PC can stop and resume the stream while it runs: it sends `S` or `R`
back to the node, which is a separate wire from the audio, so nothing the
PC sends can corrupt the recording.

---

## Layout

```
firmware/node/
├── node_crynet/
│   └── node_crynet.ino    the node firmware
├── node_capture/
│   └── node_capture.ino   the PC data collector
└── README.md
```

The two sketches repeat the I2S setup rather than sharing a header. The
Arduino IDE copies a sketch into a temporary folder before building it and
only copies the sketch's own folder, so a header in a sibling folder
would not be found.
