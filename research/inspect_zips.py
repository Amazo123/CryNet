"""Inspect structure/labels/format of candidate Kaggle zips without extracting."""
import collections
import os
import re
import zipfile

DL = r"C:\Users\HP\.t3\projects\fp-2\research\dl"


def describe(zpath):
    print("\n" + "=" * 78)
    print(os.path.basename(zpath))
    print("=" * 78)
    try:
        z = zipfile.ZipFile(zpath)
    except Exception as e:  # noqa: BLE001
        print("  !! cannot open:", e)
        return
    names = [n for n in z.namelist() if not n.endswith("/")]
    print(f"  files: {len(names)}   zip size: {os.path.getsize(zpath)/1e6:.0f} MB")
    exts = collections.Counter(os.path.splitext(n)[1].lower() for n in names)
    print("  extensions:", dict(exts.most_common(10)))
    # directory tree, depth 3
    dirs = collections.Counter()
    for n in names:
        p = n.split("/")
        key = "/".join(p[:-1]) if len(p) > 1 else "(root)"
        dirs[key] += 1
    shown = 0
    for d, c in dirs.most_common(40):
        print(f"    {c:>6}  {d}")
        shown += 1
        if shown >= 40:
            break
    print("  --- sample filenames ---")
    for n in names[:6]:
        print("    ", n)
    print("  --- largest entries ---")
    try:
        infos = sorted(z.infolist(), key=lambda i: -i.file_size)[:6]
        for i in infos:
            print(f"    {i.file_size/1e6:8.2f} MB  {i.filename}")
    except Exception:  # noqa: BLE001
        pass
    # any csv/json metadata?
    meta = [n for n in names if n.lower().endswith((".csv", ".json", ".txt", ".md"))]
    if meta:
        print("  --- metadata files ---")
        for m in meta[:15]:
            print("    ", m)
            if m.lower().endswith(".csv"):
                try:
                    head = z.read(m)[:600].decode("utf-8", "ignore")
                    print("        ", head.replace("\n", " | ")[:500])
                except Exception:  # noqa: BLE001
                    pass


for f in sorted(os.listdir(DL)):
    if f.endswith(".zip"):
        describe(os.path.join(DL, f))
