from __future__ import annotations

import asyncio
import ipaddress

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PulseApiClient, PulseApiError
from .const import CONF_HOST, CONF_PORT, CONF_TOKEN, DEFAULT_PORT, DOMAIN


class PulseConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
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
        """Scan the local /24 subnet for Pulse devices by probing /status."""
        try:
            from homeassistant.helpers.network import async_get_source_ip

            try:
                ha_ip = await async_get_source_ip(self.hass)
            except Exception:  # noqa: BLE001
                return []

            if not ha_ip or ":" in ha_ip:
                return []

            try:
                network = ipaddress.IPv4Network(f"{ha_ip}/24", strict=False)
            except ValueError:
                return []

            session = async_get_clientsession(self.hass)

            async def probe(ip: str) -> dict | None:
                try:
                    async with session.get(
                        f"http://{ip}:{DEFAULT_PORT}/status",
                        timeout=aiohttp.ClientTimeout(total=1.5),
                    ) as response:
                        if response.status != 200:
                            return None
                        data = await response.json(content_type=None)
                        if not isinstance(data, dict):
                            return None
                        if data.get("deviceName") != "pulse":
                            return None
                        return {"name": f"Pulse ({ip})", "host": ip, "port": DEFAULT_PORT}
                except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
                    return None

            tasks = [probe(str(ip)) for ip in network.hosts()]
            results_raw = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results_raw if isinstance(r, dict)]
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

    def _scan_schema(self) -> vol.Schema:
        options = {
            f"{d['host']}:{d['port']}": d["name"]
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
