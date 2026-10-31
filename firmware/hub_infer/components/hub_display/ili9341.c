/*
 * A small ILI9341 driver for ESP-IDF.
 *
 * The ESP-IDF's esp_lcd ships drivers for the ST7789 and the SSD1306 but
 * not for this panel, so this is the ILI9341 brought up directly on the
 * SPI master driver: the address window and the pixel stream are the
 * only two things it has to do.
 *
 * Three things about the ILI9341's serial interface are easy to get
 * wrong, and all three of them are fixed here:
 *
 *   1. **CS must stay down across a command and its parameters.**  The
 *      panel resets its serial interface when CS goes high, so a
 *      command byte and the bytes that follow it have to be one
 *      continuous transfer.  The ESP-IDF's `SPI_TRANS_CS_KEEP_ACTIVE`
 *      does exactly that, and the bus has to be acquired for it to be
 *      allowed.
 *   2. **D/C is the only thing that tells a command from data.**  The
 *      level is changed in the transaction's pre-transmission callback,
 *      which the driver calls once CS is asserted and just before the
 *      bytes go out — the only moment at which it is safe to change it.
 *   3. **The address window is big-endian, and it is one command per
 *      axis.**  CASET takes four bytes (start column, end column) and
 *      PASET takes four bytes (start row, end row).  Sending the column
 *      address twice — once for the start and once for the end —
 *      instead re-sets the start, and the panel ends up with a window
 *      of one pixel and displays uninitialised memory.
 *   4. **The colour order is set by one bit in MADCTL.**  The BGR bit
 *      tells the panel that the top bits of each RGB565 word are blue.
 *      The framebuffer holds red there, so leaving BGR set swaps red
 *      and blue on the glass: the teal accent came out olive, and the
 *      amber "no phone" pill came out blue.  The bit is cleared here.
 *
 * The orientation is a property of *this* panel, not of the chip: it is
 * a "landscape-first" 320x240 glass, so the upright landscape setting
 * is `MADCTL_MY` with a 320x240 logical framebuffer — the same thing
 * the legacy firmware used, via Adafruit's rotation 2 with its 240 px
 * clipping overridden.  Getting this wrong rotates the whole picture
 * by a quarter turn, which is exactly what happened the first time.
 */

#include "ili9341.h"

#include <string.h>

#include "driver/gpio.h"
#include "driver/ledc.h"
#include "driver/spi_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "ili9341";

/* The panel's commands. */
#define ILI9341_SWRESET  0x01
#define ILI9341_SLPOUT   0x11
#define ILI9341_INVOFF   0x20
#define ILI9341_DISPON   0x29
#define ILI9341_CASET    0x2A
#define ILI9341_RAMWR    0x2C
#define ILI9341_PASET    0x2B
#define ILI9341_MADCTL   0x36
#define ILI9341_PIXFMT   0x3A

/* Memory access control. */
#define MADCTL_MX  0x40
#define MADCTL_MY  0x80
#define MADCTL_MV  0x20
#define MADCTL_BGR 0x08

/* The backlight.  It used to be a plain on/off pin, and the panel was
 * left at full brightness.  A TFT at full brightness in a dark room
 * glares: the picture is blown out, the dark navy background reads as a
 * bright blue, and the teal accent is washed out with it.  The pin is
 * now a LEDC output, so the brightness is a number that can be turned
 * down.  5 kHz is above anything the eye can notice as a flicker. */
#define BL_MODE      LEDC_LOW_SPEED_MODE
#define BL_TIMER     LEDC_TIMER_0
#define BL_CHANNEL   LEDC_CHANNEL_0
#define BL_FREQ_HZ   5000
#define BL_RES       LEDC_TIMER_10_BIT
#define BL_STEPS     (1u << BL_RES)

