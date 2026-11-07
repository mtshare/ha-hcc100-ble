"""Discover, probe, and pin the selected HCC100's certificate."""

from typing import Any

import probatio as vol
from bleak.exc import BleakError
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
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


class Hcc100ConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._address: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        self._address = discovery_info.address
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_user()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            address = user_input[CONF_ADDRESS].strip().upper()
            client = None
            try:
                client = await create_client(self.hass, address)
                info = await client.open()
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured(updates={CONF_ADDRESS: address})
                return self.async_create_entry(
                    title=f"HCC100 {info.serial[-6:]}",
                    data={
                        CONF_ADDRESS: address,
                        CONF_SERIAL: info.serial,
                        CONF_FINGERPRINT: info.certificate_fingerprint,
                    },
                )
            except AuthenticationError:
                errors["base"] = "authentication_failed"
            except (Hcc100Error, BleakError, UpdateFailed, OSError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            finally:
                if client:
                    await client.close()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ADDRESS, default=self._address or ""): str}),
            errors=errors,
        )

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
