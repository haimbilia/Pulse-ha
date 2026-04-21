from __future__ import annotations

import asyncio

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import PulseDataUpdateCoordinator, PULSE_WAKE_EVENT

WAKE_TYPES = ("single_press", "pairing_mode")
MOMENTARY_PULSE_SECONDS = 2.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PulseDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    known_macs: set[str] = set()

    async_add_entities([PulseOnlineBinarySensor(entry, coordinator)])

    @callback
    def _sync_controllers() -> None:
        data = coordinator.data or {}
        controllers = data.get("controllers", [])
        new_entities: list[PulseControllerWakeSensor] = []
        for c in controllers:
            mac = c.get("mac", "").lower()
            if not mac or mac in known_macs:
                continue
            known_macs.add(mac)
            for wake_type in WAKE_TYPES:
                new_entities.append(
                    PulseControllerWakeSensor(
                        coordinator=coordinator,
                        entry=entry,
                        mac=mac,
                        controller_name=c.get("name", mac),
                        radio=c.get("radio", "unknown"),
                        wake_type=wake_type,
                    )
                )
        if new_entities:
            async_add_entities(new_entities)

    _sync_controllers()
    entry.async_on_unload(coordinator.async_add_listener(_sync_controllers))


class PulseOnlineBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "PC Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_icon = "mdi:desktop-classic"

    def __init__(self, entry: ConfigEntry, coordinator: PulseDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_pc_online"

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("pcOnline", False))


class PulseControllerWakeSensor(BinarySensorEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: PulseDataUpdateCoordinator,
        entry: ConfigEntry,
        mac: str,
        controller_name: str,
        radio: str,
        wake_type: str,
    ) -> None:
        self._coordinator = coordinator
        self._mac = mac.lower()
        self._wake_type = wake_type
        self._attr_is_on = False
        self._reset_task: asyncio.Task | None = None

        mac_slug = mac.lower().replace(":", "")
        self._attr_unique_id = f"{entry.entry_id}_{mac_slug}_{wake_type}"

        type_label = "Single-press wake" if wake_type == "single_press" else "Pairing-mode wake"
        self._attr_name = type_label

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_controller_{mac_slug}")},
            name=controller_name,
            manufacturer="Pulse",
            model=f"Controller ({radio.upper()})",
            via_device=(DOMAIN, entry.entry_id),
        )

    @property
    def icon(self) -> str:
        return "mdi:gamepad-variant"

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            self.hass.bus.async_listen(PULSE_WAKE_EVENT, self._handle_event)
        )

    @callback
    def _handle_event(self, event: Event) -> None:
        data = event.data
        if data.get("mac", "").lower() != self._mac:
            return
        if data.get("type") != self._wake_type:
            return
        self._fire_momentary()

    @callback
    def _fire_momentary(self) -> None:
        self._attr_is_on = True
        self.async_write_ha_state()
        if self._reset_task is not None and not self._reset_task.done():
            self._reset_task.cancel()
        self._reset_task = self.hass.async_create_task(self._reset_after_delay())

    async def _reset_after_delay(self) -> None:
        try:
            await asyncio.sleep(MOMENTARY_PULSE_SECONDS)
        except asyncio.CancelledError:
            return
        self._attr_is_on = False
        self.async_write_ha_state()
