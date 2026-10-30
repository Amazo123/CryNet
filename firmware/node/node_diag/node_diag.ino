/*
 * CryNet node diagnostic — ESP32-C3 SuperMini + INMP441.
 *
 * A bring-up tool, not part of the running system.  It reads the I2S
 * stream in *stereo* — both slots, 32 bits each — and prints what is
 * actually on the wire, so the microphone can be checked without
 * guessing.
 *
 * The INMP441 puts its 24-bit sample in the left slot of a 64-bit I2S
 * frame, left-justified, and drives the other slot with silence.  So a
 * healthy reading is:
 *
 *     left slot   a real 24-bit value with the microphone's DC bias
 *     right slot  zero
 *
 * What this distinguishes:
 *
 *   left ~ 0, right ~ 0      the microphone is not driving the data line
 *                             — check power, ground, the clock, and the
 *                             word-select line
 *   left real, right 0        the microphone is fine
 *   left 0, right real        L/R is not grounded, or WS and L/R are
 *                             swapped on the module
 *   both noisy                electrical noise on the data line
 *
 * If the first reading shows nothing, it then **scans every exposed
 * GPIO** to find where the microphone's data actually is, so a
 * mis-wired pin is found rather than guessed at.
 *
 * Usage: open in the Arduino IDE, upload, and read the serial monitor
 * at 115200 baud.  It prints a verdict at the end.
 */

#include <Arduino.h>
#include <ESP_I2S.h>

static const uint8_t PIN_SCK = 4;
static const uint8_t PIN_WS  = 5;
static const uint8_t PIN_DIN = 6;

/* The SuperMini breaks out GPIO0..GPIO10.  GPIO18..21 are USB and UART
 * and are not scanned. */
static const uint8_t SCAN_PINS[] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
static const int    SCAN_COUNT = (int)(sizeof(SCAN_PINS) / sizeof(SCAN_PINS[0]));

static const uint32_t SAMPLE_RATE = 16000;
static const uint32_t FRAMES = 4000;      /* ~0.25 s of stereo frames */

static I2SClass g_i2s;
static int32_t  g_raw[FRAMES * 2];

struct SlotStats {
    int32_t lo, hi;
    double  sum;
    double  sumsq;
    int32_t zero_count;
    int32_t count;
};

static void analyse(const int32_t *slot, uint32_t n, SlotStats *st) {
    st->lo = slot[0];
    st->hi = slot[0];
    st->sum = 0.0;
    st->sumsq = 0.0;
    st->zero_count = 0;
    st->count = (int32_t)n;
    for (uint32_t i = 0; i < n; i++) {
        int32_t v = slot[i];
        if (v < st->lo) {
            st->lo = v;
        }
        if (v > st->hi) {
            st->hi = v;
        }
        st->sum += v;
        st->sumsq += (double)v * (double)v;
        if (v == 0) {
            st->zero_count++;
        }
    }
}

static double rms_of(const SlotStats *st) {
    double mean = st->sum / st->count;
    double var = st->sumsq / st->count - mean * mean;
    return sqrt(var > 0.0 ? var : 0.0);
}

static void report(const char *label, const SlotStats *st) {
    double mean = st->sum / st->count;
    Serial.printf(
        "%-11s min %11ld  max %11ld  mean %12.1f  rms %9.1f  exact zeros %5.1f%%\n",
        label, (long)st->lo, (long)st->hi, mean, rms_of(st),
        100.0 * st->zero_count / st->count);
    /* The same data read as if the 24 bits sat at the bottom of the slot
     * instead of the top — the two common alignments. */
    Serial.printf("            left-justified (>>16): min %8ld max %8ld   "
                  "right-justified (&0xFFFFFF): min %8ld max %8ld\n",
                  (long)(st->lo >> 16), (long)(st->hi >> 16),
                  (long)(st->lo & 0xFFFFFF), (long)(st->hi & 0xFFFFFF));
}