/* The init sequence, in Adafruit's "command, count, data" format. */
static const uint8_t s_init[] = {
    0xEF, 3, 0x03, 0x80, 0x02,
    0xCF, 3, 0x00, 0xC1, 0x30,
    0xED, 4, 0x64, 0x03, 0x12, 0x81,
    0xE8, 3, 0x85, 0x00, 0x78,
    0xCB, 5, 0x39, 0x2C, 0x00, 0x34, 0x02,
    0xF7, 1, 0x20,
    0xEA, 2, 0x00, 0x00,
    0xC0, 1, 0x23,              /* power control 1 */
    0xC1, 1, 0x10,              /* power control 2 */
    0xC5, 2, 0x3e, 0x28,        /* VCM control */
    0xC7, 1, 0x86,              /* VCM control 2 */
    ILI9341_MADCTL, 1, 0x40,    /* memory access control: the rotation
                                 * is written again below, once the
                                 * orientation is known */
    0xB6, 1, 0x00,              /* display function control */
    0xF2, 1, 0x00,              /* 3 gamma function disable */
    0x26, 1, 0x01,              /* gamma set */
    0xE0, 15, 0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08,
              0x4E, 0xF1, 0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00,
    0xE1, 15, 0x00, 0x0E, 0x14, 0x03, 0x11, 0x07,
              0x31, 0xC1, 0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F,
    ILI9341_SLPOUT, 0x80,       /* sleep out */
    ILI9341_DISPON, 0x80,       /* display on */
};

/* The D/C line: the level the next transaction drives it to.  The SPI
 * driver reads it in the pre-transmission callback, which runs inside
 * the driver with the CS line already down. */
static void dc_pre_cb(spi_transaction_t *t)
{
    ili9341_t *dev = (ili9341_t *)t->user;
    gpio_set_level((gpio_num_t)dev->dc_pin, dev->dc_level ? 1 : 0);
}

/* Send bytes with D/C at the given level.  With keep_cs the chip select
 * stays down afterwards, so the next call continues the same transfer. */
static void tx(ili9341_t *dev, uint8_t dc, const uint8_t *buf, size_t len,
               bool keep_cs)
{
    dev->dc_level = dc;
    spi_transaction_t t = {
        .length = len * 8,
        .tx_buffer = buf,
        .user = dev,
    };
    if (keep_cs) {
        t.flags |= SPI_TRANS_CS_KEEP_ACTIVE;
    }
    spi_device_polling_transmit(dev->spi, &t);
}

/* A command, and the parameters that belong to it, in one transfer. */
static void write_command_data(ili9341_t *dev, uint8_t cmd,
                               const uint8_t *data, size_t len)
{
    spi_device_acquire_bus(dev->spi, portMAX_DELAY);
    tx(dev, 0, &cmd, 1, len > 0);
    if (len) {
        tx(dev, 1, data, len, false);
    }
    spi_device_release_bus(dev->spi);
}

