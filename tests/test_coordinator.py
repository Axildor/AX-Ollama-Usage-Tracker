"""Tests for the coordinator: parsing, backoff, auth, network errors.

Uses a stubbed API client (no HTTP) — see conftest.py for the rationale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.ollama_cloud_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaRateLimitError,
)
from custom_components.ollama_cloud_usage.coordinator import (
    OllamaUsageCoordinatorData,
    _parse_iso_utc,
    _parse_models,
)

from .conftest import (
    StubUsageClient,
    make_coordinator,
)


def _stub(payload: dict | None = None, exc: Exception | None = None) -> StubUsageClient:
    stub = StubUsageClient()
    stub.payload = payload
    stub.exc = exc
    return stub


async def test_parse_legacy_sample(hass, sample_legacy: dict) -> None:
    """200 happy path: dynamic windows, string cost, server_time captured."""
    coordinator = make_coordinator(hass, _stub(sample_legacy))
    data = await coordinator._async_update_data()
    assert isinstance(data, OllamaUsageCoordinatorData)
    assert set(data.windows) == {"session", "weekly"}
    assert data.windows["session"].usage_fraction == 0.005
    assert data.windows["session"].models == {"glm-5.3-flash": 16}
    assert data.windows["weekly"].raw_key == "weekly"
    assert data.activity_cost == 0.0  # parsed from the string "0.00000"
    assert data.server_time is not None
    assert data.server_time == datetime(2026, 9, 14, 0, 26, 9, 519800, tzinfo=UTC)


async def test_parse_daily_weekly_variant(hass, sample_daily_weekly: dict) -> None:
    """daily + weekly variant parses with dynamic iteration."""
    coordinator = make_coordinator(hass, _stub(sample_daily_weekly))
    data = await coordinator._async_update_data()
    assert set(data.windows) == {"daily", "weekly"}
    assert data.windows["daily"].usage_fraction == 0.25
    assert data.activity_cost == 1.25


async def test_parse_monthly_variant(hass, sample_monthly: dict) -> None:
    """monthly-only variant tolerated; resets sensor will be unknown."""
    coordinator = make_coordinator(hass, _stub(sample_monthly))
    data = await coordinator._async_update_data()
    assert set(data.windows) == {"monthly"}
    assert data.windows["monthly"].usage_fraction == 0.5


async def test_parse_unknown_window_variant(hass, sample_weird_window: dict) -> None:
    """Unknown window keys are tolerated and exposed."""
    coordinator = make_coordinator(hass, _stub(sample_weird_window))
    data = await coordinator._async_update_data()
    assert set(data.windows) == {"weird_window"}
    assert data.windows["weird_window"].usage_fraction == 0.75


async def test_401_raises_auth_failed(hass) -> None:
    """401 → ConfigEntryAuthFailed (triggers the reauth flow)."""
    coordinator = make_coordinator(
        hass, _stub(exc=OllamaAuthError("invalid credentials"))
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_429_applies_backoff(hass) -> None:
    """429 → UpdateFailed and the update interval doubles."""
    coordinator = make_coordinator(
        hass, _stub(exc=OllamaRateLimitError("rate limited"))
    )
    base = coordinator.update_interval
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval > base
    # Second consecutive failure doubles again
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval > base * 2


async def test_backoff_capped_at_one_hour(hass) -> None:
    """Backoff never exceeds 1 hour."""
    coordinator = make_coordinator(hass)
    for _ in range(10):
        coordinator._apply_backoff()
    assert coordinator.update_interval <= timedelta(seconds=3600)


async def test_timeout_raises_update_failed(hass) -> None:
    """Timeout → UpdateFailed; sensors go unavailable; nothing escapes."""
    coordinator = make_coordinator(hass, _stub(exc=OllamaApiError("timeout")))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_network_error_raises_update_failed(hass) -> None:
    """Network error → UpdateFailed."""
    import aiohttp

    coordinator = make_coordinator(
        hass, _stub(exc=aiohttp.ClientConnectionError("boom"))
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_successful_poll_resets_backoff(hass, sample_legacy: dict) -> None:
    """A successful poll restores the base interval."""
    coordinator = make_coordinator(hass, _stub(sample_legacy))
    base = coordinator.update_interval
    coordinator._apply_backoff()
    await coordinator._async_update_data()
    assert coordinator.update_interval == base


async def test_window_disappears_from_data(hass, sample_legacy: dict) -> None:
    """A window key vanishing from limits drops it from coordinator data.

    The sensor platform keeps registry entries and reports unavailable;
    here we verify the coordinator side: the vanished key is absent from
    the new snapshot.
    """
    stub = StubUsageClient()
    stub.payload = sample_legacy
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert "session" in data.windows
    # Next poll: session disappears
    stub.payload = {
        "activity": sample_legacy["activity"],
        "limits": {"weekly": sample_legacy["limits"]["weekly"]},
    }
    data = await coordinator._async_update_data()
    assert "session" not in data.windows
    assert "weekly" in data.windows


def test_parse_iso_utc_nanoseconds() -> None:
    """Nanosecond-precision ISO timestamps parse (truncated to µs)."""
    parsed = _parse_iso_utc("2026-09-14T00:26:09.519800895Z")
    assert parsed is not None
    assert parsed.tzinfo is UTC
    assert parsed.microsecond == 519800


def test_parse_iso_utc_invalid() -> None:
    """Garbage input returns None, never raises."""
    assert _parse_iso_utc("not-a-date") is None
    assert _parse_iso_utc("") is None


def test_parse_models_tolerates_garbage() -> None:
    """Non-list models and malformed entries are skipped."""
    assert _parse_models(None) == {}
    assert _parse_models("oops") == {}
    assert _parse_models([{"name": "a", "request_count": 3}, "junk"]) == {"a": 3}
