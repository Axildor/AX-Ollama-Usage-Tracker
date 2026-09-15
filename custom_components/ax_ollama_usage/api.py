"""HTTP client for the undocumented ollama.com usage endpoint.

The endpoint is verified-but-undocumented (verified live 2026-09-14):

    GET https://ollama.com/api/usage
    Authorization: Bearer <api_key>
    Accept: application/json

Treat the response shape as a model, not a contract — Ollama may change or
break it without notice.  This client performs a single read-only GET per
call and never issues any other HTTP verb against ollama.com.
"""

from __future__ import annotations

from typing import Any, Final

import aiohttp

from .const import (
    API_BASE_URL,
    REQUEST_TIMEOUT,
    USAGE_ENDPOINT,
    USER_AGENT,
)

__all__ = [
    "OllamaApiError",
    "OllamaAuthError",
    "OllamaClient",
    "OllamaRateLimitError",
]


class OllamaApiError(Exception):
    """Base error for the Ollama usage API client."""


class OllamaAuthError(OllamaApiError):
    """HTTP 401 — invalid credentials (bad or revoked API key)."""


class OllamaRateLimitError(OllamaApiError):
    """HTTP 429 — rate limited by ollama.com."""


class OllamaClient:
    """Thin async client for ``GET /api/usage``.

    A single :class:`aiohttp.ClientSession` is reused across polls.  The
    session is owned by the caller (the coordinator) and must be closed
    via :meth:`close` when the integration unloads.
    """

    def __init__(
        self, session: aiohttp.ClientSession, base_url: str = API_BASE_URL
    ) -> None:
        """Initialize the client with a shared aiohttp session.

        ``base_url`` defaults to the production endpoint; tests may point
        it at a local aiohttp test server.
        """
        self._session = session
        self._base_url = base_url.rstrip("/")

    async def async_get_usage(self, api_key: str) -> dict[str, Any]:
        """Fetch the usage payload.

        Returns the parsed JSON dict.  Raises:
        - :class:`OllamaAuthError` on HTTP 401
        - :class:`OllamaRateLimitError` on HTTP 429
        - :class:`OllamaApiError` on other non-200 statuses or bad JSON
        - :class:`aiohttp.ClientError` / :class:`asyncio.TimeoutError` on
          network problems (callers convert these to ``UpdateFailed``)
        """
        url: Final = f"{self._base_url}{USAGE_ENDPOINT}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self._session.get(
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401:
                    raise OllamaAuthError("invalid credentials")
                if resp.status == 429:
                    raise OllamaRateLimitError("rate limited by ollama.com")
                if resp.status != 200:
                    text = await resp.text()
                    raise OllamaApiError(
                        f"unexpected HTTP {resp.status} from {url}: {text[:200]}"
                    )
                try:
                    data: dict[str, Any] = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise OllamaApiError(f"non-JSON response from {url}") from err
        except TimeoutError as err:
            raise OllamaApiError(f"timeout fetching {url}") from err
        if not isinstance(data, dict):
            raise OllamaApiError(f"unexpected payload type from {url}")
        return data

    async def close(self) -> None:
        """Close the underlying aiohttp session."""
        await self._session.close()
