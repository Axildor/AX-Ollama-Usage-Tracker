"""Pure reset-time model for Ollama Cloud usage windows.

Reverse-engineered, deterministic — treat as a model, not a contract.
Since v0.3 the server returns ``resets_at`` directly (passthrough,
authoritative); this model survives only inside the opt-in divergence
watchdog cross-check.

- **Weekly** resets Monday 00:00:00 UTC.  Evidence: settings-page
  ``data-time="2026-09-21T00:00:00Z"`` with the current window opened
  ``2026-09-14T00:00:00Z`` (a Monday); live cross-check passed
  2026-10-07 (server ``resets_at`` 2026-10-12T00:00:00Z, a Monday).
- **Session** resets in fixed 5-hour buckets anchored in EPOCH time —
  ``t ≡ 0 (mod 18000 Unix seconds)`` — NOT to the UTC day.  Formula:
  ``next_reset = ((now_epoch // 18000) + 1) * 18000`` (strictly-greater
  ceil).  Because 5 h does not divide 24 h, the boundaries drift 4 h
  earlier each day on a 5-day cycle, then realign:

      cycle day 0: 00/05/10/15/20 · day 1: 01/06/11/16/21 ·
      day 2: 02/07/12/17/22 · day 3: 03/08/13/18/23 · day 4: 04/09/14/19

  Evidence (all on the epoch lattice, none on a day-anchored lattice):
  settings-page ``data-time`` values 2026-09-14T05:00:00Z and
  2026-09-14T15:00:00Z; the official docs' example
  ``session.resets_at: 2026-10-01T07:00:00Z``; live /api/balance
  2026-10-07 returning ``resets_at`` 08:00:00Z (a phase-3 day); and the
  user-observed rollover at 03:00Z on Oct 7 — on no static day lattice.
  Sanity anchor: Sep 14 00:00Z + 555 h = Oct 7 03:00Z, and 555 h is
  exactly 111 x 5 h — one lattice, one formula.  The 8-hour-lattice
  hypothesis is refuted by all of the above.
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
