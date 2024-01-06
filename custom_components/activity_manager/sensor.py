from __future__ import annotations

import json
import logging
import uuid
import voluptuous as vol

from .const import DOMAIN
from homeassistant.components import homeassistant
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.json import save_json
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import slugify
from homeassistant.util import dt
from homeassistant.util.json import JsonArrayType, load_json_array
from datetime import datetime, timedelta

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
PERSISTENCE = ".activities_list.json"


async def async_setup_entry(hass, config_entry, async_add_devices):
    data = hass.data[DOMAIN] = ActivityManager(hass, config_entry, async_add_devices)
    await data.async_load_activities()
    activities = []

    for item in data.items:
        activities.append(ActivityEntity(hass, config_entry, item))

    async_add_devices(activities, True)

    entity_registry = async_get(hass)
    for entity_id, entity_entry in entity_registry.entities.items():
        if entity_id.startswith("sensor.workout"):
            _LOGGER.debug(entity_entry)


class ActivityManager:
    """Class to hold activity data."""

    def __init__(self, hass: HomeAssistant, entry, async_add_devices) -> None:
        """Initialize the shopping list."""

        self.hass = hass
        self.async_add_devices = async_add_devices
        self.items: JsonArrayType = []
        self.activities = {}
        self.entry = entry

    async def async_add_activity(
        self, name, category, frequency, icon=None, last_completed=None, context=None
    ):
        if last_completed is None:
            last_completed = dt.now().isoformat()

        if icon is None:
            icon = "mdi:checkbox-outline"

        item = {
            "name": name,
            "category": category,
            "id": uuid.uuid4().hex,
            "last_completed": last_completed,
            "frequency": frequency,
            "frequency_ms": self._duration_to_ms(frequency),
            "icon": icon,
        }

        self.items.append(item)
        self.async_add_devices([ActivityEntity(self.hass, self.entry, item)], True)
        await self.update_entities()

        _LOGGER.debug("Added activity: %s", item)
        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "add", "item": item},
            context=context,
        )

        return item

    async def async_remove_activity(self, item_id=None, context=None):
        item = next((itm for itm in self.items if itm["id"] == item_id), None)

        entity_registry = async_get(self.hass)
        entity = next(
            (
                entry
                for idx, entry in entity_registry.entities.items()
                if entry.unique_id == item_id
            ),
            None,
        )

        self.items.remove(item)
        entity_registry.async_remove(entity.entity_id)
        await self.update_entities()
        _LOGGER.debug("Removed activity: %s", item)

        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "remove", "item": item},
            context=context,
        )

        return item

    async def async_update_activity(
        self,
        item_id,
        last_completed=None,
        category=None,
        frequency=None,
        context=None,
        icon=None,
    ):
        item = next((itm for itm in self.items if itm["id"] == item_id), None)

        if last_completed:
            item["last_completed"] = last_completed

        if category:
            item["category"] = category

        if frequency:
            item["frequency"] = frequency
            item["frequency_ms"] = self._duration_to_ms(frequency)

        if icon:
            item["icon"] = icon

        entity_registry = async_get(self.hass)
        for entity_id, entity_entry in entity_registry.entities.items():
            if entity_entry.unique_id == item["id"]:  # entity_entry.update()
                await self.hass.services.async_call(
                    "homeassistant",
                    "update_entity",
                    {"entity_id": entity_entry.entity_id},
                )
        await self.update_entities()
        _LOGGER.debug("Updated activity: %s", item)

        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "updated", "item": item},
            context=context,
        )

        return item

    async def update_entities(self):
        await self.hass.async_add_executor_job(self.save)

    async def async_load_activities(self) -> None:
        """Load items."""

        def load() -> JsonArrayType:
            """Load the items synchronously."""

            items = load_json_array(self.hass.config.path(PERSISTENCE))
            for item in items:
                if "frequency" not in item:
                    if "frequency_ms" in item:
                        _LOGGER.error("No frequency, using frequency_ms: %s", item)
                        continue
                    else:
                        item["frequency_ms"] = self._duration_to_ms(7)
                        _LOGGER.error("Added missing frequency: %s", item)
                        continue

                # Set frequency_ms
                item["frequency_ms"] = self._duration_to_ms(item["frequency"])

                if "icon" not in item:
                    item["icon"] = "mdi:checkbox-outline"

            return items

        self.items = await self.hass.async_add_executor_job(load)

    def save(self) -> None:
        """Save the items."""
        items = self.items

        save_json(self.hass.config.path(PERSISTENCE), items)

    def _duration_to_ms(self, frequency) -> int:
        # prior versions stored a single int for number of days
        try:
            return int(frequency) * 24 * 60 * 60 * 1000
        except:
            frequency_ms = 0
            if "days" in frequency:
                frequency_ms += frequency["days"] * 24 * 60 * 60 * 1000
            if "hours" in frequency:
                frequency_ms += frequency["hours"] * 60 * 60 * 1000
            if "minutes" in frequency:
                frequency_ms += frequency["minutes"] * 60 * 1000
            if "seconds" in frequency:
                frequency_ms += frequency["seconds"] * 1000

            return frequency_ms


class ActivityEntity(SensorEntity):
    """Representation of a sensor."""

    def __init__(self, hass, config, activity) -> None:
        """Initialize the sensor."""
        _attr_has_entity_name = True
        self._hass = hass
        self._config = config
        self._activity = activity
        self._id = self._activity["id"]
        self.entity_id = "sensor." + slugify(
            self._activity["category"] + "_" + self._activity["name"]
        )
        self._attributes = {
            "category": self._activity["category"],
            "last_completed": self._activity["last_completed"],
            "frequency_ms": self._activity["frequency_ms"],
            "friendly_name": self._activity["name"],
            "id": self._activity["id"],
            "integration": DOMAIN,
        }

    @property
    def unique_id(self):
        """Return a unique ID to use for this sensor."""
        # return slugify(self._activity["category"] + "_" + self._activity["name"])
        return self._id

    @property
    def entity_id(self):
        return self.entity_id

    def entity_id(self, value):
        self.entity_id = value

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._activity["name"]

    @property
    def state(self):
        """Return the state of the sensor."""
        return dt.as_local(
            dt.parse_datetime(self._activity["last_completed"])
        ) + timedelta(milliseconds=self._activity["frequency_ms"])

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def icon(self):
        """Return the state of the sensor."""
        return self._activity["icon"]

    def update(self) -> None:
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        for item in self._hass.data[DOMAIN].items:
            if self._id == item["id"]:
                self._attributes["last_completed"] = item["last_completed"]
                self._attributes["category"] = item["category"]
                self._attributes["frequency_ms"] = item["frequency_ms"]
                self._attributes["icon"] = item["icon"]
