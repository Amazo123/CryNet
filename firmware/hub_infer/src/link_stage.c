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

/* How long to wait for a burst before giving up on it.  The node sends
 * 286 fragments with the radio's flow control in the way, so a couple of
 * seconds is normal; fifteen is generous. */
#define BURST_TIMEOUT_MS 15000

/* A cot whose windows keep failing is left alone for a while.  A burst
 * that cannot cross the air will not cross it by being asked harder, and
 * the retries are the loudest thing on the frequency: they starve the
 * cots that *can* be heard.  Measured on the bench, one cot at -70 dBm
 * pushed 34,853 frames trying to deliver windows it never delivered,
 * and the cots beside it lost fragments to the flood.
 *
 * A cot that has failed this many windows in a row is *deaf*: the hub
 * cannot get a window from it, so the model never sees its audio and it
 * can never announce a cry.  The caregiver has to be told, because a
 * cot that cannot be heard is not a cot that is being watched. */
#define BURST_FAIL_LIMIT 3
#define BURST_BACKOFF_MS 60000

/* The pause after a window has been analysed.  The node used to need two
 * seconds to refill its window after an upload -- it threw the live
 * window away because the microphone was not read while the burst was on
 * the air -- so asking again sooner was pointless.  The node now reads
 * the microphone throughout the burst and keeps its window whole, so the
 * wait is only for the next freeze to happen. */
#define RECOOLDOWN_MS 1500

/* How long a confirmed cry keeps being announced.  A cry lasts for
 * seconds; the model's windows are two seconds apart, and a recording
 * played through a speaker has gaps between the cries, so the display
 * must not flicker back to "quiet" the moment one window comes back
 * negative. */
#define CRY_HOLD_MS 8000

/* The shortest a burst may go without a fragment before the hub asks
 * for the missing ones again.  It is a floor, not a fixed threshold:
 * the hub waits eight times the cot's own fragment spacing, which is
 * twenty-four milliseconds for a burst that crosses a good link in
 * three, and four hundred milliseconds for one that manages a fragment
 * every fifty.  The floor is what a good link gets.
 *
 * The threshold used to be fixed, at one and a half seconds, and then
 * at sixty milliseconds, and both were wrong for the same reason: one
 * number cannot describe two links.  A fixed second and a half made a
 * single lost fragment in three hundred cost the system a second and a
 * half of dead time, and a fixed sixty milliseconds called a slow
 * burst dead while it was still crossing the air -- which is what
 * happened at the cot whose link is poor, where the hub spent its
 * resend rounds before the node had finished its first pass. */
#define FRAG_STALL_MS 100

/* How long the burst must have been in flight before a stall may be
 * believed.  The node is asked for the window and then starts sending
 * it; the first fragments take a moment to arrive, and a stall
 * detector that fires before the node has begun would ask for the whole
 * window a second time for nothing.
 *
 * It was two and a half seconds, which is longer than a whole burst
 * takes now, so a stalled burst was never believed at all: the hub sat
 * out the whole fifteen-second timeout instead.  A burst crosses the
 * air in well under a second, so a quarter of a second is plenty to
 * tell "the node has started" from "the node has stopped". */
#define RESEND_MIN_FLIGHT_MS 250

/* How many times the hub may ask for the missing fragments of one
 * burst.  Each round costs a few frames of air and covers the handful
 * the last round still lost.  Three is enough in practice: the first
 * round asks for everything that is missing, the second for the handful
 * that round also lost, and the third for the one or two that the
 * second lost.
 *
 * It is now ten, for the cot whose link is poor.  Its bursts arrive at
 * a fraction of the rate a good link manages, so a round that recovers
 * a third of what is missing needs several rounds to finish, and three
 * rounds was the hub giving up while the node was still sending.  The
 * rounds are bounded by the burst's own timeout, so a round that cannot
 * help does not cost more than the time it takes to notice that
 * nothing arrived. */
#define RESEND_MAX_ROUNDS 10

/* How long the node takes to send one fragment.  The node used to wait
 * ten milliseconds between fragments, so a hundred fragments took a
 * second and a half, and the hub had to allow for that when it decided
 * a burst had stalled: asking again while the node was still sending
 * wastes a round and floods the air.  The fragments now go out as fast
 * as the radio carries them, so the margin is a few milliseconds each. */
#define FRAG_PER_FRAGMENT_MS 4

/* The longest a burst may go without a fragment before the hub calls
 * it stopped, whatever rate the cot is managing.  A burst that is
 * merely slow is caught by the cot's own fragment spacing -- eight
 * times it -- and this is the ceiling on that patience, so that a burst
 * which has really stopped is noticed and asked for again. */
#define FRAG_STALL_MS_MAX 1500

/* The longest the hub waits for the fragments of a resend round to
 * arrive before it asks for them a second time.  A round that is
 * answered slowly is not worth repeating while it is still in the air,
 * but a round that is never answered must not hold the burst open for
 * the whole of its timeout. */
#define FRAG_SETTLE_MS_MAX 3000

/* How many bursts are in the air.  While one is being received the
 * hub's single radio must not also be advertising: every advertisement
 * is a moment when the Wi-Fi receiver is deaf, and the burst loses
 * frames in the air and has to be asked for again.  The Bluetooth stack
 * is told to go quiet for the duration and to start again afterwards.
 *
 * It is also the guard on the pull itself: the hub asks for one
 * node's window at a time.  Three cots bursting together put three
 * times the frames on one channel, the channel saturates, and the
 * bursts starve each other -- measured 2026-11-03 with all three cots
 * loud at once: the nearest cot's burst completed 286/286 in 0.79 s
 * while the next lost up to 46 fragments and the farthest never got
 * past 113 of 286, and every pull churned from window to window
 * without ever finishing one.  One burst at a time crosses the air in
 * under a second, so each cot is still served well inside the few
 * seconds its frozen window is held. */
static int s_bursts_in_flight = 0;

/* How long the hub's own radio has been deaf.  While a burst is on the
 * air the Wi-Fi receiver cannot hear anything at all — not that burst's
 * own fragments, and not any other cot's telemetry — so a node that
 * says nothing for a few seconds may simply have been talking while
 * the hub was shouting.  That time is counted here, and it is not held
 * against the node. */
static int64_t s_busy_total_us = 0;  /* the deaf time so far */
static int64_t s_busy_since_us = 0;  /* when the current stretch began */
static bool    s_radio_deaf = false;

/* The deaf time so far, the stretch in progress included. */
static int64_t radio_deaf_now_us(int64_t now_us)
{
    return s_busy_total_us +
           (s_radio_deaf ? (now_us - s_busy_since_us) : 0);
}

