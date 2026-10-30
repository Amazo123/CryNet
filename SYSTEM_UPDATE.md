# CryNet — SYSTEM_UPDATE.md (living status log)

> **This file is the recovery layer.** It is rewritten/appended by the agent **after every project update or edit** (code, notebook, config, decision, or a completed run). If the chat dies, is compacted into garbage, or hits "400 Context Limit Exceeded", a fresh chat reads this file first and is immediately back up to speed.
>
> **Repo:** `C:\Users\HP\.t3\projects\fp-2` (branch `main`)
> **Deep briefing (static, rarely changes):** `PROJECT_HANDOFF.md`
> **Last updated:** 2026-10-30

---

## 0. Protocol the agent follows (non-negotiable)

1. **Update this file after every edit.** Every change to the repo, every decision, every completed run gets an entry in §5 *Change log* (newest first) and, if it moves the needle, a refresh of §3 *Live status*.
2. **Keep chat context small.** Never paste large files/diffs/logs into chat. Write them to disk (e.g. `research/*.log`) and reference the path. Prefer background runs with a persistent log over long foreground commands. If context is getting long, say so and ask the user to run `/compact` — the agent then reloads state from this file.
3. **One artifact per checkpoint.** Confirm before starting the next stage.
4. **Minimal agent fan-out.** Use direct tool calls (WebSearch/WebFetch/curl/python) over subagents. At most 1–2 subagents when genuinely needed. A previous 18-agent fan-out exhausted the usage quota and several sessions died with 400 errors.
5. **Never hand-edit `notebooks/crynet_training.ipynb`.** Edit `research/build_notebook.py`, then regenerate with `python build_notebook.py`.
6. **Long runs go to the background** with output to `research/<name>.log`, so a session break never loses the work.

### Recovery procedure (for a fresh chat or lost context)

1. Read this file (top to bottom).
2. Read `PROJECT_HANDOFF.md` for the frozen contracts (signal contract, dataset decisions, file map).
3. `git status` + `git log --oneline -5` to see what is committed vs. uncommitted.
4. Continue from **§4 Next action**.

### 0.1 Live background work (as of 2026-10-30, ~06:00)

