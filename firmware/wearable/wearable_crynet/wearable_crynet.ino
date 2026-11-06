/*
 * CryNet caregiver wearable — ESP32-C3 SuperMini + SSD1306 OLED.
 *
 * Stage 2d's first artifact: the BLE client side of the alert contract
 * (firmware/hub_infer/components/ble_alert — the same service a phone
 * connects to, verified in the alert sessions).  The wearable scans for
 * the hub, subscribes to the six-byte alert characteristic and shows the
 * alert on the OLED.  The eight-byte state characteristic is subscribed
 * to as well: the hub publishes it whenever it changes and at least once
 * a second, so a wearable that attaches in the middle of a cry still
 * sees it, and the idle face's crying mask stays honest for as long as
 * the link is up.
 *
 * All BLE work — scanning, connecting, subscribing — runs on its own
 * FreeRTOS task, and loop() only renders: the library's scan start,
 * connect and characteristic reads all block their caller, so leaving
 * them in loop() froze the whole screen whenever the hub went away.
 *
 * The screen is set in the hub panel's house style (firmware/hub_infer/
 * components/hub_display), translated to one bit: a boot face with the
 * breathing wordmark and a filling progress bar, a title card carrying
 * the device name, the builder's name and the id number, then the
 * dashboard with the waveform along its bottom edge.  An alert inverts a
 * band across the top -- the closest a monochrome panel comes to the
 * hub's red -- and blinks it while the wrist buzzes.
 *
 * The wearable does not carry the full project title: it is ninety-seven
 * characters and this screen is eighty pixels wide, so it would crowd
 * out the name and the id number that matter more here.  The title
 * belongs on the hub's panel, which has room for it.
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
 *   state (read+notify) 19b10002-...  8 bytes:
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
 * The vibration motor hangs on a BC547 low-side switch that this
 * firmware drives: GPIO7 -> 2.2 k base resistor -> base, emitter to
 * ground, the motor in the collector with its own flyback diode
 * (page 5 of the wiring diagrams).  The 100 k base-emitter pulldown
 * keeps the transistor off while the C3 boots with the pin floating, so
 * GPIO7 is driven low before anything else happens here.
 *
 * Serial console — 115200 baud: alerts, links and errors print here.
 */

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <BLEDevice.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

/* ---------------------------------------------------------------- pins -- */

static const uint8_t PIN_SDA = 5;   /* SSD1306 SDA (SYSTEM_WIRING.md 5.3) */
static const uint8_t PIN_SCL = 6;   /* SSD1306 SCL                        */
static const uint8_t PIN_MOTOR = 7; /* the BC547 haptic switch — wiring
                                       diagram page 5: GPIO7 -> 2.2 k ->
                                       base, motor in the collector     */

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

/* The haptic drive.
 *
 * GPIO7 high turns the BC547 on and the motor spins; GPIO7 low lets it
 * stop.  A buzz is a 250 ms pulse, and it runs in step with the band
 * blinking across the top of the screen — the same rhythm, so the wrist
 * and the eye agree on what is happening.
 *
 * One buzz per cry: the hub re-announces a cry when a louder cot joins
 * it, and the caregiver must not be buzzed twice for one cry. */
static const uint32_t HAPTIC_MS       = 2500;  /* how long a buzz runs    */
static const uint32_t HAPTIC_PULSE_MS = 250;   /* one pulse of the motor */
static volatile uint32_t g_haptic_until = 0;   /* when the buzz stops    */
static volatile uint32_t g_haptic_start = 0;   /* when the buzz started  */

static bool g_dirty = true;      /* the screen needs a redraw */
static bool g_oled_ok = false;

/* ------------------------------------------------------------ haptics -- */

static void haptic_trigger(void)
{
    g_haptic_start = millis();
    g_haptic_until = g_haptic_start + HAPTIC_MS;
    Serial.printf("[haptic] alert %u — motor on GPIO7 for %u ms\n",
                  (unsigned)g_event, (unsigned)HAPTIC_MS);
}

static void haptic_tick(void)
{
    const uint32_t now = millis();
    bool on = false;
    if (now < g_haptic_until) {
        /* 250 ms on, 250 ms off. */
        on = (((now - g_haptic_start) / HAPTIC_PULSE_MS) % 2) == 0;
    }
    digitalWrite(PIN_MOTOR, on ? HIGH : LOW);
}

/* ------------------------------------------------------------- theme -- */

