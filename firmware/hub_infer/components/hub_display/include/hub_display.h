/*
 * CryNet — the hub's display.
 *
 * The hub carries a 2.8" ILI9341 SPI colour display on GPIO 10-14, the
 * wiring the legacy firmware used:
 *
 *   CS 10   MOSI 11   SCK 12   DC 13   RST 14   backlight 4
 *
 * The panel driver is a small ILI9341 implementation for ESP-IDF (the
 * ESP-IDF ships drivers for the ST7789 and the SSD1306, not for this
 * one), and the text uses the classic 5x7 font Adafruit's GFX library
 * has used since 1.0, so the display looks the way the legacy one did.
 *
 * The screen has three faces.  A short animated splash runs first — the
 * waveform, the name, the boot steps — and then the dashboard: the
 * hub's own state at the top, and a card for every cot.  The BOOT
 * button opens and closes a third: the colour check, a grid of the
 * palette's swatches, which is how the panel's own colours are judged
 * (a photograph of a glowing screen in a dark room is not a colour
 * measurement).
 */

#ifndef HUB_DISPLAY_H
#define HUB_DISPLAY_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* RGB565. */
#define DISPLAY_RGB(r, g, b) \
    ((uint16_t)(((r) & 0xF8) << 8 | ((g) & 0xFC) << 3 | ((b) >> 3)))

#define DISPLAY_COLOUR_BLACK  DISPLAY_RGB(0, 0, 0)
#define DISPLAY_COLOUR_WHITE  DISPLAY_RGB(255, 255, 255)
#define DISPLAY_COLOUR_GREY   DISPLAY_RGB(64, 72, 84)
#define DISPLAY_COLOUR_RED    DISPLAY_RGB(220, 40, 40)
#define DISPLAY_COLOUR_GREEN  DISPLAY_RGB(40, 170, 80)
#define DISPLAY_COLOUR_AMBER  DISPLAY_RGB(230, 160, 30)
#define DISPLAY_COLOUR_BLUE   DISPLAY_RGB(30, 90, 200)

/* How many cots the hub knows about. */
#define HUB_DISPLAY_MAX_NODES 3

/* The battery band, from the cell voltage with hysteresis.  The bands
 * follow SYSTEM_WIRING.md 7: normal, low (charge soon), critical
 * (switch off and charge).  NONE means no reading -- USB power, no
 * divider wired, or a node too old to send the field -- and the panel
 * shows nothing for it. */
#define HUB_BAT_NONE     0u
#define HUB_BAT_NORMAL   1u
#define HUB_BAT_LOW      2u
#define HUB_BAT_CRITICAL 3u

/* One cot, as the dashboard shows it. */
typedef struct {
    uint8_t id;            /* 1..3 */
    bool    online;        /* the hub has heard from it */
    bool    crying;        /* the hub is announcing a cry from it */
    float   level;         /* its last RMS */
    uint8_t confidence;    /* the last confirmed confidence, in percent */
    uint16_t battery_mv;   /* its battery cell voltage; 0 = no reading */
    uint8_t battery_band;  /* HUB_BAT_* */
    bool    deaf;          /* the hub cannot get a window from it, so it
                            * cannot announce a cry: it is not being
                            * watched, and the card has to say so */
} hub_display_node_t;

/* The display's own state. */
typedef struct {
    bool     linked;        /* a node has been heard from */
    bool     crying;        /* the hub is announcing a cry */
    uint8_t  cot_id;        /* which cot — the loudest one */
    uint8_t  confidence;    /* the last confirmed confidence, in percent */
    float    level;         /* that cot's last RMS */
    uint8_t  node_count;    /* how many cots the hub knows about */
    bool     ble_ready;     /* the Bluetooth server is advertising */
    uint8_t  ble_clients;   /* caregiver devices connected and subscribed */
    uint32_t uptime_s;      /* how long the hub has been up */
    hub_display_node_t nodes[HUB_DISPLAY_MAX_NODES];
} hub_display_state_t;

/* Start the display and its refresh task.  Returns false if the panel
 * did not answer; the hub carries on without it. */
bool hub_display_start(void);

/* Give the display something new to show. */
void hub_display_update(const hub_display_state_t *state);

/* The backlight's brightness, as a percentage: 0 is off, 100 is full.
 * The panel is not meant to be looked at at full brightness in a dark
 * room — the glare is what makes a colour look like the wrong colour.
 * The default is set at boot; this changes it. */
void hub_display_set_brightness(uint8_t percent);

/* The backlight's brightness, as a percentage. */
uint8_t hub_display_brightness(void);

#ifdef __cplusplus
}
#endif

#endif /* HUB_DISPLAY_H */
