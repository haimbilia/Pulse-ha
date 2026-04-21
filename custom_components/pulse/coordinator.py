from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PulseApiClient, PulseApiError

_LOGGER = logging.getLogger(__name__)

PULSE_WAKE_EVENT = "pulse_wake_event"


class PulseDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: PulseApiClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="pulse",
            update_interval=timedelta(seconds=5),
        )
        self.client = client
        self._last_event_id = 0

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.async_get_status()
        except PulseApiError as err:
            raise UpdateFailed(str(err)) from err

        try:
            events = await self.client.async_get_events(after=self._last_event_id)
        except PulseApiError as err:
            _LOGGER.debug("Events fetch failed: %s", err)
            events = []

        for event_id, line in events:
            if event_id > self._last_event_id:
                self._last_event_id = event_id
            self._process_event_line(line)

        return status

    def _process_event_line(self, line: str) -> None:
        if not line.startswith("PULSE|"):
            return
        # Format: PULSE|<radio>|<mac>|<name>|<rssi>|delay=N|source=X|type=Y
        parts = line.split("|")
        if len(parts) < 5:
            return

        fields: dict[str, str] = {}
        for seg in parts[5:]:
            if "=" in seg:
                k, v = seg.split("=", 1)
                fields[k] = v

        self.hass.bus.async_fire(
            PULSE_WAKE_EVENT,
            {
                "mac": parts[2].lower(),
                "name": parts[3],
                "radio": parts[1],
                "rssi": parts[4],
                "source": fields.get("source", ""),
                "type": fields.get("type", "pairing_mode"),
            },
        )
