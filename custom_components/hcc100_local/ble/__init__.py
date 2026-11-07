"""Standalone protocol library, also bundled inside the custom integration."""

from .client import Hcc100Client
from .errors import AuthenticationError, ConnectionLost, Hcc100Error, ProtocolError
from .models import ControllerState, DeviceInfo, ZoneState

__all__ = [
    "AuthenticationError",
    "ConnectionLost",
    "ControllerState",
    "DeviceInfo",
    "Hcc100Client",
    "Hcc100Error",
    "ProtocolError",
    "ZoneState",
]
