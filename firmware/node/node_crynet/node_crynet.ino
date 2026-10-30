/*
 * CryNet cot node — ESP32-C3 SuperMini + INMP441 I2S microphone.
 *
 * Stage 2b.  The node is deliberately a dumb sensor.  It captures 16 kHz
 * mono PCM, keeps the last two seconds in RAM, reports a 100 ms RMS over
 * ESP-NOW, and uploads the two-second window as CRC-framed fragments when
 * the hub asks for it.  It never classifies anything: the model lives on
 * the hub, and the front end on the hub consumes the exact same PCM bytes
 * this node sends (the frozen signal contract).
 *
 * Wiring — INMP441 to ESP32-C3 SuperMini:
 *     VCC -> 3V3        GND -> GND        L/R -> GND   (left channel)
 *     SCK -> GPIO4      WS  -> GPIO5      SD  -> GPIO6
 *
 * The INMP441 drives a standard I2S frame of two 32-bit slots, so the
 * peripheral is configured for 32-bit slots and the samples are converted
 * to int16 in software by keeping the top 16 bits of the 24-bit word.
 * That is the only place the mic's 24 bits are narrowed; everything after
 * this point is int16, exactly like the hub's input.
 *
 * Serial console — 115200 baud, one command per line:
 *     status   print the node state
 *     stats    print the counters
 *     freeze   freeze the live window now (and make it the upload target)
 *     burst    dump the frozen window as fragment frames, in the same
 *              framing the radio uses, so a PC can check it end to end
 *     id <n>   set the node id (1..255)
 *     help     list the commands
 *
 * Frames.  One framing is used on the radio and on the serial console:
 *
 *     0  0xC3            magic
 *     1  0x7E            magic
 *     2  type            1 = telemetry, 2 = burst fragment
 *     3  node id
 *     4  u16 burst seq   (telemetry: the sequence of the pending burst)
 *     6  u16 frag index  (telemetry: 0)
 *     8  u16 frag count  (telemetry: 0)
 *    10  u16 payload len
 *    12  u16 payload CRC-16/CCITT-FALSE
 *    14  payload
 *    ..  u16 frame CRC-16/CCITT-FALSE over everything above
 *
 * Requests from the hub are 12 bytes:
 *
 *     0  0xC3  1 0x7E  2 type=3  3 node id
 *     4  u16 burst seq   6 u16 first fragment   8 u16 fragment count
 *    10  u16 CRC-16/CCITT-FALSE
 *
 * The telemetry payload is 12 bytes: u32 rms x 1000, u16 window ms,
 * u8 flags, u8 reserved, u32 CRC-32 of the frozen window (0 when there is
 * none).  The hub recomputes that CRC over the window it reassembles from
 * the radio, so the two agreeing proves the audio crossed the link intact.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <esp_timer.h>
#include <esp_now.h>
#include <esp_mac.h>
#include <ESP_I2S.h>

/* ------------------------------------------------------------------ pins -- */

static const uint8_t PIN_SCK = 4;   /* INMP441 SCK -> I2S BCLK */
static const uint8_t PIN_WS  = 5;   /* INMP441 WS            */
static const uint8_t PIN_DIN = 6;   /* INMP441 SD  -> I2S in  */

/* --------------------------------------------------------------- contract -- */

static const uint32_t SAMPLE_RATE    = 16000;
static const uint32_t WINDOW_SAMPLES = 32000;              /* 2.000 s */
static const uint32_t BURST_BYTES    = WINDOW_SAMPLES * 2;  /* 64000  */
static const uint32_t TELEMETRY_MS   = 100;
static const uint32_t RMS_SAMPLES    = SAMPLE_RATE / 10;    /* 100 ms  */

/* A fragment frame is 16 bytes of header plus the payload plus 2 bytes of
 * CRC.  ESP-NOW carries at most 255 bytes in one frame, so 224 bytes of
 * payload leaves comfortable headroom. */
static const uint16_t FRAG_PAYLOAD = 224;
static const uint16_t FRAG_COUNT   = (BURST_BYTES + FRAG_PAYLOAD - 1) / FRAG_PAYLOAD;

