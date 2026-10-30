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

/* Bring the radio up: NVS, then ESP-NOW.  Call it before the Bluetooth
 * stack starts — NimBLE's pools come out of the same internal RAM the
 * Wi-Fi driver allocates its buffers from, and when BLE claimed its
 * memory first the Wi-Fi driver ran out mid-init and the link never
 * started.  Returns false if the radio could not be started. */
bool link_stage_radio_start(void);

/* Run the radio stage.  Never returns.  The radio must already be up. */
void link_stage_run(crynet_dsp_ctx_t *dsp, crynet_infer_t *infer);

/* Whether the hub is announcing a cry for a node.  A confirmed cry is
 * held for a few seconds, so this stays true across the gaps in a
 * recording.  The display and the BLE server read this. */
bool link_stage_crying(uint8_t node_id);

#ifdef __cplusplus
}
#endif

#endif /* LINK_STAGE_H */
