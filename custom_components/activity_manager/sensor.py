"""Platform for light integration."""
from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util import slugify
from homeassistant.util import dt
from datetime import datetime, timedelta
from homeassistant.helpers.entity import generate_entity_id

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    # Add devices
    _LOGGER.debug("Sensor activities: %s", "here")

    data = hass.data[DOMAIN]
    activities = []
    for item in data.items:
        activities.append(ActivityEntity(hass, discovery_info, item))

    add_entities(activities)

async def async_setup_entry(hass, config_entry, async_add_devices):
    """Setup sensor platform."""
    
    data = hass.data[DOMAIN]
    activities = []
    for item in data.items:
        activities.append(ActivityEntity(hass, config_entry.data, item))

    _LOGGER.debug("Sensor activities: %s", activities)

    async_add_devices(activities, True)

class ActivityEntity(SensorEntity):
    """Representation of a sensor."""
    def __init__(self, hass, config, activity) -> None:
        """Initialize the sensor."""
        _attr_has_entity_name = True
        self._config = config
        self._activity = activity
        self.entity_id = "sensor." + slugify(self._activity["category"] + "_" + self._activity["name"])
        self._attributes = {
            "category": self._activity["category"],
            "last_completed": self._activity["last_completed"],
            "frequency_ms": self._activity["frequency_ms"],
            "friendly_name": self._activity["name"],
        }

    @property
    def unique_id(self):
        """Return a unique ID to use for this sensor."""
        return slugify(self._activity["category"] + "_" + self._activity["name"])

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
        return dt.as_local(dt.parse_datetime(self._activity["last_completed"])) \
            + timedelta(milliseconds=self._activity["frequency_ms"])

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
        # self._state = self.hass.data[DOMAIN]["temperature"]
        _LOGGER.debug("Updating activity: %s", self)
