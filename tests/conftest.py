"""Shared test fixtures for Activity Manager."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.activity_manager.const import DOMAIN


# Automatically enable custom integration loading for all tests in this suite.
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for every test."""


@pytest.fixture(scope="session", autouse=True)
async def prime_aiohttp_server():
    """Start and immediately close a dummy aiohttp application so the
    safe-shutdown-loop background thread is running before pytest_homeassistant_custom_component
    snapshots the thread list at hass fixture setup time.

    Without this, the first test using hass_ws_client creates the thread and it
    appears as 'lingering' during teardown even though it's a daemon thread from
    the aiohttp library itself.
    """
    import aiohttp
    app = aiohttp.web.Application()
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()
    await runner.cleanup()



SAMPLE_ACTIVITIES = [
    {
        "id": "aabbcc001122",
        "name": "Water Plants",
        "category": "Garden",
        "frequency": {"days": 7},
        "frequency_ms": 604800000,
        "last_completed": "2026-04-01T10:00:00+00:00",
        "icon": "mdi:flower",
    },
    {
        "id": "ddeeff334455",
        "name": "Oil Change",
        "category": "Car",
        "frequency": {"days": 90},
        "frequency_ms": 7776000000,
        "last_completed": "2026-01-01T10:00:00+00:00",
        "icon": "mdi:car",
    },
]

LEGACY_ACTIVITY = {
    "id": "legacy000001",
    "name": "Weekly Chores",
    "category": "Home",
    # Legacy integer frequency (days)
    "frequency": 7,
    "last_completed": "2026-03-01T10:00:00+00:00",
    "icon": "mdi:broom",
}


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a mock Activity Manager config entry for 'Home' list."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Home"},
        title="Home",
        unique_id="home",
        version=1,
        minor_version=3,
    )


@pytest.fixture
def mock_config_entry_2() -> MockConfigEntry:
    """Return a second mock Activity Manager config entry for 'Social' list."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={"name": "Social"},
        title="Social",
        unique_id="social",
        version=1,
        minor_version=3,
    )


@pytest.fixture
def mock_empty_persistence():
    """Patch load_json_array to return an empty list and os.path.exists to return True."""
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture
def mock_persistence():
    """Patch load_json_array to return sample activities and os.path.exists to return True."""
    with (
        patch("custom_components.activity_manager.coordinator.os.path.exists", return_value=True),
        patch(
            "custom_components.activity_manager.coordinator.load_json_array",
            return_value=list(SAMPLE_ACTIVITIES),
        ),
    ):
        yield


@pytest.fixture
def mock_save():
    """Patch save_json so tests don't write to disk."""
    with patch(
        "custom_components.activity_manager.coordinator.save_json"
    ) as mock:
        yield mock
