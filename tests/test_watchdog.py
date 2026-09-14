"""Tests for the divergence watchdog in the coordinator."""

from __future__ import annotations

from datetime import datetime

from custom_components.ollama_cloud_usage.coordinator import (
    OllamaUsageCoordinatorData,
    OllamaUsageUpdateCoordinator,
    WindowData,
)

from .conftest import make_coordinator


def _window(window: str, usage: float) -> WindowData:
    return WindowData(usage_fraction=usage, models={}, raw_key=window)


def _feed(
    coordinator: OllamaUsageUpdateCoordinator,
    windows: dict[str, WindowData],
    now: datetime,
) -> None:
    """Drive the watchdog directly with a prepared data snapshot."""
    coordinator.data = OllamaUsageCoordinatorData(
        windows=windows,
        anchor_divergence=coordinator.data.anchor_divergence
        if coordinator.data
        else False,
        reset_events=coordinator.data.reset_events if coordinator.data else {},
    )
    coordinator._check_divergence(windows, now)


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


async def test_drop_registers_reset_event(hass) -> None:
    """A large drop (new < old * 0.5) records a reset event."""
    coordinator = make_coordinator(hass)
    now = _utc("2026-09-14T12:00:00Z")
    _feed(coordinator, {"weekly": _window("weekly", 0.8)}, now)
    later = _utc("2026-09-14T12:05:00Z")
    _feed(coordinator, {"weekly": _window("weekly", 0.1)}, later)
    assert coordinator.data.reset_events.get("weekly")
    assert len(coordinator.data.reset_events["weekly"]) == 1


async def test_deviation_beyond_30min_sets_flag(hass) -> None:
    """Observed reset deviating > 30 min from the model sets the flag."""
    coordinator = make_coordinator(hass)
    # Seed previous usage so a drop occurs at a time far from the model's
    # predicted Monday 00:00 UTC reset (e.g. Wednesday 12:00 UTC).
    _feed(coordinator, {"weekly": _window("weekly", 0.8)}, _utc("2026-09-16T11:00:00Z"))
    _feed(coordinator, {"weekly": _window("weekly", 0.1)}, _utc("2026-09-16T12:00:00Z"))
    assert coordinator.data.anchor_divergence is True
    assert coordinator.data.reset_events.get("weekly")


async def test_no_drop_at_boundary_does_not_flag(hass) -> None:
    """A predicted reset passing with no drop is normal — no flag."""
    coordinator = make_coordinator(hass)
    # Monday 2026-09-14 00:00 UTC is a predicted weekly boundary; usage
    # stays flat (zero) across it.
    _feed(coordinator, {"weekly": _window("weekly", 0.0)}, _utc("2026-09-13T23:00:00Z"))
    _feed(coordinator, {"weekly": _window("weekly", 0.0)}, _utc("2026-09-14T01:00:00Z"))
    assert coordinator.data.anchor_divergence is False
    assert not coordinator.data.reset_events.get("weekly")


async def test_small_drop_does_not_register(hass) -> None:
    """A drop that is not large (new >= old * 0.5) is not a reset event."""
    coordinator = make_coordinator(hass)
    _feed(coordinator, {"weekly": _window("weekly", 0.8)}, _utc("2026-09-14T12:00:00Z"))
    _feed(coordinator, {"weekly": _window("weekly", 0.5)}, _utc("2026-09-14T12:05:00Z"))
    assert not coordinator.data.reset_events.get("weekly")
    assert coordinator.data.anchor_divergence is False


async def test_unmodeled_window_records_event_without_flag(hass) -> None:
    """A drop in an unmodeled window records the event but cannot flag."""
    coordinator = make_coordinator(hass)
    _feed(
        coordinator, {"monthly": _window("monthly", 0.9)}, _utc("2026-09-14T12:00:00Z")
    )
    _feed(
        coordinator, {"monthly": _window("monthly", 0.0)}, _utc("2026-09-14T12:05:00Z")
    )
    assert coordinator.data.reset_events.get("monthly")
    # No model to compare → divergence flag untouched
    assert coordinator.data.anchor_divergence is False
