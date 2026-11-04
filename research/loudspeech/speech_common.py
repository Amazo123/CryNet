"""Shared rules for the speech corpora.

The Common Voice mirror is split in half by a hash of the clip id: one
half may go into the training corpus, the other half is kept for
measurement.  Both sides must agree on the rule, so it lives here.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

# The FSD50K classes that are speech.  A nursery has all of them.
#
# "Crying_and_sobbing", "Screaming" and "Shout" are deliberately NOT in
# this list: an adult crying or screaming is not a baby's cry, but it is
# close enough that the right answer is arguable.  They are measured and
# reported separately instead of being trained on.
SPEECH_CLASSES = {
    "Speech",
    "Child_speech_and_kid_speaking",
    "Conversation",
    "Chatter",
    "Crowd",
    "Human_voice",
    "Male_speech_and_man_speaking",
    "Female_speech_and_woman_speaking",
    "Laughter",
    "Giggle",
    "Singing",
    "Male_singing",
    "Female_singing",
    "Human_group_actions",
    "Speech_synthesizer",
}

AMBIGUOUS_CLASSES = {"Crying_and_sobbing", "Screaming", "Shout"}

# The partitions of FSD50K.  The official split is dev (train) and eval
# (test); the Hugging Face mirror calls them `train-*`, `validation-*` and
# `test-*`, but the `source_partition` field carries the truth.
FSD_TRAIN_PARTITIONS = {"dev"}
FSD_MEASURE_PARTITIONS = {"eval"}


def cv_id(shard_name: str, row: int) -> str:
    """A clip id that is unique across the Common Voice shards.

    The shard's own number is part of the id: both shards of the mirror
    are called `test-0000N-of-00002`, and the row index alone would
    collide between them.
    """
    stem = Path(shard_name).stem                      # test-00001-of-00002-<hash>
    parts = stem.split("-")
    shard_no = parts[1] if len(parts) > 1 and parts[1].isdigit() else "0"
    return f"cv_{shard_no}_{row:06d}"


def cv_half(clip_id: str) -> str:
    """'train' or 'measure' — which half of Common Voice a clip belongs to."""
    h = int(hashlib.md5(clip_id.encode("utf-8")).hexdigest()[:8], 16)
    return "train" if h % 2 == 0 else "measure"
