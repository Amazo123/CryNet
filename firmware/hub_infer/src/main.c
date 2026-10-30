/*
 * CryNet hub — inference core (Stage 2a).
 *
 * Stage 2a exists to de-risk the firmware before any radio, display or BLE
 * code is written. On the real ESP32-S3 this app proves:
 *
 *   1. the front end produces the same features as the Python training
 *      pipeline (four probes, compared byte for byte against references
 *      generated on the host from the notebook's own front end);
 *   2. the INT8 model fits and runs under TFLite Micro on this MCU;
 *   3. inference latency and tensor-arena usage are measured, not guessed;
 *   4. the decision rule (silence gate + calibrated threshold) fires on a
 *      cry-like window and stays quiet on everything else.
 *
 * The three-node -> hub -> wearable transport, the TFT UI and the BLE GATT
 * server arrive in later stages, once this core is verified.
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_chip_info.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_flash.h"
#include "esp_timer.h"
#include "nvs_flash.h"

#include "crynet_model.h"
#include "crynet_dsp.h"
#include "crynet_infer.h"
#include "probes.h"
#include "link_stage.h"
#include "ble_alert.h"
#include "hub_display.h"

static const char *TAG = "crynet";

/* Worst per-byte difference we accept between the device's quantised
 * features and the host's. The host reference and the device compute the
 * same maths in float32; the only difference is the last bit of a
 * transcendental function, so a handful of LSBs may differ. */
#define FEATURE_TOLERANCE 1

/* The probe buffers: 90 KB in all.  They are only needed while the
 * probes run, but as file-scope statics they would sit in internal RAM
 * for the life of the program — and the Bluetooth stack needs that RAM
 * far more than the probes do (NimBLE's store configuration was
 * failing to allocate on a board whose radio worked perfectly).  So
 * they live in PSRAM and are handed back when the probes are done. */
static int16_t *s_pcm = NULL;
static float   *s_mel = NULL;
static int8_t  *s_q = NULL;

/* PSRAM if it is there, internal SRAM if it is not. */
static void *alloc_probe_buffer(size_t bytes)
{
    void *p = heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (p == NULL) {
        p = heap_caps_malloc(bytes, MALLOC_CAP_8BIT);
    }
    return p;
}

static void free_probe_buffers(void)
{
    heap_caps_free(s_pcm);
    heap_caps_free(s_mel);
    heap_caps_free(s_q);
    s_pcm = NULL;
    s_mel = NULL;
    s_q = NULL;
}

