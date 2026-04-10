"""Activity Manager integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_registry import async_get as er_async_get
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_ADD,
    SERVICE_REMOVE,
    SERVICE_UPDATE,
    WS_ADD,
    WS_ITEMS,
    WS_REMOVE,
    WS_UPDATE,
)
from .coordinator import ActivityManagerCoordinator
from .utils import dt_as_local

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Service schemas — entry_id required to route to the right list
# ---------------------------------------------------------------------------

_FREQUENCY_SCHEMA = vol.Any(
    vol.All(int, vol.Range(min=1)),
    vol.Schema(
        {
            vol.Optional("days"): vol.Coerce(int),
            vol.Optional("hours"): vol.Coerce(int),
            vol.Optional("minutes"): vol.Coerce(int),
            vol.Optional("seconds"): vol.Coerce(int),
        }
    ),
)

ADD_ACTIVITY_SCHEMA = vol.Schema(
    {
        vol.Required("entry_id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Required("category"): cv.string,
        vol.Required("frequency"): _FREQUENCY_SCHEMA,
        vol.Optional("last_completed"): cv.string,
        vol.Optional("icon"): cv.string,
    }
)

REMOVE_ACTIVITY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
    }
)

UPDATE_ACTIVITY_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Optional("last_completed"): cv.string,
        vol.Optional("now"): cv.boolean,
        vol.Optional("category"): cv.string,
        vol.Optional("frequency"): _FREQUENCY_SCHEMA,
        vol.Optional("icon"): cv.string,
    }
)


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> ActivityManagerCoordinator | None:
    """Look up a coordinator by entry_id."""
    return hass.data.get(DOMAIN, {}).get(entry_id)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Handle legacy YAML-based setup by triggering a config flow import."""
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up an Activity Manager list from a config entry."""
    coordinator = ActivityManagerCoordinator(hass, config_entry)
    await coordinator.async_load()

    hass.data.setdefault(DOMAIN, {})
    # Register services and WS handlers exactly once, before adding this entry,
    # using a separate flag key so the check is race-free even when HA loads
    # multiple config entries concurrently.
    first_entry = f"{DOMAIN}_registered" not in hass.data
    if first_entry:
        hass.data[f"{DOMAIN}_registered"] = True
        _register_services(hass)
        _register_websocket_handlers(hass)

    hass.data[DOMAIN][config_entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

        # Remove services and websocket handlers only when the last entry is gone.
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_ADD)
            hass.services.async_remove(DOMAIN, SERVICE_REMOVE)
            hass.services.async_remove(DOMAIN, SERVICE_UPDATE)
            hass.data.pop(f"{DOMAIN}_registered", None)

    return unload_ok


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def _register_services(hass: HomeAssistant) -> None:
    """Register domain services (called once on first entry setup)."""

    async def add_activity_service(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data["entry_id"])
        if not coordinator:
            _LOGGER.error("add_activity: unknown entry_id %s", call.data["entry_id"])
            return

        last_completed = call.data.get("last_completed")
        if last_completed:
            last_completed = dt_as_local(last_completed)

        await coordinator.async_add_activity(
            name=call.data["name"],
            category=call.data["category"],
            frequency=call.data["frequency"],
            icon=call.data.get("icon"),
            last_completed=last_completed,
        )

    async def remove_activity_service(call: ServiceCall) -> None:
        entity_registry = er_async_get(hass)
        entity = entity_registry.entities.get(call.data["entity_id"])
        if not entity:
            _LOGGER.warning("remove_activity: entity not found: %s", call.data["entity_id"])
            return

        # Derive entry_id from the entity's unique_id prefix (<entry_id>_<activity_id>).
        entry_id, _, activity_id = entity.unique_id.partition("_")
        coordinator = _get_coordinator(hass, entry_id)
        if not coordinator:
            _LOGGER.error("remove_activity: no coordinator for entry_id %s", entry_id)
            return

        await coordinator.async_remove_activity(activity_id)

    async def update_activity_service(call: ServiceCall) -> None:
        entity_registry = er_async_get(hass)
        entity = entity_registry.entities.get(call.data["entity_id"])
        if not entity:
            _LOGGER.warning("update_activity: entity not found: %s", call.data["entity_id"])
            return

        # Derive entry_id from the entity's unique_id prefix (<entry_id>_<activity_id>).
        entry_id, _, activity_id = entity.unique_id.partition("_")
        coordinator = _get_coordinator(hass, entry_id)
        if not coordinator:
            _LOGGER.error("update_activity: no coordinator for entry_id %s", entry_id)
            return

        last_completed = call.data.get("last_completed")
        if call.data.get("now"):
            last_completed = dt_util.now().isoformat()
        elif last_completed:
            last_completed = dt_as_local(last_completed)

        await coordinator.async_update_activity(
            activity_id,
            last_completed=last_completed,
            category=call.data.get("category"),
            frequency=call.data.get("frequency"),
            icon=call.data.get("icon"),
        )

    hass.services.async_register(DOMAIN, SERVICE_ADD, add_activity_service, schema=ADD_ACTIVITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE, remove_activity_service, schema=REMOVE_ACTIVITY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE, update_activity_service, schema=UPDATE_ACTIVITY_SCHEMA)


# ---------------------------------------------------------------------------
# Websocket handlers
# ---------------------------------------------------------------------------

def _register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register websocket commands (called once on first entry setup)."""

    @callback
    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_ITEMS,
            vol.Optional("entry_id"): str,
            vol.Optional("category"): str,
        }
    )
    def websocket_handle_items(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Return activity items. Optionally filter by entry_id and/or category."""
        entry_id = msg.get("entry_id")
        category = msg.get("category")

        if entry_id:
            coordinator = _get_coordinator(hass, entry_id)
            if coordinator is None:
                connection.send_error(msg["id"], "not_found", f"No list with entry_id {entry_id!r}")
                return
            items = list(coordinator.data or [])
            # Tag each item with list metadata for the card.
            for item in items:
                item = dict(item)
            items = [
                {**i, "entry_id": coordinator.entry_id, "list_title": coordinator.title}
                for i in items
            ]
        else:
            # No entry_id — return all lists merged.
            items = []
            for coord in hass.data.get(DOMAIN, {}).values():
                items.extend(
                    {**i, "entry_id": coord.entry_id, "list_title": coord.title}
                    for i in (coord.data or [])
                )

        if category:
            items = [i for i in items if i.get("category") == category]

        connection.send_message(websocket_api.result_message(msg["id"], items))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_ADD,
            vol.Required("entry_id"): str,
            vol.Required("name"): str,
            vol.Required("category"): str,
            vol.Required("frequency"): dict,
            vol.Optional("last_completed"): str,
            vol.Optional("icon"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_add(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle adding an activity via websocket."""
        msg_id = msg["id"]
        coordinator = _get_coordinator(hass, msg["entry_id"])
        if coordinator is None:
            connection.send_error(msg_id, "not_found", f"No list with entry_id {msg['entry_id']!r}")
            return

        last_completed_raw = msg.get("last_completed")
        last_completed = dt_as_local(str(last_completed_raw)) if last_completed_raw else None

        try:
            item = await coordinator.async_add_activity(
                name=msg["name"],
                category=msg["category"],
                frequency=msg["frequency"],
                icon=msg.get("icon"),
                last_completed=last_completed,
                context=connection.context(msg),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error adding activity")
            connection.send_error(msg_id, "add_failed", str(err))
            return

        connection.send_message(websocket_api.result_message(msg_id, item))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_UPDATE,
            vol.Required("entry_id"): str,
            vol.Required("item_id"): str,
            vol.Optional("last_completed"): str,
            vol.Optional("name"): str,
            vol.Optional("category"): str,
            vol.Optional("frequency"): dict,
            vol.Optional("icon"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_update(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle updating an activity via websocket."""
        msg_id = msg["id"]
        coordinator = _get_coordinator(hass, msg["entry_id"])
        if coordinator is None:
            connection.send_error(msg_id, "not_found", f"No list with entry_id {msg['entry_id']!r}")
            return

        last_completed = msg.get("last_completed")
        if last_completed:
            parsed = dt_util.parse_datetime(last_completed)
            last_completed = dt_util.as_local(parsed).isoformat() if parsed else dt_util.now().isoformat()
        else:
            last_completed = dt_util.now().isoformat()

        try:
            item = await coordinator.async_update_activity(
                item_id=msg["item_id"],
                last_completed=last_completed,
                name=msg.get("name"),
                category=msg.get("category"),
                frequency=msg.get("frequency"),
                icon=msg.get("icon"),
                context=connection.context(msg),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error updating activity")
            connection.send_error(msg_id, "update_failed", str(err))
            return

        if item is None:
            connection.send_error(msg_id, "not_found", f"Activity {msg['item_id']} not found")
            return

        connection.send_message(websocket_api.result_message(msg_id, item))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): WS_REMOVE,
            vol.Required("entry_id"): str,
            vol.Required("item_id"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_remove(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle removing an activity via websocket."""
        msg_id = msg["id"]
        coordinator = _get_coordinator(hass, msg["entry_id"])
        if coordinator is None:
            connection.send_error(msg_id, "not_found", f"No list with entry_id {msg['entry_id']!r}")
            return

        try:
            item = await coordinator.async_remove_activity(
                item_id=msg["item_id"],
                context=connection.context(msg),
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Error removing activity")
            connection.send_error(msg_id, "remove_failed", str(err))
            return

        if item is None:
            connection.send_error(msg_id, "not_found", f"Activity {msg['item_id']} not found")
            return

        connection.send_message(websocket_api.result_message(msg_id, item))

    ws_unsubs = [
        websocket_api.async_register_command(hass, websocket_handle_items),
        websocket_api.async_register_command(hass, websocket_handle_add),
        websocket_api.async_register_command(hass, websocket_handle_update),
        websocket_api.async_register_command(hass, websocket_handle_remove),
    ]
    hass.data[f"{DOMAIN}_ws_unsubs"] = ws_unsubs
