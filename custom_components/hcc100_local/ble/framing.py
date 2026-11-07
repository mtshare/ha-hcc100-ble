"""RCP framing observed on HCC100 firmware 1.2.0.0.

Transport descriptors never consume cipher bytes. Sequence gaps invalidate the
session: skipping a ciphertext byte would permanently shift the shared stream.
"""

from dataclasses import dataclass
from math import ceil

from .errors import ProtocolError

ENCRYPTED = 0x80
HANDSHAKE = 0x40
SINGLE = 0x00
START = 0x02
DATA = 0x0C
END = 0x04
MAX_MESSAGE = 65535


@dataclass(frozen=True)
class Message:
    flags: int
    payload: bytes

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & ENCRYPTED)

    @property
    def handshake(self) -> bool:
        return bool(self.flags & HANDSHAKE)


class FrameWriter:
    def __init__(self, payload_limit: int = 178) -> None:
        if not 4 <= payload_limit <= 255:
            raise ValueError("Payload limit must be between 4 and 255")
        self.payload_limit = payload_limit
        self.sequence = 0

    def _frame(self, flags: int, payload: bytes) -> bytes:
        result = bytes((flags, 0, len(payload), self.sequence)) + payload
        self.sequence = (self.sequence + 1) & 0xFF
        return result

    def encode(self, payload: bytes, flags: int) -> list[bytes]:
        if flags not in (HANDSHAKE, ENCRYPTED):
            raise ValueError("Unsupported outgoing message flags")
        if len(payload) > MAX_MESSAGE:
            raise ProtocolError("RCP message is too large")
        if len(payload) <= self.payload_limit:
            return [self._frame(flags | SINGLE, payload)]
        count = ceil(len(payload) / self.payload_limit)
        descriptor = len(payload).to_bytes(2, "big") + count.to_bytes(2, "big")
        frames = [self._frame(flags | START, descriptor)]
        frames.extend(
            self._frame(flags | DATA, payload[i : i + self.payload_limit])
            for i in range(0, len(payload), self.payload_limit)
        )
        frames.append(self._frame(flags | END, b""))
        return frames


class FrameReader:
    def __init__(self) -> None:
        self._sequence: int | None = None
        self._pending: bytearray | None = None
        self._flags = 0
        self._length = 0
        self._count = 0
        self._received = 0

    def feed(self, data: bytes) -> Message | None:
        if len(data) < 4 or len(data) != data[2] + 4 or data[1] != 0:
            raise ProtocolError("Invalid RCP frame length or reserved byte")
        flags, sequence, payload = data[0], data[3], data[4:]
        if self._sequence is not None and sequence != (self._sequence + 1) & 0xFF:
            raise ProtocolError("RCP receive sequence gap; reconnect required")
        self._sequence = sequence
        kind = flags & 0x0E
        message_flags = flags & (HANDSHAKE | ENCRYPTED)
        if message_flags not in (HANDSHAKE, ENCRYPTED):
            raise ProtocolError("Unsupported RCP message flags")
        if kind == SINGLE:
            if self._pending is not None:
                raise ProtocolError("Single message inside fragmented message")
            return Message(message_flags, payload)
        if kind == START:
            if self._pending is not None or len(payload) != 4:
                raise ProtocolError("Unexpected fragmentation descriptor")
            self._length = int.from_bytes(payload[:2], "big")
            self._count = int.from_bytes(payload[2:], "big")
            if not self._length or not self._count or self._count > self._length:
                raise ProtocolError("Invalid fragment length/count")
            self._pending = bytearray()
            self._flags = message_flags
            self._received = 0
            return None
        if self._pending is None or message_flags != self._flags:
            raise ProtocolError("Fragment without a matching start")
        if kind == DATA:
            self._received += 1
            self._pending.extend(payload)
            if self._received > self._count or len(self._pending) > self._length:
                raise ProtocolError("Fragmented response exceeds declared size")
            return None
        if kind == END:
            if payload or self._received != self._count or len(self._pending) != self._length:
                raise ProtocolError("Incomplete fragmented response")
            result = Message(self._flags, bytes(self._pending))
            self._pending = None
            return result
        raise ProtocolError("Unknown RCP packet type")
