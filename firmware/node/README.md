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

### Why the I2S peripheral is 32-bit *and* stereo

Two things about this peripheral are not what you would guess, and both
were measured on the real board rather than reasoned out:

**32-bit slots.** The INMP441 puts 24 bits of data into a standard I2S
frame of two 32-bit slots, so the peripheral is configured for 32-bit
slots and the samples are narrowed to int16 in software by keeping the top
16 bits. Narrowing it any other way would shift the audio by a byte.

**Stereo, with the right slot dropped.** Asking the peripheral for mono
*halves the frame* to 32 bits, which breaks the INMP441's framing: the
same microphone read the same way produced −3500 counts of DC with the
full frame and −620 with the halved one. With the frame intact the DMA
delivers the left and the right slot interleaved, and both sketches take
every other word — the left slot, which is where L/R grounded puts the
microphone. Asking for stereo also makes the Arduino library force the
both-slots mask whatever mask is passed, so the mask argument is not doing
what it appears to do either.

`node_diag/` prints both configurations side by side; that is where this
was settled.

The INMP441's DC output also **drifts for a while after power-up** — about
−700 counts in the first seconds, settling towards −50. The hub's front
end removes the mean of each two-second window, so it does not matter, but
it is why a freshly-booted node reads a different DC offset from one that
has been running.

---

## Build and upload

```bash
python firmware/tools/install_sketches.py
```

This copies both sketches into the Arduino sketchbook
(`~/Documents/Arduino`), which is where the IDE looks for them. Then in
the Arduino IDE:

1. **File → Open** → `node_crynet` (or `node_capture`).
2. **Tools → Board → WeAct Studio ESP32C3** — this is the exact board
   (the ESP32-C3 SuperMini) and its entry already has the right flash
   size and the right USB settings.
3. **Tools → Port** → the node's port. It enumerates as
   `USB Serial Device (COM30)`, VID:PID `303a:1001`.
4. **Tools → Upload**.

### "USB CDC On Boot" must be enabled

This board's USB connector is wired to the **ESP32-C3's own native USB**
(`303a:1001`), not to a CH340. So `Serial` — UART0 on GPIO20/GPIO21 —
goes nowhere: those pins are not connected to the connector. With
**Tools → USB CDC On Boot: Enabled**, `Serial` becomes the USB CDC
device and everything works.

The WeAct board entry has this **on by default**, so choosing the right
board is enough. If you select "ESP32C3 Dev Module" instead, you must
set *USB CDC On Boot* to *Enabled* yourself, or the sketch will build
and upload but the console will be silent and the port will disappear
when the application starts.

The baud rate is then nominal — USB CDC is not a real UART — but the
tools still open the port at the rate the sketch names, so use the
rates given below.

Both sketches were compiled for `esp32:esp32:weact_studio_esp32c3` with
the core 3.3.12 that is installed here, and they build with no warnings:

| Sketch | Flash | Static RAM |
|---|---|---|
| `node_crynet` | 975,557 B (74 %) | 166,148 B (50 %) |
| `node_capture` | 308,808 B (23 %) | 18,760 B (5 %) |

The node firmware's RAM is two 64 KB windows: the live one and the frozen
snapshot that gets uploaded.

If the Arduino IDE cannot find the board, the C3's bootloader may be in
the wrong mode: hold **BOOT**, tap **RST**, release **BOOT**, and the
board reappears as a CDC port.

---

## The node firmware

### Console

115200 baud — nominal, because the console is a USB CDC device rather
than a real UART. One command per line:

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

The request's CRC covers its **first 10 bytes**; a frame's own CRC covers
its header *and* its payload. A request for a node id of `0xFF` is for
every node.

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

Each 100 ms record carries its own CRC-16/CCITT-FALSE, over its header
and its payload:

```
 0  'C' 'R' 'Y' '1'   magic
 4  u16 sequence
 6  u16 sample count
 8  u32 rms x 1000
12  u16 CRC-16/CCITT-FALSE over bytes 0..11 and the payload
14  int16 samples, little endian
```

A record whose checksum does not check out is **dropped** and counted,
rather than written into the WAV. Without it, one dropped byte on the USB
link would shift every sample after it, and a dataset of quietly
misaligned audio is worse than no dataset.

The PC can stop and resume the stream while it runs: it sends `S` or `R`
back to the node, which is a separate wire from the audio, so nothing the
PC sends can corrupt the recording.

---

## Bringing the microphone up

`node_diag/` is a bring-up tool, not part of the running system. It reads
the I2S stream in **stereo** — both slots, 32 bits each — and prints what
is actually on the wire, then scans every exposed GPIO to find where the
microphone's data really is.

```bash
python firmware/tools/install_sketches.py
# upload node_diag, then read the console at 115200
```

The INMP441 puts its 24-bit sample in the **left** slot of a 64-bit I2S
frame and leaves the **right** slot silent, so a healthy reading is a real
DC bias and a noise floor on the left and exactly zero on the right. The
diagnostic prints that comparison and ends with a verdict.

It matters that the reading is **repeatable**. The peripheral's start-up
transient looks like a signal for the first buffer or two, so the tool
measures the original configuration a second time at the end and says
whether the two agree.

---

## Layout

```
firmware/node/
├── node_crynet/
│   └── node_crynet.ino    the node firmware
├── node_capture/
│   └── node_capture.ino   the PC data collector
├── node_diag/
│   └── node_diag.ino      the microphone bring-up diagnostic
└── README.md
```

The two sketches repeat the I2S setup rather than sharing a header. The
Arduino IDE copies a sketch into a temporary folder before building it and
only copies the sketch's own folder, so a header in a sibling folder
would not be found.