static void report_platform(void)
{
    esp_chip_info_t chip;
    esp_chip_info(&chip);

    /* ESP-IDF 6.x changed the flash API: esp_flash_get_size() now takes a
     * chip handle (NULL selects the default chip) and writes the size
     * through an out-parameter. */
    uint32_t flash_bytes = 0;
    esp_flash_get_size(NULL, &flash_bytes);

    ESP_LOGI(TAG, "chip       : rev %d, %u cores", chip.revision, chip.cores);
    ESP_LOGI(TAG, "psram      : %d bytes (%s)",
             (int)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),
             heap_caps_get_total_size(MALLOC_CAP_SPIRAM) > 0 ? "present" : "ABSENT");
    ESP_LOGI(TAG, "free int   : %d bytes", (int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
    ESP_LOGI(TAG, "flash      : %u bytes", (unsigned)flash_bytes);
    ESP_LOGI(TAG, "model      : %u bytes (int8)", (unsigned)crynet_model_size());
    ESP_LOGI(TAG, "threshold  : %.4f    silence gate %.6f",
             (double)CRYNET_THRESHOLD, (double)CRYNET_SILENCE_RMS_GATE);
    ESP_LOGI(TAG, "input quant: scale %.9f  zero point %d",
             (double)CRYNET_INPUT_SCALE, CRYNET_INPUT_ZERO_POINT);
}

/* Compare the device's quantised features against the host reference. */
static bool check_features(int probe)
{
    const int8_t *expected = crynet_probe_expected(probe);
    int worst = 0;
    int exact = 0;
    int mismatched = 0;

    for (int i = 0; i < CRYNET_FEATURE_COUNT; i++) {
        const int d = (int)s_q[i] - (int)expected[i];
        const int ad = (d < 0) ? -d : d;
        if (ad > worst) {
            worst = ad;
        }
        if (ad == 0) {
            exact++;
        } else {
            mismatched++;
        }
    }

    const bool ok = (worst <= FEATURE_TOLERANCE) && (mismatched <= CRYNET_FEATURE_COUNT / 100);
    ESP_LOGI(TAG, "  features  : max delta %d, %d/%d exact, %d differing -> %s",
             worst, exact, CRYNET_FEATURE_COUNT, mismatched, ok ? "PASS" : "FAIL");
    return ok;
}

void app_main(void)
{
    ESP_LOGI(TAG, "=================================================");
    ESP_LOGI(TAG, "CryNet hub — inference core (Stage 2a)");
    ESP_LOGI(TAG, "=================================================");
    report_platform();

    /* The Bluetooth stack keeps its keys in NVS, and the store has to be
     * there before the host starts. */
    esp_err_t nvs_err = nvs_flash_init();
    if (nvs_err == ESP_ERR_NVS_NO_FREE_PAGES ||
        nvs_err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        nvs_err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(nvs_err);

    /* ---------------- front end ---------------- */
    static crynet_dsp_ctx_t dsp;
    if (!crynet_dsp_init(&dsp)) {
        ESP_LOGE(TAG, "front end: cannot allocate the working buffers");
        return;
    }
    ESP_LOGI(TAG, "front end  : %u bytes of working memory (%s)",
             (unsigned)dsp.bytes, dsp.from_psram ? "PSRAM" : "internal SRAM");

    /* ---------------- interpreter ---------------- */
    crynet_infer_t *infer = crynet_infer_create();
    if (!crynet_infer_ready(infer)) {
        ESP_LOGE(TAG, "interpreter: %s", crynet_infer_error(infer));
        crynet_infer_destroy(infer);
        crynet_dsp_free(&dsp);
        return;
    }
    ESP_LOGI(TAG, "interpreter: ready, arena %u bytes reserved, %u used",
             (unsigned)crynet_infer_arena_bytes(infer),
             (unsigned)crynet_infer_arena_used(infer));

    /* ---------------- probes ---------------- */
    s_pcm = alloc_probe_buffer(CRYNET_PROBE_SAMPLES * sizeof(int16_t));
    s_mel = alloc_probe_buffer(CRYNET_FEATURE_COUNT * sizeof(float));
    s_q = alloc_probe_buffer(CRYNET_FEATURE_COUNT * sizeof(int8_t));
    if (s_pcm == NULL || s_mel == NULL || s_q == NULL) {
        ESP_LOGE(TAG, "the probe buffers could not be allocated");
        return;
    }

    int failures = 0;

    for (int p = 0; p < CRYNET_PROBE_COUNT; p++) {
        ESP_LOGI(TAG, "--- probe %d: %s ---", p, crynet_probe_name(p));

        crynet_probe_pcm(p, s_pcm);

        const uint32_t pcm_crc = crynet_probe_pcm_crc(p);
        const uint32_t want_pcm_crc = crynet_probe_expected_pcm_crc(p);
        if (pcm_crc != want_pcm_crc) {
            ESP_LOGE(TAG, "  pcm       : CRC 0x%08x, expected 0x%08x -> FAIL",
                     (unsigned)pcm_crc, (unsigned)want_pcm_crc);
            failures++;
            continue;
        }
        ESP_LOGI(TAG, "  pcm       : CRC 0x%08x matches the host", (unsigned)pcm_crc);

        const int64_t t0 = esp_timer_get_time();
        crynet_dsp_features(&dsp, s_pcm, s_mel);
        const int64_t t1 = esp_timer_get_time();
        crynet_dsp_quantise(s_mel, s_q);
        const int64_t t2 = esp_timer_get_time();

        ESP_LOGI(TAG, "  front end : %.2f ms  (quantise %.2f ms)",
                 (double)(t1 - t0) / 1000.0, (double)(t2 - t1) / 1000.0);

        if (!check_features(p)) {
            failures++;
        }

        float p_no_cry = 0.0f, p_cry = 0.0f;
        const int64_t t3 = esp_timer_get_time();
        const bool ran = crynet_infer_run(infer, s_q, &p_no_cry, &p_cry);
        const int64_t t4 = esp_timer_get_time();
        if (!ran) {
            ESP_LOGE(TAG, "  inference : FAILED (%s)", crynet_infer_error(infer));
            failures++;
            continue;
        }

        const float rms = crynet_dsp_rms(s_pcm);
        const bool silent = rms < CRYNET_SILENCE_RMS_GATE;
        const bool alert = (!silent) && (p_cry >= CRYNET_THRESHOLD);

        ESP_LOGI(TAG, "  inference : %.2f ms   P(no_cry)=%.4f  P(cry)=%.4f",
                 (double)(t4 - t3) / 1000.0, (double)p_no_cry, (double)p_cry);
        ESP_LOGI(TAG, "  decision  : rms %.6f  %s -> %s",
                 (double)rms,
                 silent ? "below the silence gate" : "above the silence gate",
                 alert ? "ALERT" : "no alert");
    }

    /* The probes are done with their buffers; hand them back so the
     * radio and the Bluetooth stack have the whole internal heap. */
    free_probe_buffers();
    ESP_LOGI(TAG, "free int   : %d bytes after the probes",
             (int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

    ESP_LOGI(TAG, "=================================================");
    if (failures == 0) {
        ESP_LOGI(TAG, "RESULT: PASS — %d probes, front end and model agree "
                      "with the host", CRYNET_PROBE_COUNT);
        ESP_LOGI(TAG, "=================================================");

        /* The caregiver's phone connects to the hub over BLE and is told
         * when a cot hears a cry.  The hub's own link to the nodes is
         * ESP-NOW, so the two radios coexist — and the radio comes up
         * before the Bluetooth stack on purpose: NimBLE's pools and the
         * Wi-Fi driver's buffers come out of the same internal RAM, and
         * when BLE claimed its memory first the Wi-Fi driver ran out
         * mid-init and the ESP-NOW link never started.  The radio takes
         * what it needs while the heap is whole, and BLE lives on what
         * is left. */
        if (!link_stage_radio_start()) {
            ESP_LOGW(TAG, "the radio could not be started; "
                          "the hub carries on without it");
        }
        ESP_LOGI(TAG, "free int   : %d bytes with the radio up",
                 (int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        if (!ble_alert_start()) {
            ESP_LOGW(TAG, "the Bluetooth alert server could not be started; "
                          "the hub carries on without it");
        }
        ESP_LOGI(TAG, "free int   : %d bytes with Bluetooth up",
                 (int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));
        /* The panel is optional too: a dead display does not stop the
         * monitoring, it only stops the showing. */
        if (!hub_display_start()) {
            ESP_LOGW(TAG, "the display could not be started; "
                          "the hub carries on without it");
        }
        link_stage_run(&dsp, infer);
    } else {
        ESP_LOGE(TAG, "RESULT: FAIL — %d check(s) failed", failures);
        ESP_LOGE(TAG, "=================================================");
        crynet_infer_destroy(infer);
        crynet_dsp_free(&dsp);
    }
}
