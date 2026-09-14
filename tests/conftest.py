"""Shared fixtures for the Ollama Cloud Usage test suite.

HTTP mocking strategy: ``aioresponses`` 0.7.9 and ``respx`` 0.23 are both
incompatible with the aiohttp 3.14 pin in HA 2026.x (``ClientResponse``
now requires a ``stream_writer`` kwarg).  Instead we use:

- a real ``aiohttp`` test server (``aiohttp.test_utils.TestServer``) for
  the HTTP-client tests in ``test_api.py`` — this exercises the genuine
  aiohttp request/response path;
- a stub client injected into the coordinator for coordinator/watchdog
  tests, which exercise coordinator logic rather than HTTP.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

USAGE_PATH = "/api/usage"

# Verbatim legacy-account sample (verified live 2026-09-14) — primary fixture.
SAMPLE_LEGACY = {
    "activity": {
        "cost": "0.00000",
        "period": {
            "type": "last_4_weeks",
            "starting_at": "2026-08-24T00:00:00Z",
            "ending_at": "2026-09-14T00:26:09.519800895Z",
        },
        "models": [],
    },
    "limits": {
        "session": {
            "usage": 0.005,
            "models": [{"name": "glm-5.3-flash", "request_count": 16}],
        },
        "weekly": {
            "usage": 0.001,
            "models": [{"name": "glm-5.3-flash", "request_count": 16}],
        },
    },
}

# Newer-account variant: daily + weekly.
SAMPLE_DAILY_WEEKLY = {
    "activity": {
        "cost": "1.25000",
        "period": {
            "type": "last_4_weeks",
            "starting_at": "2026-08-24T00:00:00Z",
            "ending_at": "2026-09-14T00:26:09.519800895Z",
        },
        "models": [],
    },
    "limits": {
        "daily": {"usage": 0.25, "models": [{"name": "qwen3", "request_count": 4}]},
        "weekly": {"usage": 0.10, "models": [{"name": "qwen3", "request_count": 9}]},
    },
}

# Migrated-account variant: monthly only.
SAMPLE_MONTHLY = {
    "activity": {
        "cost": "12.50000",
        "period": {
            "type": "last_4_weeks",
            "starting_at": "2026-08-24T00:00:00Z",
            "ending_at": "2026-09-14T00:26:09.519800895Z",
        },
        "models": [],
    },
    "limits": {
        "monthly": {"usage": 0.5, "models": [{"name": "glm-5.3", "request_count": 40}]},
    },
}

# Unknown-window variant: tolerated and exposed as sensors.
SAMPLE_WEIRD_WINDOW = {
    "activity": {
        "cost": "0.00000",
        "period": {
            "type": "last_4_weeks",
            "starting_at": "2026-08-24T00:00:00Z",
            "ending_at": "2026-09-14T00:26:09.519800895Z",
        },
        "models": [],
    },
    "limits": {
        "weird_window": {"usage": 0.75, "models": []},
    },
}

UNAUTH_BODY = {"error": "invalid credentials"}
NOT_FOUND_BODY = {"error": 'path "/api/nope" not found'}


# ---------------------------------------------------------------------------
# Payload fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_legacy() -> dict:
    """Verbatim legacy sample (session + weekly)."""
    return SAMPLE_LEGACY


@pytest.fixture
def sample_daily_weekly() -> dict:
    """daily + weekly variant."""
    return SAMPLE_DAILY_WEEKLY


@pytest.fixture
def sample_monthly() -> dict:
    """monthly-only variant."""
    return SAMPLE_MONTHLY


@pytest.fixture
def sample_weird_window() -> dict:
    """Unknown-window variant."""
    return SAMPLE_WEIRD_WINDOW


# ---------------------------------------------------------------------------
# Real aiohttp test server (for test_api.py)
# ---------------------------------------------------------------------------


class UsageMockServer:
    """Configurable aiohttp test server serving /api/usage."""

    def __init__(self) -> None:
        self.status = 200
        self.json_payload: dict | None = None
        self.text_body: str | None = None
        self.content_type = "application/json"
        self.delay = 0.0
        self.requests: list[web.Request] = []
        self.url = ""

    async def handle(self, request: web.Request) -> web.Response:
        """Serve the configured response."""
        import asyncio

        self.requests.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.text_body is not None:
            return web.Response(
                status=self.status, text=self.text_body, content_type=self.content_type
            )
        if self.json_payload is not None:
            # aiohttp 3.14 removed Response(json=...); use json_response.
            return web.json_response(self.json_payload, status=self.status)
        return web.Response(status=self.status)


@pytest.fixture
async def usage_server(socket_enabled) -> UsageMockServer:
    """Start a local aiohttp server mocking GET /api/usage.

    Requires pytest-socket's ``socket_enabled`` fixture because the
    pytest-homeassistant-custom-component harness blocks sockets by
    default; a loopback test server is exactly what we need here.
    """
    stub = UsageMockServer()
    app = web.Application()
    app.router.add_get(USAGE_PATH, stub.handle)
    server = TestServer(app)
    await server.start_server()
    # Base URL only — the client appends USAGE_ENDPOINT itself.
    stub.url = str(server.make_url("/"))
    yield stub
    await server.close()


# ---------------------------------------------------------------------------
# Coordinator helpers (stub client — no HTTP)
# ---------------------------------------------------------------------------


class StubUsageClient:
    """Drop-in replacement for OllamaClient with scripted behaviour."""

    def __init__(self) -> None:
        self.payload: dict | None = None
        self.exc: Exception | None = None
        self.calls = 0
        self.keys: list[str] = []

    async def async_get_usage(self, api_key: str) -> dict[str, Any]:
        self.calls += 1
        self.keys.append(api_key)
        if self.exc is not None:
            raise self.exc
        assert self.payload is not None
        return self.payload

    async def close(self) -> None:
        pass


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
    from custom_components.ollama_cloud_usage.coordinator import (
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
