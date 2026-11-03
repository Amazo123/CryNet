/*
 * CryNet caregiver wearable — ESP32-C3 SuperMini + SSD1306 OLED.
 *
 * Stage 2d's first artifact: the BLE client side of the alert contract
 * (firmware/hub_infer/components/ble_alert — the same service a phone
 * connects to, verified in the alert sessions).  The wearable scans for
 * the hub, subscribes to the six-byte alert characteristic and shows the
 * alert on the OLED.  It also reads the state characteristic once on
 * connect, so a wearable that attaches in the middle of a cry still
 * sees it.
 *
 * The hub's contract, unchanged by this sketch:
 *
 *   device name   INFANT_MONITOR_HUB
 *   service       19b10000-e8f2-537e-4f6c-d104768a1214
 *   alert (notify) 19b10001-...  6 bytes:
 *       0  cot id
 *       1  alert type   1 = a cry, 2 = the cry has stopped
 *       2  confidence, percent, little-endian u16
 *       4  event id, little-endian u16
 *   state (read)  19b10002-...  8 bytes:
 *       0  cot count   1  crying mask (bit 0 = cot 1, ...)
 *       2  reserved    3  confidence, percent
 *       4  started_at, seconds, little-endian u32
 *
 * The hub advertises only when no caregiver device is attached and no
 * ESP-NOW burst is in the air, so a disconnected wearable simply keeps
 * scanning and attaches in the gaps — that is the design, not a bug.
 *
 * Wiring — SSD1306 to ESP32-C3 SuperMini (SYSTEM_WIRING.md 5.3):
 *     VCC -> 3V3    GND -> GND    SDA -> GPIO5    SCL -> GPIO6
 *
 * The vibration motor does not exist yet.  haptic_trigger() is the hook
 * the DRV2605L will drive (I2C 0x5A, same bus); until the motor arrives
 * the onboard LED stands in and blinks the alert, so the vibration path
 * can be exercised end to end the day the motor lands.
 *
 * Serial console — 115200 baud: alerts, links and errors print here.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <BLEDevice.h>

/* ---------------------------------------------------------------- pins -- */

static const uint8_t PIN_SDA = 5;   /* SSD1306 SDA (SYSTEM_WIRING.md 5.3) */
static const uint8_t PIN_SCL = 6;   /* SSD1306 SCL                        */
static const uint8_t PIN_LED = 8;   /* onboard LED — the haptic stand-in  */
static const bool LED_ACTIVE_LOW = true;

/* ------------------------------------------------------------ contract -- */

static const char *HUB_NAME     = "INFANT_MONITOR_HUB";
static const char *SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214";
static const char *ALERT_UUID   = "19b10001-e8f2-537e-4f6c-d104768a1214";
static const char *STATE_UUID   = "19b10002-e8f2-537e-4f6c-d104768a1214";

/* ---------------------------------------------------------------- state -- */

static Adafruit_SSD1306 display(128, 64, &Wire, -1);

static BLEAdvertisedDevice   *g_hub_device = nullptr;
static BLEClient             *g_client     = nullptr;
static BLERemoteCharacteristic *g_alert    = nullptr;
static BLERemoteCharacteristic *g_state    = nullptr;

static volatile bool g_do_connect = false;
static volatile bool g_connected  = false;

/* The last alert received.  Written from the BLE callback, read by the
 * renderer — set the dirty flag after each write. */
static volatile uint8_t  g_cot      = 0;
static volatile uint8_t  g_type     = 0;    /* 1 = cry, 2 = cancel */
static volatile uint16_t g_conf_pct = 0;
static volatile uint16_t g_event    = 0;
static volatile bool     g_have_alert = false;
static volatile uint32_t g_alert_ms   = 0;

static volatile uint8_t  g_cots = 0;
static volatile uint8_t  g_mask = 0;

/* The haptic stand-in: blink the onboard LED for a while after a cry. */
static const uint32_t HAPTIC_MS = 2500;
static uint32_t g_haptic_until = 0;

static bool g_dirty = true;      /* the screen needs a redraw */
static bool g_oled_ok = false;

/* ------------------------------------------------------------ haptics -- */

