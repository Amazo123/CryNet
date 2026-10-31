"""A Kaggle notebook cell that finds the artifacts and offers them for download.

Paste this into a new cell at the end of `notebooks/crynet_training.ipynb`
(after the export cell) and run it.  It writes a zip of everything the
notebook produced to /kaggle/working/crynet_out.zip and prints a
download link.

The cell does not assume where the artifacts are.  The first version of
it looked in /kaggle/working/out and stopped with a FileNotFoundError,
because the notebook's own output directory is `Path("./out").resolve()`
- relative to whatever the working directory happened to be - and the
session that ran it was not the session that looked for it.  So the cell
asks the notebook first (the variable `OUT` survives in the kernel if
the export cell ran in this session), and then searches.

Two ways to get the file off Kaggle:

  1. **Interactive (the usual way).**  Run the cell in the notebook
     editor and click the link it prints.  Kaggle serves the file from
     the session.

  2. **Committed run ("Save Version").**  FileLink does not work there,
     but a file left in /kaggle/working is published as a notebook
     *output* and can be downloaded from the version's Output tab.  The
     zip is written to /kaggle/working, so nothing else is needed.

Drop the downloaded zip in the repo (for example research/kaggle_out/) and
the agent will unpack it and compare the model against the deployed one.
"""

import os
import zipfile

from IPython.display import FileLink, display

# The files the notebook is expected to produce.
WANTED = (
    "model_data.h", "crynet_int8.tflite", "crynet_float.tflite", "crynet.keras",
    "crynet_tables.h", "dsp_crynet.c", "dsp_crynet.h", "crynet_infer_example.c",
    "deploy_config.json", "metrics.json", "eval_music.json", "eval_indomain.json",
    "eval_esc50.json", "verify_int8_parity.json", "c_parity.json",
)

ZIP = "/kaggle/working/crynet_out.zip"

# 1. The notebook's own output directory, if its cells ran in this
#    session - `OUT` is still in the kernel then.
found = {}
try:
    notebook_out = str(OUT)
except NameError:
    notebook_out = None

if notebook_out and os.path.isdir(notebook_out):
    for name in sorted(os.listdir(notebook_out)):
        path = os.path.join(notebook_out, name)
        if os.path.isfile(path) and name in WANTED:
            found.setdefault(notebook_out, []).append(name)

# 2. Otherwise look for the files themselves, wherever they are.
if not found:
    roots = ["/kaggle/working", os.getcwd(), os.path.expanduser("~"), "/tmp"]
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in (".git", "__pycache__", "site-packages",
                                        "datasets", "models", "node_modules")]
            for name in filenames:
                if name in WANTED:
                    found.setdefault(dirpath, []).append(name)

if not found:
    print("NO ARTIFACTS FOUND.")
    print("The notebook's OUT was:", notebook_out)
    print("Here is everything under /kaggle/working:")
    for dirpath, dirnames, filenames in os.walk("/kaggle/working"):
        print(f"  {dirpath}   ({len(filenames)} files)")
        dirnames[:] = []
    print()
    print("If the training did not run in this session, run the notebook's")
    print("cells 1 and 20 (or 'Run All') here first, then run this cell again.")
else:
    print("--- the artifacts ---")
    total = 0
    for directory in sorted(found):
        for name in sorted(found[directory]):
            path = os.path.join(directory, name)
            size = os.path.getsize(path)
            total += size
            print(f"  {directory}/{name:26s} {size / 1024:9.1f} KB")
    print(f"  {'TOTAL':28s} {total / 1024:9.1f} KB")

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for directory in sorted(found):
            # keep the folder name at the top of the archive
            folder = os.path.basename(directory.rstrip(os.sep)) or "out"
            for name in sorted(found[directory]):
                z.write(os.path.join(directory, name),
                        os.path.join(folder, name))

    print("\nzip:", ZIP, f"({os.path.getsize(ZIP) / 1024:.1f} KB)")
    print("click the link below to download it")
    display(FileLink(ZIP))
