/*
 * CryNet — the hub's display.  See include/hub_display.h.
 *
 * The public API is deliberately dumb: hub_display_update() just copies
 * the newest state under a spinlock, and a low-priority task on the
 * other core redraws whatever changed.  Only this task ever touches the
 * panel, so the driver needs no locking of its own.
 *
 * The screen has two faces.
 *
 *   * A splash.  It runs first, for four seconds: a waveform that moves,
 *     the name, a progress bar and the boot steps.  The user asked for
 *     this — the dashboard should not simply appear.
 *
 *   * The dashboard.  The hub's own state at the top (radio, bluetooth,
 *     uptime), a banner that says what the system is doing, and a card
 *     for every cot: its name, whether it is online, and its level.
 *
 * The palette is a calm dark navy with a teal accent.  Red is kept for
 * one thing only — a confirmed cry — because a panel that is red all
 * the time stops meaning anything.
 *
 * Everything is composed in a framebuffer (320x240 RGB565, in PSRAM)
 * and pushed to the panel in one transfer, so a frame is never torn.
 */

#include "hub_display.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "font5x7.h"
#include "ili9341.h"

static const char *TAG = "hub_display";

/* The panel hangs on the pins the legacy firmware used: CS 10, MOSI 11,
 * SCK 12, DC 13, RST 14, backlight 4. */
#define PIN_MOSI 11
#define PIN_SCLK 12
#define PIN_CS   10
#define PIN_DC   13
#define PIN_RST  14
#define PIN_BL   4

/* This panel is "landscape-first": the upright landscape setting is
 * MADCTL_MY with a 320x240 framebuffer, which is what the legacy
 * firmware used (Adafruit's rotation 2, with its 240 px clipping
 * overridden).  Rotation 1 (MADCTL_MV) turns the whole picture a
 * quarter turn on this glass, which is what happened the first time. */
#define ROTATION_LANDSCAPE 2

#define FB_W 320
#define FB_H 240

/* ---- the palette -------------------------------------------------------- */
/* A dark, calm scheme: navy background, a teal accent, green for a cot
 * that is fine, amber for a cot that is loud, and rose — not fire-engine
 * red — for a confirmed cry. */
#define C_BG         DISPLAY_RGB(12, 20, 32)
#define C_SURFACE    DISPLAY_RGB(21, 32, 45)
#define C_SURFACE_HI DISPLAY_RGB(29, 42, 57)
/* The border is a UI component, so it has to clear 3:1 against the
 * card it sits on — the first choice (40,57,76) measured 1.40:1 and
 * was effectively invisible. */
#define C_BORDER     DISPLAY_RGB(88, 112, 136)
#define C_TEXT       DISPLAY_RGB(228, 236, 245)
#define C_DIM        DISPLAY_RGB(122, 142, 163)
#define C_ACCENT     DISPLAY_RGB(45, 212, 191)
#define C_ACCENT_DIM DISPLAY_RGB(24, 122, 110)
#define C_BLUE       DISPLAY_RGB(96, 165, 250)
#define C_GREEN      DISPLAY_RGB(52, 211, 153)
#define C_AMBER      DISPLAY_RGB(251, 191, 36)
#define C_ALERT      DISPLAY_RGB(251, 113, 133)

/* ---- the layout --------------------------------------------------------- */
#define HEADER_H     30
#define BANNER_X     10
#define BANNER_Y     40
#define BANNER_W     300
#define BANNER_H     44
#define CARD_X       10
#define CARD_W       300
#define CARD_H       40
#define CARD_Y0      92
#define CARD_STEP    44
#define FOOT_Y       226

/* The splash: how long it runs, how long each fade takes, and how fast
 * it animates. */
#define SPLASH_MS    4200
#define FADE_MS      600
#define SPLASH_TICK  100        /* ms between frames: ten a second */

static ili9341_t s_dev;
static uint16_t *s_fb;          /* 320 x 240 RGB565, in PSRAM */

static hub_display_state_t s_state;   /* guarded by s_lock */
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_version;   /* bumped on every update */

/* The region of the panel that has changed and still has to be pushed. */
static int s_dirty_x0, s_dirty_y0, s_dirty_x1, s_dirty_y1;

/* ------------------------------------------------------------------ */
/* The framebuffer                                                      */
/* ------------------------------------------------------------------ */

