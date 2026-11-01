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
 * this is worth classifying; the model rejects the false triggers.
 *
 * This is now only the fallback: the node tracks the room's noise floor
 * and reports the level it follows from it, and the hub triggers on the
 * node's number.  A fixed level of 0.030 put the system's reach at a
 * constant — a cry a metre from the node, with a median RMS of 0.0070,
 * never once reached it — so the floor is now tracked where the audio
 * actually is.  This constant is what a node that reports no level of
 * its own gets. */
#define CRYNET_TRIGGER_RMS 0.030f

/* The confidence at which one window is enough to announce a cry.
 *
 * The model's answer for a window that is very nearly silent is not
 * reliable: measured on the real boards, the same quiet room produced
 * verdicts of 0.0000 and of 0.9766 for windows that differ by nothing a
 * person could hear, and the second of those is a false alarm.  The
 * model's output saturates at 0.9961 for a clear cry, so a window that
 * reaches this level is announcing itself, and it is announced at once
 * — the panel still shows the cry two and a half seconds after it
 * happened, provided the window carries real energy (see
 * CRYNET_ANNOUNCE_MIN_RMS below).  Anything between the model's own
 * threshold and this one is a maybe, and a maybe has to be confirmed by
 * the next window before it is announced (see CRYNET_CRY_RUN in
 * link_stage.c). */
#define CRYNET_CLEAR_CRY 0.9900f

/* The rms below which no window may announce a cry at all, however
 * confident the model says it is.
 *
 * The adaptive trigger sends the model windows the old fixed 0.030
 * trigger never would, and the model is not a reliable judge of a
 * window that is nearly silent.  Measured on the real boards: the
 * quietest genuine cry that reached the model carried 0.0103 rms (the
 * phone cry at one metre), while quiet-room windows at 0.002-0.012 have
 * scored up to 0.9883.  This gate sits under the quietest genuine cry
 * with room to spare, so the one-metre cry still announces and a
 * near-silent window cannot. */
#define CRYNET_ANNOUNCE_MIN_RMS 0.006f

/* How many windows in a row have to say cry before a maybe is
 * announced.  Two: a cry lasts for seconds and its windows agree, while
 * a noise fluctuation that happens to look like a cry is not repeated
 * in the next window.
 *
 * That assumption failed in a quiet room: the trigger pins at its
 * minimum there, the hub judges near-silent window after near-silent
 * window, their verdicts scatter across 0.95-0.99 for no audible
 * reason, and two of them in a row confirmed each other into fourteen
 * false alarms in one evening.  A maybe therefore only counts toward
 * the run when its window carries real energy (CRYNET_MAYBE_MIN_RMS). */
#define CRYNET_CRY_RUN 2u

/* The rms a window needs before its maybe can count toward the
 * confirming run.  Every measured genuine cry announced saturated
 * (>= 0.99, the unmistakable path) — the run exists for a real cry that
 * scores just over the threshold, and that comes with sound behind it.
 * The measured false maybes all sat at 0.012 rms or under. */
#define CRYNET_MAYBE_MIN_RMS 0.020f

/* The peak-to-rms ratio (crest factor) a quiet window needs before its
 * saturated verdict may announce a cry.  A loud window (>= 0.020 rms)
 * announces on saturation alone; a quiet one must also have a cry's
 * shape, because the model has been known to saturate on flat hiss.
 * Measured on the real boards: every quiet window that scored highly
 * and was not a cry had a crest of 2.2-2.9 (room hiss is Gaussian, no
 * impulses), and the quietest genuine cry — the phone cry at one metre,
 * P(cry)=0.9961 at 0.0103 rms — had a crest of 5.6; the 15 cm cries
 * measured 6.6-6.9.  A loud bump has a high crest too, but the model
 * refuses bumps on its own (measured 0.0977), so this gate only does
 * work exactly where the model is least trustworthy. */
#define CRYNET_QUIET_CREST 3.5f

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
