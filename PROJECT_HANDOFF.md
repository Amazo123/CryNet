# CryNet — project handoff (paste this into a new chat)

> **Purpose of this document.** It is a complete, self-contained briefing for a fresh chat that has no memory of this project. Everything needed to continue — hardware, decisions, dataset research, the exact signal contract, validation evidence, file map, how to run, known risks, and the next checkpoint — is below.
>
> **Repo:** `C:\Users\HP\.t3\projects\fp-2` (git, branch `master`, only commit is `997cc9b Initial commit`; **checkpoint-1 work is uncommitted**).
>
> **Status at handoff:** checkpoint 1 complete and validated. Checkpoint 2 (ESP32-S3 firmware) not started.

---

## 1. The project

A **multi-node infant cry monitor** for multi-crib environments (NICU, maternity ward, daycare, twin nursery).

### Hardware (fixed — this is a final-year project with real boards)

| Subsystem | Board | Role |
|---|---|---|
| **Cot nodes ×3** | ESP32-C3 SuperMini + INMP441 MEMS mic | I2S capture at 16 kHz, DC-coupled RMS telemetry over ESP-NOW, on-demand 64 KB audio burst back to the hub |
| **Central hub** | **ESP32-S3-DevKitC-1** (dual-core Xtensa LX7 @ 240 MHz, 512 KB SRAM, **8 MB octal PSRAM**) | ESP-NOW receiver, DSP front end, **TFLite Micro inference**, TFT display (ILI9341 320×240), BLE GATT server |
| **Wearable** | ESP32-C3 SuperMini + SSD1306 OLED + DRV2605L haptic | Caregiver alert via BLE notification |

**The hub is the target device for everything below.** It has 512 KB internal SRAM and 8 MB PSRAM; the model must fit in flash and the tensor arena in RAM/PSRAM.

### Why the rebuild happened

The previous build (documented in the original 2.0.0 spec attached at the start of the project) **did not work after the firmware was uploaded** — the project stalled after flashing to the S3 and one C3 node. The decision was to restart **from model training**, discarding the old model's mechanism but keeping the hardware and the system architecture (3 cot nodes → hub → wearable).

### The three architectural decisions (made with the user, now frozen)

1. **Binary cry / no-cry head.** Not cry-cause classification. The existing BLE alert packet (`wearable_alert_packet_t`: `cot_id`, `alert_type` 0x01 = genuine cry, `confidence_pct`, `event_id`, `checksum`) only supports a binary decision.
2. **Label policy = "any cry present".** A 2-second window counts as positive if it contains *any* real cry (≈ ≥ 3 active frames), not only sustained crying. Rationale: the hub fires on an RMS spike and then grabs a 2 s buffer that usually begins just before the cry.
3. **Training runs on Kaggle GPU** (the user runs it); the notebook is validated locally first by the agent.

---

## 2. The dataset research (this was the core of checkpoint 1)

The approach was **not** to trust dataset descriptions. Every candidate was downloaded and profiled at the audio level: sample rate, duration, RMS, autocorrelation F0, spectral centroid, spectral flatness — enough to separate a real cry from a synthetic one or from renamed filler.

### Used

| Corpus | Role | Evidence |
|---|---|---|
| **ICD — `hoyyu1/infant-cry-detection`** (Hugging Face) | **PRIMARY** | 28,478 clips, *all* 16 kHz mono / 5.00 s, 5 pre-assigned balanced folds. Cries: EnesBabyCries 5,026 · CryCeleb2023 4,552 · iFLYTEK 2020 "xunfei" 3,752. Negatives: VoxCeleb speech 4,963 · DASEE domestic 4,506 · human non-speech 2,076 · **cat meows** 1,953 · silence 1,650. Manifest ↔ archives verified 1:1 (13,330 positives, 15,148 negatives, zero missing, zero extra). |
| **Baby Cry 4-class — `karimeletriby/infant-cry-classification-4-classes`** (Kaggle) | cry diversity + cross-corpus test | 4,871 real cries, 16 kHz mono WAV, −23 LUFS normalised, high-pass 50 Hz, VAD-trimmed, **cross-dataset deduplicated** (1,297 near-dupes removed). Classes: `needs` 3,103 / `physical_pain` 774 / `scared` 684 / `burping` 310. |
| **ESC-50** (Kaggle mirror `akaliutau/esc-50`) | negatives + cross-corpus test | 2,000 clips / 50 classes @ 44.1 kHz. 1,960 used as negatives (`crying_baby` excluded); the **40 `crying_baby` clips are held out entirely** as an unseen cross-domain cry test. |
| **Snoring — `tareqkhanemu/snoring`** (Kaggle) | hard negatives | 1,000 adult-vocal recordings — the confusion class a nursery monitor hits constantly. |

