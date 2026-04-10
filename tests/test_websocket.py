"""Tests for Activity Manager websocket API."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.activity_manager.const import (
    DOMAIN,
    EVENT_UPDATED,
    WS_ADD,
    WS_ITEMS,
    WS_REMOVE,
    WS_UPDATE,
)

from .conftest import SAMPLE_ACTIVITIES


@pytest.fixture
async def setup_integration(hass, mock_config_entry, mock_persistence, mock_save):
    """Set up the integration and return (hass, entry_id)."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return hass, mock_config_entry.entry_id


@pytest.fixture
async def setup_two_integrations(hass, mock_save):
    """Set up two list instances and return (hass, entry_id_1, entry_id_2)."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.activity_manager.const import DOMAIN

    entry1 = MockConfigEntry(
        domain=DOMAIN, data={"name": "Home"}, title="Home", unique_id="home",
        version=1, minor_version=3,
    )
    entry2 = MockConfigEntry(
        domain=DOMAIN, data={"name": "Social"}, title="Social", unique_id="social",
        version=1, minor_version=3,
    )

    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=list(SAMPLE_ACTIVITIES),
        ),
    ):
        entry1.add_to_hass(hass)
        await hass.config_entries.async_setup(entry1.entry_id)

    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=[],
        ),
    ):
        entry2.add_to_hass(hass)
        await hass.config_entries.async_setup(entry2.entry_id)

    await hass.async_block_till_done()
    return hass, entry1.entry_id, entry2.entry_id


def _coordinator(hass, entry_id):
    return hass.data[DOMAIN][entry_id]


async def test_ws_items_returns_list(hass, setup_integration, hass_ws_client):
    """activity_manager/items returns the full list of activities."""
    hass, entry_id = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": WS_ITEMS, "entry_id": entry_id})
    msg = await client.receive_json()

    assert msg["success"] is True
    assert isinstance(msg["result"], list)
    assert len(msg["result"]) == 2


async def test_ws_items_no_entry_id_returns_all(hass, setup_two_integrations, hass_ws_client):
    """activity_manager/items without entry_id returns all lists merged."""
    hass, entry_id_1, entry_id_2 = setup_two_integrations
    # Add one activity to the second list
    coord2 = _coordinator(hass, entry_id_2)
    await coord2.async_add_activity(name="Social", category="Friends", frequency={"days": 7})

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": WS_ITEMS})
    msg = await client.receive_json()

    assert msg["success"] is True
    # 2 from list 1 + 1 from list 2
    assert len(msg["result"]) == 3
    # Each item is tagged with its list's entry_id
    entry_ids_in_result = {item["entry_id"] for item in msg["result"]}
    assert entry_id_1 in entry_ids_in_result
    assert entry_id_2 in entry_ids_in_result


async def test_ws_items_category_filter(hass, setup_integration, hass_ws_client):
    """activity_manager/items filters by category when provided."""
    hass, entry_id = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": WS_ITEMS, "entry_id": entry_id, "category": "Garden"})
    msg = await client.receive_json()

    assert msg["success"] is True
    assert len(msg["result"]) == 1
    assert msg["result"][0]["name"] == "Water Plants"


async def test_ws_items_unknown_entry_id_returns_error(hass, setup_integration, hass_ws_client):
    """activity_manager/items with unknown entry_id returns an error."""
    hass, _ = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": WS_ITEMS, "entry_id": "nonexistent"})
    msg = await client.receive_json()

    assert msg["success"] is False


async def test_ws_add_creates_activity(hass, setup_integration, hass_ws_client):
    """activity_manager/add creates a new activity and returns it."""
    hass, entry_id = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_ADD,
        "entry_id": entry_id,
        "name": "Vacuum",
        "category": "Home",
        "frequency": {"days": 7},
        "icon": "mdi:vacuum",
    })
    msg = await client.receive_json()

    assert msg["success"] is True
    assert msg["result"]["name"] == "Vacuum"
    assert "id" in msg["result"]

    coordinator = _coordinator(hass, entry_id)
    names = [i["name"] for i in coordinator.data]
    assert "Vacuum" in names


async def test_ws_add_fires_event(hass, setup_integration, hass_ws_client):
    """activity_manager/add fires activity_manager_updated event."""
    hass, entry_id = setup_integration
    events = []
    hass.bus.async_listen(EVENT_UPDATED, lambda e: events.append(e))

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_ADD,
        "entry_id": entry_id,
        "name": "Test",
        "category": "Test",
        "frequency": {"days": 1},
    })
    await client.receive_json()
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["action"] == "add"
    assert events[0].data["entry_id"] == entry_id


async def test_ws_add_to_different_lists_are_isolated(hass, setup_two_integrations, hass_ws_client):
    """Adding to list 1 does not affect list 2."""
    hass, entry_id_1, entry_id_2 = setup_two_integrations
    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_ADD,
        "entry_id": entry_id_1,
        "name": "Home Task",
        "category": "Home",
        "frequency": {"days": 7},
    })
    await client.receive_json()

    assert len(_coordinator(hass, entry_id_1).data) == 3
    assert len(_coordinator(hass, entry_id_2).data) == 0


async def test_ws_update_sets_last_completed(hass, setup_integration, hass_ws_client):
    """activity_manager/update updates last_completed on an activity."""
    hass, entry_id = setup_integration
    item_id = SAMPLE_ACTIVITIES[0]["id"]
    new_ts = "2026-04-08T12:00:00+00:00"

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_UPDATE,
        "entry_id": entry_id,
        "item_id": item_id,
        "last_completed": new_ts,
    })
    msg = await client.receive_json()

    assert msg["success"] is True
    coordinator = _coordinator(hass, entry_id)
    updated = next(i for i in coordinator.data if i["id"] == item_id)
    assert updated["last_completed"] is not None


async def test_ws_update_unknown_id_returns_error(hass, setup_integration, hass_ws_client):
    """activity_manager/update with unknown id returns an error message."""
    hass, entry_id = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_UPDATE,
        "entry_id": entry_id,
        "item_id": "nonexistent-id",
    })
    msg = await client.receive_json()

    assert msg["success"] is False


async def test_ws_remove_deletes_activity(hass, setup_integration, hass_ws_client):
    """activity_manager/remove removes the activity from coordinator data."""
    hass, entry_id = setup_integration
    item_id = SAMPLE_ACTIVITIES[0]["id"]

    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_REMOVE,
        "entry_id": entry_id,
        "item_id": item_id,
    })
    msg = await client.receive_json()

    assert msg["success"] is True
    coordinator = _coordinator(hass, entry_id)
    assert all(i["id"] != item_id for i in coordinator.data)


async def test_ws_remove_unknown_id_returns_error(hass, setup_integration, hass_ws_client):
    """activity_manager/remove with unknown id returns an error message."""
    hass, entry_id = setup_integration
    client = await hass_ws_client(hass)
    await client.send_json({
        "id": 1,
        "type": WS_REMOVE,
        "entry_id": entry_id,
        "item_id": "nonexistent-id",
    })
    msg = await client.receive_json()

    assert msg["success"] is False
