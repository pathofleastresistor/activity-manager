"""Config flow for Activity Manager."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import slugify

from .const import DOMAIN, ENTRY_MINOR_VERSION, ENTRY_VERSION

_LOGGER = logging.getLogger(__name__)


async def async_migrate_entry(hass: HomeAssistant, entry: config_entries.ConfigEntry) -> bool:
    """Migrate a config entry to the current version."""
    _LOGGER.debug(
        "Migrating activity_manager config entry from version %s.%s",
        entry.version,
        entry.minor_version,
    )

    if entry.version == 1 and entry.minor_version < 3:
        # v1.1/v1.2 → v1.3: set a proper unique_id and title from existing name.
        name = entry.data.get("name", "Activity Manager")
        hass.config_entries.async_update_entry(
            entry,
            title=name,
            unique_id=slugify(name),
            minor_version=3,
        )

    return True


class ActivityManagerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle an Activity Manager config flow."""

    VERSION = ENTRY_VERSION
    MINOR_VERSION = ENTRY_MINOR_VERSION

    async def async_step_user(self, user_input=None):
        """Handle the initial step — ask for a list name."""
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input["name"].strip()
            if not name:
                errors["name"] = "name_required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=name, data={"name": name})

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("name"): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> ActivityManagerOptionsFlowHandler:
        """Get the options flow handler."""
        return ActivityManagerOptionsFlowHandler()


class ActivityManagerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Activity Manager."""

    async def async_step_init(self, user_input=None):
        """Allow renaming the activity list."""
        if user_input is not None:
            name = user_input["name"].strip()
            if name and name != self.config_entry.title:
                self.hass.config_entries.async_update_entry(
                    self.config_entry, title=name
                )
            return self.async_create_entry(data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required("name", default=self.config_entry.title): str}
            ),
        )
