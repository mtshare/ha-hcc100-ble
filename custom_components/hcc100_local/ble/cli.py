"""Command-line scanner and read-only client for initial hardware validation."""

import argparse
import asyncio
import json
from dataclasses import asdict

from bleak import BleakScanner

from .client import Hcc100Client
from .transport import SERVICE_UUID, BleakTransport


async def _run(args: argparse.Namespace) -> None:
    if args.command == "scan":
        devices = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
        for device, advertisement in devices.values():
            name = advertisement.local_name or device.name or ""
            if "hcc100" in name.lower() or SERVICE_UUID in advertisement.service_uuids:
                print(
                    json.dumps(
                        {"address": device.address, "name": name, "rssi": advertisement.rssi}
                    )
                )
        return
    device = await BleakScanner.find_device_by_address(args.address, timeout=args.timeout)
    if device is None:
        raise RuntimeError(
            "HCC100 not seen. Disconnect the technician app, briefly enable Bluetooth "
            "on the controller, and check range."
        )
    client = Hcc100Client(
        BleakTransport(device, payload_limit=args.payload_limit), expected_fingerprint=args.pin
    )
    try:
        if args.command == "info":
            print(json.dumps(asdict(await client.open()), indent=2))
        else:
            while True:
                state = await client.read_state()
                result = asdict(state)
                for zone_id, zone in state.zones.items():
                    result["zones"][zone_id]["outputs_open"] = zone.outputs_open
                    result["zones"][zone_id]["open_count"] = zone.open_count
                    result["zones"][zone_id]["masks_consistent"] = zone.masks_consistent
                print(json.dumps(result, indent=2, default=str))
                if not args.watch:
                    break
                await asyncio.sleep(args.watch)
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local, read-only Resideo HCC100 BLE client")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Find advertising HCC100 controllers")
    scan.add_argument("--timeout", type=float, default=15)
    for name in ("info", "state"):
        command = sub.add_parser(name)
        command.add_argument(
            "--address", required=True, help="MAC on Linux, CoreBluetooth UUID on macOS"
        )
        command.add_argument("--pin", help="Previously verified SHA-256 certificate fingerprint")
        command.add_argument("--timeout", type=float, default=20)
        command.add_argument("--payload-limit", type=int, choices=range(4, 179), metavar="4..178")
        if name == "state":
            command.add_argument("--watch", type=int, choices=range(15, 301), metavar="15..300")
    args = parser.parse_args()
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
