/*
 * CryNet — DSP front end implementation.
 *
 * This is the ONLY translation unit in the firmware that includes the
 * notebook-generated crynet_tables.h (file-scope `const` arrays have
 * external linkage in C, so including them twice is a link error).
 *
 * The signal chain, frozen and identical to the Python training pipeline:
 *
 *   int16 pcm[32000]                      2.000 s @ 16 kHz mono
 *     -> subtract mean                    DC removal (INMP441 sits at ~+18000)
 *     -> zero-pad 256 front / 512 rear
 *     -> 81 frames, 512-pt symmetric Hann, hop 400
 *     -> |rfft|^2                         257 bins
 *     -> 64 Mel bands (librosa slaney, 20 Hz - 8 kHz)
 *     -> 10*log10(max(P, 1e-10))          floored at -80 dB
 *     -> per-window standardisation       (mean 0, std 1)
 *     -> int8 quantise                    q = round(v/scale) + zero_point
 */

#include <math.h>
#include <string.h>

#include "esp_heap_caps.h"

#include "crynet_tables.h"  /* generated — see the note above */
#include "crynet_dsp.h"
#include "crynet_model.h"

/* Compile-time drift detection: the firmware mirrors a few of the
 * generated constants under its own names, because the generated header
 * may only be included once. If a new set of Kaggle artifacts changes a
 * value, this translation unit fails to compile instead of silently
 * classifying with stale numbers. */
_Static_assert(CRYNET_INPUT_SCALE == CRYNET_IN_SCALE, "input scale drift");
_Static_assert(CRYNET_INPUT_ZERO_POINT == CRYNET_IN_ZP, "input zero-point drift");
_Static_assert(CRYNET_OUTPUT_SCALE == CRYNET_OUT_SCALE, "output scale drift");
_Static_assert(CRYNET_OUTPUT_ZERO_POINT == CRYNET_OUT_ZP, "output zero-point drift");
_Static_assert(CRYNET_SILENCE_RMS_GATE == CRYNET_SILENCE_RMS, "silence gate drift");
_Static_assert(CRYNET_N_SAMPLES == 32000, "sample count drift");
_Static_assert(CRYNET_N_FRAMES == 81, "frame count drift");
_Static_assert(CRYNET_N_MELS == 64, "mel band count drift");

typedef struct {
    float re;
    float im;
} cpx_t;

/* ------------------------------------------------------------------ */
/* FFT: iterative radix-2, N = 512, in place.                          */
/* The twiddle recurrence is kept identical to the reference           */
/* implementation so the two agree bit-for-bit on the same input.      */
/* ------------------------------------------------------------------ */
static void fft512(cpx_t *a)
{
    unsigned i, j, len;

    for (i = 1, j = 0; i < CRYNET_N_FFT; i++) {
        unsigned bit = CRYNET_N_FFT >> 1;
        for (; j & bit; bit >>= 1) {
            j ^= bit;
        }
        j ^= bit;
        if (i < j) {
            cpx_t t = a[i];
            a[i] = a[j];
            a[j] = t;
        }
    }

    for (len = 2; len <= CRYNET_N_FFT; len <<= 1) {
        const float ang = -2.0f * 3.14159265358979f / (float)len;
        const float wr = cosf(ang);
        const float wi = sinf(ang);

        for (i = 0; i < CRYNET_N_FFT; i += len) {
            float cr = 1.0f, ci = 0.0f;
            for (j = 0; j < len / 2; j++) {
                const cpx_t u = a[i + j];
                cpx_t v;
                v.re = a[i + j + len / 2].re * cr - a[i + j + len / 2].im * ci;
                v.im = a[i + j + len / 2].re * ci + a[i + j + len / 2].im * cr;
                a[i + j].re = u.re + v.re;
                a[i + j].im = u.im + v.im;
                a[i + j + len / 2].re = u.re - v.re;
                a[i + j + len / 2].im = u.im - v.im;

                const float nr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = nr;
            }
        }
    }
}

/* ------------------------------------------------------------------ */

