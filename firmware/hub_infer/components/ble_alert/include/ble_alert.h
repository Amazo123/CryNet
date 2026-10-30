/*
 * CryNet — the BLE alert server.
 *
 * The hub is a GATT server: the caregiver's phone connects to it and
 * subscribes to the alert characteristic.  The service and the
 * characteristic use the UUIDs the legacy firmware published, so the
 * wearable firmware that was written against them keeps working:
 *
 *   device name   INFANT_MONITOR_HUB
 *   service       19b10000-e8f2-537e-4f6c-d104768a1214
 *   alert         19b10001-e8f2-537e-4f6c-d104768a1214
 *
 * A second characteristic, 19b10002-..., carries the *state* of every cot
 * (which cot is crying, how confident, and when it started).  The legacy
 * protocol had only the alert, but a caregiver's phone wants to show the
 * current state when it opens, not only the changes.
 *
 * The alert value is the legacy's six-byte packet, unchanged:
 *
 *   cot id, alert type (1 = cry, 2 = cancel), confidence in percent,
 *   event id.
 */

#ifndef BLE_ALERT_H
#define BLE_ALERT_H

#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The alert packet, the same six bytes the legacy firmware sent. */
typedef struct __attribute__((packed)) {
    uint8_t  cot_id;
    uint8_t  alert_type;      /* 1 = a cry, 2 = the cry has stopped */
    uint16_t confidence_pct;
    uint16_t event_id;
} ble_alert_packet_t;

/* The state of every cot, as the state characteristic reports it. */
typedef struct __attribute__((packed)) {
    uint8_t  cots;             /* how many cots the hub knows about */
    uint8_t  crying_mask;      /* bit 0 is cot 1, bit 1 is cot 2, ... */
    uint8_t  reserved;
    uint8_t  confidence_pct;   /* the loudest cry's confidence */
    uint32_t started_at_s;     /* when the current cry began */
} ble_state_packet_t;

/* Start the Bluetooth stack and begin advertising.  Returns false if the
 * stack could not be started; the hub carries on without it. */
bool ble_alert_start(void);

/* Publish a cot's state.  `crying` true raises the alert, false cancels
 * it.  Called when the state changes, not on every window. */
void ble_alert_publish(uint8_t cot_id, bool crying, uint16_t confidence_pct);

/* Publish the whole system's state, for the state characteristic. */
void ble_alert_publish_state(const ble_state_packet_t *state);

/* How many clients are connected and subscribed. */
int ble_alert_clients(void);

#ifdef __cplusplus
}
#endif

#endif /* BLE_ALERT_H */
