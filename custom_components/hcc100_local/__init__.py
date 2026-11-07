"""Experimental, local and read-only Resideo HCC100 integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import Hcc100Coordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]
type Hcc100ConfigEntry = ConfigEntry[Hcc100Coordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Hcc100ConfigEntry) -> bool:
    coordinator = Hcc100Coordinator(hass, entry)
    try:
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await coordinator.async_shutdown()
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Hcc100ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_shutdown()
        return True
    return False


async def _async_options_updated(hass: HomeAssistant, entry: Hcc100ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
