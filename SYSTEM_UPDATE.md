# CryNet — SYSTEM_UPDATE.md (living status log)

> **This file is the recovery layer.** It is rewritten/appended by the agent **after every project update or edit** (code, notebook, config, decision, or a completed run). If the chat dies, is compacted into garbage, or hits "400 Context Limit Exceeded", a fresh chat reads this file first and is immediately back up to speed.
>
> **Repo:** `C:\Users\HP\.t3\projects\fp-2` (branch `master`)
> **Deep briefing (static, rarely changes):** `PROJECT_HANDOFF.md`
> **Last updated:** 2026-10-29

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

### 0.1 Live background work (as of 2026-10-29, ~19:30)

| What | Where | How to check |
|---|---|---|
| PlatformIO ESP32-S3 build of `firmware/hub_infer` | background process, log at `research/toolchain/pio_build.log` | `tail -40 research/toolchain/pio_build.log`; if the process is gone, re-run `cd firmware/hub_infer && python -m platformio run` |
| Toolchain install | `~/.platformio/packages/` (riscv32 done, xtensa-esp-elf in progress) | `ls ~/.platformio/packages/` |

**A background build survives `/compact` and even a lost session** — it writes to the log file on disk, not to the chat. Compaction only rewrites conversation history.

**What is NOT yet done — do not claim otherwise:**
- The firmware has **never been compiled**. No build result exists yet.
- The firmware has **never run on hardware**. The user has not connected the S3.
- `firmware/` and `research/out/` are **not yet committed or pushed** (only `SYSTEM_UPDATE.md` was updated at the time of writing).

**Next concrete steps after the build finishes:**
1. Fix any compile errors (likely areas: the `esp_heap_caps.h` owning component, `tflite::MicroInterpreter` API details, the `PRIV_REQUIRES esp-tflite-micro` component name).
2. Once it builds, ask the user to flash the S3 and read the serial log — the app prints per-probe feature deltas, P(cry), front-end and inference latency, and arena usage.
3. Only then move to Stage 2b (node firmware).

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

### Artifacts on disk
`research/out/` — **the authoritative full-run artifacts**: `crynet_int8.tflite`, `crynet_float.tflite`, `crynet.keras`, `model_data.h`, `crynet_tables.h`, `dsp_crynet.c/.h`, `crynet_infer_example.c`, `deploy_config.json`, `metrics.json`, `c_parity.json`.
`research/_realfast_out/` — the earlier subsample run, kept for comparison.
Logs: `research/real_fast.log`, `research/stub_run.log`.

### Git state and remotes
Local branch `main`, tracking `crynet/main`. Latest commit `e7be48a` = checkpoint 1 (all of it now committed — nothing uncommitted).

| Remote | Points at | Purpose |
|---|---|---|
| `crynet` | `github.com/Amazo123/CryNet.git` | **The live project.** Every change is committed here and pushed. Created 2026-10-29, **public** since 2026-10-29. |
| `legacy` | `github.com/Amazo123/Multi-Node-Infant-Cry-Detection.git` | The **old** project (Arduino firmware, BOM, wiring guides, old `model_data.h`). Read-only reference — do not push to it. Its hub `.ino`, `firmware/common/protocol.h`, `firmware/central_hub_s3/pins.h` and `dsp_mel_extractor.cpp` are the starting point for checkpoint 2. |

**Backup rule:** after every meaningful change → update this file → `git add -A && git commit && git push crynet main`. Never commit `research/_cache/` (5.5 GB of corpora) or the `_*_work/` scratch dirs; they are gitignored and the notebook re-downloads the corpora itself.

**What is *not* in GitHub:** the raw datasets (5.5 GB — re-downloaded automatically by the notebook) and the `_work`/`_parity` build scratch. Everything that is source, model, exported artifact, doc or log **is** in the repo.

### Open risks
1. The full Kaggle run has not happened — every number above is a floor, not final.
2. `coughing` is the top confuser; if it survives mining, add the FSDKaggle2018 cough set.
3. **No in-domain data** — the model has never heard the user's INMP441, room or gain. ~50 self-recorded clips (cries + room noise + speech + TV) is the single biggest remaining accuracy win.
4. TFLM latency unmeasured. Estimate 100–300 ms per 2 s window on a 240 MHz LX7; must be measured on the real board.
5. Tensor arena size is a hint only — verify `AllocateTensors()` succeeds.
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

**Stage 2c — hub system.** ESP-NOW receive, RMS trigger, audio assembly across 320 fragments, inference, TFT display, BLE GATT server, alert packet.

**Stage 2d — wearable (ESP32-C3).** BLE notification client, SSD1306 OLED, DRV2605L haptic.

### 4.3 Toolchain status
This machine originally had **no ESP-IDF, no PlatformIO, no Arduino IDE and no Xtensa compiler**. PlatformIO **6.2.0 is now installed** (`research/toolchain/pio_install.log`) so the firmware can actually be **compiled and checked** here rather than written blind; the first `pio run` for `esp32s3` downloads the Xtensa toolchain. Flashing still requires the user's physical boards.

### 4.4 User-side action in parallel
**Done:** user ran the full Kaggle notebook and dropped `out/` into `research/out/`. Next user-side action is to connect the ESP32-S3 for the Stage 2a on-device verification once the build passes.

---

## 5. Change log (newest first)

| Date | Change | Files touched | Notes |
|---|---|---|---|
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
| Claimed latency | "≈ 40 ms" (never measured on the board) | unmeasured — to be measured in checkpoint 2 (est. 100–300 ms) |

### Why the legacy system failed — and what that means
The legacy repo's **last commit** is `fix(firmware): resolve false cry detection, packet loss, and full-screen landscape display` — i.e. the system was still being debugged on the hardware when it was abandoned, and the failures it was chasing were *system-level* (ESP-NOW packet loss, TFT layout, false triggers), not dataset-level. With `RMS_TRIGGER_THRESHOLD 0.18`, a soft cry (ICD cries sit at RMS ≈ 0.006) **never reached the classifier at all**, so the old model was never fairly tested on the real hardware. The rebuild therefore changed the model, the features, the trigger and the threshold — but the *dataset* was kept, because the evidence points at the firmware and the trigger logic, not at ICD.

### What is still not new / not proven yet
- **Checkpoint 2 (firmware) has not been written.** The deployed code is still the legacy Arduino firmware. The "brand new working system" is currently half-built: the model half is new and validated, the firmware half is pending.
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
