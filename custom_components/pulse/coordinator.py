"""Coordinator for the Pulse TCP integration."""

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
            update_interval=timedelta(seconds=30),
        )
        self.client = client
        self.data = {"controllers": [], "pcOnline": None}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_status()
        except PulseApiError as err:
            raise UpdateFailed(str(err)) from err
