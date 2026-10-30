/*
 * CryNet — the hub's display.  See include/hub_display.h.
 *
 * The public API is deliberately dumb: hub_display_update() just copies
 * the newest state under a spinlock, and a low-priority task on the
 * other core redraws whatever changed.  Only this task ever touches the
 * panel, so the driver needs no locking of its own.
 *
 * The layout, on the 320x240 landscape panel:
 *
 *   CryNet hub                 (title, always)
 *   cot 1 CRY 93%  /  quiet    (the state the hub is announcing)
 *   [####################]     (the node's level, sqrt-scaled)
 *   rms 0.0132                 (the number behind the bar)
 */

#include "hub_display.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "ili9341.h"

/* The panel hangs on the pins the legacy firmware used: CS 10, MOSI 11,
 * SCK 12, DC 13, RST 14, backlight 4. */
#define PIN_MOSI 11
#define PIN_SCLK 12
#define PIN_CS   10
#define PIN_DC   13
#define PIN_RST  14
#define PIN_BL   4

/* One is landscape: the panel is mounted sideways on the hub. */
#define ROTATION_LANDSCAPE 1

#define BAR_X 10
#define BAR_Y 110
#define BAR_W 300
#define BAR_H 24

static ili9341_t s_dev;

static hub_display_state_t s_state;          /* guarded by s_lock */
static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t s_version;          /* bumped on every update */

/* A line of the layout, and what the panel currently shows of it. */
typedef struct {
    char     text[32];
    uint16_t colour;
    bool     drawn;               /* false = the panel needs this line */
} line_t;

static line_t s_main;            /* the cot's state, scale 3 */
static line_t s_foot;            /* the rms readout, scale 2 */
static int      s_bar_w = -1;    /* the bar's fill, in pixels */
static uint16_t s_bar_colour;

/* Mark a line for redraw, but only if what it says actually changed —
 * a redraw is a 30 ms SPI burst, and there is nothing to spend that on
 * when the words are the same. */
static void set_line(line_t *line, const char *text, uint16_t colour)
{
    if (strcmp(line->text, text) != 0 || line->colour != colour) {
        snprintf(line->text, sizeof line->text, "%s", text);
        line->colour = colour;
        line->drawn = false;
    }
}

static void draw_line(line_t *line, int x, int y, uint8_t scale)
{
    /* Erase to the right edge, not just past the new text: a shorter
     * string replacing a longer one would otherwise leave the tail of
     * the old one on the panel. */
    ili9341_fill(&s_dev, x, y, s_dev.width - x, 8 * scale, DISPLAY_COLOUR_BLACK);
    ili9341_text(&s_dev, x, y, line->text, line->colour, scale);
    line->drawn = true;
}

static uint16_t bar_colour(float level)
{
    if (level < 0.05f) {
        return DISPLAY_COLOUR_GREEN;
    }
    if (level < 0.15f) {
        return DISPLAY_COLOUR_AMBER;
    }
    return DISPLAY_COLOUR_RED;
}

/* The bar's fill is sqrt-scaled: a quiet room (rms 0.006) still shows a
 * sliver, the trigger (0.030) lands about a third of the way up, and a
 * loud cry reaches the right-hand end.  A linear bar would sit empty
 * until the room got very loud indeed. */
static void draw_bar(float level)
{
    if (level < 0.0f) {
        level = 0.0f;
    }
    if (level > 1.0f) {
        level = 1.0f;
    }
    const int w = (int)(sqrtf(level) * (float)BAR_W + 0.5f);
    const uint16_t colour = bar_colour(level);
    if (w == s_bar_w && colour == s_bar_colour) {
        return;
    }
    s_bar_w = w;
    s_bar_colour = colour;

    ili9341_fill(&s_dev, BAR_X, BAR_Y, BAR_W, BAR_H, DISPLAY_COLOUR_BLACK);
    if (w > 0) {
        ili9341_fill(&s_dev, BAR_X, BAR_Y, w, BAR_H, colour);
    }
    ili9341_fill(&s_dev, BAR_X, BAR_Y, BAR_W, 1, DISPLAY_COLOUR_GREY);
    ili9341_fill(&s_dev, BAR_X, BAR_Y + BAR_H - 1, BAR_W, 1, DISPLAY_COLOUR_GREY);
}

/* Everything the task composed this tick, onto the panel. */
static void refresh(const hub_display_state_t *st)
{
    if (!s_main.drawn) {
        draw_line(&s_main, 8, 56, 3);
    }
    if (!s_foot.drawn) {
        draw_line(&s_foot, 8, 170, 2);
    }
    draw_bar(st->level);
}

static void display_task(void *arg)
{
    uint32_t seen = (uint32_t)-1;     /* force the first draw */

    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(100));

        hub_display_state_t st;
        uint32_t version;
        portENTER_CRITICAL(&s_lock);
        st = s_state;
        version = s_version;
        portEXIT_CRITICAL(&s_lock);

        if (version == seen) {
            continue;
        }
        seen = version;

        char text[32];
        if (!st.linked) {
            snprintf(text, sizeof text, "listening...");
            set_line(&s_main, text, DISPLAY_COLOUR_GREY);
        } else if (st.crying) {
            snprintf(text, sizeof text, "cot %u CRY %u%%",
                     (unsigned)st.cot_id, (unsigned)st.confidence);
            set_line(&s_main, text, DISPLAY_COLOUR_RED);
        } else {
            snprintf(text, sizeof text, "cot %u quiet", (unsigned)st.cot_id);
            set_line(&s_main, text, DISPLAY_COLOUR_GREEN);
        }
        snprintf(text, sizeof text, "rms %.4f", (double)st.level);
        set_line(&s_foot, text, DISPLAY_COLOUR_GREY);

        refresh(&st);
    }
}

bool hub_display_start(void)
{
    if (!ili9341_init(&s_dev, PIN_MOSI, PIN_SCLK, PIN_CS, PIN_DC, PIN_RST,
                      PIN_BL, ROTATION_LANDSCAPE)) {
        return false;
    }

    /* The static parts: a black screen, the title, the bar's track. */
    ili9341_fill(&s_dev, 0, 0, s_dev.width, s_dev.height, DISPLAY_COLOUR_BLACK);
    ili9341_text(&s_dev, 8, 8, "CryNet hub", DISPLAY_COLOUR_WHITE, 3);
    s_bar_w = -1;
    draw_bar(0.0f);

    /* Core 1: the link loop and both radio stacks run on core 0, and a
     * 30 ms SPI burst must not delay a window analysis. */
    if (xTaskCreatePinnedToCore(display_task, "hubdisp", 4096, NULL,
                                3, NULL, 1) != pdPASS) {
        return false;
    }
    return true;
}

void hub_display_update(const hub_display_state_t *state)
{
    portENTER_CRITICAL(&s_lock);
    s_state = *state;
    s_version++;
    portEXIT_CRITICAL(&s_lock);
}
