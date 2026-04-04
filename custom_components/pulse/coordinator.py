from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PulseApiClient, PulseApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PulseDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, client: PulseApiClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=5),
        )
        self.client = client

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.async_get_status()
        except PulseApiError as err:
            raise UpdateFailed(str(err)) from err
