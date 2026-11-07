"""HA Bluetooth connection selection, lifecycle and polling."""

import logging
from datetime import timedelta

from bleak import BleakClient
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble import ControllerState, Hcc100Client, Hcc100Error
from .ble.transport import BleakTransport
from .const import CONF_FINGERPRINT, CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def create_client(
    hass: HomeAssistant, address: str, fingerprint: str | None = None
) -> Hcc100Client:
    device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if device is None:
        raise UpdateFailed("HCC100 not reachable: enable its Bluetooth window and check range")

    async def connector(device, disconnected_callback) -> BleakClient:
        return await establish_connection(
            BleakClientWithServiceCache,
            device,
            device.name or "HCC100",
            disconnected_callback=disconnected_callback,
        )

    return Hcc100Client(BleakTransport(device, connector), expected_fingerprint=fingerprint)


class Hcc100Coordinator(DataUpdateCoordinator[ControllerState]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
        )
        self.entry = entry
        self.client: Hcc100Client | None = None

    async def _async_update_data(self) -> ControllerState:
        try:
            if self.client is None or not self.client.ready:
                if self.client:
                    await self.client.close()
                self.client = await create_client(
                    self.hass, self.entry.data[CONF_ADDRESS], self.entry.data[CONF_FINGERPRINT]
                )
            return await self.client.read_state()
        except (Hcc100Error, BleakError, OSError, TimeoutError, ValueError) as exc:
            if self.client:
                await self.client.close()
                self.client = None
            raise UpdateFailed(str(exc)) from exc

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        if self.client:
            await self.client.close()
            self.client = None
