# Clip screening — what the deployed model will announce

Scored with the deployed INT8 model and the notebook's own front end.
A clip is **demo-ready** when one of its 2 s windows reaches P(cry) >= 0.99 — that is the hub's single-window announce bar.

| session | clip | windows | best P | best P (100 Hz HP) | announce | maybe | rms | crest |
|---|---|---|---|---|---|---|---|---|
| session1 | **clip_0000.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1237 | 5.5 |
| session1 | **clip_0001.wav** | 4 | 0.9961 | 0.9961 | 1 | 1 | 0.0758 | 7.7 |
| session1 | **clip_0002.wav** | 4 | 0.9961 | 0.9961 | 1 | 0 | 0.1087 | 4.9 |
| session1 | **clip_0003.wav** | 4 | 0.9961 | 0.9961 | 2 | 2 | 0.1170 | 6.8 |
| session1 | **clip_0004.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1230 | 5.3 |
| session1 | **clip_0005.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1265 | 4.7 |
| session1 | **clip_0006.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.0805 | 6.0 |
| session1 | **clip_0007.wav** | 4 | 0.9961 | 0.9961 | 1 | 0 | 0.0573 | 4.8 |
| session10 | clip_0000.wav | 4 | 0.9883 | 0.9961 | 0 | 2 | 0.0420 | 3.4 |
| session10 | **clip_0001.wav** | 4 | 0.9961 | 0.9961 | 2 | 0 | 0.0168 | 4.0 |
| session10 | **clip_0003.wav** | 4 | 0.9961 | 0.9961 | 2 | 0 | 0.0162 | 3.8 |
| session10 | **clip_0004.wav** | 4 | 0.9961 | 0.9961 | 1 | 1 | 0.0127 | 4.1 |
| session10 | clip_0005.wav | 4 | 0.9727 | 0.9961 | 0 | 1 | 0.0116 | 4.0 |
| session10 | **clip_0006.wav** | 4 | 0.9961 | 0.9961 | 2 | 1 | 0.0117 | 4.8 |
| session10 | clip_0007.wav | 4 | 0.1484 | 0.9961 | 0 | 0 | 0.0125 | 4.2 |
| session10 | clip_0008.wav | 4 | 0.2812 | 0.9961 | 0 | 0 | 0.0111 | 4.7 |
| session10 | clip_0009.wav | 4 | 0.9141 | 0.9961 | 0 | 0 | 0.0130 | 4.0 |
| session10 | **clip_0010.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.0100 | 4.6 |
| session4 | **clip_0002.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1069 | 5.5 |
| session4 | **clip_0003.wav** | 4 | 0.9922 | 0.9961 | 1 | 1 | 0.1007 | 8.2 |
| session4 | **clip_0004.wav** | 4 | 0.9922 | 0.9961 | 1 | 1 | 0.1428 | 4.8 |
| session4 | **clip_0005.wav** | 4 | 0.9961 | 0.9961 | 2 | 1 | 0.1144 | 6.2 |
| session4 | **clip_0006.wav** | 4 | 0.9961 | 0.9961 | 3 | 0 | 0.1077 | 6.4 |
| session4 | **clip_0007.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1598 | 4.9 |
| session4 | **clip_0008.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.0902 | 6.4 |
| session4 | **clip_0009.wav** | 4 | 0.9961 | 0.9961 | 2 | 2 | 0.1811 | 3.6 |
| session4 | **clip_0010.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.0729 | 6.9 |
| session4 | **clip_0011.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1097 | 5.0 |
| session4 | **clip_0012.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.0590 | 7.2 |
| session4 | clip_0014.wav | 4 | 0.9492 | 0.9961 | 0 | 0 | 0.1408 | 5.1 |
| session4 | clip_0015.wav | 4 | 0.9805 | 0.9961 | 0 | 1 | 0.2207 | 4.3 |
| session4 | **clip_0016.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1671 | 5.0 |
| session4 | **clip_0018.wav** | 4 | 0.9961 | 0.9961 | 1 | 1 | 0.1823 | 5.3 |
| session4 | **clip_0019.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1011 | 7.7 |
| session4 | **clip_0020.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1796 | 4.4 |
| session4 | **clip_0021.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1358 | 7.3 |
| session4 | **clip_0022.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1352 | 6.6 |
| session4 | **clip_0023.wav** | 4 | 0.9922 | 0.9961 | 1 | 1 | 0.0893 | 6.5 |
| session4 | **clip_0024.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1763 | 3.7 |
| session4 | **clip_0025.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1191 | 5.6 |
| session4 | **clip_0026.wav** | 4 | 0.9961 | 0.9961 | 1 | 1 | 0.1254 | 4.3 |
| session4 | **clip_0028.wav** | 4 | 0.9961 | 0.9961 | 1 | 0 | 0.1263 | 5.4 |
| session4 | **clip_0029.wav** | 4 | 0.9961 | 0.9961 | 2 | 0 | 0.1598 | 4.3 |
| session4 | **clip_0030.wav** | 4 | 0.9961 | 0.9961 | 1 | 1 | 0.0976 | 5.8 |
| session4 | clip_0031.wav | 4 | 0.9453 | 0.9961 | 0 | 0 | 0.1214 | 4.5 |
| session4 | **clip_0033.wav** | 4 | 0.9961 | 0.9961 | 1 | 0 | 0.1459 | 5.5 |
| session4 | **clip_0034.wav** | 4 | 0.9961 | 0.9961 | 2 | 1 | 0.1397 | 5.9 |
| session4 | **clip_0035.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1772 | 4.2 |
| session4 | **clip_0036.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1114 | 6.4 |
| session4 | **clip_0037.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1486 | 4.9 |
| session4 | **clip_0038.wav** | 4 | 0.9961 | 0.9961 | 2 | 1 | 0.0796 | 6.6 |
| session4 | **clip_0039.wav** | 4 | 0.9961 | 0.9961 | 2 | 0 | 0.2825 | 3.5 |
| session4 | **clip_0040.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1732 | 5.8 |
| session4 | clip_0044.wav | 4 | 0.9766 | 0.9961 | 0 | 1 | 0.3165 | 3.2 |
| session9 | **clip_0000.wav** | 4 | 0.9961 | 0.9961 | 2 | 1 | 0.0533 | 4.2 |
| session9 | **clip_0002.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.2053 | 4.8 |
| session9 | **clip_0003.wav** | 4 | 0.9961 | 0.9961 | 3 | 0 | 0.0502 | 9.7 |
| session9 | **clip_0004.wav** | 4 | 0.9961 | 0.9961 | 2 | 0 | 0.0665 | 5.7 |
| session9 | **clip_0005.wav** | 4 | 0.9961 | 0.9961 | 2 | 2 | 0.0683 | 5.8 |
| session9 | **clip_0006.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.0922 | 5.0 |
| session9 | **clip_0007.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.0824 | 5.7 |
| session9 | **clip_0008.wav** | 4 | 0.9961 | 0.9961 | 3 | 1 | 0.1266 | 5.9 |
| session9 | **clip_0009.wav** | 4 | 0.9961 | 0.9961 | 2 | 2 | 0.0515 | 8.5 |
| session9 | **clip_0010.wav** | 4 | 0.9961 | 0.9961 | 4 | 0 | 0.1180 | 3.9 |
| session4 | clip_0017.wav | 4 | 0.9375 | 0.9922 | 0 | 0 | 0.1784 | 4.6 |
| session9 | **clip_0001.wav** | 4 | 0.9922 | 0.9922 | 2 | 1 | 0.0242 | 4.8 |
| session10 | clip_0002.wav | 4 | 0.0703 | 0.9883 | 0 | 0 | 0.0118 | 4.5 |
| session4 | clip_0032.wav | 4 | 0.9023 | 0.9883 | 0 | 0 | 0.1265 | 5.7 |
| session4 | clip_0042.wav | 4 | 0.4414 | 0.9805 | 0 | 0 | 0.2236 | 4.5 |
| session4 | clip_0041.wav | 4 | 0.9141 | 0.9727 | 0 | 0 | 0.2711 | 3.7 |
| session4 | clip_0043.wav | 4 | 0.9297 | 0.9727 | 0 | 0 | 0.1638 | 6.1 |
| session2 | clip_0046.wav | 4 | 0.3320 | 0.9609 | 0 | 0 | 0.0014 | 7.5 |
| session2 | clip_0028.wav | 4 | 0.5312 | 0.9375 | 0 | 0 | 0.0097 | 2.8 |
| session8 | clip_0001.wav | 4 | 0.8906 | 0.2578 | 0 | 0 | 0.0084 | 5.8 |
| session2 | clip_0024.wav | 4 | 0.6953 | 0.8672 | 0 | 0 | 0.0089 | 3.0 |
| session4 | clip_0013.wav | 4 | 0.1094 | 0.8516 | 0 | 0 | 0.0249 | 20.6 |
| session2 | clip_0007.wav | 4 | 0.1211 | 0.8398 | 0 | 0 | 0.0177 | 2.4 |
| session4 | clip_0027.wav | 4 | 0.1484 | 0.8203 | 0 | 0 | 0.0852 | 7.4 |
| session4 | clip_0045.wav | 4 | 0.1797 | 0.8047 | 0 | 0 | 0.2055 | 4.9 |
| session2 | clip_0001.wav | 4 | 0.1602 | 0.7852 | 0 | 0 | 0.0080 | 2.4 |
| session2 | clip_0002.wav | 4 | 0.1953 | 0.7852 | 0 | 0 | 0.0085 | 2.2 |
| session2 | clip_0013.wav | 4 | 0.2578 | 0.7852 | 0 | 0 | 0.0076 | 4.7 |
| session2 | clip_0018.wav | 4 | 0.1484 | 0.7852 | 0 | 0 | 0.0081 | 2.8 |
| session2 | clip_0038.wav | 4 | 0.1602 | 0.7852 | 0 | 0 | 0.0053 | 10.8 |
| session8 | clip_0008.wav | 4 | 0.0234 | 0.7656 | 0 | 0 | 0.0118 | 5.5 |
| session4 | clip_0000.wav | 4 | 0.0312 | 0.7422 | 0 | 0 | 0.0702 | 2.8 |
| session4 | clip_0046.wav | 4 | 0.1328 | 0.7422 | 0 | 0 | 0.2355 | 4.2 |
| session4 | clip_0053.wav | 4 | 0.5312 | 0.7422 | 0 | 0 | 0.0097 | 10.7 |
| session8 | clip_0006.wav | 4 | 0.1953 | 0.7422 | 0 | 0 | 0.0122 | 4.5 |
| session2 | clip_0003.wav | 4 | 0.1328 | 0.7188 | 0 | 0 | 0.0071 | 2.4 |
| session2 | clip_0006.wav | 4 | 0.0391 | 0.7188 | 0 | 0 | 0.0092 | 2.5 |
| session2 | clip_0009.wav | 4 | 0.5859 | 0.7188 | 0 | 0 | 0.0100 | 8.0 |
| session2 | clip_0014.wav | 4 | 0.6953 | 0.5859 | 0 | 0 | 0.0027 | 5.2 |
| session4 | clip_0001.wav | 4 | 0.0273 | 0.6953 | 0 | 0 | 0.0445 | 13.6 |
| session2 | clip_0036.wav | 4 | 0.0703 | 0.6680 | 0 | 0 | 0.0088 | 2.2 |
| session5 | clip_0001.wav | 4 | 0.1797 | 0.6680 | 0 | 0 | 0.0041 | 2.5 |
| session5 | clip_0010.wav | 4 | 0.0312 | 0.6445 | 0 | 0 | 0.0065 | 3.2 |
| session8 | clip_0007.wav | 4 | 0.6445 | 0.3555 | 0 | 0 | 0.0123 | 4.6 |
| session2 | clip_0037.wav | 4 | 0.0781 | 0.6172 | 0 | 0 | 0.0212 | 2.1 |
| session5 | clip_0000.wav | 4 | 0.2148 | 0.6172 | 0 | 0 | 0.0038 | 3.7 |
| session5 | clip_0003.wav | 4 | 0.4688 | 0.6172 | 0 | 0 | 0.0055 | 3.6 |
| session2 | clip_0056.wav | 4 | 0.5859 | 0.2344 | 0 | 0 | 0.0084 | 3.2 |
| session2 | clip_0010.wav | 4 | 0.0234 | 0.5586 | 0 | 0 | 0.0183 | 2.6 |
| session2 | clip_0034.wav | 4 | 0.0859 | 0.5586 | 0 | 0 | 0.0041 | 3.1 |
| session5 | clip_0002.wav | 4 | 0.1211 | 0.5586 | 0 | 0 | 0.0052 | 4.4 |
| session2 | clip_0019.wav | 4 | 0.0312 | 0.5312 | 0 | 0 | 0.0078 | 2.6 |
| session2 | clip_0033.wav | 4 | 0.3828 | 0.5312 | 0 | 0 | 0.0024 | 3.0 |
| session2 | clip_0057.wav | 4 | 0.2578 | 0.5312 | 0 | 0 | 0.0093 | 2.4 |
| session5 | clip_0005.wav | 4 | 0.0547 | 0.5312 | 0 | 0 | 0.0030 | 3.1 |
| session5 | clip_0007.wav | 4 | 0.2578 | 0.5000 | 0 | 0 | 0.0037 | 3.3 |
| session6 | clip_0000.wav | 4 | 0.3828 | 0.5000 | 0 | 0 | 0.0036 | 7.2 |
| session2 | clip_0011.wav | 4 | 0.2148 | 0.4688 | 0 | 0 | 0.0076 | 2.6 |
| session5 | clip_0006.wav | 4 | 0.0508 | 0.4688 | 0 | 0 | 0.0060 | 4.0 |
| session2 | clip_0016.wav | 4 | 0.0312 | 0.4414 | 0 | 0 | 0.0088 | 2.3 |
| session2 | clip_0026.wav | 4 | 0.1211 | 0.4414 | 0 | 0 | 0.0091 | 3.0 |
| session6 | clip_0001.wav | 4 | 0.1328 | 0.4414 | 0 | 0 | 0.0081 | 4.0 |
| session8b | clip_0004.wav | 4 | 0.1484 | 0.4414 | 0 | 0 | 0.0274 | 7.0 |
| session8b | clip_0007.wav | 4 | 0.4414 | 0.2148 | 0 | 0 | 0.0510 | 9.2 |
| session2 | clip_0000.wav | 4 | 0.4141 | 0.1797 | 0 | 0 | 0.0180 | 3.3 |
| session2 | clip_0025.wav | 4 | 0.2148 | 0.4141 | 0 | 0 | 0.0090 | 2.9 |
| session2 | clip_0029.wav | 4 | 0.1953 | 0.4141 | 0 | 0 | 0.0093 | 3.7 |
| session8 | clip_0004.wav | 4 | 0.1797 | 0.4141 | 0 | 0 | 0.0101 | 4.5 |
| session2 | clip_0015.wav | 4 | 0.1094 | 0.3828 | 0 | 0 | 0.0077 | 2.4 |
| session2 | clip_0039.wav | 4 | 0.0195 | 0.3828 | 0 | 0 | 0.0136 | 2.9 |
| session2 | clip_0045.wav | 4 | 0.1211 | 0.3828 | 0 | 0 | 0.0096 | 3.1 |
| session2 | clip_0055.wav | 4 | 0.0078 | 0.3828 | 0 | 0 | 0.0097 | 2.6 |
| session5 | clip_0008.wav | 4 | 0.0547 | 0.3828 | 0 | 0 | 0.0060 | 4.0 |
| session5 | clip_0004.wav | 4 | 0.0703 | 0.3555 | 0 | 0 | 0.0137 | 1.8 |
| session5 | clip_0009.wav | 4 | 0.0859 | 0.3555 | 0 | 0 | 0.0066 | 3.5 |
| session2 | clip_0040.wav | 4 | 0.1211 | 0.3320 | 0 | 0 | 0.0180 | 2.0 |
| session8b | clip_0003.wav | 4 | 0.3320 | 0.0000 | 0 | 0 | 0.0306 | 7.5 |
| session2 | clip_0005.wav | 4 | 0.0859 | 0.3047 | 0 | 0 | 0.0086 | 2.1 |
| session2 | clip_0058.wav | 4 | 0.0508 | 0.3047 | 0 | 0 | 0.0069 | 2.8 |
| session7 | clip_0004.wav | 4 | 0.3047 | 0.0117 | 0 | 0 | 0.0136 | 3.7 |
| session1 | clip_0009.wav | 4 | 0.0195 | 0.2812 | 0 | 0 | 0.0087 | 2.2 |
| session2 | clip_0008.wav | 4 | 0.0547 | 0.2812 | 0 | 0 | 0.0095 | 3.6 |
| session4 | clip_0056.wav | 4 | 0.2812 | 0.0625 | 0 | 0 | 0.0099 | 4.8 |
| session1 | clip_0010.wav | 4 | 0.1094 | 0.2578 | 0 | 0 | 0.0086 | 2.2 |
| session2 | clip_0032.wav | 4 | 0.0039 | 0.2578 | 0 | 0 | 0.0120 | 2.6 |
| session2 | clip_0035.wav | 4 | 0.0352 | 0.2578 | 0 | 0 | 0.0086 | 2.3 |
| session6 | clip_0002.wav | 4 | 0.0703 | 0.2578 | 0 | 0 | 0.0100 | 2.8 |
| session7 | clip_0007.wav | 4 | 0.0156 | 0.2578 | 0 | 0 | 0.0119 | 4.9 |
| session8 | clip_0000.wav | 4 | 0.2578 | 0.1328 | 0 | 0 | 0.0041 | 3.9 |
| session8 | clip_0003.wav | 4 | 0.0352 | 0.2578 | 0 | 0 | 0.0347 | 2.7 |
| session2 | clip_0021.wav | 4 | 0.1953 | 0.2344 | 0 | 0 | 0.0085 | 7.5 |
| session2 | clip_0027.wav | 4 | 0.2148 | 0.2344 | 0 | 0 | 0.0090 | 3.7 |
| session3_partial | clip_0000.wav | 4 | 0.0234 | 0.2344 | 0 | 0 | 0.0097 | 2.6 |
| session1 | clip_0008.wav | 4 | 0.0352 | 0.2148 | 0 | 0 | 0.0069 | 2.8 |
| session4 | clip_0059.wav | 4 | 0.2148 | 0.1094 | 0 | 0 | 0.0094 | 4.5 |
| session2 | clip_0012.wav | 4 | 0.1602 | 0.1953 | 0 | 0 | 0.0103 | 2.6 |
| session6 | clip_0007.wav | 4 | 0.1953 | 0.1484 | 0 | 0 | 0.0079 | 4.2 |
| session6 | clip_0010.wav | 4 | 0.1953 | 0.0625 | 0 | 0 | 0.0095 | 3.9 |
| session4 | clip_0048.wav | 4 | 0.0312 | 0.1797 | 0 | 0 | 0.0076 | 3.4 |
| session8b | clip_0001.wav | 4 | 0.1797 | 0.0000 | 0 | 0 | 0.0257 | 3.9 |
| session2 | clip_0020.wav | 4 | 0.0508 | 0.1602 | 0 | 0 | 0.0077 | 2.4 |
| session2 | clip_0023.wav | 4 | 0.1602 | 0.0312 | 0 | 0 | 0.0065 | 4.4 |
| session2 | clip_0030.wav | 4 | 0.0703 | 0.1484 | 0 | 0 | 0.0095 | 2.1 |
| session2 | clip_0043.wav | 4 | 0.0156 | 0.1484 | 0 | 0 | 0.0047 | 3.9 |
| session2 | clip_0047.wav | 4 | 0.0117 | 0.1484 | 0 | 0 | 0.0053 | 10.1 |
| session2 | clip_0031.wav | 4 | 0.0039 | 0.1328 | 0 | 0 | 0.0045 | 4.1 |
| session4 | clip_0047.wav | 4 | 0.1328 | 0.0469 | 0 | 0 | 0.0346 | 2.1 |
| session2 | clip_0042.wav | 4 | 0.0273 | 0.1211 | 0 | 0 | 0.0165 | 2.6 |
| session2 | clip_0044.wav | 4 | 0.0273 | 0.1211 | 0 | 0 | 0.0076 | 2.5 |
| session3_partial | clip_0004.wav | 4 | 0.0117 | 0.1211 | 0 | 0 | 0.0077 | 3.6 |
| session6b | clip_0008.wav | 4 | 0.0117 | 0.1211 | 0 | 0 | 0.0260 | 5.3 |
| session7 | clip_0006.wav | 4 | 0.1211 | 0.0039 | 0 | 0 | 0.0096 | 7.8 |
| session7 | clip_0002.wav | 4 | 0.1094 | 0.0039 | 0 | 0 | 0.0477 | 2.7 |
| session2 | clip_0004.wav | 4 | 0.0195 | 0.0977 | 0 | 0 | 0.0084 | 2.3 |
| session4 | clip_0051.wav | 4 | 0.0195 | 0.0977 | 0 | 0 | 0.0098 | 7.2 |
| session6 | clip_0003.wav | 4 | 0.0156 | 0.0977 | 0 | 0 | 0.0136 | 2.3 |
| session7 | clip_0010.wav | 4 | 0.0469 | 0.0977 | 0 | 0 | 0.0136 | 5.1 |
| session2 | clip_0041.wav | 4 | 0.0547 | 0.0859 | 0 | 0 | 0.0064 | 3.2 |
| session4 | clip_0052.wav | 4 | 0.0859 | 0.0352 | 0 | 0 | 0.0075 | 2.6 |
| session3_partial | clip_0001.wav | 4 | 0.0508 | 0.0781 | 0 | 0 | 0.0083 | 3.2 |
| session3_partial | clip_0005.wav | 4 | 0.0039 | 0.0781 | 0 | 0 | 0.0069 | 3.3 |
| session8 | clip_0009.wav | 4 | 0.0156 | 0.0781 | 0 | 0 | 0.0101 | 4.5 |
| session2 | clip_0022.wav | 4 | 0.0547 | 0.0703 | 0 | 0 | 0.0081 | 3.5 |
| session7 | clip_0005.wav | 4 | 0.0273 | 0.0703 | 0 | 0 | 0.0103 | 5.5 |
| session7 | clip_0009.wav | 4 | 0.0508 | 0.0703 | 0 | 0 | 0.0235 | 3.0 |
| session2 | clip_0054.wav | 4 | 0.0117 | 0.0625 | 0 | 0 | 0.0081 | 2.3 |
| session4 | clip_0055.wav | 4 | 0.0156 | 0.0625 | 0 | 0 | 0.0087 | 4.4 |
| session6 | clip_0006.wav | 4 | 0.0508 | 0.0273 | 0 | 0 | 0.0190 | 3.5 |
| session8 | clip_0005.wav | 4 | 0.0000 | 0.0508 | 0 | 0 | 0.0093 | 6.4 |
| session2 | clip_0052.wav | 4 | 0.0039 | 0.0469 | 0 | 0 | 0.0053 | 3.4 |
| session3_partial | clip_0002.wav | 4 | 0.0039 | 0.0352 | 0 | 0 | 0.0118 | 4.2 |
| session7 | clip_0000.wav | 4 | 0.0039 | 0.0352 | 0 | 0 | 0.0137 | 4.9 |
| session2 | clip_0017.wav | 4 | 0.0078 | 0.0312 | 0 | 0 | 0.0086 | 6.4 |
| session4 | clip_0057.wav | 4 | 0.0117 | 0.0273 | 0 | 0 | 0.0096 | 5.0 |
| session2 | clip_0048.wav | 4 | 0.0195 | 0.0195 | 0 | 0 | 0.0068 | 3.0 |
| session3_partial | clip_0003.wav | 4 | 0.0039 | 0.0195 | 0 | 0 | 0.0094 | 2.8 |
| session3_partial | clip_0006.wav | 4 | 0.0078 | 0.0195 | 0 | 0 | 0.0082 | 2.8 |
| session4 | clip_0058.wav | 4 | 0.0039 | 0.0195 | 0 | 0 | 0.0089 | 4.3 |
| session6 | clip_0005.wav | 4 | 0.0195 | 0.0039 | 0 | 0 | 0.0278 | 2.9 |
| session7 | clip_0008.wav | 4 | 0.0117 | 0.0195 | 0 | 0 | 0.0132 | 4.7 |
| session8b | clip_0000.wav | 4 | 0.0195 | 0.0000 | 0 | 0 | 0.0277 | 10.2 |
| session7 | clip_0003.wav | 4 | 0.0156 | 0.0000 | 0 | 0 | 0.0298 | 3.1 |
| session8b | clip_0009.wav | 4 | 0.0156 | 0.0000 | 0 | 0 | 0.0913 | 4.9 |
| session2 | clip_0049.wav | 4 | 0.0117 | 0.0117 | 0 | 0 | 0.0087 | 2.2 |
| session2 | clip_0053.wav | 4 | 0.0039 | 0.0117 | 0 | 0 | 0.0084 | 15.3 |
| session4 | clip_0049.wav | 4 | 0.0117 | 0.0117 | 0 | 0 | 0.0173 | 2.6 |
| session4 | clip_0050.wav | 4 | 0.0117 | 0.0039 | 0 | 0 | 0.0074 | 3.4 |
| session6b | clip_0006.wav | 4 | 0.0078 | 0.0117 | 0 | 0 | 0.1479 | 4.0 |
| session8 | clip_0010.wav | 4 | 0.0039 | 0.0117 | 0 | 0 | 0.0094 | 2.9 |
| session8b | clip_0002.wav | 4 | 0.0117 | 0.0039 | 0 | 0 | 0.0150 | 5.3 |
| session2 | clip_0050.wav | 4 | 0.0039 | 0.0078 | 0 | 0 | 0.0083 | 2.5 |
| session4 | clip_0060.wav | 4 | 0.0000 | 0.0078 | 0 | 0 | 0.0093 | 4.5 |
| session6b | clip_0002.wav | 4 | 0.0000 | 0.0078 | 0 | 0 | 0.0134 | 3.5 |
| session6b | clip_0005.wav | 4 | 0.0078 | 0.0078 | 0 | 0 | 0.0297 | 2.3 |
| session6b | clip_0009.wav | 4 | 0.0039 | 0.0078 | 0 | 0 | 0.2095 | 4.8 |
| session8b | clip_0005.wav | 4 | 0.0039 | 0.0078 | 0 | 0 | 0.0466 | 8.2 |
| session4 | clip_0054.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0097 | 4.3 |
| session6 | clip_0008.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0084 | 4.2 |
| session6 | clip_0009.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0084 | 3.7 |
| session6b | clip_0000.wav | 4 | 0.0039 | 0.0000 | 0 | 0 | 0.0210 | 4.3 |
| session6b | clip_0007.wav | 4 | 0.0000 | 0.0039 | 0 | 0 | 0.0173 | 12.7 |
| session6b | clip_0010.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0587 | 2.7 |
| session7 | clip_0001.wav | 4 | 0.0000 | 0.0039 | 0 | 0 | 0.0090 | 5.8 |
| session7b | clip_0006.wav | 4 | 0.0039 | 0.0000 | 0 | 0 | 0.0653 | 4.4 |
| session7b | clip_0007.wav | 4 | 0.0000 | 0.0039 | 0 | 0 | 0.0628 | 4.3 |
| session7b | clip_0008.wav | 4 | 0.0000 | 0.0039 | 0 | 0 | 0.0620 | 4.3 |
| session8b | clip_0006.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0321 | 9.6 |
| session8b | clip_0008.wav | 4 | 0.0039 | 0.0039 | 0 | 0 | 0.0333 | 13.1 |
| session8b | clip_0010.wav | 4 | 0.0039 | 0.0000 | 0 | 0 | 0.0238 | 8.4 |
| session2 | clip_0051.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0077 | 7.2 |
| session4 | clip_0061.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0091 | 4.1 |
| session4 | clip_0062.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0077 | 3.9 |
| session4 | clip_0063.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0089 | 3.8 |
| session4 | clip_0064.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0096 | 4.2 |
| session6 | clip_0004.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0151 | 4.5 |
| session6b | clip_0001.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0189 | 3.3 |
| session6b | clip_0003.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0332 | 3.1 |
| session6b | clip_0004.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0565 | 2.5 |
| session7b | clip_0000.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0629 | 6.5 |
| session7b | clip_0001.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0380 | 8.0 |
| session7b | clip_0002.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0610 | 5.6 |
| session7b | clip_0003.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0557 | 5.7 |
| session7b | clip_0004.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0507 | 8.1 |
| session7b | clip_0005.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0782 | 5.2 |
| session7b | clip_0009.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0560 | 5.2 |
| session7b | clip_0010.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0411 | 6.4 |
| session8 | clip_0002.wav | 4 | 0.0000 | 0.0000 | 0 | 0 | 0.0121 | 4.5 |

