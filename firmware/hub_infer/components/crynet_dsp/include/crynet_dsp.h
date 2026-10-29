/*
 * CryNet — DSP front end (hub firmware).
 *
 * Turns a 2 s window of int16 PCM into the 81 x 64 standardised log-Mel
 * matrix the trained model expects, then quantises it to int8.
 *
 * The maths is identical to the Python training pipeline (verified on the
 * host to 6.9e-05 max absolute deviation) and to the notebook-generated
 * reference implementation in research/out/dsp_crynet.c. This component
 * differs from that reference in three ways that matter on the target:
 *
 *   - no 130 KB file-scope static buffers; the working memory is allocated
 *     once, from PSRAM when the board has it, so it does not eat the hub's
 *     512 KB of internal SRAM;
 *   - the working set is owned by a context, so the inference task and the
 *     radio task cannot corrupt each other's state;
 *   - the decision rule (silence gate + calibrated threshold) lives next to
 *     the features it depends on.
 *
 * This header deliberately does NOT include the generated crynet_tables.h:
 * that header defines file-scope arrays, and in C a file-scope `const`
 * has external linkage, so it may only be included by one translation
 * unit in the whole firmware. crynet_dsp.c is that translation unit.
 */

#ifndef CRYNET_DSP_H
#define CRYNET_DSP_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Feature geometry — fixed by the trained weights. */
#define CRYNET_N_SAMPLES 32000
#define CRYNET_N_FRAMES  81
#define CRYNET_N_MELS    64
#define CRYNET_N_FFT     512
#define CRYNET_HOP       400
#define CRYNET_CENTER_PAD 256
#define CRYNET_TAIL_PAD  512

#define CRYNET_FEATURE_COUNT (CRYNET_N_FRAMES * CRYNET_N_MELS) /* 5184 */

/* Working memory for the front end. Opaque; call crynet_dsp_init first. */
typedef struct {
    float *window;     /* padded, mean-removed input   (32768 floats) */
    float *power;      /* 257 power-spectrum bins                   */
    float *mel;        /* 64 mel bands                              */
    void  *fft;        /* 512 complex bins                          */
    bool   from_psram; /* true if the buffers live in PSRAM          */
    size_t bytes;      /* total bytes allocated                     */
} crynet_dsp_ctx_t;

/*
 * Allocate the working buffers. Prefers PSRAM (the S3 has 8 MB of it) and
 * falls back to internal SRAM. Returns false if allocation failed.
 */
bool crynet_dsp_init(crynet_dsp_ctx_t *ctx);

void crynet_dsp_free(crynet_dsp_ctx_t *ctx);

/*
 * 2 s window of int16 mono PCM @ 16 kHz -> CRYNET_FEATURE_COUNT floats of
 * standardised log-Mel, laid out frame-major: mel[frame * 64 + band].
 */
void crynet_dsp_features(const crynet_dsp_ctx_t *ctx,
                          const int16_t *pcm,
                          float *mel_out);

/* Standardised log-Mel -> int8 in the model's input quantisation. */
void crynet_dsp_quantise(const float *mel, int8_t *q);

/* RMS of a window after DC removal, in full scale units (0..1). */
float crynet_dsp_rms(const int16_t *pcm);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_DSP_H */
