"""Shared fixtures for the AX Ollama Usage Tracker test suite.

HTTP mocking strategy: ``aioresponses`` 0.7.9 and ``respx`` 0.23 are both
incompatible with the aiohttp 3.14 pin in HA 2026.x (``ClientResponse``
now requires a ``stream_writer`` kwarg).  Instead we use:

- a real ``aiohttp`` test server (``aiohttp.test_utils.TestServer``) for
  the HTTP-client tests in ``test_api.py`` — this exercises the genuine
  aiohttp request/response path;
- a stub client injected into the coordinator for coordinator/watchdog
  tests, which exercise coordinator logic rather than HTTP.

Payload fixtures are the verbatim live-validated server responses
(2026-10-07) — canonical, not invented.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

BALANCE_PATH = "/api/balance"
USAGE_PATH = "/api/usage"

# Verbatim legacy-account balance (live 2026-10-07) — primary fixture.
SAMPLE_BALANCE_LEGACY = {
    "included": {
        "session": {
            "remaining_percent": 98.77,
            "resets_at": "2026-10-07T08:00:00Z",
        },
        "weekly": {
            "remaining_percent": 67.54,
            "resets_at": "2026-10-12T00:00:00Z",
        },
    },
    "purchased": {"balance_usd": 0},
}

# Verbatim credits-account balance (official docs' oneOf example).
SAMPLE_BALANCE_CREDITS = {
    "included": {
        "balance_usd": 72.5,
        "allowance_usd": 100,
        "period": {
            "from": "2026-09-15T09:30:00Z",
            "until": "2026-10-15T09:30:00Z",
        },
    },
    "purchased": {"balance_usd": 25},
}

# Verbatim usage 24h response (live 2026-10-07): granularity=hour,
# 25 buckets (24 complete zero-filled + final partial), totals carry
# request_count only — legacy plans omit usage_usd/input_tokens.
SAMPLE_USAGE_24H = {
    "range": "24h",
    "scope": "self",
    "granularity": "hour",
    "from": "2026-10-06T03:00:00Z",
    "until": "2026-10-07T03:17:54.970791219Z",
    "totals": {"request_count": 327},
    "buckets": [
        {
            "from": "2026-10-06T03:00:00Z",
            "until": "2026-10-06T04:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T04:00:00Z",
            "until": "2026-10-06T05:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T05:00:00Z",
            "until": "2026-10-06T06:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T06:00:00Z",
            "until": "2026-10-06T07:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T07:00:00Z",
            "until": "2026-10-06T08:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T08:00:00Z",
            "until": "2026-10-06T09:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T09:00:00Z",
            "until": "2026-10-06T10:00:00Z",
            "request_count": 16,
        },
        {
            "from": "2026-10-06T10:00:00Z",
            "until": "2026-10-06T11:00:00Z",
            "request_count": 25,
        },
        {
            "from": "2026-10-06T11:00:00Z",
            "until": "2026-10-06T12:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T12:00:00Z",
            "until": "2026-10-06T13:00:00Z",
            "request_count": 16,
        },
        {
            "from": "2026-10-06T13:00:00Z",
            "until": "2026-10-06T14:00:00Z",
            "request_count": 64,
        },
        {
            "from": "2026-10-06T14:00:00Z",
            "until": "2026-10-06T15:00:00Z",
            "request_count": 9,
        },
        {
            "from": "2026-10-06T15:00:00Z",
            "until": "2026-10-06T16:00:00Z",
            "request_count": 11,
        },
        {
            "from": "2026-10-06T16:00:00Z",
            "until": "2026-10-06T17:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T17:00:00Z",
            "until": "2026-10-06T18:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T18:00:00Z",
            "until": "2026-10-06T19:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T19:00:00Z",
            "until": "2026-10-06T20:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T20:00:00Z",
            "until": "2026-10-06T21:00:00Z",
            "request_count": 0,
        },
        {
            "from": "2026-10-06T21:00:00Z",
            "until": "2026-10-06T22:00:00Z",
            "request_count": 55,
        },
        {
            "from": "2026-10-06T22:00:00Z",
            "until": "2026-10-06T23:00:00Z",
            "request_count": 24,
        },
        {
            "from": "2026-10-06T23:00:00Z",
            "until": "2026-10-07T00:00:00Z",
            "request_count": 34,
        },
        {
            "from": "2026-10-07T00:00:00Z",
            "until": "2026-10-07T01:00:00Z",
            "request_count": 36,
        },
        {
            "from": "2026-10-07T01:00:00Z",
            "until": "2026-10-07T02:00:00Z",
            "request_count": 7,
        },
        {
            "from": "2026-10-07T02:00:00Z",
            "until": "2026-10-07T03:00:00Z",
            "request_count": 23,
        },
        {
            "from": "2026-10-07T03:00:00Z",
            "until": "2026-10-07T03:17:54.970791219Z",
            "partial": True,
            "request_count": 7,
        },
    ],
}

# 7d variant: same shape, day granularity (server-set).
SAMPLE_USAGE_7D = {
    "range": "7d",
    "scope": "self",
    "granularity": "day",
    "from": "2026-09-30T00:00:00Z",
    "until": "2026-10-07T03:17:54.970791219Z",
    "totals": {"request_count": 1204},
    "buckets": [
        {
            "from": "2026-09-30T00:00:00Z",
            "until": "2026-10-01T00:00:00Z",
            "request_count": 100,
        },
        {
            "from": "2026-10-06T00:00:00Z",
            "until": "2026-10-07T00:00:00Z",
            "request_count": 1104,
        },
    ],
}

UNAUTH_BODY = {"error": "invalid credentials"}
FORBIDDEN_BODY = {"error": "account suspended"}
NOT_FOUND_BODY = {"error": 'path "/api/nope" not found'}


# ---------------------------------------------------------------------------
# Payload fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_balance_legacy() -> dict:
    """Verbatim legacy-account balance (session + weekly)."""
    return SAMPLE_BALANCE_LEGACY


@pytest.fixture
def sample_balance_credits() -> dict:
    """Verbatim credits-account balance (docs' oneOf example)."""
    return SAMPLE_BALANCE_CREDITS


@pytest.fixture
def sample_usage_24h() -> dict:
    """Verbatim usage 24h response."""
    return SAMPLE_USAGE_24H


@pytest.fixture
def sample_usage_7d() -> dict:
    """Verbatim-shaped usage 7d response."""
    return SAMPLE_USAGE_7D


# ---------------------------------------------------------------------------
# Real aiohttp test server (for test_api.py)
# ---------------------------------------------------------------------------


class UsageMockServer:
    """Configurable aiohttp test server serving /api/balance + /api/usage."""

    def __init__(self) -> None:
        self.status = 200
        self.json_payload: dict | None = None
        self.text_body: str | None = None
        self.content_type = "application/json"
        self.delay = 0.0
        self.retry_after: str | None = None
        self.requests: list[web.Request] = []
        self.url = ""

    async def handle(self, request: web.Request) -> web.Response:
        """Serve the configured response."""
        import asyncio

        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        headers = {}
        if self.retry_after is not None:
            headers["Retry-After"] = self.retry_after
        if self.text_body is not None:
            return web.Response(
                status=self.status,
                text=self.text_body,
                content_type=self.content_type,
                headers=headers,
            )
        if self.json_payload is not None:
            # aiohttp 3.14 removed Response(json=...); use json_response.
            return web.json_response(
                self.json_payload, status=self.status, headers=headers
            )
        return web.Response(status=self.status, headers=headers)


@pytest.fixture
async def usage_server(socket_enabled) -> UsageMockServer:
    """Start a local aiohttp server mocking GET /api/balance + /api/usage.

    Requires pytest-socket's ``socket_enabled`` fixture because the
    pytest-homeassistant-custom-component harness blocks sockets by
    default; a loopback test server is exactly what we need here.
    """
    stub = UsageMockServer()
    app = web.Application()
    app.router.add_get(BALANCE_PATH, stub.handle)
    app.router.add_get(USAGE_PATH, stub.handle)
    server = TestServer(app)
    await server.start_server()
    # Base URL only — the client appends the endpoint paths itself.
    stub.url = str(server.make_url("/"))
    yield stub
    await server.close()


# ---------------------------------------------------------------------------
# Coordinator helpers (stub client — no HTTP)
# ---------------------------------------------------------------------------


class StubUsageClient:
    """Drop-in replacement for OllamaClient with scripted behaviour.

    Scripts separate payloads/exceptions per endpoint so coordinator
    tests can exercise partial-failure ticks.
    """

    def __init__(self) -> None:
        self.balance_payload: dict | None = None
        self.usage_payloads: dict[str, dict] = {}
        self.balance_exc: Exception | None = None
        self.usage_exc: Exception | None = None
        self.calls = 0
        self.keys: list[str] = []
        self.requested_ranges: list[str] = []

    async def async_get_balance(self, api_key: str) -> dict[str, Any]:
        self.calls += 1
        self.keys.append(api_key)
        if self.balance_exc is not None:
            raise self.balance_exc
        assert self.balance_payload is not None
        return self.balance_payload

    async def async_get_usage(self, api_key: str, range: str) -> dict[str, Any]:
        self.calls += 1
        self.requested_ranges.append(range)
        if self.usage_exc is not None:
            raise self.usage_exc
        assert range in self.usage_payloads, f"no scripted payload for range={range}"
        return self.usage_payloads[range]


def make_fake_entry() -> Mock:
    """A config-entry stand-in accepted by DataUpdateCoordinator."""
    entry = Mock()
    entry.entry_id = "test_entry"
    entry.title = "Ollama Cloud"
    entry.data = {"api_key": "k", "scan_interval": 300}
    entry.options = {}
    entry.state = Mock()
    return entry


def make_coordinator(hass, client: StubUsageClient | None = None):
    """Build a coordinator with a stubbed API client."""
    from custom_components.ax_ollama_usage.coordinator import (
        OllamaUsageUpdateCoordinator,
    )

    coordinator = OllamaUsageUpdateCoordinator(hass, make_fake_entry())
    if client is not None:
        coordinator._client = client
    # Cancel the periodic refresh timer so tests do not leave a lingering
    # timer handle behind (the harness fails on lingering timers).
    if coordinator._unsub_refresh is not None:
        coordinator._unsub_refresh()
        coordinator._unsub_refresh = None
    return coordinator
