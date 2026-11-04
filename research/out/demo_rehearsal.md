# The demonstration, dry run

Every clip in the demo kit, played into a quiet room by the node's own trigger, frozen by the hybrid stop-capped rule that is flashed on the bench, and judged by the deployed INT8 model and the hub's gates -- with no sound anywhere.

`gain` is the phone's volume: 1.0 is the level the clip was recorded at, 1.5 and 2.0 are louder.  Only the freezes whose window overlaps the clip are listed; the room freezes windows of its own, and those are not what the demonstration is waiting for.

| clip | gain | frozen at | rms | peak | crest | P(cry) | verdict | after the clip started |
|---|---|---|---|---|---|---|---|---|
| session10_clip_0001.wav | 1.0 | 10.9 | 0.0183 | 2462 | 4.09 | 0.1211 | **no cry** | 2.9 |
| session10_clip_0001.wav | 1.0 | 13.6 | 0.0155 | 2450 | 4.84 | 0.0391 | **no cry** | 5.6 |
| session10_clip_0001.wav | 1.5 | 10.9 | 0.0269 | 3554 | 4.03 | 0.2578 | **no cry** | 2.9 |
| session10_clip_0001.wav | 1.5 | 13.8 | 0.0193 | 3398 | 5.38 | 0.0312 | **no cry** | 5.8 |
| session10_clip_0001.wav | 2.0 | 10.9 | 0.0356 | 4647 | 3.99 | 0.3555 | **no cry** | 2.9 |
| session10_clip_0001.wav | 2.0 | 13.9 | 0.0238 | 4410 | 5.64 | 0.0039 | **no cry** | 5.9 |
| session10_clip_0003.wav | 1.0 | 10.9 | 0.0146 | 1668 | 3.48 | 0.0469 | **no cry** | 2.9 |
| session10_clip_0003.wav | 1.0 | 13.8 | 0.0122 | 1613 | 4.03 | 0.9531 | **no cry** | 5.8 |
| session10_clip_0003.wav | 1.5 | 10.9 | 0.0213 | 2407 | 3.45 | 0.0508 | **no cry** | 2.9 |
| session10_clip_0003.wav | 1.5 | 13.6 | 0.0171 | 2323 | 4.15 | 0.8203 | **no cry** | 5.6 |
| session10_clip_0003.wav | 2.0 | 10.9 | 0.0281 | 3164 | 3.44 | 0.1094 | **no cry** | 2.9 |
| session10_clip_0003.wav | 2.0 | 13.6 | 0.0219 | 3185 | 4.45 | 0.8398 | **no cry** | 5.6 |
| session10_clip_0004.wav | 1.0 | 9.6 | 0.012 | 1916 | 4.88 | 0.8047 | **no cry** | 1.6 |
| session10_clip_0004.wav | 1.0 | 12.8 | 0.0144 | 1495 | 3.18 | 0.7422 | **no cry** | 4.8 |
| session10_clip_0004.wav | 1.5 | 10.9 | 0.0167 | 1587 | 2.9 | 0.9883 | **no cry** | 2.9 |
| session10_clip_0004.wav | 1.5 | 13.6 | 0.0182 | 2041 | 3.42 | 0.0703 | **no cry** | 5.6 |
| session10_clip_0004.wav | 2.0 | 10.9 | 0.0221 | 2030 | 2.8 | 0.9922 | **ANNOUNCES** | 2.9 |
| session10_clip_0004.wav | 2.0 | 13.6 | 0.0231 | 2685 | 3.55 | 0.0781 | **no cry** | 5.6 |
| session10_clip_0006.wav | 1.0 | 9.5 | 0.0106 | 1757 | 5.04 | 0.9219 | **no cry** | 1.5 |
| session10_clip_0006.wav | 1.0 | 12.4 | 0.0129 | 1684 | 3.98 | 0.9961 | **ANNOUNCES** | 4.4 |
| session10_clip_0006.wav | 1.5 | 10.4 | 0.0176 | 2638 | 4.58 | 0.9844 | **no cry** | 2.4 |
| session10_clip_0006.wav | 1.5 | 13.6 | 0.0155 | 1965 | 3.87 | 0.1211 | **no cry** | 5.6 |
| session10_clip_0006.wav | 2.0 | 10.9 | 0.021 | 3372 | 4.91 | 0.9766 | **no cry** | 2.9 |
| session10_clip_0006.wav | 2.0 | 13.6 | 0.0193 | 2609 | 4.12 | 0.2148 | **no cry** | 5.6 |
| session1_clip_0003.wav | 1.0 | 10.9 | 0.061 | 15452 | 7.73 | 0.9961 | **ANNOUNCES** | 2.9 |
| session1_clip_0003.wav | 1.5 | 10.9 | 0.0915 | 23081 | 7.7 | 0.9883 | **no cry** | 2.9 |
| session1_clip_0003.wav | 1.5 | 14.0 | 0.0295 | 15563 | 16.09 | 0.0859 | **no cry** | 6.0 |
| session1_clip_0003.wav | 2.0 | 10.9 | 0.122 | 30710 | 7.68 | 0.9883 | **no cry** | 2.9 |
| session1_clip_0003.wav | 2.0 | 14.0 | 0.0386 | 20781 | 16.44 | 0.0703 | **no cry** | 6.0 |
| session1_clip_0004.wav | 1.0 | 10.9 | 0.1371 | 21991 | 4.9 | 0.9961 | **ANNOUNCES** | 2.9 |
| session1_clip_0004.wav | 1.5 | 10.9 | 0.2055 | 32785 | 4.87 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session1_clip_0004.wav | 2.0 | 10.9 | 0.2737 | 32998 | 3.68 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session1_clip_0005.wav | 1.0 | 10.1 | 0.1254 | 19629 | 4.78 | 0.9961 | **ANNOUNCES** | 2.1 |
| session1_clip_0005.wav | 1.0 | 12.6 | 0.0889 | 13511 | 4.64 | 0.9961 | **ANNOUNCES** | 4.6 |
| session1_clip_0005.wav | 1.5 | 10.1 | 0.1881 | 29380 | 4.77 | 0.9961 | **ANNOUNCES** | 2.1 |
| session1_clip_0005.wav | 1.5 | 12.6 | 0.1332 | 20222 | 4.63 | 0.9961 | **ANNOUNCES** | 4.6 |
| session1_clip_0005.wav | 2.0 | 10.1 | 0.2505 | 32776 | 3.99 | 0.9961 | **CLIPPED (refused)** | 2.1 |
| session1_clip_0005.wav | 2.0 | 12.6 | 0.1775 | 26934 | 4.63 | 0.9961 | **ANNOUNCES** | 4.6 |
| session1_clip_0006.wav | 1.0 | 9.5 | 0.0786 | 15821 | 6.14 | 0.9883 | **no cry** | 1.5 |
| session1_clip_0006.wav | 1.5 | 9.5 | 0.1178 | 23725 | 6.14 | 0.9805 | **no cry** | 1.5 |
| session1_clip_0006.wav | 2.0 | 9.5 | 0.1571 | 31628 | 6.15 | 0.9609 | **CLIPPED (refused)** | 1.5 |
| session4_clip_0002.wav | 1.0 | 10.9 | 0.1048 | 19304 | 5.62 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0002.wav | 1.0 | 13.9 | 0.0612 | 14566 | 7.26 | 0.2812 | **no cry** | 5.9 |
| session4_clip_0002.wav | 1.5 | 10.9 | 0.1572 | 28875 | 5.61 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0002.wav | 1.5 | 13.8 | 0.1001 | 22159 | 6.76 | 0.0508 | **no cry** | 5.8 |
| session4_clip_0002.wav | 2.0 | 10.9 | 0.2096 | 32781 | 4.77 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0002.wav | 2.0 | 13.9 | 0.1226 | 29575 | 7.36 | 0.2812 | **no cry** | 5.9 |
| session4_clip_0005.wav | 1.0 | 10.8 | 0.1161 | 23252 | 6.11 | 0.9961 | **ANNOUNCES** | 2.8 |
| session4_clip_0005.wav | 1.0 | 13.3 | 0.1589 | 28988 | 5.57 | 0.2148 | **no cry** | 5.3 |
| session4_clip_0005.wav | 1.5 | 10.8 | 0.1742 | 32787 | 5.74 | 0.9961 | **CLIPPED (refused)** | 2.8 |
| session4_clip_0005.wav | 1.5 | 13.3 | 0.2367 | 33314 | 4.3 | 0.0859 | **CLIPPED (refused)** | 5.3 |
| session4_clip_0005.wav | 2.0 | 10.8 | 0.2298 | 32911 | 4.37 | 0.9961 | **CLIPPED (refused)** | 2.8 |
| session4_clip_0005.wav | 2.0 | 13.3 | 0.3058 | 33505 | 3.34 | 0.0156 | **CLIPPED (refused)** | 5.3 |
| session4_clip_0007.wav | 1.0 | 10.9 | 0.1576 | 25740 | 4.98 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0007.wav | 1.5 | 10.9 | 0.2361 | 32812 | 4.24 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0007.wav | 1.5 | 14.5 | 0.0308 | 8101 | 8.03 | 0.0078 | **no cry** | 6.5 |
| session4_clip_0007.wav | 2.0 | 10.9 | 0.312 | 32862 | 3.21 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0007.wav | 2.0 | 14.5 | 0.0405 | 10814 | 8.14 | 0.0117 | **no cry** | 6.5 |
| session4_clip_0008.wav | 1.0 | 10.9 | 0.098 | 27376 | 8.53 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0008.wav | 1.0 | 13.4 | 0.1526 | 27601 | 5.52 | 0.9922 | **ANNOUNCES** | 5.4 |
| session4_clip_0008.wav | 1.5 | 10.9 | 0.147 | 33029 | 6.86 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0008.wav | 1.5 | 13.4 | 0.2285 | 33057 | 4.41 | 0.9805 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0008.wav | 2.0 | 10.9 | 0.1956 | 33129 | 5.17 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0008.wav | 2.0 | 13.4 | 0.2984 | 33165 | 3.39 | 0.8906 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0009.wav | 1.0 | 10.8 | 0.1613 | 21137 | 4.0 | 0.9961 | **ANNOUNCES** | 2.8 |
| session4_clip_0009.wav | 1.5 | 10.8 | 0.2419 | 31703 | 4.0 | 0.9961 | **CLIPPED (refused)** | 2.8 |
| session4_clip_0009.wav | 2.0 | 10.8 | 0.322 | 33477 | 3.17 | 0.9961 | **CLIPPED (refused)** | 2.8 |
| session4_clip_0010.wav | 1.0 | 10.9 | 0.1284 | 22506 | 5.35 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0010.wav | 1.5 | 10.9 | 0.1925 | 32834 | 5.2 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0010.wav | 2.0 | 10.9 | 0.2553 | 32846 | 3.93 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0011.wav | 1.0 | 9.4 | 0.1096 | 18235 | 5.08 | 0.9609 | **no cry** | 1.4 |
| session4_clip_0011.wav | 1.5 | 9.4 | 0.1643 | 27319 | 5.07 | 0.9219 | **no cry** | 1.4 |
| session4_clip_0011.wav | 2.0 | 9.4 | 0.219 | 32889 | 4.58 | 0.8516 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0011.wav | 2.0 | 11.9 | 0.0819 | 32776 | 12.21 | 0.0078 | **CLIPPED (refused)** | 3.9 |
| session4_clip_0012.wav | 1.0 | 10.5 | 0.0547 | 14166 | 7.9 | 0.9961 | **ANNOUNCES** | 2.5 |
| session4_clip_0012.wav | 1.5 | 10.5 | 0.0821 | 21175 | 7.87 | 0.9961 | **ANNOUNCES** | 2.5 |
| session4_clip_0012.wav | 2.0 | 10.5 | 0.1095 | 28185 | 7.86 | 0.9961 | **ANNOUNCES** | 2.5 |
| session4_clip_0016.wav | 1.0 | 10.5 | 0.1842 | 26996 | 4.47 | 0.9961 | **ANNOUNCES** | 2.5 |
| session4_clip_0016.wav | 1.0 | 13.0 | 0.129 | 25668 | 6.07 | 0.3555 | **no cry** | 5.0 |
| session4_clip_0016.wav | 1.5 | 10.5 | 0.2756 | 32825 | 3.63 | 0.9961 | **CLIPPED (refused)** | 2.5 |
| session4_clip_0016.wav | 1.5 | 13.0 | 0.1931 | 32884 | 5.2 | 0.2578 | **CLIPPED (refused)** | 5.0 |
| session4_clip_0016.wav | 2.0 | 10.5 | 0.3574 | 32839 | 2.8 | 0.9961 | **CLIPPED (refused)** | 2.5 |
| session4_clip_0016.wav | 2.0 | 13.0 | 0.2504 | 32866 | 4.01 | 0.0352 | **CLIPPED (refused)** | 5.0 |
| session4_clip_0019.wav | 1.0 | 9.5 | 0.0906 | 25441 | 8.57 | 0.7656 | **no cry** | 1.5 |
| session4_clip_0019.wav | 1.0 | 12.2 | 0.1233 | 20480 | 5.07 | 0.9961 | **ANNOUNCES** | 4.2 |
| session4_clip_0019.wav | 1.5 | 9.5 | 0.1357 | 32788 | 7.38 | 0.4688 | **CLIPPED (refused)** | 1.5 |
| session4_clip_0019.wav | 1.5 | 12.2 | 0.1848 | 30925 | 5.11 | 0.9961 | **ANNOUNCES** | 4.2 |
| session4_clip_0019.wav | 2.0 | 9.5 | 0.178 | 32804 | 5.62 | 0.2148 | **CLIPPED (refused)** | 1.5 |
| session4_clip_0019.wav | 2.0 | 12.3 | 0.2332 | 33005 | 4.32 | 0.9961 | **CLIPPED (refused)** | 4.3 |
| session4_clip_0020.wav | 1.0 | 10.9 | 0.1722 | 23584 | 4.18 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0020.wav | 1.0 | 13.4 | 0.1879 | 27041 | 4.39 | 0.9961 | **ANNOUNCES** | 5.4 |
| session4_clip_0020.wav | 1.5 | 10.9 | 0.2582 | 32782 | 3.88 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0020.wav | 1.5 | 13.4 | 0.2813 | 32782 | 3.56 | 0.9961 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0020.wav | 2.0 | 10.9 | 0.3411 | 32779 | 2.93 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0020.wav | 2.0 | 13.4 | 0.3673 | 32780 | 2.72 | 0.9961 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0021.wav | 1.0 | 9.4 | 0.1316 | 32535 | 7.55 | 0.0156 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0021.wav | 1.0 | 11.9 | 0.1365 | 21251 | 4.75 | 0.9961 | **ANNOUNCES** | 3.9 |
| session4_clip_0021.wav | 1.5 | 9.4 | 0.1967 | 32806 | 5.09 | 0.0117 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0021.wav | 1.5 | 11.9 | 0.2046 | 31899 | 4.76 | 0.9961 | **CLIPPED (refused)** | 3.9 |
| session4_clip_0021.wav | 2.0 | 9.4 | 0.2553 | 32830 | 3.92 | 0.0039 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0021.wav | 2.0 | 12.2 | 0.2821 | 32912 | 3.56 | 0.9961 | **CLIPPED (refused)** | 4.2 |
| session4_clip_0022.wav | 1.0 | 9.4 | 0.1096 | 22482 | 6.26 | 0.9492 | **no cry** | 1.4 |
| session4_clip_0022.wav | 1.0 | 13.0 | 0.2054 | 23215 | 3.45 | 0.9961 | **ANNOUNCES** | 5.0 |
| session4_clip_0022.wav | 1.5 | 9.4 | 0.1643 | 32756 | 6.08 | 0.9297 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0022.wav | 1.5 | 13.0 | 0.308 | 32895 | 3.26 | 0.9922 | **CLIPPED (refused)** | 5.0 |
| session4_clip_0022.wav | 2.0 | 9.4 | 0.2175 | 32780 | 4.6 | 0.8398 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0022.wav | 2.0 | 13.0 | 0.4079 | 32895 | 2.46 | 0.9922 | **CLIPPED (refused)** | 5.0 |
| session4_clip_0024.wav | 1.0 | 10.9 | 0.1378 | 18822 | 4.17 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0024.wav | 1.0 | 13.4 | 0.1398 | 20756 | 4.53 | 0.9297 | **no cry** | 5.4 |
| session4_clip_0024.wav | 1.5 | 10.9 | 0.2067 | 28162 | 4.16 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0024.wav | 1.5 | 13.4 | 0.2095 | 31100 | 4.53 | 0.7422 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0024.wav | 2.0 | 10.9 | 0.2754 | 32849 | 3.64 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0024.wav | 2.0 | 13.4 | 0.2786 | 33101 | 3.63 | 0.6172 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0028.wav | 1.0 | 9.8 | 0.1263 | 22250 | 5.38 | 0.9219 | **no cry** | 1.8 |
| session4_clip_0028.wav | 1.5 | 9.8 | 0.1894 | 32654 | 5.26 | 0.8203 | **CLIPPED (refused)** | 1.8 |
| session4_clip_0028.wav | 2.0 | 9.8 | 0.2515 | 32776 | 3.98 | 0.8203 | **CLIPPED (refused)** | 1.8 |
| session4_clip_0030.wav | 1.0 | 9.5 | 0.0786 | 18519 | 7.19 | 0.2812 | **no cry** | 1.5 |
| session4_clip_0030.wav | 1.0 | 12.3 | 0.0672 | 17915 | 8.13 | 0.0195 | **no cry** | 4.3 |
| session4_clip_0030.wav | 1.5 | 9.5 | 0.1179 | 27830 | 7.21 | 0.1094 | **no cry** | 1.5 |
| session4_clip_0030.wav | 1.5 | 12.3 | 0.1006 | 26679 | 8.1 | 0.0195 | **no cry** | 4.3 |
| session4_clip_0030.wav | 2.0 | 9.5 | 0.1571 | 32895 | 6.39 | 0.0781 | **CLIPPED (refused)** | 1.5 |
| session4_clip_0030.wav | 2.0 | 12.3 | 0.1339 | 32634 | 7.44 | 0.0234 | **CLIPPED (refused)** | 4.3 |
| session4_clip_0034.wav | 1.0 | 10.7 | 0.1224 | 21687 | 5.41 | 0.9961 | **ANNOUNCES** | 2.7 |
| session4_clip_0034.wav | 1.5 | 10.7 | 0.1836 | 32515 | 5.41 | 0.9961 | **CLIPPED (refused)** | 2.7 |
| session4_clip_0034.wav | 2.0 | 10.8 | 0.231 | 32828 | 4.34 | 0.9961 | **CLIPPED (refused)** | 2.8 |
| session4_clip_0035.wav | 1.0 | 10.4 | 0.1594 | 24064 | 4.61 | 0.9961 | **ANNOUNCES** | 2.4 |
| session4_clip_0035.wav | 1.0 | 13.1 | 0.1625 | 25460 | 4.78 | 0.9961 | **ANNOUNCES** | 5.1 |
| session4_clip_0035.wav | 1.5 | 10.4 | 0.2391 | 32830 | 4.19 | 0.9961 | **CLIPPED (refused)** | 2.4 |
| session4_clip_0035.wav | 1.5 | 13.1 | 0.2436 | 32883 | 4.12 | 0.9961 | **CLIPPED (refused)** | 5.1 |
| session4_clip_0035.wav | 2.0 | 10.9 | 0.3206 | 32849 | 3.13 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0035.wav | 2.0 | 13.4 | 0.2902 | 32823 | 3.45 | 0.9883 | **CLIPPED (refused)** | 5.4 |
| session4_clip_0036.wav | 1.0 | 9.4 | 0.0793 | 23270 | 8.96 | 0.0859 | **no cry** | 1.4 |
| session4_clip_0036.wav | 1.0 | 12.0 | 0.1043 | 18187 | 5.32 | 0.9961 | **ANNOUNCES** | 4.0 |
| session4_clip_0036.wav | 1.5 | 9.4 | 0.1188 | 32765 | 8.42 | 0.0195 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0036.wav | 1.5 | 12.0 | 0.1563 | 27283 | 5.33 | 0.9961 | **ANNOUNCES** | 4.0 |
| session4_clip_0036.wav | 2.0 | 9.4 | 0.1552 | 32773 | 6.44 | 0.0117 | **CLIPPED (refused)** | 1.4 |
| session4_clip_0036.wav | 2.0 | 12.0 | 0.2083 | 32878 | 4.82 | 0.9961 | **CLIPPED (refused)** | 4.0 |
| session4_clip_0037.wav | 1.0 | 11.1 | 0.1796 | 23965 | 4.07 | 0.9961 | **ANNOUNCES** | 3.1 |
| session4_clip_0037.wav | 1.5 | 11.1 | 0.2693 | 32784 | 3.72 | 0.9961 | **CLIPPED (refused)** | 3.1 |
| session4_clip_0037.wav | 2.0 | 11.1 | 0.3566 | 32777 | 2.81 | 0.9961 | **CLIPPED (refused)** | 3.1 |
| session4_clip_0038.wav | 1.0 | 10.9 | 0.08 | 17128 | 6.53 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0038.wav | 1.5 | 10.9 | 0.1199 | 25613 | 6.52 | 0.9961 | **ANNOUNCES** | 2.9 |
| session4_clip_0038.wav | 2.0 | 10.9 | 0.1598 | 32691 | 6.24 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session4_clip_0039.wav | 1.0 | 10.5 | 0.25 | 32379 | 3.95 | 0.9961 | **CLIPPED (refused)** | 2.5 |
| session4_clip_0039.wav | 1.0 | 13.1 | 0.3294 | 33195 | 3.08 | 0.0625 | **CLIPPED (refused)** | 5.1 |
| session4_clip_0039.wav | 1.5 | 10.5 | 0.3659 | 32796 | 2.74 | 0.9961 | **CLIPPED (refused)** | 2.5 |
| session4_clip_0039.wav | 1.5 | 13.1 | 0.4516 | 33345 | 2.25 | 0.0273 | **CLIPPED (refused)** | 5.1 |
| session4_clip_0039.wav | 2.0 | 10.6 | 0.4371 | 32800 | 2.29 | 0.9023 | **CLIPPED (refused)** | 2.6 |
| session4_clip_0039.wav | 2.0 | 13.1 | 0.5247 | 33501 | 1.95 | 0.0859 | **CLIPPED (refused)** | 5.1 |
| session4_clip_0040.wav | 1.0 | 9.7 | 0.1731 | 32946 | 5.81 | 0.9805 | **CLIPPED (refused)** | 1.7 |
| session4_clip_0040.wav | 1.0 | 12.8 | 0.1357 | 30096 | 6.77 | 0.9961 | **ANNOUNCES** | 4.8 |
| session4_clip_0040.wav | 1.5 | 9.7 | 0.2506 | 33176 | 4.04 | 0.9023 | **CLIPPED (refused)** | 1.7 |
| session4_clip_0040.wav | 1.5 | 13.1 | 0.2205 | 32853 | 4.55 | 0.9961 | **CLIPPED (refused)** | 5.1 |
| session4_clip_0040.wav | 2.0 | 9.7 | 0.3124 | 33283 | 3.25 | 0.8047 | **CLIPPED (refused)** | 1.7 |
| session4_clip_0040.wav | 2.0 | 13.1 | 0.2864 | 32852 | 3.5 | 0.9922 | **CLIPPED (refused)** | 5.1 |
| session9_clip_0001.wav | 1.0 | 10.9 | 0.0212 | 5440 | 7.84 | 0.9297 | **no cry** | 2.9 |
| session9_clip_0001.wav | 1.0 | 13.6 | 0.018 | 2262 | 3.84 | 0.2148 | **no cry** | 5.6 |
| session9_clip_0001.wav | 1.5 | 10.9 | 0.0312 | 8109 | 7.93 | 0.9023 | **no cry** | 2.9 |
| session9_clip_0001.wav | 1.5 | 13.5 | 0.027 | 3458 | 3.91 | 0.6953 | **no cry** | 5.5 |
| session9_clip_0001.wav | 2.0 | 10.9 | 0.0413 | 10777 | 7.97 | 0.8789 | **no cry** | 2.9 |
| session9_clip_0001.wav | 2.0 | 13.4 | 0.0364 | 4635 | 3.89 | 0.6445 | **no cry** | 5.4 |
| session9_clip_0005.wav | 1.0 | 10.9 | 0.0793 | 12808 | 4.93 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0005.wav | 1.0 | 13.4 | 0.042 | 13145 | 9.54 | 0.1094 | **no cry** | 5.4 |
| session9_clip_0005.wav | 1.5 | 10.9 | 0.1186 | 19180 | 4.94 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0005.wav | 1.5 | 13.4 | 0.0626 | 19828 | 9.66 | 0.0469 | **no cry** | 5.4 |
| session9_clip_0005.wav | 2.0 | 10.9 | 0.1579 | 25552 | 4.94 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0005.wav | 2.0 | 13.4 | 0.0834 | 26511 | 9.71 | 0.0273 | **no cry** | 5.4 |
| session9_clip_0006.wav | 1.0 | 10.9 | 0.1002 | 18663 | 5.68 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0006.wav | 1.0 | 13.4 | 0.1231 | 20101 | 4.98 | 0.9961 | **ANNOUNCES** | 5.4 |
| session9_clip_0006.wav | 1.5 | 10.9 | 0.1503 | 27941 | 5.67 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0006.wav | 1.5 | 13.4 | 0.1843 | 30184 | 5.0 | 0.9961 | **ANNOUNCES** | 5.4 |
| session9_clip_0006.wav | 2.0 | 10.9 | 0.2004 | 32745 | 4.99 | 0.9961 | **CLIPPED (refused)** | 2.9 |
| session9_clip_0006.wav | 2.0 | 13.4 | 0.2447 | 33494 | 4.18 | 0.9961 | **CLIPPED (refused)** | 5.4 |
| session9_clip_0007.wav | 1.0 | 10.0 | 0.0819 | 16080 | 5.99 | 0.9961 | **ANNOUNCES** | 2.0 |
| session9_clip_0007.wav | 1.0 | 13.1 | 0.1006 | 15200 | 4.61 | 0.9961 | **ANNOUNCES** | 5.1 |
| session9_clip_0007.wav | 1.5 | 10.0 | 0.1231 | 24097 | 5.98 | 0.9961 | **ANNOUNCES** | 2.0 |
| session9_clip_0007.wav | 1.5 | 13.1 | 0.1505 | 22788 | 4.62 | 0.9961 | **ANNOUNCES** | 5.1 |
| session9_clip_0007.wav | 2.0 | 10.9 | 0.1512 | 29316 | 5.92 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0007.wav | 2.0 | 13.4 | 0.1629 | 31449 | 5.89 | 0.8789 | **CLIPPED (refused)** | 5.4 |
| session9_clip_0008.wav | 1.0 | 10.9 | 0.1388 | 24496 | 5.38 | 0.9805 | **no cry** | 2.9 |
| session9_clip_0008.wav | 1.0 | 13.4 | 0.1128 | 15077 | 4.08 | 0.8789 | **no cry** | 5.4 |
| session9_clip_0008.wav | 1.5 | 10.9 | 0.208 | 32868 | 4.82 | 0.9844 | **CLIPPED (refused)** | 2.9 |
| session9_clip_0008.wav | 1.5 | 13.4 | 0.1689 | 22462 | 4.06 | 0.8398 | **no cry** | 5.4 |
| session9_clip_0008.wav | 2.0 | 10.9 | 0.2756 | 32897 | 3.64 | 0.9648 | **CLIPPED (refused)** | 2.9 |
| session9_clip_0008.wav | 2.0 | 13.4 | 0.2251 | 29848 | 4.05 | 0.7188 | **no cry** | 5.4 |
| session9_clip_0010.wav | 1.0 | 10.9 | 0.0895 | 12283 | 4.19 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0010.wav | 1.0 | 13.4 | 0.1193 | 18085 | 4.63 | 0.9961 | **ANNOUNCES** | 5.4 |
| session9_clip_0010.wav | 1.5 | 10.9 | 0.1342 | 18447 | 4.19 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0010.wav | 1.5 | 13.4 | 0.179 | 27067 | 4.61 | 0.9961 | **ANNOUNCES** | 5.4 |
| session9_clip_0010.wav | 2.0 | 10.9 | 0.179 | 24612 | 4.2 | 0.9961 | **ANNOUNCES** | 2.9 |
| session9_clip_0010.wav | 2.0 | 13.4 | 0.2387 | 33078 | 4.23 | 0.9922 | **CLIPPED (refused)** | 5.4 |