static void burst_started(void)
{
    const int64_t now = esp_timer_get_time();
    if (!s_radio_deaf) {
        s_radio_deaf = true;
        s_busy_since_us = now;
    }
    s_bursts_in_flight++;
    ble_alert_set_radio_busy(true);
}

static void burst_finished(void)
{
    const int64_t now = esp_timer_get_time();
    if (s_bursts_in_flight > 0) {
        s_bursts_in_flight--;
        if (s_bursts_in_flight == 0 && s_radio_deaf) {
            s_busy_total_us += now - s_busy_since_us;
            s_radio_deaf = false;
        }
    }
    ble_alert_set_radio_busy(s_bursts_in_flight > 0);
}

typedef struct {
    bool     heard;
    int64_t  last_heard_us;  /* when telemetry last arrived */
    int64_t  deaf_at_heard_us;  /* and how deaf the hub's radio was then */
    uint8_t  node_id;
    uint16_t seq;
    uint32_t crc;
    uint8_t  flags;
    float    rms;
    bool     window_full;  /* the node says its live window holds 2 s */
    uint8_t  loud_streak;  /* consecutive telemetry readings above the
                            * trigger level */
    /* How many windows in a row have said cry, and the sequence of the
     * last one counted.  The same window is judged more than once when
     * the hub asks for it again, and it always gives the same answer,
     * so it must only count once. */
    uint8_t  cry_run;
    uint16_t cry_seq;
    /* The level the node triggers at.  The node owns the room's noise
     * floor, so it owns the level that follows from it, and the hub
     * triggers on the number the node reports.  A node that reports
     * none is given CRYNET_TRIGGER_RMS instead. */
    float    event_rms;
    float    frozen_rms;   /* the level of the window the node froze */
    float    floor_rms;    /* the node's noise floor */
    uint16_t battery_mv;   /* its battery cell voltage; 0 = no reading */
    uint8_t  battery_band; /* HUB_BAT_*, moved with hysteresis */
    /* The node's own radio counters, from its telemetry: what it handed
     * to the radio, what the radio refused, what actually left it, and
     * how often the radio had no room.  They are what tell a burst that
     * was lost in the air from one the node's radio would not carry. */
    uint32_t frames_sent;
    uint32_t frames_lost;
    uint32_t frames_acked;
    uint32_t radio_full;

    bool     requested;      /* a burst is in flight */
    int64_t  requested_at_us;
    uint16_t request_seq;
    uint32_t request_crc;
    uint32_t request_raw;    /* the hub's frame counter when it asked */
    uint32_t request_frags;  /* the hub's fragment counter when it asked */
    /* How many windows this cot has failed to deliver, one after the
     * other.  A window that never completes can never be judged, so a
     * cot that keeps failing can never announce a cry -- it is deaf,
     * and the caregiver has to be told. */
    uint8_t  burst_failures;
    bool     deaf;           /* the hub cannot get a window from it */
    int64_t  backoff_until_us; /* and it is not asked again before this */
    /* The node's radio counters when it was asked, so that a stalled
     * burst can say what the node did with the fragments it was sent. */
    uint32_t request_sent;
    uint32_t request_lost;
    uint32_t request_acked;
    uint16_t last_have;      /* the fragment count at the last poll */
    uint32_t gap_ewma_ms;    /* how this cot's fragments arrive */
    /* How far apart this cot's fragments arrive, as a running mean.
     * The hub's patience has to follow the cot's own rate: a burst that
     * crosses a good link in three milliseconds a fragment is not a
     * burst that has stopped when it goes quiet for a tenth of a
     * second, and a burst that is crossing a poor link at one fragment
     * a second is not dead when it goes quiet for a moment. */

    int64_t  last_resend_us; /* when the last resend went out */
    uint8_t  resend_rounds;  /* how many resends this burst has had */

    bool     cry_active;      /* the hub is announcing a cry */
    int64_t  cry_until_us;     /* and it does so until this moment */
    int64_t  cry_started_us;   /* when the current cry began */
    uint8_t  last_confidence;  /* the last confirmed confidence, in percent */
    bool     published_cry;    /* what the caregiver's phone was last told */
    /* When this cot first became clearly louder than the named one.
     * The name only moves when that has been true for
     * COT_SWITCH_DWELL_MS, so a pair of microphones that cross over
     * cannot hand the caregiver's wrist back and forth. */
    int64_t  louder_since_us;

    int64_t  last_log_us;      /* when the telemetry was last printed */
    int64_t  last_request_us;   /* when the last window was asked for   */
    uint16_t last_flags;
    uint16_t last_seq;
    uint16_t last_completed_seq;   /* the seq of the last window the hub
                                    * actually received and judged; the
                                    * hub will not ask for the same
                                    * frozen window twice, since a second
                                    * ask only re-serves the snapshot
                                    * the hub already has and keeps the
                                    * node from freezing the next one */
} node_state_t;

/* A cot that has stopped answering is offline, and the panel has to say
 * so promptly: the caregiver unplugs a node to move it and reads the
 * panel for the change.  Radio has no disconnect message — the frames
 * just stop — so silence is the only signal there is.
 *
 * But silence is only evidence if the hub's radio was open to hear it.
 * A burst takes five or six seconds of airtime, and while it is on the
 * air the Wi-Fi receiver hears nothing at all — not that burst's own
 * fragments, and not any other cot's telemetry.  With three cots the
 * hub's radio is busy most of the time, and a plain two-second timeout
 * read those gaps as "the node is gone": the cards flickered offline
 * while every cot was perfectly alive.  So the clock that decides
 * whether a cot has gone runs on the time the radio was *open*, and the
 * hub's own deafness is discounted. */
#define NODE_LIVE_TIMEOUT_US (2LL * 1000000LL)

/* The one cap the discount cannot lift: a cot that has said nothing
 * for this long is gone, whatever the radio was doing.  It is generous
 * because with three cots talking the radio is open for only a part of
 * the time. */
#define NODE_LIVE_MAX_US (20LL * 1000000LL)

/* One entry per node the hub has heard from. */
static node_state_t state[NODE_LINK_MAX_NODES];

/* Whether each cot was on the panel the last time round, so that a
 * change can be announced instead of only shown. */
static bool s_was_live[NODE_LINK_MAX_NODES];

/* The difference between two readings of one of the node's own radio
 * counters.  The counters restart when the node reboots, and subtracting
 * two unsigned numbers across a restart wraps around: the log once said
 * the node had handed over 4 294 963 123 frames.  A counter that has
 * gone backwards says nothing about this burst, so it counts as zero. */
