#!/usr/bin/env python3
"""Talk to the CryNet hub's BLE alert server from a PC.

The hub is a GATT server with the legacy's UUIDs: the service
19b10000-e8f2-537e-4f6c-d104768a1214 and the alert characteristic
19b10001-e8f2-537e-4f6c-d104768a1214, plus a state characteristic
19b10002-e8f2-537e-4f6c-d104768a1214.  The alert value is the legacy's
six-byte packet:

    cot id, alert type (1 = cry, 2 = the cry has stopped),
    confidence in percent, event id.

Usage:
    python firmware/tools/ble_alert_test.py                 # scan only
    python firmware/tools/ble_alert_test.py --listen        # scan, connect,
                                                            # subscribe, wait
"""

from __future__ import annotations

import argparse
import asyncio
import struct
import sys

DEVICE_NAME = "INFANT_MONITOR_HUB"
SERVICE_UUID = "19b10000-e8f2-537e-4f6c-d104768a1214"
ALERT_UUID = "19b10001-e8f2-537e-4f6c-d104768a1214"
STATE_UUID = "19b10002-e8f2-537e-4f6c-d104768a1214"


def decode_alert(data: bytes) -> dict:
    if len(data) < 6:
        return {"raw": data.hex()}
    cot, kind, confidence, event = struct.unpack("<BBHH", data[:6])
    return {
        "cot": cot,
        "alert": "cry" if kind == 1 else ("cleared" if kind == 2 else kind),
        "confidence_pct": confidence,
        "event_id": event,
    }


def decode_state(data: bytes) -> dict:
    if len(data) < 8:
        return {"raw": data.hex()}
    cots, mask, _res, confidence, started = struct.unpack("<BBBBI", data[:8])
    return {
        "cots": cots,
        "crying_mask": mask,
        "confidence_pct": confidence,
        "started_at_s": started,
    }


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", action="store_true",
                    help="connect and subscribe, instead of only scanning")
    ap.add_argument("--seconds", type=float, default=120.0)
    ap.add_argument("--name", default=DEVICE_NAME)
    args = ap.parse_args()

    try:
        from bleak import BleakClient, BleakScanner
    except ImportError:
        print("bleak is not installed: pip install bleak", file=sys.stderr)
        return 1

    print(f"scanning for \"{args.name}\" ...")
    device = await BleakScanner.find_device_by_name(args.name, timeout=20.0)
    if device is None:
        print("the hub was not found. Is it powered and advertising?",
              file=sys.stderr)
        return 1
    print(f"found {device.name} at {device.address}")

    if not args.listen:
        return 0

    async def on_alert(_char, data: bytearray):
        print("ALERT", decode_alert(bytes(data)), flush=True)

    async def on_state(_char, data: bytearray):
        print("STATE", decode_state(bytes(data)), flush=True)

    async with BleakClient(device) as client:
        print("connected")
        for service in client.services:
            for char in service.characteristics:
                print(f"  service {service.uuid}  characteristic {char.uuid} "
                      f"{char.properties}")

        try:
            await client.start_notify(ALERT_UUID, on_alert)
            print("subscribed to the alert characteristic", flush=True)
        except Exception as exc:                       # noqa: BLE001
            print(f"the alert characteristic could not be subscribed to: {exc}")
        try:
            await client.start_notify(STATE_UUID, on_state)
            print("subscribed to the state characteristic", flush=True)
        except Exception as exc:                       # noqa: BLE001
            print(f"the state characteristic could not be subscribed to: {exc}")

        print(f"listening for {args.seconds:.0f} s ...")
        await asyncio.sleep(args.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
