/*
 * CryNet — the BLE alert server (NimBLE).
 *
 * The structure follows the ESP-IDF's own NimBLE peripheral example; what
 * is CryNet's own is the service, the UUIDs (the legacy's) and the value
 * format (the legacy's six-byte alert packet).
 */

#include <string.h>

#include "esp_log.h"
#include "host/ble_hs.h"
#include "host/ble_uuid.h"
#include "host/util/util.h"
#include "nimble/nimble_port.h"
#include "nimble/nimble_port_freertos.h"
#include "services/gap/ble_svc_gap.h"
#include "services/gatt/ble_svc_gatt.h"

#include "ble_alert.h"

/* The host's NVS-backed store.  The store's own header declares the read
 * and write calls but not this one; the ESP-IDF's own test app declares
 * it the same way. */
void ble_store_config_init(void);

static const char *TAG = "ble_alert";

#define DEVICE_NAME "INFANT_MONITOR_HUB"

/* The legacy's UUIDs, written least-significant byte first, which is the
 * order BLE_UUID128_INIT takes them in. */
static const ble_uuid128_t s_svc_uuid =
    BLE_UUID128_INIT(0x14, 0x12, 0x8a, 0x76, 0x04, 0xd1, 0x6c, 0x4f,
                     0x7e, 0x53, 0xf2, 0xe8, 0x00, 0x00, 0xb1, 0x19);
static const ble_uuid128_t s_alert_uuid =
    BLE_UUID128_INIT(0x14, 0x12, 0x8a, 0x76, 0x04, 0xd1, 0x6c, 0x4f,
                     0x7e, 0x53, 0xf2, 0xe8, 0x01, 0x00, 0xb1, 0x19);
static const ble_uuid128_t s_state_uuid =
    BLE_UUID128_INIT(0x14, 0x12, 0x8a, 0x76, 0x04, 0xd1, 0x6c, 0x4f,
                     0x7e, 0x53, 0xf2, 0xe8, 0x02, 0x00, 0xb1, 0x19);

static ble_alert_packet_t   s_alert_value;
static ble_state_packet_t   s_state_value;
static uint16_t s_alert_handle;
static uint16_t s_state_handle;

static uint16_t s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
static bool     s_alert_notify = false;
static bool     s_state_notify = false;
static uint16_t s_event_id = 0;

static int gap_event(struct ble_gap_event *event, void *arg);

/* ---------------------------------------------------------------- GATT -- */

static int gatt_access(uint16_t conn_handle, uint16_t attr_handle,
                       struct ble_gatt_access_ctxt *ctxt, void *arg)
{
    (void)conn_handle;
    (void)arg;

    switch (ctxt->op) {
    case BLE_GATT_ACCESS_OP_READ_CHR: {
        const uint8_t *src;
        uint16_t len;
        if (attr_handle == s_alert_handle) {
            src = (const uint8_t *)&s_alert_value;
            len = (uint16_t)sizeof s_alert_value;
        } else {
            src = (const uint8_t *)&s_state_value;
            len = (uint16_t)sizeof s_state_value;
        }
        int rc = os_mbuf_append(ctxt->om, src, len);
        return (rc == 0) ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }
    default:
        return BLE_ATT_ERR_WRITE_NOT_PERMITTED;
    }
}

static const struct ble_gatt_svc_def s_svcs[] = {
    {
        .type = BLE_GATT_SVC_TYPE_PRIMARY,
        .uuid = &s_svc_uuid.u,
        .characteristics = (struct ble_gatt_chr_def[]){
            {
                .uuid = &s_alert_uuid.u,
                .access_cb = gatt_access,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY |
                         BLE_GATT_CHR_F_INDICATE,
                .val_handle = &s_alert_handle,
            },
            {
                .uuid = &s_state_uuid.u,
                .access_cb = gatt_access,
                .flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_NOTIFY,
                .val_handle = &s_state_handle,
            },
            { 0 },
        },
    },
    { 0 },
};

static void gatt_register_cb(struct ble_gatt_register_ctxt *ctxt, void *arg)
{
    (void)arg;
    ESP_LOGI(TAG, "the GATT server registered (operation %d)", (int)ctxt->op);
}

/* Register the service with the server.  The count has to be told to the
 * stack before the services are added: it is how the stack reserves the
 * attribute handles. */
static int gatt_svr_init(void)
{
    ble_svc_gatt_init();
    int rc = ble_gatts_count_cfg(s_svcs);
    if (rc != 0) {
        return rc;
    }
    return ble_gatts_add_svcs(s_svcs);
}

/* ----------------------------------------------------------------- GAP -- */

static void advertise(void)
{
    struct ble_gap_adv_params adv_params;
    struct ble_hs_adv_fields fields;
    const char *name = DEVICE_NAME;
    int rc;

    memset(&fields, 0, sizeof fields);
    fields.flags = BLE_HS_ADV_F_DISC_GEN | BLE_HS_ADV_F_BREDR_UNSUP;
    fields.tx_pwr_lvl_is_present = 1;
    fields.tx_pwr_lvl = BLE_HS_ADV_TX_PWR_LVL_AUTO;
    fields.name = (uint8_t *)name;
    fields.name_len = (uint8_t)strlen(name);
    fields.name_is_complete = 1;

    rc = ble_gap_adv_set_fields(&fields);
    if (rc != 0) {
        ESP_LOGE(TAG, "the advertisement fields could not be set: %d", rc);
        return;
    }

    memset(&adv_params, 0, sizeof adv_params);
    adv_params.conn_mode = BLE_GAP_CONN_MODE_UND;
    adv_params.disc_mode = BLE_GAP_DISC_MODE_GEN;
    rc = ble_gap_adv_start(BLE_OWN_ADDR_PUBLIC, NULL, BLE_HS_FOREVER,
                           &adv_params, gap_event, NULL);
    if (rc != 0) {
        ESP_LOGE(TAG, "advertising could not be started: %d", rc);
        return;
    }
    ESP_LOGI(TAG, "advertising as \"" DEVICE_NAME "\"");
}

