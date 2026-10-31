# The confusion session — what the system does when the room is not quiet

The model's behaviour on **real music** was never trained and has never been
measured (no corpus in the training mix contains any). The false-alarm map
over ESC-50 says the model rejects speech, household noise and human
non-speech well (1.6 %), but ESC-50 has no music either.

The number that matters for the demo is the one measured **in this room,
through this microphone, with this speaker**. That is this session.

## What to record

Five recordings, one minute each, with the INMP441 in the cot and the hub
listening (the hub is not needed for the recording — only the node is).

| # | What | Why |
|---|---|---|
| 1 | **Quiet room** — nobody, nothing | the floor: what the room alone does |
| 2 | **Speech** — talk, read something, laugh, cough | the confusion class with the most energy |
| 3 | **Music** — play a track from the phone, loud | the class the model has never seen |
| 4 | **TV / other** — a talk show, a video game, a vacuum cleaner | broadband non-cry sound |
| 5 | **The cry** — the phone playing the baby-cry recording | the positive, at the same volume |

Record 5 **twice**: once with the phone next to the node (loud) and once a
metre away (quiet). The distance changes the level, and the hub's trigger
sits at RMS 0.030, so a cry that is too quiet never reaches the model at all.

## How

The node has to be running `node_capture` (not `node_crynet`):

```bash
ARDUINO_CLI="$LOCALAPPDATA/Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe"
cd firmware/node/node_capture
"$ARDUINO_CLI" compile --fqbn esp32:esp32:weact_studio_esp32c3 .
"$ARDUINO_CLI" upload -p COM30 --fqbn esp32:esp32:weact_studio_esp32c3 .
```

Then, one command per recording:

```bash
cd C:/Users/HP/.t3/projects/fp-2
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session5 \
       --seconds 60 --note "quiet room"
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session6 \
       --seconds 60 --note "speech"
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session7 \
       --seconds 60 --note "music"
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session8 \
       --seconds 60 --note "tv and household"
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session9 \
       --seconds 60 --note "phone cry, loud"
python firmware/tools/collect_clips.py --port COM30 --out research/in_domain/session10 \
       --seconds 60 --note "phone cry, one metre away"
```

## Then

```bash
for s in 5 6 7 8 9 10; do
  python firmware/tools/label_session.py --session research/in_domain/session$s
  python research/eval_indomain.py --session research/in_domain/session$s
done
```

Each session prints its own confusion matrix at the deployed threshold
(0.95) and at the hub's trigger (0.030): **how many windows of that sound
would reach the model, and how many of those would raise an alarm.**

## What the numbers mean

- **Quiet room** — the number of false alarms must be zero.
- **Speech / music / TV** — the false-alarm rate per loud window. This is
  the number the demo room will produce.
- **The cry** — recall, and how far away the phone can be before the hub
  stops asking the model at all (the trigger is RMS 0.030).

Anything that alarms on music goes into the next training round as a hard
negative, and the hard negatives go into `research/build_notebook.py` — not
into the `.ipynb` by hand.