bool ili9341_init(ili9341_t *dev, int mosi, int sclk, int cs, int dc,
                   int rst, int backlight, uint8_t rotation)
{
    memset(dev, 0, sizeof *dev);
    dev->dc_pin = dc;
    dev->reset_pin = rst;
    dev->backlight_pin = backlight;

    gpio_config_t out = {
        .pin_bit_mask = (1ULL << dc) | (1ULL << rst),
        .mode = GPIO_MODE_OUTPUT,
    };
    ESP_ERROR_CHECK(gpio_config(&out));

    /* The panel's reset line. */
    gpio_set_level((gpio_num_t)rst, 1);
    vTaskDelay(pdMS_TO_TICKS(10));
    gpio_set_level((gpio_num_t)rst, 0);
    vTaskDelay(pdMS_TO_TICKS(20));
    gpio_set_level((gpio_num_t)rst, 1);
    vTaskDelay(pdMS_TO_TICKS(150));

    spi_bus_config_t bus = {
        .mosi_io_num = mosi,
        .miso_io_num = -1,
        .sclk_io_num = sclk,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = 4096,
    };
    esp_err_t err = spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_CH_AUTO);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "the SPI bus could not be started: %s",
                 esp_err_to_name(err));
        return false;
    }

    spi_device_interface_config_t iface = {
        .clock_speed_hz = 40 * 1000 * 1000,
        .mode = 0,
        .spics_io_num = cs,
        .queue_size = 7,
        .pre_cb = dc_pre_cb,
    };
    err = spi_bus_add_device(SPI2_HOST, &iface, &dev->spi);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "the display could not be added to the bus: %s",
                 esp_err_to_name(err));
        return false;
    }

    /* The init sequence. */
    for (size_t i = 0; i < sizeof s_init;) {
        const uint8_t cmd = s_init[i++];
        const uint8_t count = s_init[i++];
        if (count == 0x80) {
            /* A command with no data, and a pause after it. */
            write_command_data(dev, cmd, NULL, 0);
            vTaskDelay(pdMS_TO_TICKS(120));
            continue;
        }
        write_command_data(dev, cmd, &s_init[i], count);
        i += count;
    }

    /* The rotation.  On this panel the upright landscape setting is
     * MADCTL_MY with a 320x240 logical framebuffer — see the note at
     * the top of this file.
     *
     * MADCTL_BGR is deliberately NOT set.  It would tell the panel that
     * the top bits of each RGB565 word are blue; the framebuffer puts
     * red there, so the picture would arrive with red and blue
     * exchanged — the teal accent olive, the amber pill blue.  The
     * picture in the first photograph of the panel proved it. */
    uint8_t madctl;
    switch (rotation & 3) {
    case 0:  madctl = MADCTL_MX; dev->width = 240; dev->height = 320; break;
    case 1:  madctl = MADCTL_MV; dev->width = 320; dev->height = 240; break;
    case 2:  madctl = MADCTL_MY; dev->width = 320; dev->height = 240; break;
    default: madctl = MADCTL_MX | MADCTL_MY | MADCTL_MV;
             dev->width = 320; dev->height = 240; break;
    }
    write_command_data(dev, ILI9341_MADCTL, &madctl, 1);

    /* Pin the inversion state.  The chip's default after a reset is
     * already "inversion off", but saying so explicitly means the
     * picture cannot depend on what the last user of this glass left
     * in the controller. */
    write_command_data(dev, ILI9341_INVOFF, NULL, 0);

    const uint8_t fmt = 0x55;      /* 16 bits per pixel */
    write_command_data(dev, ILI9341_PIXFMT, &fmt, 1);

    dev->rotation = rotation;

    ili9341_backlight(dev, true);
    ESP_LOGI(TAG, "the panel is up: %d x %d, rotation %d (madctl 0x%02X)",
             dev->width, dev->height, rotation, madctl);
    return true;
}

void ili9341_backlight(ili9341_t *dev, bool on)
{
    ili9341_backlight_set(dev, on ? 100 : 0);
}

void ili9341_backlight_set(ili9341_t *dev, uint8_t percent)
{
    if (dev->backlight_pin < 0) {
        return;
    }
    if (percent > 100) {
        percent = 100;
    }

    /* The first call sets the pin up as a LEDC output; after that the
     * duty alone sets the brightness.  If the LEDC cannot be had the
     * pin stays a plain output, so the panel is still lit. */
    static bool configured = false;
    if (!configured) {
        configured = true;
        ledc_timer_config_t timer = {
            .speed_mode = BL_MODE,
            .duty_resolution = BL_RES,
            .timer_num = BL_TIMER,
            .freq_hz = BL_FREQ_HZ,
            .clk_cfg = LEDC_USE_APB_CLK,
        };
        ledc_channel_config_t channel = {
            .gpio_num = dev->backlight_pin,
            .speed_mode = BL_MODE,
            .channel = BL_CHANNEL,
            .timer_sel = BL_TIMER,
            .duty = 0,
            .hpoint = 0,
            .sleep_mode = LEDC_SLEEP_MODE_NO_ALIVE_NO_PD,
        };
        if (ledc_timer_config(&timer) != ESP_OK) {
            ESP_LOGE(TAG, "the backlight timer could not be set up");
            configured = false;
        } else if (ledc_channel_config(&channel) != ESP_OK) {
            ESP_LOGE(TAG, "the backlight channel could not be set up");
            configured = false;
        }
        if (!configured) {
            gpio_config_t out = {
                .pin_bit_mask = 1ULL << dev->backlight_pin,
                .mode = GPIO_MODE_OUTPUT,
            };
            gpio_config(&out);
            gpio_set_level((gpio_num_t)dev->backlight_pin, percent ? 1 : 0);
            return;
        }
    }

    /* The backlight's polarity was never settled in the legacy firmware:
     * its diagnostic toggled the pin and asked the user which way was
     * right.  Driving it high is the usual wiring, and the panel was
     * lit when the pin was high. */
    const uint32_t duty = (percent == 0) ? 0 : (BL_STEPS * percent) / 100;
    ledc_set_duty(BL_MODE, BL_CHANNEL, duty);
    ledc_update_duty(BL_MODE, BL_CHANNEL);
}