### Rejected, with reasons

* **`mennaahmed23/baby-cry*` (five Kaggle mirrors) — CONTAMINATED.** Its `silence` class is not silence (measured RMS 0.22, peak 1.0, a constant 1225 Hz component); its `noise` class is renamed ESC-50 files (e.g. `1-100032-A.ogg`); hundreds of files are synthetic `generated3_*` derivatives. Training on it teaches dataset artifacts.
* **`rahult25/five-class-infant-cry-audio-datase`** — same base corpus plus pitch-shifted derivatives (`uncomfortable_10 … _72`).
* **ICSD (`QingyuLiu1/ICSD`)** — the best-curated corpus in existence (3,641 weakly + 807 real strongly-labelled clips with event timestamps) but **gated on Hugging Face**, needs a token and manual approval.
* **`AxonData/infant-cry-detection`** — 50 h of expertly labelled domestic recordings, but the Kaggle upload is an 18-file teaser and the full set is paid.
* **Baby Chillanto (INAOE)** — 2,267 high-quality 16 kHz newborn cries, but no clean public mirror (request-only from the lab).
* **AudioSet / FSD50K** — need YouTube extraction or a ~30 GB pull for a handful of clips ICD already covers.
* **DonateACry** — used *only* indirectly, because it is already merged (and deduplicated) inside the Baby Cry 4-class corpus. Raw DonateACry is 8 kHz with a badly skewed class distribution (382 of 457 files are `hungry`).

### Two findings that shaped the design

1. **Level asymmetry.** ICD cries sit at **RMS ≈ 0.006** while ICD negatives sit at **RMS 0.3–0.46**. A model could learn "quiet = cry" and then collapse in the real room. → the front end applies **per-window standardisation (CMVN)**, making the representation level-invariant. (Also why the silence gate had to be lowered to 0.0015.)
2. **The old trigger threshold was a real bug.** The previous hub fired an audio pull at **RMS ≥ 0.18**, so a *soft* cry never reached any classifier at all. The new design feeds the model anything above ~0.03 RMS and lets it reject false triggers — rejecting speech, cat meows and household noise is exactly what it is trained for. **This requires a firmware change in checkpoint 2.**

---

## 3. Technical design

### Signal contract (frozen — the firmware, the C code and the weights all depend on it)

```
int16_t pcm[32000]                2.000 s @ 16 kHz mono
  -> float x = pcm / 32768.0
  -> subtract mean                DC removal (INMP441 sits at ~+18000 counts)
  -> zero-pad 256 front / 512 rear
  -> 81 frames, 512-pt symmetric Hann window, hop 400
  -> |rfft|^2                     257 bins
  -> 64 Mel bands                 librosa slaney mel, 20 Hz – 8 kHz (497 non-zero weights)
  -> 10*log10(max(P, 1e-10))      floored at −80 dB
  -> per-window standardisation   (mean 0, std 1)
  -> int8 quantise                q = round(v/scale) + zero_point
  -> TFLite Micro int8 inference  -> [P(no_cry), P(cry)]
```

| Constant | Value | Constant | Value |
|---|---|---|---|
| `SR` | 16000 Hz | `N_FFT` | 512 |
| `WIN_SEC` | 2.0 s | `HOP` | 400 |
| `N_SAMPLES` | 32000 | `N_MELS` | 64 |
| `N_FRAMES` | 81 | `FMIN/FMAX` | 20 / 8000 Hz |
| `CENTER_PAD` | 256 | `TAIL_PAD` | 512 |
| `DB_FLOOR` | −80 dB | `LOG_EPS` | 1e-10 |
| `CMVN` | True | `SILENCE_RMS_GATE` | 0.0015 (~−56 dBFS) |
| `TARGET_RECALL` | 0.95 | `SEED` | 1337 |

Mel-band weights are **exported from Python into C** (`crynet_tables.h`, sparse: start/end/offset + 497 floats), so the firmware physically cannot drift from the model.

### Dataset assembly