/* Open the I2S on a given set of pins.  Returns false if it fails. */
static bool open_i2s(int8_t sck, int8_t ws, int8_t din) {
    g_i2s.end();
    /* The peripheral and the DMA buffer have to be fully torn down and
     * given time to settle, or the next reading comes from the previous
     * configuration. */
    delay(150);
    g_i2s.setPins(sck, ws, -1, din);
    g_i2s.setTimeout(2000);
    if (!g_i2s.begin(I2S_MODE_STD, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_32BIT,
                     I2S_SLOT_MODE_STEREO, I2S_STD_SLOT_BOTH)) {
        return false;
    }
    delay(150);
    g_i2s.readBytes((char *)g_raw, sizeof(g_raw));   /* discard one buffer */
    delay(60);
    g_i2s.readBytes((char *)g_raw, sizeof(g_raw));   /* and another */
    return true;
}

/* Measure the two slots.  The RMS is reported in int16 units (the value
 * shifted down by 16) so it can be compared with the numbers the running
 * node firmware prints. */
static double measure(uint32_t frames, SlotStats *ls, SlotStats *rs,
                      double *left_rms16, double *right_rms16) {
    size_t got = g_i2s.readBytes((char *)g_raw, sizeof(g_raw));
    got -= got % 8;                                  /* whole stereo frames */
    uint32_t n = (uint32_t)(got / 8);
    if (n > frames) {
        n = frames;
    }
    if (n < 8) {
        return -1.0;
    }
    static int32_t left[FRAMES];
    static int32_t right[FRAMES];
    for (uint32_t f = 0; f < n; f++) {
        left[f] = g_raw[f * 2];
        right[f] = g_raw[f * 2 + 1];
    }
    analyse(left, n, ls);
    analyse(right, n, rs);
    *left_rms16 = rms_of(ls) / 65536.0;
    *right_rms16 = rms_of(rs) / 65536.0;
    return rms_of(ls);
}

/* One row of a scan: the two slots' RMS in int16 units.
 *
 * A healthy INMP441 with L/R grounded drives the left slot with the
 * microphone's data and leaves the right slot silent, so the right RMS
 * is zero while the left one is in the tens or hundreds.  A floating or
 * mis-clocked pin produces large, unstable numbers on both. */
static void scan_role(const char *role, int8_t fixed_sck, int8_t fixed_ws,
                      int8_t fixed_din) {
    Serial.printf("\nScanning the %s pin (SCK=%d WS=%d SD=%d):\n", role,
                  fixed_sck, fixed_ws, fixed_din);
    Serial.println("  pin     left rms16     right rms16");
    SlotStats ls, rs;
    for (int i = 0; i < SCAN_COUNT; i++) {
        int8_t pin = (int8_t)SCAN_PINS[i];
        int8_t sck = fixed_sck, ws = fixed_ws, din = fixed_din;
        if (role[0] == 'd') {
            din = pin;
        } else if (role[0] == 'w') {
            ws = pin;
        } else {
            sck = pin;
        }
        if (!open_i2s(sck, ws, din)) {
            Serial.printf("  %3d    (I2S could not be opened here)\n", pin);
            continue;
        }
        double l16 = 0.0, r16 = 0.0;
        measure(600, &ls, &rs, &l16, &r16);
        bool good = (r16 < 1.0) && (l16 >= 0.5) && (l16 < 30000.0);
        Serial.printf("  %3d    %12.2f    %12.2f%s\n", pin, l16, r16,
                      good ? "   <== THE MICROPHONE" : "");
    }
}

