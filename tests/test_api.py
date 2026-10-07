"""Tests for the HTTP client (api.py) against a real local aiohttp server.

Note: the task spec called for aioresponses, but aioresponses 0.7.9 (and
respx 0.23) are incompatible with the aiohttp 3.14 pin in HA 2026.x —
``ClientResponse`` now requires a ``stream_writer`` kwarg.  A real local
aiohttp test server exercises the genuine request/response path instead.
"""

from __future__ import annotations

import aiohttp
import pytest

from custom_components.ax_ollama_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaClient,
    OllamaForbiddenError,
    OllamaRateLimitError,
)

from .conftest import (
    FORBIDDEN_BODY,
    SAMPLE_BALANCE_LEGACY,
    SAMPLE_USAGE_24H,
    UNAUTH_BODY,
)


def _client(base_url: str) -> tuple[OllamaClient, aiohttp.ClientSession]:
    session = aiohttp.ClientSession()
    return OllamaClient(session, base_url=base_url), session


# ---------------------------------------------------------------------------
# Balance endpoint
# ---------------------------------------------------------------------------


async def test_balance_happy_path(usage_server) -> None:
    """200 with the verbatim legacy balance returns the parsed dict."""
    usage_server.json_payload = SAMPLE_BALANCE_LEGACY
    client, session = _client(usage_server.url)
    try:
        data = await client.async_get_balance("k")
    finally:
        await session.close()
    assert data == SAMPLE_BALANCE_LEGACY


async def test_balance_sends_no_query_params(usage_server) -> None:
    """The balance GET carries no query params (server 400s on any)."""
    usage_server.json_payload = SAMPLE_BALANCE_LEGACY
    client, session = _client(usage_server.url)
    try:
        await client.async_get_balance("k")
    finally:
        await session.close()
    request = usage_server.requests[0]
    assert request.path == "/api/balance"
    assert not request.query  # empty MultiDict


async def test_usage_sends_range_param(usage_server) -> None:
    """The usage GET carries range=24h (and range=7d when requested)."""
    usage_server.json_payload = SAMPLE_USAGE_24H
    client, session = _client(usage_server.url)
    try:
        await client.async_get_usage("k", "24h")
        await client.async_get_usage("k", "7d")
    finally:
        await session.close()
    assert usage_server.requests[0].query["range"] == "24h"
    assert usage_server.requests[1].query["range"] == "7d"


async def test_auth_headers_sent(usage_server) -> None:
    """The request carries Bearer auth, Accept JSON, and the HA User-Agent."""
    usage_server.json_payload = SAMPLE_BALANCE_LEGACY
    client, session = _client(usage_server.url)
    try:
        await client.async_get_balance("secret-key")
    finally:
        await session.close()
    request = usage_server.requests[0]
    assert request.headers["Authorization"] == "Bearer secret-key"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"].startswith("ha-ollama-cloud-usage/")


# ---------------------------------------------------------------------------
# Error mapping (exercised via the balance endpoint; _get_json is shared)
# ---------------------------------------------------------------------------


async def test_401_raises_auth_error(usage_server) -> None:
    """HTTP 401 → OllamaAuthError."""
    usage_server.status = 401
    usage_server.json_payload = UNAUTH_BODY
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaAuthError):
            await client.async_get_balance("k")
    finally:
        await session.close()


async def test_403_raises_forbidden_error(usage_server) -> None:
    """HTTP 403 → OllamaForbiddenError (account suspended / scope)."""
    usage_server.status = 403
    usage_server.json_payload = FORBIDDEN_BODY
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaForbiddenError):
            await client.async_get_balance("k")
    finally:
        await session.close()


async def test_403_is_not_auth_error(usage_server) -> None:
    """403 must NOT be caught as OllamaAuthError (key is valid)."""
    usage_server.status = 403
    usage_server.json_payload = FORBIDDEN_BODY
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaForbiddenError):
            await client.async_get_balance("k")
    finally:
        await session.close()


async def test_429_with_retry_after_header(usage_server) -> None:
    """HTTP 429 + Retry-After: 60 → OllamaRateLimitError(retry_after=60)."""
    usage_server.status = 429
    usage_server.retry_after = "60"
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaRateLimitError) as excinfo:
            await client.async_get_balance("k")
    finally:
        await session.close()
    assert excinfo.value.retry_after == 60


async def test_429_without_retry_after_header(usage_server) -> None:
    """HTTP 429 without the header → retry_after is None."""
    usage_server.status = 429
    usage_server.retry_after = None
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaRateLimitError) as excinfo:
            await client.async_get_balance("k")
    finally:
        await session.close()
    assert excinfo.value.retry_after is None


async def test_429_non_integer_retry_after(usage_server) -> None:
    """A non-integer Retry-After value degrades to None (tolerant)."""
    usage_server.status = 429
    usage_server.retry_after = "soon"
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaRateLimitError) as excinfo:
            await client.async_get_balance("k")
    finally:
        await session.close()
    assert excinfo.value.retry_after is None


async def test_500_raises_api_error(usage_server) -> None:
    """HTTP 5xx → OllamaApiError."""
    usage_server.status = 503
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_balance("k")
    finally:
        await session.close()


async def test_timeout_raises_api_error(usage_server) -> None:
    """Timeout → OllamaApiError (converted from asyncio.TimeoutError)."""
    usage_server.delay = 20.0  # exceeds the 15 s client timeout
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_balance("k")
    finally:
        await session.close()


async def test_non_json_raises_api_error(usage_server) -> None:
    """HTML garbage → OllamaApiError."""
    usage_server.text_body = "<html>oops</html>"
    usage_server.content_type = "text/html"
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_balance("k")
    finally:
        await session.close()
