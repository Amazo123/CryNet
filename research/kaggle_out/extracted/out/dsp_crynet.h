#ifndef DSP_CRYNET_H
#define DSP_CRYNET_H
#include <stdint.h>
#include "crynet_tables.h"
#ifdef __cplusplus
extern "C" {
#endif
void crynet_log_mel(const int16_t *pcm, float *mel_out);
void crynet_quantise(const float *mel, int8_t *q);
float crynet_dequantise(int8_t v);
float crynet_window_rms(const int16_t *pcm);
#ifdef __cplusplus
}
#endif
#endif
