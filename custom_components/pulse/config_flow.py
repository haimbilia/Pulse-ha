from __future__ import annotations

import asyncio

import voluptuous as vol

from homeassistant.components import zeroconf
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PulseApiClient, PulseApiError
from .const import CONF_HOST, CONF_PORT, CONF_TOKEN, DEFAULT_PORT, DOMAIN

_MDNS_SERVICE_TYPE = "_pulse._tcp.local."


class PulseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovered_host: str | None = None
        self._discovered_port: int = DEFAULT_PORT
        self._discovered_name: str | None = None
        self._scan_results: list[dict] = []

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

    async def _async_scan_devices(self) -> list[dict]:
        """Scan the local network for Pulse devices via mDNS."""
        try:
            from zeroconf import ServiceStateChange
            from zeroconf.asyncio import AsyncServiceBrowser, AsyncServiceInfo

            aiozc = await zeroconf.async_get_async_instance(self.hass)
            services: list[tuple[str, str]] = []

            def _on_change(zc, service_type: str, name: str, state_change: ServiceStateChange) -> None:
                if state_change is ServiceStateChange.Added:
                    services.append((service_type, name))

            browser = AsyncServiceBrowser(aiozc.zeroconf, [_MDNS_SERVICE_TYPE], handlers=[_on_change])
            try:
                await asyncio.sleep(2)
            finally:
                await browser.async_cancel()

            results = []
            for service_type, name in services:
                info = AsyncServiceInfo(service_type, name)
                if await info.async_request(aiozc.zeroconf, 3000):
                    addresses = info.parsed_addresses()
                    ipv4 = [a for a in addresses if ":" not in a]
                    host = ipv4[0] if ipv4 else (addresses[0] if addresses else None)
                    if host:
                        display_name = name.replace(f".{service_type}", "").rstrip(".")
                        results.append({
                            "name": display_name,
                            "host": host,
                            "port": info.port or DEFAULT_PORT,
                        })

            return results
        except Exception:  # noqa: BLE001
            return []

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        if user_input is None:
            self._scan_results = await self._async_scan_devices()
            if not self._scan_results:
                return await self.async_step_manual()
            return self.async_show_form(
                step_id="user",
                data_schema=self._scan_schema(),
            )

        selected = user_input.get("device", "manual")
        if selected == "manual":
            return await self.async_step_manual()

        host, port_str = selected.rsplit(":", 1)
        data = {CONF_HOST: host, CONF_PORT: int(port_str)}

        errors: dict[str, str] = {}
        try:
            info = await self._async_validate_input(data)
        except PulseApiError:
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user",
                data_schema=self._scan_schema(),
                errors=errors,
            )

        await self.async_set_unique_id(info["unique_id"])
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=info["title"], data=data)

    async def async_step_manual(self, user_input: dict | None = None) -> FlowResult:
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
            return self.async_show_form(step_id="manual", data_schema=self._user_schema(user_input), errors=errors)

        return self.async_show_form(step_id="manual", data_schema=self._user_schema(), errors={})

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
                data_schema=vol.Schema({}),
                errors=errors,
                description_placeholders={
                    "name": self._discovered_name or self._discovered_host,
                    "host": self._discovered_host,
                    "port": str(self._discovered_port),
                },
            )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({}),
            errors={},
            description_placeholders={
                "name": self._discovered_name or self._discovered_host,
                "host": self._discovered_host,
                "port": str(self._discovered_port),
            },
        )

    def _scan_schema(self) -> vol.Schema:
        options = {
            f"{d['host']}:{d['port']}": f"{d['name']} ({d['host']})"
            for d in self._scan_results
        }
        options["manual"] = "Enter manually"
        return vol.Schema({
            vol.Required("device"): vol.In(options)
        })

    def _user_schema(self, user_input: dict | None = None) -> vol.Schema:
        user_input = user_input or {}
        return vol.Schema(
            {
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=user_input.get(CONF_PORT, DEFAULT_PORT)): int,
                vol.Optional(CONF_TOKEN, default=user_input.get(CONF_TOKEN, "")): str,
            }
        )
