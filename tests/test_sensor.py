"""Tests for ActivityEntity sensor."""
from __future__ import annotations

import pytest

from custom_components.activity_manager.const import (
    ATTR_LAST_COMPLETED,
    DOMAIN,
)
from custom_components.activity_manager.coordinator import ActivityManagerCoordinator
from custom_components.activity_manager.sensor import ActivityEntity

from .conftest import SAMPLE_ACTIVITIES


@pytest.fixture
async def coordinator(hass, mock_config_entry, mock_persistence, mock_save):
    """Return a loaded coordinator."""
    mock_config_entry.add_to_hass(hass)
    coord = ActivityManagerCoordinator(hass, mock_config_entry)
    await coord.async_load()
    return coord


async def test_state_is_string(coordinator):
    """Entity state must be a string (ISO datetime), not a datetime object."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    state = entity.state
    assert isinstance(state, str)
    # Basic ISO 8601 sanity check
    assert "T" in state


async def test_entity_id_no_recursion(coordinator):
    """Accessing entity_id must not raise RecursionError."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    try:
        eid = entity.entity_id
    except RecursionError:
        pytest.fail("entity_id caused infinite recursion")
    assert isinstance(eid, str)
    assert eid.startswith("sensor.")


async def test_has_entity_name_is_class_attribute(coordinator):
    """_attr_has_entity_name must be True on the class or its instances."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    # Check via instance (handles both direct class attr and property on base class)
    assert entity._attr_has_entity_name is True


async def test_entity_reflects_coordinator_update(coordinator, hass):
    """After coordinator update, entity state reflects the new last_completed."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    # Simulate HA adding the entity
    entity.hass = hass

    original_state = entity.state

    new_ts = "2026-04-08T12:00:00+00:00"
    await coordinator.async_update_activity(SAMPLE_ACTIVITIES[0]["id"], last_completed=new_ts)

    # The _activity property does a live lookup — state must reflect new data
    assert entity.state != original_state
    assert entity.extra_state_attributes[ATTR_LAST_COMPLETED] == new_ts


async def test_extra_state_attributes_keys(coordinator):
    """Extra state attributes contain the expected keys including entry_id and list_title."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    attrs = entity.extra_state_attributes
    for key in ("category", "last_completed", "frequency_ms", "id", "integration", "entry_id", "list_title"):
        assert key in attrs, f"Missing key: {key}"


async def test_unique_id_prefixed_with_entry_id(coordinator):
    """unique_id must be prefixed with entry_id to avoid collisions across lists."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    assert entity._attr_unique_id.startswith(coordinator.entry_id + "_")
    assert entity._attr_unique_id.endswith(SAMPLE_ACTIVITIES[0]["id"])


async def test_name_returns_activity_name(coordinator):
    """Entity name matches the activity name."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    assert entity.name == "Water Plants"


async def test_icon_returns_activity_icon(coordinator):
    """Entity icon matches the activity icon."""
    entity = ActivityEntity(coordinator, SAMPLE_ACTIVITIES[0]["id"])
    assert entity.icon == "mdi:flower"
