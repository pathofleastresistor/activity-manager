"""Config flow for ActivityManager."""
import voluptuous as vol
from homeassistant import config_entries

from .const import DOMAIN  # import the domain from const.py


class ActivityManagerFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a ActivityManager config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Check if already configured
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required("name"): str,
                    }
                ),
            )

        return self.async_create_entry(title=user_input["name"], data=user_input)

    async_step_import = async_step_user
