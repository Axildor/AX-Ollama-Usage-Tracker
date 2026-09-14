"""Tests for the pure reset-time model (reset_math.py)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.ollama_cloud_usage.reset_math import (
    next_reset_for_window,
    next_session_reset,
    next_weekly_reset,
)


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


class TestSessionReset:
    """5-hour UTC buckets, strictly-greater ceil."""

    def test_mid_bucket(self) -> None:
        """2026-09-14T11:00:00Z → 15:00:00Z."""
        assert next_session_reset(_utc("2026-09-14T11:00:00Z")) == _utc(
            "2026-09-14T15:00:00Z"
        )

    def test_exactly_on_boundary_is_strictly_greater(self) -> None:
        """15:00:00Z exactly → 20:00:00Z (next boundary, not itself)."""
        assert next_session_reset(_utc("2026-09-14T15:00:00Z")) == _utc(
            "2026-09-14T20:00:00Z"
        )

    def test_just_after_boundary(self) -> None:
        """15:00:01Z → 20:00:00Z."""
        assert next_session_reset(_utc("2026-09-14T15:00:01Z")) == _utc(
            "2026-09-14T20:00:00Z"
        )

    def test_known_evidence_values(self) -> None:
        """Observed data-time values are ≡ 0 (mod 5h) on the lattice."""
        for iso in ("2026-09-14T05:00:00Z", "2026-09-14T15:00:00Z"):
            dt = _utc(iso)
            assert int(dt.timestamp()) % 18000 == 0

    def test_utc_only(self) -> None:
        """Result is always timezone-aware UTC."""
        result = next_session_reset(_utc("2026-09-14T11:00:00Z"))
        assert result.tzinfo is UTC


class TestWeeklyReset:
    """Monday 00:00:00 UTC anchor."""

    def test_monday_exact_input_goes_next_week(self) -> None:
        """Monday-exact input → +7 days (strictly greater)."""
        assert next_weekly_reset(_utc("2026-09-14T00:00:00Z")) == _utc(
            "2026-09-21T00:00:00Z"
        )

    def test_friday_goes_next_monday(self) -> None:
        """Friday → next Monday 00:00 UTC."""
        assert next_weekly_reset(_utc("2026-09-18T12:00:00Z")) == _utc(
            "2026-09-21T00:00:00Z"
        )

    def test_midweek(self) -> None:
        """Wednesday → next Monday 00:00 UTC."""
        assert next_weekly_reset(_utc("2026-09-16T23:59:59Z")) == _utc(
            "2026-09-21T00:00:00Z"
        )

    def test_utc_only(self) -> None:
        """Result is always timezone-aware UTC Monday 00:00."""
        result = next_weekly_reset(_utc("2026-09-18T12:00:00Z"))
        assert result.tzinfo is UTC
        assert result.weekday() == 0
        assert (result.hour, result.minute, result.second) == (0, 0, 0)


class TestWindowDispatch:
    """next_reset_for_window: modeled vs unmodeled keys."""

    @pytest.mark.parametrize(
        ("window", "expected"),
        [
            ("session", _utc("2026-09-14T15:00:00Z")),
            ("weekly", _utc("2026-09-21T00:00:00Z")),
        ],
    )
    def test_modeled_windows(self, window: str, expected: datetime) -> None:
        now = _utc("2026-09-14T11:00:00Z")
        assert next_reset_for_window(window, now) == expected

    @pytest.mark.parametrize("window", ["daily", "monthly", "weird_window", ""])
    def test_unmodeled_windows_return_none(self, window: str) -> None:
        now = _utc("2026-09-14T11:00:00Z")
        assert next_reset_for_window(window, now) is None
