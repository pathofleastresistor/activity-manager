"""Tests for the aggregate (summary) sensors and binary sensors."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.activity_manager.const import DOMAIN
from custom_components.activity_manager.summary import (
    categories_in,
    category_key,
    compute_summary,
)

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
WEEK = 7 * 24 * 3600 * 1000


def _activity(activity_id: str, name: str, category: str, due_in: timedelta) -> dict:
    """Build a stored activity that comes due ``due_in`` from NOW (weekly)."""
    return {
        "id": activity_id,
        "name": name,
        "category": category,
        "frequency": {"days": 7},
        "frequency_ms": WEEK,
        "last_completed": (NOW + due_in - timedelta(days=7)).isoformat(),
        "icon": "mdi:check",
    }


def _items() -> list[dict]:
    return [
        _activity("a1", "Run", "Workout", timedelta(hours=-2)),  # overdue
        _activity("a2", "Chest", "Workout", timedelta(hours=12)),  # due soon
        _activity("a3", "Call parents", "Social", timedelta(days=10)),
        _activity("a4", "Dinner", "Social", timedelta(hours=30)),  # beyond 24h
    ]


@pytest.fixture(autouse=True)
def frozen(freezer):
    """Freeze time so due/overdue are deterministic."""
    freezer.move_to(NOW)
    return freezer


@pytest.fixture
async def entry(hass, mock_save, frozen):
    """Set up a 'Home' list with four activities across two categories."""
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={"name": "Home"}, title="Home", unique_id="home",
        version=1, minor_version=3,
    )
    config_entry.add_to_hass(hass)
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch("custom_components.activity_manager.coordinator.load_json_array", return_value=_items()),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


def _coordinator(hass, config_entry):
    return hass.data[DOMAIN][config_entry.entry_id]


def _state(hass, config_entry, scope: str, metric: str, domain: str = "sensor"):
    """Look a summary entity's state up by its unique id (stable, unlike entity ids)."""
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        domain, DOMAIN, f"{config_entry.entry_id}_summary_{scope}_{metric}"
    )
    assert entity_id, f"no entity for {scope}/{metric}"
    return hass.states.get(entity_id)


# ---------------------------------------------------------------------------
# Pure computation
# ---------------------------------------------------------------------------

def test_compute_summary_empty():
    summary = compute_summary([], NOW, timedelta(hours=24))
    assert (summary.due_count, summary.overdue_count) == (0, 0)
    assert summary.next_due is None and summary.next_due_name is None


def test_compute_summary_never_completed_is_overdue():
    item = {"id": "x", "name": "New", "category": "Home", "frequency_ms": WEEK}
    summary = compute_summary([item], NOW, timedelta(0))
    assert summary.overdue_count == 1 and summary.due == ["New"]


def test_compute_summary_zero_window_counts_only_overdue():
    summary = compute_summary(_items(), NOW, timedelta(0))
    assert summary.due_count == summary.overdue_count == 1


def test_category_grouping_is_case_insensitive_and_skips_empty():
    items = [{"category": "Workout"}, {"category": "workout"}, {"category": ""}, {}]
    assert categories_in(items) == {"workout": "Workout"}
    assert category_key(None) == ""


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

async def test_list_level_sensors(hass, entry):
    assert _state(hass, entry, "list", "due_count").state == "2"
    assert _state(hass, entry, "list", "overdue_count").state == "1"
    next_due = _state(hass, entry, "list", "next_due")
    assert dt_util.parse_datetime(next_due.state) == NOW - timedelta(hours=2)
    assert next_due.attributes["activity"] == "Run"


async def test_per_category_sensors(hass, entry):
    assert _state(hass, entry, "cat_workout", "due_count").state == "2"
    assert _state(hass, entry, "cat_workout", "overdue_count").state == "1"
    assert _state(hass, entry, "cat_social", "due_count").state == "0"
    assert _state(hass, entry, "cat_social", "overdue_count").state == "0"
    social_next = _state(hass, entry, "cat_social", "next_due")
    assert dt_util.parse_datetime(social_next.state) == NOW + timedelta(hours=30)
    assert social_next.attributes["activity"] == "Dinner"


