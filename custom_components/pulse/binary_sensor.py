from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities([PulseOnlineBinarySensor(entry, coordinator)])


class PulseOnlineBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "PC Online"

    def __init__(self, entry: ConfigEntry, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_pc_online"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("pcOnline", False))