/* The hub starts classifying at an RMS of 0.03 (frozen decision 5).  The
 * node uses a higher level to decide that something worth uploading is
 * happening: a cry is well above 0.03, room noise is not. */
static const float EVENT_RMS = 0.10f;

/* ----------------------------------------------------------------- state -- */

static I2SClass  g_i2s;
static int32_t   g_raw[512];            /* I2S staging, 32-bit slots      */
static int16_t   g_window[WINDOW_SAMPLES]; /* live, circular, chronological */
static int16_t   g_frozen[WINDOW_SAMPLES]; /* snapshot offered for upload */
static uint32_t  g_write = 0;           /* next write index into g_window */
static uint32_t  g_filled = 0;          /* valid samples, up to 32000     */
static uint32_t  g_frozen_fill = 0;     /* valid samples in g_frozen      */

static bool      g_frozen_valid = false;
static uint32_t  g_frozen_crc = 0;    /* CRC-32 of the frozen window's bytes */
static uint16_t  g_burst_seq = 0;
static uint8_t   g_node_id = 1;

static uint16_t  g_telemetry_seq = 0;
static uint32_t  g_last_tick = 0;
static float     g_rms = 0.0f;
static int32_t   g_mean = 0;

static uint32_t  g_frames_sent = 0;
static uint32_t  g_frames_lost = 0;
static uint32_t  g_requests = 0;
static uint32_t  g_heartbeats = 0;
static uint32_t  g_freezes = 0;

static bool      g_dump_active = false;  /* suppress text while dumping */

/* Set from the radio callback, acted on in the loop.  The callback runs in
 * the WiFi task, and sending 286 fragments from there would block the
 * radio for seconds. */
static volatile bool     g_request_pending = false;
static volatile uint16_t g_request_seq = 0;
static volatile uint16_t g_request_first = 0;
static volatile uint16_t g_request_count = 0;

/* ----------------------------------------------------------------- crc16 -- */

static uint16_t crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
                                  : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

/* CRC-32 (the IEEE 802.3 one: reflected, polynomial 0xEDB88320, the
 * final XOR of 0xFFFFFFFF that zlib's crc32 applies).  The hub computes
 * the same value over the window it reassembles from the radio, so the two
 * agreeing proves the audio crossed the link unchanged. */
static uint32_t crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 1u) ? ((crc >> 1) ^ 0xEDB88320u) : (crc >> 1);
        }
    }
    return crc ^ 0xFFFFFFFFu;
}

/* ---------------------------------------------------------------- frames -- */

static uint8_t g_frame[256];

/* Build one frame into g_frame and return its total length. */
static size_t build_frame(uint8_t type, uint16_t seq, uint16_t frag,
                          uint16_t count, const uint8_t *payload, uint16_t plen) {
    g_frame[0] = 0xC3;
    g_frame[1] = 0x7E;
    g_frame[2] = type;
    g_frame[3] = g_node_id;
    g_frame[4] = (uint8_t)(seq & 0xFF);
    g_frame[5] = (uint8_t)(seq >> 8);
    g_frame[6] = (uint8_t)(frag & 0xFF);
    g_frame[7] = (uint8_t)(frag >> 8);
    g_frame[8] = (uint8_t)(count & 0xFF);
    g_frame[9] = (uint8_t)(count >> 8);
    g_frame[10] = (uint8_t)(plen & 0xFF);
    g_frame[11] = (uint8_t)(plen >> 8);
    uint16_t pcrc = (plen > 0) ? crc16(payload, plen) : 0;
    g_frame[12] = (uint8_t)(pcrc & 0xFF);
    g_frame[13] = (uint8_t)(pcrc >> 8);
    if (plen > 0) {
        memcpy(&g_frame[14], payload, plen);
    }
    size_t total = 14 + (size_t)plen;
    uint16_t fcrc = crc16(g_frame, total);
    g_frame[total] = (uint8_t)(fcrc & 0xFF);
    g_frame[total + 1] = (uint8_t)(fcrc >> 8);
    return total + 2;
}

/* ----------------------------------------------------------- the window -- */