static int gap_event(struct ble_gap_event *event, void *arg)
{
    (void)arg;

    switch (event->type) {
    case BLE_GAP_EVENT_CONNECT:
        if (event->connect.status == 0) {
            s_conn_handle = event->connect.conn_handle;
            ESP_LOGI(TAG, "a caregiver's phone connected");
        } else {
            ESP_LOGW(TAG, "the connection failed: %d", event->connect.status);
        }
        break;

    case BLE_GAP_EVENT_DISCONNECT:
        ESP_LOGI(TAG, "the caregiver's phone disconnected (reason %d)",
                 event->disconnect.reason);
        s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
        s_alert_notify = false;
        s_state_notify = false;
        advertise();   /* so the next phone can find the hub */
        break;

    case BLE_GAP_EVENT_SUBSCRIBE:
        if (event->subscribe.attr_handle == s_alert_handle) {
            s_alert_notify = event->subscribe.cur_notify;
            ESP_LOGI(TAG, "the alert characteristic is %s",
                     s_alert_notify ? "subscribed" : "no longer subscribed");
        } else if (event->subscribe.attr_handle == s_state_handle) {
            s_state_notify = event->subscribe.cur_notify;
            ESP_LOGI(TAG, "the state characteristic is %s",
                     s_state_notify ? "subscribed" : "no longer subscribed");
        }
        break;

    default:
        break;
    }
    return 0;
}

static void on_reset(int reason)
{
    ESP_LOGW(TAG, "the Bluetooth stack reset (reason %d)", reason);
    s_conn_handle = BLE_HS_CONN_HANDLE_NONE;
    s_alert_notify = false;
    s_state_notify = false;
}

static void on_sync(void)
{
    int rc = ble_hs_util_ensure_addr(0);
    if (rc != 0) {
        ESP_LOGE(TAG, "no usable Bluetooth address: %d", rc);
        return;
    }
    advertise();
}

/* -------------------------------------------------------------- public -- */

static void notify_value(uint16_t handle, bool subscribed, const void *value,
                         uint16_t len)
{
    if (s_conn_handle == BLE_HS_CONN_HANDLE_NONE || !subscribed) {
        return;
    }
    struct os_mbuf *om = ble_hs_mbuf_from_flat(value, len);
    if (om == NULL) {
        ESP_LOGE(TAG, "the notification could not be built");
        return;
    }
    int rc = ble_gatts_notify_custom(s_conn_handle, handle, om);
    if (rc != 0) {
        ESP_LOGW(TAG, "the notification was not sent: %d", rc);
    }
}

void ble_alert_publish(uint8_t cot_id, bool crying, uint16_t confidence_pct)
{
    s_alert_value.cot_id = cot_id;
    s_alert_value.alert_type = crying ? 1u : 2u;
    s_alert_value.confidence_pct = confidence_pct;
    s_event_id++;
    s_alert_value.event_id = s_event_id;

    ESP_LOGI(TAG, "%s cot %u at %u%%",
             crying ? "a cry on" : "the cry on cot", cot_id,
             (unsigned)confidence_pct);

    notify_value(s_alert_handle, s_alert_notify, &s_alert_value,
                 (uint16_t)sizeof s_alert_value);
}

void ble_alert_publish_state(const ble_state_packet_t *state)
{
    s_state_value = *state;
    notify_value(s_state_handle, s_state_notify, &s_state_value,
                 (uint16_t)sizeof s_state_value);
}

int ble_alert_clients(void)
{
    return (s_conn_handle == BLE_HS_CONN_HANDLE_NONE) ? 0 : 1;
}

static void host_task(void *param)
{
    (void)param;
    nimble_port_run();          /* returns only when the host stops */
    nimble_port_freertos_deinit();
}

bool ble_alert_start(void)
{
    int rc = nimble_port_init();
    if (rc != 0) {
        ESP_LOGE(TAG, "the Bluetooth host could not be started: %d", rc);
        return false;
    }

    ble_hs_cfg.reset_cb = on_reset;
    ble_hs_cfg.sync_cb = on_sync;
    ble_hs_cfg.gatts_register_cb = gatt_register_cb;
    ble_hs_cfg.store_status_cb = ble_store_util_status_rr;

    ble_svc_gap_device_name_set(DEVICE_NAME);
    ble_svc_gap_init();

    rc = gatt_svr_init();
    if (rc != 0) {
        ESP_LOGE(TAG, "the GATT service could not be registered: %d", rc);
        return false;
    }

    /* The host's own store, in NVS. */
    ble_store_config_init();

    nimble_port_freertos_init(host_task);
    ESP_LOGI(TAG, "the Bluetooth host is starting");
    return true;
}
