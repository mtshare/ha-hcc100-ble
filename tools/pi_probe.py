"""Run a temporary probe in HA's existing container, using its installed libraries.

Only a TemporaryDirectory inside the container is written, then removed. This
does not install dependencies, edit /config, load a HA config entry, or restart
any service. SSH uses the user's existing alias and credentials.
"""

import argparse
import base64
import json
import os
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("smoke", "scan", "info", "state"))
    parser.add_argument("--ssh", default="hassio")
    parser.add_argument("--address")
    parser.add_argument("--pin")
    parser.add_argument("--payload-limit", type=int)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.mode in ("info", "state") and not args.address:
        parser.error("--address is required")
    blob = BytesIO()
    with zipfile.ZipFile(blob, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in (ROOT / "custom_components").rglob("*"):
            if path.is_file() and path.suffix in (".py", ".json"):
                archive.write(path, path.relative_to(ROOT))
    encoded = base64.b64encode(blob.getvalue()).decode()
    request = json.dumps(
        {
            "mode": args.mode,
            "address": args.address,
            "pin": args.pin,
            "payload_limit": args.payload_limit,
        }
    )
    script = f"""
import asyncio, base64, importlib, io, json, sys, tempfile, zipfile
from dataclasses import asdict
request = json.loads({request!r})
async def probe(folder):
    if request['mode'] == 'smoke':
        for module in ['__init__', 'config_flow', 'sensor', 'binary_sensor', 'diagnostics']:
            suffix = '' if module == '__init__' else '.' + module
            importlib.import_module('custom_components.hcc100_local' + suffix)
        from homeassistant.const import __version__
        return {{'home_assistant': __version__, 'imports': 'ok'}}
    sys.path.insert(0, folder + '/custom_components/hcc100_local')
    from bleak import BleakScanner
    from ble import Hcc100Client
    from ble.transport import BleakTransport, SERVICE_UUID
    if request['mode'] == 'scan':
        devices = await BleakScanner.discover(timeout=15, return_adv=True)
        return [{{'address': d.address, 'name': a.local_name or d.name, 'rssi': a.rssi}}
                for d,a in devices.values()
                if 'hcc100' in (a.local_name or d.name or '').lower()
                or SERVICE_UUID in a.service_uuids]
    found = asyncio.get_running_loop().create_future()
    def detected(device, advertisement):
        if device.address.lower() == request['address'].lower() and not found.done():
            found.set_result(device)
    scanner = BleakScanner(detected)
    client = None
    await scanner.start()
    try:
        device = await asyncio.wait_for(found, timeout=60)
        from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
        async def connect(device, disconnected_callback):
            return await establish_connection(
                BleakClientWithServiceCache, device, device.name or 'HCC100',
                disconnected_callback=disconnected_callback)
        transport = BleakTransport(device, connect, request['payload_limit'])
        client = Hcc100Client(transport, expected_fingerprint=request['pin'])
        if request['mode'] == 'info':
            info = asdict(await client.open())
            return {{'device': info, 'payload_limit': transport.payload_limit}}
        state = await client.read_state()
        result = asdict(state)
        for zone_id, zone in state.zones.items():
            result['zones'][zone_id]['outputs_open'] = zone.outputs_open
            result['zones'][zone_id]['open_count'] = zone.open_count
            result['zones'][zone_id]['masks_consistent'] = zone.masks_consistent
        result['payload_limit'] = transport.payload_limit
        return result
    finally:
        if client:
            await client.close()
        await scanner.stop()
with tempfile.TemporaryDirectory(prefix='hcc100-probe-') as folder:
    with zipfile.ZipFile(io.BytesIO(base64.b64decode({encoded!r}))) as archive:
        archive.extractall(folder)
    sys.path.insert(0, folder)
    print(json.dumps(asyncio.run(probe(folder)), default=str))
"""
    result = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            args.ssh,
            "docker",
            "exec",
            "-i",
            "homeassistant",
            "python3",
            "-",
        ],
        input=script,
        text=True,
        capture_output=True,
        timeout=150,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout or "Remote probe failed")
    parsed = json.loads(result.stdout)
    if args.report:
        args.report.parent.mkdir(exist_ok=True, parents=True)
        with os.fdopen(
            os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w"
        ) as f:
            json.dump(parsed, f, indent=2, ensure_ascii=False)
        print(f"Report saved locally: {args.report}")
    else:
        print(json.dumps(parsed, indent=2))


if __name__ == "__main__":
    main()
