"""Long-lived Pulse TCP event listener."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

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
        self._callbacks: list[Callable[[], None]] = []
        self._state = "idle"
        self._connected = False
        self._connect_count = 0
        self._disconnect_count = 0
        self._poll_count = 0
        self._raw_line_count = 0
        self._ha_event_count = 0
        self._parsed_event_count = 0
        self._fired_event_count = 0
        self._ignored_line_count = 0
        self._error_count = 0
        self._last_poll_at: datetime | None = None
        self._last_connect_at: datetime | None = None
        self._last_disconnect_at: datetime | None = None
        self._last_raw_line: str | None = None
        self._last_ha_event_line: str | None = None
        self._last_event_payload: str | None = None
        self._last_parsed_event: dict[str, Any] | None = None
        self._last_ignored_reason: str | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        self._state = "starting"
        self._notify()
        self._task = self._hass.async_create_task(self._run())

    async def async_stop(self) -> None:
        self._stopping = True
        self._state = "stopping"
        self._notify()
        for task in (self._task, self._sync_task):
            if task is not None and not task.done():
                task.cancel()
        for task in (self._task, self._sync_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._state = "stopped"
        self._connected = False
        self._notify()

    def async_add_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        self._callbacks.append(callback)

        def _remove() -> None:
            if callback in self._callbacks:
                self._callbacks.remove(callback)

        return _remove

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "connected": self._connected,
            "connect_count": self._connect_count,
            "disconnect_count": self._disconnect_count,
            "poll_count": self._poll_count,
            "raw_line_count": self._raw_line_count,
            "ha_event_count": self._ha_event_count,
            "parsed_event_count": self._parsed_event_count,
            "fired_event_count": self._fired_event_count,
            "ignored_line_count": self._ignored_line_count,
            "error_count": self._error_count,
            "last_event_seq": self._last_event_seq,
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "last_connect_at": self._last_connect_at.isoformat() if self._last_connect_at else None,
            "last_disconnect_at": self._last_disconnect_at.isoformat() if self._last_disconnect_at else None,
            "last_raw_line": self._last_raw_line,
            "last_ha_event_line": self._last_ha_event_line,
            "last_event_payload": self._last_event_payload,
            "last_parsed_event": self._last_parsed_event,
            "last_ignored_reason": self._last_ignored_reason,
            "last_error": self._last_error,
        }

    def _notify(self) -> None:
        for callback in tuple(self._callbacks):
            callback()

    async def _run(self) -> None:
        backoff = 2.0
        while not self._stopping:
            self._state = "connecting"
            self._notify()
            try:
                reader, writer = await asyncio.open_connection(
                    self._client.host,
                    self._client.port,
                )
            except OSError as err:
                self._connected = False
                self._state = "connect_failed"
                self._error_count += 1
                self._last_error = str(err)
                self._notify()
                _LOGGER.debug("Pulse TCP event listener connect failed: %s", err)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
                continue

            backoff = 2.0
            self._connected = True
            self._state = "connected"
            self._connect_count += 1
            self._last_connect_at = dt_util.utcnow()
            self._last_error = None
            self._notify()
            poll_task = asyncio.create_task(self._poll_events(writer))
            try:
                while not self._stopping:
                    raw = await reader.readline()
                    if not raw:
                        break
                    line = raw.decode(errors="replace").strip()
                    if line:
                        self._raw_line_count += 1
                        self._last_raw_line = line
                        self._handle_line(line)
            except (ConnectionError, OSError) as err:
                self._error_count += 1
                self._last_error = str(err)
                _LOGGER.debug("Pulse TCP event listener disconnected: %s", err)
            finally:
                self._connected = False
                self._state = "disconnected" if not self._stopping else "stopping"
                self._disconnect_count += 1
                self._last_disconnect_at = dt_util.utcnow()
                self._notify()
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
            self._poll_count += 1
            self._last_poll_at = dt_util.utcnow()
            self._notify()
            await asyncio.sleep(2.0)

    def _handle_line(self, line: str) -> None:
        if line.startswith("HA_SYNC|DIRTY"):
            self._schedule_controller_sync()
            self._notify()
            return

        if line.startswith("PULSE|"):
            self._last_event_payload = line
            event_data = parse_pulse_event(line)
            if event_data is not None:
                self._parsed_event_count += 1
                self._last_parsed_event = event_data
                self._hass.bus.async_fire(PULSE_WAKE_EVENT, event_data)
                self._fired_event_count += 1
                self._last_ignored_reason = None
            else:
                self._ignored_line_count += 1
                self._last_ignored_reason = "pulse_parse_failed"
            self._notify()
            return

        if not line.startswith("HA_EVENT|"):
            self._ignored_line_count += 1
            self._last_ignored_reason = "not_ha_event"
            self._notify()
            return
        self._ha_event_count += 1
        self._last_ha_event_line = line
        parts = line.split("|", 2)
        if len(parts) != 3:
            self._ignored_line_count += 1
            self._last_ignored_reason = "bad_ha_event_format"
            self._notify()
            return
        try:
            seq = int(parts[1], 10)
        except ValueError:
            self._ignored_line_count += 1
            self._last_ignored_reason = "bad_ha_event_seq"
            self._notify()
            return
        if seq <= self._last_event_seq:
            self._ignored_line_count += 1
            self._last_ignored_reason = "duplicate_or_old_seq"
            self._notify()
            return
        self._last_event_seq = seq
        self._last_event_payload = parts[2]
        event_data = parse_pulse_event(self._last_event_payload)
        if event_data is not None:
            self._parsed_event_count += 1
            self._last_parsed_event = event_data
            self._hass.bus.async_fire(PULSE_WAKE_EVENT, event_data)
            self._fired_event_count += 1
        else:
            self._ignored_line_count += 1
            self._last_ignored_reason = "pulse_parse_failed"
        self._notify()

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
