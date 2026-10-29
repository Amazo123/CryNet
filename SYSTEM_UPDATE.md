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

**Checkpoint 1 = DONE and validated. Checkpoint 2 (ESP32-S3 firmware) = NOT STARTED.**

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

### Current numbers (indicative — small local run, NOT the final Kaggle run)
3 epochs on an 8,490-window subsample. The real Kaggle run is 74 k windows / 35 epochs / 3 models.

| Split | AUC | F1 | Recall | FPR |
|---|---|---|---|---|
| ICD val (fold 4) | 0.9807 | 0.9145 | 0.9504 | 0.1240 |
| ICD test (fold 5) | 0.9839 | 0.9131 | 0.9534 | 0.1058 |
| cross-corpus (cry4+ESC50+snore, unseen) | 0.9887 | 0.9413 | 0.9544 | 0.0789 |

- Selected variant: **`conv_cnn`** (122,770 params) → **135.1 KB INT8** (`research/_realfast_out/crynet_int8.tflite`, SHA-256 `d6d1dc4f…485ef0`).
- `sep_cnn` was not trained in the fast run; `temporal_cnn` underperformed (val AUC 0.695) and was dropped.
- **Calibrated alarm threshold = 0.23** (largest threshold reaching ≥ 95 % recall on the ICD val fold). At 0.50 it would be recall 91.9 % / FPR 4.2 %.
- Input quantisation: scale **0.071706**, zero_point **−37**. Output: `[1,2]` int8, scale 0.00390625, zp −128, classes `["no_cry","cry"]`.
- Quantisation: input scale 0.0717, zero_point −37. Tensor arena hint **120 KB** (put in PSRAM if it does not fit in internal SRAM).
- Unseen-cry recall: cry4 `needs` 98.8 % / `physical_pain` 96.9 % / `scared` 90.5 % / `burping` 82.0 %; ESC-50 `crying_baby` 85 %.
- Worst false-alarm categories: `coughing` 57 % · `car_horn` 33 % · `church_bells` 33 % · `siren` 25 % · `washing_machine` 23 %.
- Mining effect on the stand-in run: cross-corpus FPR **0.109 → 0.004**.

### Artifacts on disk
`research/_realfast_out/` — full export set from the real-corpus fast run: `crynet_int8.tflite`, `crynet_float.tflite`, `crynet.keras`, `model_data.h`, `crynet_tables.h`, `dsp_crynet.c/.h`, `crynet_infer_example.c`, `deploy_config.json`, `metrics.json`, `c_parity.json`.
`research/out/` is **empty** — the real Kaggle run has not happened.
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

1. **Port `dsp_crynet.c` to ESP-IDF.** Replace the reference radix-2 FFT with ESP-DSP `dsps_fft2r` + `dsps_cmplx_mag` (~10× faster). Copy `crynet_tables.h` + `model_data.h` into the firmware tree.
2. **Wire TFLite Micro.** INT8 input `[1, 81, 64, 1]`; `MicroMutableOpResolver` with `AddConv2D`, `AddDepthwiseConv2D`, `AddMaxPool2D`, `AddMean`, `AddFullyConnected`, `AddSoftmax`; arena in PSRAM if needed. `crynet_infer_example.c` is the template.
3. **Fix the hub trigger threshold:** drop the RMS ≥ 0.18 audio-pull trigger to ~0.03 so soft cries reach the model; add the 0.0015 silence gate; let the calibrated 0.23 threshold do the discriminating.
4. **Forward the model output** to the existing BLE packet: `alert_type = 0x01` when `P(cry) >= 0.23`, `confidence_pct = round(P(cry) * 100)`.
5. **Measure** inference latency and arena usage on the real board; log both.
6. **Collect ~50 in-domain clips**, add as a custom corpus to the notebook, retrain.

*User-side action in parallel:* run `notebooks/crynet_training.ipynb` on Kaggle (GPU T4, Internet On, ~40 min) and download `out/`.

---

## 5. Change log (newest first)

| Date | Change | Files touched | Notes |
|---|---|---|---|
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