/* Point the panel's address window at a rectangle.  The caller must be
 * holding the bus. */
static void set_window(ili9341_t *dev, int x, int y, int w, int h)
{
    const uint16_t x0 = (uint16_t)x;
    const uint16_t x1 = (uint16_t)(x + w - 1);
    const uint16_t y0 = (uint16_t)y;
    const uint16_t y1 = (uint16_t)(y + h - 1);
    const uint8_t cols[4] = {
        (uint8_t)(x0 >> 8), (uint8_t)(x0 & 0xFF),
        (uint8_t)(x1 >> 8), (uint8_t)(x1 & 0xFF),
    };
    const uint8_t rows[4] = {
        (uint8_t)(y0 >> 8), (uint8_t)(y0 & 0xFF),
        (uint8_t)(y1 >> 8), (uint8_t)(y1 & 0xFF),
    };
    const uint8_t cmd_caset = ILI9341_CASET;
    const uint8_t cmd_paset = ILI9341_PASET;
    tx(dev, 0, &cmd_caset, 1, true);
    tx(dev, 1, cols, 4, true);
    tx(dev, 0, &cmd_paset, 1, true);
    tx(dev, 1, rows, 4, true);
}

void ili9341_fill(ili9341_t *dev, int x, int y, int w, int h, uint16_t colour)
{
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > dev->width)  { w = dev->width - x; }
    if (y + h > dev->height) { h = dev->height - y; }
    if (w <= 0 || h <= 0) {
        return;
    }

    /* The pixel stream: the same colour, over and over, in one
     * transfer with CS down the whole way. */
    uint8_t chunk[512];
    const uint16_t px = colour;
    for (size_t i = 0; i < sizeof chunk; i += 2) {
        chunk[i] = (uint8_t)(px >> 8);
        chunk[i + 1] = (uint8_t)(px & 0xFF);
    }
    const size_t pixels = (size_t)w * h;
    const size_t chunk_pixels = sizeof chunk / 2;

    spi_device_acquire_bus(dev->spi, portMAX_DELAY);
    set_window(dev, x, y, w, h);
    const uint8_t cmd_ramwr = ILI9341_RAMWR;
    tx(dev, 0, &cmd_ramwr, 1, true);
    for (size_t sent = 0; sent < pixels; sent += chunk_pixels) {
        size_t n = pixels - sent;
        if (n > chunk_pixels) {
            n = chunk_pixels;
        }
        const bool last = (sent + n >= pixels);
        tx(dev, 1, chunk, n * 2, !last);
    }
    spi_device_release_bus(dev->spi);
}

void ili9341_blit(ili9341_t *dev, int x, int y, int w, int h,
                   const uint16_t *pixels, size_t stride)
{
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > dev->width)  { w = dev->width - x; }
    if (y + h > dev->height) { h = dev->height - y; }
    if (w <= 0 || h <= 0) {
        return;
    }

    spi_device_acquire_bus(dev->spi, portMAX_DELAY);
    set_window(dev, x, y, w, h);
    const uint8_t cmd_ramwr = ILI9341_RAMWR;
    tx(dev, 0, &cmd_ramwr, 1, true);

    /* The panel wants RGB565 big endian; the framebuffer holds it in
     * the host's order, so each pixel is swapped on the way out. */
    const size_t row_px = (size_t)w;
    uint8_t chunk[512];
    for (int row = 0; row < h; row++) {
        const uint16_t *src = pixels + (size_t)row * stride;
        size_t done = 0;
        while (done < row_px) {
            size_t n = row_px - done;
            if (n * 2 > sizeof chunk) {
                n = sizeof chunk / 2;
            }
            for (size_t i = 0; i < n; i++) {
                const uint16_t px = src[done + i];
                chunk[i * 2] = (uint8_t)(px >> 8);
                chunk[i * 2 + 1] = (uint8_t)(px & 0xFF);
            }
            const bool last = (row == h - 1) && (done + n >= row_px);
            tx(dev, 1, chunk, n * 2, !last);
            done += n;
        }
    }
    spi_device_release_bus(dev->spi);
}
