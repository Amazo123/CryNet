/*
 * CryNet — the hub's half of the node link.  See node_link.h.
 */

#include "node_link.h"

#include <stdlib.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "esp_event.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_now.h"
#include "esp_wifi.h"
#include "esp_mac.h"

static const char *TAG = "node_link";

/* The radio channel the nodes use.  Both sides set it explicitly, because
 * ESP-NOW does not roam: a node on channel 1 and a hub on channel 6 hear
 * nothing of each other. */
#define NODE_LINK_CHANNEL 1

#define NODE_LINK_MAX_FRAME 260

typedef struct {
    bool     used;
    uint8_t  id;
    uint8_t  src_mac[6];

    /* telemetry */
    uint16_t burst_seq;
    float    rms;
    uint16_t window_ms;
    uint8_t  flags;
    uint32_t frozen_crc;
    uint32_t last_seen_ms;
    bool     telemetry_new;

    /* burst reassembly */
    bool     in_burst;
    uint16_t frag_seq;
    uint16_t frag_want;
    uint16_t frag_have;
    uint32_t bad_payloads;
    uint8_t  bitmap[(CRYNET_PROTO_FRAG_COUNT + 7u) / 8u];

    int16_t *window;
} node_slot_t;

struct node_link {
    bool           up;
    uint32_t       raw_shown;   /* how many raw frames have been printed */
    node_slot_t    slots[NODE_LINK_MAX_NODES];
    SemaphoreHandle_t lock;
    node_link_stats_t stats;
};

/* ESP-NOW has one global receive callback and no user-data pointer, so the
 * hub keeps a single instance and the callback finds it here.  There is one
 * hub. */
static node_link_t *s_instance = NULL;

static void link_lock(const node_link_t *nl)
{
    if (nl->lock != NULL) {
        xSemaphoreTake(nl->lock, portMAX_DELAY);
    }
}

static void link_unlock(const node_link_t *nl)
{
    if (nl->lock != NULL) {
        xSemaphoreGive(nl->lock);
    }
}

/* A millisecond clock.  The link needs nothing finer: telemetry arrives
 * every 100 ms and a burst is measured in seconds.  The FreeRTOS tick is
 * used rather than esp_timer so that this component does not have to
 * depend on it. */
static uint32_t now_ms(void)
{
    return (uint32_t)xTaskGetTickCount() * portTICK_PERIOD_MS;
}

/* The addresses of the peers the hub has heard from.  Each node's address
 * is learned from the frames it sends and then added to the ESP-NOW peer
 * list, so the radio's receive filter includes it.
 *
 * The addition is *deferred* to the application task: the receive callback
 * runs in the Wi-Fi task, and esp_now_add_peer() waits for the Wi-Fi task
 * to service it.  Called from inside that callback it blocks the very task
 * it is waiting for, and the radio stops delivering frames until something
 * else nudges it loose — the hub was receiving one frame in sixty. */
#define KNOWN_PEERS NODE_LINK_MAX_NODES
static uint8_t g_known[KNOWN_PEERS][6];
static int     g_known_count = 0;
static bool    g_pending[KNOWN_PEERS];

static void ensure_peer(const uint8_t *mac)
{
    for (int slot = 0; slot < KNOWN_PEERS; slot++) {
        if (g_known[slot][0] == mac[0] && g_known[slot][1] == mac[1] &&
            g_known[slot][2] == mac[2] && g_known[slot][3] == mac[3] &&
            g_known[slot][4] == mac[4] && g_known[slot][5] == mac[5]) {
            return;
        }
    }
    for (int slot = 0; slot < KNOWN_PEERS; slot++) {
        if (g_known[slot][0] != 0) {
            continue;   /* this slot is taken */
        }
        memcpy(g_known[slot], mac, 6);
        g_pending[slot] = true;
        return;
    }
}

/*
 * Add any peer whose address was learned since the last call.  Called from
 * the application task, where esp_now_add_peer() is safe.
 */
void node_link_service_peers(node_link_t *nl)
{
    if (nl == NULL) {
        return;
    }
    for (int slot = 0; slot < KNOWN_PEERS; slot++) {
        if (!g_pending[slot]) {
            continue;
        }
        esp_now_peer_info_t peer = {};
        memcpy(peer.peer_addr, g_known[slot], 6);
        peer.channel = NODE_LINK_CHANNEL;
        peer.ifidx = WIFI_IF_STA;
        peer.encrypt = false;
        if (esp_now_add_peer(&peer) == ESP_OK) {
            g_pending[slot] = false;
            ESP_LOGI(TAG, "peer %02X:%02X:%02X:%02X:%02X:%02X added",
                     g_known[slot][0], g_known[slot][1], g_known[slot][2],
                     g_known[slot][3], g_known[slot][4], g_known[slot][5]);
        }
    }
}

