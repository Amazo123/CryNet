/*
 * CryNet — TFLite Micro inference component.
 *
 * A thin C API over the TFLite Micro interpreter. The interpreter itself
 * is C++, so it is hidden behind an opaque handle and this header is
 * usable from plain C.
 *
 * The model is the INT8 graph produced by the training notebook
 * (crynet_model_bytes()), so the weights, the input quantisation and the
 * output quantisation all come from the same artifact — the firmware
 * never carries its own copy of the calibration numbers.
 */

#ifndef CRYNET_INFER_H
#define CRYNET_INFER_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct crynet_infer crynet_infer_t;

/*
 * Create the interpreter. Allocates the tensor arena (PSRAM first) and
 * allocates the tensors. Returns NULL only if the model itself is
 * unusable; a returned handle with ready == false carries the reason in
 * crynet_infer_error().
 */
crynet_infer_t *crynet_infer_create(void);

void crynet_infer_destroy(crynet_infer_t *inf);

/*
 * Run one 2 s window. `features` is CRYNET_FEATURE_COUNT int8 values in
 * the model's input quantisation. p_no_cry / p_cry receive the
 * dequantised class probabilities; either may be NULL.
 */
bool crynet_infer_run(crynet_infer_t *inf,
                      const int8_t *features,
                      float *p_no_cry,
                      float *p_cry);

/* Bytes of tensor arena reserved, and how much of it the model used. */
size_t crynet_infer_arena_bytes(const crynet_infer_t *inf);
size_t crynet_infer_arena_used(const crynet_infer_t *inf);

/* Last error text ("" when there was none). */
const char *crynet_infer_error(const crynet_infer_t *inf);

/* True once the interpreter has allocated its tensors successfully. */
bool crynet_infer_ready(const crynet_infer_t *inf);

#ifdef __cplusplus
}
#endif

#endif /* CRYNET_INFER_H */