## demo-ready clips (P >= 0.99): 56 of 241
- `session1/clips/clip_0000.wav` — P 0.9961, 3 announcing window(s)
- `session1/clips/clip_0001.wav` — P 0.9961, 1 announcing window(s)
- `session1/clips/clip_0002.wav` — P 0.9961, 1 announcing window(s)
- `session1/clips/clip_0003.wav` — P 0.9961, 2 announcing window(s)
- `session1/clips/clip_0004.wav` — P 0.9961, 4 announcing window(s)
- `session1/clips/clip_0005.wav` — P 0.9961, 4 announcing window(s)
- `session1/clips/clip_0006.wav` — P 0.9961, 4 announcing window(s)
- `session1/clips/clip_0007.wav` — P 0.9961, 1 announcing window(s)
- `session10/clips/clip_0001.wav` — P 0.9961, 2 announcing window(s)
- `session10/clips/clip_0003.wav` — P 0.9961, 2 announcing window(s)
- `session10/clips/clip_0004.wav` — P 0.9961, 1 announcing window(s)
- `session10/clips/clip_0006.wav` — P 0.9961, 2 announcing window(s)
- `session10/clips/clip_0010.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0002.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0003.wav` — P 0.9922, 1 announcing window(s)
- `session4/clips/clip_0004.wav` — P 0.9922, 1 announcing window(s)
- `session4/clips/clip_0005.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0006.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0007.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0008.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0009.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0010.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0011.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0012.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0016.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0018.wav` — P 0.9961, 1 announcing window(s)
- `session4/clips/clip_0019.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0020.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0021.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0022.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0023.wav` — P 0.9922, 1 announcing window(s)
- `session4/clips/clip_0024.wav` — P 0.9961, 3 announcing window(s)
- `session4/clips/clip_0025.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0026.wav` — P 0.9961, 1 announcing window(s)
- `session4/clips/clip_0028.wav` — P 0.9961, 1 announcing window(s)
- `session4/clips/clip_0029.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0030.wav` — P 0.9961, 1 announcing window(s)
- `session4/clips/clip_0033.wav` — P 0.9961, 1 announcing window(s)
- `session4/clips/clip_0034.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0035.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0036.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0037.wav` — P 0.9961, 4 announcing window(s)
- `session4/clips/clip_0038.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0039.wav` — P 0.9961, 2 announcing window(s)
- `session4/clips/clip_0040.wav` — P 0.9961, 4 announcing window(s)
- `session9/clips/clip_0000.wav` — P 0.9961, 2 announcing window(s)
- `session9/clips/clip_0002.wav` — P 0.9961, 3 announcing window(s)
- `session9/clips/clip_0003.wav` — P 0.9961, 3 announcing window(s)
- `session9/clips/clip_0004.wav` — P 0.9961, 2 announcing window(s)
- `session9/clips/clip_0005.wav` — P 0.9961, 2 announcing window(s)
- `session9/clips/clip_0006.wav` — P 0.9961, 4 announcing window(s)
- `session9/clips/clip_0007.wav` — P 0.9961, 4 announcing window(s)
- `session9/clips/clip_0008.wav` — P 0.9961, 3 announcing window(s)
- `session9/clips/clip_0009.wav` — P 0.9961, 2 announcing window(s)
- `session9/clips/clip_0010.wav` — P 0.9961, 4 announcing window(s)
- `session9/clips/clip_0001.wav` — P 0.9922, 2 announcing window(s)

