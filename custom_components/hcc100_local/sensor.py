"""Temperature, setpoint and count of logically open zone outputs."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import Hcc100ConfigEntry
from .entity import Hcc100Entity

DESCRIPTIONS = (
    SensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="setpoint",
        translation_key="setpoint",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="demand",
        translation_key="demand",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
    ),
    SensorEntityDescription(key="open_count", translation_key="open_count", icon="mdi:valve"),
)


async def async_setup_entry(
    hass, entry: Hcc100ConfigEntry, async_add_entities: AddEntitiesCallback
):
    coordinator = entry.runtime_data
    seen = set()

    @callback
    def add_zones():
        additions = []
        for zone_id in coordinator.data.zones.keys() - seen:
            additions.extend(Hcc100ZoneSensor(coordinator, zone_id, d) for d in DESCRIPTIONS)
            seen.add(zone_id)
        if additions:
            async_add_entities(additions)

    async_add_entities([Hcc100FirmwareSensor(coordinator)])
    add_zones()
    entry.async_on_unload(coordinator.async_add_listener(add_zones))


class Hcc100ZoneSensor(Hcc100Entity, SensorEntity):
    def __init__(self, coordinator, zone_id, description):
        super().__init__(coordinator, zone_id)
        self.entity_description = description
        self._attr_unique_id = f"{self.serial}_zone_{zone_id}_{description.key}"

    @property
    def native_value(self):
        return getattr(self.zone, self.entity_description.key, None)


class Hcc100FirmwareSensor(Hcc100Entity, SensorEntity):
    _attr_translation_key = "firmware"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{self.serial}_firmware"

    @property
    def native_value(self):
        return self.coordinator.data.device.firmware