* 2 s windows; clips longer than 2 s are cropped (random for train, centre for eval); shorter clips are zero-padded.
* **Splits are by source clip, never by window** — no recording can appear in both train and test.
  * ICD: folds 1–3 → train, fold 4 → val, fold 5 → test (the corpus ships its own folds).
  * cry4: 70 % train / 30 % cross-corpus test.
  * ESC-50: 75 % train / 25 % cross-corpus test, **plus all 40 `crying_baby` clips held out**.
  * Snoring: 75 % train / 25 % cross-corpus test.
* Exact-duplicate windows are removed by MD5 of the feature bytes.
* Augmentation (train only, waveform domain): random gain (−18…+6 dB) · real non-cry noise mixed at SNR 3–25 dB drawn from the ICD negative pool · optional room impulse response (ICD ships `rir.zip`, applied with p = 0.35) · SpecAugment in the feature domain (2 frequency bands ≤ 8 bins, 2 time spans ≤ 12 frames, drawn per sample).

### Models (all TFLite-Micro friendly — no attention, no RNN)

| Name | Params | Shape |
|---|---|---|
| `conv_cnn` | 122,770 | 5 × [Conv2D + BN + ReLU + MaxPool2D] → GAP → Dense(64) → Dropout(0.3) → Dense(2) |
| `sep_cnn` | 29,839 | 4 × [DepthwiseConv2D + pointwise Conv2D + BN + ReLU + MaxPool2D] → GAP → Dense(64) → Dropout → Dense(2) |
| `temporal_cnn` | 65,154 | Conv2D over time (Mel bins as channels) + MaxPool((2,1)) → GAP → Dense(64) → Dropout → Dense(2) |

`bsc_cnn` exists in the code as an optional fourth candidate. The best variant is chosen on **validation AUC**.

### Hard-example mining (added after the first real-data run)

After the main training, the notebook scores its own training set, takes the **600 most cry-like non-cry windows** and the **600 least cry-like cry windows**, duplicates them, and fine-tunes for 6 epochs at LR 3e-4 with early stopping. Only training rows are mined, so the held-out folds stay honest.

*Motivation (measured):* `coughing` produced a **57 % false-alarm rate** (car horn / church bells ~33 %) — acoustically a cough is a vocal expulsion, like a cry.

### Threshold calibration

The alarm threshold is **not** hard-coded to 0.65. The notebook sweeps thresholds on the ICD validation fold and picks the largest threshold that still reaches ≥ 95 % recall on the cry class, then reports the whole recall/FPR curve so the trade-off is visible. (On the small real-data run this chose 0.23 → recall 95.7 %, FPR 13.6 %; at 0.50 it would be recall 91.9 %, FPR 4.2 %.)

### INT8 quantization

Full INT8 post-training quantization (`TFLITE_BUILTINS_INT8`, int8 input and output) with a 512-window representative dataset drawn from the training set. The notebook then runs the **actual int8 TFLite interpreter** over the validation set and reports float-vs-int8 parity, and asserts every operator in the model has a TFLite Micro kernel.

---

## 4. Validation evidence

| Check | Result |
|---|---|
| Whole notebook end-to-end (data → features → training → mining → INT8 → export) | ✅ all 24 cells, on synthetic stand-in archives |
| Same pipeline on the **real** corpus | ✅ cells 1–15 on all 28,478 real clips (feature extraction 128 s for 56,956 windows) |
| **C front end vs. the Python training front end** | ✅ compiled and compared on 4 probes (sine+harmonic, noise, DC-offset cry with the INMP441 bias, silence): **max deviation 7.06 × 10⁻⁵**, mean 2.8 × 10⁻⁶ |
| Every op has a TFLite Micro kernel | ✅ `CONV_2D`, `DEPTHWISE_CONV_2D`, `MAX_POOL_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX` — asserted at export time, recorded in `deploy_config.json` |
| INT8 vs float32 | ✅ AUC delta **−0.00007**, 99.70 % decision agreement |
| Corpus integrity | ✅ ICD manifest ↔ archives exact 1:1; all 16 kHz mono / 5.00 s |
| Exported model size | ✅ **135 KB INT8** (122,770 params) |
| `nbformat.validate()` | ✅ notebook is valid |

### Measured on the real corpus

From a deliberately small local CPU run — **3 epochs on an 8,490-window subsample** (the full Kaggle run is 74 k windows / 35 epochs / 3 models), so these are a **floor, not final numbers**:

