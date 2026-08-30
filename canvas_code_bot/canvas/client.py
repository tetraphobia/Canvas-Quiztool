from __future__ import annotations

import aiohttp

from canvas_code_bot.core.exceptions import (
    CanvasAuthError,
    CanvasError,
    CanvasNotFoundError,
)


class CanvasClient:
    """Async HTTP client for a single Canvas instance."""

    def __init__(
        self, base_url: str, token: str, session: aiohttp.ClientSession
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        self._session = session

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def get(self, path: str) -> dict:
        """GET ``path``; returns parsed JSON. Raises CanvasError on non-2xx."""
        async with self._session.get(
            self._url(path), headers=self._headers
        ) as resp:
            await self._check_response(resp)
            return await resp.json()

    async def put(self, path: str, payload: dict) -> tuple[int, dict | None]:
        """
        PUT ``path`` with JSON ``payload``.
        Returns ``(status_code, body_dict_or_None)``.
        Raises CanvasError on non-2xx.
        """
        async with self._session.put(
            self._url(path),
            headers={**self._headers, "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            await self._check_response(resp)
            if resp.status == 204:
                return 204, None
            return resp.status, await resp.json()

    async def patch(self, path: str, payload: dict) -> tuple[int, dict | None]:
        """
        PATCH ``path`` with JSON ``payload``.
        Returns ``(status_code, body_dict_or_None)``.
        Raises CanvasError on non-2xx.
        """
        async with self._session.patch(
            self._url(path),
            headers={**self._headers, "Content-Type": "application/json"},
            json=payload,
        ) as resp:
            await self._check_response(resp)
            if resp.status == 204:
                return 204, None
            return resp.status, await resp.json()

    async def _check_response(self, resp: aiohttp.ClientResponse) -> None:
        if resp.status == 401:
            raise CanvasAuthError(
                "Canvas: 401 Unauthorized — check your token", http_status=401
            )
        if resp.status == 404:
            raise CanvasNotFoundError(
                "Canvas: 404 Not Found — check course/assignment IDs",
                http_status=404,
            )
        if resp.status >= 400:
            body = await resp.text()
            raise CanvasError(
                f"Canvas error {resp.status}: {body[:300]}", http_status=resp.status
            )