/* Diagnostic: promiscuous mode hands up every frame on the channel.  The
 * buffer is opaque, so the node's own magic (C3 7E) is looked for in it.
 * If the counter moves, the node's transmissions are on the air and the
 * ESP-NOW layer is losing them; if it does not, the node is not
 * transmitting them. */
static uint32_t s_bad_dbg = 0;   /* the first few rejects are printed, then quiet */
static volatile uint32_t s_promisc_total = 0;
static volatile uint32_t s_promisc_magic = 0;

static void promisc_rx(void *buf, wifi_promiscuous_pkt_type_t type)
{
    (void)type;
    s_promisc_total++;
    const uint8_t *p = (const uint8_t *)buf;
    for (int i = 0; i + 1 < 400; i++) {
        if (p[i] == 0xC3 && p[i + 1] == 0x7E) {
            s_promisc_magic++;
            return;
        }
    }
}

/* Diagnostic: move the radio to another channel and count what is there. */
void node_link_sweep_channel(uint8_t ch)
{
    esp_wifi_set_channel(ch, WIFI_SECOND_CHAN_NONE);
}

uint32_t node_link_promisc_total(void) { return s_promisc_total; }
uint32_t node_link_promisc_magic(void) { return s_promisc_magic; }

/* ------------------------------------------------------------- reception -- */

static void handle_telemetry(node_link_t *nl, uint8_t node_id, uint16_t seq,
                             const uint8_t *payload)
{
    crynet_proto_telemetry_t tel;
    if (!crynet_proto_decode_telemetry(payload, CRYNET_PROTO_TELEMETRY_BYTES, &tel)) {
        return;
    }

    node_slot_t *slot = NULL;
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        if (nl->slots[i].used && nl->slots[i].id == node_id) {
            slot = &nl->slots[i];
            break;
        }
    }
    if (slot == NULL) {
        for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
            if (!nl->slots[i].used) {
                slot = &nl->slots[i];
                /* The window buffer was allocated for every slot at create;
                 * a plain memset here zeroed that pointer, and every
                 * fragment afterwards hit "window == NULL" and was counted
                 * bad — no burst ever reassembled. */
                void *win = slot->window;
                memset(slot, 0, sizeof(*slot));
                slot->window = win;
                slot->used = true;
                slot->id = node_id;
                ESP_LOGI(TAG, "node %u heard for the first time", node_id);
                break;
            }
        }
    }
    if (slot == NULL) {
        ESP_LOGW(TAG, "node %u ignored: the hub tracks %d nodes",
                 node_id, NODE_LINK_MAX_NODES);
        return;
    }

    slot->burst_seq = seq;
    slot->rms = tel.rms;
    slot->window_ms = tel.window_ms;
    slot->flags = tel.flags;
    slot->frozen_crc = tel.frozen_crc;
    slot->last_seen_ms = now_ms();
    slot->telemetry_new = true;
}