| Split | AUC | F1 | Recall | FPR |
|---|---|---|---|---|
| ICD val (fold 4) | 0.9807 | 0.9145 | 0.9504 | 0.1240 |
| ICD test (fold 5) | 0.9839 | 0.9131 | 0.9534 | 0.1058 |
| **cross-corpus** (cry4 + ESC-50 + snoring — never trained on) | **0.9887** | 0.9413 | 0.9544 | 0.0789 |

Cry recall on the **unseen** cry4 corpus: `needs` 98.8 % · `physical_pain` 96.9 % · `scared` 90.5 % · `burping` 82.0 %. On ESC-50's `crying_baby` (also unseen): 85 % recall.

Per-category false-alarm rates (worst): `coughing` 57 % · `car_horn` 33 % · `church_bells` 33 % · `siren` 25 % · `washing_machine` 23 %.

Mining effect measured on the stand-in run: cross-corpus FPR **0.109 → 0.004**.

### Bugs found and fixed during validation

All of these would have surfaced **on the device, not in training**:

1. `tf.py_function` erased the batch shape → Keras raised `as_list() is not defined on an unknown TensorShape`. Fixed by rewriting SpecAugment in pure TF ops (also faster on GPU).
2. The TFLite converter rejected the representative dataset: it must yield a **list** of arrays, not a bare array.
3. The front-end output tensor was missing its channel axis → `X[i:i+1]` instead of `X[i:i+1, :, :, None]`.
4. A runaway silence gate (0.0035) would have discarded the quiet ICD cries (RMS 0.006) → lowered to 0.0015.
5. The augmentation loop iterated over *windows* instead of *clips*, doubling the training set and memory → fixed.
6. Holding every intermediate array caused a **native segfault** during `model.fit` on Windows (17 GB box, 10.6 GB free) → added explicit `del` + `gc.collect()` and a bounded 32,768 shuffle buffer.
7. `GlobalAveragePooling2D` lowers to `MEAN`; TFLM registers it in `kernels/reduce.cc` (**not** `mean.cc`, so a naive filename search wrongly suggests it is unsupported) → confirmed and now asserted automatically.

---

## 5. File map

```
C:\Users\HP\.t3\projects\fp-2\
├── README.md                    ← project overview, dataset decision, contract
├── PROJECT_HANDOFF.md           ← static deep briefing (paste into a new chat)
├── SYSTEM_UPDATE.md             ← LIVING status log, updated after every edit
                                 ← recovery layer if the chat/context is lost
├── .gitignore
├── notebooks/
│   └── crynet_training.ipynb    ← THE DELIVERABLE (24 cells, Kaggle-ready)
└── research/                    ← the investigation; not needed to run the notebook
    ├── README.md
    ├── build_notebook.py        ← generates the .ipynb (patch this, then rebuild)
    ├── run_notebook_local.py    ← executes the notebook cell-by-cell locally
    ├── run_stub.sh              ← end-to-end test on synthetic stand-in archives
    ├── run_real.sh              ← full-corpus local run (CPU; slow)
    ├── run_real_fast.sh         ← full-corpus, subsampled, CPU-friendly
    ├── make_stub.py             ← builds the stand-in archives
    ├── test_c_parity.py         ← compiles dsp_crynet.c, compares against Python
    ├── scan_kaggle.py           ← Kaggle dataset search/metadata API (no auth)
    ├── inspect_zips.py          ← archive structure without extracting
    ├── analyze_audio.py         ← audio forensics (SR, duration, F0, flatness)
    ├── _cache/                  ← 5.5 GB of downloaded corpora (gitignored)
    └── _stub_out/, _realfast_out/  ← artifacts from local runs (gitignored)
```

**The notebook is generated.** To change it, edit `research/build_notebook.py` and run `python build_notebook.py` — do not hand-edit the `.ipynb`.

### Artifacts the notebook writes to `out/`

