"""A Kaggle notebook cell that packs the artifacts and offers them for download.

Paste this into a new cell at the end of `notebooks/crynet_training.ipynb`
(after the export cell) and run it.  It writes a zip of everything the
notebook put in `out/` to /kaggle/working/crynet_out.zip and prints a
download link.

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

OUT = os.environ.get("CRYNET_OUT", "/kaggle/working/out")
ZIP = "/kaggle/working/crynet_out.zip"

if not os.path.isdir(OUT):
    OUT = os.path.abspath("out")          # a local run, not a Kaggle one

print("--- artifacts in", OUT, "---")
total = 0
for name in sorted(os.listdir(OUT)):
    path = os.path.join(OUT, name)
    if os.path.isfile(path):
        size = os.path.getsize(path)
        total += size
        print(f"  {name:28s} {size / 1024:10.1f} KB")
print(f"  {'TOTAL':28s} {total / 1024:10.1f} KB")

with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _dirs, files in os.walk(OUT):
        for name in files:
            full = os.path.join(root, name)
            # keep the "out/" folder at the top of the archive
            z.write(full, os.path.relpath(full, os.path.dirname(OUT)))

print("\nzip:", ZIP, f"({os.path.getsize(ZIP) / 1024:.1f} KB)")
print("click the link below to download it")
display(FileLink(ZIP))