static void handle_fragment(node_link_t *nl, uint8_t node_id, uint16_t seq,
                             uint16_t frag, uint16_t frag_count,
                             const uint8_t *payload, int payload_len)
{
    node_slot_t *slot = NULL;
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        if (nl->slots[i].used && nl->slots[i].id == node_id) {
            slot = &nl->slots[i];
            break;
        }
    }
    if (slot == NULL) {
        return;  /* fragments without telemetry are not ours */
    }

    if (frag_count != CRYNET_PROTO_FRAG_COUNT || frag >= CRYNET_PROTO_FRAG_COUNT) {
        if (s_bad_dbg < 8u) {
            s_bad_dbg++;
            ESP_LOGI(TAG, "frag reject: count %u frag %u (want %u)",
                     frag_count, frag, (unsigned)CRYNET_PROTO_FRAG_COUNT);
        }
        nl->stats.frames_bad++;
        return;
    }
    if (payload_len <= 0 || payload == NULL) {
        if (s_bad_dbg < 8u) {
            s_bad_dbg++;
            ESP_LOGI(TAG, "frag reject: payload_len %d", payload_len);
        }
        nl->stats.frames_bad++;
        return;
    }
    if (slot->window == NULL) {
        /* A slot without its window buffer: every fragment for it would
         * be dropped silently, which is exactly what happened once. */
        if (s_bad_dbg < 8u) {
            s_bad_dbg++;
            ESP_LOGE(TAG, "frag reject: node %u has no window buffer", node_id);
        }
        nl->stats.frames_bad++;
        return;
    }

    /* A new burst sequence starts a new reassembly. */
    if (!slot->in_burst || slot->frag_seq != seq) {
        memset(slot->bitmap, 0, sizeof(slot->bitmap));
        slot->in_burst = true;
        slot->frag_seq = seq;
        slot->frag_want = frag_count;
        slot->frag_have = 0;
    }

    const uint8_t bit = (uint8_t)(frag & 7u);
    const uint8_t mask = (uint8_t)(1u << bit);
    uint8_t *byte = &slot->bitmap[frag >> 3];
    if (*byte & mask) {
        return;  /* a duplicate; the first copy was already stored */
    }
    *byte |= mask;

    /* The payload is the window's raw little-endian int16 bytes. */
    const size_t offset = (size_t)frag * CRYNET_PROTO_FRAG_PAYLOAD;
    const size_t room = CRYNET_PROTO_WINDOW_BYTES - offset;
    const size_t copy = ((size_t)payload_len < room) ? (size_t)payload_len : room;
    memcpy((uint8_t *)slot->window + offset, payload, copy);
    slot->frag_have++;

    ESP_LOGD(TAG, "node %u fragment %u/%u (seq %u)", node_id, frag + 1u,
             frag_count, seq);
}

static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len)
{
    node_link_t *nl = s_instance;
    if (nl == NULL || data == NULL || len <= 0) {
        return;
    }

    uint8_t type = 0, node_id = 0;
    uint16_t seq = 0, frag = 0, frag_count = 0;
    const uint8_t *payload = NULL;

    nl->stats.raw_frames++;
    if (nl->raw_shown < 5u) {
        nl->raw_shown++;
        ESP_LOGI(TAG, "raw frame %u bytes from %02X:%02X:%02X:%02X:%02X:%02X "
                      "(first bytes %02X %02X %02X %02X)",
                 (unsigned)len, info->src_addr[0], info->src_addr[1],
                 info->src_addr[2], info->src_addr[3], info->src_addr[4],
                 info->src_addr[5], data[0], len > 1 ? data[1] : 0,
                 len > 2 ? data[2] : 0, len > 3 ? data[3] : 0);
    }

    const int parsed = crynet_proto_parse(data, (size_t)len, &type, &node_id,
                                          &seq, &frag, &frag_count, &payload);
    if (parsed == CRYNET_PROTO_BAD_FRAME) {
        /* Print the first few rejects with the fields the parse checked,
         * so the failing check can be seen from the log. */
        if (s_bad_dbg < 5u && data[0] == CRYNET_PROTO_MAGIC0) {
            s_bad_dbg++;
            const uint16_t plen = (uint16_t)(data[10] | ((uint16_t)data[11] << 8));
            const uint16_t show = (plen > CRYNET_PROTO_MAX_PAYLOAD)
                                      ? CRYNET_PROTO_MAX_PAYLOAD : plen;
            uint16_t fcrc = 0;
            if (len >= (int)(CRYNET_PROTO_HEADER_BYTES + show + 2u)) {
                fcrc = (uint16_t)(data[CRYNET_PROTO_HEADER_BYTES + show] |
                                  ((uint16_t)data[CRYNET_PROTO_HEADER_BYTES + show + 1] << 8));
            }
            ESP_LOGI(TAG, "BAD frame: len %u type %u plen %u fcrc %04X computed %04X",
                     (unsigned)len, data[2], plen, fcrc,
                     (unsigned)crynet_proto_crc16(data,
                          CRYNET_PROTO_HEADER_BYTES + show));
        }
        nl->stats.frames_bad++;
        return;
    }
    if (parsed == CRYNET_PROTO_BAD_PAYLOAD) {
        nl->stats.payloads_bad++;
        return;
    }
    if (type == CRYNET_PROTO_TYPE_REQUEST) {
        return;  /* a request is the other direction; ignore it */
    }

    nl->stats.frames_ok++;

    /* The node's address is learned from the frames it sends, and added
     * to the peer list.  The Wi-Fi driver's receive filter is built from
     * that list, and a node whose address is not in it is not heard. */
    if (info != NULL) {
        ensure_peer(info->src_addr);
    }

    link_lock(nl);
    if (type == CRYNET_PROTO_TYPE_TELEMETRY) {
        handle_telemetry(nl, node_id, seq, payload);
        if (info != NULL) {
            for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
                if (nl->slots[i].used && nl->slots[i].id == node_id) {
                    memcpy(nl->slots[i].src_mac, info->src_addr, 6);
                    break;
                }
            }
        }
    } else if (type == CRYNET_PROTO_TYPE_FRAGMENT) {
        handle_fragment(nl, node_id, seq, frag, frag_count, payload, parsed);
    }
    link_unlock(nl);
}

