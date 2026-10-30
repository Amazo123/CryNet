/*
 * CryNet capture — ESP32-C3 SuperMini + INMP441, streamed to the PC.
 *
 * This is the tool for collecting in-domain data.  The deployed model was
 * trained on Kaggle corpora that no microphone in this room has ever
 * produced: different capsule, different pre-amplifier, different gain,
 * different room.  Until the model has heard this microphone, the
 * reported accuracy is an estimate about somebody else's audio.
 *
 * The sketch captures 16 kHz mono from the INMP441 and streams it to the
 * PC over the USB serial link as a sequence of records:
 *
 *     0  'C' 'R' 'Y' '1'   magic
 *     4  u16 sequence
 *     6  u16 sample count
 *     8  u32 rms x 1000
 *    12  u16 CRC-16/CCITT-FALSE over the first 12 header bytes and the payload
 *    14  int16 samples, little endian
 *
 * One record is 100 ms.  The CRC is what makes the recording trustworthy:
 * a dropped byte on the USB link would otherwise shift every sample after
 * it, and a dataset of quietly misaligned audio is worse than no dataset.
 * `firmware/tools/collect_clips.py` reads the stream, rejects any record
 * whose CRC does not check out, writes a continuous WAV, and cuts it into
 * clips.
 *
 * Wiring — INMP441 to ESP32-C3 SuperMini:
 *     VCC -> 3V3   GND -> GND   L/R -> GND
 *     SCK -> GPIO4  WS -> GPIO5  SD -> GPIO6
 *
 * The PC can send a single character back while the stream is running —
 * the transmit direction is a separate wire, so nothing the PC sends can
 * corrupt the audio coming out:
 *     S   stop streaming
 *     R   resume streaming
 */

#include <Arduino.h>
#include <ESP_I2S.h>

static const uint8_t PIN_SCK = 4;
static const uint8_t PIN_WS  = 5;
static const uint8_t PIN_DIN = 6;

static const uint32_t SAMPLE_RATE = 16000;
static const uint16_t REC_SAMPLES = 1600;      /* 100 ms per record */
static const uint32_t SERIAL_BAUD = 460800;

static I2SClass g_i2s;
static int32_t  g_raw[512];
static int16_t  g_record[REC_SAMPLES];

static uint16_t g_seq = 0;
static uint32_t g_total_samples = 0;
static bool     g_streaming = true;

static uint8_t  g_header[14];

/* CRC-16/CCITT-FALSE — the same function the node firmware uses, so
 * there is one checksum in the project rather than three. */
static uint16_t crc16_update(uint16_t crc, const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u)
                                  : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static void send_record(const int16_t *samples, uint16_t count) {
    /* The RMS of the record, computed with an exact integer mean, so the
     * PC can find the loud parts without decoding the audio. */
    int64_t sum = 0;
    for (uint16_t i = 0; i < count; i++) {
        sum += (int64_t)samples[i];
    }
    int32_t mean = (int32_t)(sum / (int64_t)count);
    int64_t acc = 0;
    for (uint16_t i = 0; i < count; i++) {
        int32_t d = (int32_t)samples[i] - mean;
        acc += (int64_t)d * d;
    }
    double rms = sqrt((double)acc / (double)count) / 32768.0;
    int32_t rms_milli = (int32_t)(rms * 1000.0 + 0.5);

    g_header[0] = 'C';
    g_header[1] = 'R';
    g_header[2] = 'Y';
    g_header[3] = '1';
    g_header[4] = (uint8_t)(g_seq & 0xFF);
    g_header[5] = (uint8_t)(g_seq >> 8);
    g_header[6] = (uint8_t)(count & 0xFF);
    g_header[7] = (uint8_t)(count >> 8);
    g_header[8] = (uint8_t)(rms_milli & 0xFF);
    g_header[9] = (uint8_t)((rms_milli >> 8) & 0xFF);
    g_header[10] = (uint8_t)((rms_milli >> 16) & 0xFF);
    g_header[11] = (uint8_t)((rms_milli >> 24) & 0xFF);

    /* The checksum covers the header prefix and the payload, so a dropped
     * byte on the link is caught instead of quietly shifting every
     * sample after it. */
    uint16_t crc = crc16_update(0xFFFF, g_header, 12);
    crc = crc16_update(crc, (const uint8_t *)samples, (size_t)count * 2);
    g_header[12] = (uint8_t)(crc & 0xFF);
    g_header[13] = (uint8_t)(crc >> 8);

    Serial.write(g_header, sizeof(g_header));
    Serial.write((const uint8_t *)samples, (size_t)count * 2);
    g_seq++;
}

void setup() {
    Serial.begin(SERIAL_BAUD);
    /* Give the host a moment to open the port, then print a banner that
     * the collector can wait for before it starts parsing. */
    delay(300);

    Serial.println("CRY-CAPTURE-READY 16000 1 16");

    g_i2s.setPins(PIN_SCK, PIN_WS, -1, PIN_DIN);
    g_i2s.setTimeout(500);
    /* STEREO with both slots: the INMP441 drives a 64-bit I2S frame of two
     * 32-bit slots and puts its 24-bit sample, left-justified, in the left
     * one.  The peripheral has to be given the whole frame —
     * I2S_SLOT_MODE_MONO halves it to 32 bits and the microphone's data
     * comes out misaligned — and the right slot is dropped in loop().
     * Asking for stereo also makes the Arduino library force the
     * both-slots mask whatever mask is given. */
    if (!g_i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                     I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        Serial.println("FATAL: I2S init failed");
        while (true) {
            delay(1000);
        }
    }
    /* The INMP441's first samples are garbage: measured on the real board,
     * the first 100 ms record after begin() is a full-scale burst (its own
     * RMS field reads 656 milli against the room's 6-11) and it decays over
     * about half a second.  Discard 500 ms here so no clip ever contains
     * the power-on transient; the slower DC drift that remains is removed
     * by the per-window mean. */
    static const uint32_t WARMUP_FRAMES = SAMPLE_RATE / 2;   /* 500 ms */
    uint32_t warmed = 0;
    while (warmed < WARMUP_FRAMES) {
        size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
        got -= got % 8;                 /* whole stereo frames only */
        warmed += got / 8;
    }
    Serial.println("CRY-CAPTURE-LIVE");
}

void loop() {
    /* Commands from the PC arrive on the other direction of the link. */
    while (Serial.available() > 0) {
        char c = (char)Serial.read();
        if (c == 'S') {
            g_streaming = false;
            Serial.println("CRY-CAPTURE-PAUSED");
        } else if (c == 'R') {
            g_streaming = true;
            Serial.println("CRY-CAPTURE-LIVE");
        }
    }

    if (!g_streaming) {
        delay(20);
        return;
    }

    size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
    got -= got % 8;                     /* whole stereo frames only */
    size_t frames = got / 8;

    for (size_t f = 0; f < frames; f++) {
        /* The left slot holds the microphone's 24-bit sample, left
         * justified; the right slot is a constant and is dropped. */
        g_record[g_total_samples % REC_SAMPLES] = (int16_t)(g_raw[f * 2] >> 16);
        g_total_samples++;
        if (g_total_samples % REC_SAMPLES == 0) {
            send_record(g_record, REC_SAMPLES);
        }
    }
}
