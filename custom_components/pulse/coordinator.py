"""Coordinator — pure data holder, no polling.

Updated by the webhook handler in __init__.py via async_set_updated_data
when the firmware pushes a "state" payload. The firmware also pushes
"pulse" events directly to the bus; the coordinator only carries the
periodic state snapshot.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import PulseApiClient

_LOGGER = logging.getLogger(__name__)

PULSE_WAKE_EVENT = "pulse_wake_event"


class PulseDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, client: PulseApiClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="pulse",
            # No update_interval — this coordinator does not poll. Data
            # arrives via the firmware webhook push handler.
        )
        self.client = client
        # Seed with empty state so platforms can read coordinator.data
        # safely before the first push arrives.
        self.data = {"controllers": [], "pcOnline": None}

    async def _async_update_data(self) -> dict[str, Any]:
        # Coordinator is push-driven; never refresh on its own. If HA
        # asks for an update (e.g. async_config_entry_first_refresh),
        # just return whatever we have.
        return self.data
