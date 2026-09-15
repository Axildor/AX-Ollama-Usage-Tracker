"""Tests for the sensor platform (entity values, unique_ids, attributes)."""

from __future__ import annotations

from datetime import UTC, datetime

from custom_components.ax_ollama_usage.coordinator import (
    OllamaUsageCoordinatorData,
    OllamaUsageUpdateCoordinator,
    WindowData,
)
from custom_components.ax_ollama_usage.sensor import (
    OllamaActivityCostSensor,
    OllamaAnchorDivergenceSensor,
    OllamaClockSkewSensor,
    OllamaModelRequestsSensor,
    OllamaRemainingSensor,
    OllamaResetsAtSensor,
    OllamaUsageSensor,
)

from .conftest import make_coordinator


def _window(usage: float, models: dict[str, int] | None = None) -> WindowData:
    return WindowData(usage_fraction=usage, models=models or {}, raw_key="w")


def _seed(
    coordinator: OllamaUsageUpdateCoordinator, windows: dict[str, WindowData]
) -> None:
    coordinator.data = OllamaUsageCoordinatorData(
        windows=windows,
        activity_cost=0.0,
        server_time=datetime(2026, 9, 14, 0, 26, 9, tzinfo=UTC),
    )


async def test_usage_sensor_value_and_attributes(hass) -> None:
    """Usage sensor reports % and carries models/predicted_reset/window_key."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"session": _window(0.005, {"glm-5.3-flash": 16})})
    entry = coordinator._entry
    sensor = OllamaUsageSensor(coordinator, entry, "session")
    assert sensor.native_value == 0.5  # 0.005 * 100, rounded 1
    attrs = sensor.extra_state_attributes
    assert attrs["models"] == {"glm-5.3-flash": 16}
    assert attrs["window_key"] == "session"
    assert attrs["predicted_reset_utc"] is not None
    assert sensor.unique_id == "test_entry_session_usage"
    assert sensor.has_entity_name is True
    assert sensor.name == "Session Usage"


async def test_usage_sensor_unknown_window_label(hass) -> None:
    """Unknown window keys get a title-cased, underscore-free label."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"last_4_weeks": _window(0.1)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "last_4_weeks")
    assert sensor.name == "Last 4 Weeks Usage"


async def test_remaining_sensor(hass) -> None:
    """Remaining = 100 - usage."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"session": _window(0.005)})
    sensor = OllamaRemainingSensor(coordinator, coordinator._entry, "session")
    assert sensor.native_value == 99.5
    assert sensor.unique_id == "test_entry_session_remaining"
    assert sensor.name == "Session Remaining"


async def test_resets_at_sensor_session(hass) -> None:
    """Session resets sensor returns a computed UTC datetime."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"session": _window(0.005)})
    sensor = OllamaResetsAtSensor(coordinator, coordinator._entry, "session")
    value = sensor.native_value
    assert value is not None
    assert value.tzinfo is UTC
    assert int(value.timestamp()) % 18000 == 0
    assert sensor.unique_id == "test_entry_session_resets_at"
    assert sensor.name == "Session Resets At"


async def test_resets_at_sensor_unmodeled_is_unknown(hass) -> None:
    """Unmodeled windows (monthly, weird) report unknown (None)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"monthly": _window(0.5), "weird_window": _window(0.75)})
    for window in ("monthly", "weird_window"):
        sensor = OllamaResetsAtSensor(coordinator, coordinator._entry, window)
        assert sensor.native_value is None, window


async def test_vanished_window_reports_unavailable(hass) -> None:
    """A window missing from coordinator data yields None (unavailable)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(0.1)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "session")
    assert sensor.native_value is None


async def test_model_requests_sensor(hass) -> None:
    """Per-model request sensor reports the count and a legible name."""
    coordinator = make_coordinator(hass)
    _seed(
        coordinator,
        {"session": _window(0.235, {"glm-5.3-flash": 231, "glm-5.3": 75})},
    )
    entry = coordinator._entry
    sensor = OllamaModelRequestsSensor(coordinator, entry, "session", "glm-5.3-flash")
    assert sensor.native_value == 231
    assert sensor.unique_id == "test_entry_session_glm-5.3-flash_requests"
    assert sensor.name == "Session glm-5.3-flash Requests"
    assert sensor.state_class == "total_increasing"

    # Model missing from the window → None (unavailable)
    other = OllamaModelRequestsSensor(coordinator, entry, "weekly", "glm-5.3")
    assert other.native_value is None


async def test_diagnostics_sensors(hass) -> None:
    """Activity Cost, Clock Skew, and Anchor Divergence sensors."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(0.1)})
    entry = coordinator._entry

    cost = OllamaActivityCostSensor(coordinator, entry)
    assert cost.native_value == 0.0
    assert cost.unique_id == "test_entry_activity_cost"
    assert cost.translation_key == "activity_cost"
    assert cost.entity_category is None

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
    """All sensors share one DeviceInfo (manufacturer Ollama)."""
    coordinator = make_coordinator(hass)
    _seed(coordinator, {"weekly": _window(0.1)})
    sensor = OllamaUsageSensor(coordinator, coordinator._entry, "weekly")
    info = sensor.device_info
    assert info["manufacturer"] == "Axildor"
    assert info["model"] == "AX Ollama Usage Tracker"
    assert ("ax_ollama_usage", "test_entry") in info["identifiers"]
