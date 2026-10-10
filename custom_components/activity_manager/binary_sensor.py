"""Binary sensor platform for Activity Manager."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import ActivityManagerCoordinator
from .summary import SummaryEntity, async_setup_summary_platform

SUMMARY_METRICS = ("has_due",)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up "has due activities" binary sensors from a config entry."""
    coordinator: ActivityManagerCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_setup_summary_platform(
        config_entry,
        coordinator,
        async_add_entities,
        "binary_sensor",
        lambda key, name: [HasDueBinarySensor(coordinator, "has_due", key, name)],
        SUMMARY_METRICS,
    )


class HasDueBinarySensor(SummaryEntity, BinarySensorEntity):
    """On while the list (or category) has any due or overdue activity."""

    _attr_icon = "mdi:clipboard-alert-outline"

    @property
    def is_on(self) -> bool:
        """Return True when at least one activity is due or overdue."""
        return self.summary.due_count > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Add the names of the due activities."""
        attrs = super().extra_state_attributes
        attrs["activities"] = self.summary.due
        return attrs