/* Exact mean over the valid part of the live window.  The sum is an
 * integer: a float accumulator loses a few counts on 32000 samples and
 * the residual DC is what the front end's standardisation then amplifies
 * (this is exactly the bug the hub's on-device probes caught).
 *
 * The valid region is the newest `valid` samples, so it is walked
 * backwards from the write cursor.  That matters after a burst: the live
 * window is dropped and refilled, and until it is full again the newest
 * samples are not at the start of the array. */
static int32_t window_mean(uint32_t valid) {
    int64_t sum = 0;
    uint32_t idx = g_write;
    for (uint32_t k = 0; k < valid; k++) {
        if (idx == 0) {
            idx = WINDOW_SAMPLES;
        }
        idx--;
        sum += (int64_t)g_window[idx];
    }
    return (int32_t)(sum / (int64_t)valid);
}

/* RMS of the newest n samples, using the mean of the whole window so that
 * the number matches what the hub's front end will see for the same
 * window.  Returned in the same normalised units as the hub: the sample
 * divided by 32768 after the mean is removed. */
static float rms_of_last(int32_t mean, uint32_t n) {
    if (n == 0) {
        return 0.0f;
    }
    uint32_t idx = (g_write + WINDOW_SAMPLES - n) % WINDOW_SAMPLES;
    int64_t acc = 0;
    for (uint32_t k = 0; k < n; k++) {
        int32_t d = (int32_t)g_window[idx] - mean;
        acc += (int64_t)d * d;
        if (++idx == WINDOW_SAMPLES) {
            idx = 0;
        }
    }
    double m = (double)acc / (double)n;
    return (float)(sqrt(m) / 32768.0);
}

/* Copy the live window into the frozen snapshot, oldest sample first. */
static void freeze_window(void) {
    for (uint32_t i = 0; i < WINDOW_SAMPLES; i++) {
        uint32_t idx = g_write + i;
        if (idx >= WINDOW_SAMPLES) {
            idx -= WINDOW_SAMPLES;
        }
        g_frozen[i] = g_window[idx];
    }
    g_frozen_fill = WINDOW_SAMPLES;
    g_frozen_valid = true;
    /* The checksum of the exact bytes that will be uploaded.  The hub
     * computes the same value over the window it reassembles, so the two
     * agreeing is the proof that the radio delivered the audio intact. */
    g_frozen_crc = crc32((const uint8_t *)g_frozen, BURST_BYTES);
    g_burst_seq++;
    g_freezes++;
}

/* Sample i of the upload target, oldest first. */
static int16_t burst_sample(uint16_t i, bool from_frozen) {
    if (from_frozen) {
        return g_frozen[i];
    }
    uint32_t idx = g_write + i;
    if (idx >= WINDOW_SAMPLES) {
        idx -= WINDOW_SAMPLES;
    }
    return g_window[idx];
}

/* ------------------------------------------------------------------ i2s -- */

static bool i2s_start(void) {
    g_i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_DIN);
    g_i2s.setTimeout(500);
    /* STEREO with both slots — the peripheral must be given the whole
     * 64-bit frame.
     *
     * The INMP441 drives a 64-bit I2S frame of two 32-bit slots and puts
     * its 24-bit sample, left-justified, in the left one.  Asking for
     * I2S_SLOT_MODE_MONO halves the frame to 32 bits, the microphone's
     * framing breaks and the samples come out misaligned: measured on the
     * real board, -3500 counts with the full frame against -620 with the
     * halved one.  Asking for stereo also makes the Arduino library force
     * the both-slots mask whatever mask is given, so the DMA delivers the
     * left and the right slot interleaved either way; the right one is
     * dropped in i2s_pump().  node_diag prints both side by side. */
    if (!g_i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                     I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        return false;
    }
    /* The INMP441's first samples are garbage: measured on the real board,
     * the first 100 ms window after begin() is a full-scale burst (the
     * capture node's RMS field reads 656 milli against the room's 6-11)
     * and it decays over about half a second.  Without this, every boot
     * would freeze a garbage window the moment the burst crossed the EVENT
     * level and hand the hub a spurious upload.  Discard 500 ms; the
     * slower DC drift that remains is removed by the mean. */
    static const uint32_t WARMUP_FRAMES = SAMPLE_RATE / 2;   /* 500 ms */
    uint32_t warmed = 0;
    while (warmed < WARMUP_FRAMES) {
        size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
        got -= got % 8;                 /* whole stereo frames only */
        warmed += got / 8;
    }
    return true;
}

