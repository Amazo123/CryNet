from concurrent.futures import ThreadPoolExecutor
from huggingface_hub import hf_hub_download
import os, shutil
REPO = "hoyyu1/infant-cry-detection"
OUT = "dl_hf"
os.makedirs(OUT, exist_ok=True)

def get(fn):
    p = hf_hub_download(REPO, fn, repo_type="dataset", local_dir=OUT)
    print("DONE", fn, round(os.path.getsize(p)/1e6), "MB", flush=True)
    return p

with ThreadPoolExecutor(2) as ex:
    list(ex.map(get, ["audio/positive.zip", "audio/negative.zip"]))