static uint32_t counter_delta(uint32_t now_v, uint32_t base)
{
    return (now_v >= base) ? (now_v - base) : 0u;
}

/* A node is live while its telemetry is recent.  Everything the
 * caregiver sees — the cards, the banner, the NODE pill — reads this,
 * not the latched `heard` flag, or an unplugged cot would stay online
 * forever. */
static bool node_live(const node_state_t *n, int64_t now_us)
{
    if (!n->heard) {
        return false;
    }
    const int64_t age = now_us - n->last_heard_us;
    if (age < NODE_LIVE_TIMEOUT_US) {
        return true;   /* plainly alive */
    }
    if (age > NODE_LIVE_MAX_US) {
        return false;  /* gone, whatever the radio was doing */
    }
    /* Only the silence the hub could have heard through counts. */
    int64_t deaf = radio_deaf_now_us(now_us) - n->deaf_at_heard_us;
    if (deaf > age) {
        deaf = age;
    }
    return (age - deaf) < NODE_LIVE_TIMEOUT_US;
}

/* The battery band a node sits in, moved with hysteresis.  The first
 * reading starts at NORMAL, whatever it is: a cell that boots already
 * deep in LOW or CRITICAL walks one band per reading until it arrives,
 * which takes seconds and cannot frighten anyone.  A node with no
 * reading has no band, and the panel shows nothing for it. */
static uint8_t battery_band_advance(uint8_t band, uint16_t mv)
{
    if (mv == 0u) {
        return HUB_BAT_NONE;
    }
    if (band == HUB_BAT_NONE) {
        band = HUB_BAT_NORMAL;
    }
    if (band == HUB_BAT_NORMAL && mv < 3670u) {
        band = HUB_BAT_LOW;
    } else if (band == HUB_BAT_LOW) {
        if (mv > 3730u) {
            band = HUB_BAT_NORMAL;
        } else if (mv < 3520u) {
            band = HUB_BAT_CRITICAL;
        }
    } else if (band == HUB_BAT_CRITICAL && mv > 3580u) {
        band = HUB_BAT_LOW;
    }
    return band;
}

/* How long the Bluetooth advertising stays off after a cot is heard
 * getting loud.  The window arrives half a second later, and the radio
 * only has to be quiet *before* the burst starts, so this is generous. */
#define PREPARE_QUIET_MS 3000

/* When the radio may go back to advertising. */
static int64_t s_prepare_until_us = 0;

/* The cot the caregiver was last told about, and whether that cot is
 * crying.  The alert that reaches the wrist names *one* cot: the
 * loudest one, the same rule the panel uses.  When two cots hear one
 * cry the hub used to publish an alert for each of them, and the
 * wearable showed "cot 2", then "cot 1", then "cot 2" again for a
 * single physical cry — three buzzes for one baby. */
static uint8_t s_ble_cot = 0;

/* The cots the hub could not get a window from, as a mask.  Bit 0 is
 * cot 1.  The caregiver's phone and the wearable are told when this
 * changes, because a cot that cannot be heard is not being watched. */
static uint8_t s_deaf_mask = 0;
static bool    s_ble_cry = false;

/* The cot a console test alert is standing in for, 0 when there is
 * none.  The console (see console.c) sets it, and it is published as
 * if that cot had heard a cry -- which is how the caregiver's phone
 * and the wearable are checked without making a sound. */
static uint8_t s_test_cot = 0;

/* How much louder another cot has to be before the caregiver is told
 * about it instead of the cot that was already named. */
#define COT_SWITCH_MARGIN 1.5f

/* How long that has to be true before the name moves.
 *
 * Measured on the bench, 2026-11-04 21:16: three cots a hand's width
 * apart on one desk, one cry from a phone, and the name changed hands
 * twelve times in eleven seconds -- the wrist buzzed "cot 1, cot 3,
 * cot 1, cot 3" for a single physical cry.  The test that let it through
 * was on the *live* reading: a hundred milliseconds of a signal that
 * is a cry, and two microphones that close cross over every few
 * hundred milliseconds.  So a challenger has to be clearly louder on
 * the *window* it froze -- a number that holds for the seconds a
 * window lasts -- and has to stay so for this long before the
 * caregiver's wrist is told about a different cot. */
#define COT_SWITCH_DWELL_MS 1500

