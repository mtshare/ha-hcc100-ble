"""Guided HCC100 pairing that mirrors the technician app.

The controller stays invisible until its physical Bluetooth button is pressed.
The flow therefore walks the user through it: a first press makes the device
advertise so it can be discovered, then a second press opens the connection
window where the autonomous P-256 handshake runs.
"""

import asyncio
from typing import Any

import probatio as vol
from bleak.exc import BleakError
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import UpdateFailed

from .ble import AuthenticationError, Hcc100Error
from .const import (
    CONF_FINGERPRINT,
    CONF_POLL_INTERVAL,
    CONF_SERIAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .coordinator import create_client

# How long to keep scanning for the controller after the first button press,
# and how often to re-check Home Assistant's discovered devices. The pairing
# window lasts about a minute, so stay well inside it.
DISCOVERY_TIMEOUT = 40.0
DISCOVERY_INTERVAL = 1.0

# The connection window can close quickly; retry the handshake a few times
# within the second-press window before giving up.
HANDSHAKE_ATTEMPTS = 3
HANDSHAKE_RETRY_DELAY = 2.0

# The HCC100 GATT service. The advertised name is user-editable (e.g.
# "HCC100 Hallway"), so also match on this service to find a renamed controller.
SERVICE_UUID = "0000f300-0000-1000-8000-00805f9b34fb"


def _is_hcc100(info: BluetoothServiceInfoBleak) -> bool:
    name = info.name or ""
    if name.upper().startswith("HCC100"):
        return True
    return SERVICE_UUID in (info.service_uuids or [])


class Hcc100ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None
        self._name: str | None = None
        self._discovered: dict[str, str | None] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Home Assistant saw the controller advertise after the first press."""
        address = discovery_info.address.upper()
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()
        self._address = address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {"name": discovery_info.name or "HCC100"}
        return await self.async_step_confirm()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """First press: discover the controller, or accept a typed address.

        Leaving the address empty searches automatically after the button
        press. Typing the Bluetooth address skips discovery and goes straight
        to the handshake, which is the reliable path when the controller does
        not surface in the scan.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            address = (user_input.get(CONF_ADDRESS) or "").strip().upper()
            if address:
                self._address, self._name = address, None
                return await self.async_step_confirm()
            known = set(self._async_current_ids())
            self._discovered = {
                found: name
                for found, name in (await self._async_discover()).items()
                if found not in known
            }
            if not self._discovered:
                errors["base"] = "not_found"
            elif len(self._discovered) == 1:
                self._address, self._name = next(iter(self._discovered.items()))
                return await self.async_step_confirm()
            else:
                return await self.async_step_pick()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_ADDRESS): str}),
            errors=errors,
        )

    async def async_step_pick(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Several HCC100 were found: let the user choose one."""
        if user_input is not None:
            self._address = user_input[CONF_ADDRESS]
            self._name = self._discovered.get(self._address)
            return await self.async_step_confirm()
        options = {
            address: f"{name or 'HCC100'} ({address})" for address, name in self._discovered.items()
        }
        return self.async_show_form(
            step_id="pick",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS): vol.In(options)}),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second press: open the connection window and run the handshake."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(self._address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            try:
                info = await self._async_handshake()
            except AuthenticationError:
                errors["base"] = "authentication_failed"
            except (Hcc100Error, BleakError, UpdateFailed, OSError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"HCC100 {info.serial[-6:]}",
                    data={
                        CONF_ADDRESS: self._address,
                        CONF_SERIAL: info.serial,
                        CONF_FINGERPRINT: info.certificate_fingerprint,
                    },
                )
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"name": self._name or self._address or "HCC100"},
        )

    async def _async_discover(self) -> dict[str, str | None]:
        """Poll Home Assistant's discovered devices for an advertising HCC100."""
        deadline = self.hass.loop.time() + DISCOVERY_TIMEOUT
        while True:
            found = {
                info.address.upper(): info.name
                for info in async_discovered_service_info(self.hass, connectable=True)
                if _is_hcc100(info)
            }
            if found or self.hass.loop.time() >= deadline:
                return found
            await asyncio.sleep(DISCOVERY_INTERVAL)

    async def _async_handshake(self) -> Any:
        """Connect and run the handshake, retrying inside the press window."""
        assert self._address is not None
        last_exc: Exception | None = None
        for attempt in range(HANDSHAKE_ATTEMPTS):
            client = None
            try:
                client = await create_client(self.hass, self._address)
                return await client.open()
            except AuthenticationError:
                raise
            except (
                Hcc100Error,
                BleakError,
                UpdateFailed,
                OSError,
                TimeoutError,
                ValueError,
            ) as exc:
                last_exc = exc
                if attempt + 1 < HANDSHAKE_ATTEMPTS:
                    await asyncio.sleep(HANDSHAKE_RETRY_DELAY)
            finally:
                if client:
                    await client.close()
        raise last_exc  # type: ignore[misc]

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return Hcc100OptionsFlow(config_entry)


class Hcc100OptionsFlow(OptionsFlow):
    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=self._entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    ): vol.All(vol.Coerce(int), vol.Range(min=15, max=300))
                }
            ),
        )
