from __future__ import annotations

from homeassistant.components import webhook
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_WEBHOOK_ID, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    bucket = hass.data[DOMAIN][entry.entry_id]
    webhook_id: str = bucket[DATA_WEBHOOK_ID]
    async_add_entities([PulseWebhookUrlSensor(entry, hass, webhook_id)])


class PulseWebhookUrlSensor(SensorEntity):
    """Diagnostic sensor exposing the firmware-facing webhook URL.

    Lives on the gateway device (via_device root) — users copy this
    value into the firmware via `ha_url` / `ha_webhook` serial commands.
    """

    _attr_has_entity_name = True
    _attr_name = "HA Webhook URL"
    _attr_icon = "mdi:webhook"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self,
        entry: ConfigEntry,
        hass: HomeAssistant,
        webhook_id: str,
    ) -> None:
        self._attr_unique_id = f"{entry.entry_id}_webhook_url"
        self._attr_native_value = webhook.async_generate_url(hass, webhook_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Pulse",
            manufacturer="Pulse",
            model="Gateway",
        )
