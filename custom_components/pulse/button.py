from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import PulseApiError
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([PulseWakeButton(entry, client), PulseSyncControllersButton(entry, client, coordinator)])


class PulseWakeButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Wake PC"
    _attr_icon = "mdi:power-cycle"

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wake_pc"

    async def async_press(self) -> None:
        await self._client.async_wake_pc()


class PulseSyncControllersButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Sync controllers"
    _attr_icon = "mdi:sync"

    def __init__(self, entry: ConfigEntry, client, coordinator) -> None:
        self._client = client
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_sync_controllers"

    async def async_press(self) -> None:
        await self._coordinator.async_request_refresh()
        if not self._coordinator.last_update_success:
            return
        try:
            await self._client.async_clear_ha_sync_dirty()
        except PulseApiError:
            pass
