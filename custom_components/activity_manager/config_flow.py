"""Config flow for ActivityManager."""
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN  # import the domain from const.py
import logging

_LOGGER = logging.getLogger(__name__)


class ActivityManagerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a ActivityManager config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Check if already configured
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title='Activity Manager', data={'name': 'Activity Manager'})

    async_step_import = async_step_user