/* Read whatever the microphone has produced and append it to the window. */
static uint32_t g_loop_iters = 0;
static uint32_t g_loop_max_us = 0;
static uint64_t g_t_pump = 0, g_t_tick = 0, g_t_req = 0, g_t_rest = 0;
static uint32_t g_pump_calls = 0;
static uint32_t g_pump_empty = 0;   /* calls that returned no whole frame */
static uint32_t g_pump_frames = 0;
static uint32_t g_pump_max_us = 0;
static size_t i2s_pump(void) {
    const int64_t t0 = esp_timer_get_time();
    size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
    const int64_t dt = esp_timer_get_time() - t0;
    g_t_pump += (uint64_t)dt;
    if (dt > (int64_t)g_pump_max_us) {
        g_pump_max_us = (uint32_t)dt;
    }
    g_pump_calls++;
    if (got < 8) {
        g_pump_empty++;
    }
    g_pump_frames += got / 8;
    got -= got % 8;                 /* whole stereo frames only */
    size_t frames = got / 8;
    for (size_t f = 0; f < frames; f++) {
        /* The left slot holds the microphone's 24-bit sample, left
         * justified, so the top 16 bits are the full-scale int16 value.
         * The right slot is a constant and is dropped. */
        int16_t s = (int16_t)(g_raw[f * 2] >> 16);
        g_window[g_write] = s;
        g_write++;
        if (g_write == WINDOW_SAMPLES) {
            g_write = 0;
        }
        if (g_filled < WINDOW_SAMPLES) {
            g_filled++;
        }
    }
    return frames;
}

/* ---------------------------------------------------------------- radio -- */

static uint8_t g_bcast[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

/* The hub's address, learned from the request the node receives: the hub
 * broadcasts its requests, and the node replies to the address they came
 * from.  Unicast is used once the hub is known, because a broadcast
 * destination is filtered more aggressively by the receiver's radio. */
static uint8_t g_hub_mac[6] = {0};
static bool     g_hub_known = false;
/* Set from the receive callback, acted on in the loop: the callback
 * runs in the WiFi task, and esp_now_add_peer() waits for that very
 * task, which wedged the radio — the send callback stopped firing and
 * every radio_send burned its two-second cap.  The hub's node_link
 * carries the same rule: peers are added from a normal task. */
static volatile bool g_hub_peer_pending = false;
static uint8_t       g_pending_mac[6];

/* The radio's transmit callback.  It fires when a frame has actually left
 * the queue, and the sender waits for it before queueing the next one:
 * ESP-NOW's queue is ten frames deep, so a 286-fragment burst sent back to
 * back overflows it and every frame past the tenth is lost for good. */
static volatile uint32_t g_tx_acks = 0;

/* How long the sender waits for the radio to take each frame.  A frame
 * that is acknowledged in a millisecond was handed to the driver, not put
 * on the air; a frame that takes a hundred milliseconds was transmitted
 * and acknowledged. */
static uint32_t g_send_max_us = 0;   /* time inside esp_now_send() */
static uint32_t g_send_calls = 0;
static uint32_t g_tx_wait_us = 0;
static uint32_t g_tx_wait_n = 0;
static uint32_t g_tx_wait_max = 0;

static void on_send(const esp_now_send_info_t *info, esp_now_send_status_t status) {
    (void)info;
    (void)status;
    g_tx_acks++;
}

static void on_recv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
    if (len < 12 || data[0] != 0xC3 || data[1] != 0x7E) {
        return;
    }
    /* A heartbeat (type 4) is the hub keeping its radio awake.  It asks
     * for nothing, so the node's window is left alone. */
    /* Learn the hub's address from any frame it sends — requests and
     * heartbeats both — and add it as a peer so the reply can be
     * unicast to it.  The heartbeat arrives every 100 ms, so the
     * address is learned within a tenth of a second of boot; waiting
     * for a request meant that a hub which had already heard the node
     * (and so had stopped probing) never told the node where to send. */
    if (!g_hub_known && !g_hub_peer_pending && info != NULL &&
        (data[2] == 3 || data[2] == 4)) {
        memcpy(g_pending_mac, info->src_addr, 6);
        g_hub_peer_pending = true;
    }
    /* A heartbeat (type 4) is the hub keeping its radio awake.  It asks
     * for nothing, so the node's window is left alone. */
    if (data[2] == 4) {
        g_heartbeats++;
        return;
    }
    if (data[2] != 3) {
        return;
    }
    uint16_t want = (uint16_t)data[10] | ((uint16_t)data[11] << 8);
    if (crc16(data, 10) != want) {
        g_frames_lost++;
        return;
    }
    if (data[3] != g_node_id && data[3] != 0xFF) {
        return;                      /* not for us */
    }
    g_request_pending = true;
    g_request_seq   = (uint16_t)data[4] | ((uint16_t)data[5] << 8);
    g_request_first = (uint16_t)data[6] | ((uint16_t)data[7] << 8);
    g_request_count = (uint16_t)data[8] | ((uint16_t)data[9] << 8);
    if (Serial) {
        Serial.printf("request: seq %u first %u count %u\n",
                      (unsigned)g_request_seq, (unsigned)g_request_first,
                  (unsigned)g_request_count);
    }
}

