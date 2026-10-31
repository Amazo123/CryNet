/*
 * CryNet — the radio stage of the hub.  See link_stage.h.
 */

#include "link_stage.h"
#include "ble_alert.h"
#include "hub_display.h"

#include <math.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_now.h"
#include "nvs_flash.h"

#include "crynet_model.h"
#include "crynet_proto.h"
#include "node_link.h"

static const char *TAG = "link";

static bool s_swept = false;

/* How long to wait for a burst before giving up on it.  The node sends
 * 286 fragments with the radio's flow control in the way, so a couple of
 * seconds is normal; fifteen is generous. */
#define BURST_TIMEOUT_MS 15000

/* The pause after a window has been analysed.  The node needs two seconds
 * to refill its window after an upload, so asking again sooner is
 * pointless. */
#define RECOOLDOWN_MS 2500

/* How long a confirmed cry keeps being announced.  A cry lasts for
 * seconds; the model's windows are two seconds apart, and a recording
 * played through a speaker has gaps between the cries, so the display
 * must not flicker back to "quiet" the moment one window comes back
 * negative. */
#define CRY_HOLD_MS 8000

/* How long the burst may go without a fragment before the hub asks for
 * the missing ones again.  The node paces its fragments about thirteen
 * milliseconds apart, so a gap of one and a half seconds is not a slow
 * burst -- it is a burst that has stopped. */
#define FRAG_STALL_MS 1200

/* How long the burst must have been in flight before a stall may be
 * believed.  The node is asked for the window and then starts sending
 * it; the first fragments take a moment to arrive, and a stall
 * detector that fires before the node has begun would ask for the whole
 * window a second time for nothing. */
#define RESEND_MIN_FLIGHT_MS 2500

/* How many times the hub may ask for the missing fragments of one
 * burst.  Each round costs a few frames of air and covers the handful
 * the last round still lost.  Three is enough in practice: the first
 * round asks for everything that is missing, the second for the handful
 * that round also lost, and the third for the one or two that the
 * second lost. */
#define RESEND_MAX_ROUNDS 3

/* How long the node takes to send one fragment.  The node waits ten
 * milliseconds between fragments and the radio needs a couple more, so
 * a hundred fragments take a second and a half.  The hub has to allow
 * for that when it decides a burst has stalled: asking again while the
 * node is still sending wastes a round and floods the air. */
#define FRAG_PER_FRAGMENT_MS 15

typedef struct {
    bool     heard;
    uint8_t  node_id;
    uint16_t seq;
    uint32_t crc;
    uint8_t  flags;
    float    rms;
    bool     window_full;  /* the node says its live window holds 2 s */
    uint8_t  loud_streak;  /* consecutive telemetry readings above the
                            * trigger level */

    bool     requested;      /* a burst is in flight */
    int64_t  requested_at_us;
    uint16_t request_seq;
    uint32_t request_crc;
    uint32_t request_raw;    /* the hub's frame counter when it asked */
    uint32_t request_frags;  /* the hub's fragment counter when it asked */
    uint16_t last_have;      /* the fragment count at the last poll */
    int64_t  last_frag_us;   /* when a fragment last arrived */
    int64_t  last_resend_us; /* when the last resend went out */
    uint8_t  resend_rounds;  /* how many resends this burst has had */

    bool     cry_active;      /* the hub is announcing a cry */
    int64_t  cry_until_us;     /* and it does so until this moment */
    int64_t  cry_started_us;   /* when the current cry began */
    uint8_t  last_confidence;  /* the last confirmed confidence, in percent */
    bool     published_cry;    /* what the caregiver's phone was last told */

    int64_t  last_log_us;      /* when the telemetry was last printed */
    int64_t  last_request_us;   /* when the last window was asked for   */
    uint16_t last_flags;
    uint16_t last_seq;
} node_state_t;

/* One entry per node the hub has heard from. */
static node_state_t state[NODE_LINK_MAX_NODES];

/* The window the hub analyses.  64 KB, so it lives in PSRAM. */
static int16_t *s_window = NULL;
static float    *s_mel = NULL;
static int8_t   *s_q = NULL;

/* The link object the radio stage works through: created by
 * link_stage_radio_start(), used by link_stage_run(). */
static node_link_t *s_nl = NULL;

/* The exact integer mean of a window, and its RMS after that mean has been
 * removed.  The node reports the same numbers over the telemetry, so the
 * two can be compared. */
