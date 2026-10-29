"""Enumerate candidate Kaggle datasets for infant-cry detection + negative audio."""
import json
import urllib.parse
import urllib.request

API = "https://www.kaggle.com/api/v1/datasets/list"

QUERIES = [
    "infant cry",
    "baby cry",
    "cry detection",
    "chillanto",
    "donate a cry",
    "baby sound",
    "baby monitor audio",
    "ESC-50",
]


def fetch(url):
    """Kaggle's edge rejects urllib; shell out to curl instead."""
    import subprocess

    out = subprocess.run(
        ["curl", "-s", "--max-time", "60", url],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(out)


def summarize(slug):
    try:
        meta = fetch(f"https://www.kaggle.com/api/v1/datasets/view/{slug}")
    except Exception as e:  # noqa: BLE001
        return {"ref": slug, "error": str(e)}
    files = meta.get("resources") or meta.get("files") or []
    names = [f.get("path") or f.get("name") for f in files]
    tops = {}
    for n in names:
        if not n:
            continue
        parts = n.split("/")
        key = parts[0] if len(parts) > 1 else "(root)"
        tops[key] = tops.get(key, 0) + 1
    return {
        "ref": slug,
        "title": meta.get("title"),
        "size_mb": round((meta.get("totalBytes") or 0) / 1e6, 1),
        "n_files": len(names),
        "top_dirs": tops,
        "sample_files": names[:8],
        "license": meta.get("licenseName"),
    }


def main():
    seen = {}
    for q in QUERIES:
        url = f"{API}?search={urllib.parse.quote(q)}"
        try:
            rows = fetch(url)
        except Exception as e:  # noqa: BLE001
            print(f"!! search failed {q}: {e}")
            continue
        print(f"\n=== search: {q!r} -> {len(rows)} hits ===")
        for row in rows[:12]:
            ref = row.get("ref")
            print(
                f"  {ref:<55} {round((row.get('totalBytes') or 0)/1e6,1):>8} MB "
                f"dl={row.get('downloadCount'):<7} votes={row.get('voteCount')} | "
                f"{(row.get('title') or '')[:48]}"
            )
            seen[ref] = True

    print("\n\n########## FILE-TREE SUMMARIES ##########")
    targets = [
        "warcoder/infant-cry-audio-corpus",
        "mennaahmed23/decoding-cries-baby",
        "eliasmarcon/environmental-sound-classification-50",
        "akaliutau/esc-50",
        "chrisfilo/urbansound8k",
    ]
    for slug in targets:
        info = summarize(slug)
        print(f"\n--- {slug} ---")
        for k, v in info.items():
            print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
