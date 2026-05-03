from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_HOST, CONF_PORT, DATA_EVENT_LISTENER, DOMAIN


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    listener = hass.data[DOMAIN][entry.entry_id][DATA_EVENT_LISTENER]
    async_add_entities([PulseTcpEndpointSensor(entry), PulseEventDiagnosticsSensor(entry, listener)])


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


class PulseEventDiagnosticsSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Event diagnostics"
    _attr_icon = "mdi:timeline-question"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, listener) -> None:
        self._listener = listener
        self._attr_unique_id = f"{entry.entry_id}_event_diagnostics"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Pulse",
            manufacturer="Pulse",
            model="Gateway",
        )
        self._refresh_from_listener()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._listener.async_add_listener(self._handle_update))

    def _handle_update(self) -> None:
        self._refresh_from_listener()
        self.async_write_ha_state()

    def _refresh_from_listener(self) -> None:
        diagnostics = self._listener.diagnostics
        self._attr_native_value = diagnostics["state"]
        self._attr_extra_state_attributes = diagnostics