/* The hub's panel sets the house style, and this little screen borrows
 * it in one bit: the waveform that runs along the bottom edge, the
 * wordmark, the accent band across the top of the title card, and the
 * boot progress bar that fills as the device comes up.
 *
 * Colour is the one thing a monochrome panel cannot copy, so the accent
 * is drawn inverted, and an alert turns the whole screen upside down
 * for as long as the wrist is buzzing -- the loudest thing one bit can
 * say. */

#define WEAR_BOOT_MS   2400    /* the boot face, before the title card  */
#define WEAR_TITLE_MS  6400    /* how long the title card holds         */
#define ALERT_HOLD_MS  60000   /* how long an alert stays on the screen */

static uint32_t g_boot_ms      = 0;    /* millis() when the OLED came up */
static uint32_t g_last_draw_ms = 0;    /* the last frame put on the glass */

/* The classic font is six pixels wide per cell, at any text size, so
 * centring is arithmetic, not measurement. */
static uint8_t centre_x(const char *s, uint8_t size)
{
    return (uint8_t)((128 - (int)strlen(s) * 6 * size) / 2);
}

/* The waveform along the bottom edge -- the same two drifting sine
 * waves the panel's title card uses, drawn as filled bars.  It is the
 * one motif that says this screen and the hub's panel are the same
 * project. */
static void draw_waveform(uint8_t y_base, int frame)
{
    const float t = (float)frame * 0.18f;
    for (int i = 0; i < 21; i++) {
        const float p = t + i * 0.42f;
        const float a = 0.5f + 0.5f * sinf(p * 1.7f);
        const float b = 0.5f + 0.5f * sinf(p * 0.53f + 1.7f);
        const int bh = (int)(8.0f * (0.18f + 0.82f * a * b));
        display.fillRect(i * 6, y_base + 1 - bh, 4, bh, SSD1306_WHITE);
    }
}

/* The boot steps, in the panel's voice -- and in its capitalisation: a
 * sentence starts with a capital, the way the panel's own boot lines do
 * when they are read out. */
static const char *s_boot_steps[] = {
    "The display is up",
    "Bluetooth is awake",
    "Searching for the hub",
};

/* The device's name, on two lines because it is sixteen characters and
 * this screen is a hundred and twenty-eight pixels wide: at the panel's
 * headline size two, sixteen characters need a hundred and ninety-two
 * pixels.  Stacked, the two halves sit inside the screen and still read
 * as one name. */
#define DEVICE_NAME_TOP "AMAZING'S"
#define DEVICE_NAME_BOT "CRYNET"

static void draw_boot_face(uint32_t elapsed_ms, int frame)
{
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    /* The wordmark -- the device's name, not the project's -- and under
     * it the breathing line that stands in for the panel's colour pulse:
     * a monochrome wordmark cannot brighten and dim, but the line under
     * it can swell and shrink. */
    display.setTextSize(2);
    display.setCursor(centre_x(DEVICE_NAME_TOP, 2), 3);
    display.print(DEVICE_NAME_TOP);
    display.setCursor(centre_x(DEVICE_NAME_BOT, 2), 19);
    display.print(DEVICE_NAME_BOT);
    display.setTextSize(1);
    display.setCursor(centre_x("INFANT CRY MONITOR", 1), 35);
    display.print("INFANT CRY MONITOR");

    const float pulse = 0.5f + 0.5f * sinf((float)frame * 0.12f);
    const int line_w = (int)(12.0f + 36.0f * pulse);
    display.fillRect(64 - line_w / 2, 44, line_w, 1, SSD1306_WHITE);

    /* What the wrist is doing as it comes up. */
    int step = (int)(elapsed_ms / (WEAR_BOOT_MS / 3));
    if (step > 2) { step = 2; }
    display.setCursor(centre_x(s_boot_steps[step], 1), 48);
    display.print(s_boot_steps[step]);

    /* The progress bar, same as the panel's. */
    const int bar_w = 80, bar_x = (128 - bar_w) / 2, bar_y = 57;
    const float prog = (float)elapsed_ms / (float)WEAR_BOOT_MS;
    const int filled = (int)(bar_w * (prog > 1.0f ? 1.0f : prog));
    display.drawRect(bar_x - 1, bar_y - 1, bar_w + 2, 6, SSD1306_WHITE);
    if (filled > 0) {
        display.fillRect(bar_x, bar_y, filled, 4, SSD1306_WHITE);
    }
    display.display();
}

