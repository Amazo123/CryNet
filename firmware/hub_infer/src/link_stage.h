/*
 * CryNet — the radio stage of the hub.
 *
 * Stage 2c's first artifact: the hub listens to the nodes, decides when
 * there is something worth classifying, pulls the two-second window over
 * ESP-NOW and runs it through the Stage 2a inference core.
 *
 * The decision rule is the one frozen at the start of the rebuild: the
 * hub asks for audio once the node's RMS reaches 0.03, and the *model*
 * decides whether that audio is a cry.  The older firmware pulled audio
 * at RMS 0.18, so a soft cry never reached the classifier at all.
 */

#ifndef LINK_STAGE_H
#define LINK_STAGE_H

#include "crynet_dsp.h"
#include "crynet_infer.h"

#ifdef __cplusplus
extern "C" {
#endif

/* The level at which the hub asks a node for its window.  Anything above
 * this is worth classifying; the model rejects the false triggers. */
#define CRYNET_TRIGGER_RMS 0.030f

/* Run the radio stage.  Never returns. */
void link_stage_run(crynet_dsp_ctx_t *dsp, crynet_infer_t *infer);

#ifdef __cplusplus
}
#endif

#endif /* LINK_STAGE_H */
