
/* ===========================================================================
 * crynet_infer_example.c — glue between the DSP front end and TFLite Micro.
 *
 * Port this into the ESP32-S3 firmware.  It assumes:
 *   - model_data.h   (the INT8 model as a C array)
 *   - crynet_tables.h (Mel filterbank, Hann window, quantisation constants)
 *   - dsp_crynet.c   (the log-Mel front end)
 *
 * ESP-IDF: add the TensorFlowLite-ESP32 component and include
 * "tensorflow/lite/micro/micro_interpreter.h".
 * =========================================================================*/
#include <stdint.h>
#include <string.h>

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "dsp_crynet.h"
#include "model_data.h"

#ifndef CRYNET_ARENA_SIZE
#define CRYNET_ARENA_SIZE 120000   /* bytes; raise if AllocateTensors fails */
#endif

/* The ops the exported model uses: CONV_2D, DEPTHWISE_CONV_2D, MAX_POOL_2D,
 * MEAN, FULLY_CONNECTED, SOFTMAX.  AddConv2D() etc. come from
 * tensorflow/lite/micro/kernels/kernel_registrar.h. */
static tflite::MicroMutableOpResolver<6> g_resolver;
static tflite::MicroInterpreter *g_interp = nullptr;
static uint8_t *g_arena = nullptr;

bool crynet_init() {
  g_arena = (uint8_t *)malloc(CRYNET_ARENA_SIZE);
  if (g_arena == nullptr) return false;
  g_resolver.AddConv2D();
  g_resolver.AddDepthwiseConv2D();
  g_resolver.AddMaxPool2D();
  g_resolver.AddMean();            /* GlobalAveragePooling2D lowers to MEAN */
  g_resolver.AddFullyConnected();
  g_resolver.AddSoftmax();

  const tflite::Model *model = tflite::GetModel(crynet_model);
  static tflite::MicroInterpreter interpreter(model, g_resolver, g_arena,
                                              CRYNET_ARENA_SIZE);
  if (interpreter.AllocateTensors() != kTfLiteOk) return false;
  g_interp = &interpreter;
  return true;
}

/* pcm: CRYNET_N_SAMPLES int16 samples @ 16 kHz mono.
 * Returns P(cry) in [0, 1]; 0.0 if the window is silent or inference failed. */
float crynet_probability(const int16_t *pcm) {
  if (g_interp == nullptr) return 0.0f;
  if (crynet_window_rms(pcm) < CRYNET_SILENCE_RMS) return 0.0f;   /* silence gate */

  static float mel[CRYNET_N_FRAMES * CRYNET_N_MELS];
  static int8_t quant[CRYNET_N_FRAMES * CRYNET_N_MELS];
  crynet_log_mel(pcm, mel);
  crynet_quantise(mel, quant);

  TfLiteTensor *in = g_interp->input(0);
  memcpy(in->data.raw, quant, sizeof(quant));
  in->bytes = sizeof(quant);
  if (g_interp->Invoke() != kTfLiteOk) return 0.0f;

  TfLiteTensor *out = g_interp->output(0);
  const int8_t *o = out->data.int8;
  /* output order is [P(no_cry), P(cry)] */
  return (float)(o[1] - out->params.zero_point) * out->params.scale;
}

/* Call once per 2 s window; returns true when the alarm should fire. */
bool crynet_is_cry(const int16_t *pcm, float *confidence) {
  const float p = crynet_probability(pcm);
  if (confidence) *confidence = p;
  return p >= CRYNET_THRESHOLD;
}