static bool radio_start(void) {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.channel(1);
    delay(100);

    if (esp_now_init() != ESP_OK) {
        return false;
    }
    esp_now_register_recv_cb(on_recv);
    esp_now_register_send_cb(on_send);

    esp_now_peer_info_t peer = {};
    memcpy(peer.peer_addr, g_bcast, 6);
    /* The channel is set explicitly rather than left at 0.  With 0 the
     * peer is supposed to follow the interface's current channel, but on
     * this driver the frame never left the node: the send callback fired
     * and nothing arrived at the hub, on any of the thirteen channels.
     * The hub's peer has always had the channel set, and the hub's
     * transmissions arrive perfectly. */
    peer.channel = 1;
    peer.ifidx   = WIFI_IF_STA;
    peer.encrypt = false;
    if (esp_now_add_peer(&peer) != ESP_OK) {
        return false;
    }
    return true;
}

static bool radio_send(const uint8_t *data, size_t len) {
    /* Wait for the previous frame to leave the queue before adding this
     * one.  ESP-NOW's transmit queue holds ten frames; a burst is 286 of
     * them, so without this the queue overflows, esp_now_send() fails with
     * ESP_ERR_NO_MEM, and the burst never gets reassembled on the hub. */
    const uint32_t before = g_tx_acks;
    /* Broadcast.  Unicast to the learned hub address wedged the send
     * path: the frame was accepted, never transmitted, and the send
     * callback never fired, so every send burned its wait cap and the
     * loop starved the microphone.  Broadcast callbacks fire in
     * milliseconds; revisit unicast only with a passing dedicated
     * test. */
    const uint8_t *dest = g_bcast;
    const int64_t st0 = esp_timer_get_time();
    const esp_err_t serr = esp_now_send(dest, data, len);
    const int64_t sdt = esp_timer_get_time() - st0;
    g_send_calls++;
    if (sdt > (int64_t)g_send_max_us) {
        g_send_max_us = (uint32_t)sdt;
    }
    if (serr != ESP_OK) {
        g_frames_lost++;
        return false;
    }
    g_frames_sent++;
    uint32_t waited = 0;
    const uint32_t t0 = micros();
    while (g_tx_acks == before && waited < 50) {
        delay(1);
        waited++;
    }
    const uint32_t waited_us = micros() - t0;
    g_tx_wait_us += waited_us;
    g_tx_wait_n++;
    if (waited_us > g_tx_wait_max) {
        g_tx_wait_max = waited_us;
    }
    return true;
}

/* Send one fragment of the upload target. */
static void send_fragment(uint16_t index, bool from_frozen, bool over_serial) {
    uint8_t payload[FRAG_PAYLOAD];
    uint16_t offset = (uint16_t)(index * FRAG_PAYLOAD);
    uint16_t len = (uint16_t)(BURST_BYTES - offset);
    if (len > FRAG_PAYLOAD) {
        len = FRAG_PAYLOAD;
    }
    for (uint16_t i = 0; i < len; i += 2) {
        int16_t s = burst_sample((uint16_t)(offset / 2 + i / 2), from_frozen);
        payload[i]     = (uint8_t)(s & 0xFF);
        payload[i + 1] = (uint8_t)((uint16_t)s >> 8);
    }
    size_t total = build_frame(2, g_burst_seq, index, FRAG_COUNT, payload, len);
    if (over_serial) {
        Serial.write(g_frame, total);
    } else {
        radio_send(g_frame, total);
    }
}

