# CryNet — decision and issue log

> **What this file is.** The project's report and documentation record: every
> decision that was made, why it was made, every issue that was hit, how it
> was diagnosed, what was done about it, and what the result was.
>
> **Repo:** `C:\Users\HP\.t3\projects\fp-2` (branch `main`)
> **Companion files:** `SYSTEM_UPDATE.md` (the living status log and recovery
> layer — rewritten after every change) and `PROJECT_HANDOFF.md` (the deep
> briefing: the frozen contracts and the file map).
> **Last updated:** 2026-10-31
>
> **Conventions.** Each decision is written as **D-n** and each issue as
> **I-n**. A decision that was later changed carries a "revised by" note
> rather than being deleted, so the reasoning history survives. Every claim
> here was measured on the real hardware or in a real run; nothing is
> asserted from theory alone.

---

## 0. The system in one paragraph

Three ESP32-C3 cot nodes (INMP441 microphone, I2S at 16 kHz) → ESP-NOW
radio → an **ESP32-S3-DevKitC-1 hub** that reassembles each node's two-second
window, runs a TFLite Micro INT8 binary cry/no-cry classifier on it, and
shows the result on an ILI9341 TFT and publishes it to the caregiver's phone
over BLE GATT → a wearable (ESP32-C3 + OLED + DRV2605L haptic) that is still
to be built. The previous firmware attempt failed after flashing, so the
project was rebuilt from model training upwards.

---

## 1. The decisions

### 1.1 Scope and architecture

| # | Decision | Why |
|---|---|---|
| **D-1** | **Binary cry / no-cry**, not a multi-class head. | The BLE packet the wearable firmware was written against carries `alert_type 0x01` for a cry. There is no wire format for "cough" or "tired" without changing the wearable. Binary keeps the protocol honest and the alert unambiguous. |
| **D-2** | **Rebuild the firmware from scratch in ESP-IDF** rather than port the abandoned Arduino code. | The legacy hub was one 46 KB `.ino` with global state and a `loop()`/FreeRTOS mix. Its DSP implemented the *old* feature contract (128 mel bands, HTK scale, no normalisation), which is incompatible with the new model, so a "port" would have meant rewriting the signal path anyway. Rewriting gave a component tree, a single explicit state machine, and a wire format with per-fragment integrity. |
| **D-3** | **Keep the hardware facts, re-derive the software.** Physical pin assignments, the 3-node → hub → wearable topology and the legacy BLE UUIDs were inherited unchanged; the model, features, trigger, threshold, transport and application architecture were re-derived. | The boards and the wiring are facts about the user's real hardware. The parts that failed were the ones that had been guessed. Section 6 of `SYSTEM_UPDATE.md` carries the line-by-line comparison against the legacy repo. |
| **D-4** | **Model training first, firmware second.** The model is retrained and exported before any firmware is written. | The legacy system's trigger (`RMS ≥ 0.18`) meant a soft cry (the ICD corpus sits at RMS ≈ 0.006) never reached its classifier at all, so the old model was never fairly tested. Training first means the firmware is built against a contract that is known to work on real audio. |
| **D-5** | **One artifact per checkpoint; the agent updates `SYSTEM_UPDATE.md` after every edit and never pastes large logs into chat.** | Sessions were repeatedly lost to "400 Context Limit Exceeded". The status log is the recovery layer, and the checkpoints mean a crash costs one stage rather than the project. |

### 1.2 Data

| # | Decision | Why |
|---|---|---|
| **D-6** | **Every candidate corpus was profiled at audio level** (sample rate, duration, RMS, autocorrelation F0, spectral centroid and flatness) before any of it was used. | Sample rate and level decide whether a corpus can train a model that will run behind a fixed signal contract. A corpus that is 8 kHz or whose "silence" is loud cannot be mixed into a dataset that has none. |
| **D-7** | **Primary corpus: ICD (`hoyyu1/infant-cry-detection`)**, 28,478 clips, all 16 kHz mono 5.00 s, five shipped folds. Added: **Baby Cry 4-class** (cry diversity and a cross-corpus test), **ESC-50** (negatives and 40 held-out `crying_baby`), **Snoring** (hard negatives). | ICD is the only large, clean, 16 kHz cry corpus available without gating. The others widen the negative class and prove the model is not tuned to one recorder. |
| **D-8** | **Rejected corpora and the reason for each:** `mennaahmed23/baby-cry*` family — **contaminated** (fake "silence" at RMS 0.22, renamed ESC-50, synthetic derivatives); `rahult25/five-class…` — pitch-shifted derivatives of the same material; ICSD — gated on Hugging Face; AxonData — paid; Baby Chillanto — request-only; AudioSet / FSD50K — redundant; raw DonateACry — 8 kHz and skewed, and already merged into cry4. | Contaminated or derivative data does not add information and can teach the model the contamination. Gated or paid corpora cannot be re-fetched by the notebook, so the run would not be reproducible. |
| **D-9** | **Negatives deliberately include cat meows, speech and snoring.** | The deployed negative is a room, a baby and a television, not silence. A model that has only ever seen silence as a negative will fire on a fan. |
| **D-10** | **Label policy: "any cry present" in the 2 s window** (approximately three or more active frames). | The window is the unit the firmware classifies. A soft label (the loudest frame) would disagree with the label the hub's trigger effectively uses. |
| **D-51** | **Music joins the training corpus: GTZAN (Kaggle `carlthome/gtzan-genre-collection`, ten genres, 1,000 real recordings) as an all-negative corpus, with random windows per clip and the same 75 / 25 train / cross-corpus split as the other supplementary corpora.** | The false-alarm map of 2026-10-31 found that **no corpus in the training mix contained any music** — not ICD, not ESC-50, not the cry set, not the snoring set — so the model had never been taught to reject a song, and ESC-50 could not be used to measure it either, because ESC-50 has no music in it. A nursery has a radio, a television and a mobile playing something, so music is a first-class confusion class, not an afterthought. Random windows rather than a single centred one, because a thirty-second track is not one sound: the part that plays in the cot matters, not the average of the track. The 25 % held out keeps the model measurable on music it has never seen. |
| **D-52** | **`ZipReader` gained `index_by_path()` and `build_corpus` falls back to it.** | GTZAN names every clip `blues.00000.au` … `blues.00099.au`, once per genre — the same file name in ten folders. A stem index keeps only the first of them, so four fifths of the corpus would have vanished silently and the run would have looked normal. |

### 1.3 The signal contract (frozen — D-11)

