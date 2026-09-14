"""Tests for the HTTP client (api.py) against a real local aiohttp server.

Note: the task spec called for aioresponses, but aioresponses 0.7.9 (and
respx 0.23) are incompatible with the aiohttp 3.14 pin in HA 2026.x —
``ClientResponse`` now requires a ``stream_writer`` kwarg.  A real local
aiohttp test server exercises the genuine request/response path instead.
"""

from __future__ import annotations

import aiohttp
import pytest

from custom_components.ollama_cloud_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaClient,
    OllamaRateLimitError,
)

from .conftest import UNAUTH_BODY


def _client(base_url: str) -> tuple[OllamaClient, aiohttp.ClientSession]:
    session = aiohttp.ClientSession()
    return OllamaClient(session, base_url=base_url), session


async def test_happy_path_parses_json(usage_server, sample_legacy: dict) -> None:
    """200 with the verbatim sample returns the parsed dict."""
    usage_server.json_payload = sample_legacy
    client, session = _client(usage_server.url)
    try:
        data = await client.async_get_usage("k")
    finally:
        await session.close()
    assert data == sample_legacy


async def test_auth_headers_sent(usage_server, sample_legacy: dict) -> None:
    """The request carries Bearer auth, Accept JSON, and the HA User-Agent."""
    usage_server.json_payload = sample_legacy
    client, session = _client(usage_server.url)
    try:
        await client.async_get_usage("secret-key")
    finally:
        await session.close()
    request = usage_server.requests[0]
    assert request.headers["Authorization"] == "Bearer secret-key"
    assert request.headers["Accept"] == "application/json"
    assert request.headers["User-Agent"].startswith("ha-ollama-cloud-usage/")


async def test_401_raises_auth_error(usage_server) -> None:
    """HTTP 401 → OllamaAuthError."""
    usage_server.status = 401
    usage_server.json_payload = UNAUTH_BODY
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaAuthError):
            await client.async_get_usage("k")
    finally:
        await session.close()


async def test_429_raises_rate_limit(usage_server) -> None:
    """HTTP 429 → OllamaRateLimitError."""
    usage_server.status = 429
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaRateLimitError):
            await client.async_get_usage("k")
    finally:
        await session.close()


async def test_500_raises_api_error(usage_server) -> None:
    """HTTP 5xx → OllamaApiError."""
    usage_server.status = 503
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_usage("k")
    finally:
        await session.close()


async def test_timeout_raises_api_error(usage_server) -> None:
    """Timeout → OllamaApiError (converted from asyncio.TimeoutError)."""
    usage_server.delay = 20.0  # exceeds the 15 s client timeout
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_usage("k")
    finally:
        await session.close()


async def test_non_json_raises_api_error(usage_server) -> None:
    """HTML garbage → OllamaApiError."""
    usage_server.text_body = "<html>oops</html>"
    usage_server.content_type = "text/html"
    client, session = _client(usage_server.url)
    try:
        with pytest.raises(OllamaApiError):
            await client.async_get_usage("k")
    finally:
        await session.close()
