#!/usr/bin/env python3
"""The gate a retrained model has to pass before it is deployed.

    python -I research/loudspeech/gate_model.py --model research/_out/crynet_int8.tflite

It runs the whole false-alarm and recall battery over a candidate model
and prints one table with a PASS or FAIL on every line.  The numbers it
checks against are the *deployed* model's numbers, measured in this repo:

  * speech (the reason for the retrain): the announcement rate over
    loud speech, and the announcements on children's speech;
  * music: 0.21 % of the clips that reach the model;
  * ESC-50: 1.18 % on the non-cry clips, 36 of 40 crying_baby clips;
  * the room's own recordings: no false alarm in any confusion take,
    and the per-window recall on the cry at 15 cm.

A candidate that fixes speech and loses the cry is no use, so both
halves are gates, not preferences.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research" / "out"
PY = sys.executable

# --- the deployed model's numbers, measured in this repo --------------------
GATE = {
    # what the deployed model scores today
    "speech_announce_rate": 0.0156,     # 60 announcements / 3,842 loud speech clips
    "speech_child_announce_rate": 0.161,  # 5 / 31
    "music_alarm_rate": 0.0021,          # 2 / 965
    "esc50_alarm_rate": 0.0118,          # ESC-50 non-cry
    "esc50_cry_recall": 0.90,            # 36 / 40 crying_baby
    "indomain_false_alarms": 0,          # the confusion takes
    "indomain_cry_recall": 0.864,        # session 9, the cry at 15 cm
}

# what a candidate must reach
REQUIRE = {
    "speech_announce_rate": 0.002,       # ten times better than today
    "speech_child_announce_rate": 0.0,   # not one child's voice
    "music_alarm_rate": 0.0021,          # no worse than the deployed model
    "esc50_alarm_rate": 0.0118,          # no worse
    "esc50_cry_recall": 0.90,            # no worse
    "indomain_false_alarms": 0,          # none
    "indomain_cry_recall": 0.80,         # within reach of the deployed 0.864
}

SESSIONS = ["session5", "session6", "session6b", "session7", "session7b",
            "session8", "session8b"]
CRY_SESSION = "session9"


def run(cmd):
    print("+ " + " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit(f"failed: {cmd[1] if len(cmd) > 1 else cmd}")
    return r.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(OUT / "crynet_int8.tflite"))
    ap.add_argument("--workdir", default=str(ROOT / "research" / "loudspeech" / "gate"))
    ap.add_argument("--skip-runs", action="store_true",
                    help="judge the reports already in the workdir")
    args = ap.parse_args()

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    model = Path(args.model)
    if not model.is_file():
        raise SystemExit(f"no such model: {model}")

    if not args.skip_runs:
        run([PY, "-I", ROOT / "research" / "eval_speech.py", "--model", model,
             "--report", work / "eval_speech.json"])
        run([PY, "-I", ROOT / "research" / "eval_music.py", "--model", model,
             "--report", work / "eval_music.json"])
        run([PY, "-I", ROOT / "research" / "eval_esc50.py", "--model", model,
             "--report", work / "eval_esc50.json"])
        for s in SESSIONS + [CRY_SESSION]:
            run([PY, "-I", ROOT / "research" / "eval_indomain.py",
                 "--session", ROOT / "research" / "in_domain" / s,
                 "--model", model, "--report", work / f"eval_{s}.json"])

    speech = json.loads((work / "eval_speech.json").read_text())
    music = json.loads((work / "eval_music.json").read_text())
    esc50 = json.loads((work / "eval_esc50.json").read_text())

    clear = [c for c in speech["per_clip"] if not c["ambiguous"]]
    reached = [c for c in clear if c["reaches_model"]]
    speech_announce = sum(1 for c in reached if c["announces"])
    child = [c for c in reached if "Child_speech" in c["group"]]
    child_announce = sum(1 for c in child if c["announces"])

    negatives = esc50.get("negatives", {}) or {}
    esc50_alarm_rate = negatives.get("alarm_rate_over_reached", 0.0)
    # the crying_baby clips are the cross-corpus cry test: how many of
    # them the model calls a cry
    cry_clips = [c for c in esc50.get("per_clip", []) if c.get("category") == "crying_baby"]
    cry_recall = (sum(1 for c in cry_clips if c.get("alarm")) / len(cry_clips)
                  if cry_clips else 0.0)

    # the confusion takes: the false positives the model made on
    # non-cry audio recorded in this room
    false_alarms = 0
    for s in SESSIONS:
        p = work / f"eval_{s}.json"
        if p.exists():
            false_alarms += int(json.loads(p.read_text())["int8"]["fp"])
    cry_recall_room = 0.0
    p = work / f"eval_{CRY_SESSION}.json"
    if p.exists():
        cry_recall_room = float(json.loads(p.read_text())["int8"]["recall"])

    measured = {
        "speech_announce_rate": speech_announce / len(reached) if reached else 0.0,
        "speech_child_announce_rate": child_announce / len(child) if child else 0.0,
        "music_alarm_rate": music["overall"]["alarm_rate_over_reached"],
        "esc50_alarm_rate": esc50_alarm_rate,
        "esc50_cry_recall": cry_recall,
        "indomain_false_alarms": false_alarms,
        "indomain_cry_recall": cry_recall_room,
    }

    print()
    print("=" * 88)
    print(f"  gate for {model}")
    print("=" * 88)
    print(f"{'measure':<30}{'deployed':>12}{'candidate':>12}{'required':>12}   verdict")
    print("-" * 88)
    ok_all = True
    for k, req in REQUIRE.items():
        val = measured[k]
        base = GATE[k]
        if k.endswith("_rate"):
            good = val <= req
            fmt = f"{val*100:.2f} %"
            print(f"{k:<30}{base*100:>11.2f}%{fmt:>12}{req*100:>11.2f}%   "
                  f"{'PASS' if good else 'FAIL'}")
        elif k == "esc50_cry_recall":
            good = val >= req
            print(f"{k:<30}{base*100:>11.2f}%{val*100:>11.2f}%{req*100:>11.2f}%   "
                  f"{'PASS' if good else 'FAIL'}")
        elif k == "indomain_false_alarms":
            good = val <= req
            print(f"{k:<30}{base:>12}{val:>12}{req:>12}   {'PASS' if good else 'FAIL'}")
        else:   # indomain_cry_recall
            good = val >= req
            print(f"{k:<30}{base*100:>11.2f}%{val*100:>11.2f}%{req*100:>11.2f}%   "
                  f"{'PASS' if good else 'FAIL'}")
        ok_all = ok_all and good
    print("-" * 88)
    print(f"  speech: {speech_announce} announcements over {len(reached)} loud speech clips")
    print(f"  children's speech: {child_announce} announcements over {len(child)} clips")
    print()
    print("VERDICT:", "PASS — the candidate may be deployed" if ok_all
          else "FAIL — do not deploy this model")
    (work / "gate.json").write_text(json.dumps(
        {"model": str(model), "measured": measured, "required": REQUIRE,
         "passed": ok_all}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
