"""An independent HCC100 reader: no Frida, app binary, cloud, or captured keys."""

import asyncio
import json
from typing import Any

from .crypto import CLIENT_HELLO, DeviceHello, SessionCipher, create_client_hello
from .errors import AuthenticationError, ConnectionLost, Hcc100Error, ProtocolError
from .framing import ENCRYPTED, HANDSHAKE, FrameReader, FrameWriter, Message
from .models import ControllerState, DeviceInfo, SystemState, ZoneState
from .transport import Transport

SESSION = "WickAppDIY"
_ALLOWED_COMMANDS = frozenset({"GetDeviceInfo", "GetName", "GetList"})

# Supply/outdoor sensors report this value when a reading is unavailable; the
# app shows "--" for it. Treat it as unknown instead of a temperature.
_TEMP_UNAVAILABLE = 327.67


def _temperature(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and -30 <= value <= 100:
        return float(value)
    return None


def _percentage(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 100:
        return float(value)
    return None


def _flow_temperature(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if abs(value - _TEMP_UNAVAILABLE) < 0.01:
            return None
        if -40 <= value <= 150:
            return float(value)
    return None


def _code(value: Any, allowed: frozenset[int]) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value in allowed:
        return value
    return None


def _mask(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1 << 20:
        return value
    return None


class Hcc100Client:
    def __init__(
        self,
        transport: Transport,
        *,
        expected_fingerprint: str | None = None,
        timeout: float = 20,
    ) -> None:
        self.transport = transport
        self.expected_fingerprint = expected_fingerprint
        self.timeout = timeout
        self.device_info: DeviceInfo | None = None
        self._reader = FrameReader()
        self._writer = FrameWriter()
        self._queue: asyncio.Queue[Message | Hcc100Error] = asyncio.Queue(maxsize=64)
        self._cipher: SessionCipher | None = None
        self._phase = "closed"
        self._request_lock = asyncio.Lock()
        self._open_lock = asyncio.Lock()
        self._zone_names: dict[int, str] = {}
        self.received_messages = 0
        self.sent_messages = 0
        transport.set_disconnected_callback(self._on_disconnect)

    @property
    def ready(self) -> bool:
        return self._phase == "ready" and self.transport.is_connected

    def _fail(self, exc: Hcc100Error) -> None:
        self._phase = "failed"
        self._cipher = None
        if self._queue.full():
            while not self._queue.empty():
                self._queue.get_nowait()
        self._queue.put_nowait(exc)

    def _on_disconnect(self) -> None:
        if self._phase not in ("closed", "connecting"):
            self._fail(ConnectionLost("HCC100 Bluetooth connection closed"))

    def _notification(self, data: bytes) -> None:
        if self._phase in ("closed", "failed"):
            return
        try:
            message = self._reader.feed(data)
            if message is None:
                return
            if message.encrypted:
                if self._cipher is None or self._phase not in ("verified_auth", "ready"):
                    raise ProtocolError("Encrypted data before session negotiation completed")
                message = Message(ENCRYPTED, self._cipher.transform(message.payload))
            elif self._phase == "await_auth":
                if (
                    not message.handshake
                    or len(message.payload) != 36
                    or message.payload[:4] != b"\x00\x00\x00\x20"
                    or self._cipher is None
                ):
                    raise AuthenticationError("Unexpected HCC100 handshake confirmation")
                # The 32 encrypted confirmation bytes precede all application
                # traffic in the SAME bidirectional CTR stream. Their meaning
                # is not assumed; a model query must also succeed before ready.
                self._cipher.transform(message.payload[4:])
                self._phase = "verified_auth"
            self.received_messages += 1
            self._queue.put_nowait(message)
        except asyncio.QueueFull:
            self._fail(ProtocolError("Receive queue overflow; session cannot be reused"))
        except Hcc100Error as exc:
            self._fail(exc)

    async def _next(self) -> Message:
        item = await self._queue.get()
        if isinstance(item, Hcc100Error):
            raise item
        return item

    async def _send(self, payload: bytes, flags: int) -> None:
        for frame in self._writer.encode(payload, flags):
            await self.transport.write(frame)
        self.sent_messages += 1

    async def open(self) -> DeviceInfo:
        async with self._open_lock:
            if self.ready and self.device_info:
                return self.device_info
            self._reader = FrameReader()
            self._queue = asyncio.Queue(maxsize=64)
            self._zone_names = {}
            self._cipher = None
            self.device_info = None
            self._phase = "connecting"
            try:
                async with asyncio.timeout(self.timeout + 30):
                    await self.transport.connect()
                    # HA's retry connector can emit disconnect callbacks for
                    # unsuccessful attempts before returning a connected client.
                    self._phase = "await_device"
                    self._writer = FrameWriter(self.transport.payload_limit)
                    await self.transport.start_notify(self._notification)
                    await self._send(CLIENT_HELLO, HANDSHAKE)
                    response = await self._next()
                    if not response.handshake or response.encrypted:
                        raise AuthenticationError("Expected a device handshake message")
                    hello = DeviceHello.parse(response.payload, self.expected_fingerprint)
                    payload, self._cipher = create_client_hello(hello)
                    self._phase = "await_auth"
                    await self._send(payload, HANDSHAKE)
                    confirmation = await self._next()
                    if not confirmation.handshake or self._phase != "verified_auth":
                        raise AuthenticationError("Handshake did not complete")
                    commands = await self._request({"Cmd": "GetDeviceInfo"})
                    info = next((c for c in commands if c.get("Cmd") == "DeviceInfo"), None)
                    if not info or info.get("Model") != "HCC100":
                        raise AuthenticationError("Encrypted model verification failed")
                    self.device_info = DeviceInfo(
                        hello.serial, hello.fingerprint, "HCC100", str(info.get("SwVer", "unknown"))
                    )
                    self._phase = "ready"
                    return self.device_info
            except BaseException:
                await self.close()
                raise

    async def close(self) -> None:
        self._phase = "closed"
        self._cipher = None
        self._zone_names = {}
        await self.transport.disconnect()

    async def _request(self, command: dict[str, Any]) -> list[dict[str, Any]]:
        if command.get("Cmd") not in _ALLOWED_COMMANDS:
            raise ValueError("This client only supports documented read commands")
        async with self._request_lock:
            if self._phase not in ("verified_auth", "ready") or self._cipher is None:
                raise ConnectionLost("HCC100 is not connected")
            try:
                async with asyncio.timeout(self.timeout):
                    if not self._queue.empty():
                        raise ProtocolError("Unexpected unsolicited message before a request")
                    body = json.dumps(
                        {"Session": SESSION, "Cfg": [command]},
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode()
                    encrypted = self._cipher.transform(body)
                    await self._send(encrypted, ENCRYPTED)
                    result: list[dict[str, Any]] = []
                    for _ in range(32):
                        message = await self._next()
                        if not message.encrypted:
                            raise ProtocolError("Unexpected plaintext application response")
                        try:
                            response = json.loads(message.payload.rstrip(b"\x00"))
                        except (ValueError, UnicodeDecodeError) as exc:
                            raise ProtocolError(
                                "Invalid decrypted JSON; stream lost alignment"
                            ) from exc
                        if response.get("Session") != SESSION or not isinstance(
                            response.get("Cfg"), list
                        ):
                            raise ProtocolError("Unexpected RCP response envelope")
                        for item in response["Cfg"]:
                            if not isinstance(item, dict):
                                raise ProtocolError("Invalid RCP command in response")
                            if item.get("Cmd") == "Complete":
                                return result
                            if item.get("Cmd") == "Error":
                                raise ProtocolError("HCC100 rejected the read request")
                            result.append(item)
                    raise ProtocolError("Response did not terminate")
            except BaseException:
                # A failed/aborted write or read may already have consumed CTR
                # bytes on the peer. Never retry inside this session.
                await self.close()
                raise

    async def get_parameters(self, ids: list[int], zone_id: int | None = None) -> dict[int, Any]:
        if not ids or any(not isinstance(i, int) or not 1 <= i <= 65535 for i in ids):
            raise ValueError("Invalid parameter IDs")
        command: dict[str, Any] = {"Cmd": "GetList", "Range": True, "IDs": ids}
        if zone_id is not None:
            if not 1 <= zone_id <= 8:
                raise ValueError("Zone must be between 1 and 8")
            command["ZoneID"] = zone_id
        response = await self._request(command)
        values = {
            item["ID"]: item.get("Val")
            for item in response
            if item.get("Cmd") == "Resp"
            and item.get("ID") in ids
            and (zone_id is None or item.get("ZoneID") == zone_id)
        }
        if any(i not in values for i in ids):
            raise ProtocolError("Response omitted requested parameters")
        return values

    async def read_state(self) -> ControllerState:
        await self.open()
        assert self.device_info is not None
        if not self._zone_names:
            response = await self._request({"Cmd": "GetName", "ZoneID": list(range(1, 9))})
            for item in response:
                if item.get("Cmd") != "GetName":
                    continue
                ids, names = item.get("ZoneID", []), item.get("ZoneName", [])
                if isinstance(ids, list) and isinstance(names, list):
                    self._zone_names = {
                        i: name
                        for i, name in zip(ids, names, strict=False)
                        if isinstance(i, int) and isinstance(name, str)
                    }
        zones = {}
        for zone_id in range(1, 9):
            assignment = await self.get_parameters([224], zone_id)
            assigned = _mask(assignment[224])
            if not assigned:
                continue
            # The two status groups follow the observed app's read path.
            temperatures = await self.get_parameters([230, 231, 232], zone_id)
            opened = await self.get_parameters([229, 238], zone_id)
            closed = await self.get_parameters([241, 254], zone_id)
            zones[zone_id] = ZoneState(
                zone_id,
                self._zone_names.get(zone_id, f"Zone {zone_id}"),
                assigned,
                _mask(opened[238]),
                _mask(closed[241]),
                _temperature(temperatures[230]),
                _temperature(temperatures[231]),
                demand=_percentage(opened[229]),
            )
        system = await self._read_system()
        return ControllerState(self.device_info, zones, system)

    async def _read_system(self) -> SystemState | None:
        """Read controller-wide status without a ZoneID.

        Mirrors the app's status (235/248/236/237), sensor (245/247) and
        supply (244/215) groups. Each group is best-effort: a controller that
        omits a group leaves those fields unknown without failing the whole
        read, so the existing per-zone polling is never blocked by it.
        """
        values: dict[int, Any] = {}
        for ids in ([235, 248, 236, 237], [245, 247], [244, 215]):
            try:
                values.update(await self.get_parameters(ids))
            except Hcc100Error:
                continue
        if not values:
            return None
        return SystemState(
            heat_demand=_percentage(values.get(236)),
            cool_demand=_percentage(values.get(237)),
            supply_setpoint=_flow_temperature(values.get(244)),
            max_supply_temp=_flow_temperature(values.get(215)),
            supply_temp=_flow_temperature(values.get(245)),
            outdoor_temp=_flow_temperature(values.get(247)),
            pump=_code(values.get(235), frozenset({0, 1, 2})),
            mode=_code(values.get(248), frozenset({1, 2})),
        )
