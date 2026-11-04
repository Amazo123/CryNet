# The 25-minute ambient watch, 2026-11-04

The hub, the three cot nodes and the wearable were all on one laptop: the
nodes on a USB hub, the hub and the wearable directly.  The room had people
in it, which is the worst case for a false alarm.

| what | number |
|---|---|
| minutes watched | 20.5 |
| windows scored by the model | 178 |
| **alerts raised** | **0** |
| windows at P(cry) >= 0.99 | 0 |
| windows at P(cry) 0.95-0.99 | 3 |
| windows at P(cry) 0.8-0.95 | 18 |
| windows below 0.8 | 157 |
| bursts completed | 178 |
| resend rounds (stalls) | 347 |
| brownouts or resets | 0 |

The three windows that reached 0.95-0.99, and why they are quiet:

| node | P(cry) | rms | crest |
|---|---|---|---|
| 2 | 0.9805 | 0.0168 | 4.4 |
| 2 | 0.9688 | 0.0232 | 3.3 |
| 3 | 0.9805 | 0.0170 | 3.3 |

The node logs were trimmed: each node prints its rms every 100 ms, and the
lines that matter (the boot banner, the radio counters, the end of the
watch) are kept.