/* The vibration hook.  One day: DRV2605L at I2C 0x5A on SDA 5 / SCL 6,
 * driven in realtime mode for the alert.  Today: the onboard LED blinks,
 * so the path from BLE notify to "something physically reacts" is
 * testable without the motor. */
static void haptic_trigger(void)
{
    g_haptic_until = millis() + HAPTIC_MS;
    Serial.printf("[haptic] alert %u — motor not present, LED stands in\n",
                  (unsigned)g_event);
}

static void haptic_tick(void)
{
    const bool on = millis() < g_haptic_until;
    const bool level = on && ((millis() / 120) % 2 == 0);
    digitalWrite(PIN_LED, LED_ACTIVE_LOW ? !level : level);
}

/* ------------------------------------------------------------- render -- */

static void render(void)
{
    if (!g_oled_ok) {
        return;
    }
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    display.setTextSize(1);
    display.setCursor(0, 0);
    display.print("CryNet");
    display.setCursor(78, 0);
    display.print(g_connected ? "LINK" : "SCAN");

    if (g_have_alert && g_type == 1) {
        display.setTextSize(2);
        display.setCursor(0, 16);
        display.printf("COT %u", (unsigned)g_cot);
        display.setCursor(0, 36);
        display.printf("CRY %u%%", (unsigned)g_conf_pct);
        display.setTextSize(1);
        display.setCursor(0, 56);
        display.printf("event #%u  %us ago",
                       (unsigned)g_event,
                       (unsigned)((millis() - g_alert_ms) / 1000));
    } else {
        display.setTextSize(2);
        display.setCursor(0, 20);
        if (g_have_alert && g_type == 2) {
            display.print("cleared");
        } else {
            display.print("all clear");
        }
        display.setTextSize(1);
        display.setCursor(0, 56);
        if (g_connected) {
            if (g_mask) {
                display.print("crying: cot");
                for (uint8_t bit = 0; bit < 8 && bit < (g_cots ? g_cots : 8); ++bit) {
                    if (g_mask & (1u << bit)) {
                        display.printf(" %u", (unsigned)(bit + 1));
                    }
                }
            } else {
                display.print("no cry anywhere");
            }
        } else {
            display.print("searching for hub...");
        }
    }
    display.display();
}

/* ---------------------------------------------------------------- BLE -- */

static void alert_notify_cb(BLERemoteCharacteristic * /*chr*/,
                            uint8_t *data, size_t len, bool /*isNotify*/)
{
    if (len < 6) {
        Serial.printf("[ble] short alert (%u bytes) ignored\n", (unsigned)len);
        return;
    }
    /* What the wrist was told last, so one cry is one buzz. */
    const uint8_t prev_type = g_type;
    g_cot      = data[0];
    g_type     = data[1];
    g_conf_pct = (uint16_t)data[2] | ((uint16_t)data[3] << 8);
    g_event    = (uint16_t)data[4] | ((uint16_t)data[5] << 8);
    g_have_alert = true;
    g_alert_ms   = millis();
    g_dirty      = true;
    Serial.printf("[ble] ALERT cot %u type %u conf %u%% event #%u\n",
                  (unsigned)g_cot, (unsigned)g_type,
                  (unsigned)g_conf_pct, (unsigned)g_event);
    if (g_type == 1 && prev_type != 1) {
        /* One buzz per cry, not one per announcement.  The hub names
         * the loudest cot, and it re-issues the alert when a louder
         * cot joins the cry -- the display follows the baby from cot
         * to cot, but the wrist buzzes once. */
        haptic_trigger();
    }
}

static void read_state_once(void)
{
    if (!g_state) {
        return;
    }
    String v = g_state->readValue();
    if (v.length() < 8) {
        Serial.printf("[ble] short state (%u bytes)\n", (unsigned)v.length());
        return;
    }
    g_cots = (uint8_t)v[0];
    g_mask = (uint8_t)v[1];
    /* v[3] carries the loudest cry's confidence; started_at is v[4..7]. */
    g_dirty = true;
    Serial.printf("[ble] state: %u cot(s), mask 0x%02X\n",
                  (unsigned)g_cots, (unsigned)g_mask);
}

