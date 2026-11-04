# The after-peak freeze, simulated over the corpus

Every frozen window the node would hand over, scored with the deployed INT8 model and put through the hub's gates.

| rule | label | windows | announced | rate | loudest P | worst rms |
|---|---|---|---|---|---|---|
| new | cry | 172 | 42 | 24.4 % | 0.9961 | 0.3076 |
| new | room | 69 | 0 | 0.0 % | 0.4141 | 0.0308 |
| new | unlabelled | 8 | 0 | 0.0 % | 0.0352 | 0.0219 |
| hybrid | cry | 219 | 53 | 24.2 % | 0.9961 | 0.3132 |
| hybrid | room | 100 | 0 | 0.0 % | 0.8516 | 0.0350 |
| hybrid | unlabelled | 11 | 0 | 0.0 % | 0.0508 | 0.0255 |
| old | cry | 230 | 52 | 22.6 % | 0.9961 | 0.3013 |
| old | room | 104 | 0 | 0.0 % | 0.7656 | 0.0277 |
| old | unlabelled | 12 | 0 | 0.0 % | 0.0625 | 0.0172 |

## Episode level: did the cot that heard the cry say so?

For every cry clip (one cry = one episode) the window the node freezes first over that clip is the one that decides the alert.

| rule | cry episodes | first window announced | none announced | no window at all |
|---|---|---|---|---|
| new | 273 | 41 | 125 | 107 |
| hybrid | 294 | 52 | 158 | 84 |
| old | 297 | 52 | 172 | 73 |

**new rule:** 0 of 69 room windows announced (0 of those room windows were loud enough for the 0.95 rule); 42 of 172 cry windows announced.

**hybrid rule:** 0 of 100 room windows announced (0 of those room windows were loud enough for the 0.95 rule); 53 of 219 cry windows announced.

**old rule:** 0 of 104 room windows announced (0 of those room windows were loud enough for the 0.95 rule); 52 of 230 cry windows announced.