/* ------------------------------------------------------------ telemetry -- */

static void send_telemetry(void) {
    int32_t rms_milli = (int32_t)(g_rms * 1000.0f + (g_rms >= 0 ? 0.5f : -0.5f));
    uint8_t payload[12];
    payload[0] = (uint8_t)(rms_milli & 0xFF);
    payload[1] = (uint8_t)((rms_milli >> 8) & 0xFF);
    payload[2] = (uint8_t)((rms_milli >> 16) & 0xFF);
    payload[3] = (uint8_t)((rms_milli >> 24) & 0xFF);
    uint16_t win_ms = (uint16_t)(WINDOW_SAMPLES * 1000 / SAMPLE_RATE);
    payload[4] = (uint8_t)(win_ms & 0xFF);
    payload[5] = (uint8_t)(win_ms >> 8);
    uint8_t flags = 0;
    if (g_frozen_valid) {
        flags |= 0x01;              /* a burst is ready */
    }
    if (g_rms >= EVENT_RMS) {
        flags |= 0x02;              /* the event level is being crossed */
    }
    if (g_filled == WINDOW_SAMPLES) {
        flags |= 0x04;              /* the live window is complete */
    }
    payload[6] = flags;
    payload[7] = 0;
    /* The CRC-32 of the frozen window, so the hub can check the window it
     * reassembles against the one the node actually froze. */
    uint32_t crc = g_frozen_valid ? g_frozen_crc : 0u;
    payload[8]  = (uint8_t)(crc & 0xFF);
    payload[9]  = (uint8_t)((crc >> 8) & 0xFF);
    payload[10] = (uint8_t)((crc >> 16) & 0xFF);
    payload[11] = (uint8_t)((crc >> 24) & 0xFF);

    size_t total = build_frame(1, g_burst_seq, 0, 0, payload, sizeof(payload));
    radio_send(g_frame, total);
    g_telemetry_seq++;
}

/* ---------------------------------------------------------------- console -- */

static void print_status(void) {
    /* The radio's own address, which the hub needs in its table of node
     * addresses.  WiFi.macAddress() reports a different one on this
     * board, so it is read from the chip directly. */
    uint8_t sta[6] = {0};
    esp_read_mac(sta, ESP_MAC_WIFI_STA);
    Serial.printf("node %u  mac %02X:%02X:%02X:%02X:%02X:%02X\n", g_node_id,
                  sta[0], sta[1], sta[2], sta[3], sta[4], sta[5]);
    Serial.printf("esp_now_send calls=%u max_us=%u\n",
                  (unsigned)g_send_calls, (unsigned)g_send_max_us);
    Serial.printf("time pump=%llu tick=%llu req=%llu rest=%llu ms\n",
                  (unsigned long long)(g_t_pump / 1000),
                  (unsigned long long)(g_t_tick / 1000),
                  (unsigned long long)(g_t_req / 1000),
                  (unsigned long long)(g_t_rest / 1000));
    Serial.printf("pump calls=%u empty=%u frames=%u max_us=%u loops=%u loop_max_us=%u\n",
                  (unsigned)g_pump_calls, (unsigned)g_pump_empty,
                  (unsigned)g_pump_frames, (unsigned)g_pump_max_us,
                  (unsigned)g_loop_iters, (unsigned)g_loop_max_us);
    Serial.printf("window %u/%u samples   frozen=%u seq=%u\n", (unsigned)g_filled,
                  (unsigned)WINDOW_SAMPLES, g_frozen_valid ? 1 : 0,
                  (unsigned)g_burst_seq);
    if (g_frozen_valid) {
        Serial.printf("frozen crc32 0x%08X\n", (unsigned)g_frozen_crc);
    }
    Serial.printf("rms %.4f  mean %d  fragments=%u\n", g_rms, (int)g_mean,
                  (unsigned)FRAG_COUNT);
    Serial.printf("heap %u bytes\n", (unsigned)ESP.getFreeHeap());
    Serial.printf("channel %d\n", (int)WiFi.channel());
    uint32_t ver = 0;
    esp_now_get_version(&ver);
    Serial.printf("ESP-NOW version %u, hub %s\n", (unsigned)ver,
                  g_hub_known ? "known" : "unknown");
}

