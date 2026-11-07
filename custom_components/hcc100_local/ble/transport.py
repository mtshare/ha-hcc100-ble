"""Bleak transport; Home Assistant can inject its connection/adaptor selection."""

from collections.abc import Awaitable, Callable
from typing import Protocol

from bleak import BleakClient
from bleak.backends.device import BLEDevice

TX_UUID = "0000b835-0000-1000-8000-00805f9b34fb"
RX_UUID = "0000b836-0000-1000-8000-00805f9b34fb"
SERVICE_UUID = "0000f300-0000-1000-8000-00805f9b34fb"
Notification = Callable[[bytes], None]


class Transport(Protocol):
    @property
    def is_connected(self) -> bool: ...
    @property
    def payload_limit(self) -> int: ...
    def set_disconnected_callback(self, callback: Callable[[], None]) -> None: ...
    async def connect(self) -> None: ...
    async def start_notify(self, callback: Notification) -> None: ...
    async def write(self, data: bytes) -> None: ...
    async def disconnect(self) -> None: ...


Connector = Callable[[BLEDevice, Callable[[BleakClient], None]], Awaitable[BleakClient]]


class BleakTransport:
    def __init__(
        self,
        device: BLEDevice,
        connector: Connector | None = None,
        payload_limit: int | None = None,
    ) -> None:
        self.device = device
        self._connector = connector
        self._payload_override = payload_limit
        self._client: BleakClient | None = None
        self._disconnected_callback: Callable[[], None] = lambda: None

    @property
    def is_connected(self) -> bool:
        return bool(self._client and self._client.is_connected)

    @property
    def payload_limit(self) -> int:
        # BLE ATT MTU includes three ATT bytes, plus our four-byte RCP header.
        # BlueZ may report only 23; small RCP fragments remain safe in that case.
        limit = max(4, min(178, (self._client.mtu_size if self._client else 23) - 7))
        return min(limit, self._payload_override) if self._payload_override else limit

    def set_disconnected_callback(self, callback: Callable[[], None]) -> None:
        self._disconnected_callback = callback

    def _on_disconnect(self, _: BleakClient) -> None:
        self._disconnected_callback()

    async def connect(self) -> None:
        if self._connector:
            self._client = await self._connector(self.device, self._on_disconnect)
        else:
            self._client = BleakClient(
                self.device, disconnected_callback=self._on_disconnect, timeout=30
            )
            await self._client.connect()

    async def start_notify(self, callback: Notification) -> None:
        assert self._client is not None
        await self._client.start_notify(RX_UUID, lambda _, data: callback(bytes(data)))

    async def write(self, data: bytes) -> None:
        assert self._client is not None
        await self._client.write_gatt_char(TX_UUID, data, response=True)

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.disconnect()
            finally:
                self._client = None
