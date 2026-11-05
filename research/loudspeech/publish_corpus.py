#!/usr/bin/env python3
"""Publish the loud-speech corpus as a public release asset.

    python research/loudspeech/publish_corpus.py

The Kaggle notebook cannot attach a 757 MB file without the user dragging
it into Kaggle by hand, so the corpus is published once on GitHub and the
notebook fetches it from a plain URL like any other corpus it already
downloads.

The GitHub credential comes from the machine's own git credential store
(`git credential fill`), so it is never written into a file or onto a
command line.  The token never appears in the output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "research" / "_cache" / "speech__fsd50k_speech.zip"
REPO = "Amazo123/CryNet"
TAG = "speech-corpus-v1"
ASSET = "speech__fsd50k_speech.zip"

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"

NOTES = """The loud-speech corpus for the CryNet retrain.

6,000 clips of real speech, 16 kHz mono, 2 s windows ready for the
notebook's front end:

  * 3,500 clips from FSD50K (https://github.com/quinnlue/FSD50K-16k),
    dev partition only — the classes a nursery actually contains:
    Laughter, Human_group_actions, Speech, Singing,
    Female_speech_and_woman_speaking, Crowd,
    Male_speech_and_man_speaking, Child_speech_and_kid_speaking, Giggle,
    Chatter, Conversation.  FSD50K is CC-BY 4.0 (c) the FSD50K authors.
  * 2,500 clips from Common Voice 16 kHz
    (https://huggingface.co/datasets/DTU54DL/common-voice-test16k),
    the hash-halved training half only, for speaker and accent breadth.
    Mozilla Common Voice is released under CC0 / MIT.

The notebook that builds this is research/loudspeech/build_speech_zip.py
and the split rules are research/loudspeech/speech_common.py: the
measurement half of Common Voice and the eval partition of FSD50K are
never trained on.

This file is fetched by notebooks/crynet_training.ipynb at runtime.  It
is a build artefact and is not part of the repository history.
"""


def credential() -> tuple[str, str]:
    """The machine's own stored GitHub credential (never printed)."""
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    out = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            out[k] = v
    if "password" not in out:
        raise SystemExit("no GitHub credential in the git credential store")
    return out.get("username", ""), out["password"]


def api(method: str, url: str, token: str, data=None, ctype=None, expect_json=True):
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if ctype:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=120) as r:
        body = r.read()
    if expect_json:
        return json.loads(body) if body else {}
    return body


def main() -> int:
    if not CORPUS.is_file():
        raise SystemExit(f"corpus not built: {CORPUS}")
    size = CORPUS.stat().st_size
    user, token = credential()

    me = api("GET", f"{API}/user", token)
    print(f"authenticated as {me.get('login')}")

    repo = api("GET", f"{API}/repos/{REPO}", token)
    print(f"{REPO}: {'private' if repo.get('private') else 'public'}")

    # the release, created if it is not there yet
    try:
        rel = api("GET", f"{API}/repos/{REPO}/releases/tags/{TAG}", token)
        print(f"release {TAG} exists (id {rel['id']})")
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rel = api("POST", f"{API}/repos/{REPO}/releases", token,
                  data=json.dumps({"tag_name": TAG, "name": TAG,
                                   "body": NOTES, "draft": False,
                                   "prerelease": False}).encode(),
                  ctype="application/json")
        print(f"created release {TAG} (id {rel['id']})")

    # the asset, uploaded if it is not there yet
    have = {a["name"]: a for a in rel.get("assets", [])}
    if ASSET in have:
        asset = have[ASSET]
        print(f"asset already there ({asset['size']} bytes)")
    else:
        print(f"uploading {size/1e6:.0f} MB ...")
        upload_url = (f"{UPLOADS}/repos/{REPO}/releases/{rel['id']}/assets"
                      f"?name={ASSET}")
        with CORPUS.open("rb") as fh:
            asset = api("POST", upload_url, token, data=fh,
                        ctype="application/octet-stream")
        print(f"uploaded: {asset['name']}  {asset['size']} bytes  "
              f"id {asset['id']}")

    url = (f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}")
    print()
    print("public download URL:")
    print(f"  {url}")

    # check it as an anonymous visitor would: no credentials at all
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("User-Agent", "crynet-publish-check")
    with urllib.request.urlopen(req, timeout=120) as r:
        print(f"  anonymous HEAD -> {r.status}  "
              f"content-length {r.headers.get('Content-Length')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
