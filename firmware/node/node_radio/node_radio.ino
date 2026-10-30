/*
 * CryNet radio bring-up — the smallest thing that can put a frame on
 * the air.
 *
 * This sketch exists because the node's ESP-NOW transmit path could not
 * be shown to work: the hub heard one frame in sixty, and a sweep of all
 * thirteen channels found the node's traffic on none of them, while the
 * node's own send callback fired two milliseconds after every send.  So
 * the frames were being accepted by the driver and then never transmitted.
 *
 * The cause turned out not to be the radio at all: the node's loop was
 * being starved by the blocking USB-CDC write path (a print with no
 * host reading the port costs up to two seconds), so the node was barely
 * running when it was supposed to transmit.  The cure is in
 * node_crynet.ino — `Serial.setTxTimeoutMs(0)`.  This sketch is kept as
 * the smallest possible radio test; note that it *unicasts* to the hub
 * below, and that unicast wedged the send path on the real board, so
 * node_crynet broadcasts instead.
 *
 * This is the Arduino ESP-NOW broadcast example with nothing added except
 * the CryNet frame magic, so that the hub can recognise it.  If this
 * sketch's frames arrive at the hub, the fault is in node_crynet; if they
 * do not, it is in the radio setup or the board.
 *
 * Wiring: none.  The INMP441 is not needed.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_now.h>
#include <ESP_I2S.h>

static const uint8_t PIN_SCK = 4;
static const uint8_t PIN_WS  = 5;
static const uint8_t PIN_DIN = 6;
static I2SClass g_i2s;
static int32_t  g_raw[512];
static bool     g_i2s_ok = false;

static const uint8_t BROADCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};
static const uint8_t HUB[6] = {0x30, 0x30, 0xF9, 0x17, 0x2F, 0x80};
static const uint32_t PERIOD_MS = 100;

static uint8_t  g_frame[32];
static uint32_t g_seq = 0;
static uint32_t g_sent = 0;
static uint32_t g_failed = 0;

static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len)
{
    (void)info;
    Serial.printf("received %d bytes\n", len);
}

static volatile uint32_t g_tx_acks = 0;

static void on_send(const esp_now_send_info_t *info, esp_now_send_status_t status)
{
    (void)info;
    (void)status;
    g_tx_acks++;
}

void setup()
{
    Serial.begin(115200);
    delay(300);
    Serial.println("CryNet radio bring-up");

    /* The microphone first, exactly as node_crynet does it. */
    g_i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_DIN);
    g_i2s.setTimeout(500);
    if (!g_i2s.begin(I2S_MODE_STD, 16000, I2S_DATA_BIT_WIDTH_32BIT,
                     I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        Serial.println("FATAL: I2S init failed");
    } else {
        g_i2s_ok = true;
        Serial.println("I2S ready");
    }

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.channel(1);
    delay(100);

    if (esp_now_init() != ESP_OK) {
        Serial.println("FATAL: esp_now_init failed");
        return;
    }
    esp_now_register_recv_cb(on_recv);
    esp_now_register_send_cb(on_send);

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, BROADCAST, 6);
    peer.channel = 0;
    peer.ifidx = WIFI_IF_STA;
    peer.encrypt = false;
    if (esp_now_add_peer(&peer) != ESP_OK) {
        Serial.println("FATAL: esp_now_add_peer failed");
        return;
    }

    uint8_t mac[6];
    WiFi.macAddress(mac);
    Serial.printf("STA %02X:%02X:%02X:%02X:%02X:%02X, channel %d\n",
                  mac[0], mac[1], mac[2], mac[3], mac[4], mac[5],
                  (int)WiFi.channel());
    /* The hub's address, as a peer, so the frames can be sent to it
     * unicast. */
    esp_now_peer_info_t hub = {};
    memcpy(hub.peer_addr, HUB, 6);
    hub.channel = 1;
    hub.ifidx = WIFI_IF_STA;
    hub.encrypt = false;
    Serial.printf("add hub peer: %d\n", (int)esp_now_add_peer(&hub));

    Serial.println("sending every 100 ms");
}

void loop()
{
    g_frame[0] = 0xC3;
    g_frame[1] = 0x7E;
    g_frame[2] = 0xF0;                      /* a test frame type */
    g_frame[3] = 0x01;
    g_frame[4] = (uint8_t)(g_seq & 0xFF);
    g_frame[5] = (uint8_t)(g_seq >> 8);
    for (int i = 6; i < 28; i++) {
        g_frame[i] = (uint8_t)i;
    }

    if (g_i2s_ok) {
        size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
        got -= got % 8;
        (void)got;
    }

    const uint32_t before = g_tx_acks;
    if (esp_now_send(HUB, g_frame, 28) == ESP_OK) {
        g_sent++;
    } else {
        g_failed++;
    }
    uint32_t waited = 0;
    while (g_tx_acks == before && waited < 2000) {
        delay(1);
        waited++;
    }
    g_seq++;

    if (g_seq % 50 == 0) {
        Serial.printf("sent %u, failed %u\n", (unsigned)g_sent,
                      (unsigned)g_failed);
    }
    delay(PERIOD_MS);
}