static int32_t window_mean(const int16_t *pcm, uint32_t n)
{
    int64_t sum = 0;
    for (uint32_t i = 0; i < n; i++) {
        sum += (int64_t)pcm[i];
    }
    return (int32_t)(sum / (int64_t)n);
}

static float window_rms(const int16_t *pcm, uint32_t n, int32_t mean)
{
    int64_t acc = 0;
    for (uint32_t i = 0; i < n; i++) {
        const int32_t d = (int32_t)pcm[i] - mean;
        acc += (int64_t)d * d;
    }
    return (float)(sqrt((double)acc / (double)n) / 32768.0);
}

static int32_t window_peak(const int16_t *pcm, uint32_t n, int32_t mean)
{
    int32_t peak = 0;
    for (uint32_t i = 0; i < n; i++) {
        const int32_t d = (int32_t)pcm[i] - mean;
        if (d < 0 ? -d > peak : d > peak) {
            peak = (d < 0) ? -d : d;
        }
    }
    return peak;
}

/* Analyse one window and report what the model says about it. */
static void analyse(crynet_dsp_ctx_t *dsp, crynet_infer_t *infer,
                    node_state_t *st, const int16_t *pcm)
{
    const uint8_t node_id = st->node_id;
    const int32_t mean = window_mean(pcm, CRYNET_N_SAMPLES);
    const float rms = window_rms(pcm, CRYNET_N_SAMPLES, mean);
    const int32_t peak = window_peak(pcm, CRYNET_N_SAMPLES, mean);

    ESP_LOGI(TAG, "node %u: window rms %.6f  mean %d  peak %d",
             node_id, (double)rms, (int)mean, (int)peak);

    const int64_t t0 = esp_timer_get_time();
    crynet_dsp_features(dsp, pcm, s_mel);
    crynet_dsp_quantise(s_mel, s_q);
    const int64_t t1 = esp_timer_get_time();

    float p_no_cry = 0.0f, p_cry = 0.0f;
    if (!crynet_infer_run(infer, s_q, &p_no_cry, &p_cry)) {
        ESP_LOGE(TAG, "inference failed: %s", crynet_infer_error(infer));
        return;
    }
    const int64_t t2 = esp_timer_get_time();

    const bool silent = rms < CRYNET_SILENCE_RMS_GATE;
    const bool confirmed = (!silent) && (p_cry >= CRYNET_THRESHOLD);

    /* A confirmed cry is held: the announcement outlives the window
     * that confirmed it, so the display does not flicker while the
     * recording's gaps pass by. */
    const int64_t now = esp_timer_get_time();
    if (confirmed) {
        if (!st->cry_active) {
            st->cry_started_us = now;
        }
        st->cry_active = true;
        st->cry_until_us = now + (CRY_HOLD_MS * 1000);
        st->last_confidence = (uint8_t)(p_cry * 100.0f + 0.5f);
    } else if (st->cry_active && now > st->cry_until_us) {
        st->cry_active = false;
    }

    ESP_LOGI(TAG, "node %u: front end %.1f ms, inference %.1f ms, "
                  "P(no_cry)=%.4f P(cry)=%.4f",
             node_id, (double)(t1 - t0) / 1000.0, (double)(t2 - t1) / 1000.0,
             (double)p_no_cry, (double)p_cry);
    ESP_LOGI(TAG, "node %u: %s", node_id,
             st->cry_active ? (confirmed ? "ALERT — cry" : "cry (held)")
                            : (silent ? "silent" : "no cry"));
}

/* Whether the hub is announcing a cry for a node.  The display and the
 * BLE server read this, so they show one state and not two. */
bool link_stage_crying(uint8_t node_id)
{
    const int64_t now = esp_timer_get_time();
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        if (state[i].heard && state[i].node_id == node_id) {
            if (state[i].cry_active && now > state[i].cry_until_us) {
                state[i].cry_active = false;
            }
            return state[i].cry_active;
        }
    }
    return false;
}

