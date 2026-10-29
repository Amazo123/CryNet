
/* ===========================================================================
 * dsp_crynet.c — CryNet log-Mel front end, numerically identical to the
 *                Python implementation used for training.
 *
 *  Host parity test:
 *      gcc -O2 -DCRYNET_SELFTEST -o dsp_test dsp_crynet.c -lm
 *      ./dsp_test probe.s16le
 *
 *  On the ESP32-S3 replace fft512() with ESP-DSP:
 *      dsps_fft2r() + dsps_cmplx_mag()  (roughly 10x faster than the
 *      reference FFT below, which is kept so the file builds anywhere).
 * =========================================================================*/
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "crynet_tables.h"

typedef struct { float re, im; } cpx_t;

/* ---- iterative radix-2 FFT, N = 512, in place ---------------------------- */
static void fft512(cpx_t *a) {
    unsigned i, j, len;
    cpx_t t;
    for (i = 1, j = 0; i < 512; i++) {
        unsigned bit = 512 >> 1;
        for (; j & bit; bit >>= 1) j ^= bit;
        j ^= bit;
        if (i < j) { t = a[i]; a[i] = a[j]; a[j] = t; }
    }
    for (len = 2; len <= 512; len <<= 1) {
        float ang = -2.0f * 3.14159265358979f / (float)len;
        float wr = cosf(ang), wi = sinf(ang);
        for (i = 0; i < 512; i += len) {
            float cr = 1.0f, ci = 0.0f;
            for (j = 0; j < len / 2; j++) {
                cpx_t u = a[i + j];
                cpx_t v;
                v.re = a[i + j + len / 2].re * cr - a[i + j + len / 2].im * ci;
                v.im = a[i + j + len / 2].re * ci + a[i + j + len / 2].im * cr;
                a[i + j].re = u.re + v.re;  a[i + j].im = u.im + v.im;
                a[i + j + len / 2].re = u.re - v.re;
                a[i + j + len / 2].im = u.im - v.im;
                float nr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = nr;
            }
        }
    }
}

/* ---- log-Mel front end ---------------------------------------------------- */
/*  pcm     : CRYNET_N_SAMPLES int16 mono samples @ 16 kHz
 *  mel_out : CRYNET_N_FRAMES * CRYNET_N_MELS floats (standardised dB)     */
void crynet_log_mel(const int16_t *pcm, float *mel_out) {
    static float x[CRYNET_N_SAMPLES + CRYNET_CENTER_PAD + CRYNET_TAIL_PAD];
    static cpx_t spec[CRYNET_N_FFT];
    static float power[CRYNET_N_FFT / 2 + 1];
    static float mel[CRYNET_N_MELS];

    /* 1. DC removal + normalise to [-1, 1] */
    float mean = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) mean += (float)pcm[i];
    mean /= (float)CRYNET_N_SAMPLES;

    memset(x, 0, sizeof(float) * (CRYNET_N_SAMPLES + CRYNET_CENTER_PAD + CRYNET_TAIL_PAD));
    for (int i = 0; i < CRYNET_N_SAMPLES; i++)
        x[CRYNET_CENTER_PAD + i] = ((float)pcm[i] - mean) / 32768.0f;

    /* 2. frames -> FFT -> power -> mel -> dB */
    for (int fr = 0; fr < CRYNET_N_FRAMES; fr++) {
        const float *w = x + fr * CRYNET_HOP;
        for (int i = 0; i < CRYNET_N_FFT; i++) {
            spec[i].re = w[i] * CRYNET_HANN[i];
            spec[i].im = 0.0f;
        }
        fft512(spec);
        for (int i = 0; i <= CRYNET_N_FFT / 2; i++)
            power[i] = spec[i].re * spec[i].re + spec[i].im * spec[i].im;
        for (int m = 0; m < CRYNET_N_MELS; m++) {
            float acc = 0.0f;
            int start = CRYNET_MEL_START[m], end = CRYNET_MEL_END[m];
            const float *wts = &CRYNET_MEL_WEIGHTS[CRYNET_MEL_OFFSET[m]];
            for (int b = start; b < end; b++) acc += power[b] * wts[b - start];
            mel[m] = acc;
        }
        for (int m = 0; m < CRYNET_N_MELS; m++) {
            float p = mel[m];
            if (p < CRYNET_LOG_EPS) p = CRYNET_LOG_EPS;
            float db = 10.0f * log10f(p);
            if (db < CRYNET_DB_FLOOR) db = CRYNET_DB_FLOOR;
            mel_out[fr * CRYNET_N_MELS + m] = db;
        }
    }

#if CRYNET_CMVN
    /* 3. per-window standardisation */
    float mu = 0.0f;
    const int n = CRYNET_N_FRAMES * CRYNET_N_MELS;
    for (int i = 0; i < n; i++) mu += mel_out[i];
    mu /= (float)n;
    float var = 0.0f;
    for (int i = 0; i < n; i++) { float d = mel_out[i] - mu; var += d * d; }
    float sd = sqrtf(var / (float)n) + 1e-6f;
    for (int i = 0; i < n; i++) mel_out[i] = (mel_out[i] - mu) / sd;
#endif
}

/* ---- quantisation helpers ------------------------------------------------ */
void crynet_quantise(const float *mel, int8_t *q) {
    const int n = CRYNET_N_FRAMES * CRYNET_N_MELS;
    for (int i = 0; i < n; i++) {
        float v = nearbyintf(mel[i] / CRYNET_IN_SCALE) + (float)CRYNET_IN_ZP;
        if (v > 127.0f) v = 127.0f;
        if (v < -128.0f) v = -128.0f;
        q[i] = (int8_t)v;
    }
}

float crynet_dequantise(int8_t v) {
    return ((float)v - (float)CRYNET_OUT_ZP) * CRYNET_OUT_SCALE;
}

/* ---- silence gate -------------------------------------------------------- */
float crynet_window_rms(const int16_t *pcm) {
    float mean = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) mean += (float)pcm[i];
    mean /= (float)CRYNET_N_SAMPLES;
    float acc = 0.0f;
    for (int i = 0; i < CRYNET_N_SAMPLES; i++) {
        float d = ((float)pcm[i] - mean) / 32768.0f;
        acc += d * d;
    }
    return sqrtf(acc / (float)CRYNET_N_SAMPLES);
}

/* ---- host parity test ---------------------------------------------------- */
#ifdef CRYNET_SELFTEST
int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s raw_pcm_s16le.bin\n", argv[0]); return 2; }
    FILE *f = fopen(argv[1], "rb");
    if (!f) { perror("fopen"); return 2; }
    static int16_t pcm[CRYNET_N_SAMPLES];
    size_t got = fread(pcm, sizeof(int16_t), CRYNET_N_SAMPLES, f);
    fclose(f);
    if (got != CRYNET_N_SAMPLES) { fprintf(stderr, "short read\n"); return 2; }
    static float mel[CRYNET_N_FRAMES * CRYNET_N_MELS];
    crynet_log_mel(pcm, mel);
    FILE *o = fopen("mel_c.bin", "wb");
    fwrite(mel, sizeof(float), CRYNET_N_FRAMES * CRYNET_N_MELS, o);
    fclose(o);
    fprintf(stderr, "wrote mel_c.bin  rms=%.6f\n", crynet_window_rms(pcm));
    return 0;
}
#endif
