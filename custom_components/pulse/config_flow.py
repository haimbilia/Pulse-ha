from __future__ import annotations

import voluptuous as vol

from homeassistant.components import zeroconf
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PulseApiClient, PulseApiError
from .const import CONF_HOST, CONF_PORT, CONF_TARGET_ID, CONF_TOKEN, DEFAULT_PORT, DOMAIN


class PulseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str | None = None

    async def _async_validate_input(self, data: dict) -> dict:
        client = PulseApiClient(
            session=async_get_clientsession(self.hass),
            host=data[CONF_HOST],
            port=data[CONF_PORT],
            token=data.get(CONF_TOKEN),
        )
        await client.async_get_status()
        return {
            "title": f"Pulse ({data[CONF_HOST]})",
            "unique_id": f"{data[CONF_HOST]}:{data[CONF_PORT]}",
        }

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is not None:
            errors: dict[str, str] = {}
            try:
                info = await self._async_validate_input(user_input)
            except PulseApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)

            return self.async_show_form(step_id="user", data_schema=self._user_schema(user_input), errors=errors)

        return self.async_show_form(step_id="user", data_schema=self._user_schema(), errors={})

    async def async_step_zeroconf(self, discovery_info: zeroconf.ZeroconfServiceInfo) -> FlowResult:
        self._discovered_host = discovery_info.host
        self._discovered_port = discovery_info.port or DEFAULT_PORT
        self._discovered_name = discovery_info.name.rstrip(".")

        await self.async_set_unique_id(f"{self._discovered_host}:{self._discovered_port}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host, CONF_PORT: self._discovered_port})

        self.context["title_placeholders"] = {
            "name": self._discovered_name or self._discovered_host,
            "host": self._discovered_host,
        }
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(self, user_input: dict | None = None) -> FlowResult:
        assert self._discovered_host is not None

        if user_input is not None:
            data = {
                CONF_HOST: self._discovered_host,
                CONF_PORT: self._discovered_port,
            }
            if user_input.get(CONF_TOKEN):
                data[CONF_TOKEN] = user_input[CONF_TOKEN]
            if user_input.get(CONF_TARGET_ID):
                data[CONF_TARGET_ID] = user_input[CONF_TARGET_ID]

            errors: dict[str, str] = {}
            try:
                info = await self._async_validate_input(data)
            except PulseApiError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=data)

            return self.async_show_form(
                step_id="zeroconf_confirm",
                data_schema=self._zeroconf_schema(user_input),
                errors=errors,
                description_placeholders={
                    "name": self._discovered_name or self._discovered_host,
                    "host": self._discovered_host,
                    "port": str(self._discovered_port),
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=self._zeroconf_schema(),
            errors={},
            description_placeholders={
                "name": self._discovered_name or self._discovered_host,
                "host": self._discovered_host,
                "port": str(self._discovered_port),
            },
        )

    def _user_schema(self, user_input: dict | None = None) -> vol.Schema:
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_TOKEN, default=user_input.get(CONF_TOKEN, "")): str,
                vol.Optional(CONF_TARGET_ID, default=user_input.get(CONF_TARGET_ID, "")): str,
            }
        )

    def _zeroconf_schema(self, user_input: dict | None = None) -> vol.Schema:
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Optional(CONF_TOKEN, default=user_input.get(CONF_TOKEN, "")): str,
                vol.Optional(CONF_TARGET_ID, default=user_input.get(CONF_TARGET_ID, "")): str,
            }
        )