Nothing in the firmware, the exported tables or the weights may change without changing all of them at once.

```
int16 pcm[32000] (2.0 s @ 16 kHz mono)
  → /32768 → subtract mean → zero-pad 256 front / 512 rear
  → 81 frames, 512-pt symmetric Hann, hop 400
  → |rfft|² (257 bins)
  → 64 Mel bands (librosa slaney, 20 Hz–8 kHz, 497 non-zero weights)
  → 10·log10(max(P, 1e-10)) floored at −80 dB
  → per-window standardisation (CMVN)
  → int8 quantise → TFLM → [P(no_cry), P(cry)]
```

| Constant | Value | Constant | Value |
|---|---|---|---|
| SR | 16000 | N_FFT | 512 |
| WIN_SEC | 2.0 | HOP | 400 |
| N_SAMPLES | 32000 | N_MELS | 64 |
| N_FRAMES | 81 | FMIN/FMAX | 20 / 8000 |
| CENTER_PAD | 256 | TAIL_PAD | 512 |
| DB_FLOOR | −80 dB | LOG_EPS | 1e-10 |
| CMVN | True | SILENCE_RMS_GATE | 0.0015 |
| TARGET_RECALL | 0.95 | SEED | 1337 |

| # | Decision | Why |
|---|---|---|
| **D-11** | **Freeze the signal contract, and export the Mel filterbank from Python into C** (`crynet_tables.h`). | The firmware cannot drift from the model if the filterbank *is* the model's filterbank: the weights are copied, not reimplemented. A hand-written Mel in C would drift silently and only show up as a small accuracy loss on the board. |
| **D-12** | **Per-window CMVN, not absolute dB.** | The legacy system used `power_to_db(top_db=80)` — absolute dB with no normalisation — which made the model level-dependent, and the deployed levels are wildly different from the training levels (ICD cries sit at RMS 0.006, the user's INMP441 room sits at 0.002–0.016 and a cry at 0.057–0.082). CMVN makes the model level-invariant, which is what lets one threshold work in both places. |
| **D-13** | **64 Mel bands, librosa slaney scale, fmin 20 Hz** (not the legacy 128 HTK bands). | A consequence of D-11: the features are defined by the notebook that trained the model. Changing them changes the meaning of the weights. |
| **D-14** | **The DC-removal mean is an exact `int32` sum, and the 100 ms RMS reported by the node is computed with the mean of the whole two-second window removed.** | Two reasons. First, a float accumulator loses counts on 32,000 samples and the residual DC is what the per-window standardisation then amplifies (see I-1). Second, the number the node reports must be *the same quantity* the hub's front end computes for that window — otherwise the hub's 0.03 trigger means nothing. |

### 1.4 The model and its verification

| # | Decision | Why |
|---|---|---|
| **D-15** | **Three plain CNN variants, no attention and no RNN** (`conv_cnn`, `sep_cnn`, `temporal_cnn`), and **every op is asserted to have a TFLite Micro kernel at export time**. | The legacy `TinyCryNet` (channel attention + GRU) needed ONNX and a bespoke 6.0 MB `app0` partition. Constraining the architecture to ops TFLM implements means the model is deployable on the target at all, and the assertion makes that a build-time fact rather than a hope. |
| **D-16** | **`conv_cnn` selected**: 122,770 parameters, val AUC **0.9994**, cross-corpus AUC **0.9973**; INT8 artefact **137,384 bytes**, SHA-256 `4aef55d8…126bc11`. | Best validation and cross-corpus AUC of the three, and 45× smaller than the legacy 6.15 MB FP32 model, so it fits a stock partition with room to spare. |
| **D-17** | **Calibrated alarm threshold = 0.95**, re-derived from the full run (an earlier subsample's 0.23 no longer applies). | The threshold is a *calibration result*, not a guess: it is the point on the recall curve that holds ≥ 0.95 recall, and the whole recall/FPR curve is reported with it. |
| **D-18** | **Verification is automated and numerical at every layer**: C front end vs Python, INT8 vs float32, TFLM kernel check, and the same four probes run *on the chip*. | The legacy repo had a parity script but it was a simulation. Four of the five Stage 2a defects were only findable by running the code on the silicon (I-1 through I-5). |
| **D-19** | **The tensor arena is reserved in PSRAM** (262,144 B reserved, 108,328 B used). | The 256 KB arena does not fit in the S3's internal SRAM alongside everything else. PSRAM is slower but the arena is touched linearly. Moving it into internal SRAM is the obvious next optimisation and was not needed for a triggered monitor. |

**Measured results (authoritative, from the full Kaggle run):**

| Split | AUC | F1 | Recall | Precision |
|---|---|---|---|---|
| ICD val (fold 4) | **0.9994** | 0.9905 | 0.9844 | 0.9966 |
| ICD test (fold 5) | **0.9995** | 0.9905 | — | — |
| cross-corpus (cry4 + ESC-50 + snoring, never trained on) | **0.9973** | 0.9801 | — | — |

| Check | Result |
|---|---|
| C front end vs Python (real run) | max deviation **6.905 × 10⁻⁵**, mean 2.79 × 10⁻⁶ |
| INT8 vs float32 (11,386 windows, host-measured) | ΔAUC **−0.001373**, decision agreement **99.956 %**, recall @ 0.95 0.9780 vs 0.9782, FPR 0.0036 vs 0.0036 |
| TFLM kernel check | `CONV_2D, FULLY_CONNECTED, MAX_POOL_2D, MEAN, SOFTMAX` — all present |
| On-device probes (ESP32-S3) | **4/4 PASS** — features match the host exactly on three probes, within 1 LSB on 3 of 5,184 values on the fourth |

### 1.5 Decision logic

| # | Decision | Why |
|---|---|---|
| **D-20** | **The trigger is RMS ≥ 0.030, not the legacy 0.18.** | The legacy value was a real bug: soft cries never reached a classifier. 0.030 sits an order of magnitude above the measured quiet room (0.002–0.016) and below a real cry (0.057–0.082), and it is the *same* number on the node and the hub. |
| **D-21** | **The trigger requires the level to have been sustained for two telemetry readings** (~200 ms), and the node's own event level is 0.030 as well. | The INMP441's slow DC drift produces one lone reading above the trigger on its own. In the quiet room the old trigger fired on the drift and pulled bursts continuously; the sustained rule stays quiet. |
| **D-22** | **The node freezes the window *before* it announces it**, and advertises the window's sequence number and CRC-32 in the telemetry. | The hub triggers on the node's 100 ms RMS but is served a *two-second* window. Before this change the hub was handed the live window, whose average is mostly the gaps between cries (trigger 0.0710 → window 0.0182 → "no cry"). Freezing first also gives the hub something it can *check*: the CRC-32 of the window it reassembles must equal the one the node froze, which is the proof that the audio crossed the link unchanged. |
| **D-23** | **A burst is analysed only when every one of its 286 fragments is present.** | A hole in the window is a hole in the audio. The alternative — analysing a partial window — would feed the classifier a signal the model never saw. The link tolerates loss by *recovering* it (D-26), not by pretending it away. |
| **D-24** | **The alert is published on state *change*, not per window, and only after the cry has been held for `CRY_HOLD_MS` = 8000 ms.** | A recording of cries has gaps; a per-window alert would flap on and off. One notification when a cot starts crying and one when it stops is what a caregiver needs. |
| **D-25** | **A silence gate of 0.0015 sits below the trigger.** | Below the gate the window is silence and no classification is meaningful. Above it, the calibrated 0.95 threshold decides. |

### 1.6 The radio link (node ↔ hub)

| # | Decision | Why |
|---|---|---|
| **D-26** | **The hub may ask the node to re-send the exact fragments that went missing** — a new `RESEND` frame carrying a 36-byte bitmap, one bit per fragment. This is the mechanism that makes the burst complete despite airtime loss. | The hub's radio is deaf whenever it is retuned to a Bluetooth channel, so a burst of 286 frames sent flat out always loses a few of them, scattered through the middle. The link must tolerate that by *recovery*, and a bitmap of the missing fragments is the cheapest way to ask: one 54-byte request covers any scattered pattern, and the node re-sends only what is missing. See I-24 to I-28. |
| **D-27** | **The stall detector asks for the missing fragments as soon as the burst stops growing**, and the wait before it declares a stall grows with the number of fragments still missing. | Asking early keeps the latency down; asking proportionally avoids spending a round while the node is still sending a hundred fragments that take a second and a half to arrive. |
| **D-28** | **The resend request is sent three times, and the node answers a repeat of the request it is already serving only once.** | ESP-NOW broadcast is never acknowledged: the sender is told the frame left the queue, not that it arrived. A resend request sent at exactly the moment the burst has just gone quiet is at the moment the radio has been busiest. Repeating the request covers a lost one; the node's dedupe stops the repeats turning into two or three redundant sends of a hundred fragments. |
| **D-29** | **The node holds an uploaded window for four seconds before freezing the next one.** | The upload is not the end of the conversation about that window: the hub asks for the fragments it missed, and only the node can send them again. The node used to freeze the next window about three seconds after the upload, and the hub's first request for the missing fragments often arrived just after that — by which time the node had thrown the old window away and refused the request. |
| **D-30** | **The hub abandons a burst the node can no longer complete** — if the node's telemetry reports a newer window sequence while a burst is in flight, the burst is dropped and the newer window is asked for at once. | The node no longer holds the fragments of the old window, so the burst cannot be completed and waiting out the 15-second timeout only delays the next attempt. |
| **D-31** | **ESP-NOW channel 6, set explicitly on both sides with `esp_wifi_set_channel()`** — not `WiFi.channel()`. | The Arduino core has no channel *setter*: `WiFi.channel(x)` is the scan result's channel (`WiFiScanClass::channel(uint8_t i)`), so the call compiled, returned an int, and changed nothing. The node sat on channel 1 while the hub sat on 6 and the sends failed with "peer channel is not equal to the home channel". ESP-NOW does not roam. The channel is also set *after* `esp_now_init()`, because starting the driver puts the interface back on channel 1. |
| **D-32** | **Broadcast at 10 Hz; unicast was tried and rolled back.** | Unicast to the learned hub address wedged the ESP-NOW send path: the frame was accepted, never transmitted, the send callback never fired, and every send burned its wait cap until the loop starved. Broadcast is reliable now that the node's loop runs in real time, and it disproved the earlier "the hub radio sleeps" theory — which is why the 100 ms heartbeat was removed (`WIFI_PS_NONE` plus constant node traffic is why the hub hears everything). |
| **D-33** | **The node waits for the previous frame's send callback before queueing the next one**, and paces the fragments about 13 ms apart. | ESP-NOW's transmit queue is ten frames deep; a 286-fragment burst sent back to back overflows it and every frame past the tenth is lost for good. The pacing spreads the burst over about four seconds, which the hub's timeout has plenty of room for. |
| **D-34** | **Promiscuous Wi-Fi mode is off by default** (build with `-DCRYNET_LINK_PROMISCUOUS=1` to bring it back). | It hands the host *every* frame on the channel. With the laptop's own Wi-Fi on channel 1 that flooded the receive path and cost the hub about fifteen fragments out of every burst. |
| **D-35** | **Every frame carries a CRC-16/CCITT-FALSE; the frozen window additionally carries a CRC-32 (the IEEE 802.3 one, the same function `zlib.crc32` computes).** | The CRC-16 covers each frame's header and payload; the CRC-32 covers the whole two-second window and is what proves the reassembled audio is byte-for-byte what the node froze. The wire format was validated numerically *before* any hardware was involved: CRC-16 reproduces the standard check vector `0x29B1`, and the C frame builder and the Python parser agree on every header offset and both CRCs. |
| **D-36** | **A fragment belonging to a window the hub did not ask for is dropped, not counted.** | The radio delivers frames in the order it wants to; one straggler from the last burst must not wipe the burst being assembled now. |
| **D-37** | **The node's serial console can never cost the node loop time** (`Serial.setTxTimeoutMs(0)`). | See I-12 — this was the root cause of a whole week of "the microphone is dead" symptoms. |
| **D-38** | **The node's radio is set up on channel 6 and the peer is added from `loop()`, never from a receive callback.** | `esp_now_add_peer()` waits for the Wi-Fi task to service it. Called from inside that task's own callback it blocks the very task it is waiting for, and the radio stops delivering frames until something else nudges it loose — the hub was receiving one frame in sixty. The hub's own `node_link.c` documents this trap. |

### 1.7 The hub system: memory, Bluetooth, display

| # | Decision | Why |
|---|---|---|
| **D-39** | **Boot-only buffers live in PSRAM and are freed after the probes run.** | 154 KB of the hub's static RAM (the probe PCM, the Mel and quantise buffers, and a 64 KB CRC buffer) was needed only while the boot probes ran, but as statics it held internal RAM for the life of the program — which is exactly the RAM NimBLE's store configuration wanted. Moving them to PSRAM took the hub's RAM from **59.9 % to 12.9 %** (196,140 B → 42,236 B) and made the whole stack fit: free internal heap 298,763 B at boot → 290,791 B after the probes → **215,155 B with the radio up → 149,271 B with Bluetooth up**. |
| **D-40** | **Init order: radio → Bluetooth → display.** | NimBLE's pools and the Wi-Fi driver's buffers come out of the same internal RAM, and when Bluetooth claimed its memory first the Wi-Fi driver ran out mid-init (`esf_buf_setup_static: alloc eb fail(1)`) and the ESP-NOW link never started. The radio takes what it needs while the heap is whole; Bluetooth lives on what is left. The panel is optional — a dead display must not stop the monitoring. |
| **D-41** | **`CONFIG_ESP_COEX_SW_COEXIST_ENABLE=y`** so the two stacks share airtime. | The one radio has to carry both. Coexistence is the software arbitrator; without it the two stacks fight. |
| **D-42** | **The BLE server serves the legacy UUIDs**, so the wearable firmware written against them keeps working: service `19b10000-e8f2-537e-4f6c-d104768a1214`, alert characteristic `19b10001-…` (read/notify/indicate; the legacy six-byte packet — cot id, alert type 1 = cry / 2 = cancel, confidence %, event id), plus a **new** state characteristic `19b10002-…` carrying the whole system (`cots`, `crying_mask`, loudest confidence, how long the cry has run). | Reusing the UUIDs means the wearable is a drop-in. The extra state characteristic is for a phone that opens late: it still sees the current state without waiting for the next change. |
| **D-43** | **The display is a state snapshot behind a spinlock, redrawn by a low-priority task pinned to core 1**, and each line is erased to the right edge so a shorter string cannot leave the tail of a longer one on the panel. | A 30 ms SPI burst must never delay the link loop or the inference. The level bar is sqrt-scaled so a quiet room still shows a sliver and the 0.030 trigger lands about a third of the way up. |
| **D-44** | **The Wi-Fi receive buffers were raised to 32 static / 64 dynamic** once the RAM was free. | The node sends a 286-fragment burst as fast as the radio allows; the hub needs receive buffers that can hold one. |

### 1.8 Toolchain and process

| # | Decision | Why |
|---|---|---|
| **D-45** | **PlatformIO 6.2.0 with `platform-espressif32` 8.0.0 and ESP-IDF 6.1.0**, installed by hand rather than pinned by URL. | PlatformIO 6.2 installs a URL-specified package by treating the archive as an **npm package**: it picks the wrong `package.json` out of the tree, writes a bogus version into `.piopm`, and leaves `packages/framework-espidf` holding only a test-fixture package (I-6). IDF 5.3.2 could not be installed through PlatformIO at all; 6.1.0 was already on disk and satisfies the port's `idf >= 5.1`. |
| **D-46** | **The vendored TFLite Micro port lives inside `firmware/hub_infer/components/`**, and `esp-nn` is wired as the port's own dependency with the registry copy removed. | PlatformIO re-compiles IDF components with SCons using the *source basename* for object names, and the TFLM port has twelve basename collisions, so the build died with "Multiple ways to build the same target". Moving the vendored components inside the project makes the paths relative and distinct. `firmware/tools/patch_deps.py` keeps the build offline and pinned. |
| **D-47** | **The flash mode is DIO throughout** — the effective config is `CONFIG_ESPTOOLPY_FLASHMODE "dio"` and both `bootloader.bin` and `firmware.bin` carry flash-mode byte `0x02`. | A combined image built with QIO makes the chip watchdog-reset in a loop (`rst:0x7 TG0WDT_SYS_RST` repeating, no application output). The ROM cannot read this board's flash in QIO before the bootloader has configured its own timing. DIO costs nothing at this workload. |
| **D-48** | **The node sketches are compiled with the Arduino IDE's own `arduino-cli` against core 3.3.12**, and the toolchain state is kept in the repo (`dependencies.lock`, `firmware/tools/fetch_deps.sh`, `patch_deps.py`). | The user's machine originally had no ESP-IDF, no PlatformIO, no Arduino IDE and no Xtensa compiler. Everything the build needs is now reproducible from the repo rather than from the state of one machine. |
| **D-49** | **Every host tool that reads a serial stream resynchronises on its own magic** and never waits for a fixed block; capture records carry a CRC-16 and the collector drops any record that fails it. | A USB CDC port can enumerate *after* the sketch has already printed its banner, and a single dropped byte on the USB link would otherwise shift every later sample and quietly ruin the dataset. Both stream parsers are testable classes, checked against synthetic streams. |
| **D-50** | **The notebook is generated from `research/build_notebook.py` and never hand-edited.** | The notebook is a build artefact. Editing it directly makes it impossible to regenerate and to diff. It is validated with `nbformat.validate()` after every regeneration. |

---

## 2. The issues, in the order they were found

Each entry: what it looked like → how it was diagnosed → what was done → the result.

### 2.1 Model and data

| # | Issue | Diagnosis | Measure | Result |
|---|---|---|---|---|
| **I-1** | **The INT8-vs-float32 parity cell reported `NaN` for both AUCs.** | The cell took a *prefix* of the validation fold. The ICD manifest lists every positive clip before every negative one, so the fold's positive clips alone contribute 5,330 windows — more than the 4,000-window cap — so that slice was 100 % cry and its AUC was undefined. | The notebook cell now draws a seeded random permutation subset and **warns loudly if a slice is single-class**. The gap was closed independently on the host by `research/verify_int8_parity.py`. | The model was never affected — every headline metric is computed over whole splits — but the quantisation delta had never actually been measured. Now: ΔAUC **−0.001373**, decision agreement **99.956 %**, and the independently computed float AUC (0.999299) corroborates the Kaggle figure (0.999419) from a different set of windows. |
| **I-2** | **Contaminated corpora were nearly used for training.** | Every corpus was profiled at the audio level, which is what exposed them. | Rejected at the source with the reason recorded in D-8. | The `mennaahmed23/baby-cry*` family was never trained on. Its "silence" sits at RMS 0.22 — louder than a real cry — and would have taught the model that loud means safe. |
| **I-29** | **The deployed model raises a false alarm on 8.19 % of loud music clips — a class it had never seen.** The user's requirement is that the system tells a cry from background noise, speech and music. Speech and noise are handled (1.6 % each); **music was not handled at all**, and the cause was structural, not a tuning slip: **no corpus in the training mix contained any music**, and ESC-50 — the corpus used for the false-alarm map — has none either, so neither the training nor the measurement ever touched it. | Two measurements. First `research/eval_esc50.py` over ESC-50's 2,000 real clips through the deployed INT8 model: 36 of the 40 real `crying_baby` clips alarm (90 %) and 38 of the 1,439 loud non-cry clips do (2.64 %) — urban 4.3 %, animal 3.7 %, domestic 1.6 %, human non-speech 1.6 %, nature 0.8 %. Then the corpus was checked for what it does *not* contain, which is what exposed the gap. | GTZAN was downloaded and `research/eval_music.py` ran the same deployed model over its 1,000 real music clips: **79 of the 965 clips that reach the model alarm — 8.19 %**, three times the rate for any other kind of sound. Worst genres: jazz 14.3 %, blues 13.0 %, pop 12.0 %, disco 10.0 %, rock 10.0 %; best: reggae 2.0 %, classical 2.9 %, country 3.0 %, metal 4.0 %. The mechanism is obvious in hindsight: a cry is a voiced, harmonic-rich sound, and a saxophone, a trumpet or a sung vowel in the log-Mel domain looks very much like one. GTZAN was added to the training corpus (D-51), the notebook was regenerated and validated locally on the stub cache, and the Kaggle re-run is the user's to start. | **Not fixed yet — the deployed model still false-alarms on music, and the fix is a training round, not a code change.** The deployed threshold cannot rescue it either: the model's INT8 output saturates at P(cry) = 0.9961, so 45 of the 81 music alarms and 34 of the 36 true cry detections sit at exactly the same value, and raising the threshold from 0.95 to 0.99 would remove 27 music alarms at the price of two real cry detections. A "two consecutive windows" confirmation was considered and deferred: music is continuous, so it would not help against music, and it would cost the demo a short single cry clip. |

### 2.2 Stage 2a — the hub's inference core

| # | Issue | Diagnosis | Measure | Result |
|---|---|---|---|---|
| **I-3** | **The DC-removal mean was accumulated in float32.** | Summing 32,000 samples of 18,000 in float32 gives 575,726,660 instead of 576,000,000, so the mean came out 8.5 counts low and 8.5 counts of DC survived. The per-window standardisation then blows that residual up into a completely different feature vector — the DC-offset probe failed with a max delta of 131. | The sum is now an exact `int32`. | Probe 2 passes; the on-device feature vectors match the host exactly. |
| **I-4** | **The build was at `-Og`, not optimised.** | `build_flags = -DCOMPILER_OPTIMIZATION_PERF` is an *Arduino* macro that means nothing to PlatformIO's ESP-IDF builder, so ESP-IDF's debug default applied. | Set the optimisation the ESP-IDF way: `CONFIG_COMPILER_OPTIMIZATION_PERF=y`. | Part of the front-end speed-up below. |
| **I-5** | **The CPU ran at 160 MHz, not 240.** | Read from the platform summary on the device. | `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`. | The board now reports 240 MHz. |
| **I-6** | **The front end kept a 128 KB padded copy of the signal in PSRAM.** | PSRAM on the S3 is uncached external memory, and the FFT and the Mel filterbank stream through the working set 81 times per window. | The padded copy is gone: each frame is built straight from the caller's int16 PCM. The working set is now **5,380 bytes in internal SRAM**. | Front end **135 ms → 41.7 ms**. |
| **I-7** | **A combined image built with QIO flash mode made the chip watchdog-reset in a loop.** | `rst:0x7 TG0WDT_SYS_RST` repeating with no application output; the ROM cannot read this board's flash in QIO before the bootloader has configured its own timing. | The combined image must use **DIO**. The whole build is DIO — the effective config is `CONFIG_ESPTOOLPY_FLASHMODE "dio"` and both images carry flash-mode byte `0x02`. | The board boots and runs. DIO costs nothing at this workload. |
| **I-8** | **The FlatBuffer alignment, the arena fit, the feature agreement and the latency were all unverified.** | Only a build proves nothing about the chip. | The same four probes the host parity test uses are run **on the target MCU**, and the device reports its own arena usage and timings. | **RESULT: PASS — 4 probes.** Arena 262,144 B reserved / 108,328 B used; front end **41.7 ms**; inference **101.8 ms** (ESP-NN SIMD kernels linked in: `esp_nn_conv_s8_esp32s3`, `esp_nn_conv_s8_1x1`, `esp_nn_conv_s8_3x3_opt`). |

### 2.3 Stage 2b — the node firmware

| # | Issue | Diagnosis | Measure | Result |
|---|---|---|---|---|
| **I-9** | **The INMP441's data line read exactly 0.00 in steady state.** The captured window was flat at 0–1 count with 533 single-sample spikes. | A new bring-up sketch (`node_diag`) read both I2S slots and scanned every exposed GPIO. The SCK scan read 0.00 on **every** pin, which is the clearest statement of the fault: with the clock on the wrong pin the microphone is never clocked, and with the clock on the right pin its data line still stayed flat. A repeat measurement of the identical configuration read 0.00/0.00 where the first read 3961/2320 — the apparent "signal" was the peripheral's **start-up transient**. | The fault was in the **wiring**, not the firmware: the INMP441 only drives SD when it is powered, clocked and given a valid word-select. The user rewired the board. | `verify_burst.py` then reports **PASS, 286/286 fragments, 0 bad CRC, exactly 64,000 bytes**, written out as a 2.00 s WAV: 1,943 distinct values, RMS 349 counts (0.011 of full scale), peak ±1,150 — a quiet room, no clipping. |
| **I-10** | **The two sketches disagreed about the I2S format** (one `MONO`+`SLOT_LEFT`, the other `STEREO`+`SLOT_LEFT`). | The diagnostic settles it: **STEREO with both slots, taking every other word**. MONO halves the I2S frame to 32 bits, which breaks the INMP441's framing — the same microphone read the same way gives −3500 counts of DC with the full frame and −620 with the halved one. Asking for stereo also makes the Arduino library force the both-slots mask whatever mask is passed, so the mask argument never does what it appears to do. | Both sketches now do the same thing. | The INMP441 puts 24 bits into a 64-bit frame, so the I2S setup uses **32-bit slots**; the narrowing to int16 is done in software by keeping the top 16 bits. The ESP32-C3 is I2S hardware v2, so the left-channel slot is selected in hardware, with no software decimation. |
| **I-11** | **A closed serial port starved the node's loop — the root cause of the week.** The mic appeared dead; the "INMP441 power-on transient" seen in hub captures was stale ring-buffer data. | ESP32 Arduino's USB-CDC (HWCDC) write path waits `tx_timeout_ms` (default 100) × up to 20 consecutive timeouts = **~2 s per print** when no host reads the port, and `usb_serial_jtag_is_connected()` stays true whenever the cable is plugged in, so `if (Serial)` gates did *not* help. The node printed its RMS every 100 ms, so an unattended node crawled to ~3 loops/s: the mic starved, telemetry fell to 0.35 Hz, and the window never filled. | **`Serial.setTxTimeoutMs(0)`** in `setup()` — prints drop instead of block. | Telemetry hit 10 Hz within one flash. (The earlier sessions only worked because the Arduino IDE serial monitor held the port open.) |
| **I-12** | **The INMP441's power-on transient** — the first 100 ms record read 0.656 of full scale, decaying 656 → 79 → 41 → 22 → 12 milli over ~500 ms. | It is the microphone's power-on burst, and it mattered twice: clips are cut from t=0, so `clip_0000` of every session contained it, and on the deployed node it would freeze a garbage window the moment it crossed the event level and hand the hub a spurious upload after every boot. | Both sketches read and discard 500 ms (8,000 stereo frames) right after the I2S starts. | A fresh capture session reads **7 milli on its very first record** — room level from sample 0, versus 656 before. `node_crynet` boots with a first RMS of 0.047 and never crosses EVENT. |
| **I-13** | **The node's window mean averaged the stale tail with the fresh head.** | After a burst the live window is dropped and refills; until it is full the newest samples are not at the start of the array, so a mean summed from index 0 was meaningless for exactly as long as the window was invalid. | The valid region is now walked **backwards from the write cursor**; the cursor is no longer reset, and a request arriving while the window is incomplete is refused rather than answered with a window whose order is unknown. | Both sketches recompiled clean. |
| **I-14** | **The Arduino IDE build failed with `cc1plus.exe: out of memory allocating 4194296 bytes`.** | The machine's **page file is disabled**, so the commit limit was 16,190 MB against 15,109 MB committed. | `AutomaticManagedPagefile` was set to `True` (the Windows default), which takes effect at the next boot; meanwhile the sketches are built and flashed with `arduino-cli` outside the IDE. | Both sketches build with **zero warnings**: `node_crynet` 979,375 B (74 %) flash / 166,308 B (50 %) RAM; `node_capture` 311,120 B / 18,592 B. |

### 2.4 Stage 2c — the radio, the panel and Bluetooth

| # | Issue | Diagnosis | Measure | Result |
|---|---|---|---|---|
| **I-15** | **`handle_telemetry` memset a new node's slot to zero, wiping the 64 KB window pointer `node_link_create` had pre-allocated.** | Every fragment was rejected on `window == NULL` and **not one burst ever reassembled**. The stats line decoded it: 702 raw, 702 parsed OK, 560 bad — parse passed, `handle_fragment` rejected; the only silent reject was the window pointer. | Save and restore the pointer across the memset; a slot with no window buffer now logs an error instead of being dropped silently. | Bursts reassemble. |
| **I-16** | **The hub's 2-second probe had become a 50 ms flood**, and the node wiped its whole live window after serving a one-fragment probe. | The heartbeat edit had deleted `last_probe_us = probe_now`. | Restore the timestamp; the node only wipes the live window after a real burst. | The probe flood is gone. |
| **I-17** | **`esp_now_add_peer` ran from the node's WiFi-task callback.** | The hub's own `node_link.c` documents this exact trap (see D-38). | Peer-add moved into `loop()`. | The hub receives every frame the node sends. |
| **I-18** | **Unicast to the learned hub address wedged the ESP-NOW send path.** | `esp_now_send` returned OK, frames never left, the send callback never fired, every send burned its wait cap and the loop starved. | **Rolled back to broadcast** at 10 Hz, which is reliable now that the loop runs in real time. | Broadcast works. This also disproved the "the hub radio sleeps" theory, so the 100 ms heartbeat was removed. |
| **I-19** | **The node on the board was running stale firmware.** | The "freeze before you announce" change had been written to `node_crynet.ino` but never reflashed, so the node had no auto-freeze at all: `g_peak_pending` appears 0 times in the last committed node build and 7 times in the current source. | Rebuilt and reflashed. | The chain runs for the first time end to end. |
| **I-20** | **The node's freeze was cancelled in the same tick that created it.** | `if (g_frozen_valid && (now - g_frozen_ms) > FROZEN_EXPIRE_MS)` used a `now` captured *before* `freeze_window()` ran, and `g_frozen_ms` is stamped *inside* it — so the subtraction underflowed to ~4 billion and the window expired the instant it was frozen. The symptom was unmistakable: the frozen sequence advanced (1, 2, 3, 4, 5 …) while the flags stayed `0x06` and the CRC stayed `0x00000000`, so the node never once advertised a burst as ready. | Measure the age from a fresh `millis()`. | The telemetry advertises `flags 0x07` and the window's CRC. |
| **I-21** | **The hub was still in promiscuous Wi-Fi mode** — a leftover diagnostic. | It hands the host every frame on the channel; with the laptop's own Wi-Fi on channel 1 that flooded the receive path. | Promiscuous mode off by default (D-34); `ESP_WIFI_STATIC_RX_BUFFER_NUM` 16 → 32 and `DYNAMIC` 32 → 64; 3 ms of pacing between the node's fragments. | The fragments are lost between the two radios, not in either end's code — the node's own numbers were healthy: 7,667 frames sent, **0 lost**, 2.3 ms average send wait, and the hub's parse was clean (0 bad frames, 0 bad payloads). |
| **I-22** | **Bluetooth and the ESP-NOW radio did not coexist.** With BLE up, `esp_wifi_init` failed (`esf_buf_setup_static: alloc eb fail(1)`) and the radio never started; in a later build NimBLE **asserted** on `Failed to allocate memory for ble_store_config_vars` and reset the chip in a loop. | The first fix attempt (radio before BLE) moved the failure to the other side, which is what showed the problem was not ordering. The real cause was in the ELF: **154 KB of the hub's static RAM was boot-only buffers that never got handed back**. | Move them to PSRAM (borrowed and returned) and free the probes' CRC buffer after each use (D-39). | RAM **59.9 % → 12.9 %**. The whole stack fits: free internal heap 215,155 B with the radio up, 149,271 B with Bluetooth up. Verified live: the panel comes up, the radio hears the node, the BLE server advertises, and a real client connects and subscribes while the radio keeps running — frames counted 21 → 308 with **0 bad, 0 bad payloads, 0 failed requests**, no resets. |
| **I-23** | **Three IDF 6 facts the build had to be taught.** | (1) The SPI and GPIO drivers live in `esp_driver_spi` / `esp_driver_gpio`, not `driver`. (2) A stale CMake configure ignores a `REQUIRES` change until the build directory's CMake state is deleted. (3) `font5x7.h`'s rows need their own braces or `-Werror=missing-braces` stops the build. | All three fixed. | The panel driver builds and runs. |
| **I-30** | **The TFT panel showed static noise — and the driver reported "the panel is up" the whole time.** The user wired the panel and plugged both boards in; the chain ran end to end on real audio (nine windows at P(cry) = 0.9961, one at 0.9883, CRC-32 MATCH on every burst, and P(cry) = 0.0000 on the quiet room and on a loud non-cry sound), but the panel was a field of coloured noise. **Three bugs, all in my own driver, all of which the driver was structurally unable to detect.** | **(1) The address window was little-endian.** `CASET` and `PASET` take four bytes big-endian; the code cast a `uint16_t` to `uint8_t *`, so 319 (0x013F) went out as 0x3F 0x01 and the panel read column 16129. **(2) `CASET` was sent twice.** The window is one command for the columns and one for the rows; sending the column start and then the column *end* as a second `CASET` re-sets the start instead of the end, collapsing the window to one pixel. **(3) CS was released between a command and its parameters.** The ILI9341 resets its serial interface when CS goes high, so every parameter byte was arriving as a *command* — the panel was never initialised at all, and what the user was looking at was uninitialised display memory. | The driver now **drives D/C in the SPI pre-transmission callback** (the only moment the level can safely change), sends **a command and its parameters as one transfer** with `SPI_TRANS_CS_KEEP_ACTIVE` on an acquired bus, and builds the address window big-endian, one command per axis. The text renderer was rewritten to draw **horizontal runs** instead of single pixels — about sixty times less SPI traffic, which is what makes a redraw cheap enough to run every second. A **blue 12×12 marker in the panel's top-right corner** settles the orientation from one photograph. | **Fixed and reflashed** (`research/toolchain/pio_build_display.log`, RAM 12.9 %, flash 61.9 %). The lesson is recorded rather than the fix: **a display driver that cannot fail is a display driver that lies** — the ILI9341's ID register can be read, but MISO is not wired, so it cannot be, and the driver's "up" message was only ever reporting that the SPI transactions returned without error. |

### 2.5 The airtime problem — the last and hardest issue

This is the one that kept the burst from ever completing, and it is worth recording in full because the reasoning was wrong twice before it was right.

| # | Issue | Diagnosis | Measure | Result |
|---|---|---|---|---|
| **I-24** | **The burst never completed: 267–274 of 286 fragments arrived, then the burst timed out.** | Three hypotheses were tested in turn and two were wrong. *(a) The Wi-Fi channel* — both sides were moved to channel 6 and the node was heard. *(b) The node's own counters* — 7,667 frames sent, **0 lost**, 2.3 ms average send wait, so the node was not dropping anything. *(c) **The hub's own Bluetooth advertising*** — the decisive test: the hub was built **without BLE** and produced **286/286 fragments in 3.75 s, four complete bursts in a row**. With BLE on, the same build lost ~6 % of every burst. | BLE advertises on channels 37/38/39, and the hub's single radio must *retune* to reach them — during which the Wi-Fi receiver is deaf. Three BLE events per advertisement at ~30 ms intervals ≈ 9 % deafness, independent of the Wi-Fi channel and the frame rate. That fits every observation, including why it was independent of the channel. | The root cause was confirmed. It is not a bug in either end's code; it is the physical reality of one radio carrying two protocols. |
| **I-25** | **The burst had no way to recover the frames it lost.** | The hub could see *that* fragments were missing but had no way to ask for them, and the node had no way to send them again. | Implement the `RESEND` frame (D-26): a 36-byte bitmap of the missing fragments in a 54-byte request; the node re-sends exactly those from the same frozen window with the same sequence number. | **The burst completed 286/286 with BLE on**, CRC-32 MATCH, and the first end-to-end cry alert. |
| **I-26** | **A resend request could be lost entirely.** | ESP-NOW broadcast is never acknowledged. The resend goes out at exactly the moment the burst has just gone quiet — the moment the radio has been busiest. One lost request means the round is wasted and the burst times out with the fragments still missing. | The request is sent **three times** (D-28). | A lost request no longer costs a round. |
| **I-27** | **The node re-sent the same fragments two or three times.** | The hub's three request copies each set the node's single pending flag, so the node served the whole request again. With 128 fragments missing that meant 256 or 384 fragments of air instead of 128, and the burst took 9.6 s instead of 5. | The node answers a repeat of the request it is already serving only once, within an 800 ms window (D-28). | One serving per round; the burst settles in about 5–7 s. |
| **I-28** | **The node refused the resend: "no frozen window for it."** | The node froze the next window about three seconds after the upload, and the hub's request for the missing fragments often arrived just after that — by which time the old snapshot had been replaced. | The node **holds** an uploaded window for four seconds (D-29), and the hub **abandons** a burst the node can no longer complete and asks for the newer window at once (D-30). | The resend is served, and a hopeless burst is recovered in about three seconds instead of fifteen. |

**The live test that closed it** — hub + node + a real BLE client connected, with the cry recording played through the PC's speakers:

```
W (37022) link: node 1: the burst stalled with 268 of 286 fragments; asking for the 18 that are missing
W (38562) link: node 1: the burst stalled with 285 of 286 fragments; asking for the 1 that are missing
I (39830) link: node 1: 286/286 fragments in 6.58 s
I (39830) link: node 1: window crc32 0x336F318E, the node advertised 0x336F318E -> MATCH
...
I (60681) link: node 1: window crc32 0x6230F1C4, the node advertised 0x6230F1C4 -> MATCH
I (60842) link: node 1: ALERT — cry
```

and on the phone:

```
ALERT {'cot': 1, 'alert': 'cry', 'confidence_pct': 100, 'event_id': 1}
STATE {'cots': 1, 'crying_mask': 1, 'confidence_pct': 100, 'started_at_s': 0}
ALERT {'cot': 1, 'alert': 'cleared', 'confidence_pct': 100, 'event_id': 2}
```

---

## 3. Results so far

| Claim | Number | How it was measured |
|---|---|---|
| ICD validation AUC | **0.9994** | full Kaggle run, fold 4 |
| ICD test AUC | **0.9995** | full Kaggle run, fold 5 |
| Cross-corpus AUC (never trained on) | **0.9973** | cry4 + ESC-50 + snoring |
| Deployed model | **137,384 bytes** INT8 | SHA-256 `4aef55d8…126bc11` |
| C front end vs Python | max **6.9 × 10⁻⁵** | 4 probes, real run |
| INT8 vs float32 | ΔAUC **−0.00137**, agreement **99.956 %** | 11,386 windows, host |
| On-chip front end | **41.7 ms** per 2 s window | ESP32-S3, 240 MHz, −O2 |
| On-chip inference | **101.8 ms** per window | ESP-NN SIMD kernels |
| Hub RAM | **12.9 %** (42,236 B) | after the PSRAM move |
| Hub flash | 61.9 % | 1,297,303 B of 2 MB |
| Hub internal heap with radio + Bluetooth | **149,271 B** free | at boot |
| Node flash / RAM | 979,375 B (74 %) / 166,308 B (50 %) | `weact_studio_esp32c3` |
| Radio link | **0 bad frames, 0 bad payloads** over thousands of frames | hub's own counters |
| Burst completion | **286/286 with CRC-32 MATCH** | live test, BLE client connected |
| End-to-end alert | **`ALERT {'cot': 1, 'alert': 'cry', 'confidence_pct': 100}`** | delivered to a real BLE client |
| Real baby cries detected | **36 of 40** ESC-50 `crying_baby` clips alarm | deployed INT8 model, `research/eval_esc50.py` |
| False alarms, loud non-cry sounds | **2.64 %** (38 of 1,439) | ESC-50, environmental + human non-speech |
| False alarms, **loud music** | **8.19 %** (79 of 965) | GTZAN, ten genres — `research/eval_music.py` |
| False alarms, quiet room | **0 in 236 windows** | this room's INMP441, `research/eval_indomain.py` |
| **Live chain, phone-played cry** | **P(cry) = 0.9961** on nine windows and 0.9883 on a tenth, every burst **286/286 with CRC-32 MATCH** | hub + node + a real BLE client, `research/hub_live.log` |
| **Live chain, quiet room and a loud non-cry sound** | **P(cry) = 0.0000** on every window, no alert raised | same session — the trigger fired (RMS 0.035-0.085) and the model rejected it |

---

## 4. Open items

| # | Item | Why it is still open |
|---|---|---|
| **O-1** | **The wearable (Stage 2d)** does not exist yet. | It is a BLE notification client with an SSD1306 OLED and a DRV2605L haptic driver. The hub's side of the contract (the legacy UUIDs and the six-byte alert packet) is done and verified against a real client, so the wearable can be written directly against it. |
| **O-2** | **The model has never heard a real cry.** | The only cry source available in this room is a *recording played through a phone speaker* — compressed, band-limited and EQ'd by the speaker. It is labelled as such. On that audio the model's AUC is 0.9283 with recall 0.724 and FPR 0.000; the misses are two-second windows landing in the gaps between cries. The negatives (this room, this microphone) are authentic. ~50 self-recorded real clips remain the single biggest accuracy win. |
| **O-3** | **Nobody has looked at the TFT panel.** | The code runs and the panel comes up at 320×240 — but "comes up" only ever meant the SPI transactions returned without error, and the first photograph showed **static noise**, which turned out to be three bugs in the driver (I-30). Those are fixed and reflashed; **one photograph of the panel now settles both what it shows and which way round it is mounted**, the blue square in the top-right corner being the orientation marker. |
| **O-4** | **The tensor arena is still in PSRAM.** | Moving it into internal SRAM is the obvious next optimisation. At 101.8 ms of inference per two-second window it is not urgent for a triggered monitor. |
| **O-5** | **The in-domain audio is speaker-played, not real.** | A real cry in this room, recorded with `node_capture`, is the honest test of whether the system works in the real room — and the dataset the model should be fine-tuned on. |
| **O-6** | **The distance curve (how far the phone can be) is still open.** | The phase cues did not line up in the earlier attempt, so the far-side measurement has to be repeated. |
| **O-7** | **The resend mechanism has not been exercised under a genuinely hostile channel.** | It is verified against the hub's own Bluetooth advertising, which is the real interference in this design, but not against a busy Wi-Fi environment with a second router on the same channel. |
| **O-8** | **The deployed model false-alarms on 8.19 % of loud music, and the fix is a training round that has not been run yet.** | GTZAN is now in the training corpus and the notebook is patched, regenerated and validated locally (D-51, I-29), but the re-run happens on the user's Kaggle account. Until it does, a room with music playing will produce roughly one false alarm per twelve loud music windows. The demo should therefore be run in a quiet room, or the music corpus should be trained in before the defence. |
| **O-9** | **The confusion session — the in-room measurement of speech, music, television and the phone-played cry — has not been recorded.** | `research/CONFUSION_SESSION.md` has the exact commands: six one-minute sessions with `node_capture`. It is the only measurement that uses this room's microphone, this room's gain and this room's acoustics, and it is what turns the corpus numbers into a number for the room the defence happens in. |

---

## 5. How to reproduce the results

```bash
# 1. the model, in the cloud
#    open notebooks/crynet_training.ipynb and run it on a Kaggle GPU
#    (regenerate it with: cd research && python build_notebook.py)

# 2. the host-side checks
cd research
python make_stub.py && bash run_stub.sh        # synthetic smoke test
bash run_real_fast.sh                          # real corpus, subsampled, CPU
pip install ziglang && python test_c_parity.py # C <-> Python parity
python verify_int8_parity.py                   # INT8 <-> float32 parity
python eval_indomain.py                        # the model on this room's audio

# 3. the firmware
cd firmware/hub_infer && python -m platformio run       # ~1 min incremental
python firmware/tools/flash_hub.py --port COM32         # flash and read the log
bash firmware/tools/fetch_deps.sh                        # re-fetch the pinned deps

# 4. the node (Arduino IDE, board WeAct Studio ESP32C3, USB CDC on boot)
arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_crynet
python firmware/tools/verify_burst.py --port COM30       # the node's window, as a WAV
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session1

# 5. the live end-to-end test
python firmware/tools/flash_hub.py --port COM32 --log-only --seconds 150
python firmware/tools/ble_alert_test.py --listen --seconds 140   # the phone
```

Every run's log is under `research/toolchain/` and every run's conclusion is
in `SYSTEM_UPDATE.md`'s change log.