static void print_stats(void) {
    Serial.printf("telemetry seq %u  frames sent %u  lost %u  requests %u  freezes %u\n",
                  (unsigned)g_telemetry_seq, (unsigned)g_frames_sent,
                  (unsigned)g_frames_lost, (unsigned)g_requests,
                  (unsigned)g_freezes);
    Serial.printf("tx wait: avg %u us, max %u us, over %u frames\n",
                  (unsigned)(g_tx_wait_n ? g_tx_wait_us / g_tx_wait_n : 0),
                  (unsigned)g_tx_wait_max, (unsigned)g_tx_wait_n);
}

static void handle_command(char *line) {
    if (strcmp(line, "status") == 0) {
        print_status();
    } else if (strcmp(line, "stats") == 0) {
        print_stats();
    } else if (strcmp(line, "freeze") == 0) {
        if (g_filled < WINDOW_SAMPLES) {
            Serial.println("window not full yet");
        } else {
            freeze_window();
            Serial.printf("frozen seq=%u\n", g_burst_seq);
        }
    } else if (strcmp(line, "burst") == 0) {
        if (!g_frozen_valid) {
            Serial.println("no frozen window");
        } else {
            Serial.printf("BURST seq=%u fragments=%u bytes=%u\n", g_burst_seq,
                          FRAG_COUNT, (unsigned)BURST_BYTES);
            g_dump_active = true;
            for (uint16_t i = 0; i < FRAG_COUNT; i++) {
                send_fragment(i, true, true);
            }
            g_dump_active = false;
            Serial.println("BURST-END");
        }
    } else if (strncmp(line, "id ", 3) == 0) {
        int v = atoi(line + 3);
        if (v >= 1 && v <= 255) {
            g_node_id = (uint8_t)v;
            Serial.printf("node id %u\n", g_node_id);
        } else {
            Serial.println("id must be 1..255");
        }
    } else if (strcmp(line, "help") == 0) {
        Serial.println("status | stats | freeze | burst | id <n> | help");
    } else {
        Serial.println("unknown command");
    }
}

/* ------------------------------------------------------------------ loop -- */

void setup() {
    Serial.begin(115200);
    /* A closed serial port must never cost the loop time: the HWCDC
     * write path waits up to two seconds per print when the host is not
     * reading, and an unattended node printing its rms every hundred
     * milliseconds starved its own loop into a crawl.  Zero timeout
     * makes prints drop instead of block. */
    Serial.setTxTimeoutMs(0);
    delay(200);

    uint8_t mac[6];
    WiFi.macAddress(mac);
    g_node_id = (uint8_t)((mac[5] & 0x0F) + 1);

    Serial.println("\nCryNet node firmware — Stage 2b");
    Serial.printf("node id %u (derived from the MAC; change it with \"id <n>\")\n",
                  g_node_id);

    if (!i2s_start()) {
        Serial.println("FATAL: I2S init failed");
        while (true) {
            delay(1000);
        }
    }
    Serial.println("I2S ready: 16 kHz, mono, 32-bit slots -> int16");

    if (!radio_start()) {
        Serial.println("FATAL: ESP-NOW init failed");
        while (true) {
            delay(1000);
        }
    }
    uint32_t now_version = 0;
    if (esp_now_get_version(&now_version) == ESP_OK) {
        Serial.printf("ESP-NOW protocol version %u\n", (unsigned)now_version);
    }
    Serial.println("ESP-NOW ready on channel 1");

    Serial.println("commands: status | stats | freeze | burst | id <n> | help");
}

