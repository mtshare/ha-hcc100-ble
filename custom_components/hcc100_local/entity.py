"""Common controller/zone identity and availability."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .ble.models import ZoneState
from .const import CONF_SERIAL, DOMAIN
from .coordinator import Hcc100Coordinator


class Hcc100Entity(CoordinatorEntity[Hcc100Coordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: Hcc100Coordinator, zone_id: int | None = None) -> None:
        super().__init__(coordinator)
        self.zone_id = zone_id
        self.serial = coordinator.entry.data[CONF_SERIAL]

    @property
    def zone(self) -> ZoneState | None:
        return self.coordinator.data.zones.get(self.zone_id)

    @property
    def available(self) -> bool:
        return super().available and (self.zone_id is None or self.zone is not None)

    @property
    def device_info(self) -> DeviceInfo:
        controller = (DOMAIN, self.serial)
        if self.zone_id is None:
            return DeviceInfo(
                identifiers={controller},
                name=f"HCC100 {self.serial[-6:]}",
                manufacturer="Resideo",
                model="HCC100",
                sw_version=self.coordinator.data.device.firmware,
            )
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.serial}_zone_{self.zone_id}")},
            name=self.zone.name if self.zone else f"Zone {self.zone_id}",
            manufacturer="Resideo",
            model="HCC100 zone",
            via_device=controller,
        )
