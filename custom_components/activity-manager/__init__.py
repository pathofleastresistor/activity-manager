from __future__ import annotations
from typing import Any
from datetime import datetime, timedelta
import logging
import voluptuous as vol
import uuid
from homeassistant.helpers.json import save_json
from homeassistant.components import websocket_api
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

    data = hass.data[DOMAIN] = ActivityManager(hass)
    await data.async_load_activities()
    await data.update_entities(data.items)

    async def add_item_service(call: ServiceCall) -> None:
        """Add an item with `name`."""
        data = hass.data[DOMAIN]

        name = call.data["name"]
        category = call.data["category"]
        frequency = call.data["frequency"]

        await data.async_add_activity(name, category, frequency)

    async def remove_item_service(call: ServiceCall) -> None:
        """Remove the first item with matching `name`."""
        data = hass.data[DOMAIN]

        name = call.data["name"]
        category = call.data["category"]

        try:
            item = [
                item
                for item in data.items
                if (item["name"] == name and item["category"] == category)
            ][0]
        except IndexError:
            _LOGGER.error("Removing of item failed: %s cannot be found", name)
        else:
            await data.async_remove_activity(item["id"])

    async def update_item_service(call: ServiceCall) -> None:
        """Remove the first item with matching `name`."""
        data = hass.data[DOMAIN]
        name = call.data["name"]
        category = call.data["category"]

        try:
            item = [
                item
                for item in data.items
                if (item["name"] == name and item["category"] == category)
            ][0]
        except IndexError:
            _LOGGER.error("Update of item failed: %s cannot be found", name)
        else:
            await data.async_update_activity(item["id"])

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
            vol.Required("frequency"): int,
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
            name, category, frequency, connection.context(msg)
        )
        connection.send_message(websocket_api.result_message(id, item))

    @websocket_api.websocket_command(
        {
            vol.Required("type"): "activity_manager/update",
            vol.Required("item_id"): str,
            vol.Optional("last_completed"): str,
            vol.Optional("name"): str,
            vol.Optional("category"): str,
            vol.Optional("frequency"): int,
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

        item = await hass.data[DOMAIN].async_update_activity(
            item_id, connection.context(msg)
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

    # hass.helpers.discovery.load_platform("sensor", DOMAIN, {}, config_entry)
    # async_track_time_interval(hass, test, timedelta(seconds=2))

    return True


class ActivityManager:
    """Class to hold activity data."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the shopping list."""

        self.hass = hass
        self.items: JsonArrayType = []

    async def async_add_activity(self, name, category, frequency, context=None):
        item = {
            "name": name,
            "category": category,
            "id": uuid.uuid4().hex,
            "last_completed": dt.now().isoformat(),
            "frequency": int(frequency),
        }
        self.items.append(item)
        await self.update_entity(item)
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "add", "item": item},
            context=context,
        )

        return item

    async def async_remove_activity(self, item_id, context=None):
        item = next((itm for itm in self.items if itm["id"] == item_id), None)

        # if item is None:
        #     raise NoMatchingShoppingListItem

        self.items.remove(item)
        await self.remove_entity(item)
        await self.hass.async_add_executor_job(self.save)
        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "remove", "item": item},
            context=context,
        )

        return item

    async def async_update_activity(self, item_id, context=None):
        item = next((itm for itm in self.items if itm["id"] == item_id), None)
        item.update({"last_completed": dt.now().isoformat()})

        await self.update_entity(item)
        await self.hass.async_add_executor_job(self.save)

        self.hass.bus.async_fire(
            "activity_manager_updated",
            {"action": "updated", "item": item},
            context=context,
        )
        return item

    async def update_entities(self, items):
        for item in items:
            await self.update_entity(item)

    async def update_entity(self, item):
        entity_name = slugify(item["category"] + "_" + item["name"])
        entity_id = f"{DOMAIN}.{entity_name}"

        self.hass.states.async_set(
            entity_id,
            dt.as_local(dt.parse_datetime(item["last_completed"]))
            + timedelta(days=item["frequency"]),
            {
                "name": item["name"],
                "friendly_name": item["name"],
                "category": item["category"],
                "last_completed": item["last_completed"],
                "frequency": item["frequency"],
            },
        )

    async def remove_entity(self, item):
        entity_name = slugify(item["category"] + "_" + item["name"])
        entity_id = f"{DOMAIN}.{entity_name}"
        self.hass.states.async_remove(entity_id)

    async def async_load_activities(self) -> None:
        """Load items."""

        def load() -> JsonArrayType:
            """Load the items synchronously."""
            return load_json_array(self.hass.config.path(PERSISTENCE))

        self.items = await self.hass.async_add_executor_job(load)

    def save(self) -> None:
        """Save the items."""
        save_json(self.hass.config.path(PERSISTENCE), self.items)