static void mark_dirty(int x, int y, int w, int h)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (s_dirty_x1 < s_dirty_x0) {
        s_dirty_x0 = x; s_dirty_y0 = y;
        s_dirty_x1 = x + w - 1; s_dirty_y1 = y + h - 1;
        return;
    }
    if (x < s_dirty_x0) { s_dirty_x0 = x; }
    if (y < s_dirty_y0) { s_dirty_y0 = y; }
    if (x + w - 1 > s_dirty_x1) { s_dirty_x1 = x + w - 1; }
    if (y + h - 1 > s_dirty_y1) { s_dirty_y1 = y + h - 1; }
}

static inline void fb_px(int x, int y, uint16_t c)
{
    if ((unsigned)x >= FB_W || (unsigned)y >= FB_H) {
        return;
    }
    s_fb[(size_t)y * FB_W + x] = c;
}

static void fb_fill(int x, int y, int w, int h, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > FB_W) { w = FB_W - x; }
    if (y + h > FB_H) { h = FB_H - y; }
    for (int j = 0; j < h; j++) {
        uint16_t *row = &s_fb[(size_t)(y + j) * FB_W + x];
        for (int i = 0; i < w; i++) {
            row[i] = c;
        }
    }
    mark_dirty(x, y, w, h);
}

static void fb_hline(int x, int y, int w, uint16_t c)
{
    fb_fill(x, y, w, 1, c);
}

static void fb_vline(int x, int y, int h, uint16_t c)
{
    fb_fill(x, y, 1, h, c);
}

static void fb_rect(int x, int y, int w, int h, uint16_t c)
{
    fb_hline(x, y, w, c);
    fb_hline(x, y + h - 1, w, c);
    fb_vline(x, y, h, c);
    fb_vline(x + w - 1, y, h, c);
}