/* When the hub came up, for the uptime on the display. */
static int64_t s_boot_us = 0;

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
    /* Crest factor: a cry carries impulsive voiced peaks; room hiss is
     * flat (see CRYNET_QUIET_CREST). */
    const float crest = (rms > 0.0f)
                            ? ((float)peak / (rms * 32768.0f))
                            : 0.0f;

    ESP_LOGI(TAG, "node %u: window rms %.6f  mean %d  peak %d  crest %.1f",
             node_id, (double)rms, (int)mean, (int)peak, (double)crest);

    /* A clipped window is not evidence.
     *
     * The INMP441 is a fixed-gain microphone: its own output saturates
     * before the node's 16-bit window does, so a sound close enough to
     * the microphone -- a hand on the desk, a toy, a baby crying right
     * at the mic -- arrives flat-topped and the harmonics the model
     * reads are gone.  Measured on the bench: node 2 clipped at peak
     * 31801 of 32767 on ordinary room sound, and a phone held 10 cm
     * from the microphone clipped the cry it was playing, which cost
     * that window its saturation (0.9805 instead of 0.9961) and made
     * the alert name the wrong cot for 42 seconds.
     *
     * There is no software cure: the microphone's output is already
     * flat when the node sees it.  So the window is refused outright,
     * the operator is told, and the clean cot's window announces the
     * cry instead. */
    const bool clipped = (peak >= CRYNET_CLIP_PEAK);
    if (clipped) {
        ESP_LOGW(TAG, "node %u: the window is CLIPPED (peak %d of 32767) — "
                      "the microphone is too close to the sound; this window "
                      "is not evidence and will not announce a cry",
                 node_id, (int)peak);
    }

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
    const bool says_cry = (!silent) && (p_cry >= CRYNET_THRESHOLD);
    /* No window this quiet may announce a cry at all: the model's
     * verdict on near-silence is noise (see CRYNET_ANNOUNCE_MIN_RMS). */
    const bool audible = rms >= CRYNET_ANNOUNCE_MIN_RMS;
    /* Only a saturated window may announce.
     *
     * The loud window's own rule -- "a window this loud may announce
     * on the model's threshold (0.95) instead of waiting for the
     * saturation" -- was a band-aid for a clipped recording, and it
     * opened the door this rule now closes.
     *
     * The band-aid was for a measured case: a phone held 10 cm from
     * the microphone distorted the cry it played, the window clipped,
     * and the model scored the damaged window 0.9805 instead of
     * 0.9961, so the quiet path refused a real cry and the alert named
     * the wrong cot.  But the model does not only lose certainty on
     * clipped cries: on 2026-11-04, in a room with people talking, it
     * scored an ordinary conversation window 0.9727 (node 3, rms 0.058,
     * crest 3.5).  One step louder, that window was on the loud path's
     * threshold, and the loud path announces on one window alone -- a
     * false alarm, at 0.080 rms, from somebody talking in the next
     * room.  The hub's own boot probe scores 0.9805 on a window of
     * synthetic noise, so no level below the saturation is safe.
     *
     * So a cry is announced when the model saturates and not before.
     * A clipped window does not saturate, and is refused -- which is
     * what the loud path was invented to avoid, but it is refused on
     * the *clean* cot's window instead, where the same cry saturates.
     * The cost is measured: on the corpus, 8 of the 57 episodes that
     * the old rule detected peaked between 0.96 and 0.99 and are now
     * missed; on the bench, three genuine cries out of three scored
     * 0.9961 and all three still announce.  One number moves it back
     * when the model is retrained against loud speech. */
    const bool saturated = (p_cry >= CRYNET_CLEAR_CRY);
    /* A loud window carries enough energy to announce on its own
     * confidence; a quiet one must also have the cry's impulsive
     * shape, not flat hiss.  Both thresholds are the saturation today;
     * the loud one is a separate number so that the old, more sensitive
     * rule is one edit away (see CRYNET_LOUD_ANNOUNCE_P). */
    const bool unmistakable = audible && !clipped &&
        ((rms >= CRYNET_LOUD_ANNOUNCE_RMS)
             ? (p_cry >= CRYNET_LOUD_ANNOUNCE_P)  /* loud: the model's word */
             : (p_cry >= CRYNET_CLEAR_CRY)) &&    /* quiet: it must saturate */
        ((rms >= CRYNET_MAYBE_MIN_RMS) || (crest >= CRYNET_QUIET_CREST));

    /* The announcement rule.
     *
     * The model is not a reliable judge of a window that is very nearly
     * silent: on the real boards, the same quiet room has produced
     * verdicts of 0.0000 and of 0.9766 for windows that differ by
     * nothing a person could hear, and the second of those is a false
     * alarm.  So one window announces a cry on its own only when it is
     * unmistakable — the model's output saturates at 0.9961 for a clear
     * cry, and that window is announced at once if it carries real
     * energy and, when quiet, has the impulsive shape of a cry.
     *
     * A window between the model's threshold (0.95) and the saturation
     * (0.99) is a maybe, and a maybe is never announced on its own:
     * the loud path that used to let one out is gone (see the note
     * above), because a conversation in the next room reaches 0.9727
     * and one step louder would have been announced.  The run of
     * maybes is kept as a counter — it says how close the model came
     * — but it no longer announces anything, because a room that
     * produces a maybe produces the next one too.
     *
     * What is left of the confirmation rule is the level: a near-silent
     * window can neither announce nor be counted, and a real cry
     * saturates and announces alone. */
    bool confirmed = false;
    if (says_cry) {
        if (rms >= CRYNET_MAYBE_MIN_RMS && st->cry_seq != st->request_seq) {
            st->cry_seq = st->request_seq;
            if (st->cry_run < 255u) {
                st->cry_run++;
            }
        }
        /* The run is a counter now, not a licence: it records how many
         * windows in a row have said cry, and the announcement itself
         * is the unmistakable window's own verdict.  The second number
         * is here so that the whole old rule can be brought back with
         * one edit (see CRYNET_CONFIRM_P). */
        confirmed = unmistakable ||
            (st->cry_run >= CRYNET_CRY_RUN && rms >= CRYNET_MAYBE_MIN_RMS &&
             p_cry >= CRYNET_CONFIRM_P);
    } else {
        st->cry_run = 0;
    }

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
                            : (says_cry ? (rms < CRYNET_MAYBE_MIN_RMS
                                               ? "cry (too quiet to announce)"
                                               : "cry (unconfirmed)")
                                        : (silent ? "silent" : "no cry")));
}

/* Whether the hub is announcing a cry for a node.  The display and the
 * BLE server read this, so they show one state and not two. */
bool link_stage_crying(uint8_t node_id)
{
    /* A console test alert shows on the panel as well as on the wrist. */
    if (s_test_cot != 0 && node_id == s_test_cot) {
        return true;
    }
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

/* The console's window into the cots. */
void link_stage_test_alert(uint8_t cot_id)
{
    s_test_cot = cot_id;
    ESP_LOGW(TAG, "the console is holding a TEST ALERT for cot %u",
             (unsigned)cot_id);
}

void link_stage_test_clear(void)
{
    s_test_cot = 0;
    ESP_LOGW(TAG, "the console has taken the test alert back");
}

int link_stage_cots(link_stage_cot_t *out, int max)
{
    int n = 0;
    for (int i = 0; i < NODE_LINK_MAX_NODES && n < max; i++) {
        if (!state[i].heard) {
            continue;
        }
        out[n].node_id = state[i].node_id;
        out[n].rms = state[i].rms;
        out[n].level = state[i].event_rms;
        out[n].frozen_rms = state[i].frozen_rms;
        out[n].crying = link_stage_crying(state[i].node_id);
        out[n].confidence = state[i].last_confidence;
        out[n].window_full = state[i].window_full;
        out[n].deaf = state[i].deaf;
        n++;
    }
    return n;
}

/* The cots the hub cannot get a window from.  See link_stage.h. */
uint8_t link_stage_deaf_mask(void)
{
    uint8_t mask = 0;
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        const node_state_t *st = &state[i];
        if (!st->heard || !st->deaf) {
            continue;
        }
        if (st->node_id >= 1u && st->node_id <= 8u) {
            mask |= (uint8_t)(1u << (st->node_id - 1u));
        }
    }
    return mask;
}

