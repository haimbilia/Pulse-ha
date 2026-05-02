from __future__ import annotations

import asyncio
import re
from typing import Any, Callable


class PulseApiError(Exception):
    """Raised when the Pulse TCP protocol fails."""


_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")


class PulseApiClient:
    def __init__(self, host: str, port: int, token: str | None = None) -> None:
        self.host = host
        self.port = port
        self.token = token

    async def _exchange(
        self,
        commands: list[str],
        done: Callable[[list[str]], bool],
        *,
        timeout: float = 6.0,
    ) -> list[str]:
        lines: list[str] = []
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=timeout,
            )
        except OSError as err:
            raise PulseApiError("Failed to connect to Pulse TCP server") from err

        try:
            for command in commands:
                writer.write(f"{command}\n".encode())
            await writer.drain()

            deadline = asyncio.get_running_loop().time() + timeout
            while not done(lines):
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise PulseApiError("Pulse TCP response timed out")
                raw = await asyncio.wait_for(reader.readline(), timeout=remaining)
                if not raw:
                    break
                line = raw.decode(errors="replace").strip()
                if line:
                    lines.append(line)
            return lines
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def async_get_status(self) -> dict[str, Any]:
        """Fetch a status snapshot over the Pulse TCP line protocol."""
        try:
            lines = await self._exchange(
                ["status", "wifi_status", "ha_sync_status", "l"],
                lambda current: any(line == "LIST_END" for line in current),
                timeout=6.0,
            )
        except (asyncio.TimeoutError, PulseApiError, OSError) as err:
            raise PulseApiError("Failed to fetch Pulse status") from err

        return _parse_status_snapshot(lines)

    async def async_clear_ha_sync_dirty(self) -> None:
        """Tell WiFi_NODE that Home Assistant has synced saved controllers."""
        try:
            lines = await self._exchange(
                ["session_take", "ha_sync_clear"],
                lambda current: any(
                    line.startswith("HA_SYNC|STATE|")
                    or line.startswith("OK|ha_sync_clear")
                    or line.startswith("ERR|")
                    for line in current
                ),
                timeout=6.0,
            )
        except (asyncio.TimeoutError, PulseApiError, OSError) as err:
            raise PulseApiError("Failed to clear Pulse HA sync state") from err

        error = next((line for line in lines if line.startswith("ERR|")), None)
        if error:
            raise PulseApiError(error)

    async def async_wake_pc(self, target_id: str | None = None) -> None:
        """Trigger a Pulse wake/power pulse over TCP."""
        try:
            lines = await self._exchange(
                ["session_take", "pulse"],
                lambda current: any(
                    line.startswith("PULSE|QUEUED")
                    or line.startswith("PULSE|FIRED")
                    or line.startswith("ERR|")
                    for line in current
                ),
                timeout=6.0,
            )
        except (asyncio.TimeoutError, PulseApiError, OSError) as err:
            raise PulseApiError("Failed to trigger Pulse wake") from err

        error = next((line for line in lines if line.startswith("ERR|")), None)
        if error:
            raise PulseApiError(error)

    async def async_is_pc_online(self, target_id: str | None = None) -> bool:
        status = await self.async_get_status()
        return bool(status.get("pcOnline", False))

    async def async_get_events(self, after: int = 0) -> list[tuple[int, str]]:
        """Event polling is no longer part of the Pulse control protocol."""
        return []


def _parse_status_snapshot(lines: list[str]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "deviceName": "pulse",
        "controllers": [],
        "pcOnline": None,
        "tcpConnected": True,
    }

    for line in lines:
        if line.startswith("STATUS|"):
            _parse_pipe_kv(line, data)
        elif line.startswith("WIFI|STATUS|CONNECTED|"):
            parts = line.split("|")
            if len(parts) >= 5:
                data["wifiConnected"] = True
                data["ssid"] = parts[3]
                data["ip"] = parts[4]
            if len(parts) >= 6:
                data["rssi"] = _safe_int(parts[5])
        elif line.startswith("WIFI|STATUS|"):
            data["wifiConnected"] = False
            data["wifiStatus"] = line.removeprefix("WIFI|STATUS|").lower()
        elif line.startswith("WIFI|STATE|"):
            data["wifiEnabled"] = line.endswith("|ENABLED")
        elif line.startswith("HA_SYNC|STATE|"):
            _parse_ha_sync_state(line, data)
        elif line.startswith("PULSE_WIFI|HELLO|"):
            _parse_wifi_hello(line, data)
        else:
            controller = _parse_controller_line(line)
            if controller:
                data["controllers"].append(controller)

    return data


def _parse_pipe_kv(line: str, data: dict[str, Any]) -> None:
    for token in line.split("|")[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key == "ver":
            data["fw"] = value
        elif key == "wifi":
            data["wifiStatus"] = value
            data["wifiConnected"] = value == "connected"
        elif key == "ip":
            data["ip"] = value
        elif key == "owner":
            data["owner"] = value
        else:
            data[key] = value


def _parse_wifi_hello(line: str, data: dict[str, Any]) -> None:
    for token in line.split("|")[2:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key == "fw":
            data["wifiFw"] = value
        elif key == "build":
            data["wifiBuild"] = value
        elif key == "api":
            data["wifiApi"] = value


def _parse_ha_sync_state(line: str, data: dict[str, Any]) -> None:
    for token in line.split("|")[2:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key == "dirty":
            data["haSyncDirty"] = value == "1"
        elif key == "reason":
            data["haSyncReason"] = value


def parse_pulse_event(line: str) -> dict[str, Any] | None:
    """Parse a BT_NODE PULSE event into Home Assistant event data."""
    if not line.startswith("PULSE|"):
        return None
    parts = line.split("|")
    if len(parts) < 5:
        return None
    source = parts[1]
    mac = parts[2].lower()
    if not _MAC_RE.match(mac):
        return None

    attrs: dict[str, str] = {}
    for token in parts[4:]:
        if "=" in token:
            key, value = token.split("=", 1)
            attrs[key] = value

    wake_type = "single_press" if attrs.get("sp") == "1" else "wake_mode"
    return {
        "mac": mac,
        "type": wake_type,
        "source": source,
        "name": parts[3],
        "line": line,
    }


def _parse_controller_line(line: str) -> dict[str, Any] | None:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 7 or not _MAC_RE.match(parts[0]):
        return None

    return {
        "mac": parts[0].lower(),
        "name": parts[1] or parts[0].lower(),
        "delay": _safe_int(parts[2].removesuffix("s")),
        "radio": parts[3].lower(),
        "pm_action": _safe_int(parts[4]),
        "sp_action": _safe_int(parts[5]),
        "singlePressValidated": bool(_safe_int(parts[6])),
    }


def _safe_int(value: str | None) -> int:
    try:
        return int(str(value or "").strip(), 10)
    except ValueError:
        return 0
