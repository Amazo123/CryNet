# What each freeze rule scores on a yelp

The window is padded with silence where the clip is shorter than two seconds -- that is what the node's ring holds when the room is quiet.

| clip | placement | rms | peak | crest | P(cry) | announces (quiet rule 0.99) |
|---|---|---|---|---|---|---|
| yelp_1.5s.wav | after-peak | 0.0446 | 12980 | 8.9 | 0.0039 | no |
| yelp_1.5s.wav | stop-capped | 0.0533 | 12965 | 7.4 | 0.3047 | no |
| yelp_1.5s.wav | peak-centred | 0.0533 | 12965 | 7.4 | 0.3047 | no |

| yelp_1.7s.wav | after-peak | 0.0493 | 12863 | 8.0 | 0.0508 | no |
| yelp_1.7s.wav | stop-capped | 0.0573 | 12849 | 6.8 | 0.9023 | no |
| yelp_1.7s.wav | peak-centred | 0.0573 | 12849 | 6.8 | 0.9023 | no |

| yelp_2.0s.wav | after-peak | 0.0229 | 12842 | 17.1 | 0.0234 | no |
| yelp_2.0s.wav | stop-capped | 0.0682 | 13160 | 5.9 | 0.9961 | yes |
| yelp_2.0s.wav | peak-centred | 0.0519 | 13202 | 7.8 | 0.0039 | no |

| session9_clip_0005.wav | after-peak | 0.0313 | 13144 | 12.8 | 0.0039 | no |
| session9_clip_0005.wav | stop-capped | 0.0530 | 13128 | 7.6 | 0.9648 | loud rule |
| session9_clip_0005.wav | peak-centred | 0.0492 | 13136 | 8.2 | 0.1953 | no |