async def test_names_in_attributes(hass, entry):
    due = _state(hass, entry, "list", "due_count")
    assert due.attributes["activities"] == ["Run", "Chest"]
    assert _state(hass, entry, "list", "overdue_count").attributes["activities"] == ["Run"]
    assert due.attributes["entry_id"] == entry.entry_id
    assert due.attributes["list_title"] == "Home"
    assert _state(hass, entry, "cat_workout", "due_count").attributes["category"] == "Workout"


async def test_device_and_state_classes(hass, entry):
    due = _state(hass, entry, "list", "due_count")
    assert due.attributes["state_class"] == "measurement"
    assert "device_class" not in due.attributes
    assert _state(hass, entry, "list", "next_due").attributes["device_class"] == "timestamp"

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None and device.name == "Home"
    registry = er.async_get(hass)
    summary_entries = [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "_summary_" in e.unique_id
    ]
    # 4 scopes (list + 2 categories = 3) x (3 sensors + 1 binary sensor) = 12
    assert len(summary_entries) == 12
    assert {e.device_id for e in summary_entries} == {device.id}


async def test_entity_ids_are_predictable(hass, entry):
    assert hass.states.get("sensor.home_due").state == "2"
    assert hass.states.get("sensor.home_overdue").state == "1"
    assert hass.states.get("sensor.home_workout_overdue").state == "1"
    assert hass.states.get("sensor.home_social_due").state == "0"
    assert hass.states.get("binary_sensor.home_has_due_activities").state == "on"
    assert hass.states.get("binary_sensor.home_social_has_due_activities").state == "off"


async def test_summary_entities_are_invisible_to_integration_selectors(hass, entry):
    """The blueprint/card editor select on attributes.integration; summaries must not match."""
    summaries = [
        s for s in hass.states.async_all()
        if "_summary_" in (er.async_get(hass).async_get(s.entity_id) or type("x", (), {"unique_id": ""})).unique_id
    ]
    assert summaries
    assert all("integration" not in s.attributes for s in summaries)
    matching = [
        s for s in hass.states.async_all("sensor")
        if s.attributes.get("integration") == DOMAIN
    ]
    assert len(matching) == 4  # only the per-activity sensors, unchanged


async def test_binary_sensor_attributes(hass, entry):
    state = _state(hass, entry, "list", "has_due", "binary_sensor")
    assert state.state == "on"
    assert state.attributes["activities"] == ["Run", "Chest"]
    assert _state(hass, entry, "cat_social", "has_due", "binary_sensor").state == "off"


# ---------------------------------------------------------------------------
# Updates: data changes
# ---------------------------------------------------------------------------

async def test_completing_an_activity_updates_counts(hass, entry):
    await _coordinator(hass, entry).async_update_activity("a1", last_completed=NOW.isoformat())
    await hass.async_block_till_done()
    assert _state(hass, entry, "list", "overdue_count").state == "0"
    assert _state(hass, entry, "list", "due_count").state == "1"
    assert _state(hass, entry, "cat_workout", "overdue_count").state == "0"


async def test_editing_frequency_updates_counts(hass, entry):
    await _coordinator(hass, entry).async_update_activity(
        "a3", last_completed=(NOW - timedelta(days=3)).isoformat(), frequency={"days": 1}
    )
    await hass.async_block_till_done()
    assert _state(hass, entry, "cat_social", "overdue_count").state == "1"


async def test_adding_an_activity_updates_counts(hass, entry):
    await _coordinator(hass, entry).async_add_activity(
        "Late", "Workout", {"days": 1}, last_completed=(NOW - timedelta(days=3)).isoformat()
    )
    await hass.async_block_till_done()
    assert _state(hass, entry, "list", "overdue_count").state == "2"
    assert _state(hass, entry, "cat_workout", "overdue_count").state == "2"


async def test_removing_an_activity_updates_counts(hass, entry):
    await _coordinator(hass, entry).async_remove_activity("a1")
    await hass.async_block_till_done()
    assert _state(hass, entry, "list", "overdue_count").state == "0"


async def test_new_category_creates_entities(hass, entry):
    await _coordinator(hass, entry).async_add_activity("Mow", "Garden", {"days": 7})
    await hass.async_block_till_done()
    assert _state(hass, entry, "cat_garden", "due_count").state == "0"
    assert hass.states.get("sensor.home_garden_due") is not None
    assert _state(hass, entry, "cat_garden", "has_due", "binary_sensor") is not None


