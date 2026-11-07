"""Failures which must not leave an uncertain CTR session in use."""


class Hcc100Error(Exception):
    """Base protocol error."""


class ProtocolError(Hcc100Error):
    """Malformed, missing or out-of-order data."""


class AuthenticationError(Hcc100Error):
    """Unsupported identity, certificate change or unsuccessful handshake."""


class ConnectionLost(Hcc100Error):
    """The active BLE connection cannot be reused."""
