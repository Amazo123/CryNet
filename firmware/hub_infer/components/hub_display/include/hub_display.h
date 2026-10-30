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

/* The display's own state. */
typedef struct {
    bool     linked;        /* a node has been heard from */
    bool     crying;        /* the hub is announcing a cry */
    uint8_t  cot_id;        /* which cot */
    uint8_t  confidence;    /* the last confirmed confidence, in percent */
    float    level;         /* the node's last RMS, 0..1 */
} hub_display_state_t;

/* Start the display and its refresh task.  Returns false if the panel
 * did not answer; the hub carries on without it. */
bool hub_display_start(void);

/* Give the display something new to show. */
void hub_display_update(const hub_display_state_t *state);

#ifdef __cplusplus
}
#endif

#endif /* HUB_DISPLAY_H */
