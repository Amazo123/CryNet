# The in-room confusion session — measured 2026-11-01

**O-9, closed.** This is the honest in-room number: the deployed INT8 model
(the file flashed on the hub) run over audio recorded by *this room's*
INMP441, at *this room's* levels, through *this room's* acoustics.

Every take is one minute, recorded with `node_capture` on COM30, cut into
5 s clips with a 2.5 s stride (22 clips, 44 windows of 2 s each), and
labelled with the ground truth of the session rather than by loudness
(`label_session.py --truth`).

**Reproduce:** `research/CONFUSION_SESSION.md` has the commands; the
per-session reports are `research/out/eval_session*.json`.

---

## The result

| # | Take | Class | Median RMS | Peak RMS | Records ≥ 0.030 | Clips that reach the model | **False alarms** | Recall |
|---|---|---|---|---|---|---|---|---|
| 1 | `session5` | quiet room | 0.0020 | 0.0100 | 0 / 590 | 0 / 22 | **0** | — |
| 2 | `session6` | speech, desk distance | 0.0040 | 0.0530 | 3 / 590 | 0 / 22 | **0** | — |
| 2b | `session6b` | speech, 30 cm | 0.0080 | 0.6670 | 62 / 590 | 6 / 22 | **0** | — |
| 3 | `session7` | music, 1 m | 0.0100 | 0.0380 | 1 / 590 | 0 / 22 | **0** | — |
| 4 | `session8` | movie, 1 m | 0.0070 | 0.0190 | 0 / 590 | 0 / 22 | **0** | — |
| 4b | `session8b` | movie, 30 cm | 0.0260 | 0.2180 | 269 / 590 | 12 / 22 | **0** | — |
| 4c | `session7b` | music, 30 cm | 0.0470 | 0.1410 | 493 / 590 | 20 / 22 | **0** | — |
| 5 | `session9` | **the cry**, 15 cm | 0.0370 | 0.3870 | 329 / 590 | 20 / 22 | 0 | **38/44 = 86.4 %** |
| 6 | `session10` | **the cry**, 1 m | 0.0070 | 0.0160 | 0 / 590 | 0 / 22 | 0 | *18/44 = 40.9 % if asked* |

**Zero false alarms in 308 windows of non-cry audio.** Seven takes of
speech, music and film; 44 windows each; the model never once crossed
P(cry) ≥ 0.95.

The two loud takes are the ones that count, because the trigger fired on
almost half of the loud movie (269/590 records) and on 84 % of the loud
music (493/590) — the model was asked 44 times in each and refused every
one. That is the retrain (D-58) working in the room it was supposed to
work in: on GTZAN the music false-alarm rate was 8.19 %, and on the
loudest music this room can produce it is 0/44.

## What the numbers say

**1. The trigger, not the model, is the limit on how far the hub can hear.**
The hub only pulls a 2 s window when the node's telemetry RMS reaches
`CRYNET_TRIGGER_RMS` = 0.030. A phone at one metre, volume at maximum,
reaches a median of 0.0070 and a peak of 0.0160 — **0 of 590 records get
past the trigger**, so the cry at one metre is not "missed by the model",
it is never offered to the model at all. If the model were asked anyway
(the confusion matrix ignores the trigger), it would still have caught
18 of 44 windows. The system is blind at one metre *by trigger*, not by
discrimination.

**2. A cry 15 cm from the mic is caught 86 % of windows.** This is the
realistic case: the microphone is *in the cot*, the baby is *in the cot*.

**3. Everything else in the room is below the trigger.** At one metre, a
laptop playing music or a film never crosses 0.030 (0.0100 and 0.0070
medians). The hub would sit silent through both. Close up, both cross it
comfortably, and the model rejects both.

**4. The quiet floor is very low.** 0.0020 median, 0.0100 peak, and the
room alone never asks the model a question.

**5. The microphone is quiet, and the fix is in software, not in hardware.**
A close, loud conversation peaks at 0.6670, but a phone at full volume a
metre away peaks at 0.0160. The INMP441 has **no gain setting**: its `L/R`
pin is a left/right *channel select* (LOW = the left slot), not a gain
strap, and the part is fixed at −26 dBFS ±3 dB sensitivity — the
datasheet's own note is that "in most applications, the microphone output
requires some gain added in the signal path". So there is nothing to
rewire. The reach is set by two software levers: the hub's trigger
threshold, and a digital gain in the telemetry path. A gain in the
*telemetry* path alone (the number the hub's trigger sees) is the cheap
one — it lifts the signal and the noise floor together, so it cannot
separate a distant cry from the quiet room, whereas a trigger that scales
with the measured noise floor can.

**6. A suggested change, with the evidence for it.** Lowering
`CRYNET_TRIGGER_RMS` from 0.030 to about 0.012 would extend the
detection range substantially: the quiet room (p99 0.0070) stays below it,
the movie at one metre (p90 0.0120) only brushes it, and every window of
every loud take was already rejected by the model. **But this is a
suggestion, not a change** — it is measured on 308 windows of one room on
one afternoon, and the corpus numbers say the threshold is also what keeps
ESC-50's non-cry rate at 1.18 %. It belongs in the next training round's
evaluation, not in a flash tonight.

The better version of the same idea is an **adaptive trigger**: the hub
already sees the node's 100 ms RMS continuously, so it could track the
quiet floor per node and trigger at a multiple of it (say 3× the running
minimum) rather than at a fixed 0.030. In this room the floor is 0.0020,
so 3× would be 0.006 — below the one-metre phone's 0.0070 — while the
quiet room would still never trigger. That separates a distant cry from
the room, which no amount of fixed gain can do. It is a hub-firmware
change, not a model change, so it costs no re-deployment.

## The honest caveat

The cry is a phone speaker playing a recording, 15 cm from a mic that
sits in a cot. A real baby in a real cot is a different sound: closer,
lower, and coupled by the cot's own resonances. The model's behaviour on
that has never been measured, and cannot be, without a baby. What this
session *does* establish is that the false-alarm side is solid in this
room — which is the half of the problem that the system controls.

## Files

| What | Where |
|---|---|
| The takes (audio, gitignored) | `research/in_domain/session{5,6,6b,7,7b,8,8b,9,10}/` |
| Per-session reports | `research/out/eval_session*.json` |
| Per-session manifests and timelines | `research/in_domain/session*/manifest.csv`, `summary.txt` |
| The procedure | `research/CONFUSION_SESSION.md` |