/* The title card: what the device is, who built it, and the number it
 * is registered under -- the panel's own card, set for a screen eighty
 * pixels wide where the panel has three hundred and twenty.
 *
 * The full project title is ninety-seven characters and this font is
 * six pixels a cell, so the title cannot be laid out here the way it is
 * on the panel -- it would crowd out the name and the id number, which
 * matter more on a wrist.  The title stays on the hub's panel, which has
 * the room; this card carries the device's name and its owner's. */
static void draw_title_face(uint32_t now, int frame)
{
    (void)now;
    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);

    /* The accent band across the top, with its thicker leading edge. */
    display.fillRect(0, 0, 128, 2, SSD1306_WHITE);
    display.fillRect(0, 0, 34, 3, SSD1306_WHITE);

    /* The device's name -- sixteen characters, which at the panel's
     * headline size would need a hundred and ninety-two pixels, so it
     * sits on one line at the smaller size instead. */
    display.setTextSize(1);
    display.setCursor(centre_x(DEVICE_NAME_TOP " " DEVICE_NAME_BOT, 1), 9);
    display.print(DEVICE_NAME_TOP " " DEVICE_NAME_BOT);

    /* A rule, then the two things a panel has to say if the person
     * looking at it is the person who built it. */
    display.fillRect(28, 21, 72, 1, SSD1306_WHITE);

    display.setCursor(centre_x("AMAZING AYOMIKUN", 1), 27);
    display.print("AMAZING AYOMIKUN");
    display.setCursor(centre_x("ADELOWO", 1), 37);
    display.print("ADELOWO");
    display.setCursor(centre_x("22/05/04/0029", 1), 47);
    display.print("22/05/04/0029");

    /* The same waveform the panel runs along its edge, so the card is
     * alive in the same way the dashboard will be. */
    draw_waveform(62, frame * 2);
    display.display();
}

/* The dashboard, in the panel's language: a wordmark and a status pill
 * in the header, the news in the middle, and the waveform along the
 * bottom edge so the screen is visibly alive even when nothing is
 * happening. */
static void draw_dashboard(uint32_t now, int frame)
{
    const bool cry_now    = g_have_alert && g_type == 1 &&
                            (now - g_alert_ms) < ALERT_HOLD_MS;
    const bool deaf_now   = g_have_alert && g_type == 3 &&
                            (now - g_alert_ms) < ALERT_HOLD_MS;
    const bool cleared_now = g_have_alert && g_type == 2 &&
                            (now - g_alert_ms) < ALERT_HOLD_MS;

    display.clearDisplay();
    display.setTextColor(SSD1306_WHITE);
    display.setTextSize(1);

    /* ------------------------------------------------- the alert face */
    if (cry_now || deaf_now) {
        /* The band across the top, inverted -- the monochrome answer to
         * the panel's red.  It blinks while the wrist is buzzing, then
         * holds steady: urgency first, information after. */
        const bool band_on = (now - g_alert_ms) >= HAPTIC_MS ||
                             ((now / 250) % 2 == 0);
        if (band_on) {
            display.fillRect(0, 0, 128, 11, SSD1306_WHITE);
            display.setTextColor(SSD1306_BLACK);
        }
        display.setCursor(2, 2);
        display.print(cry_now ? "CRY" : "DEAF");
        char pill[8];
        snprintf(pill, sizeof pill, "COT %u", (unsigned)g_cot);
        display.setCursor(126 - (int)strlen(pill) * 6, 2);
        display.print(pill);
        display.setTextColor(SSD1306_WHITE);

        /* Who, large -- read from across a room. */
        display.setTextSize(3);
        display.setCursor(centre_x(pill, 3), 17);
        display.print(pill);
        display.setTextSize(1);

        if (cry_now) {
            /* The confidence, on a bar: the panel's level bar, scaled
             * to what the model is sure of rather than to how loud the
             * room is -- a wrist has no microphone. */
            const int bar_w = 86, bar_y = 45;
            display.drawRect(-1, bar_y - 1, bar_w + 2, 8, SSD1306_WHITE);
            const int filled = (int)(bar_w * (g_conf_pct / 100.0f));
            if (filled > 0) {
                display.fillRect(0, bar_y, filled, 6, SSD1306_WHITE);
            }
            char pct[6];
            snprintf(pct, sizeof pct, "%u%%", (unsigned)g_conf_pct);
            display.setCursor(126 - (int)strlen(pct) * 6, 46);
            display.print(pct);
        } else {
            /* The cot has gone deaf: the hub cannot get its audio, so
             * nobody is watching that cot at all. */
            display.setCursor(centre_x("The hub cannot", 1), 44);
            display.print("The hub cannot");
            display.setCursor(centre_x("hear that cot", 1), 53);
            display.print("hear that cot");
            display.display();
            return;
        }

        char line[24];
        snprintf(line, sizeof line, "Event #%u  %us ago",
                 (unsigned)g_event,
                 (unsigned)((now - g_alert_ms) / 1000));
        display.setCursor(0, 57);
        display.print(line);
        display.display();
        return;
    }

    /* --------------------------------------------------- the header */
    display.setCursor(0, 0);
    display.print("CRYNET");
    /* The pill: solid when the hub is attached, hollow while it scans --
     * the panel's two-state pill, reduced to outline and fill. */
    if (g_connected) {
        display.fillRect(84, 1, 4, 4, SSD1306_WHITE);
        display.setCursor(92, 0);
        display.print("LINK");
    } else {
        display.drawRect(84, 1, 4, 4, SSD1306_WHITE);
        display.setCursor(92, 0);
        display.print("SCAN");
    }

    /* ------------------------------------------------ the middle news */
    if (cleared_now) {
        display.setTextSize(2);
        display.setCursor(centre_x("CLEARED", 2), 22);
        display.print("CLEARED");
        display.setTextSize(1);
    } else if (g_connected) {
        if (g_mask) {
            display.setTextSize(2);
            display.setCursor(0, 20);
            display.print("CRYING");
            display.setTextSize(1);
            display.setCursor(0, 42);
            for (uint8_t bit = 0; bit < 8 && bit < (g_cots ? g_cots : 8); ++bit) {
                if (g_mask & (1u << bit)) {
                    display.printf("COT %u ", (unsigned)(bit + 1));
                }
            }
        } else {
            display.setTextSize(2);
            display.setCursor(centre_x("ALL CLEAR", 2), 22);
            display.print("ALL CLEAR");
            display.setTextSize(1);
            display.setCursor(centre_x("Every cot is quiet", 1), 42);
            display.print("Every cot is quiet");
        }
    } else {
        display.setCursor(centre_x("Searching", 1), 22);
        display.print("Searching");
        display.setCursor(centre_x("for the hub...", 1), 34);
        display.print("for the hub...");
    }

    /* ------------------------------------------------------ the edge */
    draw_waveform(64, g_mask ? frame * 2 : frame);
    display.display();
}

