"""Read-only state; output masks describe logical commands, not valve position."""

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    certificate_fingerprint: str
    model: str
    firmware: str


@dataclass(frozen=True)
class ZoneState:
    zone_id: int
    name: str
    assigned_mask: int
    open_mask: int | None
    closed_mask: int | None
    temperature: float | None
    setpoint: float | None
    demand: float | None = None

    @property
    def masks_consistent(self) -> bool:
        return (
            self.open_mask is not None
            and self.closed_mask is not None
            and (self.open_mask | self.closed_mask) == self.assigned_mask
            and (self.open_mask & self.closed_mask) == 0
        )

    @property
    def outputs_open(self) -> bool | None:
        return bool(self.open_mask) if self.masks_consistent else None

    @property
    def open_count(self) -> int | None:
        return self.open_mask.bit_count() if self.masks_consistent else None


@dataclass(frozen=True)
class SystemState:
    """Controller-wide status read without a ZoneID.

    Reconstructed from the app's general status and sensor read groups.
    Pump (235) and mode (248) are kept as raw codes: the 1/2 mode mapping and
    the pump's special value 2 are not yet corroborated, so no label or on/off
    meaning is implied here.
    """

    heat_demand: float | None = None  # 236, %
    cool_demand: float | None = None  # 237, %
    supply_setpoint: float | None = None  # 244, °C
    max_supply_temp: float | None = None  # 215, °C
    supply_temp: float | None = None  # 245, °C (327.67 = unavailable)
    outdoor_temp: float | None = None  # 247, °C (327.67 = unavailable)
    pump: int | None = None  # 235, raw code 0/1/2
    mode: int | None = None  # 248, raw code 1/2


@dataclass(frozen=True)
class ControllerState:
    device: DeviceInfo
    zones: dict[int, ZoneState]
    system: SystemState | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