void loop() {
    const int64_t lt0 = esp_timer_get_time();
    g_loop_iters++;
    if (g_hub_peer_pending) {
        g_hub_peer_pending = false;
        esp_now_peer_info_t hub = {};
        memcpy(g_hub_mac, g_pending_mac, 6);
        memcpy(hub.peer_addr, g_hub_mac, 6);
        hub.channel = 1;
        hub.ifidx = WIFI_IF_STA;
        hub.encrypt = false;
        if (esp_now_add_peer(&hub) == ESP_OK) {
            g_hub_known = true;
            if (Serial)
                Serial.printf("hub is %02X:%02X:%02X:%02X:%02X:%02X\n",
                          g_hub_mac[0], g_hub_mac[1], g_hub_mac[2],
                          g_hub_mac[3], g_hub_mac[4], g_hub_mac[5]);
        }
    }
    i2s_pump();

    /* The window is only worth measuring once it holds a full 100 ms: the
     * hub's front end removes the mean of the whole two seconds, and a
     * partial window would not match it. */
    const int64_t tk0 = esp_timer_get_time();
    if (g_filled >= RMS_SAMPLES) {
        uint32_t now = millis();
        if (now - g_last_tick >= TELEMETRY_MS) {
            g_last_tick = now;
            g_mean = window_mean(g_filled);
            uint32_t n = (g_filled < RMS_SAMPLES) ? g_filled : RMS_SAMPLES;
            g_rms = rms_of_last(g_mean, n);

            send_telemetry();

            if (!g_dump_active && Serial) {
                /* Serial here is USB-CDC: with no host reading the
                 * port, a write blocks — and this print runs every
                 * hundred milliseconds, so an unattended node starved
                 * its own loop and stopped pumping the microphone. */
                Serial.printf("rms %.4f  mean %d  %s\n", g_rms, (int)g_mean,
                              g_rms >= EVENT_RMS ? "EVENT" : "");
            }

            if (g_rms >= EVENT_RMS && !g_frozen_valid &&
                g_filled == WINDOW_SAMPLES) {
                freeze_window();
                if (!g_dump_active && Serial) {
                    Serial.printf("froze window, burst seq %u\n", g_burst_seq);
                }
            }
        }
    }
    g_t_tick += (uint64_t)(esp_timer_get_time() - tk0);

    /* A request from the hub is served from the frozen snapshot when it
     * matches, and from the live window otherwise. */
    const int64_t rq0 = esp_timer_get_time();
    if (g_request_pending) {
        g_request_pending = false;
        g_requests++;
        bool from_frozen = (g_request_seq == g_burst_seq) && g_frozen_valid;
        if (!from_frozen && g_filled < WINDOW_SAMPLES) {
            /* The live window is still refilling after the last upload,
             * so its chronological order is not known.  Wait. */
            from_frozen = false;
            if (!g_dump_active && Serial) {
                Serial.println("request ignored: the live window is not complete");
            }
        } else {
            uint16_t first = g_request_first;
            uint16_t count = g_request_count;
            if (count == 0 || count > FRAG_COUNT) {
                count = FRAG_COUNT;
            }
            if (first >= FRAG_COUNT) {
                first = 0;
            }
            for (uint16_t i = 0; i < count; i++) {
                uint16_t index = (uint16_t)(first + i);
                if (index >= FRAG_COUNT) {
                    break;
                }
                send_fragment(index, from_frozen, false);
            }
            /* A one-fragment probe costs a few milliseconds of air, not
             * a burst, so the live window keeps its value.  A real burst
             * took seconds to send and the microphone kept running into
             * a DMA buffer that was not being read, so the live window
             * has holes in it: drop it and refill; the write cursor
             * stays where it is so the valid region keeps moving. */
            if (count > 1) {
                g_filled = 0;
                g_frozen_valid = false;
            }
        }
    }
    g_t_req += (uint64_t)(esp_timer_get_time() - rq0);

    /* The console. */
    static char line[64];
    static uint8_t len = 0;
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == '\n' || c == '\r') {
            line[len] = 0;
            if (len > 0) {
                handle_command(line);
            }
            len = 0;
        } else if (len < sizeof(line) - 1) {
            line[len++] = c;
        }
    }
    const int64_t ldt = esp_timer_get_time() - lt0;
    g_t_rest += (uint64_t)ldt;
    if (ldt > (int64_t)g_loop_max_us) {
        g_loop_max_us = (uint32_t)ldt;
    }
}
