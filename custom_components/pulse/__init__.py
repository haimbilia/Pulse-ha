from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import PulseApiClient
from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DEFAULT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import PulseDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.version == 1:
        data = dict(entry.data)
        if data.get(CONF_PORT) == 80:
            data[CONF_PORT] = DEFAULT_PORT
        hass.config_entries.async_update_entry(entry, data=data, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    client = PulseApiClient(
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        token=entry.data.get(CONF_TOKEN),
    )
    coordinator = PulseDataUpdateCoordinator(hass, client)

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
