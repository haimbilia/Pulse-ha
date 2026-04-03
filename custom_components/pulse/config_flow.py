from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONF_HOST, CONF_PORT, CONF_TARGET_ID, CONF_TOKEN, DEFAULT_PORT, DOMAIN


class PulseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input.get(CONF_TARGET_ID, 'default')}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"Pulse ({user_input[CONF_HOST]})",
                data=user_input,
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_TOKEN): str,
                vol.Optional(CONF_TARGET_ID): str,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors={})
