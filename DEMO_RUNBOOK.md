# Demo runbook

**What this is:** the procedure for the day you demonstrate CryNet. One
page, in order, with the waiting times and the exact log lines to look
for.

**The system:** three ESP32-C3 cot nodes with INMP441 microphones, one
ESP32-S3 hub that runs the model, one BLE wearable on the caregiver's
wrist. A phone plays a recorded infant cry; the hub names the cot that
heard it; the wrist buzzes.

---

## Before you start (once)

1. **The phone's volume.** Set it once, to the level that makes the hub
   read **0.10–0.20 rms** on its panel, and **do not touch it during the
   demonstration**. On most of the clip kit, one volume step louder
   saturates the microphone and the window is refused — the margin
   between "announces" and "clipped" is one step. (Measured:
   `research/out/demo_rehearsal.md`.)
2. **The clip.** Put `session9_clip_0005.wav` on the phone. It is in
   `research/out/demo_kit/`, and it is the most forgiving of the kit:
   it announces at every volume and never clips.
   - Backups, in order: `session4_clip_0012.wav`, `session1_clip_0005.wav`.
   - **Do not** play from the laptop's speakers. They reshape the cry
     enough that the model refuses it (P 0.03–0.15 on a window the model
     scores 0.9961 from the same recording). The phone is not a
     nicety; it is the only source shown to work.
3. **The room.** Quiet if you can get it. The system was measured in a
   quiet room and holds no false alarm in 20.5 minutes of a room with
   people talking, but the demonstration is easier in a quiet room.

---

## The procedure

**The phone goes 15 cm from the microphone of the cot you are testing.**
Not 10 cm (that saturates the microphone) and not 1 m (the cry never
crosses the trigger). 15 cm.

### Cot 1

1. Hold the phone **15 cm from cot 1's microphone**.
2. Press play. **Let the whole 5-second clip run out.** Do not press
   twice, and do not stop it early.
3. **Wait 5 seconds.**
4. **Look at the hub's log**, not only at the wrist:

   ```
   node 1: front end 48.2 ms, inference 103.5 ms, P(no_cry)=0.0039 P(cry)=0.9961
   node 1: ALERT — cry
   ```

   **That second line, on the node you played at, is the pass condition.**
5. **Wait 10 more seconds.** The alert is held for 8 s and then clears
   (the wrist shows `cleared`). You must let it clear before the next
   cot, or the hub keeps naming cot 1 and the wrist shows the wrong cot.

### Cot 2 — the same five steps, ~15 seconds each

### Cot 3 — the same five steps

### After the third cot

1. **Wait 10 seconds of quiet.**
2. Check the hub's log: there should be **three `ALERT — cry` lines, one
   per cot, and nothing after the last one.** A quiet window must never
   announce.

**Total: about 45 seconds of playing, 75 seconds with the waits.**

---

## Reading the log

| the log says | what it means | what to do |
|---|---|---|
| `node N: ALERT — cry` | **pass** — the right cot named | move to the next cot |
| `the window is CLIPPED` | the phone is too close; the microphone saturated | move it **back** to 15 cm, do **not** turn the volume down |
| `no cry` (with P(cry) high) | the window caught a pause in the clip, not the cry | play once more, same place |
| `cry (too quiet to announce)` | below the 0.020 rms floor | phone closer, or the volume up |
| `cry (unconfirmed)` | a maybe: P(cry) was high but the window was not clean | play once more |
| `ALERT — cry` on the **wrong** cot | another cot heard it cleanly | wait out the 8 s hold, then play again |
| nothing at all | the cry never crossed the trigger | phone closer |

**The log is the evidence. The wrist is the output.** The wrist buzzes
once per cry and names the loudest cot, so "it buzzed" proves much less
than the log line does.

---

## Why one play, and not several

The node freezes **one** window per cry. Once it has, it will not freeze
again until the room goes quiet, so a second play of the same clip lands
on the tail of the clip — a pause between cries — and the model scores
that around 0.11. That "no cry" is the *clip* being wrong, not the
system being wrong.

Playing once and reading the log tells you what happened. Playing three
times and watching the wrist tells you almost nothing.

---

## If something goes wrong, in the order to try

1. **Move the phone back to 15 cm.** Clipping is the most common
   failure and the fix is distance, not volume.
2. **Play once more**, same place, and read the log.
3. **Check the hub is still alive** — the console answers `status`:

   ```
   I (12345) console: << status
   I (12346) console:   cot 1: rms 0.0154  level 0.0092  window 0.0121 (whole)  confidence 0%
   I (12347) console:   cot 2: rms 0.0148  level 0.0088  window 0.0119 (whole)  confidence 0%
   I (12348) console:   cot 3: rms 0.0161  level 0.0095  window 0.0124 (whole)  confidence 0%
   ```

   If the console does not answer, the hub has crashed or lost power.
4. **Check the node is alive** — its console answers `status` and
   `stats` too.
5. **The link**, if a window never arrives: the hub logs
   `the burst stalled with N of 286 fragments` and asks for the missing
   ones. The resend rounds recover nearly all of it; if a burst dies
   outright, move the cot away from whatever is on the same channel.

---

## What was measured, and where

| fact | source |
|---|---|
| the kit re-derived against the rule on the boards; 27 of 37 clips announce; 17 clip if turned up | `research/out/demo_rehearsal.md` |
| the clip list and what to use | `research/out/DEMO_KIT.md` |
| the freeze lands 2.0–5.4 s after the clip starts (median 2.9 s) | `research/out/demo_rehearsal.csv` |
| the model needs ~1.5–1.75 s of continuous cry in the window | `research/out/DEMO_KIT.md` |
| the alert is held 8 s and names one cot | `firmware/hub_infer/src/link_stage.c` (`CRY_HOLD_MS`, `COT_SWITCH_MARGIN`) |
| 20.5 minutes with people talking, 0 false alarms | `research/out/ambient_25min/summary.md` |
| three cots on one hub, 25 minutes, no brownout or reset | `SYSTEM_UPDATE.md` |

---

## The one thing to remember

**Set the volume before you start. Do not touch it during.**
