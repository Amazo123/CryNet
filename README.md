# CryNet — infant cry detection for the ESP32-S3 hub

Training pipeline for the cry detector that runs on the **Central Intelligence Hub (ESP32-S3-DevKitC-1)** of the multi-node infant monitor.

**Status:** checkpoint 1 — dataset research done, training notebook written and validated.

---

## What is in this repo

| Path | What it is |
|---|---|
| `notebooks/crynet_training.ipynb` | **The deliverable.** Downloads the corpora, builds the feature set, trains, quantizes to INT8 and exports the firmware artifacts. Run it on Kaggle. |
| `research/` | The dataset investigation behind the notebook: scripts, corpus analysis, and the C↔Python parity test. |

---

## The dataset decision

The research phase downloaded and profiled every public infant-cry corpus on Kaggle and Hugging Face (audio-level forensics: sample rate, duration, F0, spectral flatness, real-vs-synthetic). The result:

### Used

| Corpus | Role | Why |
|---|---|---|
| **[ICD — `hoyyu1/infant-cry-detection`](https://huggingface.co/datasets/hoyyu1/infant-cry-detection)** | **primary** | 28,478 clips, **all 16 kHz mono / 5 s**, pre-assigned 5 balanced folds. Cries from EnesBabyCries (5,026), CryCeleb2023 (4,552) and iFLYTEK 2020 (3,752) — three independent corpora, hundreds of different infants. Negatives: VoxCeleb speech (4,963), DASEE domestic noise (4,506), human non-speech (2,076), cat meows (1,953), silence (1,650). |
| **[Baby Cry 4-class — `karimeletriby/…`](https://www.kaggle.com/datasets/karimeletriby/infant-cry-classification-4-classes)** | cry diversity + cross-corpus test | 4,871 real cries, 16 kHz, LUFS-normalised, VAD-trimmed, cross-dataset deduplicated (1,297 near-duplicates removed). |
| **[ESC-50](https://github.com/karolpiczak/esc-50)** | negatives + cross-corpus test | 1,960 non-cry clips (speech, laughing, vacuum, clock alarm, door knocks…) plus 40 real `crying_baby` clips kept purely as an unseen cross-domain test. |
| **[Snoring](https://www.kaggle.com/datasets/tareqkhanemu/snoring)** | hard negatives | 1,000 adult-vocal recordings — the confusion class a nursery monitor hits constantly. |

### Rejected, and why

* **`mennaahmed23/baby-cry*` (five Kaggle mirrors)** — the "silence" class is **not silence**: RMS 0.22, peak 1.0, a constant 1225 Hz. The "noise" class is renamed ESC-50 files. Hundreds of files are synthetic `generated3_*` variants. Training on these teaches dataset artifacts, not cries.
* **`rahult25/five-class-…`** — same base corpus plus pitch-shifted derivatives (`uncomfortable_10 … _72`).
* **ICSD (`QingyuLiu1/ICSD`)** — the best-curated corpus in existence (3,641 weakly + 807 real strongly-labelled clips, event-level timestamps) but it is **gated on Hugging Face** and needs a token plus manual approval.
* **`AxonData/infant-cry-detection`** — 50 h of real, expertly-labelled domestic recordings, but the Kaggle upload is an 18-file teaser and the full set is paid.
* **Baby Chillanto (INAOE)** — 2,267 high-quality 16 kHz newborn cries, but no clean public mirror; it is request-only from the lab.
* **AudioSet / FSD50K** — would need YouTube extraction or a 30 GB pull for a handful of clips that ICD already covers.

### Two decisions that changed the design

1. **The old trigger threshold was the real bug.** The hub fired an audio pull at RMS ≥ 0.18, so a *soft* cry never reached any classifier. The new design feeds the model anything above ~0.03 RMS and lets it reject false triggers — rejecting speech, cat meows and household noise is exactly what it was trained for.
2. **The front end must match training exactly.** Log-mel computed by librosa and by the firmware's ESP-DSP code differ enough to destroy accuracy. So the notebook *generates* the Mel filterbank and Hann window as C tables, and `out/dsp_crynet.c` is verified against the Python implementation by a compiled parity test (measured deviation **7 × 10⁻⁵**).

---

## Running the training

### On Kaggle (recommended)

1. New notebook → *Add Input* → attach nothing.
2. Accelerator **GPU T4**, Internet **On**.
3. Upload `notebooks/crynet_training.ipynb` → *Run All*.

The notebook pulls ~4.6 GB of audio (resumable via `huggingface_hub`), extracts features, trains four CNN variants, picks the best on validation AUC, calibrates the alarm threshold for ≥ 95 % recall, quantizes to INT8 and writes the artifacts to `/kaggle/working/out/`.

| Artifact | What it is |
|---|---|
| `crynet_int8.tflite` | the deployable model |
| `model_data.h` | the model as a C byte array |
| `crynet_tables.h` | Mel filterbank + Hann window + quantisation constants |
| `dsp_crynet.c` / `.h` | portable C front end, numerically identical to training |
| `crynet_infer_example.c` | TFLite Micro glue: PCM → log-Mel → quantise → `Invoke()` → `P(cry)` |
| `crynet.keras` | the trained Keras model, so INT8 export can be repeated without retraining |
| `deploy_config.json` | input shape, quantisation params, operator list, threshold, metrics |
| `metrics.json` | per-variant AUC / F1 / recall |
| `c_parity.json` | measured C-vs-Python deviation of the front end |

### Locally

```bash
pip install numpy librosa soundfile soxr scipy scikit-learn tensorflow
CRYNET_FAST=1 python research/run_notebook_local.py     # smoke test, minutes
```

---

## What was verified before handing it over

| Check | Result |
|---|---|
| Whole notebook runs end to end (data → features → training → mining → INT8 → export) | ✅ all 24 cells, on synthetic stand-in archives; and cells 1–15 on the **real** 28,478-clip corpus (feature extraction 128 s for 56,956 windows) |
| C front end vs. the Python training front end | ✅ compiled and compared on 4 probes: **max deviation 7 × 10⁻⁵** (`research/test_c_parity.py`, and again inside the notebook) |
| Every op in the exported model has a TFLite Micro kernel | ✅ `CONV_2D`, `DEPTHWISE_CONV_2D`, `MAX_POOL_2D`, `MEAN`, `FULLY_CONNECTED`, `SOFTMAX` — the notebook asserts this at export time and records the list in `deploy_config.json` |
| INT8 vs float32 parity | ✅ measured in the notebook (AUC delta printed; 0.00000 on the stand-in run) |
| Corpus integrity | ✅ ICD manifest ↔ archives: 13,330 positives and 15,148 negatives, exact 1:1 match, all 16 kHz mono / 5.00 s |
| Exported model size | ✅ ~135 KB INT8 (122,770 parameters) — fits the S3 flash with room to spare |

Bugs found and fixed during validation (all would have surfaced on the device, not in training): `tf.py_function` erasing the batch shape, the TFLite converter rejecting the representative-dataset format, the front-end output tensor missing its channel axis, and a runaway silence gate that would have discarded quiet cries.

### Measured on the real corpus (indicative)

From a deliberately small local CPU run — **3 epochs on an 8,490-window subsample** of the real data, not the full 74 k / 35-epoch Kaggle configuration. Treat these as a floor, not the final numbers.

| Split | AUC | F1 | Recall | FPR |
|---|---|---|---|---|
| ICD val (fold 4) | 0.9807 | 0.9145 | 0.9504 | 0.1240 |
| ICD test (fold 5) | 0.9839 | 0.9131 | 0.9534 | 0.1058 |
| **cross-corpus** (cry4 + ESC-50 + snoring, never trained on) | **0.9887** | 0.9413 | 0.9544 | 0.0789 |

INT8 vs float32: AUC 0.9806 vs 0.9807 (**delta −0.00007**), 99.70 % decision agreement.

Cry recall on the **unseen** cry4 corpus: `needs` 98.8 %, `physical_pain` 96.9 %, `scared` 90.5 %, `burping` 82.0 %. On ESC-50's `crying_baby` (also unseen): 85 % recall, and 0 % false positives against the other 49 ESC-50 categories.

**The weak spot, worth acting on:** `coughing` produced a 57 % false-alarm rate, followed by `car_horn` and `church_bells` at 33 %. Coughing is acoustically close to crying — a vocal expulsion — and a baby monitor that alerts on coughs is a nuisance. The notebook therefore gained a **hard-example mining round**: after the main training, it scores its own training set, takes the 600 most cry-like non-cry windows and the 600 least cry-like cry windows, duplicates them, and fine-tunes for a few epochs at a 3× lower learning rate. Only training rows are mined, so the held-out folds stay honest. On the stand-in run this cut the cross-corpus false-alarm rate from 0.109 to 0.004.

If `coughing` is still the top confuser after the full Kaggle run, the next lever is a dedicated cough corpus (e.g. ESC-50's 40 cough clips are only partially in training; the FSDKaggle2018 cough set would add several hundred more).

---


---

## The firmware contract

```
int16_t pcm[32000]                 2.000 s @ 16 kHz mono
  -> float x = pcm / 32768.0
  -> subtract mean                 DC removal (INMP441 sits at ~+18000 counts)
  -> zero-pad 256 front / 512 rear
  -> 81 frames, 512-pt Hann, hop 400
  -> |rfft|^2                     257 bins
  -> 64 Mel bands                 librosa slaney mel, 20 Hz - 8 kHz
  -> 10*log10(max(P,1e-10))       floored at -80 dB
  -> per-window standardisation   (mean 0, std 1)
  -> int8 quantise                q = round(v/scale) + zero_point
  -> TFLite Micro int8 inference  -> P(cry)
```

Decision rule: `P(cry) >= threshold` → alert. The threshold is *calibrated on the validation fold*, not hard-coded to 0.65.

---

## Next (checkpoint 2)

1. Port `dsp_crynet.c` to ESP-IDF, swapping the reference FFT for ESP-DSP `dsps_fft2r` + `dsps_cmplx_mag` (~10× faster).
2. Run TFLite Micro with an INT8 input `[1, 81, 64, 1]`; arena in PSRAM if it does not fit in internal SRAM.
3. **Record ~50 real clips from your own INMP441** (cries + room noise + speech + TV) and add them as a custom corpus. Matching your actual microphone, gain and room is the single biggest accuracy win left.
4. Decide the alert policy for the wearable (`alert_type` / `confidence_pct` map straight onto the model output).
