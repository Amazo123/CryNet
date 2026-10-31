/*
 * A small ILI9341 driver for ESP-IDF: the panel on the hub.
 */

#ifndef ILI9341_H
#define ILI9341_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "driver/spi_master.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    spi_device_handle_t spi;
    int dc_pin;
    int reset_pin;
    int backlight_pin;
    int width;
    int height;
    uint8_t rotation;
    uint8_t dc_level;     /* the level the next transaction drives D/C to */
} ili9341_t;

/* Bring the panel up.  Returns false if it did not answer. */
bool ili9341_init(ili9341_t *dev, int mosi, int sclk, int cs, int dc,
                   int rst, int backlight, uint8_t rotation);

/* Fill a rectangle with one colour. */
void ili9341_fill(ili9341_t *dev, int x, int y, int w, int h, uint16_t colour);

/* Push a rectangle of RGB565 pixels to the panel.  The pixels are in
 * the host's byte order and are swapped on the way out; `stride` is the
 * distance between one row and the next, in pixels — so a whole screen
 * can be sent in one call. */
void ili9341_blit(ili9341_t *dev, int x, int y, int w, int h,
                   const uint16_t *pixels, size_t stride);

/* The backlight. */
void ili9341_backlight(ili9341_t *dev, bool on);

#ifdef __cplusplus
}
#endif

#endif /* ILI9341_H */
