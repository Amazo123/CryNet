/*
 * CryNet — the radio stage of the hub.  See link_stage.h.
 */

#include "link_stage.h"

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

typedef struct {
    bool     heard;
    uint8_t  node_id;
    uint16_t seq;
    uint32_t crc;
    uint8_t  flags;
    float    rms;
    bool     window_full;  /* the node says its live window holds 2 s */

    bool     requested;      /* a burst is in flight */
    int64_t  requested_at_us;
    uint16_t request_seq;
    uint32_t request_crc;

    int64_t  last_log_us;      /* when the telemetry was last printed */
    int64_t  last_request_us;   /* when the last window was asked for   */
    uint16_t last_flags;
    uint16_t last_seq;
} node_state_t;

/* The window the hub analyses.  64 KB, so it lives in PSRAM. */
static int16_t *s_window = NULL;
static float    *s_mel = NULL;
static int8_t   *s_q = NULL;

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
                    uint8_t node_id, const int16_t *pcm)
{
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
    const bool alert = (!silent) && (p_cry >= CRYNET_THRESHOLD);

    ESP_LOGI(TAG, "node %u: front end %.1f ms, inference %.1f ms, "
                  "P(no_cry)=%.4f P(cry)=%.4f",
             node_id, (double)(t1 - t0) / 1000.0, (double)(t2 - t1) / 1000.0,
             (double)p_no_cry, (double)p_cry);
    ESP_LOGI(TAG, "node %u: %s", node_id,
             alert ? "ALERT — cry" : (silent ? "silent" : "no cry"));
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

    /* The Wi-Fi driver opens the NVS partition during esp_wifi_init(), so
     * it has to be initialised first. */
    const esp_err_t nv = nvs_flash_init();
    if (nv != ESP_OK && nv != ESP_ERR_NVS_NO_FREE_PAGES) {
        ESP_LOGE(TAG, "nvs_flash_init failed: %s", esp_err_to_name(nv));
        return;
    }

    node_link_t *nl = node_link_create();
    if (nl == NULL) {
        ESP_LOGE(TAG, "the link could not be created");
        return;
    }
    if (!node_link_start(nl)) {
        ESP_LOGE(TAG, "the radio could not be started");
        return;
    }

    ESP_LOGI(TAG, "listening on ESP-NOW; asking for audio at RMS >= %.3f",
             (double)CRYNET_TRIGGER_RMS);

    static node_state_t state[NODE_LINK_MAX_NODES];
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
                    if (burst.complete) {
                        const int64_t t0 = esp_timer_get_time();
                        if (node_link_take_window(nl, st->node_id, s_window,
                                                  CRYNET_N_SAMPLES)) {
                            const uint32_t crc = crynet_proto_crc32(
                                (const uint8_t *)s_window, CRYNET_N_SAMPLES * 2u);
                            const bool match = (st->request_crc != 0) &&
                                               (crc == st->request_crc);
                            ESP_LOGI(TAG, "node %u: %u/%u fragments in %.2f s",
                                     st->node_id, (unsigned)burst.frag_have,
                                     (unsigned)burst.frag_want,
                                     (double)(t0 - st->requested_at_us) / 1000000.0);
                            if (st->request_crc != 0) {
                                ESP_LOGI(TAG, "node %u: window crc32 0x%08X, the node "
                                              "advertised 0x%08X -> %s",
                                         st->node_id, (unsigned)crc,
                                         (unsigned)st->request_crc,
                                         match ? "MATCH" : "MISMATCH");
                            } else {
                                ESP_LOGI(TAG, "node %u: live window, crc32 0x%08X "
                                              "(the node had no frozen window to "
                                              "compare against)",
                                         st->node_id, (unsigned)crc);
                            }
                            analyse(dsp, infer, st->node_id, s_window);
                        }
                        st->requested = false;
                        st->last_log_us = esp_timer_get_time();
                    } else if ((now - st->requested_at_us) > (BURST_TIMEOUT_MS * 1000)) {
                        ESP_LOGW(TAG, "node %u: the burst timed out with %u of %u "
                                      "fragments",
                                 st->node_id, (unsigned)burst.frag_have,
                                 (unsigned)burst.frag_want);
                        node_link_reset_burst(nl, st->node_id);
                        st->requested = false;
                    }
                }
                continue;
            }

            /* Nothing in flight.  Ask for a window when the node's own
             * level says there is something to hear and its window holds a
             * full two seconds. */
            /* Two triggers.  The hub's own: the node's RMS has reached
             * the level above which audio is worth classifying.  And the
             * node's: it froze a window because it crossed its event
             * level, and that window is worth classifying even if the
             * level has fallen again since. */
            const bool loud = (st->rms >= CRYNET_TRIGGER_RMS);
            const bool event = (st->flags & CRYNET_PROTO_FLAG_BURST_READY) != 0;
            if ((loud || event) && st->window_full &&
                (now - st->last_request_us) > (RECOOLDOWN_MS * 1000)) {
                if (node_link_request_window(nl, st->node_id, st->seq)) {
                    st->requested = true;
                    st->requested_at_us = now;
                    st->request_seq = st->seq;
                    st->request_crc = st->crc;
                    st->last_request_us = now;
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
            ESP_LOGI(TAG, "air: %u frames seen raw, %u carrying our magic",
                     (unsigned)node_link_promisc_total(),
                     (unsigned)node_link_promisc_magic());

        }

        vTaskDelay(pdMS_TO_TICKS(50));
    }
}
