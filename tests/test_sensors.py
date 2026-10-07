"""Tests for the sensor platform (entity values, unique_ids, attributes)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.ax_ollama_usage.coordinator import (
    OllamaUsageCoordinatorData,
    OllamaUsageUpdateCoordinator,
    WindowData,
)
from custom_components.ax_ollama_usage.sensor import (
    OllamaAnchorDivergenceSensor,
    OllamaClockSkewSensor,
    OllamaIncludedAllowanceSensor,
    OllamaIncludedBalanceSensor,
    OllamaIncludedResetsAtSensor,
    OllamaPurchasedBalanceSensor,
    OllamaRemainingSensor,
    OllamaRequests7dSensor,
    OllamaRequests24hSensor,
    OllamaResetsAtSensor,
    OllamaUsageSensor,
)

from .conftest import make_coordinator


def _window(remaining: float, resets_at: datetime | None = None) -> WindowData:
    return WindowData(remaining_percent=remaining, resets_at=resets_at, raw_key="w")


def _seed(
    coordinator: OllamaUsageUpdateCoordinator,
    windows: dict[str, WindowData],
    **kwargs,
) -> None:
    coordinator.data = OllamaUsageCoordinatorData(
        windows=windows,
        server_time=datetime(2026, 10, 7, 3, 17, 54, tzinfo=UTC),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Per-window sensors (legacy branch)
# ---------------------------------------------------------------------------


async def test_usage_sensor_value_and_attributes(hass) -> None:
    """Usage = 100 - remaining_percent; attributes carry resets_at/window_key."""
    coordinator = make_coordinator(hass)
    _seed(
        coordinator,
        {
            "session": _window(
                98.77, resets_at=datetime(2026, 10, 7, 8, 0, 0, tzinfo=UTC)
            )
        },
    )
    entry = coordinator._entry
    sensor = OllamaUsageSensor(coordinator, entry, "session")
    # Value assertion (Amendment 6): the true float lives on the window
    # data — 100 - 98.77 == 1.23.
    assert coordinator.data.windows["session"].used_percent == pytest.approx(1.23)
    # The sensor reports the display-rounded value (precision 1 → 1.2).
    assert sensor.native_value == pytest.approx(1.2)
    assert sensor.suggested_display_precision == 1
    attrs = sensor.extra_state_attributes
    assert attrs["resets_at"] == "2026-10-07T08:00:00+00:00"
    assert attrs["window_key"] == "session"
    assert sensor.unique_id == "test_entry_session_usage"
    assert sensor.has_entity_name is True
    assert sensor.name == "Session Usage"


async def test_usage_sensor_unknown_window_label(hass) -> None:
    """Unknown window keys get a title-cased, underscore-free label."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"last_4_weeks": _window(90.0)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "last_4_weeks")
    assert sensor.name == "Last 4 Weeks Usage"


async def test_remaining_sensor(hass) -> None:
    """Remaining = the server's remaining_percent (67.54 in the fixture)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)})
    sensor = OllamaRemainingSensor(coordinator, coordinator._entry, "weekly")
    assert sensor.native_value == pytest.approx(67.5)  # rounded to 1 dp
    assert sensor.unique_id == "test_entry_weekly_remaining"
    assert sensor.name == "Weekly Remaining"


async def test_resets_at_sensor_passthrough(hass) -> None:
    """Resets At is the server's resets_at passthrough (authoritative)."""
    coordinator = make_coordinator(hass)
    server_reset = datetime(2026, 10, 7, 8, 0, 0, tzinfo=UTC)
    _seed(coordinator, {"session": _window(98.77, resets_at=server_reset)})
    sensor = OllamaResetsAtSensor(coordinator, coordinator._entry, "session")
    assert sensor.native_value == server_reset
    assert sensor.unique_id == "test_entry_session_resets_at"
    assert sensor.name == "Session Resets At"


async def test_resets_at_sensor_absent_is_unknown(hass) -> None:
    """A window without resets_at reports unknown (None)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"monthly": _window(50.0), "weird_window": _window(75.0)})
    for window in ("monthly", "weird_window"):
        sensor = OllamaResetsAtSensor(coordinator, coordinator._entry, window)
        assert sensor.native_value is None, window


async def test_vanished_window_reports_unavailable(hass) -> None:
    """A window missing from coordinator data yields None (unavailable)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(90.0)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "session")
    assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Entry-level sensors
# ---------------------------------------------------------------------------