/* The splash and the dashboard, whichever face the clock calls for. */
static void render(void)
{
    if (!g_oled_ok) {
        return;
    }
    const uint32_t now = millis();
    const uint32_t up  = now - g_boot_ms;

    if (up < WEAR_BOOT_MS) {
        draw_boot_face(up, (int)(now / 50));
        return;
    }
    if (up < WEAR_BOOT_MS + WEAR_TITLE_MS) {
        draw_title_face(now, (int)(now / 50));
        return;
    }
    draw_dashboard(now, (int)(now / 50));
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
    } else if (g_type == 3 && prev_type != 3) {
        /* That cot has gone deaf: the hub cannot get its audio, so it
         * cannot announce a cry.  It is not being watched, and the
         * caregiver has to hear that from the wrist, not only see it
         * on the hub's panel. */
        Serial.printf("[ble] cot %u is DEAF\n", (unsigned)g_cot);
        haptic_trigger();
    }
}

/* The state characteristic arrives on its own: the hub publishes it
 * whenever it changes and at least once a second while a link is up, so
 * the idle face's crying mask is never more than a second stale and
 * nothing here ever blocks waiting for a read the hub may never answer. */
static void state_notify_cb(BLERemoteCharacteristic * /*chr*/,
                            uint8_t *data, size_t len, bool /*isNotify*/)
{
    if (len < 8) {
        Serial.printf("[ble] short state (%u bytes)\n", (unsigned)len);
        return;
    }
    g_cots = (uint8_t)data[0];
    g_mask = (uint8_t)data[1];
    /* data[3] carries the loudest cry's confidence; started_at is data[4..7]. */
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

    /* Fresh service discovery, every connection.  The library keeps the
     * previous connection's service handles across a disconnect —
     * m_haveServices survives it — so without this the second connect
     * hands back handles that point at a peer that no longer exists:
     * subscriptions go nowhere and the link looks alive but is deaf. */
    if (g_client->getServices()->empty()) {
        Serial.println("[ble] service discovery failed");
        g_client->disconnect();
        return false;
    }

    BLERemoteService *svc = g_client->getService(BLEUUID(SERVICE_UUID));
    if (!svc) {
        Serial.println("[ble] alert service not found");
        g_client->disconnect();
        return false;
    }
    g_alert = svc->getCharacteristic(BLEUUID(ALERT_UUID));
    if (!g_alert) {
        Serial.println("[ble] alert characteristic not found");
        g_alert = nullptr;
        g_client->disconnect();
        return false;
    }
    if (!g_alert->subscribe(true, alert_notify_cb, false)) {
        Serial.println("[ble] alert subscribe failed");
        g_alert = nullptr;
        g_client->disconnect();
        return false;
    }
    g_state = svc->getCharacteristic(BLEUUID(STATE_UUID));
    if (!g_state || !g_state->subscribe(true, state_notify_cb, false)) {
        Serial.println("[ble] state subscribe failed");
        g_state = nullptr;
        g_client->disconnect();
        return false;
    }

    if (!g_client->isConnected()) {
        /* The hub dropped us while the subscriptions were going up. */
        Serial.println("[ble] hub dropped during setup");
        return false;
    }

    g_connected = true;
    g_dirty     = true;
    Serial.println("[ble] subscribed to alerts + state");
    return true;
}

