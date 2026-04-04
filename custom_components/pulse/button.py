from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_CLIENT, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    client = hass.data[DOMAIN][entry.entry_id][DATA_CLIENT]
    async_add_entities([PulseWakeButton(entry, client)])


class PulseWakeButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Wake PC"
    _attr_icon = "mdi:power-cycle"

    def __init__(self, entry: ConfigEntry, client) -> None:
        self._client = client
        self._attr_unique_id = f"{entry.entry_id}_wake_pc"

    async def async_press(self) -> None:
        await self._client.async_wake_pc()
