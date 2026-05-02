"""Long-lived Pulse TCP event listener."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant

from .api import PulseApiClient, PulseApiError, parse_pulse_event
from .coordinator import PULSE_WAKE_EVENT, PulseDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class PulseTcpEventListener:
    """Listen for async Pulse events on the TCP line protocol."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: PulseApiClient,
        coordinator: PulseDataUpdateCoordinator,
    ) -> None:
        self._hass = hass
        self._client = client
        self._coordinator = coordinator
        self._task: asyncio.Task | None = None
        self._sync_task: asyncio.Task | None = None
        self._last_event_seq = 0
        self._stopping = False

    def start(self) -> None:
        self._task = self._hass.async_create_task(self._run())

    async def async_stop(self) -> None:
        self._stopping = True
        for task in (self._task, self._sync_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._task, self._sync_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    async def _run(self) -> None:
        backoff = 2.0
        while not self._stopping:
            try:
                reader, writer = await asyncio.open_connection(
                    self._client.host,
                    self._client.port,
                )
            except OSError as err:
                _LOGGER.debug("Pulse TCP event listener connect failed: %s", err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
                continue

            backoff = 2.0
            poll_task = asyncio.create_task(self._poll_events(writer))
            try:
                while not self._stopping:
                    raw = await reader.readline()
                    if not raw:
                        break
                    line = raw.decode(errors="replace").strip()
                    if line:
                        self._handle_line(line)
            except (ConnectionError, OSError) as err:
                _LOGGER.debug("Pulse TCP event listener disconnected: %s", err)
            finally:
                poll_task.cancel()
                try:
                    await poll_task
                except asyncio.CancelledError:
                    pass
                except (ConnectionError, OSError):
                    pass
                writer.close()
                try:
                    await writer.wait_closed()
                except (ConnectionError, OSError):
                    pass
                if not self._stopping:
                    await asyncio.sleep(1.0)

    async def _poll_events(self, writer: asyncio.StreamWriter) -> None:
        while not self._stopping:
            writer.write(f"ha_events {self._last_event_seq}\n".encode())
            await writer.drain()
            await asyncio.sleep(2.0)

    def _handle_line(self, line: str) -> None:
        if line.startswith("HA_SYNC|DIRTY"):
            self._schedule_controller_sync()
            return

        if not line.startswith("HA_EVENT|"):
            return
        parts = line.split("|", 2)
        if len(parts) != 3:
            return
        try:
            seq = int(parts[1], 10)
        except ValueError:
            return
        if seq <= self._last_event_seq:
            return
        self._last_event_seq = seq
        event_data = parse_pulse_event(parts[2])
        if event_data is not None:
            self._hass.bus.async_fire(PULSE_WAKE_EVENT, event_data)

    def _schedule_controller_sync(self) -> None:
        if self._sync_task is not None and not self._sync_task.done():
            return
        self._sync_task = self._hass.async_create_task(
            self._sync_controllers(),
        )

    async def _sync_controllers(self) -> None:
        await self._coordinator.async_request_refresh()
        if not self._coordinator.last_update_success:
            return
        try:
            await self._client.async_clear_ha_sync_dirty()
        except PulseApiError as err:
            _LOGGER.debug("Failed to clear Pulse HA sync dirty state: %s", err)
