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
class ControllerState:
    device: DeviceInfo
    zones: dict[int, ZoneState]
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