/* ------------------------------------------------------------ lifecycle -- */

node_link_t *node_link_create(void)
{
    node_link_t *nl = calloc(1, sizeof(node_link_t));
    if (nl == NULL) {
        return NULL;
    }

    nl->lock = xSemaphoreCreateMutex();
    if (nl->lock == NULL) {
        free(nl);
        return NULL;
    }

    /* The window buffers are the bulk of the memory: 64 KB per node.  They
     * live in PSRAM, which the S3 has in 8 MB, and they are only touched
     * when a burst is being assembled. */
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        nl->slots[i].window = heap_caps_malloc(CRYNET_PROTO_WINDOW_BYTES,
                                               MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
        if (nl->slots[i].window == NULL) {
            nl->slots[i].window = heap_caps_malloc(CRYNET_PROTO_WINDOW_BYTES,
                                                   MALLOC_CAP_8BIT);
        }
        if (nl->slots[i].window == NULL) {
            ESP_LOGE(TAG, "no memory for a %u byte window buffer",
                     (unsigned)CRYNET_PROTO_WINDOW_BYTES);
            node_link_destroy(nl);
            return NULL;
        }
    }

    s_instance = nl;
    return nl;
}

void node_link_destroy(node_link_t *nl)
{
    if (nl == NULL) {
        return;
    }
    if (s_instance == nl) {
        s_instance = NULL;
    }
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        free(nl->slots[i].window);
    }
    if (nl->lock != NULL) {
        vSemaphoreDelete(nl->lock);
    }
    free(nl);
}