| File | Contents |
|---|---|
| `crynet_int8.tflite` | the deployable model |
| `crynet_float.tflite` | float32 reference |
| `crynet.keras` | the trained Keras model, so INT8 export can be repeated without retraining |
| `model_data.h` | the model as a C byte array (`crynet_model[]`, `crynet_model_len`) |
| `crynet_tables.h` | Mel filterbank (start/end/offset + 497 weights), Hann window, all constants, quantisation scales, threshold, silence gate |
| `dsp_crynet.c` / `.h` | portable C99 front end — `crynet_log_mel()`, `crynet_quantise()`, `crynet_dequantise()`, `crynet_window_rms()` |
| `crynet_infer_example.c` | TFLite Micro glue: PCM → log-Mel → quantise → `Invoke()` → `P(cry)` → `crynet_is_cry()` |
| `deploy_config.json` | input shape, quantisation params, operator list, TFLM kernel check, threshold, metrics, model SHA-256 |
| `metrics.json` | per-variant AUC / F1 / recall |
| `c_parity.json` | measured C-vs-Python front-end deviation |

---

## 6. How to run

### Kaggle (the real run)

1. New notebook → *Add Input* → attach nothing (everything downloads) or pre-attach for speed.
2. Accelerator **GPU T4**, Internet **On**.
3. Upload `notebooks/crynet_training.ipynb` → *Run All*.
4. Expected: ~10 min download (4.6 GB, resumable via `huggingface_hub`) + ~5 min feature extraction + ~20–40 min training for the 3 variants + mining + INT8 export. Artifacts land in `/kaggle/working/out/`.

### Locally

```bash
pip install numpy librosa soundfile soxr scipy scikit-learn tensorflow huggingface_hub
# end-to-end smoke test on synthetic stand-ins (minutes)
cd research && python make_stub.py && bash run_stub.sh
# full corpus, subsampled, CPU (tens of minutes)
bash run_real_fast.sh
# C <-> Python parity
pip install ziglang && python test_c_parity.py
```

### Environment switches (env vars read by the notebook)

| Variable | Effect |
|---|---|
| `CRYNET_FAST=1` | subsample the corpora and train 3 epochs — smoke test |
| `CRYNET_OFFLINE=1` | never download; require the archives to already be in the cache |
| `CRYNET_KINDS` | which variants to train, e.g. `temporal_cnn` (default `conv_cnn,sep_cnn,temporal_cnn`) |
| `CRYNET_EPOCHS` | training epochs (default 35) |
| `CRYNET_MINING_ROUNDS` | hard-example mining rounds (default 1; 0 disables) |
| `CRYNET_CACHE` / `CRYNET_WORK` / `CRYNET_OUT` | cache, scratch and output directories |

The HF archives are cached at `CRYNET_CACHE/audio/positive.zip`, `.../audio/negative.zip`, `.../metadata/all28479.csv`; the Kaggle ones at `CRYNET_CACHE/<key>__<owner>__<slug>.zip`. A file attached under `/kaggle/input` is used as-is.

### Verified versions (local Windows box)

Python 3.11.9 · TensorFlow 2.21.0 (CPU-only; no GPU on Windows TF ≥ 2.11) · librosa 0.11.0 · soundfile 0.14.0 · numpy 2.4.6 · scipy 1.17.1 · scikit-learn · ziglang 21.1.0 (used as a C compiler for the parity test, since no gcc is installed).

---

## 7. Known risks and open questions

1. **The full Kaggle run has not happened yet.** Every number above comes from a small local run. Expect better, but verify.
2. **`coughing` remains the top confuser** (57 % FPR before mining). If it survives mining, the next lever is a dedicated cough corpus (the FSDKaggle2018 cough set would add several hundred clips).
3. **No in-domain data.** The model has never heard your INMP441, your room or your gain. **Recording ~50 real clips from your own hardware (cries + room noise + speech + TV) and adding them as a custom corpus is the single biggest remaining accuracy win.**
4. **TFLM latency is unmeasured.** Estimate: 135 KB INT8 CNN over 81×64 on a 240 MHz LX7 ≈ 100–300 ms per 2 s window — acceptable for an event, but it must be measured on the real board. The old spec claimed 38–54 ms for a smaller 58 k-param model.
5. **Tensor arena size** is a hint only (120 KB). Verify `AllocateTensors()` succeeds; put the arena in PSRAM if it does not fit in internal SRAM.
6. **The ble/display policy** is unchanged from the old spec and still assumes binary output — fine.
7. The old firmware's other gotchas still apply: INMP441 DC offset, ESP-NOW TX queue overflow (needs callback flow control), Arduino-3.x callback signature change, and the ILI9341 240 px clipping (the `HubDisplay` subclass).

---

## 8. Next checkpoint — the ESP32-S3 firmware

Concrete plan, in order:

