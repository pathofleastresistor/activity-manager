"""Tests for ActivityManagerCoordinator."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from custom_components.activity_manager.const import (
    ATTR_CATEGORY,
    ATTR_FREQUENCY_MS,
    ATTR_ID,
    ATTR_LAST_COMPLETED,
    ATTR_NAME,
    DOMAIN,
    EVENT_UPDATED,
)
from custom_components.activity_manager.coordinator import ActivityManagerCoordinator

from .conftest import LEGACY_ACTIVITY, SAMPLE_ACTIVITIES


@pytest.fixture
async def coordinator(hass, mock_config_entry, mock_persistence, mock_save):
    """Return a loaded coordinator with sample data."""
    mock_config_entry.add_to_hass(hass)
    coord = ActivityManagerCoordinator(hass, mock_config_entry)
    await coord.async_load()
    return coord


@pytest.fixture
async def empty_coordinator(hass, mock_config_entry, mock_empty_persistence, mock_save):
    """Return a loaded coordinator with no data."""
    mock_config_entry.add_to_hass(hass)
    coord = ActivityManagerCoordinator(hass, mock_config_entry)
    await coord.async_load()
    return coord


@pytest.fixture
async def two_coordinators(hass, mock_config_entry, mock_config_entry_2, mock_save):
    """Return two coordinators for multi-instance tests."""
    mock_config_entry.add_to_hass(hass)
    mock_config_entry_2.add_to_hass(hass)

    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=list(SAMPLE_ACTIVITIES),
        ),
    ):
        coord1 = ActivityManagerCoordinator(hass, mock_config_entry)
        await coord1.async_load()

    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=[],
        ),
    ):
        coord2 = ActivityManagerCoordinator(hass, mock_config_entry_2)
        await coord2.async_load()

    return coord1, coord2


async def test_load_activities(coordinator):
    """Coordinator loads sample activities from disk."""
    assert len(coordinator.data) == 2
    assert coordinator.data[0][ATTR_NAME] == "Water Plants"
    assert coordinator.data[1][ATTR_NAME] == "Oil Change"


async def test_frequency_ms_computed_on_load(coordinator):
    """frequency_ms is (re)computed from frequency dict on load."""
    item = coordinator.data[0]
    # 7 days in ms
    assert item[ATTR_FREQUENCY_MS] == 7 * 24 * 60 * 60 * 1000


async def test_legacy_integer_frequency_migrated(hass, mock_config_entry, mock_save):
    """Legacy integer frequency is converted to ms correctly."""
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=[dict(LEGACY_ACTIVITY)],
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        coord = ActivityManagerCoordinator(hass, mock_config_entry)
        await coord.async_load()

    assert len(coord.data) == 1
    assert coord.data[0][ATTR_FREQUENCY_MS] == 7 * 24 * 60 * 60 * 1000


async def test_corrupt_activity_skipped(hass, mock_config_entry, mock_save, caplog):
    """Activity missing frequency key is skipped with a warning."""
    corrupt = {"id": "baditem", "name": "No Frequency", "category": "Test"}
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=[corrupt],
        ),
    ):
        mock_config_entry.add_to_hass(hass)
        coord = ActivityManagerCoordinator(hass, mock_config_entry)
        await coord.async_load()

    assert len(coord.data) == 0
    assert "baditem" in caplog.text


async def test_add_activity(empty_coordinator, hass):
    """Adding an activity updates coordinator data and fires event."""
    events = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    item = await empty_coordinator.async_add_activity(
        name="Vacuum",
        category="Home",
        frequency={"days": 7},
        icon="mdi:vacuum",
    )

    assert len(empty_coordinator.data) == 1
    assert empty_coordinator.data[0][ATTR_NAME] == "Vacuum"
    assert ATTR_ID in item
    await hass.async_block_till_done()
    assert len(events) == 1
    assert events[0].data["action"] == "add"


async def test_add_activity_saves_to_disk(empty_coordinator, mock_save):
    """Adding an activity triggers a save."""
    await empty_coordinator.async_add_activity(
        name="Test", category="Test", frequency={"days": 1}
    )
    mock_save.assert_called_once()


async def test_remove_activity(coordinator, hass):
    """Removing an activity updates coordinator data and fires event."""
    events = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    item_id = SAMPLE_ACTIVITIES[0]["id"]
    removed = await coordinator.async_remove_activity(item_id)

    assert removed[ATTR_ID] == item_id
    assert len(coordinator.data) == 1
    assert coordinator.data[0][ATTR_NAME] == "Oil Change"
    await hass.async_block_till_done()
    assert events[0].data["action"] == "remove"


async def test_remove_unknown_activity_returns_none(coordinator):
    """Removing a non-existent id returns None without error."""
    result = await coordinator.async_remove_activity("nonexistent-id")
    assert result is None
    assert len(coordinator.data) == 2  # unchanged


async def test_update_activity(coordinator, hass):
    """Updating an activity mutates the correct item and fires event."""
    events = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    item_id = SAMPLE_ACTIVITIES[0]["id"]
    new_ts = "2026-04-08T12:00:00+00:00"
    updated = await coordinator.async_update_activity(item_id, last_completed=new_ts)

    assert updated[ATTR_LAST_COMPLETED] == new_ts
    assert coordinator.data[0][ATTR_LAST_COMPLETED] == new_ts
    # Other item unchanged
    assert coordinator.data[1][ATTR_LAST_COMPLETED] == SAMPLE_ACTIVITIES[1]["last_completed"]
    await hass.async_block_till_done()
    assert events[0].data["action"] == "updated"


async def test_update_frequency_recomputes_ms(coordinator):
    """Updating frequency also recomputes frequency_ms."""
    item_id = SAMPLE_ACTIVITIES[0]["id"]
    await coordinator.async_update_activity(item_id, frequency={"days": 14})

    assert coordinator.data[0][ATTR_FREQUENCY_MS] == 14 * 24 * 60 * 60 * 1000


async def test_update_unknown_activity_returns_none(coordinator):
    """Updating a non-existent id returns None without error."""
    result = await coordinator.async_update_activity("nonexistent-id", category="X")
    assert result is None
    assert len(coordinator.data) == 2  # unchanged


async def test_data_immutability_between_mutations(coordinator):
    """Each mutation creates a new list; the old snapshot is not mutated."""
    snapshot_before = coordinator.data
    item_id = SAMPLE_ACTIVITIES[0]["id"]
    await coordinator.async_update_activity(item_id, last_completed="2026-04-08T00:00:00+00:00")

    # coordinator.data is a new list object after the update
    assert coordinator.data is not snapshot_before


async def test_coordinator_exposes_entry_id_and_title(mock_config_entry, mock_persistence, mock_save, hass):
    """Coordinator exposes entry_id and title for card discovery."""
    mock_config_entry.add_to_hass(hass)
    coord = ActivityManagerCoordinator(hass, mock_config_entry)
    await coord.async_load()

    assert coord.entry_id == mock_config_entry.entry_id
    assert coord.title == "Home"


async def test_two_coordinators_are_isolated(two_coordinators):
    """Two coordinators operate on independent data."""
    coord1, coord2 = two_coordinators

    # coord1 has 2 activities from SAMPLE_ACTIVITIES
    assert len(coord1.data) == 2
    # coord2 starts empty
    assert len(coord2.data) == 0

    # Mutating coord2 doesn't affect coord1
    await coord2.async_add_activity(name="Social Meet", category="Friends", frequency={"days": 30})
    assert len(coord2.data) == 1
    assert len(coord1.data) == 2


async def test_event_includes_entry_id(empty_coordinator, hass, mock_config_entry):
    """EVENT_UPDATED includes entry_id so subscribers can identify the source list."""
    events = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    await empty_coordinator.async_add_activity(
        name="Test", category="Test", frequency={"days": 1}
    )
    await hass.async_block_till_done()

    assert events[0].data["entry_id"] == mock_config_entry.entry_id