class HubScanCallbacks : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice advertisedDevice) override
    {
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

/* Defined below; setup() hands it to the scheduler. */
static void ble_task(void *arg);

void setup()
{
    Serial.begin(115200);
    /* Serial on the C3 is CDC: a write with no reader (a laptop asleep,
     * a cable in a charger) blocks until the buffer drains, and prints
     * made from BLE callbacks stall the radio that has to keep the
     * link alive.  Zero timeout — never wait on the console. */
    Serial.setTxTimeoutMs(0);
    delay(300);
    Serial.println("\nCryNet wearable — BLE alert client (stage 2d)");

    /* The motor's switch first, and low: the transistor must be off
     * from the first instruction, not from whenever setup() gets
     * round to it. */
    pinMode(PIN_MOTOR, OUTPUT);
    digitalWrite(PIN_MOTOR, LOW);

    Wire.begin(PIN_SDA, PIN_SCL);
    /* The waveform and the title ticker redraw ten times a second; at
     * the default 100 kHz each frame costs most of that budget, so the
     * bus runs at 400 kHz. */
    Wire.setClock(400000);
    g_oled_ok = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
    if (!g_oled_ok) {
        Serial.println("[oled] SSD1306 not found at 0x3C — check SDA 5 / SCL 6");
    } else {
        Serial.println("[oled] up");
    }
    g_boot_ms      = millis();   /* the splash starts here */
    g_last_draw_ms = g_boot_ms;
    g_dirty = true;

    BLEDevice::init("CRYNET_WEARABLE");
    g_client = BLEDevice::createClient();
    g_client->setClientCallbacks(new HubClientCallbacks());
    BLEScan *scan = BLEDevice::getScan();
    scan->setAdvertisedDeviceCallbacks(new HubScanCallbacks(), false);
    scan->setActiveScan(true);
    scan->setInterval(50);
    scan->setWindow(30);

    /* The BLE worker gets a generous stack: service discovery and the
     * library's own bookkeeping run on it.  Priority 1 — below nothing
     * the user sees, above the idle task. */
    xTaskCreate(ble_task, "ble", 6144, nullptr, 1, nullptr);
}

/* The BLE task.  Every library call here blocks its caller — the two-
 * argument scan start waits on a semaphore forever, connect can hold
 * for up to thirty seconds, and a characteristic read waits for a peer
 * that may never answer — so it gets its own task and the render loop
 * never waits on the radio.  Unplugging the hub can stall this task for
 * a while; the screen, the buzz and the animation keep going. */
static void ble_task(void * /*arg*/)
{
    for (;;) {
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
        vTaskDelay(pdMS_TO_TICKS(20));
    }
}

void loop()
{
    haptic_tick();

    /* The screen is animated — the waveform moves, the title ticker
     * crawls, the alert band blinks — so it redraws on a steady beat,
     * and at once whenever new information arrives.  The render itself
     * decides which face the clock calls for, so an alert also leaves
     * the screen on its own when its minute is up. */
    const uint32_t now = millis();
    if (g_dirty || now - g_last_draw_ms >= 100) {
        g_dirty        = false;
        g_last_draw_ms = now;
        render();
    }
    delay(10);
}
