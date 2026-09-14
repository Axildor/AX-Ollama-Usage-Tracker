"""Pure reset-time model for Ollama Cloud usage windows.

Reverse-engineered, deterministic — treat as a model, not a contract.

- **Weekly** resets Monday 00:00:00 UTC.  Evidence: settings-page
  ``data-time="2026-09-21T00:00:00Z"`` with the current window opened
  ``2026-09-14T00:00:00Z`` (a Monday).
- **Session** resets in fixed 5-hour buckets on the UTC lattice anchored
  at 00:00 UTC.  Evidence: settings-page ``data-time`` values
  ``2026-09-14T05:00:00Z`` and ``2026-09-14T15:00:00Z`` — both ≡ 0
  (mod 5h), ten hours apart.  A third confirming observation is pending,
  so this ships as the default model, not a hard constant.
- **Any other window** (``daily``, ``monthly``, unknown keys): reset
  anchor UNKNOWN — :func:`next_reset_for_window` returns ``None`` and the
  resets sensor reports ``unknown``.  No anchor is fabricated.

All math is UTC-only (no DST logic).  Both functions are pure so they are
unit-testable.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final

from .const import (
    SESSION_BUCKET_SECONDS,
    WEEKLY_ANCHOR_WEEKDAY,
    WINDOW_SESSION,
    WINDOW_WEEKLY,
)

__all__ = ["next_reset_for_window", "next_session_reset", "next_weekly_reset"]


def _ensure_utc(now: datetime) -> datetime:
    """Return ``now`` converted to UTC (naive input is assumed UTC)."""
    if now.tzinfo is None:
        return now.replace(tzinfo=UTC)
    return now.astimezone(UTC)


def next_session_reset(now: datetime) -> datetime:
    """Return the next 5-hour session boundary strictly after ``now``.

    Buckets sit on the UTC lattice anchored at 00:00 UTC:
    ``next_reset = ceil_strict(now_epoch / 18000) * 18000``.

    The ceil is *strictly greater*: if ``now`` is exactly on a boundary,
    the answer is the NEXT boundary (e.g. 15:00:00Z → 20:00:00Z).
    """
    now_utc = _ensure_utc(now)
    epoch = now_utc.timestamp()
    # floor + 1 implements the strictly-greater ceil: an exact boundary
    # maps to itself + one bucket, never to itself.
    next_epoch = (int(epoch // SESSION_BUCKET_SECONDS) + 1) * SESSION_BUCKET_SECONDS
    return datetime.fromtimestamp(next_epoch, tz=UTC)


def next_weekly_reset(now: datetime) -> datetime:
    """Return the next Monday 00:00:00 UTC strictly after ``now``.

    If ``now`` is exactly Monday 00:00:00 UTC, the answer is the
    following Monday (+7 days) — consistent with the strictly-greater
    convention used for sessions.
    """
    now_utc = _ensure_utc(now)
    # Days until the anchor weekday (Monday), strictly greater.
    days_ahead = (WEEKLY_ANCHOR_WEEKDAY - now_utc.weekday()) % 7
    candidate = (now_utc + timedelta(days=days_ahead)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if candidate <= now_utc:
        candidate += timedelta(days=7)
    return candidate


def next_reset_for_window(window: str, now: datetime) -> datetime | None:
    """Return the predicted next reset for a window key, or ``None``.

    Only ``session`` and ``weekly`` have a (reverse-engineered) model.
    ``daily``, ``monthly`` and any unknown key return ``None`` — the
    anchor is unknown and must not be fabricated.
    """
    known: Final = {
        WINDOW_SESSION: next_session_reset,
        WINDOW_WEEKLY: next_weekly_reset,
    }
    fn = known.get(window)
    if fn is None:
        return None
    return fn(now)