/* Blend two colours.  t = 0 gives a, t = 1 gives b. */
static uint16_t blend(uint16_t a, uint16_t b, float t)
{
    if (t <= 0.0f) { return a; }
    if (t >= 1.0f) { return b; }
    const int ar = (a >> 11) & 0x1F, ag = (a >> 5) & 0x3F, ab = a & 0x1F;
    const int br = (b >> 11) & 0x1F, bg = (b >> 5) & 0x3F, bb = b & 0x1F;
    const int f = (int)(t * 256.0f);
    const int r = (ar * (256 - f) + br * f) >> 8;
    const int g = (ag * (256 - f) + bg * f) >> 8;
    const int bl = (ab * (256 - f) + bb * f) >> 8;
    return (uint16_t)(((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (bl & 0x1F));
}

/* A filled rectangle with rounded corners. */
static void fb_round_fill(int x, int y, int w, int h, int r, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (r <= 0) {
        fb_fill(x, y, w, h, c);
        return;
    }
    if (r > w / 2) { r = w / 2; }
    if (r > h / 2) { r = h / 2; }
    fb_fill(x + r, y, w - 2 * r, h, c);
    fb_fill(x, y + r, r, h - 2 * r, c);
    fb_fill(x + w - r, y + r, r, h - 2 * r, c);

    /* The four corner discs. */
    const int cx[4] = { x + r, x + w - 1 - r, x + r, x + w - 1 - r };
    const int cy[4] = { y + r, y + r, y + h - 1 - r, y + h - 1 - r };
    for (int k = 0; k < 4; k++) {
        for (int dx = 0; dx < r; dx++) {
            for (int dy = 0; dy < r; dy++) {
                const int px = cx[k] + ((k % 2) ? (r - 1 - dx) : dx);
                const int py = cy[k] + ((k / 2) ? (r - 1 - dy) : dy);
                const int ex = px - cx[k];
                const int ey = py - cy[k];
                if (ex * ex + ey * ey <= r * r) {
                    fb_px(px, py, c);
                }
            }
        }
    }
    mark_dirty(x, y, w, h);
}

/* An outlined rectangle with rounded corners. */
static void fb_round_rect(int x, int y, int w, int h, int r, uint16_t c)
{
    if (w <= 0 || h <= 0) {
        return;
    }
    if (r <= 0) {
        fb_rect(x, y, w, h, c);
        return;
    }
    if (r > w / 2) { r = w / 2; }
    if (r > h / 2) { r = h / 2; }
    fb_hline(x + r, y, w - 2 * r, c);
    fb_hline(x + r, y + h - 1, w - 2 * r, c);
    fb_vline(x, y + r, h - 2 * r, c);
    fb_vline(x + w - 1, y + r, h - 2 * r, c);

    const int cx[4] = { x + r, x + w - 1 - r, x + r, x + w - 1 - r };
    const int cy[4] = { y + r, y + r, y + h - 1 - r, y + h - 1 - r };
    for (int k = 0; k < 4; k++) {
        for (int dx = 0; dx < r; dx++) {
            for (int dy = 0; dy < r; dy++) {
                const int px = cx[k] + ((k % 2) ? (r - 1 - dx) : dx);
                const int py = cy[k] + ((k / 2) ? (r - 1 - dy) : dy);
                const int ddx = px - cx[k];
                const int ddy = py - cy[k];
                const int d2 = ddx * ddx + ddy * ddy;
                if (d2 <= r * r && d2 >= (r - 1) * (r - 1)) {
                    fb_px(px, py, c);
                }
            }
        }
    }
    mark_dirty(x, y, w, h);
}

/* Fade the whole framebuffer towards one colour.  t = 0 leaves it
 * alone, t = 1 washes it out completely. */
static void fb_fade(uint16_t towards, float t)
{
    if (t <= 0.0f) {
        return;
    }
    if (t > 1.0f) { t = 1.0f; }
    const int f = (int)(t * 256.0f);
    const uint16_t tr = (towards >> 11) & 0x1F;
    const uint16_t tg = (towards >> 5) & 0x3F;
    const uint16_t tb = towards & 0x1F;
    for (size_t i = 0; i < (size_t)FB_W * FB_H; i++) {
        const uint16_t v = s_fb[i];
        const int vr = (v >> 11) & 0x1F, vg = (v >> 5) & 0x3F, vb = v & 0x1F;
        const int r = (vr * (256 - f) + tr * f) >> 8;
        const int g = (vg * (256 - f) + tg * f) >> 8;
        const int b = (vb * (256 - f) + tb * f) >> 8;
        s_fb[i] = (uint16_t)(((r & 0x1F) << 11) | ((g & 0x3F) << 5) | (b & 0x1F));
    }
    mark_dirty(0, 0, FB_W, FB_H);
}

/* ------------------------------------------------------------------ */
/* Text                                                                 */
/* ------------------------------------------------------------------ */

static int fb_text_w(const char *text, uint8_t scale)
{
    if (scale == 0) { scale = 1; }
    const int n = (int)strlen(text);
    if (n == 0) { return 0; }
    return n * (FONT5X7_WIDTH + 1) * scale - scale;
}

static void fb_text(int x, int y, const char *text, uint16_t c, uint8_t scale)
{
    if (scale == 0) { scale = 1; }
    int cursor = x;
    for (const char *p = text; *p; p++) {
        unsigned char ch = (unsigned char)*p;
        if (ch < FONT5X7_FIRST || ch > FONT5X7_LAST) {
            ch = '?';
        }
        const uint8_t *glyph = s_font5x7[ch - FONT5X7_FIRST];
        for (int col = 0; col < FONT5X7_WIDTH; col++) {
            const uint8_t bits = glyph[col];
            if (!bits) { continue; }
            for (int row = 0; row < FONT5X7_HEIGHT; row++) {
                if (bits & (1 << row)) {
                    fb_fill(cursor + col * scale, y + row * scale,
                            scale, scale, c);
                }
            }
        }
        cursor += (FONT5X7_WIDTH + 1) * scale;
    }
}

static void fb_text_centre(int y, const char *text, uint16_t c, uint8_t scale)
{
    fb_text((FB_W - fb_text_w(text, scale)) / 2, y, text, c, scale);
}

/* ------------------------------------------------------------------ */
/* The splash                                                           */
/* ------------------------------------------------------------------ */

#define WAVE_BARS 36
#define WAVE_STEP 7
#define WAVE_X0   ((FB_W - (WAVE_BARS * WAVE_STEP - 3)) / 2)
#define WAVE_Y    84
#define WAVE_MAX  26

/* A scrolling waveform: the shape of sound arriving at the mic. */
static void draw_waveform(int frame)
{
    const float t = (float)frame * 0.18f;
    for (int i = 0; i < WAVE_BARS; i++) {
        const float p = t + i * 0.42f;
        const float a = 0.5f + 0.5f * sinf(p * 1.7f);
        const float b = 0.5f + 0.5f * sinf(p * 0.53f + 1.7f);
        const float h = (float)WAVE_MAX * (0.18f + 0.82f * a * b);
        const int bh = (int)h;
        const int x = WAVE_X0 + i * WAVE_STEP;
        fb_fill(x, WAVE_Y - bh, 4, bh, C_ACCENT);
        fb_fill(x, WAVE_Y + 1, 4, bh, C_ACCENT_DIM);
    }
}

static const char *const s_boot_steps[] = {
    "starting the display",
    "the classifier is loaded",
    "the radio is listening",
    "bluetooth is advertising",
    "searching for the cots",
};

static void draw_splash(int64_t elapsed_ms, int frame)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    draw_waveform(frame);

    /* The name, breathing a little. */
    const float pulse = 0.5f + 0.5f * sinf((float)frame * 0.12f);
    fb_text_centre(126, "CRYNET", blend(C_TEXT, C_ACCENT, 0.25f + 0.35f * pulse), 4);
    fb_text_centre(164, "INFANT CRY MONITOR", C_DIM, 1);

    /* The boot steps and a progress bar that fills as they go. */
    int step = (int)(elapsed_ms / (SPLASH_MS / 5));
    if (step > 4) { step = 4; }
    fb_text_centre(190, s_boot_steps[step], C_ACCENT, 1);

    const int bar_x = 90, bar_w = 140, bar_y = 206;
    const float prog = (float)elapsed_ms / (float)SPLASH_MS;
    int filled = (int)(bar_w * (prog > 1.0f ? 1.0f : prog));
    fb_fill(bar_x, bar_y, bar_w, 6, C_SURFACE_HI);
    if (filled > 0) {
        fb_fill(bar_x, bar_y, filled, 6, C_ACCENT);
    }
    fb_rect(bar_x - 1, bar_y - 1, bar_w + 2, 8, C_BORDER);

    fb_text_centre(222, "esp32-s3 hub", C_DIM, 1);
}

/* ------------------------------------------------------------------ */
/* The dashboard                                                        */
/* ------------------------------------------------------------------ */

/* A small status pill: a dot and a word. */
static void draw_pill(int x, int y, const char *label, bool good)
{
    const uint16_t col = good ? C_GREEN : C_DIM;
    fb_fill(x, y + 2, 6, 6, col);
    fb_text(x + 10, y, label, col, 1);
}

/* The same, but with the colour chosen by the caller — the caregiver's
 * device has three states, not two: attached, waiting to be attached,
 * and the Bluetooth stack itself down. */
static void draw_pill_col(int x, int y, const char *label, uint16_t col)
{
    fb_fill(x, y + 2, 6, 6, col);
    fb_text(x + 10, y, label, col, 1);
}

static void draw_level_bar(int x, int y, int w, int h, float level, bool crying)
{
    fb_fill(x, y, w, h, C_SURFACE_HI);
    /* The bar is sqrt-scaled: a quiet room still shows a sliver, the
     * 0.030 trigger lands about a third of the way up, and a loud cry
     * reaches the end.  A linear bar would sit empty until the room
     * got very loud indeed. */
    float v = level;
    if (v < 0.0f) { v = 0.0f; }
    if (v > 1.0f) { v = 1.0f; }
    int fill_w = (int)(sqrtf(v) * (float)(w - 2) + 0.5f);
    uint16_t col = C_GREEN;
    if (crying) {
        col = C_ALERT;
    } else if (level >= 0.030f) {
        col = C_AMBER;
    }
    if (fill_w > 0) {
        fb_fill(x + 1, y + 1, fill_w, h - 2, col);
    }
    fb_rect(x, y, w, h, C_BORDER);
}

static void draw_dashboard(const hub_display_state_t *st)
{
    fb_fill(0, 0, FB_W, FB_H, C_BG);

    /* ---- the header ---- */
    fb_fill(0, 0, FB_W, HEADER_H, C_SURFACE);
    fb_text(12, 8, "CRYNET", C_ACCENT, 2);
    fb_text(90, 12, "S3 HUB", C_DIM, 1);
    draw_pill(196, 11, "RADIO", st->linked);
    /* The caregiver's device — the phone, or the wearable, which uses the
     * same GATT service — is the other half of the system, so its state
     * belongs on the panel: green when one is connected and subscribed,
     * amber when the stack is up but nobody has attached yet, dim when
     * Bluetooth itself is down. */
    const uint16_t phone_col = (st->ble_clients > 0) ? C_GREEN
                             : (st->ble_ready ? C_AMBER : C_DIM);
    draw_pill_col(258, 11, "PHONE", phone_col);
    fb_fill(0, HEADER_H, FB_W, 2, C_ACCENT_DIM);

    /* ---- the banner: what the system is doing ---- */
    uint16_t banner_col = C_DIM;
    const char *banner = "SEARCHING FOR THE COTS";
    if (st->crying) {
        banner = "CRY DETECTED";
        banner_col = C_ALERT;
    } else if (st->linked) {
        banner = "LISTENING";
        banner_col = C_ACCENT;
    }
    fb_round_fill(BANNER_X, BANNER_Y, BANNER_W, BANNER_H, 8,
                  blend(C_SURFACE, banner_col, 0.12f));
    fb_round_rect(BANNER_X, BANNER_Y, BANNER_W, BANNER_H, 8,
                  blend(C_BORDER, banner_col, st->crying ? 0.85f : 0.25f));
    /* A short bar of the state colour down the left edge. */
    fb_fill(BANNER_X + 3, BANNER_Y + 10, 3, BANNER_H - 20, banner_col);
    fb_text(BANNER_X + 16, BANNER_Y + 9, banner, banner_col, 2);

    char right[24];
    if (st->crying) {
        snprintf(right, sizeof right, "COT %u  %u%%", st->cot_id,
                 st->confidence);
    } else if (st->linked) {
        snprintf(right, sizeof right, "%.3f", (double)st->level);
    } else {
        snprintf(right, sizeof right, "--");
    }
    fb_text(BANNER_X + BANNER_W - 12 - fb_text_w(right, 1), BANNER_Y + 26,
            right, C_DIM, 1);

    /* A cry that nobody is attached to hear goes nowhere, and the
     * caregiver has to know that before they go looking for their
     * phone. */
    if (st->crying && st->ble_clients == 0) {
        fb_text(BANNER_X + 16, BANNER_Y + 26, "ALERT NOT DELIVERED",
                C_AMBER, 1);
    }

    /* ---- a card for every cot ---- */
    const int count = st->node_count > HUB_DISPLAY_MAX_NODES
                    ? HUB_DISPLAY_MAX_NODES : st->node_count;
    unsigned online = 0;
    for (int i = 0; i < count; i++) {
        const int y = CARD_Y0 + i * CARD_STEP;
        const hub_display_node_t *n = &st->nodes[i];
        const bool known = n->online;
        const uint16_t accent = n->crying ? C_ALERT
                             : (known ? C_ACCENT : C_BORDER);

        if (known) {
            online++;
        }

        fb_round_fill(CARD_X, y, CARD_W, CARD_H, 6,
                      blend(C_SURFACE, accent, n->crying ? 0.16f : 0.05f));
        fb_round_rect(CARD_X, y, CARD_W, CARD_H, 6,
                      blend(C_BORDER, accent, known ? 0.45f : 0.0f));

        char name[8];
        snprintf(name, sizeof name, "COT %u", (unsigned)(i + 1));
        fb_text(CARD_X + 14, y + 8, name, known ? C_TEXT : C_DIM, 2);

        const char *state;
        uint16_t state_col;
        if (n->crying) {
            snprintf(right, sizeof right, "CRY %u%%", (unsigned)n->confidence);
            state = right;
            state_col = C_ALERT;
        } else if (known) {
            state = "ONLINE";
            state_col = C_GREEN;
        } else {
            state = "NO SIGNAL";
            state_col = C_DIM;
        }
        fb_text(CARD_X + CARD_W - 14 - fb_text_w(state, 1), y + 11, state,
                state_col, 1);

        draw_level_bar(CARD_X + 14, y + 28, CARD_W - 28, 7,
                       known ? n->level : 0.0f, n->crying);
    }

    /* ---- the footer ----
     * The footer counts the cots that are actually answering, not the
     * cards on the screen.  A card for a cot that has gone quiet reads
     * NO SIGNAL, so "3 cots linked" printed above two NO SIGNAL cards
     * would be a lie — and the panel is the one place the caregiver is
     * certain to look. */
    char foot[40];
    if (online == 0) {
        snprintf(foot, sizeof foot, "no cots linked");
    } else {
        snprintf(foot, sizeof foot, "%u cot%s linked", online,
                 online == 1 ? "" : "s");
    }
    fb_text(12, FOOT_Y, foot, C_DIM, 1);

    char up[24];
    const uint32_t up_s = st->uptime_s;
    snprintf(up, sizeof up, "up %u:%02u", (unsigned)(up_s / 60),
             (unsigned)(up_s % 60));
    fb_text(FB_W - 12 - fb_text_w(up, 1), FOOT_Y, up, C_DIM, 1);
}

/* ------------------------------------------------------------------ */
/* The task                                                             */
/* ------------------------------------------------------------------ */

static void flush_dirty(void)
{
    if (s_dirty_x1 < s_dirty_x0) {
        return;
    }
    const int x = s_dirty_x0, y = s_dirty_y0;
    const int w = s_dirty_x1 - s_dirty_x0 + 1;
    const int h = s_dirty_y1 - s_dirty_y0 + 1;
    s_dirty_x0 = FB_W; s_dirty_y0 = FB_H;
    s_dirty_x1 = -1; s_dirty_y1 = -1;
    ili9341_blit(&s_dev, x, y, w, h, &s_fb[(size_t)y * FB_W + x], FB_W);
}

static void display_task(void *arg)
{
    const TickType_t t0 = xTaskGetTickCount();
    uint32_t seen = 0;
    int frame = 0;
    TickType_t last_dash = 0;

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(SPLASH_TICK));

        hub_display_state_t st;
        uint32_t version;
        portENTER_CRITICAL(&s_lock);
        st = s_state;
        version = s_version;
        portEXIT_CRITICAL(&s_lock);

        const TickType_t now = xTaskGetTickCount();
        const int64_t ms = (int64_t)(now - t0) * portTICK_PERIOD_MS;

        if (ms < SPLASH_MS) {
            draw_splash(ms, frame++);
            flush_dirty();
        } else if (ms < SPLASH_MS + FADE_MS) {
            draw_splash(ms, frame++);
            fb_fade(C_BG, (float)(ms - SPLASH_MS) / (float)FADE_MS);
            flush_dirty();
        } else if (ms < SPLASH_MS + 2 * FADE_MS) {
            draw_dashboard(&st);
            fb_fade(C_BG, 1.0f - (float)(ms - SPLASH_MS - FADE_MS) /
                            (float)FADE_MS);
            flush_dirty();
        } else if (version != seen ||
                   ((now - last_dash) * portTICK_PERIOD_MS) > 1000) {
            seen = version;
            last_dash = now;
            draw_dashboard(&st);
            flush_dirty();
        }
    }
}

