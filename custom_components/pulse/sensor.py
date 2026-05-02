from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DOMAIN


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PulseTcpEndpointSensor(entry)])


class PulseTcpEndpointSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "TCP Endpoint"
    _attr_icon = "mdi:ethernet"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        self._attr_unique_id = f"{entry.entry_id}_tcp_endpoint"
        self._attr_native_value = f"{host}:{port}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Pulse",
            manufacturer="Pulse",
            model="Gateway",
        )