bool node_link_start(node_link_t *nl)
{
    if (nl == NULL) {
        return false;
    }

    if (esp_netif_init() != ESP_OK) {
        ESP_LOGE(TAG, "esp_netif_init failed");
        return false;
    }
    const esp_err_t ev = esp_event_loop_create_default();
    if (ev != ESP_OK && ev != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "event loop failed");
        return false;
    }

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&cfg) != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_init failed");
        return false;
    }
    if (esp_wifi_set_storage(WIFI_STORAGE_RAM) != ESP_OK) {
        ESP_LOGE(TAG, "wifi storage failed");
        return false;
    }
    if (esp_wifi_set_mode(WIFI_MODE_STA) != ESP_OK) {
        ESP_LOGE(TAG, "wifi mode failed");
        return false;
    }

    if (esp_wifi_start() != ESP_OK) {
        ESP_LOGE(TAG, "esp_wifi_start failed");
        return false;
    }

    /* Power save has to be turned off *after* the driver is started, and
     * this is not a detail: with the radio left to sleep between beacons
     * the hub received one node frame in six, because it was asleep for
     * the other fifty-nine out of every sixty.  The node's sketch calls
     * WiFi.setSleep(false) after WiFi.mode() for the same reason.  A
     * burst of 286 fragments would be lost almost entirely. */
    esp_wifi_set_ps(WIFI_PS_NONE);
    if (esp_wifi_set_channel(NODE_LINK_CHANNEL, WIFI_SECOND_CHAN_NONE) != ESP_OK) {
        ESP_LOGE(TAG, "channel %d failed", NODE_LINK_CHANNEL);
        return false;
    }

    if (esp_now_init() != ESP_OK) {
        ESP_LOGE(TAG, "esp_now_init failed");
        return false;
    }

    esp_now_peer_info_t peer = {};
    static const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    memcpy(peer.peer_addr, bcast, 6);
    /* The channel is set explicitly rather than left at 0.  A peer with
     * channel 0 is on "the current channel", but the driver's receive
     * filter is built from the peer list, and an explicit channel is
     * what it needs to listen on it. */
    peer.channel = NODE_LINK_CHANNEL;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    if (esp_now_add_peer(&peer) != ESP_OK) {
        ESP_LOGE(TAG, "esp_now_add_peer failed");
        return false;
    }

    /* The nodes' addresses are configured here rather than discovered.
     *
     * The Wi-Fi driver's receive filter is built from the peer list, and a
     * frame from an address that is not in it is not delivered to the
     * ESP-NOW callback.  A node cannot be discovered by the frames it
     * sends, because those frames are exactly the ones being filtered —
     * the hub was hearing one frame in sixty from a node whose address it
     * had never been told.  So the addresses go in the table below and
     * every node is a peer from the first frame.
     *
     * The addresses are printed by the node's "status" command. */
    static const uint8_t node_addresses[][6] = {
        {0xE0, 0x72, 0xA1, 0x72, 0xAC, 0x14},   /* node 1 */
    };
    for (size_t i = 0; i < sizeof(node_addresses) / 6; i++) {
        esp_now_peer_info_t np = {};
        memcpy(np.peer_addr, node_addresses[i], 6);
        np.channel = NODE_LINK_CHANNEL;
        np.ifidx = WIFI_IF_STA;
        np.encrypt = false;
        if (esp_now_add_peer(&np) == ESP_OK) {
            /* Remember it, so the address is not added a second time when
             * the first frame from it arrives. */
            if (g_known_count < KNOWN_PEERS) {
                memcpy(g_known[g_known_count], node_addresses[i], 6);
                g_known_count++;
            }
            ESP_LOGI(TAG, "node %u peer %02X:%02X:%02X:%02X:%02X:%02X added",
                     (unsigned)(i + 1), node_addresses[i][0], node_addresses[i][1],
                     node_addresses[i][2], node_addresses[i][3],
                     node_addresses[i][4], node_addresses[i][5]);
        } else {
            ESP_LOGE(TAG, "node %u peer could not be added", (unsigned)(i + 1));
        }
    }


    if (esp_now_register_recv_cb(on_recv) != ESP_OK) {
        ESP_LOGE(TAG, "esp_now_register_recv_cb failed");
        return false;
    }

    if (esp_wifi_set_promiscuous(true) == ESP_OK) {
        esp_wifi_set_promiscuous_rx_cb(promisc_rx);
        ESP_LOGW(TAG, "promiscuous mode is on (diagnostic)");
    }

    uint32_t version = 0;
    if (esp_now_get_version(&version) == ESP_OK) {
        ESP_LOGI(TAG, "ESP-NOW protocol version %u", (unsigned)version);
    }

    uint8_t mac[6] = {0};
    if (esp_read_mac(mac, ESP_MAC_WIFI_STA) == ESP_OK) {
        ESP_LOGI(TAG, "the hub's STA address is %02X:%02X:%02X:%02X:%02X:%02X",
                 mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
    }

    uint8_t channel = 0;
    wifi_second_chan_t second = WIFI_SECOND_CHAN_NONE;
    if (esp_wifi_get_channel(&channel, &second) == ESP_OK) {
        ESP_LOGI(TAG, "the radio is on channel %u", (unsigned)channel);
    }

    nl->up = true;
    ESP_LOGI(TAG, "ESP-NOW ready on channel %d", NODE_LINK_CHANNEL);
    return true;
}

bool node_link_ready(const node_link_t *nl)
{
    return nl != NULL && nl->up;
}

/* ------------------------------------------------------------ telemetry -- */

bool node_link_poll_telemetry(node_link_t *nl, node_link_telemetry_t *out)
{
    if (nl == NULL) {
        return false;
    }

    bool found = false;
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        node_slot_t *slot = &nl->slots[i];
        if (!slot->used || !slot->telemetry_new) {
            continue;
        }
        slot->telemetry_new = false;
        out->node_id = slot->id;
        out->burst_seq = slot->burst_seq;
        out->rms = slot->rms;
        out->window_ms = slot->window_ms;
        out->flags = slot->flags;
        out->frozen_crc = slot->frozen_crc;
        out->age_ms = now_ms() - slot->last_seen_ms;
        found = true;
        break;
    }
    link_unlock(nl);
    return found;
}

