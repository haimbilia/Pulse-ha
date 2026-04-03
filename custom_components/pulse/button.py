from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PulseWakeButton(entry)])


class PulseWakeButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_name = "Wake PC"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_wake_pc"

    async def async_press(self) -> None:
        # TODO: Call Pulse API here
        return
