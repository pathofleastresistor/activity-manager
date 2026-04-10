"""Sensor platform for Activity Manager."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    ATTR_CATEGORY,
    ATTR_FREQUENCY_MS,
    ATTR_ICON,
    ATTR_ID,
    ATTR_LAST_COMPLETED,
    ATTR_NAME,
    DEFAULT_ICON,
    DOMAIN,
)
from .coordinator import ActivityManagerCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Activity Manager sensors from a config entry."""
    coordinator: ActivityManagerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Store callback on coordinator so it can add entities for new activities.
    coordinator.async_add_entities = async_add_entities

    entities = [
        ActivityEntity(coordinator, item[ATTR_ID])
        for item in (coordinator.data or [])
    ]
    async_add_entities(entities)


class ActivityEntity(CoordinatorEntity[ActivityManagerCoordinator], SensorEntity):
    """Sensor entity representing a single recurring activity.

    Reads all state live from coordinator.data so it is never stale.
    CoordinatorEntity automatically calls async_write_ha_state() whenever
    the coordinator calls async_set_updated_data().
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: ActivityManagerCoordinator,
        activity_id: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._activity_id = activity_id
        activity = self._activity
        # Prefix unique_id with entry_id to avoid collisions across lists.
        self._attr_unique_id = f"{coordinator.entry_id}_{activity_id}"
        self.entity_id = "sensor." + slugify(
            activity.get(ATTR_CATEGORY, "") + "_" + activity.get(ATTR_NAME, "")
        )

    @property
    def _activity(self) -> dict[str, Any]:
        """Live lookup into coordinator data — never stale."""
        return next(
            (
                item
                for item in (self.coordinator.data or [])
                if item[ATTR_ID] == self._activity_id
            ),
            {},
        )

    @property
    def name(self) -> str:
        """Return the activity name."""
        return self._activity.get(ATTR_NAME, "")

    @property
    def state(self) -> str:
        """Return the due datetime as an ISO 8601 string."""
        activity = self._activity
        last_completed_str = activity.get(ATTR_LAST_COMPLETED)
        frequency_ms = activity.get(ATTR_FREQUENCY_MS, 0)

        if not last_completed_str:
            return dt_util.now().isoformat()

        last_completed = dt_util.parse_datetime(last_completed_str)
        if last_completed is None:
            return dt_util.now().isoformat()

        due = dt_util.as_local(last_completed) + timedelta(milliseconds=frequency_ms)
        return due.isoformat()

    @property
    def icon(self) -> str:
        """Return the activity icon."""
        return self._activity.get(ATTR_ICON, DEFAULT_ICON)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        activity = self._activity
        return {
            ATTR_CATEGORY: activity.get(ATTR_CATEGORY),
            ATTR_LAST_COMPLETED: activity.get(ATTR_LAST_COMPLETED),
            ATTR_FREQUENCY_MS: activity.get(ATTR_FREQUENCY_MS),
            ATTR_ID: activity.get(ATTR_ID),
            "integration": DOMAIN,
            # Expose entry_id and list title so the card can discover available lists.
            "entry_id": self.coordinator.entry_id,
            "list_title": self.coordinator.title,
        }
