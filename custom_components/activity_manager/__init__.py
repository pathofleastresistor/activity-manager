from __future__ import annotations
from typing import Any
from datetime import datetime, timedelta
import logging
import voluptuous as vol
import uuid
import json
from homeassistant.helpers.json import save_json
from homeassistant.components import websocket_api
from homeassistant.helpers.entity_registry import async_get
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.util.json import JsonArrayType, load_json_array
from homeassistant import config_entries
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify
from homeassistant.util import dt
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PERSISTENCE = ".activities_list.json"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Initialize the activity."""

    if DOMAIN not in config:
        return True

    hass.async_create_task(
        discovery.async_load_platform(hass, "sensor", DOMAIN, None, hass_config=config)
    )

    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_IMPORT}
        )
    )

    return True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
) -> bool:
    """Set up Activity Manager from a config entry."""
    # Add sensor
    hass.async_add_job(
        hass.config_entries.async_forward_entry_setup(config_entry, "sensor")
    )

    async def add_item_service(call: ServiceCall) -> None:
        """Add an item with `name`."""
        data = hass.data[DOMAIN]

        name = call.data.get("name")
        category = call.data.get("category")
        frequency_str = call.data.get("frequency")
        last_completed = call.data.get("last_completed")
        icon = call.data.get("icon")

        if last_completed:
            last_completed = dt.parse_datetime(last_completed).isoformat()
        else:
            last_completed = dt.now().isoformat()

        await data.async_add_activity(
            name, category, frequency_str, icon=icon, last_completed=last_completed
        )

    async def remove_item_service(call: ServiceCall) -> None:
        data = hass.data[DOMAIN]

        entity_id = call.data.get("entity_id")

        if entity_id:
            entity_registry = async_get(hass)
            entity = entity_registry.entities.get(entity_id)
            if entity:
                await data.async_remove_activity(entity.unique_id)

    async def update_item_service(call: ServiceCall) -> None:
        data = hass.data[DOMAIN]
        entity_id = call.data.get("entity_id")
        last_completed = call.data.get("last_completed")
        category = call.data.get("category")
        now = call.data.get("now")
        frequency = call.data.get("frequency")
        icon = call.data.get("icon")

        if last_completed:
            last_completed = dt.parse_datetime(last_completed).isoformat()

        if now:
            last_completed = dt.now().isoformat()

        if entity_id:
            entity_registry = async_get(hass)
            entity = entity_registry.entities.get(entity_id)
            if entity:
                await data.async_update_activity(
                    entity.unique_id,
                    last_completed=last_completed,
                    category=category,
                    frequency=frequency,
                    icon=icon,
                )

    hass.services.async_register(DOMAIN, "add_activity", add_item_service)
    hass.services.async_register(DOMAIN, "remove_activity", remove_item_service)
    hass.services.async_register(DOMAIN, "update_activity", update_item_service)

    @callback
    @websocket_api.websocket_command(
        {vol.Required("type"): "activity_manager/items", vol.Optional("category"): str}
    )
    def websocket_handle_items(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle getting activity_manager items."""
        connection.send_message(
            websocket_api.result_message(msg["id"], hass.data[DOMAIN].items)
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "activity_manager/add",
            vol.Required("name"): str,
            vol.Required("category"): str,
            vol.Required("frequency"): dict,
            vol.Optional("last_completed"): int,
            vol.Optional("icon"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_add(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle updating activity."""
        id = msg.pop("id")
        name = msg.pop("name")
        category = msg.pop("category")
        frequency = msg.pop("frequency")
        msg.pop("type")

        item = await hass.data[DOMAIN].async_add_activity(
            name, category, frequency, context=connection.context(msg)
        )
        connection.send_message(websocket_api.result_message(id, item))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "activity_manager/update",
            vol.Required("item_id"): str,
            vol.Optional("last_completed"): str,
            vol.Optional("name"): str,
            vol.Optional("category"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_update(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle updating activity."""
        msg_id = msg.pop("id")
        item_id = msg.pop("item_id")
        msg.pop("type")
        data = msg

        # TODO: Support custom last_completed from UI
        last_completed = dt.now().isoformat()

        item = await hass.data[DOMAIN].async_update_activity(
            item_id, last_completed=last_completed, context=connection.context(msg)
        )
        connection.send_message(websocket_api.result_message(msg_id, item))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "activity_manager/remove",
            vol.Required("item_id"): str,
        }
    )
    @websocket_api.async_response
    async def websocket_handle_remove(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        """Handle removing activity."""
        msg_id = msg.pop("id")
        item_id = msg.pop("item_id")
        msg.pop("type")
        data = msg

        item = await hass.data[DOMAIN].async_remove_activity(
            item_id, connection.context(msg)
        )
        connection.send_message(websocket_api.result_message(msg_id, item))

    websocket_api.async_register_command(hass, websocket_handle_items)
    websocket_api.async_register_command(hass, websocket_handle_add)
    websocket_api.async_register_command(hass, websocket_handle_update)
    websocket_api.async_register_command(hass, websocket_handle_remove)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when it changed."""
    await hass.config_entries.async_reload(entry.entry_id)