bool crynet_dsp_init(crynet_dsp_ctx_t *ctx)
{
    if (ctx == NULL) {
        return false;
    }
    memset(ctx, 0, sizeof(*ctx));

    const size_t win_floats = CRYNET_N_SAMPLES + CRYNET_CENTER_PAD + CRYNET_TAIL_PAD;
    const size_t total = win_floats * sizeof(float)      /* window */
                         + (CRYNET_N_FFT / 2 + 1) * sizeof(float) /* power */
                         + CRYNET_N_MELS * sizeof(float)  /* mel    */
                         + CRYNET_N_FFT * sizeof(cpx_t);  /* fft    */

    /*
     * PSRAM first: the hub's internal SRAM is 512 KB and the radio, TFT
     * and BLE stacks all want it. The front end's 130 KB window buffer is
     * the single largest allocation in the firmware, so it belongs in the
     * 8 MB of PSRAM the S3-DevKitC-1 N16R8 has.
     */
    uint8_t *mem = heap_caps_malloc(total, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    ctx->from_psram = (mem != NULL);
    if (mem == NULL) {
        mem = heap_caps_malloc(total, MALLOC_CAP_8BIT);
        ctx->from_psram = false;
    }
    if (mem == NULL) {
        return false;
    }

    ctx->bytes = total;
    ctx->window = (float *)mem;
    ctx->power = ctx->window + win_floats;
    ctx->mel = ctx->power + (CRYNET_N_FFT / 2 + 1);
    ctx->fft = ctx->mel + CRYNET_N_MELS;
    return true;
}

void crynet_dsp_free(crynet_dsp_ctx_t *ctx)
{
    if (ctx == NULL || ctx->window == NULL) {
        return;
    }
    if (ctx->from_psram) {
        heap_caps_free(ctx->window);
    } else {
        free(ctx->window);
    }
    memset(ctx, 0, sizeof(*ctx));
}

void crynet_dsp_features(const crynet_dsp_ctx_t *ctx,
                          const int16_t *pcm,
                          float *mel_out)
{
    const size_t win_floats = CRYNET_N_SAMPLES + CRYNET_CENTER_PAD + CRYNET_TAIL_PAD;
    float *x = ctx->window;
    cpx_t *spec = (cpx_t *)ctx->fft;
    float *power = ctx->power;
    float *mel = ctx->mel;

    /* 1. DC removal + normalise to [-1, 1]. The INMP441 sits at roughly
     *    +18000 counts, so this step is not optional. */
    float mean = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) {
        mean += (float)pcm[i];
    }
    mean /= (float)CRYNET_N_SAMPLES;

    memset(x, 0, win_floats * sizeof(float));
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) {
        x[CRYNET_CENTER_PAD + i] = ((float)pcm[i] - mean) / 32768.0f;
    }

    /* 2. frames -> FFT -> power -> mel -> dB */
    for (int fr = 0; fr < CRYNET_N_FRAMES; fr++) {
        const float *w = x + fr * CRYNET_HOP;

        for (int i = 0; i < CRYNET_N_FFT; i++) {
            spec[i].re = w[i] * CRYNET_HANN[i];
            spec[i].im = 0.0f;
        }
        fft512(spec);

        for (int i = 0; i <= CRYNET_N_FFT / 2; i++) {
            power[i] = spec[i].re * spec[i].re + spec[i].im * spec[i].im;
        }

        for (int m = 0; m < CRYNET_N_MELS; m++) {
            float acc = 0.0f;
            const int start = CRYNET_MEL_START[m];
            const int end = CRYNET_MEL_END[m];
            const float *wts = &CRYNET_MEL_WEIGHTS[CRYNET_MEL_OFFSET[m]];
            for (int b = start; b < end; b++) {
                acc += power[b] * wts[b - start];
            }
            mel[m] = acc;
        }

        for (int m = 0; m < CRYNET_N_MELS; m++) {
            float p = mel[m];
            if (p < CRYNET_LOG_EPS) {
                p = CRYNET_LOG_EPS;
            }
            float db = 10.0f * log10f(p);
            if (db < CRYNET_DB_FLOOR) {
                db = CRYNET_DB_FLOOR;
            }
            mel_out[fr * CRYNET_N_MELS + m] = db;
        }
    }

    /* 3. per-window standardisation — this is what makes the model
     *    level-invariant. Without it the network can learn "quiet = cry",
     *    because the ICD cries sit at RMS 0.006 and its negatives at
     *    0.3-0.46. */
    const int n = CRYNET_N_FRAMES * CRYNET_N_MELS;
    float mu = 0.0f;
    for (int i = 0; i < n; i++) {
        mu += mel_out[i];
    }
    mu /= (float)n;

    float var = 0.0f;
    for (int i = 0; i < n; i++) {
        const float d = mel_out[i] - mu;
        var += d * d;
    }
    const float sd = sqrtf(var / (float)n) + 1e-6f;

    for (int i = 0; i < n; i++) {
        mel_out[i] = (mel_out[i] - mu) / sd;
    }
}

void crynet_dsp_quantise(const float *mel, int8_t *q)
{
    const int n = CRYNET_N_FRAMES * CRYNET_N_MELS;
    for (int i = 0; i < n; i++) {
        float v = nearbyintf(mel[i] / CRYNET_IN_SCALE) + (float)CRYNET_IN_ZP;
        if (v > 127.0f) {
            v = 127.0f;
        }
        if (v < -128.0f) {
            v = -128.0f;
        }
        q[i] = (int8_t)v;
    }
}

float crynet_dsp_rms(const int16_t *pcm)
{
    float mean = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) {
        mean += (float)pcm[i];
    }
    mean /= (float)CRYNET_N_SAMPLES;

    float acc = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) {
        const float d = ((float)pcm[i] - mean) / 32768.0f;
        acc += d * d;
    }
    return sqrtf(acc / (float)CRYNET_N_SAMPLES);
}