bool node_link_last_telemetry(const node_link_t *nl, uint8_t node_id,
                              node_link_telemetry_t *out)
{
    if (nl == NULL) {
        return false;
    }

    bool found = false;
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        const node_slot_t *slot = &nl->slots[i];
        if (!slot->used || slot->id != node_id) {
            continue;
        }
        out->node_id = slot->id;
        out->burst_seq = slot->burst_seq;
        out->rms = slot->rms;
        out->window_ms = slot->window_ms;
        out->flags = slot->flags;
        out->frozen_crc = slot->frozen_crc;
        out->age_ms = now_ms() - slot->last_seen_ms;
        found = true;
        break;
    }
    link_unlock(nl);
    return found;
}

/* --------------------------------------------------------------- bursts -- */

bool node_link_request_window(node_link_t *nl, uint8_t node_id, uint16_t burst_seq)
{
    if (nl == NULL || !nl->up) {
        return false;
    }

    uint8_t frame[CRYNET_PROTO_REQUEST_BYTES];
    const size_t len = crynet_proto_build(frame, CRYNET_PROTO_TYPE_REQUEST,
                                           node_id, burst_seq, 0u,
                                           CRYNET_PROTO_FRAG_COUNT, NULL, 0u);
    if (len == 0) {
        return false;
    }

    /* The old burst is stale, and it is cleared *before* the request goes
     * out: a fragment that arrives between the send and the clear would
     * otherwise be counted into the new burst and then wiped. */
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        node_slot_t *slot = &nl->slots[i];
        if (slot->used && slot->id == node_id) {
            slot->in_burst = false;
            slot->frag_have = 0;
            slot->frag_want = 0;
            slot->frag_seq = burst_seq;
            memset(slot->bitmap, 0, sizeof(slot->bitmap));
        }
    }
    link_unlock(nl);

    static const uint8_t bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
    if (esp_now_send(bcast, frame, len) != ESP_OK) {
        nl->stats.requests_failed++;
        return false;
    }
    nl->stats.requests_sent++;
    return true;
}

bool node_link_burst_state(const node_link_t *nl, uint8_t node_id,
                           node_link_burst_t *out)
{
    if (nl == NULL) {
        return false;
    }

    bool found = false;
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        const node_slot_t *slot = &nl->slots[i];
        if (!slot->used || slot->id != node_id) {
            continue;
        }
        out->node_id = slot->id;
        out->burst_seq = slot->frag_seq;
        out->frag_want = slot->frag_want;
        out->frag_have = slot->frag_have;
        out->complete = slot->in_burst &&
                        (slot->frag_want > 0) &&
                        (slot->frag_have >= slot->frag_want);
        out->bad_payloads = slot->bad_payloads;
        out->missing = (slot->frag_want > slot->frag_have)
                           ? (slot->frag_want - slot->frag_have) : 0u;
        found = true;
        break;
    }
    link_unlock(nl);
    return found;
}

bool node_link_take_window(node_link_t *nl, uint8_t node_id,
                           int16_t *dst, size_t dst_samples)
{
    if (nl == NULL || dst == NULL || dst_samples < CRYNET_PROTO_WINDOW_SAMPLES) {
        return false;
    }

    bool ok = false;
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        node_slot_t *slot = &nl->slots[i];
        if (!slot->used || slot->id != node_id) {
            continue;
        }
        if (slot->in_burst && slot->frag_want == CRYNET_PROTO_FRAG_COUNT &&
            slot->frag_have >= CRYNET_PROTO_FRAG_COUNT && slot->window != NULL) {
            memcpy(dst, slot->window, CRYNET_PROTO_WINDOW_BYTES);
            ok = true;
        }
        break;
    }
    link_unlock(nl);
    return ok;
}

void node_link_reset_burst(node_link_t *nl, uint8_t node_id)
{
    if (nl == NULL) {
        return;
    }
    link_lock(nl);
    for (int i = 0; i < NODE_LINK_MAX_NODES; i++) {
        node_slot_t *slot = &nl->slots[i];
        if (slot->used && slot->id == node_id) {
            slot->in_burst = false;
            slot->frag_have = 0;
            slot->frag_want = 0;
            memset(slot->bitmap, 0, sizeof(slot->bitmap));
        }
    }
    link_unlock(nl);
}

void node_link_get_stats(const node_link_t *nl, node_link_stats_t *out)
{
    if (nl == NULL || out == NULL) {
        return;
    }
    *out = nl->stats;
}
