from __future__ import annotations

from typing import Any

from aiohttp import ClientError, ClientSession


class PulseApiError(Exception):
    """Raised when the Pulse device API fails."""


class PulseApiClient:
    def __init__(self, session: ClientSession, host: str, port: int, token: str | None = None) -> None:
        self._session = session
        self.host = host
        self.port = port
        self.token = token

    @property
    def _base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"X-Pulse-Token": self.token}

    async def async_get_status(self) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{self._base_url}/status",
                headers=self._headers(),
                timeout=10,
            ) as response:
                response.raise_for_status()
                data = await response.json()
        except (ClientError, TimeoutError, ValueError) as err:
            raise PulseApiError("Failed to fetch Pulse status") from err

        if not isinstance(data, dict):
            raise PulseApiError("Pulse status payload was not a JSON object")

        return data

    async def async_wake_pc(self, target_id: str | None = None) -> None:
        try:
            async with self._session.post(
                f"{self._base_url}/wake",
                headers=self._headers(),
                timeout=10,
            ) as response:
                response.raise_for_status()
                await response.read()
        except (ClientError, TimeoutError) as err:
            raise PulseApiError("Failed to trigger Pulse wake") from err

    async def async_is_pc_online(self, target_id: str | None = None) -> bool:
        status = await self.async_get_status()
        return bool(status.get("pcOnline", False))