async def test_category_entities_removed_when_category_empties(hass, entry):
    coordinator = _coordinator(hass, entry)
    await coordinator.async_remove_activity("a3")
    await coordinator.async_remove_activity("a4")
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert not [
        e for e in er.async_entries_for_config_entry(registry, entry.entry_id)
        if "_summary_cat_social_" in e.unique_id
    ]
    assert hass.states.get("sensor.home_social_due") is None
    # The rest are untouched.
    assert _state(hass, entry, "cat_workout", "due_count").state == "2"
    assert _state(hass, entry, "list", "due_count").state == "2"


async def test_stale_category_entities_cleaned_up_on_startup(hass, mock_save, frozen):
    config_entry = MockConfigEntry(
        domain=DOMAIN, data={"name": "Home"}, title="Home", unique_id="home",
        version=1, minor_version=3,
    )
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    stale = registry.async_get_or_create(
        "sensor", DOMAIN, f"{config_entry.entry_id}_summary_cat_gone_due_count",
        config_entry=config_entry,
    )
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch("custom_components.activity_manager.coordinator.load_json_array", return_value=_items()),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert registry.async_get(stale.entity_id) is None


async def test_unique_ids_are_stable_across_reload(hass, entry):
    registry = er.async_get(hass)

    def ids():
        return {
            e.unique_id: e.entity_id
            for e in er.async_entries_for_config_entry(registry, entry.entry_id)
            if "_summary_" in e.unique_id
        }

    before = ids()
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch("custom_components.activity_manager.coordinator.load_json_array", return_value=_items()),
    ):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert ids() == before


# ---------------------------------------------------------------------------
# Updates: time passing
# ---------------------------------------------------------------------------

async def test_activity_becoming_overdue_updates_without_data_change(hass, entry, frozen):
    assert _state(hass, entry, "cat_workout", "overdue_count").state == "1"
    later = NOW + timedelta(hours=13)  # Chest comes due at +12h
    frozen.move_to(later)
    async_fire_time_changed(hass, later)
    await hass.async_block_till_done()
    assert _state(hass, entry, "cat_workout", "overdue_count").state == "2"
    assert _state(hass, entry, "list", "overdue_count").state == "2"


async def test_activity_entering_due_soon_window_updates(hass, entry, frozen):
    assert _state(hass, entry, "cat_social", "due_count").state == "0"
    later = NOW + timedelta(hours=7)  # Dinner (+30h) is now within 24h
    frozen.move_to(later)
    async_fire_time_changed(hass, later)
    await hass.async_block_till_done()
    assert _state(hass, entry, "cat_social", "due_count").state == "1"
    assert _state(hass, entry, "cat_social", "overdue_count").state == "0"


async def test_timer_is_cancelled_on_unload(hass, entry):
    coordinator = _coordinator(hass, entry)
    assert coordinator._unsub_transition is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator._unsub_transition is None


# ---------------------------------------------------------------------------
# Options and multiple lists
# ---------------------------------------------------------------------------

async def test_due_soon_option_changes_counts_and_reloads(hass, entry):
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch("custom_components.activity_manager.coordinator.load_json_array", return_value=_items()),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"name": "Home", "due_soon_hours": 0}
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert _state(hass, entry, "list", "due_count").state == "1"
    assert _state(hass, entry, "list", "overdue_count").state == "1"


async def test_options_default_matches_existing_behaviour(hass, entry):
    """An entry saved before this option existed still gets the 24h default."""
    assert entry.options.get("due_soon_hours") is None
    assert _coordinator(hass, entry).due_soon == timedelta(hours=24)


async def test_each_list_gets_its_own_device_and_entities(hass, entry, mock_save):
    second = MockConfigEntry(
        domain=DOMAIN, data={"name": "Social"}, title="Social", unique_id="social",
        version=1, minor_version=3,
    )
    second.add_to_hass(hass)
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch("custom_components.activity_manager.coordinator.load_json_array", return_value=[]),
    ):
        await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()
    assert _state(hass, second, "list", "due_count").state == "0"
    assert _state(hass, second, "list", "next_due").state == "unknown"
    assert _state(hass, entry, "list", "due_count").state == "2"
    devices = dr.async_get(hass)
    assert devices.async_get_device(identifiers={(DOMAIN, second.entry_id)}) is not None
    assert (
        devices.async_get_device(identifiers={(DOMAIN, second.entry_id)}).id
        != devices.async_get_device(identifiers={(DOMAIN, entry.entry_id)}).id
    )
