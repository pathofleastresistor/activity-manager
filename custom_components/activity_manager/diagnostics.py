"""Diagnostics support for Activity Manager."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_CATEGORY,
    ATTR_FREQUENCY,
    ATTR_FREQUENCY_MS,
    ATTR_ID,
    ATTR_NAME,
    DOMAIN,
)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for an Activity Manager config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return {"error": "coordinator not found"}

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
        "activity_count": len(coordinator.data or []),
        "activities": [
            {
                ATTR_ID: item.get(ATTR_ID),
                ATTR_NAME: item.get(ATTR_NAME),
                ATTR_CATEGORY: item.get(ATTR_CATEGORY),
                ATTR_FREQUENCY: item.get(ATTR_FREQUENCY),
                ATTR_FREQUENCY_MS: item.get(ATTR_FREQUENCY_MS),
                # last_completed intentionally omitted — reveals user behaviour (PII)
            }
            for item in (coordinator.data or [])
        ],
    }
