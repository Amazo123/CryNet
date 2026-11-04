/*
 * CryNet hub — the bench console.
 *
 * The hub has always logged to its UART; this gives it a way to answer
 * as well.  The commands are few and none of them changes how the
 * system behaves:
 *
 *   help         what the console understands
 *   status       the cots: their level, the window they have, their state
 *   alert <cot>  publish a test alert for that cot, as if it had heard
 *                a cry.  The caregiver's phone buzzes; the wearable
 *                shows "a cry on cot N at 100%"
 *   clear        take the test alert back
 *
 * Why it exists: the last unproven link in the system was the
 * Bluetooth one.  The hub published "a cry on cot 1 at 100%" and the
 * wearable was not attached to see it, so the whole path -- publisher,
 * link, client, display -- was untested.  With this command it can be
 * tested at any time, in any room, without a sound.
 *
 * The console reads the same UART the hub logs to, so a command and
 * the log share the port.  That is why the reader is on its own task
 * and why it only ever reads whole lines: a line of log arriving while
 * a command is being typed is discarded, and a command is only acted
 * on when a newline ends it.
 */

#include <stdlib.h>
#include <string.h>

#include "driver/uart.h"
#include "esp_err.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "console.h"
#include "link_stage.h"

static const char *TAG = "console";

/* The longest command the console accepts, and the longest line it
 * will hold while it waits for the newline. */
#define CONSOLE_LINE_MAX 64

/* The cots the status command reports. */
#define CONSOLE_MAX_COTS 8

static void print_help(void)
{
    ESP_LOGI(TAG, "commands:");
    ESP_LOGI(TAG, "  help          this list");
    ESP_LOGI(TAG, "  status        the cots and what they are hearing");
    ESP_LOGI(TAG, "  alert <cot>   publish a test alert for that cot");
    ESP_LOGI(TAG, "  clear         take the test alert back");
}

/* The status command: what the hub knows about each cot. */
static void print_status(void)
{
    link_stage_cot_t cots[CONSOLE_MAX_COTS];
    const int n = link_stage_cots(cots, CONSOLE_MAX_COTS);
    if (n == 0) {
        ESP_LOGI(TAG, "no cot has been heard yet");
        return;
    }
    for (int i = 0; i < n; i++) {
        const link_stage_cot_t *c = &cots[i];
        ESP_LOGI(TAG, "  cot %u: rms %.4f  level %.4f  window %.4f%s  "
                      "confidence %u%%",
                 (unsigned)c->node_id, (double)c->rms, (double)c->level,
                 (double)c->frozen_rms,
                 c->window_full ? " (whole)" : " (filling)",
                 (unsigned)c->confidence);
    }
}

/* Run one line.  The line has already had its newline removed. */
static void run_line(const char *line)
{
    ESP_LOGI(TAG, "<< %s", line);

    if (strcmp(line, "help") == 0 || strcmp(line, "?") == 0) {
        print_help();
        return;
    }
    if (strcmp(line, "status") == 0) {
        print_status();
        return;
    }
    if (strcmp(line, "clear") == 0) {
        link_stage_test_clear();
        return;
    }
    if (strncmp(line, "alert", 5) == 0) {
        const char *arg = line + 5;
        while (*arg == ' ') {
            arg++;
        }
        if (*arg == '\0') {
            ESP_LOGW(TAG, "alert needs a cot number: alert 1");
            return;
        }
        const int cot = atoi(arg);
        if (cot < 1 || cot > 8) {
            ESP_LOGW(TAG, "a cot is numbered 1 to 8, not %d", cot);
            return;
        }
        link_stage_test_alert((uint8_t)cot);
        return;
    }
    ESP_LOGW(TAG, "unknown command: %s", line);
}

/* The console task. */
static void console_task(void *arg)
{
    (void)arg;
    char line[CONSOLE_LINE_MAX];
    int len = 0;

    ESP_LOGI(TAG, "the console is listening: help, status, alert <cot>, clear");

    for (;;) {
        uint8_t c;
        /* A short wait, so the task does not spin on a quiet line. */
        const int n = uart_read_bytes(UART_NUM_0, &c, 1, pdMS_TO_TICKS(50));
        if (n != 1) {
            continue;
        }
        if (c == '\r' || c == '\n') {
            if (len > 0) {
                line[len] = '\0';
                run_line(line);
                len = 0;
            }
            continue;
        }
        if (c == 8 || c == 127) {   /* backspace */
            if (len > 0) {
                len--;
            }
            continue;
        }
        if (len < CONSOLE_LINE_MAX - 1) {
            line[len++] = (char)c;
        }
    }
}

void console_start(void)
{
    /* The UART driver has to be installed before anything can be read
     * from the console UART.  The ESP-IDF log writes to that UART
     * without a driver -- it puts the bytes in the hardware's own
     * register -- and the driver, with the receive buffer a command
     * arrives in, is installed only by the console's REPL, which this
     * firmware does not start.
     *
     * Installing it does not disturb the log: the log's own write path
     * keeps using the hardware register, because the VFS only switches
     * to the driver when the REPL takes the port over. */
    const esp_err_t err = uart_driver_install(UART_NUM_0, 1024, 0, 0, NULL, 0);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_LOGE(TAG, "the console UART could not be set up: %s",
                 esp_err_to_name(err));
        return;
    }
    xTaskCreate(console_task, "console", 3072, NULL, 3, NULL);
}