## At the recorded level: **27 of 37 clips announce** under the rule that is on the boards.

The clips that do not:

- `session10_clip_0001.wav` — no cry (rms 0.0183, peak 2462, P 0.1211)
- `session10_clip_0001.wav` — no cry (rms 0.0155, peak 2450, P 0.0391)
- `session10_clip_0003.wav` — no cry (rms 0.0146, peak 1668, P 0.0469)
- `session10_clip_0003.wav` — no cry (rms 0.0122, peak 1613, P 0.9531)
- `session10_clip_0004.wav` — no cry (rms 0.012, peak 1916, P 0.8047)
- `session10_clip_0004.wav` — no cry (rms 0.0144, peak 1495, P 0.7422)
- `session1_clip_0006.wav` — no cry (rms 0.0786, peak 15821, P 0.9883)
- `session4_clip_0011.wav` — no cry (rms 0.1096, peak 18235, P 0.9609)
- `session4_clip_0028.wav` — no cry (rms 0.1263, peak 22250, P 0.9219)
- `session4_clip_0030.wav` — no cry (rms 0.0786, peak 18519, P 0.2812)
- `session4_clip_0030.wav` — no cry (rms 0.0672, peak 17915, P 0.0195)
- `session4_clip_0039.wav` — CLIPPED (refused) (rms 0.25, peak 32379, P 0.9961)
- `session4_clip_0039.wav` — CLIPPED (refused) (rms 0.3294, peak 33195, P 0.0625)
- `session9_clip_0001.wav` — no cry (rms 0.0212, peak 5440, P 0.9297)
- `session9_clip_0001.wav` — no cry (rms 0.018, peak 2262, P 0.2148)
- `session9_clip_0008.wav` — no cry (rms 0.1388, peak 24496, P 0.9805)
- `session9_clip_0008.wav` — no cry (rms 0.1128, peak 15077, P 0.8789)