void setup() {
    Serial.begin(115200);
    delay(400);

    Serial.println("CRY-DIAG: INMP441, 16 kHz, 32-bit slots, stereo");
    Serial.printf("assumed pins: SCK=%u WS=%u SD=%u\n", PIN_SCK, PIN_WS, PIN_DIN);

    if (!open_i2s(PIN_SCK, PIN_WS, PIN_DIN)) {
        Serial.println("FATAL: I2S init failed");
        while (true) {
            delay(1000);
        }
    }

    SlotStats ls, rs;
    double l16 = 0.0, r16 = 0.0;
    double lrms = measure(FRAMES, &ls, &rs, &l16, &r16);
    if (lrms < 0.0) {
        Serial.println("FATAL: no samples came back from the I2S peripheral");
        while (true) {
            delay(1000);
        }
    }

    Serial.printf("read %lu frames\n\n", (unsigned long)FRAMES);
    Serial.println("first 16 frames, raw 32-bit slots in hex:");
    Serial.println("   frame        left slot        right slot");
    for (uint32_t f = 0; f < 16; f++) {
        Serial.printf("  %5u   %08lX  %08lX\n", f,
                      (unsigned long)(uint32_t)g_raw[f * 2],
                      (unsigned long)(uint32_t)g_raw[f * 2 + 1]);
    }
    Serial.println();

    report("left slot", &ls);
    report("right slot", &rs);

    double rrms = rms_of(&rs);
    Serial.printf("\nleft slot rms %.1f (%.2f in int16 units), "
                  "right slot rms %.1f (%.2f in int16 units)\n",
                  lrms, l16, rrms, r16);

    Serial.println("\nVERDICT:");
    if (r16 < 1.0 && l16 >= 0.5 && l16 < 30000.0) {
        Serial.println("  GOOD. The left slot carries the signal and the right slot");
        Serial.println("  is silent, which is exactly what the INMP441 does with");
        Serial.println("  L/R grounded. The microphone and the wiring are correct.");
    } else if (l16 >= 30000.0 || r16 >= 30000.0) {
        Serial.println("  GARBAGE. The slots carry full-scale noise, which is what a");
        Serial.println("  floating data line reads. The microphone is not driving");
        Serial.println("  the line: check power, ground, the clock and word select.");
    } else if (l16 < 0.5 && r16 < 0.5) {
        Serial.println("  SILENT. Both slots are flat. The microphone is not driving");
        Serial.println("  the data line at all.");
    } else {
        Serial.println("  UNUSUAL. The two slots are not what the INMP441 should");
        Serial.println("  produce. Look at the scan below for a working pin.");
    }

    /* Where is the microphone actually? */
    scan_role("data", PIN_SCK, PIN_WS, PIN_DIN);
    scan_role("ws", PIN_SCK, PIN_DIN, PIN_DIN);
    scan_role("sck", PIN_WS, PIN_WS, PIN_DIN);

    /* Repeat the original configuration.  If it now reads differently
     * from the first measurement, the scan itself is unreliable and the
     * numbers above should not be trusted. */
    if (open_i2s(PIN_SCK, PIN_WS, PIN_DIN)) {
        double l2 = 0.0, r2 = 0.0;
        measure(FRAMES, &ls, &rs, &l2, &r2);
        Serial.printf("\nRepeat check on the original pins (SCK=%u WS=%u SD=%u): "
                      "left %.2f, right %.2f   (first reading was left %.2f, "
                      "right %.2f)\n", PIN_SCK, PIN_WS, PIN_DIN, l2, r2, l16, r16);
        if (fabs(l2 - l16) > 1.0 || fabs(r2 - r16) > 1.0) {
            Serial.println("The two readings disagree, so the pin scan above is "
                           "not reliable.\nRe-run the diagnostic once the wiring "
                           "has been checked.");
        } else {
            Serial.println("The readings agree, so the scan above is meaningful.");
        }
    }

    Serial.println("\nIf no pin is marked, the microphone is not being clocked at "
                   "all: check that\nSCK really reaches the module's SCK pin, that WS "
                   "reaches its WS pin, and\nthat the module has VCC and GND. The "
                   "INMP441 will not drive its data\nline unless it is powered and sees "
                   "a proper clock and word select.");
    Serial.println("\nCRY-DIAG-DONE");
}

void loop() {
    delay(1000);
}
