"""Synthetic peer with real P-256/ECDH/AES. No captured device data or keys."""

import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from hcc100_ble.crypto import SessionCipher, derive_material
from hcc100_ble.framing import ENCRYPTED, HANDSHAKE, FrameReader, FrameWriter


class FakeTransport:
    def __init__(self, payload_limit=16):
        self.payload_limit = payload_limit
        self.is_connected = False
        self._disconnected = lambda: None
        self.callback = None
        self.private = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "HCC100-001122334455")])
        self.certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(self.private.public_key())
            .serial_number(1)
            .not_valid_before(datetime.now(UTC) - timedelta(days=1))
            .not_valid_after(datetime.now(UTC) + timedelta(days=365))
            .sign(self.private, hashes.SHA256())
        )
        self.commands = []
        self.client_points = []
        self.drop_response = False

    def set_disconnected_callback(self, callback):
        self._disconnected = callback

    async def connect(self):
        self.is_connected = True
        self.reader = FrameReader()
        self.writer = FrameWriter(37)
        self.writer.sequence = 250  # Exercise counter wrap during the certificate.
        self.cipher = None
        self.nonce = bytes(range(16))

    async def start_notify(self, callback):
        self.callback = callback

    def _reply(self, payload, flags):
        for frame in self.writer.encode(payload, flags):
            if flags == HANDSHAKE:
                # Device handshake replies carry the additional observed low bit.
                frame = bytes([frame[0] | 1]) + frame[1:]
            self.callback(frame)

    async def write(self, frame):
        assert self.is_connected
        message = self.reader.feed(frame)
        if message is None:
            return
        if message.handshake and len(message.payload) == 5:
            der = self.certificate.public_bytes(serialization.Encoding.DER)
            payload = b"\x02" + bytes(4) + bytes.fromhex("001122334455")
            payload += self.nonce + len(der).to_bytes(4, "big") + der
            self._reply(payload, HANDSHAKE)
        elif message.handshake:
            assert len(message.payload) == 80
            point, nonce = message.payload[:64], message.payload[64:]
            self.client_points.append(point)
            public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), b"\x04" + point)
            shared = self.private.exchange(ec.ECDH(), public)
            key, iv = derive_material(shared, nonce, self.nonce)
            self.cipher = SessionCipher(key, iv)
            auth = self.cipher.transform(hashlib.sha256(b"synthetic-peer-confirmation").digest())
            self._reply(len(auth).to_bytes(4, "big") + auth, HANDSHAKE)
        else:
            assert self.cipher is not None
            request = json.loads(self.cipher.transform(message.payload))
            assert request["Session"] == "WickAppDIY"
            command = request["Cfg"][0]
            self.commands.append(command)
            if self.drop_response:
                return
            if command["Cmd"] == "GetDeviceInfo":
                response = [{"Cmd": "DeviceInfo", "Model": "HCC100", "SwVer": "test"}]
            elif command["Cmd"] == "GetName":
                response = [
                    {
                        "Cmd": "GetName",
                        "ZoneID": list(range(1, 9)),
                        "ZoneName": [f"Test zone {i}" for i in range(1, 9)],
                    }
                ]
            else:
                zone = command.get("ZoneID")
                values = {
                    224: 3 if zone == 1 else 0,
                    230: 20.5,
                    231: 21.0,
                    232: 0,
                    229: 5,
                    238: 1,
                    241: 2,
                    254: 0,
                }
                response = [
                    {"Cmd": "Resp", "ID": i, "Val": values[i], "ZoneID": zone}
                    for i in command["IDs"]
                ]
            response.append({"Cmd": "Complete"})
            payload = (
                json.dumps(
                    {"Session": "WickAppDIY", "Cfg": response}, separators=(",", ":")
                ).encode()
                + b"\x00"
            )
            self._reply(self.cipher.transform(payload), ENCRYPTED)

    async def disconnect(self):
        if self.is_connected:
            self.is_connected = False
            self._disconnected()


@pytest.fixture
def peer():
    return FakeTransport()
