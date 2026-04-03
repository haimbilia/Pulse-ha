from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PulseOnlineBinarySensor(entry)])


class PulseOnlineBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "PC Online"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_pc_online"

    @property
    def is_on(self) -> bool:
        return False
