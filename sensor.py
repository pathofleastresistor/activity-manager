"""Platform for light integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    # Add devices
    data = hass.data[DOMAIN]
    activities = []
    for item in data.items:
        activities.append(ActivityEntity(item))
    # add_entities(activities)


class ActivityEntity(SensorEntity):
    """Representation of a sensor."""

    def __init__(self, activity) -> None:
        """Initialize the sensor."""
        self._state = None
        self._name = activity["name"]
        self._category = activity["category"]

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    def update(self) -> None:
        """Fetch new state data for the sensor.

        This is the only method that should fetch new data for Home Assistant.
        """
        # self._state = self.hass.data[DOMAIN]["temperature"]