## The gain sweep

| clip | 1.0 | 1.5 | 2.0 |
|---|---|---|---|
| session10_clip_0001.wav | no cry | no cry | no cry |
| session10_clip_0003.wav | no cry | no cry | no cry |
| session10_clip_0004.wav | no cry | no cry | **announces** |
| session10_clip_0006.wav | **announces** | no cry | no cry |
| session1_clip_0003.wav | **announces** | no cry | no cry |
| session1_clip_0004.wav | **announces** | clipped | clipped |
| session1_clip_0005.wav | **announces** | **announces** | **announces** |
| session1_clip_0006.wav | no cry | no cry | clipped |
| session4_clip_0002.wav | **announces** | **announces** | clipped |
| session4_clip_0005.wav | **announces** | clipped | clipped |
| session4_clip_0007.wav | **announces** | clipped | clipped |
| session4_clip_0008.wav | **announces** | clipped | clipped |
| session4_clip_0009.wav | **announces** | clipped | clipped |
| session4_clip_0010.wav | **announces** | clipped | clipped |
| session4_clip_0011.wav | no cry | no cry | clipped |
| session4_clip_0012.wav | **announces** | **announces** | **announces** |
| session4_clip_0016.wav | **announces** | clipped | clipped |
| session4_clip_0019.wav | **announces** | **announces** | clipped |
| session4_clip_0020.wav | **announces** | clipped | clipped |
| session4_clip_0021.wav | **announces** | clipped | clipped |
| session4_clip_0022.wav | **announces** | clipped | clipped |
| session4_clip_0024.wav | **announces** | **announces** | clipped |
| session4_clip_0028.wav | no cry | clipped | clipped |
| session4_clip_0030.wav | no cry | no cry | clipped |
| session4_clip_0034.wav | **announces** | clipped | clipped |
| session4_clip_0035.wav | **announces** | clipped | clipped |
| session4_clip_0036.wav | **announces** | **announces** | clipped |
| session4_clip_0037.wav | **announces** | clipped | clipped |
| session4_clip_0038.wav | **announces** | **announces** | clipped |
| session4_clip_0039.wav | clipped | clipped | clipped |
| session4_clip_0040.wav | **announces** | clipped | clipped |
| session9_clip_0001.wav | no cry | no cry | no cry |
| session9_clip_0005.wav | **announces** | **announces** | **announces** |
| session9_clip_0006.wav | **announces** | **announces** | clipped |
| session9_clip_0007.wav | **announces** | **announces** | **announces** |
| session9_clip_0008.wav | no cry | clipped | clipped |
| session9_clip_0010.wav | **announces** | **announces** | **announces** |
