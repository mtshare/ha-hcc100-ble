"""Zone output state, deliberately separate from heating demand/valve position."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Hcc100ConfigEntry
from .entity import Hcc100Entity


async def async_setup_entry(
    hass, entry: Hcc100ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def add_zones():
        additions = []
        for zone_id in coordinator.data.zones.keys() - seen:
            additions.append(Hcc100ZoneOutputs(coordinator, zone_id))
            seen.add(zone_id)
        if additions:
            async_add_entities(additions)

    add_zones()
    entry.async_on_unload(coordinator.async_add_listener(add_zones))


class Hcc100ZoneOutputs(Hcc100Entity, BinarySensorEntity):
    _attr_translation_key = "outputs_open"
    _attr_icon = "mdi:valve"

    def __init__(self, coordinator, zone_id):
        super().__init__(coordinator, zone_id)
        self._attr_unique_id = f"{self.serial}_zone_{zone_id}_outputs_open"

    @property
    def is_on(self):
        return self.zone.outputs_open if self.zone else None

    @property
    def extra_state_attributes(self):
        if not self.zone:
            return {}
        return {
            "assigned_mask": self.zone.assigned_mask,
            "open_mask": self.zone.open_mask,
            "closed_mask": self.zone.closed_mask,
            "masks_consistent": self.zone.masks_consistent,
        }
