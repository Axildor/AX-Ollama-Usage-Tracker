"""HTTP client for the ollama.com usage/balance endpoints.

The endpoints are documented (OpenAPI specs at docs.ollama.com/api/
balance.md and docs.ollama.com/api/cloud-usage.md; live-validated
2026-10-07):

    GET https://ollama.com/api/balance          (no query params)
    GET https://ollama.com/api/usage?range=24h  (range: 24h | 7d | 30d)

    Authorization: Bearer <api_key>
    Accept: application/json

Treat the response shapes as models, not contracts — this API family
has mutated before.  This client performs read-only GETs per call and
never issues any other HTTP verb against ollama.com.

Error mapping (per the official specs):
- 401 → :class:`OllamaAuthError` (invalid credentials)
- 403 → :class:`OllamaForbiddenError` (account suspended / team scope
  without admin access — the key is VALID; do not trigger reauth)
- 429 → :class:`OllamaRateLimitError` carrying ``retry_after`` from the
  guaranteed ``Retry-After`` header (``None`` when absent)
- other non-200 → :class:`OllamaApiError`
"""

from __future__ import annotations

from typing import Any, Final

import aiohttp

from .const import (
    API_BASE_URL,
    BALANCE_ENDPOINT,
    REQUEST_TIMEOUT,
    USAGE_ENDPOINT,
    USER_AGENT,
)

__all__ = [
    "OllamaApiError",
    "OllamaAuthError",
    "OllamaClient",
    "OllamaForbiddenError",
    "OllamaRateLimitError",
]


class OllamaApiError(Exception):
    """Base error for the Ollama usage API client."""


class OllamaAuthError(OllamaApiError):
    """HTTP 401 — invalid credentials (bad or revoked API key)."""


class OllamaForbiddenError(OllamaApiError):
    """HTTP 403 — account suspended, or team scope without admin access.

    The API key itself is valid in this state; callers must NOT treat
    this as an auth failure or trigger reauth.
    """


class OllamaRateLimitError(OllamaApiError):
    """HTTP 429 — rate limited by ollama.com.

    ``retry_after`` carries the server's ``Retry-After`` header value in
    seconds, or ``None`` when the header is absent.  Callers must honor
    it exactly (never multiplied or compounded).
    """

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        """Initialize with the message and optional Retry-After seconds."""
        super().__init__(message)
        self.retry_after = retry_after


class OllamaClient:
    """Thin async client for the balance and usage endpoints.

    A single :class:`aiohttp.ClientSession` is reused across polls.  The
    session is owned by Home Assistant (``async_get_clientsession``) and
    is NOT closed by this client — closing a shared session would break
    every other consumer of it.
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

    async def _get_json(
        self, path: str, api_key: str, params: dict[str, str] | None = None
    ) -> dict[str, Any]:
        """Perform one authenticated GET and return the parsed JSON dict.

        Raises:
        - :class:`OllamaAuthError` on HTTP 401
        - :class:`OllamaForbiddenError` on HTTP 403
        - :class:`OllamaRateLimitError` on HTTP 429 (with ``retry_after``)
        - :class:`OllamaApiError` on other non-200 statuses or bad JSON
        - :class:`aiohttp.ClientError` / :class:`asyncio.TimeoutError` on
          network problems (callers convert these to ``UpdateFailed``)
        """
        url: Final = f"{self._base_url}{path}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                if resp.status == 401:
                    raise OllamaAuthError("invalid credentials")
                if resp.status == 403:
                    text = await resp.text()
                    raise OllamaForbiddenError(
                        f"account suspended or insufficient scope: {text[:200]}"
                    )
                if resp.status == 429:
                    retry_after: int | None = None
                    raw_retry = resp.headers.get("Retry-After")
                    if raw_retry is not None:
                        try:
                            retry_after = int(raw_retry)
                        except ValueError:
                            retry_after = None
                    raise OllamaRateLimitError(
                        "rate limited by ollama.com", retry_after=retry_after
                    )
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

    async def async_get_balance(self, api_key: str) -> dict[str, Any]:
        """Fetch the balance payload (GET /api/balance, no query params).

        The server returns HTTP 400 if any query parameters are sent.
        """
        return await self._get_json(BALANCE_ENDPOINT, api_key)

    async def async_get_usage(self, api_key: str, range: str) -> dict[str, Any]:
        """Fetch the usage payload (GET /api/usage?range=<range>).

        ``range`` is one of ``24h``, ``7d``, ``30d``; granularity is
        server-set (hour for 24h, day for 7d/30d).
        """
        return await self._get_json(USAGE_ENDPOINT, api_key, params={"range": range})
