"""Config flow for ActivityManager."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback

from .const import DOMAIN  # import the domain from const.py
import logging

_LOGGER = logging.getLogger(__name__)


class ActivityManagerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a ActivityManager config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""

        # Check if already configured
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title="Activity Manager", data={'name': "Activity Manager"})

    async_step_import = async_step_user
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return ActivityManagerOptionsFlowHandler(config_entry)


class ActivityManagerOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for the Activity Manager component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize ActivityManager options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return self.async_abort(reason="single_instance_allowed")