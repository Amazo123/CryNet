# research/ — how the dataset decision was made

Everything here is the investigation behind `../notebooks/crynet_training.ipynb`. Nothing in this folder is needed to *run* the notebook on Kaggle — it is kept so the choices can be audited and repeated.

## Scripts

| Script | What it does |
|---|---|
| `scan_kaggle.py` | Queries the public Kaggle dataset API (no auth needed) and summarises every candidate: size, download count, file tree. |
| `inspect_zips.py` | Reads the archive central directories to reveal folder/class structure, formats and metadata files without extracting anything. |
| `analyze_audio.py` | Audio forensics on samples drawn straight from the archives: sample rate, duration, RMS, autocorrelation F0, spectral centroid, spectral flatness — enough to tell a real cry from a synthetic one. |
| `build_notebook.py` | **Generates `../notebooks/crynet_training.ipynb`.** The notebook is generated rather than hand-written so the code stays reviewable and the build is reproducible. |
| `run_notebook_local.py` | Executes the generated notebook cell by cell locally (so it can be validated before upload). |
| `test_c_parity.py` | Compiles the exported `dsp_crynet.c` and compares its log-Mel against the Python training front end. Uses `gcc` if present, otherwise the `ziglang` wheel (`pip install ziglang`). |
| `make_stub.py` | Builds tiny synthetic stand-in archives so the full pipeline can be exercised without a 4.6 GB download. |

## What the forensics found

* **The `mennaahmed23` "Baby Cry" family is contaminated.** Its `silence` class measures RMS 0.22 with a constant 1225 Hz — it is not silence. Its `noise` class is renamed ESC-50 files. Hundreds of files are synthetic `generated3_*` derivatives. Training on it teaches dataset artifacts.
* **DonateACry is 8 kHz.** Usable, but upsampling adds no information above 4 kHz, and the class distribution is badly skewed (382 of 457 files are `hungry`).
* **The ICD corpus is uniform**: every clip is 16 kHz mono / 5.00 s, and the manifest matches the archives 1:1 (13,330 positives, 15,148 negatives). Its recordings are quiet (RMS ≈ 0.006) while the negatives are loud (RMS 0.3–0.46) — a level cue the model must not rely on, which is why the front end applies per-window standardisation.
* **TFLite Micro kernel availability is not obvious.** `GlobalAveragePooling2D` lowers to the `MEAN` op; TFLM registers it in `kernels/reduce.cc` (not `mean.cc`, which is why a naive filename search suggests it is missing). The notebook now asserts that every op in the exported model has a TFLM kernel.

## Local runs

```bash
# full pipeline on synthetic stand-ins (minutes)
python make_stub.py && CRYNET_FAST=1 CRYNET_OFFLINE=1 python run_notebook_local.py

# C <-> Python parity
python test_c_parity.py
```

The real corpora are cached under `_cache/` (not committed — see `.gitignore`).