## seen but not announceable (P >= 0.6 only): 45
- `session10/clips/clip_0000.wav` — P 0.9883 (HP 0.9961)
- `session10/clips/clip_0005.wav` — P 0.9727 (HP 0.9961)
- `session10/clips/clip_0007.wav` — P 0.1484 (HP 0.9961)
- `session10/clips/clip_0008.wav` — P 0.2812 (HP 0.9961)
- `session10/clips/clip_0009.wav` — P 0.9141 (HP 0.9961)
- `session4/clips/clip_0014.wav` — P 0.9492 (HP 0.9961)
- `session4/clips/clip_0015.wav` — P 0.9805 (HP 0.9961)
- `session4/clips/clip_0031.wav` — P 0.9453 (HP 0.9961)
- `session4/clips/clip_0044.wav` — P 0.9766 (HP 0.9961)
- `session4/clips/clip_0017.wav` — P 0.9375 (HP 0.9922)
- `session10/clips/clip_0002.wav` — P 0.0703 (HP 0.9883)
- `session4/clips/clip_0032.wav` — P 0.9023 (HP 0.9883)
- `session4/clips/clip_0042.wav` — P 0.4414 (HP 0.9805)
- `session4/clips/clip_0041.wav` — P 0.9141 (HP 0.9727)
- `session4/clips/clip_0043.wav` — P 0.9297 (HP 0.9727)
- `session2/clips/clip_0046.wav` — P 0.3320 (HP 0.9609)
- `session2/clips/clip_0028.wav` — P 0.5312 (HP 0.9375)
- `session8/clips/clip_0001.wav` — P 0.8906 (HP 0.2578)
- `session2/clips/clip_0024.wav` — P 0.6953 (HP 0.8672)
- `session4/clips/clip_0013.wav` — P 0.1094 (HP 0.8516)
- `session2/clips/clip_0007.wav` — P 0.1211 (HP 0.8398)
- `session4/clips/clip_0027.wav` — P 0.1484 (HP 0.8203)
- `session4/clips/clip_0045.wav` — P 0.1797 (HP 0.8047)
- `session2/clips/clip_0001.wav` — P 0.1602 (HP 0.7852)
- `session2/clips/clip_0002.wav` — P 0.1953 (HP 0.7852)
- `session2/clips/clip_0013.wav` — P 0.2578 (HP 0.7852)
- `session2/clips/clip_0018.wav` — P 0.1484 (HP 0.7852)
- `session2/clips/clip_0038.wav` — P 0.1602 (HP 0.7852)
- `session8/clips/clip_0008.wav` — P 0.0234 (HP 0.7656)
- `session4/clips/clip_0000.wav` — P 0.0312 (HP 0.7422)
- `session4/clips/clip_0046.wav` — P 0.1328 (HP 0.7422)
- `session4/clips/clip_0053.wav` — P 0.5312 (HP 0.7422)
- `session8/clips/clip_0006.wav` — P 0.1953 (HP 0.7422)
- `session2/clips/clip_0003.wav` — P 0.1328 (HP 0.7188)
- `session2/clips/clip_0006.wav` — P 0.0391 (HP 0.7188)
- `session2/clips/clip_0009.wav` — P 0.5859 (HP 0.7188)
- `session2/clips/clip_0014.wav` — P 0.6953 (HP 0.5859)
- `session4/clips/clip_0001.wav` — P 0.0273 (HP 0.6953)
- `session2/clips/clip_0036.wav` — P 0.0703 (HP 0.6680)
- `session5/clips/clip_0001.wav` — P 0.1797 (HP 0.6680)
- `session5/clips/clip_0010.wav` — P 0.0312 (HP 0.6445)
- `session8/clips/clip_0007.wav` — P 0.6445 (HP 0.3555)
- `session2/clips/clip_0037.wav` — P 0.0781 (HP 0.6172)
- `session5/clips/clip_0000.wav` — P 0.2148 (HP 0.6172)
- `session5/clips/clip_0003.wav` — P 0.4688 (HP 0.6172)
