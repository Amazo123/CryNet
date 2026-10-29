/*
 * CryNet — verification probes for Stage 2a.
 *
 * See probes.h for the definitions; they must stay in step with
 * firmware/tools/gen_probe_refs.py.
 */

#include <math.h>
#include <string.h>

#include "probes.h"
#include "crynet_probe_refs.h"   /* generated: expected features */

static const char *const kProbeNames[CRYNET_PROBE_COUNT] = {
    "silence",
    "dc_bias",
    "tone",
    "noise",
};

const char *crynet_probe_name(int index)
{
    if (index < 0 || index >= CRYNET_PROBE_COUNT) {
        return "?";
    }
    return kProbeNames[index];
}

static double clip(double v)
{
    if (v > 1.0) {
        return 1.0;
    }
    if (v < -1.0) {
        return -1.0;
    }
    return v;
}

/* 32-bit LCG, 24 high bits used as a uniform in [0, 1). */
static uint32_t lcg_next(uint32_t *state)
{
    *state = (uint32_t)(1103515245u * (*state) + 12345u);
    return (*state >> 8) & 0x00FFFFFFu;
}

void crynet_probe_pcm(int index, int16_t *pcm)
{
    switch (index) {
    case 0: /* silence */
        memset(pcm, 0, CRYNET_PROBE_SAMPLES * sizeof(int16_t));
        break;

    case 1: /* the INMP441's quiescent DC bias, and nothing else */
        for (int i = 0; i < CRYNET_PROBE_SAMPLES; i++) {
            pcm[i] = (int16_t)18000;
        }
        break;

    case 2: { /* two tones */
        for (int i = 0; i < CRYNET_PROBE_SAMPLES; i++) {
            const double t = (double)i / 16000.0;
            const double x = 0.35 * sin(2.0 * M_PI * 420.0 * t)
                           + 0.12 * sin(2.0 * M_PI * 1350.0 * t);
            pcm[i] = (int16_t)(clip(x) * 32767.0);
        }
        break;
    }

    case 3: { /* broadband noise */
        uint32_t state = 12345u;
        for (int i = 0; i < CRYNET_PROBE_SAMPLES; i++) {
            const double u = (double)lcg_next(&state) / 16777216.0;
            const double x = 0.05 * (2.0 * u - 1.0);
            pcm[i] = (int16_t)(clip(x) * 32767.0);
        }
        break;
    }

    default:
        memset(pcm, 0, CRYNET_PROBE_SAMPLES * sizeof(int16_t));
        break;
    }
}

static uint32_t crc32_buf(const void *data, size_t len)
{
    const uint8_t *p = (const uint8_t *)data;
    uint32_t crc = 0xFFFFFFFFu;

    for (size_t i = 0; i < len; i++) {
        crc ^= p[i];
        for (int b = 0; b < 8; b++) {
            const uint32_t mask = (uint32_t) - (int32_t)(crc & 1u);
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

uint32_t crynet_probe_pcm_crc(int index)
{
    static int16_t pcm[CRYNET_PROBE_SAMPLES];
    if (index < 0 || index >= CRYNET_PROBE_COUNT) {
        return 0;
    }
    crynet_probe_pcm(index, pcm);
    return crc32_buf(pcm, CRYNET_PROBE_SAMPLES * sizeof(int16_t));
}

const int8_t *crynet_probe_expected(int index)
{
    if (index < 0 || index >= CRYNET_PROBE_COUNT) {
        return NULL;
    }
    return crynet_probe_refs[index];
}

uint32_t crynet_probe_expected_crc(int index)
{
    if (index < 0 || index >= CRYNET_PROBE_COUNT) {
        return 0;
    }
    return crynet_probe_ref_feature_crc[index];
}

uint32_t crynet_probe_expected_pcm_crc(int index)
{
    if (index < 0 || index >= CRYNET_PROBE_COUNT) {
        return 0;
    }
    return crynet_probe_ref_pcm_crc[index];
}
