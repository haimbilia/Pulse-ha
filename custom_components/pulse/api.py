from __future__ import annotations

import asyncio
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

    async def _request_json(self, path: str) -> dict[str, Any]:
        async with self._session.get(
            f"{self._base_url}{path}",
            headers=self._headers(),
            timeout=10,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        if not isinstance(data, dict):
            raise PulseApiError("Pulse status payload was not a JSON object")

        return data

    async def async_get_status(self) -> dict[str, Any]:
        try:
            data = await self._request_json("/status")
        except (ClientError, TimeoutError, ValueError) as err:
            raise PulseApiError("Failed to fetch Pulse status") from err

        return data

    async def _wake_once(self, method: str) -> None:
        request = getattr(self._session, method.lower())
        async with request(
            f"{self._base_url}/wake",
            headers=self._headers(),
            timeout=10,
        ) as response:
            response.raise_for_status()
            await response.read()

    async def async_wake_pc(self, target_id: str | None = None) -> None:
        attempts = ("post", "get", "post")
        last_error: Exception | None = None

        for index, method in enumerate(attempts):
            try:
                await self._wake_once(method)
                return
            except (ClientError, TimeoutError) as err:
                last_error = err
                if index < len(attempts) - 1:
                    await asyncio.sleep(0.4)

        raise PulseApiError("Failed to trigger Pulse wake") from last_error

    async def async_is_pc_online(self, target_id: str | None = None) -> bool:
        status = await self.async_get_status()
        return bool(status.get("pcOnline", False))