1. **Port `dsp_crynet.c` to ESP-IDF.** Swap the reference radix-2 FFT for ESP-DSP `dsps_fft2r` + `dsps_cmplx_mag` (~10× faster). Copy `crynet_tables.h` and `model_data.h` into the firmware tree.
2. **Wire TFLite Micro.** INT8 input `[1, 81, 64, 1]`; `MicroMutableOpResolver` with `AddConv2D`, `AddDepthwiseConv2D`, `AddMaxPool2D`, `AddMean`, `AddFullyConnected`, `AddSoftmax`; arena in PSRAM if needed. `crynet_infer_example.c` is the template.
3. **Fix the trigger threshold** in the hub: drop the RMS ≥ 0.18 audio-pull trigger to ~0.03 so soft cries reach the model, and let the calibrated threshold do the discriminating. Add the 0.0015 silence gate.
4. **Forward the model output** to the existing BLE packet: `alert_type = 0x01` when `P(cry) >= threshold`, `confidence_pct = round(P(cry) * 100)`.
5. **Measure** inference latency and arena usage on the real board, and log both.
6. **Collect ~50 in-domain clips** and add them as a custom corpus to the notebook, then retrain.

---

## 9. Working preferences (important)

* **Work in checkpoints.** Deliver one artifact per checkpoint; confirm before starting the next stage.
* **Run very few agents in parallel.** A previous session launched ~18 agents at once and exhausted the usage limit within minutes; several sessions then died with "400 Context Limit Exceeded". Prefer direct tool calls (WebSearch / WebFetch / curl / scripts) over subagents. Two sessions died mid-run during this checkpoint — long foreground commands are risky; **prefer background runs writing to a persistent log file in the repo** (e.g. `research/stub_run.log`) so a session break does not lose the work.
* The user is happy for the agent to make and document judgement calls (they answered three structured questions: binary head, "any cry" label policy, Kaggle execution).

---

## 10. Source references

- ICD corpus — https://huggingface.co/datasets/hoyyu1/infant-cry-detection (paper: arXiv 2508.19308, "Infant Cry Detection In Noisy Environment Using Blueprint Separable Convolutions and Time-Frequency Recurrent Neural Network")
- ICSD (gated, rejected) — https://arxiv.org/html/2408.10561v1
- Baby Cry 4-class — https://www.kaggle.com/datasets/karimeletriby/infant-cry-classification-4-classes
- ESC-50 — https://github.com/karolpiczak/esc-50
- Snoring — https://www.kaggle.com/datasets/tareqkhanemu/snoring
- Survey of infant-cry datasets — https://www.computer.org/csdl/journal/ta/2026/01/11267068/2bUqPTUno40
- TinyML infant-cry classification (79,461 params, 96.26 % Baby Chillanto) — https://ieeexplore.ieee.org/iel8/6287639/10820123/11132295.pdf
- TFLite Micro kernel registry — https://github.com/tensorflow/tflite-micro (`tensorflow/lite/micro/kernels/reduce.cc` registers MEAN; `micro_mutable_op_resolver.h` has `AddMean`)
- MicroNets / BC-ResNet (tiny audio backbones) — https://arxiv.org/abs/2010.08691

---

### One-paragraph summary for a lazy reader

Checkpoint 1 of the infant-cry detector is done: the best public corpora were identified by audio-level forensics (ICD as primary — 28,478 real 16 kHz clips from CryCeleb2023/EnesBabyCries/iFLYTEK — plus Baby-Cry-4, ESC-50 and Snoring; the `mennaahmed23` family was rejected as contaminated), and a 24-cell Kaggle notebook was written that trains a ~135 KB INT8 CNN on 2 s 81×64 log-Mel windows, calibrates the alarm threshold for ≥95 % recall, verifies the C front end against Python to 7 × 10⁻⁵, and exports `crynet_int8.tflite`, `model_data.h`, `crynet_tables.h`, `dsp_crynet.c` and `crynet_infer_example.c`. The notebook is written and validated end-to-end (24/24 cells) on stand-in archives, cells 1–15 on the real 28,478-clip corpus, with an indicative real-data result of **val AUC 0.981 / cross-corpus AUC 0.989 and an INT8-vs-float AUC delta of −0.00007**. The user's next action is to run the notebook on Kaggle (T4, ~40 min) and download `out/`; the following checkpoint is the ESP32-S3 firmware port, where the trigger threshold must drop from RMS 0.18 to ~0.03.
