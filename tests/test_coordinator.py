"""Tests for the coordinator: parsing, backoff, auth, 403, network errors.

Uses a stubbed API client (no HTTP) — see conftest.py for the rationale.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.ax_ollama_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaForbiddenError,
    OllamaRateLimitError,
)
from custom_components.ax_ollama_usage.coordinator import (
    OllamaUsageCoordinatorData,
    _parse_iso_utc,
    _parse_usd,
)

from .conftest import (
    SAMPLE_BALANCE_CREDITS,
    SAMPLE_BALANCE_LEGACY,
    SAMPLE_USAGE_7D,
    SAMPLE_USAGE_24H,
    StubUsageClient,
    make_coordinator,
)


def _stub(
    balance: dict | None = None,
    usage_24h: dict | None = None,
    usage_7d: dict | None = None,
    balance_exc: Exception | None = None,
    usage_exc: Exception | None = None,
) -> StubUsageClient:
    stub = StubUsageClient()
    stub.balance_payload = balance
    stub.usage_payloads = {"24h": usage_24h or {}, "7d": usage_7d or {}}
    stub.balance_exc = balance_exc
    stub.usage_exc = usage_exc
    return stub


def _legacy_stub() -> StubUsageClient:
    """Canonical legacy tick: verbatim balance + both usage payloads."""
    return _stub(
        balance=SAMPLE_BALANCE_LEGACY,
        usage_24h=SAMPLE_USAGE_24H,
        usage_7d=SAMPLE_USAGE_7D,
    )


# ---------------------------------------------------------------------------
# Balance parsing — legacy branch
# ---------------------------------------------------------------------------


async def test_parse_legacy_balance(hass) -> None:
    """Legacy balance: dynamic windows, remaining_percent, resets_at passthrough."""
    coordinator = make_coordinator(hass, _legacy_stub())
    data = await coordinator._async_update_data()
    assert isinstance(data, OllamaUsageCoordinatorData)
    assert set(data.windows) == {"session", "weekly"}
    assert data.windows["session"].remaining_percent == 98.77
    assert data.windows["session"].used_percent == pytest.approx(1.23)
    assert data.windows["weekly"].remaining_percent == 67.54
    assert data.windows["weekly"].raw_key == "weekly"
    assert data.windows["session"].resets_at == datetime(
        2026, 10, 7, 8, 0, 0, tzinfo=UTC
    )
    assert data.windows["weekly"].resets_at == datetime(
        2026, 10, 12, 0, 0, 0, tzinfo=UTC
    )
    assert data.purchased_balance_usd == 0


async def test_parse_purchased_balance_as_string(hass) -> None:
    """purchased.balance_usd as a JSON string parses tolerantly."""
    stub = _stub(
        balance={
            "included": SAMPLE_BALANCE_LEGACY["included"],
            "purchased": {"balance_usd": "12.50"},
        },
        usage_24h=SAMPLE_USAGE_24H,
        usage_7d=SAMPLE_USAGE_7D,
    )
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert data.purchased_balance_usd == 12.5


async def test_parse_unknown_balance_shape(hass) -> None:
    """An unrecognized 'included' shape parses no windows but never crashes."""
    stub = _stub(
        balance={"included": {"something_new": {}}, "purchased": {}},
        usage_24h=SAMPLE_USAGE_24H,
        usage_7d=SAMPLE_USAGE_7D,
    )
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert data.windows == {}
    assert data.purchased_balance_usd is None


# ---------------------------------------------------------------------------
# Balance parsing — credits branch (oneOf variant)
# ---------------------------------------------------------------------------


async def test_parse_credits_balance(hass) -> None:
    """Credits variant: credits fields populate; windows is an empty dict."""
    stub = _stub(
        balance=SAMPLE_BALANCE_CREDITS,
        usage_24h=SAMPLE_USAGE_24H,
        usage_7d=SAMPLE_USAGE_7D,
    )
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert data.windows == {}  # empty dict, not absent
    assert data.included_balance_usd == 72.5
    assert data.allowance_usd == 100
    assert data.included_period_until == datetime(2026, 10, 15, 9, 30, 0, tzinfo=UTC)
    assert data.purchased_balance_usd == 25


async def test_credits_balance_tolerates_string_usd(hass) -> None:
    """Credits balance_usd/allowance_usd as strings parse tolerantly."""
    credits = {
        "included": {
            "balance_usd": "72.5",
            "allowance_usd": "100",
            "period": SAMPLE_BALANCE_CREDITS["included"]["period"],
        },
        "purchased": {"balance_usd": "25"},
    }
    stub = _stub(balance=credits, usage_24h=SAMPLE_USAGE_24H, usage_7d=SAMPLE_USAGE_7D)
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert data.included_balance_usd == 72.5
    assert data.allowance_usd == 100
    assert data.purchased_balance_usd == 25


async def test_legacy_to_credits_flip_no_crash(hass) -> None:
    """A legacy→credits schema flip (like Oct 6) parses without crashing."""
    stub = _legacy_stub()
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert set(data.windows) == {"session", "weekly"}
    # Next tick: the account flips to the credits variant.
    stub.balance_payload = SAMPLE_BALANCE_CREDITS
    data = await coordinator._async_update_data()
    assert data.windows == {}
    assert data.included_balance_usd == 72.5


# ---------------------------------------------------------------------------
# Usage parsing
# ---------------------------------------------------------------------------


async def test_parse_usage_24h(hass) -> None:
    """24h usage: totals.request_count, partial-bucket current hour, until."""
    coordinator = make_coordinator(hass, _legacy_stub())
    data = await coordinator._async_update_data()
    assert data.requests_24h == 327
    assert data.current_hour_requests == 7  # final partial bucket
    assert data.usage_until == datetime(2026, 10, 7, 3, 17, 54, 970791, tzinfo=UTC)
    assert data.server_time == data.usage_until


async def test_parse_usage_7d(hass) -> None:
    """7d usage: totals.request_count parsed."""
    coordinator = make_coordinator(hass, _legacy_stub())
    data = await coordinator._async_update_data()
    assert data.requests_7d == 1204


async def test_usage_without_partial_bucket(hass) -> None:
    """A payload with no partial bucket leaves current_hour_requests None."""
    payload = {
        "range": "24h",
        "granularity": "hour",
        "from": "2026-10-06T03:00:00Z",
        "until": "2026-10-07T03:00:00Z",
        "totals": {"request_count": 320},
        "buckets": [
            {
                "from": "2026-10-06T03:00:00Z",
                "until": "2026-10-06T04:00:00Z",
                "request_count": 5,
            }
        ],
    }
    stub = _stub(
        balance=SAMPLE_BALANCE_LEGACY, usage_24h=payload, usage_7d=SAMPLE_USAGE_7D
    )
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert data.requests_24h == 320
    assert data.current_hour_requests is None


def test_parse_usd_tolerant() -> None:
    """_parse_usd handles str, int, float, bool, and garbage."""
    assert _parse_usd(0) == 0.0
    assert _parse_usd(12.5) == 12.5
    assert _parse_usd("12.5") == 12.5
    assert _parse_usd(True) is None  # bool is not a USD figure
    assert _parse_usd("garbage") is None
    assert _parse_usd(None) is None
    assert _parse_usd({"oops": 1}) is None


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_401_raises_auth_failed(hass) -> None:
    """401 → ConfigEntryAuthFailed (triggers the reauth flow)."""
    coordinator = make_coordinator(
        hass, _stub(balance_exc=OllamaAuthError("invalid credentials"))
    )
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_403_is_update_failed_not_auth_failed(hass) -> None:
    """403 → UpdateFailed with the suspension message; NOT auth-failed."""
    coordinator = make_coordinator(
        hass, _stub(balance_exc=OllamaForbiddenError("account suspended"))
    )
    with pytest.raises(UpdateFailed) as excinfo:
        await coordinator._async_update_data()
    assert "suspended" in str(excinfo.value).lower()


async def test_403_on_usage_is_update_failed(hass) -> None:
    """403 on the usage GET also maps to UpdateFailed, not auth-failed."""
    coordinator = make_coordinator(
        hass,
        _stub(
            balance=SAMPLE_BALANCE_LEGACY,
            usage_exc=OllamaForbiddenError("team scope denied"),
        ),
    )
    with pytest.raises(UpdateFailed) as excinfo:
        await coordinator._async_update_data()
    assert "suspended" in str(excinfo.value).lower()


async def test_429_with_retry_after_honored_exactly(hass) -> None:
    """429 + Retry-After: 60 → next interval exactly 60 s (never multiplied)."""
    coordinator = make_coordinator(
        hass,
        _stub(
            balance_exc=OllamaRateLimitError("rate limited", retry_after=60),
        ),
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=60)


async def test_429_retry_after_capped(hass) -> None:
    """A Retry-After above the cap is clamped to BACKOFF_MAX (1 hour)."""
    coordinator = make_coordinator(
        hass,
        _stub(
            balance_exc=OllamaRateLimitError("rate limited", retry_after=99999),
        ),
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=3600)


async def test_429_without_retry_after_exponential(hass) -> None:
    """429 without Retry-After → the existing exponential path."""
    coordinator = make_coordinator(
        hass, _stub(balance_exc=OllamaRateLimitError("rate limited"))
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
    coordinator = make_coordinator(hass, _stub(balance_exc=OllamaApiError("timeout")))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_network_error_raises_update_failed(hass) -> None:
    """Network error → UpdateFailed."""
    import aiohttp

    coordinator = make_coordinator(
        hass, _stub(balance_exc=aiohttp.ClientConnectionError("boom"))
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_usage_fails_after_balance_succeeds(hass) -> None:
    """A mid-tick failure fails the tick (UpdateFailed), never partial data."""
    coordinator = make_coordinator(
        hass,
        _stub(
            balance=SAMPLE_BALANCE_LEGACY,
            usage_exc=OllamaApiError("HTTP 500 from usage"),
        ),
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_successful_poll_resets_backoff(hass) -> None:
    """A successful poll restores the base interval."""
    coordinator = make_coordinator(hass, _legacy_stub())
    base = coordinator.update_interval
    coordinator._apply_backoff()
    await coordinator._async_update_data()
    assert coordinator.update_interval == base


async def test_usage_ranges_requested(hass) -> None:
    """Each tick requests exactly range=24h and range=7d."""
    stub = _legacy_stub()
    coordinator = make_coordinator(hass, stub)
    await coordinator._async_update_data()
    assert sorted(stub.requested_ranges) == ["24h", "7d"]


async def test_window_disappears_from_data(hass) -> None:
    """A window key vanishing from included drops it from coordinator data.

    The sensor platform keeps registry entries and reports unavailable;
    here we verify the coordinator side: the vanished key is absent from
    the new snapshot.
    """
    stub = _legacy_stub()
    coordinator = make_coordinator(hass, stub)
    data = await coordinator._async_update_data()
    assert "session" in data.windows
    # Next poll: session disappears
    stub.balance_payload = {
        "included": {"weekly": SAMPLE_BALANCE_LEGACY["included"]["weekly"]},
        "purchased": {"balance_usd": 0},
    }
    data = await coordinator._async_update_data()
    assert "session" not in data.windows
    assert "weekly" in data.windows


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


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