class HubClientCallbacks : public BLEClientCallbacks {
    void onConnect(BLEClient *) override
    {
        Serial.println("[ble] hub connected");
    }
    void onDisconnect(BLEClient *) override
    {
        Serial.println("[ble] hub lost — rescanning");
        g_connected = false;
        g_alert     = nullptr;
        g_state     = nullptr;
        g_dirty     = true;
    }
};

static bool connect_to_hub(void)
{
    Serial.printf("[ble] connecting to %s\n", g_hub_device->getAddress().toString().c_str());

    /* Connect to the remote BLE Server. */
    if (!g_client->connect(g_hub_device)) {
        Serial.println("[ble] connect failed");
        return false;
    }

    BLERemoteService *svc = g_client->getService(BLEUUID(SERVICE_UUID));
    if (!svc) {
        Serial.println("[ble] alert service not found");
        return false;
    }
    g_alert = svc->getCharacteristic(BLEUUID(ALERT_UUID));
    if (!g_alert) {
        Serial.println("[ble] alert characteristic not found");
        return false;
    }
    if (!g_alert->subscribe(true, alert_notify_cb, false)) {
        Serial.println("[ble] subscribe failed");
        return false;
    }
    g_state = svc->getCharacteristic(BLEUUID(STATE_UUID));
    read_state_once();

    g_connected = true;
    g_dirty     = true;
    Serial.println("[ble] subscribed to alerts");
    return true;
}

class HubScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertisedDevice) override
    {
        /* SCAN DEBUG — what the scan actually sees.  Removed once the
         * link is verified. */
        Serial.printf("[scan] %s name=\"%s\" svc_uuid=%d\n",
                      advertisedDevice.getAddress().toString().c_str(),
                      advertisedDevice.getName().c_str(),
                      advertisedDevice.haveServiceUUID() ? 1 : 0);
        const bool name_ok = advertisedDevice.getName() == HUB_NAME;
        const bool uuid_ok = advertisedDevice.haveServiceUUID() &&
                             advertisedDevice.isAdvertisingService(BLEUUID(SERVICE_UUID));
        if (!name_ok && !uuid_ok) {
            return;
        }
        Serial.printf("[ble] hub found (%s)\n",
                      advertisedDevice.getAddress().toString().c_str());
        BLEDevice::getScan()->stop();
        delete g_hub_device;
        g_hub_device = new BLEAdvertisedDevice(advertisedDevice);
        g_do_connect = true;
    }
};

/* ----------------------------------------------------------------- main -- */

void setup()
{
    Serial.begin(115200);
    delay(300);
    Serial.println("\nCryNet wearable — BLE alert client (stage 2d)");

    pinMode(PIN_LED, OUTPUT);
    digitalWrite(PIN_LED, LED_ACTIVE_LOW ? HIGH : LOW);

    Wire.begin(PIN_SDA, PIN_SCL);
    g_oled_ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
    if (!g_oled_ok) {
        Serial.println("[oled] SSD1306 not found at 0x3C — check SDA 5 / SCL 6");
    } else {
        Serial.println("[oled] up");
    }
    g_dirty = true;

    BLEDevice::init("CRYNET_WEARABLE");
    g_client = BLEDevice::createClient();
    g_client->setClientCallbacks(new HubClientCallbacks());
    BLEScan *scan = BLEDevice::getScan();
    scan->setAdvertisedDeviceCallbacks(new HubScanCallbacks(), false);
    scan->setActiveScan(true);
    scan->setInterval(50);
    scan->setWindow(30);
}

void loop()
{
    if (g_do_connect) {
        g_do_connect = false;
        if (!connect_to_hub()) {
            g_connected = false;      /* the scan resumes; the client is reused */
            g_dirty     = true;
        }
    } else if (!g_connected) {
        BLEScan *scan = BLEDevice::getScan();
        scan->start(2, false);        /* scan in two-second windows */
        scan->clearResults();
    }

    haptic_tick();

    /* Cancel the alert panel a minute after its cry so the screen
     * returns to the idle face on its own. */
    if (g_have_alert && g_type == 1 && millis() - g_alert_ms > 60000) {
        g_dirty = true;
    }

    if (g_dirty) {
        g_dirty = false;
        render();
    }
    delay(10);
}