bool hub_display_start(void)
{
    if (!ili9341_init(&s_dev, PIN_MOSI, PIN_SCLK, PIN_CS, PIN_DC, PIN_RST,
                      PIN_BL, ROTATION_LANDSCAPE)) {
        return false;
    }

    /* The framebuffer.  320 x 240 RGB565 is 150 KB, which is more than
     * the hub has to spare in internal RAM, so it lives in PSRAM. */
    s_fb = heap_caps_malloc((size_t)FB_W * FB_H * sizeof(uint16_t),
                             MALLOC_CAP_SPIRAM);
    if (s_fb == NULL) {
        ESP_LOGE(TAG, "there is no room for the framebuffer");
        return false;
    }
    memset(s_fb, 0, (size_t)FB_W * FB_H * sizeof(uint16_t));

    s_dirty_x0 = FB_W; s_dirty_y0 = FB_H;
    s_dirty_x1 = -1; s_dirty_y1 = -1;

    /* Core 1: the link loop and both radio stacks run on core 0, and a
     * 30 ms SPI burst must not delay a window analysis. */
    if (xTaskCreatePinnedToCore(display_task, "hubdisp", 4096, NULL,
                                3, NULL, 1) != pdPASS) {
        return false;
    }
    ESP_LOGI(TAG, "the display is up: %d x %d", FB_W, FB_H);
    return true;
}

void hub_display_update(const hub_display_state_t *state)
{
    portENTER_CRITICAL(&s_lock);
    s_state = *state;
    s_version++;
    portEXIT_CRITICAL(&s_lock);
}