bool link_stage_radio_start(void)
{
    /* The Wi-Fi driver opens the NVS partition during esp_wifi_init(), so
     * it has to be initialised first. */
    const esp_err_t nv = nvs_flash_init();
    if (nv != ESP_OK && nv != ESP_ERR_NVS_NO_FREE_PAGES) {
        ESP_LOGE(TAG, "nvs_flash_init failed: %s", esp_err_to_name(nv));
        return false;
    }

    s_nl = node_link_create();
    if (s_nl == NULL) {
        ESP_LOGE(TAG, "the link could not be created");
        return false;
    }
    if (!node_link_start(s_nl)) {
        ESP_LOGE(TAG, "the radio could not be started");
        return false;
    }

    ESP_LOGI(TAG, "listening on ESP-NOW; asking for audio at RMS >= %.3f",
             (double)CRYNET_TRIGGER_RMS);
    return true;
}

void link_stage_run(crynet_dsp_ctx_t *dsp, crynet_infer_t *infer)
{
    s_window = heap_caps_malloc(CRYNET_N_SAMPLES * sizeof(int16_t),
                                 MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (s_window == NULL) {
        s_window = heap_caps_malloc(CRYNET_N_SAMPLES * sizeof(int16_t),
                                    MALLOC_CAP_8BIT);
    }
    s_mel = heap_caps_malloc(CRYNET_FEATURE_COUNT * sizeof(float), MALLOC_CAP_8BIT);
    s_q = heap_caps_malloc(CRYNET_FEATURE_COUNT * sizeof(int8_t), MALLOC_CAP_8BIT);
    if (s_window == NULL || s_mel == NULL || s_q == NULL) {
        ESP_LOGE(TAG, "no memory for the analysis buffers");
        return;
    }

    /* The radio was started by link_stage_radio_start(), before the
     * Bluetooth stack took its share of the internal RAM. */
    node_link_t *nl = s_nl;
    if (nl == NULL) {
        ESP_LOGE(TAG, "the radio is not running; "
                      "call link_stage_radio_start() first");
        return;
    }

    int64_t last_stats_us = 0;
    int64_t last_probe_us = 0;

    for (;;) {
        /* ---------------- telemetry ---------------- */
        node_link_telemetry_t tel;
        while (node_link_poll_telemetry(nl, &tel)) {
            node_state_t *st = NULL;
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (!state[i].heard) {
                    state[i].heard = true;
                    state[i].node_id = tel.node_id;
                    st = &state[i];
                    break;
                }
                if (state[i].node_id == tel.node_id) {
                    st = &state[i];
                    break;
                }
            }
            if (st == NULL) {
                continue;
            }

            st->seq = tel.burst_seq;
            st->crc = tel.frozen_crc;
            st->flags = tel.flags;
            st->rms = tel.rms;
            st->window_full = (tel.flags & CRYNET_PROTO_FLAG_WINDOW_FULL) != 0;

            /* The node has moved on to a newer window.  The burst in
             * flight can never be completed -- the node no longer
             * holds the fragments of the old one, so it cannot send
             * them again -- and waiting out the timeout would only
             * delay the next attempt.  The burst is abandoned and the
             * newer window is asked for instead. */
            if (st->requested && st->seq != st->request_seq &&
                (tel.flags & CRYNET_PROTO_FLAG_BURST_READY) != 0) {
                ESP_LOGW(TAG, "node %u: the node moved to window %u while "
                              "window %u was in flight; asking for the new one",
                         tel.node_id, (unsigned)tel.burst_seq,
                         (unsigned)st->request_seq);
                node_link_reset_burst(nl, tel.node_id);
                st->requested = false;
                st->last_request_us = 0;
            }

            /* How long the level has been sustained.  A cry lasts for
             * seconds; the microphone's slow DC drift produces one lone
             * reading above the trigger, and a single reading is not
             * worth a 286-fragment burst. */
            if (tel.rms >= CRYNET_TRIGGER_RMS) {
                if (st->loud_streak < 255u) {
                    st->loud_streak++;
                }
            } else {
                st->loud_streak = 0;
            }

            const int64_t now = esp_timer_get_time();
            const bool changed = (tel.flags != st->last_flags) ||
                                 (tel.burst_seq != st->last_seq);
            if (changed || (now - st->last_log_us) > 1000000) {
                st->last_log_us = now;
                st->last_flags = tel.flags;
                st->last_seq = tel.burst_seq;
                ESP_LOGI(TAG, "node %u: rms %.4f  seq %u  flags 0x%02X  crc 0x%08X",
                         tel.node_id, (double)tel.rms, (unsigned)tel.burst_seq,
                         (unsigned)tel.flags, (unsigned)tel.frozen_crc);
            }
        }

        /* ---------------- requests and bursts ---------------- */
        const int64_t now = esp_timer_get_time();

        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            node_state_t *st = &state[i];
            if (!st->heard) {
                continue;
            }

            if (st->requested) {
                node_link_burst_t burst;
                if (node_link_burst_state(nl, st->node_id, &burst)) {
                    /* Watch the fragment count: a burst that stops
                     * growing has stopped, and that is the moment to ask
                     * for what is missing rather than to wait out the
                     * timeout. */
                    if (burst.frag_have != st->last_have) {
                        st->last_have = burst.frag_have;
                        st->last_frag_us = now;
                    }
                    if (burst.complete) {
                        const int64_t t0 = esp_timer_get_time();
                        if (node_link_take_window(nl, st->node_id, s_window,
                                                  CRYNET_N_SAMPLES)) {
                            const uint32_t crc = crynet_proto_crc32(
                                (const uint8_t *)s_window, CRYNET_N_SAMPLES * 2u);
                            /* The CRC can only be checked when the node
                             * served the window the hub asked for.  If it
                             * moved on to a newer one, comparing the two
                             * would report a mismatch that means
                             * nothing, so the log says "not verified"
                             * instead. */
                            const bool checkable = (st->request_crc != 0) &&
                                                  (burst.burst_seq == st->request_seq);
                            const bool match = checkable && (crc == st->request_crc);
                            ESP_LOGI(TAG, "node %u: %u/%u fragments in %.2f s",
                                     st->node_id, (unsigned)burst.frag_have,
                                     (unsigned)burst.frag_want,
                                     (double)(t0 - st->requested_at_us) / 1000000.0);
                            if (checkable) {
                                ESP_LOGI(TAG, "node %u: window crc32 0x%08X, the node "
                                              "advertised 0x%08X -> %s",
                                         st->node_id, (unsigned)crc,
                                         (unsigned)st->request_crc,
                                         match ? "MATCH" : "MISMATCH");
                            } else if (st->request_crc != 0) {
                                ESP_LOGI(TAG, "node %u: window crc32 0x%08X, not verified "
                                              "(the node served window %u, the hub "
                                              "asked for %u)",
                                         st->node_id, (unsigned)crc,
                                         (unsigned)burst.burst_seq,
                                         (unsigned)st->request_seq);
                            } else {
                                ESP_LOGI(TAG, "node %u: live window, crc32 0x%08X "
                                              "(the node had no frozen window to "
                                              "compare against)",
                                         st->node_id, (unsigned)crc);
                            }
                            analyse(dsp, infer, st, s_window);
                        }
                        st->requested = false;
                        st->last_log_us = esp_timer_get_time();
                    } else {
                        /* The burst is short of fragments.  If it has
                         * stopped arriving, ask the node for the ones
                         * that are missing: the hub's radio also carries
                         * Bluetooth, and while it is retuned to a BLE
                         * channel the Wi-Fi receiver is deaf, so a
                         * burst sent flat out always loses a few frames
                         * in the air.  The node keeps the window it
                         * froze, so it can send them again. */
                        /* The wait before a burst counts as stalled
                         * grows with the number of fragments the node
                         * still has to send: a hundred missing
                         * fragments take a second and a half to arrive,
                         * and a burst that is quiet for less than that
                         * is a burst still in flight. */
                        const int still_missing =
                            (int)burst.frag_want - (int)burst.frag_have;
                        const int64_t stall_us =
                            ((int64_t)FRAG_STALL_MS +
                             (int64_t)still_missing * FRAG_PER_FRAGMENT_MS) * 1000;
                        const bool stalled =
                            (now - st->last_frag_us) > stall_us;
                        const bool long_enough =
                            (now - st->requested_at_us) > (RESEND_MIN_FLIGHT_MS * 1000);
                        /* A second round waits out a stall period of
                         * its own: the fragments the last round asked
                         * for are on the air, and asking again before
                         * they arrive only spends a round. */
                        const bool settled =
                            (now - st->last_resend_us) > stall_us;
                        if (stalled && long_enough && settled &&
                            st->resend_rounds < RESEND_MAX_ROUNDS) {
                            const int asked = node_link_request_missing(
                                nl, st->node_id, st->request_seq);
                            if (asked > 0) {
                                st->resend_rounds++;
                                st->last_resend_us = now;
                                ESP_LOGW(TAG, "node %u: the burst stalled with "
                                              "%u of %u fragments; asking for "
                                              "the %u that are missing",
                                         st->node_id, (unsigned)burst.frag_have,
                                         (unsigned)burst.frag_want,
                                         (unsigned)asked);
                            }
                        } else if ((now - st->requested_at_us) >
                                   (BURST_TIMEOUT_MS * 1000)) {
                        ESP_LOGW(TAG, "node %u: the burst timed out with %u of %u "
                                      "fragments",
                                 st->node_id, (unsigned)burst.frag_have,
                                 (unsigned)burst.frag_want);
                        {
                            node_link_stats_t rs;
                            node_link_get_stats(nl, &rs);
                            ESP_LOGW(TAG, "node %u: %u frames reached the hub "
                                          "during the burst, %u of them "
                                          "fragments",
                                     st->node_id,
                                     (unsigned)(rs.raw_frames - st->request_raw),
                                     (unsigned)(rs.frag_frames - st->request_frags));
                        }
                        /* Which ones are missing?  A burst that lost its
                         * first frames lost them to the request; one that
                         * lost its last frames never had them sent; a
                         * scattered set was lost in the air. */
                        uint16_t missing[16];
                        const int n_missing = node_link_burst_missing(
                            nl, st->node_id, missing,
                            (int)(sizeof missing / sizeof missing[0]));
                        if (n_missing > 0) {
                            ESP_LOGW(TAG, "node %u: missing fragments:",
                                     st->node_id);
                            for (int m = 0; m < n_missing; m++) {
                                ESP_LOGW(TAG, "  %u", (unsigned)missing[m]);
                            }
                        }
                        node_link_reset_burst(nl, st->node_id);
                        st->requested = false;
                        }
                    }
                }
                continue;
            }

            /* Nothing in flight.  Ask for a window when the node's own
             * level says there is something to hear and its window holds a
             * full two seconds. */
            /* Two conditions, and both have to hold.  The hub's own: the
             * node's RMS has reached the level above which audio is worth
             * classifying, and has stayed there for two readings (a cry
             * lasts for seconds; the microphone's DC drift produces one
             * lone reading).  And the node's: it froze a window, which is
             * the loudest two seconds it has, and the one whose CRC-32
             * can be checked against what the node advertises. */
            const bool loud = (st->loud_streak >= 2u);
            /* Only ask for a window the node has actually frozen.  The
             * node's live window is emptied by an upload and needs two
             * seconds to refill, and a request that arrives in that gap
             * is ignored — the burst times out with nothing received.
             * The node freezes at the same level the hub triggers at, so
             * a loud telemetry always carries this flag. */
            const bool frozen =
                (st->flags & CRYNET_PROTO_FLAG_BURST_READY) != 0;
            if (loud && frozen && st->window_full &&
                (now - st->last_request_us) > (RECOOLDOWN_MS * 1000)) {
                if (node_link_request_window(nl, st->node_id, st->seq)) {
                    st->requested = true;
                    st->requested_at_us = now;
                    st->request_seq = st->seq;
                    st->request_crc = st->crc;
                    {
                        /* How many frames the hub has seen, so the
                         * timeout can say how many arrived during the
                         * burst: if the number is the number of
                         * fragments, they reached the hub and the
                         * reassembly is at fault; if it is short, they
                         * were lost on the way. */
                        node_link_stats_t rs;
                        node_link_get_stats(nl, &rs);
                        st->request_raw = rs.raw_frames;
                        st->request_frags = rs.frag_frames;
                    }
                    st->last_request_us = now;
                    st->last_have = 0;
                    st->last_frag_us = now;
                    st->last_resend_us = 0;
                    st->resend_rounds = 0;
                    /* The node drops its live window when it serves a
                     * request and refills it over the next two seconds,
                     * so until it says the window is whole again there is
                     * nothing to ask for. */
                    st->window_full = false;
                    ESP_LOGI(TAG, "node %u: asking for the window (seq %u, rms %.4f)",
                             st->node_id, (unsigned)st->seq, (double)st->rms);
                } else {
                    ESP_LOGW(TAG, "node %u: the request could not be sent",
                             st->node_id);
                }
            }
        }

        /* ---------------- the caregiver's phone ---------------- */
        /* The alert is published when the state *changes*: once when a
         * cot starts crying and once when it stops, not once for every
         * two-second window. */
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            node_state_t *st = &state[i];
            if (!st->heard) {
                continue;
            }
            const bool crying = link_stage_crying(st->node_id);
            if (crying == st->published_cry) {
                continue;
            }
            st->published_cry = crying;
            ble_alert_publish(st->node_id, crying, st->last_confidence);

            /* The state characteristic carries the whole system. */
            ble_state_packet_t sp;
            memset(&sp, 0, sizeof sp);
            for (int j = 0; j < NODE_LINK_MAX_NODES; j++) {
                if (!state[j].heard) {
                    continue;
                }
                sp.cots++;
                if (state[j].published_cry) {
                    if (state[j].node_id >= 1 && state[j].node_id <= 8) {
                        sp.crying_mask |= (uint8_t)(1u << (state[j].node_id - 1));
                    }
                    if (state[j].last_confidence > sp.confidence_pct) {
                        sp.confidence_pct = state[j].last_confidence;
                    }
                    if (state[j].cry_started_us > 0) {
                        const int64_t age = (esp_timer_get_time() -
                                             state[j].cry_started_us) / 1000000;
                        if ((uint32_t)age > sp.started_at_s) {
                            sp.started_at_s = (uint32_t)age;
                        }
                    }
                }
            }
            ble_alert_publish_state(&sp);
        }

        /* While no node has been heard, probe.  The probe asks for a
         * single fragment, which is enough to prove that the two boards
         * can talk and which way the traffic is failing. */
        bool any_heard = false;
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            if (state[i].heard) {
                any_heard = true;
            }
        }
        const int64_t probe_now = esp_timer_get_time();
        /* Learned peers are added here rather than in the receive
         * callback: the callback runs in the Wi-Fi task and
         * esp_now_add_peer() waits for that task, which would block the
         * radio. */
        node_link_service_peers(nl);

        if (!any_heard && (probe_now - last_probe_us) > 2000000) {
            last_probe_us = probe_now;
            uint8_t frame[CRYNET_PROTO_REQUEST_BYTES];
            const size_t flen = crynet_proto_build(frame,
                                                    CRYNET_PROTO_TYPE_REQUEST,
                                                    0xFF, 0u, 0u, 1u, NULL, 0u);
            static const uint8_t bcast[6] =
                {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
            const esp_err_t err = esp_now_send(bcast, frame, flen);
            ESP_LOGI(TAG, "probe: sent to everybody, %s",
                     (err == ESP_OK) ? "ok" : esp_err_to_name(err));
        }

        /* ---------------- the display ---------------- */
        /* One snapshot per loop: the crying cot if there is one,
         * otherwise the loudest node the hub has heard from.
         *
         * When two cots hear the same cry — they are in the same room,
         * so they all hear it — the one that hears it *loudest* is the
         * one the baby is in.  So the display names the loudest crying
         * cot, not the first one the hub happens to have heard from. */
        node_state_t *show = NULL;
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            if (state[i].heard && link_stage_crying(state[i].node_id)) {
                if (show == NULL || state[i].rms > show->rms) {
                    show = &state[i];
                }
            }
        }
        if (show == NULL) {
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (state[i].heard &&
                    (show == NULL || state[i].rms > show->rms)) {
                    show = &state[i];
                }
            }
        }
        hub_display_state_t ds;
        memset(&ds, 0, sizeof ds);
        if (show != NULL) {
            ds.linked = true;
            ds.crying = link_stage_crying(show->node_id);
            ds.cot_id = show->node_id;
            ds.confidence = show->last_confidence;
            ds.level = show->rms;
        }
        hub_display_update(&ds);

        const int64_t stats_now = esp_timer_get_time();
        if ((stats_now - last_stats_us) > 5000000) {
            last_stats_us = stats_now;
            node_link_stats_t st;
            node_link_get_stats(nl, &st);
            ESP_LOGI(TAG, "link: %u frames off the air, %u parsed, %u bad, "
                          "%u bad payload, %u requests sent, %u failed",
                     (unsigned)st.raw_frames, (unsigned)st.frames_ok,
                     (unsigned)st.frames_bad, (unsigned)st.payloads_bad,
                     (unsigned)st.requests_sent, (unsigned)st.requests_failed);
            /* The air counters only move when promiscuous mode is on,
             * which it is not by default; skip the line rather than
             * print two zeroes every five seconds. */
            if (node_link_promisc_total() > 0) {
                ESP_LOGI(TAG, "air: %u frames seen raw, %u carrying our magic",
                         (unsigned)node_link_promisc_total(),
                         (unsigned)node_link_promisc_magic());
            }

        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