async def test_requests_24h_sensor(hass) -> None:
    """Requests 24h = totals.request_count; attribute = partial bucket."""
    coordinator = make_coordinator(hass)
    _seed(
        coordinator,
        {"weekly": _window(67.54)},
        requests_24h=327,
        current_hour_requests=7,
    )
    sensor = OllamaRequests24hSensor(coordinator, coordinator._entry)
    assert sensor.native_value == 327
    assert sensor.extra_state_attributes == {"current_hour_requests": 7}
    assert sensor.unique_id == "test_entry_requests_24h"
    assert sensor.translation_key == "requests_24h"
    # Rolling-window sums can decrease → MEASUREMENT, not total_increasing.
    assert sensor.state_class == "measurement"


async def test_requests_7d_sensor(hass) -> None:
    """Requests 7d = 7d totals.request_count."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)}, requests_7d=1204)
    sensor = OllamaRequests7dSensor(coordinator, coordinator._entry)
    assert sensor.native_value == 1204
    assert sensor.unique_id == "test_entry_requests_7d"
    assert sensor.translation_key == "requests_7d"
    assert sensor.state_class == "measurement"


async def test_purchased_balance_sensor(hass) -> None:
    """Purchased Balance = purchased.balance_usd with USD + currency."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)}, purchased_balance_usd=0.0)
    sensor = OllamaPurchasedBalanceSensor(coordinator, coordinator._entry)
    assert sensor.native_value == 0.0
    assert sensor.unique_id == "test_entry_purchased_balance"
    assert sensor.translation_key == "purchased_balance"
    # ISO4217 unit — for MONETARY sensors the unit IS the currency signal
    # (this HA build has no separate currency entity attribute).
    assert sensor.native_unit_of_measurement == "USD"
    assert sensor.device_class == "monetary"


# ---------------------------------------------------------------------------
# Credits-branch sensors
# ---------------------------------------------------------------------------


async def test_credits_sensors_populate(hass) -> None:
    """Credits variant: Included Balance/Allowance/Resets At populate."""
    coordinator = make_coordinator(hass)
    _seed(
        coordinator,
        {},  # credits branch → windows empty
        included_balance_usd=72.5,
        allowance_usd=100.0,
        included_period_until=datetime(2026, 10, 15, 9, 30, 0, tzinfo=UTC),
    )
    entry = coordinator._entry

    balance = OllamaIncludedBalanceSensor(coordinator, entry)
    assert balance.native_value == 72.5
    assert balance.unique_id == "test_entry_included_balance"
    assert balance.native_unit_of_measurement == "USD"
    assert balance.device_class == "monetary"

    allowance = OllamaIncludedAllowanceSensor(coordinator, entry)
    assert allowance.native_value == 100.0
    assert allowance.unique_id == "test_entry_included_allowance"
    assert allowance.native_unit_of_measurement == "USD"
    assert allowance.device_class == "monetary"

    resets = OllamaIncludedResetsAtSensor(coordinator, entry)
    assert resets.native_value == datetime(2026, 10, 15, 9, 30, 0, tzinfo=UTC)
    assert resets.unique_id == "test_entry_included_resets_at"


async def test_credits_sensors_unknown_on_legacy(hass) -> None:
    """On the legacy branch the credits sensors report unknown (None)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)})
    entry = coordinator._entry
    assert OllamaIncludedBalanceSensor(coordinator, entry).native_value is None
    assert OllamaIncludedAllowanceSensor(coordinator, entry).native_value is None
    assert OllamaIncludedResetsAtSensor(coordinator, entry).native_value is None


# ---------------------------------------------------------------------------
# Diagnostics + device
# ---------------------------------------------------------------------------


async def test_diagnostics_sensors(hass) -> None:
    """Clock Skew and Anchor Divergence sensors (translation-keyed)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)})
    entry = coordinator._entry

    skew = OllamaClockSkewSensor(coordinator, entry)
    assert skew.native_value is not None
    assert skew.unique_id == "test_entry_clock_skew"
    assert skew.translation_key == "clock_skew"
    assert skew.entity_category is not None
    assert skew.entity_category.value == "diagnostic"

    div = OllamaAnchorDivergenceSensor(coordinator, entry)
    assert div.native_value is False
    assert div.unique_id == "test_entry_anchor_divergence"
    assert div.translation_key == "anchor_divergence"
    assert div.entity_category is not None
    assert div.entity_category.value == "diagnostic"


async def test_device_info_shared(hass) -> None:
    """All sensors share one DeviceInfo (manufacturer Axildor)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(67.54)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "weekly")
    info = sensor.device_info
    assert info["manufacturer"] == "Axildor"
    assert info["model"] == "AX Ollama Usage Tracker"
    assert ("ax_ollama_usage", "test_entry") in info["identifiers"]
