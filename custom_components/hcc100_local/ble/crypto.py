"""Ephemeral P-256 handshake and verified HCC100 session derivation."""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.x509.oid import NameOID

from .errors import AuthenticationError, ProtocolError

# Public client identifier observed in the technician app, not a secret/key.
CLIENT_HELLO = bytes.fromhex("0200deba7e")


@dataclass(frozen=True)
class DeviceHello:
    serial: str
    nonce: bytes
    certificate: x509.Certificate
    fingerprint: str

    @classmethod
    def parse(cls, payload: bytes, expected_fingerprint: str | None = None) -> "DeviceHello":
        if len(payload) < 31 or payload[0] != 2:
            raise ProtocolError("Unsupported HCC100 handshake version/length")
        certificate_length = int.from_bytes(payload[27:31], "big")
        if certificate_length != len(payload) - 31:
            raise ProtocolError("Invalid certificate length")
        try:
            certificate = x509.load_der_x509_certificate(payload[31:])
        except ValueError as exc:
            raise AuthenticationError("Invalid device certificate") from exc
        fingerprint = certificate.fingerprint(hashes.SHA256()).hex()
        if expected_fingerprint and not secrets.compare_digest(
            fingerprint, expected_fingerprint.lower().replace(":", "")
        ):
            raise AuthenticationError("The HCC100 device certificate has changed")
        serial = payload[5:11].hex().upper()
        common_names = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if len(common_names) != 1 or common_names[0].value != f"HCC100-{serial}":
            raise AuthenticationError("Certificate subject does not match the HCC100 identity")
        now = datetime.now(UTC)
        if not certificate.not_valid_before_utc <= now <= certificate.not_valid_after_utc:
            raise AuthenticationError("Device certificate is outside its validity dates")
        public_key = certificate.public_key()
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or not isinstance(
            public_key.curve, ec.SECP256R1
        ):
            raise AuthenticationError("Expected a P-256 device public key")
        return cls(serial, payload[11:27], certificate, fingerprint)


def derive_material(shared: bytes, client_nonce: bytes, device_nonce: bytes) -> tuple[bytes, bytes]:
    if len(shared) != 32 or len(client_nonce) != 16 or len(device_nonce) != 16:
        raise ProtocolError("Unexpected P-256 secret or nonce length")
    suffix = client_nonce + device_nonce
    key = hashlib.sha256(shared + b"AES-KEY" + suffix).digest()[:16]
    iv = hashlib.sha256(shared + b"AES-IV" + suffix).digest()[:16]
    return key, iv


class SessionCipher:
    """One stream for BOTH directions. Never reset it between messages."""

    def __init__(self, key: bytes, iv: bytes) -> None:
        self._stream = Cipher(algorithms.AES(key), modes.CTR(iv)).encryptor()
        self.offset = 0

    def transform(self, data: bytes) -> bytes:
        self.offset += len(data)
        return self._stream.update(data)


def create_client_hello(hello: DeviceHello) -> tuple[bytes, SessionCipher]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    nonce = secrets.token_bytes(16)
    point = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )[1:]
    shared = private_key.exchange(ec.ECDH(), hello.certificate.public_key())
    key, iv = derive_material(shared, nonce, hello.nonce)
    return point + nonce, SessionCipher(key, iv)
