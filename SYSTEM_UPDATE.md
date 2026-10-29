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

### Git state
Branch `master`, one commit `997cc9b Initial commit`. **All checkpoint-1 work is uncommitted** (modified `README.md`; untracked `.gitignore`, `PROJECT_HANDOFF.md`, `notebooks/`, `research/`).

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
| 2026-10-29 | **Created `SYSTEM_UPDATE.md`** — standing living status/recovery log. Imported the full checkpoint-1 state from `PROJECT_HANDOFF.md` and verified it against disk (`research/_realfast_out/*`, `metrics.json`, `deploy_config.json`, `real_fast.log`). | `SYSTEM_UPDATE.md` (new) | First entry. Establishes the update-after-every-edit protocol and the context-management rules (§0). |
| 2026-10-29 | `PROJECT_HANDOFF.md` §5 file map now points at `SYSTEM_UPDATE.md` as the living log / recovery layer. | `PROJECT_HANDOFF.md` | One-line map addition. |
| 2026-10-29 | Checkpoint 1 completed and validated (before this file existed). | `notebooks/crynet_training.ipynb`, `research/*` | Details in `PROJECT_HANDOFF.md` §4. |
| 2026-10-29 | Initial commit. | — | `997cc9b` |

---

## 6. Quick reference

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