| What | Where | How to check |
|---|---|---|
| **Nothing is running.** The ESP32-S3 firmware **compiles, flashes and passes its on-device verification** — see §3. | — | `tail -60 research/toolchain/pio_build.log` for the last build |
| Rebuild from scratch | `cd firmware/hub_infer && python -m platformio run` | ~8 min from clean; ~1 min incrementally |
| Flash + read the log | `python firmware/tools/flash_hub.py` | finds the board, writes it, prints the report |
| Re-fetch the vendored deps | `bash firmware/tools/fetch_deps.sh` | clones the pinned commits and re-applies `patch_deps.py` |
| Install the node sketches into the Arduino IDE | `python firmware/tools/install_sketches.py` | copies `firmware/node/*` into `~/Documents/Arduino` |
| Build a node sketch without the IDE | `arduino-cli compile --fqbn esp32:esp32:weact_studio_esp32c3 firmware/node/node_crynet` | `arduino-cli.exe` ships inside the Arduino IDE |
| Ports | the hub on **COM32** (CH343), the node on **COM30** (`303a:1001`, the C3's own USB) | `python firmware/tools/collect_clips.py --list` |

**A background build survives `/compact` and even a lost session** — it writes to the log file on disk, not to the chat. Compaction only rewrites conversation history.

**What is NOT yet done — do not claim otherwise:**
- Stage 2a is complete *for the inference core*: the front end and the model are verified against the host reference on real hardware. Nothing else exists yet — no radio, no display, no BLE.
- Stage 2b is **written and compiles** for the ESP32-C3, but **has never run on the board**: the wiring is untested and the INMP441's actual level, DC offset and sample-rate accuracy are unmeasured.
- The inference is 101.8 ms per window. That is 5 % of the 2 s window and fine for a triggered monitor, but the tensor arena is still in PSRAM; moving it into internal SRAM is the obvious next optimisation.
- **No in-domain data yet** — the model has never heard the user's INMP441, room or gain.

**Next concrete steps:**
1. **Put the node on the board.** Upload `node_crynet` to the C3, wire the INMP441, and run `firmware/tools/verify_burst.py` — it checks the capture, the framing and the CRC on the real device and writes the two-second window out as a WAV. The node's I2S configuration (32-bit slots, left channel) has been compiled but never seen a microphone.
2. **Collect in-domain audio.** Upload `node_capture` and run `firmware/tools/collect_clips.py` to record the room, then ~50 real cry clips. This is the single biggest remaining accuracy win.
3. Then Stage 2c (the hub's radio, display and BLE) and Stage 2d (the wearable).

**Tools built so far (all runnable on the host):**
- `firmware/tools/check_artifact_drift.py` — verifies `research/out/` against `deploy_config.json` and the staged firmware copies. Currently **PASS**.
- `firmware/tools/gen_probe_refs.py` — regenerates `crynet_probe_refs.h` (expected on-device features) from the notebook's own front end.

---

## 1. Project in one paragraph

Multi-node infant cry monitor. 3× ESP32-C3 cot nodes (INMP441, I2S 16 kHz) → ESP-NOW → **ESP32-S3-DevKitC-1 hub** (TFLite Micro INT8 inference, ILI9341 TFT, BLE GATT) → wearable (ESP32-C3 + OLED + DRV2605L haptic). Model is a **binary cry / no-cry** classifier on 2 s log-Mel windows. Previous firmware attempt failed after flashing, so the project was rebuilt from model training.

---

## 2. Frozen decisions (do not re-litigate)

| # | Decision |
|---|---|
| 1 | Binary cry / no-cry head (BLE packet `alert_type 0x01` only supports binary). |
| 2 | Label policy = "any cry present" in the 2 s window (≈ ≥ 3 active frames). |
| 3 | Training runs on Kaggle GPU (user executes); notebook validated locally first by the agent. |
| 4 | Signal contract (below) is frozen — firmware, C code and weights all depend on it. |
| 5 | Trigger threshold must drop from RMS ≥ 0.18 → ~0.03 in the hub (old value was a real bug: soft cries never reached a classifier). |

**Signal contract (frozen):**
`int16 pcm[32000] (2.0 s @ 16 kHz mono)` → `/32768` → subtract mean → zero-pad 256 front / 512 rear → 81 frames, 512-pt symmetric Hann, hop 400 → `|rfft|²` (257 bins) → 64 Mel bands (librosa slaney, 20 Hz–8 kHz, 497 non-zero weights) → `10*log10(max(P,1e-10))` floored at −80 dB → per-window standardisation (CMVN) → int8 quantise → TFLM → `[P(no_cry), P(cry)]`.

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

Mel weights are **exported from Python into C** (`crynet_tables.h`), so firmware cannot drift from the model.

---

## 3. Live status (as of 2026-10-29)

**Checkpoint 1 = DONE, including the full Kaggle run. Checkpoint 2 (ESP32-S3 firmware) = Stage 2a in progress.**

### Done
- Dataset forensics: every candidate corpus downloaded and profiled at audio level (SR, duration, RMS, autocorr F0, spectral centroid/flatness).
  - **Used:** ICD `hoyyu1/infant-cry-detection` (PRIMARY, 28,478 clips, all 16 kHz mono 5.00 s, 5 shipped folds), Baby Cry 4-class (cry diversity + cross-corpus test), ESC-50 (negatives + 40 held-out `crying_baby`), Snoring (hard negatives).
  - **Rejected:** `mennaahmed23/baby-cry*` family (CONTAMINATED — fake "silence" at RMS 0.22, renamed ESC-50, synthetic derivatives), `rahult25/five-class...` (pitch-shifted derivatives), ICSD (gated HF), `AxonData` (paid), Baby Chillanto (request-only), AudioSet/FSD50K (redundant), raw DonateACry (8 kHz, skewed; already merged in cry4).
- 24-cell Kaggle notebook written, generated from `research/build_notebook.py`.
- **Validated end-to-end** on synthetic stand-ins (24/24 cells) and cells 1–15 on the real 28,478-clip corpus.
- **C front end == Python front end:** max deviation **7.06 × 10⁻⁵**, mean 2.8 × 10⁻⁶, over 4 probes (sine+harmonic, noise, DC-offset cry with INMP441 bias, silence).
- **Every op has a TFLM kernel** — asserted at export: `CONV_2D, FULLY_CONNECTED, MAX_POOL_2D, MEAN, SOFTMAX`.
- **INT8 vs float32:** AUC delta **−0.00007**, 99.70 % decision agreement.
- Notebook validated with `nbformat.validate()`.

### Current numbers — **the full Kaggle run** (authoritative)

The user ran `notebooks/crynet_training.ipynb` on Kaggle (GPU T4) and the artifacts are in `research/out/`. These numbers supersede the earlier subsample figures.

| Split | AUC | F1 | Recall | Precision |
|---|---|---|---|---|
| ICD val (fold 4) | **0.9994** | 0.9905 | 0.9844 | 0.9966 |
| ICD test (fold 5) | **0.9995** | 0.9905 | — | — |
| cross-corpus (cry4 + ESC-50 + snoring, never trained on) | **0.9973** | 0.9801 | — | — |

| Variant | Params | val AUC | cross AUC |
|---|---|---|---|
| **`conv_cnn` (selected)** | 122,770 | **0.9994** | 0.9973 |
| `sep_cnn` | 29,839 | 0.9974 | 0.9928 |
| `temporal_cnn` | 65,154 | 0.9805 | 0.9714 |

- Deployed model: `crynet_int8.tflite`, **137,384 bytes**, SHA-256 `4aef55d8cfc0fb75aa944e73945ef5b832f12d71479c48f82aff58563126bc11`.
- **Calibrated alarm threshold = 0.95** (re-derived by this run; the earlier subsample's 0.23 no longer applies).
- Input quantisation: scale **0.060125612**, zero_point **−4**. Output: `[1,2]` int8, scale 0.00390625, zp −128, classes `["no_cry","cry"]`.
- Tensor arena hint **120 KB** (the firmware reserves 256 KB and places it in PSRAM).
- C front end vs Python on the real run: max deviation **6.905 × 10⁻⁵**, mean 2.79 × 10⁻⁶.
- TFLM kernel check: **ok** — ops `CONV_2D, FULLY_CONNECTED, MAX_POOL_2D, MEAN, SOFTMAX`.
- **INT8 vs float32 — CLOSED.** The full run reported both AUCs as `NaN` because the parity cell took a *prefix* of the validation fold; the ICD manifest lists every positive clip before every negative one, and the fold's positive clips alone contribute 5,330 windows — more than the 4,000-window cap — so that slice was 100 % cry and its AUC was undefined. The model was never affected (every headline metric is computed over whole splits), but the quantisation delta for these weights was never measured.
  Re-measured independently on the host by `research/verify_int8_parity.py`, which rebuilds fold 4 from the cached archives with the notebook's own front end and runs **both** the exported INT8 model and the float32 Keras model over 11,386 windows (5,693 clips, centre-cropped — independent of the notebook's random crops):

  | | INT8 (as deployed) | float32 reference |
  |---|---|---|
  | val AUC | **0.997926** | **0.999299** |
  | recall @ 0.95 | 0.9780 | 0.9782 |
  | FPR @ 0.95 | 0.0036 | 0.0036 |

  ΔAUC **−0.001373**; max |Δp| 0.182; mean |Δp| 0.0029; **decision agreement 99.956 %**. The independent float AUC (0.999299) corroborates the Kaggle figure (0.999419) from a different set of windows. Report: `research/out/verify_int8_parity.json`.
- **Notebook fixed:** the parity cell now draws a seeded random permutation subset and warns loudly if a slice is single-class. Notebook regenerated and `nbformat.validate()`-passed.

- **On-device verification — CLOSED (2026-10-30).** The Stage 2a firmware runs on the
  user's ESP32-S3-DevKitC-1 (COM32, CH343 USB-serial) and **all four probes pass**:
  the device's quantised features match the host reference exactly for silence, DC
  bias and the two-tone signal, and to within 1 LSB on 3 of 5,184 values for the
  noise probe. `RESULT: PASS — 4 probes, front end and model agree with the host`.

  | | value |
  |---|---|
  | PSRAM | 8,388,608 bytes, present |
  | flash | 16,777,216 bytes |
  | model | 137,384 bytes int8 |
  | front-end working set | 5,380 bytes, internal SRAM |
  | tensor arena | 262,144 reserved, **108,328 used** |
  | front end | **41.7 ms** per 2 s window (was 135 ms before optimisation) |
  | inference | **101.8 ms** per window (ESP-NN SIMD kernels linked in) |
  | CPU | 240 MHz, `-O2` |

  Four real bugs were found *only* by running it on the chip:
  1. **The DC-removal mean was accumulated in float32.** Summing 32,000 samples of
     18,000 in float32 gives 575,726,660 instead of 576,000,000, so the mean came
     out 8.5 counts low and 8.5 counts of DC survived. On the DC-offset probe that
     leaves a constant residual which the per-window standardisation blows up into
     a completely different feature vector — the probe failed with a max delta of
     131. The sum is now accumulated in `int32`, which holds it exactly.
  2. **The build was at `-Og`.** `build_flags = -DCOMPILER_OPTIMIZATION_PERF` is an
     *Arduino* macro that means nothing to PlatformIO's ESP-IDF builder, so
     ESP-IDF's debug default applied. The optimisation level is now set the
     ESP-IDF way, `CONFIG_COMPILER_OPTIMIZATION_PERF=y`.
  3. **The CPU ran at 160 MHz**, not 240. `CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`.
  4. **The front end kept a 128 KB padded copy of the signal in PSRAM.** PSRAM on
     the S3 is uncached external memory, and the FFT and the Mel filterbank stream
     through the working set 81 times per window. The padded copy is gone — each
     frame is now built straight from the caller's int16 PCM — and the working set
     is 5.4 KB in internal SRAM. Front end 135 ms → 41.7 ms.

  A fifth trap is not a firmware bug but a flashing one: **a combined image built
  with QIO flash mode makes the chip watchdog-reset in a loop** (`rst:0x7
  TG0WDT_SYS_RST` repeating, no application output). The ROM cannot read this
  board's flash in QIO before the bootloader has configured its own timing. The
  combined image must use **DIO**. In fact the whole build is DIO — the effective
  config is `CONFIG_ESPTOOLPY_FLASHMODE "dio"` and both `bootloader.bin` and
  `firmware.bin` carry flash-mode byte `0x02` — so the application runs in DIO as
  well, which costs nothing at this workload. See `firmware/README.md`.

- **Stage 2b — the node firmware is written and compiles (2026-10-30), but has
  not run on the board.** Two Arduino sketches for the ESP32-C3, built with the
  Arduino IDE's own `arduino-cli` against core 3.3.12, **zero warnings**:

  | Sketch | Flash | Static RAM | What it does |
  |---|---|---|---|
  | `firmware/node/node_crynet/` | 977,617 B (74 %) | 165,972 B (50 %) | the node: I2S capture, a 2 s rolling window, 100 ms RMS telemetry over ESP-NOW, the 64 KB burst in 286 CRC-framed fragments |
  | `firmware/node/node_capture/` | 311,120 B (23 %) | 18,592 B (5 %) | streams the microphone to the PC so in-domain audio can be recorded |

  The I2S setup is Espressif's own recipe for this microphone — **32-bit slots**
  (the INMP441 puts 24 bits into a 64-bit frame, so 16-bit slots would misalign
  the data), `I2S_SLOT_MODE_MONO` with `I2S_STD_SLOT_LEFT`, and the narrowing to
  int16 done in software by keeping the top 16 bits. The ESP32-C3 is I2S
  hardware v2, so the left-channel slot is selected in hardware, with no
  software decimation.

  The node repeats the hub's DC lesson: the mean is an exact **integer** sum,
  and the 100 ms RMS is computed with the mean of the **whole 2 s window**
  removed, so the number the node reports is the same quantity the hub's front
  end will compute for that window — otherwise the hub's 0.03 trigger threshold
  means nothing.

  Two host tools came with it: `firmware/tools/verify_burst.py` asks the node
  for its window over the serial console, checks every frame's CRC and writes
  the result as a WAV; `firmware/tools/collect_clips.py` records the session and
  cuts it into 5 s clips. `firmware/tools/install_sketches.py` copies the
  sketches into the Arduino sketchbook.

  **Not yet proven:** that the wiring is right, that the INMP441's actual level
  and DC offset land in a sensible range, and that the effective sample rate is
  within tolerance of 16 kHz. All three are measured by `verify_burst.py` the
  first time the node runs.

  The **wire format was validated numerically** before any hardware was
  involved: CRC-16/CCITT-FALSE reproduces the standard check vector `0x29B1`,
  and the C frame builder and the Python parser agree on every header offset
  and on both CRCs (the frame's CRC covers its header *and* its payload; a
  request's CRC covers its first 10 bytes).

- **Firmware build — CLOSED (2026-10-30).** `firmware/hub_infer` now **compiles and links** for `esp32s3`:
  - toolchain: PlatformIO 6.2.0, `platform-espressif32` 8.0.0, **ESP-IDF 6.1.0**, `toolchain-xtensa-esp-elf` 14.2.0 (GCC 14.2);
  - images: `firmware.bin` **468,800 B**, `bootloader.bin` 22,560 B, `partitions.bin` 3,072 B;
  - **RAM 52.1 %** (170,668 B of 327,680 B) and **flash 22.3 %** (468,373 B of the 2 MB factory partition);
  - effective config: `esp32s3`, 16 MB flash, **octal PSRAM at 80 MHz**, custom 16 MB partition table, and **`CONFIG_ESP_TFLITE_MICRO_USE_ESP_NN=y`** — the ESP-NN SIMD kernels are compiled in, which is the difference between roughly 40 ms and roughly 2.3 s per convnet invoke on an S3;
  - the whole TFLite Micro port and ESP-NN compile cleanly under GCC 14 with the port's own `-Werror`;
  - `firmware/tools/check_artifact_drift.py` still **PASSes** (model SHA-256, threshold, quantisation, staged copies);
  - `firmware/hub_infer/dependencies.lock` records the exact IDF version and is committed.
  **Still unverified: anything that only happens on the chip** — the FlatBuffer alignment, the arena fitting, the probe feature agreement and the latency.

### Artifacts on disk
`research/out/` — **the authoritative full-run artifacts**: `crynet_int8.tflite`, `crynet_float.tflite`, `crynet.keras`, `model_data.h`, `crynet_tables.h`, `dsp_crynet.c/.h`, `crynet_infer_example.c`, `deploy_config.json`, `metrics.json`, `c_parity.json`.
`research/_realfast_out/` — the earlier subsample run, kept for comparison.
Logs: `research/real_fast.log`, `research/stub_run.log`.

### Git state and remotes
Local branch `main`, tracking `crynet/main`. Latest commit `bb89503` = **Stage 2b, the node firmware** (all of it committed — nothing uncommitted).

| Remote | Points at | Purpose |
|---|---|---|
| `crynet` | `github.com/Amazo123/CryNet.git` | **The live project.** Every change is committed here and pushed. Created 2026-10-29, **public** since 2026-10-29. |
| `legacy` | `github.com/Amazo123/Multi-Node-Infant-Cry-Detection.git` | The **old** project (Arduino firmware, BOM, wiring guides, old `model_data.h`). Read-only reference — do not push to it. Its hub `.ino`, `firmware/common/protocol.h`, `firmware/central_hub_s3/pins.h` and `dsp_mel_extractor.cpp` are the starting point for checkpoint 2. |

**Backup rule:** after every meaningful change → update this file → `git add -A && git commit && git push crynet main`. Never commit `research/_cache/` (5.5 GB of corpora) or the `_*_work/` scratch dirs; they are gitignored and the notebook re-downloads the corpora itself.

**What is *not* in GitHub:** the raw datasets (5.5 GB — re-downloaded automatically by the notebook) and the `_work`/`_parity` build scratch. Everything that is source, model, exported artifact, doc or log **is** in the repo.

### Open risks
1. **Unverified on hardware.** A successful build says nothing about the chip: the FlatBuffer alignment, whether the 256 KB arena actually fits, whether the DSP reproduces the Python features, and the real latency are all still unknown. This is the top risk, and the reason Stage 2a exists.
2. `coughing` is the top confuser; if it survives mining, add the FSDKaggle2018 cough set.
3. **No in-domain data** — the model has never heard the user's INMP441, room or gain. ~50 self-recorded clips (cries + room noise + speech + TV) is the single biggest remaining accuracy win.
4. TFLM latency unmeasured. With ESP-NN enabled the expectation is tens of milliseconds per 2 s window on a 240 MHz LX7, not the 100–300 ms the un-optimised kernels would cost; it must be measured on the real board.
5. The tensor arena is a 256 KB reservation placed in PSRAM; `AllocateTensors()` has never run. The notebook's hint was 120 KB, so it should fit — but the *actual* high-water mark is unmeasured.
6. BLE/display policy unchanged from the old spec; it already assumes binary output.
7. Old firmware gotchas still apply: INMP441 DC offset (~+18000 counts), ESP-NOW TX queue overflow (needs callback flow control), Arduino-3.x callback signature change, ILI9341 240 px clipping (the `HubDisplay` subclass).
---

## 4. Next action (checkpoint 2 — ESP32-S3 firmware)

### 4.0 Kaggle outputs — received and staged
The user placed the full-run `out/` at `research/out/`. `firmware/tools/check_artifact_drift.py` verifies the SHA-256, model size, quantisation, thresholds and the staged copies. **Current result: PASS** (137,384 bytes, SHA-256 `4aef55d8…126bc11`, threshold 0.95, input scale 0.060125612 / zp −4).

| File | Used by | Why it matters |
|---|---|---|
| `crynet_int8.tflite` | reference | the deployable model; `model_data.h` is the same bytes as a C array |
| `model_data.h` | hub | `crynet_model[]` + `crynet_model_len` — compiled into flash |
| `crynet_tables.h` | hub, node | Mel filterbank (start/end/offset + weights), Hann window, all constants, quant scales, **calibrated threshold**, silence gate |
| `deploy_config.json` | hub | input shape, quantisation params, operator list, TFLM kernel check, threshold, metrics, model SHA-256 |
| `metrics.json` | docs | per-variant AUC / F1 / recall |
| `c_parity.json` | docs | measured C-vs-Python front-end deviation |
| `crynet_float.tflite`, `crynet.keras`, `dsp_crynet.c/.h`, `crynet_infer_example.c` | reference | float reference, retrainable model, the portable C front end, TFLM glue template |

`research/_realfast_out/` stays as the *subsample* run for comparison; `research/out/` becomes the **authoritative** one.

### 4.1 The firmware is written from scratch — what that means concretely
The firmware is **not** a port of the abandoned Arduino code. ESP-IDF, new module layout, new transport, new application state machine. Explicitly:

**Re-derived (legacy code is not reused):**
1. **Application architecture.** The legacy hub was one 46 KB `.ino` with global state and a `loop()`/FreeRTOS mix. New: ESP-IDF with separate components (`crynet_dsp`, `crynet_model`, `crynet_infer`, `node_link`), a dedicated inference task, and an explicit event-driven state machine.
2. **The node↔hub transport.** The legacy telemetry had no ack, no retry, no per-fragment integrity check — which is exactly why it lost audio packets. New: my own packet layout with session IDs, per-fragment sequence numbers, CRC, and retransmission; the hub tolerates loss by design.
3. **The DSP front end.** The legacy `dsp_mel_extractor.cpp` implements the *old* contract (128 mel, HTK scale, no normalisation) and is incompatible with the new model anyway. New: the notebook's `dsp_crynet.c` (this rebuild's own code, already validated against Python to 7.06 × 10⁻⁵), ported to ESP-DSP `dsps_fft2r` + `dsps_cmplx_mag`.
4. **Trigger and decision logic.** Legacy: hard-coded `RMS ≥ 0.18` + `CONFIRMATION_PROB 0.65`. New: `RMS ≥ 0.03` trigger, 0.0015 silence gate, and the **calibrated** threshold from `crynet_tables.h`.

**Kept deliberately (hardware facts, not design decisions):**
1. The model's input contract (2 s, 16 kHz, 81 × 64 log-Mel, CMVN) — the trained weights require it exactly.
2. Physical pin assignments and the board wiring — facts about the user's real hardware, verified against the wiring docs, with the driver code written fresh.
3. The 3-node → hub → wearable topology and the binary alert semantics (`alert_type 0x01`).

### 4.2 Staged plan — one artifact per stage

**Stage 2a — hub inference core.** *(the risk-reduction stage: no radio, no display, no BLE)*
Minimal ESP-IDF app that links `model_data.h` + `crynet_tables.h`, runs the DSP front end and TFLM INT8 on a 2 s buffer, and prints `P(cry)`, inference latency and tensor-arena usage. Runs the **same four probes** as the Python parity test *on the target MCU*, so the DSP is verified on real hardware, not just on the host.
Exit criteria: compiles; runs on the S3; on-board front-end deviation vs Python < 1 × 10⁻³; latency and arena measured and logged; arena moved to PSRAM if it does not fit in internal SRAM.

**Stage 2b — node firmware (ESP32-C3).** I2S INMP441 capture at 16 kHz, DC-offset removal, 100 ms RMS telemetry, on-demand 64 KB audio burst with fragmentation + CRC + retry.
*Status (2026-10-30): written, compiles with zero warnings, **not yet run on the board**.* See §3. The hub's radio side of the protocol is Stage 2c.

**Stage 2c — hub system.** ESP-NOW receive, RMS trigger, audio assembly across 320 fragments, inference, TFT display, BLE GATT server, alert packet.

**Stage 2d — wearable (ESP32-C3).** BLE notification client, SSD1306 OLED, DRV2605L haptic.

### 4.3 Toolchain status
This machine originally had **no ESP-IDF, no PlatformIO, no Arduino IDE and no Xtensa compiler**. PlatformIO **6.2.0** is installed (`research/toolchain/pio_install.log`) so the firmware can actually be **compiled and checked** here rather than written blind. Flashing still requires the user's physical boards.

**What is installed now**

| Package | Version | Notes |
|---|---|---|
| `platform-espressif32` | **8.0.0** | pinned in `platformio.ini` |
| `framework-espidf` | **ESP-IDF 6.1.0** (`4.60100.0`) | installed **by hand** — see below |
| `toolchain-xtensa-esp-elf` | 14.2.0 | GCC 14.2 |
| `toolchain-riscv32-esp`, `toolchain-esp32ulp`, gdb packages | — | for the C3 nodes and debugging |
| `arduino:esp32` (Arduino core) | **3.3.12** | the node sketches. `ESP_I2S`, `ESP_NOW` and `BLE` are all present in it |
| `arduino-cli` | **1.5.1** | ships *inside* the Arduino IDE (`resources/app/lib/backend/resources/arduino-cli.exe`) — it is how the node sketches are compiled and checked here, without opening the IDE |
| PlatformIO IDE (VS Code extension) | 3.3.4 | pointed at the **pip-installed** Core 6.2.0 (see below), so it drives the same toolchain every build in this repo came from and needs no network |

**The PlatformIO IDE in VS Code.** The extension is installed and works with
the toolchain that is already here. `.vscode/settings.json` (at the repo
root and in `firmware/hub_infer/`) sets:

```json
"platformio-ide.useBuiltinPython": false,
"platformio-ide.useBuiltinPIOCore": true,
"platformio-ide.customPATH": "C:\\Users\\HP\\.platformio\\penv\\Scripts"
```

**`useBuiltinPIOCore` must be `true`.** The extension's compatibility
check is `get-platformio.py check core --version-spec ">=6.1.6"`, and it
looks for a Core in `~/.platformio/penv/Scripts` — nowhere else. With the
setting off it reports *"Could not find compatible PlatformIO Core.
Please enable `platformio-ide.useBuiltinPIOCore`"*. The Core was
installed there with PlatformIO's own bootstrap script:

```bash
python ~/.platformio/.cache/tmp/get-platformio-1.2.2.py
```

It is **6.2.0**, the same version the command line uses, and it shares
`~/.platformio`, so ESP-IDF 6.1.0, the Xtensa toolchain and esptool are
the ones already installed and **nothing is re-downloaded**. The hub
builds through it in **99.3 s**. Open `firmware/hub_infer` as the folder
and use the toolbar: **✓ build**, **→ upload**, **plug serial monitor**.

**Do not pin the framework with a `platform_packages` URL.** PlatformIO 6.2 installs a URL-specified package by treating the archive as an **npm package**: it picks the wrong `package.json` out of the tree, writes a bogus version into `.piopm`, and leaves `packages/framework-espidf` holding only a test-fixture package. CMake then fails with:

```
include could not find requested file:
  .../packages/framework-espidf/tools/cmake/project.cmake
```

The fix that worked: delete `packages/framework-espidf`, move the fully extracted tree into its place, and write `.piopm` by hand:

```json
{"type": "tool", "name": "framework-espidf", "version": "4.60100.0",
 "spec": {"owner": "platformio", "id": null, "name": "framework-espidf",
          "requirements": "~4.60100.0", "uri": null}}
```

**Why ESP-IDF 6.1.0 and not 5.3.2.** 5.3.2 was the original target, but PlatformIO's registry only offers the framework as `~4.60100.0` (6.1.0) with `~3.50505.0` (5.5.0) as the alternative for this platform, and the 5.3.2 archive could not be installed through PlatformIO at all. 6.1.0 was already on disk, satisfies the port's `idf >= 5.1` requirement, and needed no further download. **Fallback if the port misbehaves under IDF 6.1/GCC 14:** install `platform-espressif32` 6.9.0 (framework `~3.50301.0` = IDF 5.3.1, toolchain 13.2.0) and let PlatformIO fetch both.

### 4.4 User-side action in parallel
**Done:** the user ran the full Kaggle notebook and dropped `out/` into `research/out/`; the user connected the ESP32-S3 and the Stage 2a on-device verification **passed**.

**Now, in order:**
1. Upload `node_crynet` to the C3 — Arduino IDE → board **WeAct Studio ESP32C3** → port **COM30** — with the INMP441 wired as in `firmware/node/README.md`, then run `python firmware/tools/verify_burst.py --port COM30`. It writes the node's two-second window out as a WAV and reports the mean, the RMS and the peak — that is what tells us the wiring is right and what the microphone's DC offset and level actually are.
2. Upload `node_capture` and run `python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session1` to record the room, then ~50 real cry clips.
3. The hub's radio (Stage 2c) can then be written against a node that is known to be producing correct audio.

**Both boards are already connected:** the ESP32-S3 on COM32, the ESP32-C3 SuperMini (with the INMP441 on the breadboard) on COM30. The C3's USB is its own native USB, so *"USB CDC On Boot"* must be **Enabled** — the WeAct board entry has it on by default.

---

## 5. Change log (newest first)

| Date | Change | Files touched | Notes |
|---|---|---|---|
| 2026-10-30 | **The node sketches are in the Arduino sketchbook and build from there.** `install_sketches.py` had been run from the wrong directory (the user was in `firmware/hub_infer`, so the relative path did not resolve), and their PowerShell `python` is **3.15.2** at `C:\Python315`, which had no **pyserial** — the node tools need it. pyserial 3.5 is now installed for 3.15, so `python firmware/tools/...` works with whichever interpreter is first on PATH; the 3.11 that has PlatformIO is still the one for the hub CLI. Both sketches are installed at `~/Documents/Arduino/node_crynet` and `~/Documents/Arduino/node_capture`, and **both were compiled from the sketchbook copies** for `weact_studio_esp32c3` with zero warnings, so the IDE will find and build them. | `firmware/tools/install_sketches.py`, `SYSTEM_UPDATE.md` | For the hub from a terminal, the cleanest command is the standalone `C:\Users\HP\.platformio\penv\Scripts\platformio.exe` — the same Core 6.2.0 the IDE drives, and it needs no Python on PATH. PlatformIO was deliberately **not** installed into 3.15: Core 6.2.0 predates that release. |
| 2026-10-30 | **The PlatformIO IDE works now, and the node's real hardware is identified.** (1) The VS Code extension refused to start with *"Could not find compatible PlatformIO Core"* — caused by my own setting. The extension's check is `get-platformio.py check core --version-spec ">=6.1.6"`, and with `useBuiltinPIOCore: false` it looked for a Core in `~/.platformio/penv/Scripts` and found none. The fix: `useBuiltinPIOCore: true` (the extension's own advice) and the Core installed into the penv by PlatformIO's own bootstrap script. The penv Core is **6.2.0** — the same version the command line uses — it shares `~/.platformio`, so ESP-IDF 6.1.0 and the Xtensa toolchain were reused and **nothing was re-downloaded**; the hub builds through it in **99.3 s**, RAM 52.0 %, flash 22.0 %. (2) The user's node is a **WeAct Studio ESP32-C3 SuperMini**, and its USB is the **ESP32-C3's own native USB** (`303a:1001` on **COM30**), *not* a CH340 — so UART0 on GPIO20/21 goes nowhere and **"USB CDC On Boot" must be Enabled** or the console is silent and the port vanishes when the app starts. The Arduino core has an exact board entry for it (`weact_studio_esp32c3`) with CDC-on-boot already on; both sketches were recompiled for it with zero warnings. (3) The **capture records now carry a CRC-16** over their header and payload, and the collector drops any record that fails it — without it a single dropped byte on the USB link would shift every later sample and quietly ruin the dataset. Both stream parsers were rewritten as testable classes and checked against synthetic streams: the burst parser finds 285 of 286 fragments and flags exactly the corrupted one; the capture parser accepts 19 of 20 records and rejects exactly the corrupted one, with every surviving payload byte-exact. | `.vscode/settings.json`, `firmware/hub_infer/.vscode/settings.json`, `firmware/node/node_capture/node_capture.ino`, `firmware/node/README.md`, `firmware/tools/collect_clips.py`, `firmware/tools/verify_burst.py`, `SYSTEM_UPDATE.md` | The tools also had to stop depending on the sketch's text banner: a USB CDC port can enumerate *after* the sketch has already printed it, so the parsers resynchronise on their own magic and the banner is only informational. `verify_burst.py` now also retries the `freeze` command, because the node refuses to freeze until its two-second window is full. |
| 2026-10-30 | **Node window bug found by reading the code before the hardware did.** After a burst is sent the live window is dropped and refills, so for two seconds the newest samples are not at the start of the array — but the mean summed from index 0, averaging the stale tail with the fresh head and making the reported RMS meaningless for exactly as long as the window was invalid. The valid region is now walked **backwards from the write cursor**, which is right whether the window is full or refilling, the cursor is no longer reset, and a request arriving while the window is incomplete is refused rather than answered with a window whose order is unknown. | `firmware/node/node_crynet/node_crynet.ino`, `firmware/node/README.md` | Both sketches recompiled clean. The wire format was also validated numerically: CRC-16/CCITT-FALSE matches the standard check vector `0x29B1`, and the C frame builder and the Python parser agree on every header offset and both CRCs. |
| 2026-10-30 | **Stage 2b: the node firmware is written and compiles, and the offline GUI path is set up.** Two Arduino sketches for the ESP32-C3 — `node_crynet` (I2S capture, a 2 s rolling window, 100 ms RMS telemetry over ESP-NOW, the 64 KB burst as 286 CRC-framed fragments, a serial console) and `node_capture` (streams the microphone to the PC for in-domain data). Both build for `esp32:esp32:esp32c3` against the installed core 3.3.12 with **zero warnings**: 977,617 B / 165,972 B and 311,120 B / 18,592 B. The I2S setup follows Espressif's own recipe for this microphone — **32-bit slots** (the INMP441 puts 24 bits in a 64-bit frame, so 16-bit slots would misalign the data), `I2S_SLOT_MODE_MONO` + `I2S_STD_SLOT_LEFT`, narrowed to int16 in software by keeping the top 16 bits; the C3 is I2S hardware v2, so the left slot is chosen in hardware. The node repeats the hub's DC lesson: an exact **integer** mean, and the 100 ms RMS computed with the mean of the **whole 2 s window** removed, so the node's RMS is the same quantity the hub's front end will compute — otherwise the hub's 0.03 trigger threshold means nothing. Two host tools came with it: `verify_burst.py` (asks the node for its window over the serial console, checks every frame's CRC, writes the WAV) and `collect_clips.py` (records a session and cuts it into 5 s clips), plus `install_sketches.py` to copy the sketches into the Arduino sketchbook. Separately, the **PlatformIO IDE in VS Code** was pointed at the pip-installed Core 6.2.0 (`useBuiltinPython: false`, `useBuiltinPIOCore: false`, `customPATH` at the Python `Scripts` folder) so it drives the toolchain that is already installed and needs no network. Also corrected a claim: the build is DIO throughout (`CONFIG_ESPTOOLPY_FLASHMODE "dio"`, flash-mode byte `0x02` in both images), so the application runs in DIO — the bootloader does *not* switch it back to QIO. | `firmware/node/node_crynet/node_crynet.ino`, `firmware/node/node_capture/node_capture.ino`, `firmware/node/README.md`, `firmware/tools/verify_burst.py`, `firmware/tools/collect_clips.py`, `firmware/tools/install_sketches.py`, `firmware/README.md`, `.vscode/settings.json`, `firmware/hub_infer/.vscode/settings.json`, `SYSTEM_UPDATE.md` | One real API error was caught by compiling: IDF 5.x/6.x changed `esp_now_recv_cb_t` to take an `esp_now_recv_info_t *` first argument. **The node has still never run on the board** — the wiring, the INMP441's actual level and DC offset, and the effective sample rate are all unmeasured. |
| 2026-10-30 | **Stage 2a closed: the firmware runs on the real chip and all four probes pass.** The user's ESP32-S3-DevKitC-1 (COM32) now reports `RESULT: PASS — 4 probes, front end and model agree with the host`, with the device's quantised features matching the host reference exactly on three probes and to within 1 LSB on three values of the fourth. Measured on the chip: PSRAM 8 MB present, flash 16 MB, front-end working set 5,380 B in internal SRAM, tensor arena 262,144 B reserved / **108,328 B used**, front end **41.7 ms**, inference **101.8 ms**. Five defects were only findable by running it: the **DC-removal mean accumulated in float32** (32,000 samples of 18,000 summed to 575,726,660 instead of 576,000,000, so 8.5 counts of DC survived and the per-window standardisation turned them into a completely different feature vector — the DC-offset probe failed with a max delta of 131; the sum is now an exact `int32`); the build was at **`-Og`** because `-DCOMPILER_OPTIMIZATION_PERF` is an Arduino macro PlatformIO's ESP-IDF builder ignores (`CONFIG_COMPILER_OPTIMIZATION_PERF=y` now); the CPU ran at **160 MHz** (`CONFIG_ESP_DEFAULT_CPU_FREQ_MHZ_240=y`); the front end kept a **128 KB padded copy of the signal in PSRAM**, which is uncached external memory on the S3 and was streamed through 81 times per window (the copy is gone — each frame is built straight from the caller's int16 PCM — and the working set is 5.4 KB in internal SRAM, 135 ms → 41.7 ms); and a **combined flash image built with QIO flash mode makes the chip watchdog-reset in a loop** because the ROM cannot read this board's flash in QIO before the bootloader configures its own timing (the combined image must use DIO; the bootloader switches to QIO itself afterwards). Added `firmware/tools/flash_hub.py` (finds the board, flashes it, prints the log — nothing to download), `firmware/tools/capture_serial.py` and `firmware/README.md` documenting the build and the three offline flash routes. | `firmware/hub_infer/components/crynet_dsp/*`, `firmware/hub_infer/sdkconfig.defaults`, `firmware/hub_infer/platformio.ini`, `firmware/tools/flash_hub.py`, `firmware/tools/capture_serial.py`, `firmware/README.md`, `SYSTEM_UPDATE.md` | ESP-NN's SIMD kernels are linked in (`esp_nn_conv_s8_esp32s3`, `esp_nn_conv_s8_1x1`, `esp_nn_conv_s8_3x3_opt`). The FPU **is** used (`madd.s` in the disassembly) — an earlier check that appeared to show software float was run against the wrong compiler binary. The inference at 101.8 ms is 5 % of the 2 s window and acceptable for a triggered monitor, but the arena is still in PSRAM. |
| 2026-10-30 | **The Stage 2a firmware builds.** `firmware/hub_infer` compiles and links for the ESP32-S3: `firmware.bin` 468,800 B, RAM 52.1 %, flash 22.3 %, ESP-NN enabled, octal PSRAM at 80 MHz. Getting there meant fixing six separate things: (1) PlatformIO 6.2 installs a URL-pinned `framework-espidf` as if it were an **npm package**, so it read the wrong `package.json` and left `packages/framework-espidf` holding only a test fixture — CMake then failed with *"include could not find requested file: tools/cmake/project.cmake"*; fixed by installing the platform's own framework (**ESP-IDF 6.1.0**) by hand and dropping the `platform_packages` pin; (2) the top-level `CMakeLists.txt` **assigned** `EXTRA_COMPONENT_DIRS`, shadowing the `-DEXTRA_COMPONENT_DIRS:PATH=<src>` that PlatformIO passes for the application component, and pointed at a component instead of a directory that contains components; (3) the vendored components sat **outside** the project directory, and PlatformIO re-compiles IDF components with SCons using the *source basename* for object names — the TFLite Micro port has twelve basename collisions, so the build died with *"Multiple ways to build the same target were specified for …/circular_buffer.cc.o"*; moving the vendored components into `firmware/hub_infer/components/` makes the paths relative and distinct; (4) the port was wired to the registry copy of `esp-nn` while `esp-nn` was also vendored locally — a duplicate-component error — so `firmware/tools/patch_deps.py` now drops the registry dependency and adds `esp-nn` to the port's own requirements, keeping the build offline and pinned; (5) IDF 6.x moved `esp_flash.h` into the `spi_flash` component, changed `esp_flash_get_size()` to take a chip handle and an out-parameter, and requires an explicit capability argument on `heap_caps_calloc`; (6) the model copy is now aligned to 16 bytes by hand, because `heap_caps_malloc` only guarantees 4-byte alignment and the FlatBuffer verifier wants 16. | `firmware/hub_infer/*`, `firmware/tools/patch_deps.py`, `firmware/tools/fetch_deps.sh`, `.gitignore` | **`CONFIG_DDSP` no longer exists in IDF 6.x** and was dropped from `sdkconfig.defaults`. **The firmware has still never run on hardware** — there is no serial log yet, so the FlatBuffer alignment, the arena fit, the probe feature agreement and the latency are all still unverified. |
| 2026-10-30 | **The build finally configures — four real bugs found and fixed.** Diagnosis: PlatformIO 6.2 installs a URL-pinned `framework-espidf` by treating the archive as an npm package, so it read the wrong `package.json` out of the tree and left `packages/framework-espidf` holding only a test-fixture package — hence CMake's *"include could not find requested file: tools/cmake/project.cmake"*. Fixed by installing the platform's own framework by hand (**ESP-IDF 6.1.0**, `platform-espressif32` 8.0.0) and dropping the `platform_packages` URL pin. Also fixed: (1) the top-level `CMakeLists.txt` **assigned** `EXTRA_COMPONENT_DIRS`, shadowing the `-DEXTRA_COMPONENT_DIRS:PATH=<src>` that PlatformIO passes for the application component — it now *appends*, and points at `third_party/` (a directory that **contains** components) rather than at the component itself; (2) the vendored TFLM port was wired to the registry copy of `esp-nn` while `esp-nn` was also vendored locally — a duplicate-component error; `firmware/tools/patch_deps.py` now removes the registry dependency and adds `esp-nn` to the port's own requirements, keeping the build **offline and pinned**; (3) IDF 6.x moved `esp_flash.h` into the `spi_flash` component and changed `esp_flash_get_size()` to take a chip handle and an out-parameter; (4) `CONFIG_DDSP` no longer exists in IDF 6.x and was dropped from `sdkconfig.defaults`. | `firmware/hub_infer/CMakeLists.txt`, `firmware/hub_infer/platformio.ini`, `firmware/hub_infer/sdkconfig.defaults`, `firmware/hub_infer/src/main.c`, `firmware/hub_infer/src/CMakeLists.txt`, `firmware/tools/patch_deps.py`, `firmware/tools/fetch_deps.sh` | IDF 6.1 gives every component `freertos esp_hw_support heap log soc hal esp_rom esp_common esp_system` automatically, so the earlier `esp_heap_caps.h` ownership worry is moot. ESP-NN is worth keeping: on an S3 it is the difference between ~40 ms and ~2.3 s per convnet invoke. **The firmware has still never been compiled or run.** |---|
| 2026-10-29 | **Toolchain recovery documented.** The first ESP-IDF 5.3.2 install was killed mid-unpack by the background task's 30-minute limit, leaving a partial `framework-espidf` tree (no `tools/`, `main/`, `examples/`, `version.txt`). The partial tree was deleted and the build restarted; the 933 MB archive was already cached in `~/.platformio/.cache/downloads/`, so **no re-download was needed**. §4.3 now records the pin and a 3-step idempotent recovery. | `SYSTEM_UPDATE.md` | Restarted as background process `blewy4qwx` with a 2-hour limit. Still **NOT yet compiled**. |
| 2026-10-29 | **INT8-vs-float parity gap closed.** `research/verify_int8_parity.py` rebuilt the ICD validation fold (fold 4, 5,693 clips → 11,386 centre-cropped windows) from the cached archives with the notebook's own front end and ran the exported INT8 model and the float32 Keras model over it. **INT8 AUC 0.997926 vs float32 0.999299, ΔAUC −0.001373, decision agreement 99.956 %**; recall 0.9780 vs 0.9782 and FPR 0.0036 vs 0.0036 at the 0.95 threshold. The independently computed float AUC corroborates the Kaggle figure. Report: `research/out/verify_int8_parity.json`. | `research/verify_int8_parity.py`, `research/out/verify_int8_parity.json`, `SYSTEM_UPDATE.md` | Root cause of the NaN documented: the parity cell took a *prefix* of a label-sorted array, so the slice was 100 % cry and its AUC was undefined. The model was never affected. |
| 2026-10-29 | **Full Kaggle outputs received and staged.** `research/out/` contains the full run. Model `conv_cnn`, 137,384 bytes, SHA-256 `4aef55d8…126bc11`, threshold 0.95, input scale 0.060125612 / zp −4. `firmware/tools/check_artifact_drift.py` verifies the outputs and the staged copies against `deploy_config.json` — **PASS**. On-device probe references generated by `firmware/tools/gen_probe_refs.py` from the notebook's own front end. | `research/out/*`, `firmware/hub_infer/components/*`, `firmware/tools/*` | Val AUC 0.9994, test AUC 0.9995, cross AUC 0.9973. C/Python parity 6.905 × 10⁻⁵. **Gap:** `int8_val_auc` and `float_val_auc` are NaN in the full-run config; parity needs to be re-measured. |
| 2026-10-29 | **Stage 2a (hub inference core) scaffolded.** New ESP-IDF project with `crynet_model`, `crynet_dsp` (PSRAM-aware, reference FFT), `crynet_infer` (TFLM INT8), and the four on-device verification probes. PlatformIO espressif32 toolchain download/build in progress (`research/toolchain/pio_build.log`). | `firmware/hub_infer/*`, `firmware/tools/*` | **NOT yet compiled or run on hardware.** The user has not connected the board. TFLM port is checked out under `firmware/third_party/esp-tflite-micro` for testing but is not yet vendored/pinned; dependency wiring still needs completion. |
| 2026-10-29 | **Checkpoint-2 plan written into §4** — where to place the Kaggle `out/` (`research/out/`, now un-gitignored so the trained weights are versioned), the "firmware written from scratch" contract (§4.1: re-derived vs deliberately kept), the 4-stage plan 2a→2d (§4.2), and the toolchain status (§4.3). | `SYSTEM_UPDATE.md`, `.gitignore` | PlatformIO 6.2.0 installed via pip so the firmware can be compiled and checked here — this machine had no ESP-IDF, PlatformIO, Arduino IDE or Xtensa compiler. |
| 2026-10-29 | **CryNet repo made public** (was private) at the user's request. | GitHub repo settings | `github.com/Amazo123/CryNet` → private: false. |
| 2026-10-29 | **Added §6 "Legacy system vs. this rebuild"** — a line-by-line comparison of the abandoned system (read directly from the `legacy` remote) against the rebuild: architecture, model size (6.15 MB FP32 vs 135 KB INT8), mel bands, CMVN, dataset strategy, trigger/threshold, verification discipline. Documents what was inherited on purpose (hardware, topology, wire protocol) vs. re-decided (everything model/feature/threshold related), and states plainly that checkpoint 2 firmware is still pending. | `SYSTEM_UPDATE.md` | Answers the user's question about whether the rebuild is genuinely new or a re-skin of the failed system. Evidence: legacy `TinyCryNet` (attention + GRU, 6.15 MB), `RMS_TRIGGER_THRESHOLD 0.18`, 128 mel, no CMVN, ICD as a git submodule. |
| 2026-10-29 | **Checkpoint 1 committed and pushed to GitHub.** Created `github.com/Amazo123/CryNet` (private), committed the full checkpoint-1 deliverable as `e7be48a`, renamed the branch `master` → `main`, pushed with upstream tracking. The old repo was renamed remote `origin` → `legacy` and left as a read-only reference. | all checkpoint-1 files; `.gitignore` | `.gitignore` extended to exclude `research/_real_work/`, `research/_realfast_work/`, `*.exe`, `*.pdb`, `*.o`, `*.obj` (build scratch). Push verified: remote `main` = `e7be48a`, 34 files. |
| 2026-10-29 | **Created `SYSTEM_UPDATE.md`** — standing living status/recovery log. Imported the full checkpoint-1 state from `PROJECT_HANDOFF.md` and verified it against disk (`research/_realfast_out/*`, `metrics.json`, `deploy_config.json`, `real_fast.log`). | `SYSTEM_UPDATE.md` (new) | First entry. Establishes the update-after-every-edit protocol and the context-management rules (§0). |
| 2026-10-29 | `PROJECT_HANDOFF.md` §5 file map now points at `SYSTEM_UPDATE.md` as the living log / recovery layer. | `PROJECT_HANDOFF.md` | One-line map addition. |
| 2026-10-29 | Checkpoint 1 completed and validated (before this file existed). | `notebooks/crynet_training.ipynb`, `research/*` | Details in `PROJECT_HANDOFF.md` §4. |
| 2026-10-29 | Initial commit. | — | `997cc9b` |

---

## 6. Legacy system vs. this rebuild (what was inherited, what was re-decided)

Verified on 2026-10-29 by reading the legacy repo directly (`legacy` remote): `firmware/central_hub_s3/central_hub_s3.ino`, `dsp_mel_extractor.h`, `firmware/common/protocol.h`, `model_training/tiny_crynet_esp32.py`, `model_training/reference_pipeline.py`, `model_artifacts/README.md`, and the git tree.

### Inherited on purpose (hardware + topology — the user's real boards)
Same 3× ESP32-C3 cot nodes → ESP32-S3 hub → ESP32-C3 wearable; same ESP-NOW telemetry/audio-fragment protocol; same 2 s @ 16 kHz window with 512-pt FFT and hop 400; same `wearable_alert_packet_t` BLE format; same TFT/GATT UI. Nothing here was re-litigated, because the hardware is fixed and the wire format already exists.

### Re-decided from scratch (this is where the new work is)

| Aspect | Legacy system | This rebuild |
|---|---|---|
| Architecture | `TinyCryNet` — 5 × BSConvU blocks + **CCA channel attention** + **GRU** temporal aggregator (PyTorch → ONNX) | 3 plain CNN variants, **no attention, no RNN**, chosen so every op has a TFLite Micro kernel (asserted at export) |
| Model size | `model_data.h` = **6,157,199 bytes (6.15 MB)**, FP32 in flash; needed a bespoke **6.0 MB `app0` partition** | **135 KB INT8** — 45× smaller, fits comfortably in stock partitions |
| Input | `[1,1,81,128]` — 128 mel bands | `[1,81,64,1]` — 64 mel bands |
| Mel filter | `htk=True`, `fmin=0` | librosa **slaney**, `fmin=20 Hz` |
| Level handling | `power_to_db(top_db=80)` — **absolute dB, no normalisation** ⇒ the model was level-dependent | **per-window CMVN** ⇒ level-invariant (ICD cries sit at RMS 0.006 vs negatives at 0.3–0.46) |
| Dataset | ICD pulled in as a **git submodule** of an academic baseline repo (`ICD_MMSP`, tree mode 160000); one corpus, no audio-level verification, no external negatives | every corpus **profiled at audio level**; ICD as primary **combined with** cry4 + ESC-50 + Snoring; contaminated corpora rejected; negatives deliberately include cat meows, speech, snoring |
| Trigger | hard-coded `RMS_TRIGGER_THRESHOLD 0.18` + `CONFIRMATION_PROB 0.65` | trigger ~0.03 + silence gate 0.0015 + **threshold calibrated on data** (0.23 at ≥ 95 % recall) with the whole recall/FPR curve reported |
| Training | 35-epoch SpeechBrain/PyTorch run, artifacts in a 105 MB LFS tarball; no recorded per-class false-alarm analysis | Keras/TFLite notebook, **hard-example mining**, **per-category FPR breakdown**, cross-corpus evaluation on corpora never trained on |
| Verification | `verify_dsp_parity.py` existed as a simulation script | **automated** C↔Python parity (max deviation 7.06 × 10⁻⁵), INT8↔float parity (AUC delta −0.00007), TFLM kernel assertion at export, manifest↔archive 1:1 corpus check |
| Claimed latency | "≈ 40 ms" (never measured on the board) | **measured on the chip**: front end **41.7 ms**, inference **101.8 ms** per 2 s window, CPU 240 MHz |

### Why the legacy system failed — and what that means
The legacy repo's **last commit** is `fix(firmware): resolve false cry detection, packet loss, and full-screen landscape display` — i.e. the system was still being debugged on the hardware when it was abandoned, and the failures it was chasing were *system-level* (ESP-NOW packet loss, TFT layout, false triggers), not dataset-level. With `RMS_TRIGGER_THRESHOLD 0.18`, a soft cry (ICD cries sit at RMS ≈ 0.006) **never reached the classifier at all**, so the old model was never fairly tested on the real hardware. The rebuild therefore changed the model, the features, the trigger and the threshold — but the *dataset* was kept, because the evidence points at the firmware and the trigger logic, not at ICD.

### What is still not new / not proven yet
- **Checkpoint 2 (firmware) is half written.** The hub's inference core (Stage 2a) is new, verified on the real chip, and committed. The node firmware (Stage 2b) is new and compiles but has never run. The hub's radio, display and BLE (Stage 2c) and the wearable (Stage 2d) do not exist yet. The "brand new working system" is still half-built: the model half is new and validated, the firmware half is in progress.
- **No in-domain data.** The model has never heard the user's INMP441, room or gain. ~50 self-recorded clips remain the single biggest accuracy win, and they are also the honest test of whether the new system actually works in the real room.

---

## 7. Quick reference

**Run locally**
```bash
pip install numpy librosa soundfile soxr scipy scikit-learn tensorflow huggingface_hub
cd research && python make_stub.py && bash run_stub.sh     # synthetic smoke test
bash run_real_fast.sh                                       # real corpus, subsampled, CPU
pip install ziglang && python test_c_parity.py              # C <-> Python parity
```

**Notebook env switches**
`CRYNET_FAST=1` (subsample + 3 epochs) · `CRYNET_OFFLINE=1` · `CRYNET_KINDS=conv_cnn,sep_cnn,temporal_cnn` · `CRYNET_EPOCHS=35` · `CRYNET_MINING_ROUNDS=1` · `CRYNET_CACHE` / `CRYNET_WORK` / `CRYNET_OUT`.

**Caches**
HF archives at `research/_cache/audio/positive.zip`, `.../audio/negative.zip`, `research/_cache/metadata/all28479.csv`. Kaggle archives at `research/_cache/<key>__<owner>__<slug>.zip`.

**Verified local versions**
Python 3.11.9 · TensorFlow 2.21.0 (CPU) · librosa 0.11.0 · soundfile 0.14.0 · numpy 2.4.6 · scipy 1.17.1 · ziglang 21.1.0 (C compiler for the parity test; no gcc installed).
