"""Tests for the divergence watchdog in the coordinator (v0.3 semantics).

The watchdog is opt-in (``enable_watchdog`` option, default off).  A
reset is a jump UP of ``remaining_percent`` by more than
``RESET_JUMP_THRESHOLD`` (25 points) between consecutive polls.
"""

from __future__ import annotations

from datetime import datetime

from custom_components.ax_ollama_usage.coordinator import (
    OllamaUsageCoordinatorData,
    OllamaUsageUpdateCoordinator,
    WindowData,
)

from .conftest import make_coordinator


def _window(window: str, remaining: float) -> WindowData:
    return WindowData(remaining_percent=remaining, resets_at=None, raw_key=window)


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


def _enable_watchdog(coordinator: OllamaUsageUpdateCoordinator) -> None:
    """Flip the opt-in watchdog on (mirrors the options flow)."""
    coordinator._watchdog_enabled = True


async def test_default_off_records_no_events(hass) -> None:
    """Default (watchdog off): a large jump records no events, no flag."""
    coordinator = make_coordinator(hass)
    assert coordinator._watchdog_enabled is False
    _feed(coordinator, {"weekly": _window("weekly", 5.0)}, _utc("2026-10-12T00:05:00Z"))
    _feed(
        coordinator, {"weekly": _window("weekly", 95.0)}, _utc("2026-10-12T00:10:00Z")
    )
    assert not coordinator.data.reset_events.get("weekly")
    assert coordinator.data.anchor_divergence is False


async def test_jump_up_registers_reset_event(hass) -> None:
    """A jump up > 25 points records a reset event (watchdog on)."""
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    now = _utc("2026-10-12T00:05:00Z")
    _feed(coordinator, {"weekly": _window("weekly", 5.0)}, now)
    later = _utc("2026-10-12T00:10:00Z")
    _feed(coordinator, {"weekly": _window("weekly", 95.0)}, later)
    assert coordinator.data.reset_events.get("weekly")
    assert len(coordinator.data.reset_events["weekly"]) == 1


async def test_deviation_beyond_30min_sets_flag(hass) -> None:
    """Observed reset deviating > 30 min from the model sets the flag."""
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    # Seed previous remaining so a jump occurs at a time far from the
    # model's predicted Monday 00:00 UTC reset (e.g. Wednesday 12:00 UTC).
    _feed(coordinator, {"weekly": _window("weekly", 5.0)}, _utc("2026-10-14T11:00:00Z"))
    _feed(
        coordinator, {"weekly": _window("weekly", 95.0)}, _utc("2026-10-14T12:00:00Z")
    )
    assert coordinator.data.anchor_divergence is True
    assert coordinator.data.reset_events.get("weekly")


async def test_no_jump_at_boundary_does_not_flag(hass) -> None:
    """A predicted reset passing with no jump is normal — no flag."""
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    # Monday 2026-10-12 00:00 UTC is a predicted weekly boundary; the
    # remaining figure stays flat (zero usage) across it.
    _feed(
        coordinator, {"weekly": _window("weekly", 100.0)}, _utc("2026-10-11T23:00:00Z")
    )
    _feed(
        coordinator, {"weekly": _window("weekly", 100.0)}, _utc("2026-10-12T01:00:00Z")
    )
    assert coordinator.data.anchor_divergence is False
    assert not coordinator.data.reset_events.get("weekly")


async def test_small_jump_does_not_register(hass) -> None:
    """A jump that is not large (<= 25 points) is not a reset event."""
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    _feed(
        coordinator, {"weekly": _window("weekly", 50.0)}, _utc("2026-10-12T00:05:00Z")
    )
    _feed(
        coordinator, {"weekly": _window("weekly", 70.0)}, _utc("2026-10-12T00:10:00Z")
    )
    assert not coordinator.data.reset_events.get("weekly")
    assert coordinator.data.anchor_divergence is False


async def test_near_idle_small_jump_ignored(hass) -> None:
    """Known corner: a reset on a nearly idle window (98.77 → 100 = 1.23
    points) is below the threshold and records no event.  Acceptable —
    an unused window has nothing to diverge from.  Not a bug.
    """
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    _feed(
        coordinator,
        {"session": _window("session", 98.77)},
        _utc("2026-10-07T08:05:00Z"),
    )
    _feed(
        coordinator,
        {"session": _window("session", 100.0)},
        _utc("2026-10-07T08:10:00Z"),
    )
    assert not coordinator.data.reset_events.get("session")
    assert coordinator.data.anchor_divergence is False


async def test_unmodeled_window_records_event_without_flag(hass) -> None:
    """A jump in an unmodeled window records the event but cannot flag."""
    coordinator = make_coordinator(hass)
    _enable_watchdog(coordinator)
    _feed(
        coordinator, {"monthly": _window("monthly", 5.0)}, _utc("2026-10-12T00:05:00Z")
    )
    _feed(
        coordinator, {"monthly": _window("monthly", 95.0)}, _utc("2026-10-12T00:10:00Z")
    )
    assert coordinator.data.reset_events.get("monthly")
    # No model to compare → divergence flag untouched
    assert coordinator.data.anchor_divergence is False
