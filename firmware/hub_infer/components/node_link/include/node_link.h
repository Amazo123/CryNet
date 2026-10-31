/*
 * CryNet — the hub's half of the node link.
 *
 * The node is a dumb sensor: it reports its 100 ms RMS over ESP-NOW every
 * 100 ms, and when the hub asks, it uploads its two-second window as 286
 * CRC-framed fragments.  This component is the hub's side of that
 * conversation:
 *
 *   - it receives and validates every frame the nodes send;
 *   - it keeps the telemetry of every node it has heard;
 *   - it reassembles a burst into one 32000-sample int16 window, in the
 *     right order, with every fragment's CRC checked;
 *   - it asks a node for that window.
 *
 * The window it hands back is the same PCM the node's microphone produced,
 * so the front end on the hub sees exactly the signal the contract
 * describes — no resampling, no gain change, nothing.
 *
 * Design note — reassembly tolerates loss by design.  A fragment that never
 * arrives leaves a hole, and the burst is reported as incomplete rather than
 * silently analysed as if it were whole.  The hub's decision is only ever
 * made on a window with every fragment present.
 */

#ifndef NODE_LINK_H
#define NODE_LINK_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "crynet_proto.h"

#ifdef __cplusplus
extern "C" {
#endif

/* How many cot nodes the hub tracks.  The project is specified for three;
 * one more than that is headroom. */
#define NODE_LINK_MAX_NODES 4

typedef struct node_link node_link_t;

/* The newest telemetry seen from a node. */
typedef struct {
    uint8_t  node_id;
    uint16_t burst_seq;   /* the sequence of the window the node would send */
    float    rms;         /* the node's 100 ms RMS, in full-scale units */
    uint16_t window_ms;
    uint8_t  flags;
    uint32_t frozen_crc;  /* the node's frozen-window CRC-32, 0 if it has none */
    uint32_t age_ms;      /* how long ago this telemetry arrived */
} node_link_telemetry_t;

/* The state of one node's burst. */
typedef struct {
    uint8_t  node_id;
    uint16_t burst_seq;
    uint16_t frag_want;
    uint16_t frag_have;
    bool     complete;
    uint32_t bad_payloads;  /* fragments whose payload CRC failed */
    uint32_t missing;       /* fragments still outstanding */
} node_link_burst_t;

/* Counters for the whole link. */
typedef struct {
    uint32_t raw_frames;   /* frames off the air, before any parsing */
    uint32_t frag_frames;  /* fragment frames received, whatever they carried */
    uint32_t frames_ok;
    uint32_t frames_bad;      /* malformed or frame-CRC failures */
    uint32_t payloads_bad;    /* the frame was sound, the payload was not */
    uint32_t requests_sent;
    uint32_t requests_failed;
    uint32_t resends_sent;   /* requests for the fragments that went missing */
} node_link_stats_t;

/* Create the link.  Returns NULL only if the memory for the windows
 * cannot be found. */
node_link_t *node_link_create(void);

void node_link_destroy(node_link_t *nl);

/*
 * Bring up Wi-Fi and ESP-NOW and start listening.  Returns false if the
 * radio could not be started; the reason is logged by the component.
 *
 * The NVS partition must have been initialised (nvs_flash_init) before
 * this is called: the Wi-Fi driver keeps its calibration and MAC tables
 * there and opens that partition during esp_wifi_init().
 */
bool node_link_start(node_link_t *nl);

/* True once the radio is up. */
bool node_link_ready(const node_link_t *nl);

/*
 * Take the newest telemetry from any node.  Returns false when nothing new
 * has arrived since the last call.
 */
bool node_link_poll_telemetry(node_link_t *nl, node_link_telemetry_t *out);

/* The last telemetry seen from a node, whether or not it is new. */
bool node_link_last_telemetry(const node_link_t *nl, uint8_t node_id,
                              node_link_telemetry_t *out);

/*
 * Ask a node for its two-second window.  `burst_seq` is the sequence the
 * node advertised in its telemetry; sending it makes the node serve the
 * frozen snapshot it took when it crossed its event level.
 */
bool node_link_request_window(node_link_t *nl, uint8_t node_id, uint16_t burst_seq);

/* The state of a node's burst.  False if the node is unknown. */
bool node_link_burst_state(const node_link_t *nl, uint8_t node_id,
                           node_link_burst_t *out);

/* Which fragments of the burst in flight are still missing. */
int node_link_burst_missing(node_link_t *nl, uint8_t node_id,
                            uint16_t *out, int max);

/*
 * Ask the node to send the fragments of the burst in flight that never
 * arrived.  The request carries a bitmap of exactly the missing
 * fragments, so one request covers a scattered set of losses.
 *
 * Returns the number of fragments asked for, 0 if nothing was missing,
 * or -1 if the request could not be built or sent.
 */
int node_link_request_missing(node_link_t *nl, uint8_t node_id, uint16_t seq);

/*
 * Copy a node's reassembled window into `dst`, which must have room for
 * CRYNET_PROTO_WINDOW_SAMPLES int16 samples.  Returns false if the window
 * is not complete.
 */
bool node_link_take_window(node_link_t *nl, uint8_t node_id,
                           int16_t *dst, size_t dst_samples);

/*
 * Add any node whose address was learned since the last call.  Must be
 * called regularly from an application task — esp_now_add_peer() waits for
 * the Wi-Fi task, so it must never be called from the receive callback.
 */
void node_link_service_peers(node_link_t *nl);

/* Diagnostic counters from the promiscuous receive callback. */
void node_link_sweep_channel(uint8_t ch);

uint32_t node_link_promisc_total(void);
uint32_t node_link_promisc_magic(void);

/* Forget a node's partial burst, e.g. after it timed out. */
void node_link_reset_burst(node_link_t *nl, uint8_t node_id);

void node_link_get_stats(const node_link_t *nl, node_link_stats_t *out);


#ifdef __cplusplus
}
#endif

#endif /* NODE_LINK_H */