bool link_stage_radio_start(void)
{
    s_boot_us = esp_timer_get_time();
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

    ESP_LOGI(TAG, "listening on ESP-NOW; asking for audio at RMS >= %.3f "
                  "(the level a node reports wins; this is the fallback)",
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
            const int64_t heard_at = esp_timer_get_time();
            st->last_heard_us = heard_at;
            st->deaf_at_heard_us = radio_deaf_now_us(heard_at);

            st->seq = tel.burst_seq;
            st->crc = tel.frozen_crc;
            st->flags = tel.flags;
            st->rms = tel.rms;
            st->window_full = (tel.flags & CRYNET_PROTO_FLAG_WINDOW_FULL) != 0;

            /* The level to trigger at comes from the node.  The node
             * tracks the room's noise floor and turns it into the level
             * it freezes a window at, and the hub is asked to trigger on
             * the same number -- the node is the one that freezes the
             * window, so the level that matters is the one it used.  A
             * node that reports none is an older node, and it gets the
             * fixed level. */
            st->event_rms = (tel.event_rms > 0.0f) ? tel.event_rms
                                                    : CRYNET_TRIGGER_RMS;
            st->frozen_rms = tel.frozen_rms;
            st->floor_rms = tel.floor_rms;

            /* The battery, and the band it sits in.  The band moves on
             * hysteresis -- into a worse band 30 mV below its edge, out
             * of it 30 mV above -- so one radio-load dip cannot flash
             * LOW at the caregiver.  The edges are SYSTEM_WIRING.md 7's:
             * normal above 3.70 V, low 3.55-3.70, critical below 3.55. */
            st->battery_mv = tel.battery_mv;
            st->battery_band = battery_band_advance(st->battery_band,
                                                    tel.battery_mv);

            /* The node's radio counters.  They are kept so that a
             * stalled burst can say whether the node handed the
             * fragments over and lost them in the air, or whether its
             * own radio would not carry them. */
            st->frames_sent = tel.frames_sent;
            st->frames_lost = tel.frames_lost;
            st->frames_acked = tel.frames_acked;
            st->radio_full = tel.radio_full;

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
                burst_finished();
            }

            /* How long the level has been sustained.  A cry lasts for
             * seconds; the microphone's slow DC drift produces one lone
             * reading above the trigger, and a single reading is not
             * worth a 286-fragment burst. */
            if (tel.rms >= st->event_rms) {
                if (st->loud_streak < 255u) {
                    st->loud_streak++;
                }
            } else {
                st->loud_streak = 0;
            }

            const int64_t now = esp_timer_get_time();
            /* The cot is getting loud, so a window is half a second away.
             * The Bluetooth advertising stops now, while there is still
             * time for the radio to go quiet: the ESP32-S3 has one radio
             * for both, and an advertisement that slips through while
             * the burst is on the air deafens the Wi-Fi receiver for a
             * moment.  It was costing exactly one fragment of every
             * burst -- always the same one, always among the first
             * thirty, which is the advertising interval. */
            if (tel.rms >= st->event_rms &&
                (now + PREPARE_QUIET_MS * 1000) > s_prepare_until_us) {
                s_prepare_until_us = now + (PREPARE_QUIET_MS * 1000);
                ble_alert_set_preparing(true);
            }
            const bool changed = (tel.flags != st->last_flags) ||
                                 (tel.burst_seq != st->last_seq);
            if (changed || (now - st->last_log_us) > 1000000) {
                st->last_log_us = now;
                st->last_flags = tel.flags;
                st->last_seq = tel.burst_seq;
                /* Everything the hub's own decision depends on, in one
                 * line: the level the cot triggers at, how many
                 * readings in a row have been above it, and the level of
                 * the window it froze.  When a cry goes unheard, this
                 * line is where the answer is. */
                ESP_LOGI(TAG, "node %u: rms %.4f  seq %u  flags 0x%02X"
                         "  crc 0x%08X  level %.4f  streak %u  win %.4f"
                         "  bat %u mV",
                         tel.node_id, (double)tel.rms,
                         (unsigned)tel.burst_seq, (unsigned)tel.flags,
                         (unsigned)tel.frozen_crc, (double)st->event_rms,
                         (unsigned)st->loud_streak, (double)st->frozen_rms,
                         (unsigned)tel.battery_mv);
            }
        }

        /* ---------------- requests and bursts ---------------- */
        const int64_t now = esp_timer_get_time();

        /* The frozen window the next pull will ask for: the loudest
         * eligible one anywhere in the room, picked below and pulled
         * after the loop so only one burst is ever on the air. */
        node_state_t *pull = NULL;
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
                        /* The rate comes from the receive callback now,
                         * where the arrivals are actually seen; the
                         * loop's own view of the gap was the gap
                         * between two iterations of this loop, and on a
                         * busy hub that is nearly two hundred
                         * milliseconds -- so the hub waited all of that
                         * before it noticed the burst had ended. */
                        if (burst.gap_ewma_ms > 0) {
                            st->gap_ewma_ms = burst.gap_ewma_ms;
                        }
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
                            ESP_LOGI(TAG, "node %u: %u/%u fragments in %.2f s "
                                          "(signal %d dBm, from %d to %d; its "
                                          "telemetry reads %d dBm)",
                                     st->node_id, (unsigned)burst.frag_have,
                                     (unsigned)burst.frag_want,
                                     (double)(t0 - st->requested_at_us) / 1000000.0,
                                     (int)burst.rssi_avg, (int)burst.rssi_min,
                                     (int)burst.rssi_max, (int)burst.tel_rssi);
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
                        st->last_completed_seq = st->request_seq;
                        /* The window arrived whole.  Whatever was wrong
                         * with the link is over, so the cot is heard
                         * again and the caregiver is told so. */
                        if (st->burst_failures != 0 || st->deaf) {
                            ESP_LOGI(TAG, "node %u: the link is working again "
                                          "after %u failed windows",
                                     st->node_id, (unsigned)st->burst_failures);
                        }
                        st->burst_failures = 0;
                        st->deaf = false;
                        st->backoff_until_us = 0;
                        }
                        st->requested = false;
                        st->last_log_us = esp_timer_get_time();
                        burst_finished();
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
                        /* How long this cot's fragments take to arrive,
                         * as its own burst has shown it.  A burst that
                         * has not started yet has no rate of its own, so
                         * the estimate for a good link is used until it
                         * has one. */
                        int64_t per_fragment_ms = FRAG_PER_FRAGMENT_MS;
                        if (st->gap_ewma_ms > 0) {
                            per_fragment_ms = st->gap_ewma_ms;
                            if (per_fragment_ms < 1) {
                                per_fragment_ms = 1;
                            }
                        }
                        /* A burst has stopped when it has been quiet
                         * for sixteen times its own fragment spacing --
                         * a hundred milliseconds for a burst that
                         * crosses a good link in six milliseconds, and
                         * eight hundred for one that manages a fragment
                         * every fifty.  Sixteen, not eight: the node
                         * hands the radio a group of four frames at a
                         * time, so the gap between two arrivals is
                         * small inside a group and a pause between
                         * groups, and eight of the average was close
                         * enough to the pause to call a burst dead
                         * while it was still crossing the air. */
                        int64_t stall_ms = per_fragment_ms * 16;
                        if (stall_ms < FRAG_STALL_MS) {
                            stall_ms = FRAG_STALL_MS;
                        }
                        if (stall_ms > FRAG_STALL_MS_MAX) {
                            stall_ms = FRAG_STALL_MS_MAX;
                        }
                        const int64_t stall_us = stall_ms * 1000;
                        const bool stalled =
                            burst.last_frag_age_ms > (uint32_t)stall_ms;
                        const bool long_enough =
                            (now - st->requested_at_us) > (RESEND_MIN_FLIGHT_MS * 1000);
                        /* A second round waits out the fragments the
                         * last round asked for: they are on the air, and
                         * asking again before they arrive only spends a
                         * round.  How long they need is this cot's own
                         * fragment spacing times the number of them --
                         * a second for a good link, and the few seconds
                         * a poor one needs. */
                        int64_t settle_ms = (int64_t)still_missing *
                                            per_fragment_ms;
                        if (settle_ms > FRAG_SETTLE_MS_MAX) {
                            settle_ms = FRAG_SETTLE_MS_MAX;
                        }
                        if (settle_ms < stall_ms) {
                            settle_ms = stall_ms;
                        }
                        const bool settled =
                            (now - st->last_resend_us) > (settle_ms * 1000);
                        if (stalled && long_enough && settled &&
                            st->resend_rounds < RESEND_MAX_ROUNDS) {
                            /* Which fragments?  One in three hundred is
                             * being lost on the way, and the index says
                             * whether it is a frame that never left
                             * the node, a frame the hub's receiver
                             * dropped, or a frame the hub counted
                             * twice. */
                            uint16_t miss[8];
                            const int n_miss = node_link_burst_missing(
                                nl, st->node_id, miss,
                                (int)(sizeof miss / sizeof miss[0]));
                            if (n_miss > 0) {
                                ESP_LOGW(TAG, "node %u: missing fragments:",
                                         st->node_id);
                                for (int m = 0; m < n_miss; m++) {
                                    ESP_LOGW(TAG, "  %u of %u",
                                             (unsigned)miss[m],
                                             (unsigned)burst.frag_want);
                                }
                            }
                            const int asked = node_link_request_missing(
                                nl, st->node_id, st->request_seq);
                            if (asked > 0) {
                                st->resend_rounds++;
                                st->last_resend_us = now;
                                char pattern[72];
                                node_link_burst_pattern(nl, st->node_id,
                                                        pattern, sizeof pattern);
                                ESP_LOGW(TAG, "node %u: the burst stalled with "
                                              "%u of %u fragments (%u frames "
                                              "arrived); asking for the %u "
                                              "that are missing (signal %d dBm, "
                                              "from %d to %d; its telemetry "
                                              "reads %d dBm)",
                                         st->node_id, (unsigned)burst.frag_have,
                                         (unsigned)burst.frag_want,
                                         (unsigned)burst.frag_seen,
                                         (unsigned)asked,
                                         (int)burst.rssi_avg,
                                         (int)burst.rssi_min,
                                         (int)burst.rssi_max,
                                         (int)burst.tel_rssi);
                                /* What the node's own radio did with the
                                 * fragments it was sent.  A node that
                                 * handed them all over and saw few of
                                 * them come back has lost them in the
                                 * air; a node whose radio refused them
                                 * has a queue that is too small for the
                                 * burst.  The two faults are fixed in
                                 * opposite places, so the log says which
                                 * one it is. */
                                ESP_LOGW(TAG, "node %u: its radio handed over "
                                              "%u frames since the burst began, "
                                              "%u of them left it, %u were "
                                              "refused, %u times it had no room",
                                         st->node_id,
                                         (unsigned)counter_delta(st->frames_sent,
                                                                 st->request_sent),
                                         (unsigned)counter_delta(st->frames_acked,
                                                                 st->request_acked),
                                         (unsigned)counter_delta(st->frames_lost,
                                                                 st->request_lost),
                                         (unsigned)st->radio_full);
                                if (st->frames_sent < st->request_sent) {
                                    ESP_LOGW(TAG, "node %u: its counters went "
                                                  "backwards -- the node has "
                                                  "restarted since the burst "
                                                  "began, so the numbers above "
                                                  "count only what it has "
                                                  "handed over since",
                                             st->node_id);
                                }
                                ESP_LOGW(TAG, "node %u: arrival pattern: %s",
                                         st->node_id, pattern);
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
                        burst_finished();
                        /* The window did not arrive.  Count it, and
                         * after a few in a row stop asking: a burst
                         * that cannot cross the air does not cross it
                         * by being asked harder, and the retries take
                         * the airtime the other cots need. */
                        if (st->burst_failures < 255u) {
                            st->burst_failures++;
                        }
                        if (st->burst_failures >= BURST_FAIL_LIMIT) {
                            if (!st->deaf) {
                                st->deaf = true;
                                ESP_LOGW(TAG, "node %u: DEAF — %u windows in a "
                                              "row did not arrive; it cannot "
                                              "announce a cry until the link "
                                              "improves. Asking it again in %d s.",
                                         st->node_id,
                                         (unsigned)st->burst_failures,
                                         BURST_BACKOFF_MS / 1000);
                            }
                            st->backoff_until_us =
                                now + (BURST_BACKOFF_MS * 1000);
                        }
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
             * lone reading).  The level is the node's own — it tracks the
             * room's noise floor and reports the level that follows from
             * it.  And the node's: it froze a window, which is the two
             * seconds centred on the moment it crossed that level, and
             * the one whose CRC-32 can be checked against what the node
             * advertises.
             *
             * A third, added on 2026-11-04: a window the node has
             * *frozen* is evidence of the moment it froze, not of the
             * moment the hub is looking at.  The stop-capped freeze
             * lands up to two seconds after the peak, and the hub only
             * polls the pull rule every so often, so by the time it
             * looks the live reading has often fallen back into the
             * room's own noise — and the loud window sat there
             * un-pulled.  Measured on the bench, the same minute:
             * node 1 advertised a window of 0.177 rms (a genuine cry)
             * for seven seconds, streak 0 and rms at the room's own
             * level the whole time, and the hub never asked for it.
             * The node also advertises the window's own level beside
             * the live reading — that is the number the model will
             * actually be shown — and a window that loud is worth
             * pulling no matter what the room is doing now. */
            const bool loud = (st->loud_streak >= 2u) ||
                              (st->rms >= 3.0f * st->event_rms) ||
                              (st->frozen_rms >= CRYNET_PULL_CRY_RMS);
            /* Only ask for a window the node has actually frozen.  The
             * node's live window is emptied by an upload and needs two
             * seconds to refill, and a request that arrives in that gap
             * is ignored — the burst times out with nothing received.
             * The node freezes at the same level the hub triggers at, so
             * a loud telemetry always carries this flag. */
            const bool frozen =
                (st->flags & CRYNET_PROTO_FLAG_BURST_READY) != 0;
            /* Only ask for a window worth the radio.  The node tells the
             * hub how loud the window it froze was, before the hub asks
             * for it, and a window quieter than the level the hub would
             * ever announce is one the hub would refuse as "too quiet
             * to announce" anyway.  Pulling it spends five or six
             * seconds of airtime — during which the hub's own receiver
             * is deaf and no other cot can be heard — for nothing.
             *
             * This matters because the cots' triggers sit just above
             * their own noise floor in a quiet room, so the cots freeze
             * a window every few seconds and the hub was pulling every
             * one of them.  With three cots the radio was deaf three
             * quarters of the time, the fetches stalled and were asked
             * for again, and a real cry at the third cot could not be
             * fetched in time to be classified.  The margin below the
             * gate keeps the hub honest about the level the model
             * sees, which is not exactly the node's own count. */
            const bool worth_pulling =
                (st->frozen_rms <= 0.0f) ||
                (st->frozen_rms >= 0.8f * CRYNET_MAYBE_MIN_RMS);
            /* One burst on the air at a time: a pull only starts while
             * no burst is in flight, and when several cots have frozen
             * windows the loudest window is the one asked for first.
             * The loudest is also the most likely to be announced, so
             * spending the airtime on it first is the right order even
             * before fairness. */
            if (loud && frozen && worth_pulling && st->window_full &&
                (st->seq != st->last_completed_seq) &&
                (now - st->last_request_us) > (RECOOLDOWN_MS * 1000) &&
                (now >= st->backoff_until_us) &&
                s_bursts_in_flight == 0 &&
                (pull == NULL || st->frozen_rms > pull->frozen_rms)) {
                pull = st;
            }
        }

        /* The chosen window goes on the air, alone.  Nothing else may
         * share the channel with it: a burst that loses frames to
         * another cot's burst needs resend rounds to recover, and the
         * node refreezes a window every few seconds, so a pull that
         * drags past that abandons a nearly whole window and starts
         * over -- which is exactly the churn three concurrent bursts
         * were stuck in, and why nodes 2 and 3 never finished one. */
        if (pull != NULL) {
            node_state_t *st = pull;
            if (node_link_request_window(nl, st->node_id, st->seq)) {
                st->requested = true;
                burst_started();
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
                    st->request_sent = st->frames_sent;
                    st->request_lost = st->frames_lost;
                    st->request_acked = st->frames_acked;
                }
                st->last_request_us = now;
                st->last_have = 0;

                st->last_resend_us = 0;
                st->resend_rounds = 0;
                /* The node drops its live window when it serves a
                 * request and refills it over the next two seconds,
                 * so until it says the window is whole again there is
                 * nothing to ask for. */
                st->window_full = false;
                ESP_LOGI(TAG, "node %u: asking for the window (seq %u, "
                              "rms %.4f, level %.4f, win %.4f)",
                         st->node_id, (unsigned)st->seq, (double)st->rms,
                         (double)st->event_rms, (double)st->frozen_rms);
            } else {
                ESP_LOGW(TAG, "node %u: the request could not be sent",
                         st->node_id);
            }
        }

        /* ---------------- the caregiver's phone ---------------- */
        /* The advertising goes back on once the burst has come and
         * gone: the radio has to be quiet before a burst, not during
         * the whole quiet period afterwards. */
        if (s_prepare_until_us != 0 && now > s_prepare_until_us) {
            s_prepare_until_us = 0;
            ble_alert_set_preparing(false);
        }
        /* The per-cot state first: which cots are crying. */
        bool any_state_changed = false;
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            node_state_t *st = &state[i];
            if (!st->heard) {
                continue;
            }
            const bool crying = link_stage_crying(st->node_id);
            if (crying != st->published_cry) {
                st->published_cry = crying;
                any_state_changed = true;
            }
        }

        /* The alert names *one* cot, and the same cot for the whole
         * episode.  Publishing an alert per cot meant that two cots
         * hearing one cry produced two buzzes and the wearable showed
         * "cot 2", then "cot 1", then "cot 2" again for a single
         * physical cry.  Naming the loudest cot is not enough on its
         * own: two cots in one room both hear the cry, and their
         * levels cross over from window to window, so "the loudest"
         * changed hands every few hundred milliseconds.  The cot that
         * was named keeps the alert until it stops crying, or until
         * another cot is clearly louder. */
        node_state_t *loudest = NULL;
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            node_state_t *st = &state[i];
            if (!st->heard || !st->published_cry) {
                continue;
            }
            if (loudest == NULL || st->rms > loudest->rms) {
                loudest = st;
            }
        }
        if (s_ble_cry && loudest != NULL && loudest->node_id != s_ble_cot) {
            /* The named cot is still crying: it keeps the alert unless
             * the other one is clearly louder -- and "clearly louder"
             * is now judged on the *window* the challenger froze, and
             * has to hold for COT_SWITCH_DWELL_MS before the name
             * moves.  See the note on COT_SWITCH_DWELL_MS: the live
             * reading crosses over between two microphones a hand's
             * width apart every few hundred milliseconds, and the
             * caregiver's wrist was told twelve times about one cry.
             *
             * The named cot keeps the alert right up to that point, so
             * one cry is one buzz. */
            node_state_t *incumbent = NULL;
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                node_state_t *st = &state[i];
                if (st->heard && st->node_id == s_ble_cot &&
                    st->published_cry) {
                    incumbent = st;
                    break;
                }
            }
            if (incumbent != NULL) {
                const bool clearly_louder =
                    loudest->frozen_rms >
                        incumbent->frozen_rms * COT_SWITCH_MARGIN;
                if (clearly_louder) {
                    if (loudest->louder_since_us == 0) {
                        loudest->louder_since_us = now;
                    }
                    if ((now - loudest->louder_since_us) <
                            (COT_SWITCH_DWELL_MS * 1000)) {
                        loudest = incumbent;
                    }
                    /* otherwise the challenger takes the alert over */
                } else {
                    loudest->louder_since_us = 0;
                    loudest = incumbent;
                }
            }
        }
        /* A test alert from the console stands in for the cots: it is
         * what the bench uses to check the caregiver's phone and the
         * wearable without making a sound, and it is held until the
         * console says otherwise. */
        if (s_test_cot != 0) {
            if (!s_ble_cry || s_ble_cot != s_test_cot) {
                ble_alert_publish(s_test_cot, true, 100);
                s_ble_cot = s_test_cot;
                s_ble_cry = true;
                any_state_changed = true;
            }
        } else if (loudest != NULL) {
            if (!s_ble_cry || loudest->node_id != s_ble_cot) {
                ble_alert_publish(loudest->node_id, true,
                                  loudest->last_confidence);
                s_ble_cot = loudest->node_id;
                s_ble_cry = true;
                any_state_changed = true;
                /* The name has moved: nobody is "clearly louder" now,
                 * so the dwell starts again from scratch if it is ever
                 * challenged. */
                for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                    state[i].louder_since_us = 0;
                }
            }
        } else if (s_ble_cry) {
            /* The cry is over: the cot that was named is told so. */
            ble_alert_publish(s_ble_cot, false, 0);
            s_ble_cry = false;
            s_ble_cot = 0;
            any_state_changed = true;
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                state[i].louder_since_us = 0;
            }
        }

        /* A cot that has gone deaf is announced, and the announcement is
         * withdrawn when the link comes back.  A cot the hub cannot hear
         * is not a cot that is being watched, and silence from it would
         * read as "all quiet" on the wrist. */
        {
            const uint8_t deaf_now = link_stage_deaf_mask();
            if (deaf_now != s_deaf_mask) {
                const uint8_t deaf_new = (uint8_t)(deaf_now & ~s_deaf_mask);
                const uint8_t deaf_gone = (uint8_t)(s_deaf_mask & ~deaf_now);
                s_deaf_mask = deaf_now;
                any_state_changed = true;
                for (int j = 0; j < NODE_LINK_MAX_NODES; j++) {
                    if (!state[j].heard || state[j].node_id < 1u ||
                        state[j].node_id > 8u) {
                        continue;
                    }
                    const uint8_t bit =
                        (uint8_t)(1u << (state[j].node_id - 1u));
                    if (deaf_new & bit) {
                        ble_alert_publish_deaf(state[j].node_id);
                    } else if (deaf_gone & bit) {
                        /* The link is back: the cot is watched again. */
                        ble_alert_publish(state[j].node_id, false, 0);
                    }
                }
            }
        }

        /* The state characteristic carries the whole system. */
        if (any_state_changed) {
            ble_state_packet_t sp;
            memset(&sp, 0, sizeof sp);
            sp.deaf_mask = s_deaf_mask;
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

        /* While no node is live, probe.  The probe asks for a single
         * fragment, which is enough to prove that the two boards can
         * talk and which way the traffic is failing.  A hub whose cots
         * were all unplugged goes back to probing once they time out,
         * instead of waiting forever beside a dark nursery. */
        const int64_t probe_now = esp_timer_get_time();
        bool any_heard = false;
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            if (node_live(&state[i], probe_now)) {
                any_heard = true;
            }
        }
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
        const int64_t snap_now = esp_timer_get_time();
        node_state_t *show = NULL;
        /* The cot the caregiver was told about keeps the display as
         * well: two cots in one room cross over from window to
         * window, and a card that changes every few hundred
         * milliseconds is unreadable.  While an alert is up the
         * display names *the same cot the wrist does* -- a panel that
         * says "cot 3" while the bracelet says "cot 1" is worse than
         * no panel at all. */
        if (s_ble_cry) {
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (state[i].node_id == s_ble_cot &&
                    node_live(&state[i], snap_now) &&
                    link_stage_crying(state[i].node_id)) {
                    show = &state[i];
                    break;
                }
            }
        }
        if (show == NULL) {
            /* No alert is up: the loudest crying cot, or the loudest
             * cot the hub has heard from. */
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (node_live(&state[i], snap_now) &&
                    link_stage_crying(state[i].node_id)) {
                    if (show == NULL || state[i].rms > show->rms) {
                        show = &state[i];
                    }
                }
            }
        }
        if (show == NULL) {
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (node_live(&state[i], snap_now) &&
                    (show == NULL || state[i].rms > show->rms)) {
                    show = &state[i];
                }
            }
        }
        hub_display_state_t ds;
        memset(&ds, 0, sizeof ds);
        ds.node_count = HUB_DISPLAY_MAX_NODES;
        ds.ble_ready = ble_alert_is_running();
        ds.ble_clients = (uint8_t)ble_alert_clients();
        ds.uptime_s = (uint32_t)((snap_now - s_boot_us) / 1000000);
        if (show != NULL) {
            ds.linked = true;
            ds.crying = link_stage_crying(show->node_id);
            ds.cot_id = show->node_id;
            ds.confidence = show->last_confidence;
            ds.level = show->rms;
        }
        /* Every cot the hub has heard from, so the dashboard can show
         * them one by one.  The slot is the cot number, so the cards
         * are always in the same order. */
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            if (!state[i].heard) {
                continue;
            }
            const int slot = (int)state[i].node_id - 1;
            if (slot < 0 || slot >= HUB_DISPLAY_MAX_NODES) {
                continue;
            }
            ds.nodes[slot].id = state[i].node_id;
            /* A cot that has gone quiet keeps its card — the caregiver
             * needs somewhere to look — but it reads OFFLINE, and it
             * stops driving the banner and the NODE pill. */
            const bool live = node_live(&state[i], snap_now);
            ds.nodes[slot].online = live;
            ds.nodes[slot].crying = live && link_stage_crying(state[i].node_id);
            ds.nodes[slot].level = state[i].rms;
            ds.nodes[slot].confidence = state[i].last_confidence;
            /* The battery only while the cot is answering: a card that
             * has gone quiet must not go on quoting a level nothing is
             * measuring -- and a cot that died of a flat cell must not
             * be shown a healthy one. */
            ds.nodes[slot].battery_mv = live ? state[i].battery_mv : 0u;
            ds.nodes[slot].battery_band = live ? state[i].battery_band
                                               : HUB_BAT_NONE;
            /* A cot whose windows never arrive is online but deaf: it
             * is transmitting, and the hub still cannot get its audio,
             * so it cannot announce a cry. */
            ds.nodes[slot].deaf = state[i].deaf;
            /* Say it when a cot appears or disappears, so the panel's
             * offline cards can be counted rather than squinted at. */
            if (live != s_was_live[i]) {
                s_was_live[i] = live;
                ESP_LOGI(TAG, "node %u is %s", state[i].node_id,
                         live ? "online" : "offline");
            }
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

        /* The loop polls the radio, asks for windows and shows the
         * panel.  At fifty milliseconds a decision could sit waiting for
         * the next turn of the loop -- a fifth of the time a cry now
         * takes to be answered, and there is nothing in the loop heavy
         * enough to want that much of the CPU. */
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}
