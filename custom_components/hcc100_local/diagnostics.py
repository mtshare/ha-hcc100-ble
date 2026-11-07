"""Diagnostics intentionally contain no session keys or raw packets."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "firmware": coordinator.data.device.firmware,
        "model": coordinator.data.device.model,
        "certificate_pinned": True,
        "last_update_success": coordinator.last_update_success,
        "configured_zones": len(coordinator.data.zones),
        "connection_ready": bool(coordinator.client and coordinator.client.ready),
        "received_messages": coordinator.client.received_messages if coordinator.client else 0,
        "sent_messages": coordinator.client.sent_messages if coordinator.client else 0,
    }
