"""Data update coordinator for the AX Ollama Usage Tracker integration.

Three GETs per tick against the documented endpoints (live-validated
2026-10-07): ``GET /api/balance`` (no params), ``GET /api/usage?range=24h``
and ``GET /api/usage?range=7d``.  Responsibilities:

- Parse the balance payload into :class:`OllamaUsageCoordinatorData` with
  a **dynamic** ``windows`` dict — the window key list is never
  hardcoded.  ``BalanceResponse.included`` is a documented ``oneOf``:
  legacy ``{session, weekly}`` windows OR credits
  ``{balance_usd, allowance_usd, period}``.  Both branches are parsed;
  the variant is detected by key shape (tolerant, not strict).
- Parse ``purchased.balance_usd`` tolerantly (str-or-number — this API
  family has mutated before).
- Parse the usage payloads: ``totals.request_count`` per range, the
  current-hour count from the final ``partial: true`` bucket, and
  ``until`` (nanosecond-precision ISO UTC) as ``server_time`` for the
  clock-skew diagnostic.
- Backoff on HTTP 429/5xx: a 429 carrying ``Retry-After`` schedules the
  next attempt at exactly that many seconds (capped, never multiplied);
  otherwise the interval doubles per consecutive failure (cap 1 hour).
  ``UpdateFailed`` on network/timeout errors so sensors go unavailable
  but the coordinator never raises past itself.
- HTTP 403 (account suspended / team scope without admin) →
  ``UpdateFailed`` with a distinct message — the key is valid, so
  reauth is NOT triggered.
- Divergence watchdog (opt-in, default off): track previous
  ``remaining_percent`` per window; when a poll shows a large jump up
  (``new > old + RESET_JUMP_THRESHOLD``) record a reset event and
  compare it against the reset model's prediction.  A deviation greater
  than 30 minutes sets ``anchor_divergence`` and logs a warning — the
  model itself is never modified.  Known corner: a reset on a nearly
  idle window produces a small jump (e.g. 98.77 → 100 = 1.23 points)
  below the threshold and records no event — acceptable, an unused
  window has nothing to diverge from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
import homeassistant.util.dt as dt_util

from .api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaClient,
    OllamaForbiddenError,
    OllamaRateLimitError,
)
from .const import (
    BACKOFF_MAX,
    DEFAULT_ENABLE_WATCHDOG,
    DEFAULT_SCAN_INTERVAL,
    DIVERGENCE_TOLERANCE,
    LOGGER,
    RESET_JUMP_THRESHOLD,
    USAGE_RANGE_7D,
    USAGE_RANGE_24H,
)
from .reset_math import next_reset_for_window

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

__all__ = [
    "OllamaUsageCoordinatorData",
    "OllamaUsageUpdateCoordinator",
    "WindowData",
]


@dataclass
class WindowData:
    """Parsed state for one usage window (e.g. ``session``, ``weekly``).

    ``remaining_percent`` is the server's REMAINING figure (0-100);
    :attr:`used_percent` derives the used figure so existing "Usage"
    sensors and automations keep their meaning.
    """

    remaining_percent: float
    resets_at: datetime | None
    raw_key: str

    @property
    def used_percent(self) -> float:
        """Used percentage (100 - remaining, clamped to 0-100)."""
        return max(0.0, min(100.0, 100.0 - self.remaining_percent))


@dataclass
class OllamaUsageCoordinatorData:
    """Snapshot read by all entities.

    ``windows`` is dynamic — keys are whatever the balance payload
    returned on the latest successful poll (legacy branch).  On the
    credits branch ``windows`` is an EMPTY dict (not absent) so legacy
    window sensors report unavailable per the never-delete rule.
    Windows that disappear from the payload are dropped from this dict;
    the sensor platform keeps their registry entries and reports them
    ``unavailable``.
    """

    windows: dict[str, WindowData] = field(default_factory=dict)
    purchased_balance_usd: float | None = None
    # Credits-branch fields (None on the legacy branch)
    included_balance_usd: float | None = None
    allowance_usd: float | None = None
    included_period_until: datetime | None = None
    # Usage payload fields
    requests_24h: int | None = None
    requests_7d: int | None = None
    current_hour_requests: int | None = None
    usage_from: datetime | None = None
    usage_until: datetime | None = None
    server_time: datetime | None = None
    # Watchdog state (exposed for the diagnostics sensors)
    anchor_divergence: bool = False
    reset_events: dict[str, list[datetime]] = field(default_factory=dict)
    last_update_success: bool = True


def _parse_iso_utc(value: str) -> datetime | None:
    """Parse an ISO-8601 UTC timestamp, tolerating nanosecond precision.

    Python 3.11+ ``fromisoformat`` accepts arbitrary fractional digits,
    but older paths and some formats need the 6-digit truncation fallback.
    """
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_usd(raw: Any) -> float | None:
    """Parse a USD figure tolerantly — str or number (API has mutated)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        try:
            return float(raw)
        except ValueError:
            return None
    return None


def _parse_windows(included: dict[str, Any]) -> dict[str, WindowData]:
    """Parse the legacy ``included`` branch into a windows dict.

    Iterates whatever window keys are present — never hardcodes.  Each
    window must carry a numeric ``remaining_percent``; ``resets_at`` is
    passthrough (server-authoritative) and may be absent.
    """
    windows: dict[str, WindowData] = {}
    for window_key, raw_window in included.items():
        if not isinstance(raw_window, dict):
            continue
        remaining = raw_window.get("remaining_percent")
        if not isinstance(remaining, (int, float)) or isinstance(remaining, bool):
            LOGGER.warning(
                "Ollama usage: window '%s' has no numeric 'remaining_percent'; skipped",
                window_key,
            )
            continue
        resets_at = None
        raw_resets = raw_window.get("resets_at")
        if isinstance(raw_resets, str):
            resets_at = _parse_iso_utc(raw_resets)
        windows[window_key] = WindowData(
            remaining_percent=float(remaining),
            resets_at=resets_at,
            raw_key=window_key,
        )
    return windows


def _parse_usage(payload: dict[str, Any]) -> dict[str, Any]:
    """Parse one usage payload into totals/current-hour/server-time fields."""
    parsed: dict[str, Any] = {}
    totals = payload.get("totals")
    if isinstance(totals, dict):
        count = totals.get("request_count")
        if isinstance(count, (int, float)) and not isinstance(count, bool):
            parsed["request_count"] = int(count)
    buckets = payload.get("buckets")
    if isinstance(buckets, list) and buckets:
        last = buckets[-1]
        if isinstance(last, dict) and last.get("partial"):
            count = last.get("request_count")
            if isinstance(count, (int, float)) and not isinstance(count, bool):
                parsed["current_hour_requests"] = int(count)
    raw_until = payload.get("until")
    if isinstance(raw_until, str):
        parsed["until"] = _parse_iso_utc(raw_until)
    raw_from = payload.get("from")
    if isinstance(raw_from, str):
        parsed["from"] = _parse_iso_utc(raw_from)
    return parsed


class OllamaUsageUpdateCoordinator(DataUpdateCoordinator[OllamaUsageCoordinatorData]):
    """Coordinator polling the balance + usage endpoints for one account."""

    def __init__(self, hass, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a config entry."""
        scan_interval = entry.options.get(
            "scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            LOGGER,
            name=f"AX Ollama Usage Tracker ({entry.title})",
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self._entry = entry
        self._api_key: str = entry.data["api_key"]
        session = async_get_clientsession(hass)
        self._client = OllamaClient(session)
        # Backoff state (429 / 5xx)
        self._consecutive_rate_failures: int = 0
        self._base_interval: timedelta = timedelta(seconds=scan_interval)
        # Watchdog: previous remaining percent per window key
        self._previous_remaining: dict[str, float] = {}
        # Watchdog opt-in (options flow)
        self._watchdog_enabled: bool = entry.options.get(
            "enable_watchdog", DEFAULT_ENABLE_WATCHDOG
        )

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _apply_backoff(self, retry_after: int | None = None) -> None:
        """Schedule the next attempt after a retryable error.

        With ``retry_after`` (from a 429's Retry-After header) the next
        interval is EXACTLY that many seconds — capped by BACKOFF_MAX,
        never multiplied or compounded.  Without it the interval doubles
        per consecutive failure (cap 1 hour).
        """
        if retry_after is not None:
            self._consecutive_rate_failures = 0
            capped = min(timedelta(seconds=retry_after), timedelta(seconds=BACKOFF_MAX))
            self.update_interval = capped
            LOGGER.warning(
                "Ollama usage poll rate limited; honoring Retry-After: next"
                " attempt in %s",
                capped,
            )
            return
        self._consecutive_rate_failures += 1
        multiplier = 2 ** min(self._consecutive_rate_failures, 10)
        backoff = self._base_interval * multiplier
        capped = min(backoff, timedelta(seconds=BACKOFF_MAX))
        self.update_interval = capped
        LOGGER.warning(
            "Ollama usage poll failed with a retryable error; backing off to %s",
            capped,
        )

    def _reset_backoff(self) -> None:
        """Restore the normal poll interval after a successful poll."""
        self._consecutive_rate_failures = 0
        self.update_interval = self._base_interval

    # ------------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------------

    def _check_divergence(self, windows: dict[str, WindowData], now: datetime) -> None:
        """Detect remaining-percent jumps, record resets, compare the model.

        Opt-in (``enable_watchdog`` option, default off).  When off, no
        events are recorded and no divergence is flagged — the server's
        ``resets_at`` passthrough is authoritative regardless.

        - A jump up of ``remaining_percent`` by more than
          ``RESET_JUMP_THRESHOLD`` points records a reset event at ``now``.
        - If the observed reset deviates from the model's prediction by
          more than 30 minutes, set ``anchor_divergence`` and log a
          warning.  The model is never modified.
        - Known corner: a reset on a nearly idle window produces a small
          jump (e.g. 98.77 → 100 = 1.23 points) below the threshold and
          records no event — acceptable, an unused window has nothing to
          diverge from.  Not a bug.
        """
        if not self._watchdog_enabled:
            for window, wdata in windows.items():
                self._previous_remaining[window] = wdata.remaining_percent
            return
        data = self.data
        for window, wdata in windows.items():
            old = self._previous_remaining.get(window)
            new = wdata.remaining_percent
            if old is not None and new > old + RESET_JUMP_THRESHOLD:
                events = data.reset_events.setdefault(window, [])
                events.append(now)
                predicted = next_reset_for_window(window, now)
                if predicted is not None:
                    deviation = abs((now - predicted).total_seconds())
                    if deviation > DIVERGENCE_TOLERANCE:
                        data.anchor_divergence = True
                        LOGGER.warning(
                            "Ollama usage watchdog: observed reset for window "
                            "'%s' at %s deviates from the model prediction %s "
                            "by %.0f s (> %d s) — the reset model may be wrong",
                            window,
                            now.isoformat(),
                            predicted.isoformat(),
                            deviation,
                            DIVERGENCE_TOLERANCE,
                        )
                    else:
                        LOGGER.debug(
                            "Ollama usage watchdog: reset event for '%s' "
                            "matches the model (deviation %.0f s)",
                            window,
                            deviation,
                        )
                else:
                    LOGGER.debug(
                        "Ollama usage watchdog: reset event for unmodeled "
                        "window '%s' recorded (no model to compare)",
                        window,
                    )
            self._previous_remaining[window] = new

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> OllamaUsageCoordinatorData:
        """Fetch and parse one balance + two usage payloads."""
        now = dt_util.utcnow()
        balance_payload: dict[str, Any] | None = None
        usage_24h_payload: dict[str, Any] | None = None
        usage_7d_payload: dict[str, Any] | None = None
        try:
            balance_payload = await self._client.async_get_balance(self._api_key)
            usage_24h_payload = await self._client.async_get_usage(
                self._api_key, USAGE_RANGE_24H
            )
            usage_7d_payload = await self._client.async_get_usage(
                self._api_key, USAGE_RANGE_7D
            )
        except OllamaAuthError as err:
            raise ConfigEntryAuthFailed(
                "Ollama API key rejected (invalid credentials)"
            ) from err
        except OllamaForbiddenError as err:
            # 403: account suspended / team scope without admin.  The key
            # is VALID — do NOT trigger reauth; surface as UpdateFailed.
            raise UpdateFailed(
                f"Ollama account suspended or insufficient scope: {err}"
            ) from err
        except OllamaRateLimitError as err:
            self._apply_backoff(err.retry_after)
            raise UpdateFailed(f"Ollama rate limited: {err}") from err
        except OllamaApiError as err:
            # Includes 5xx wrapped by the client and timeouts.
            if "HTTP 5" in str(err):
                self._apply_backoff()
            raise UpdateFailed(f"Error fetching Ollama usage: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed(f"Timeout fetching Ollama usage: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Network error fetching Ollama usage: {err}") from err

        self._reset_backoff()

        # ---- Balance payload ----
        windows: dict[str, WindowData] = {}
        purchased_balance_usd: float | None = None
        included_balance_usd: float | None = None
        allowance_usd: float | None = None
        included_period_until: datetime | None = None
        if isinstance(balance_payload, dict):
            purchased = balance_payload.get("purchased")
            if isinstance(purchased, dict):
                purchased_balance_usd = _parse_usd(purchased.get("balance_usd"))
            included = balance_payload.get("included")
            if isinstance(included, dict):
                if "session" in included or "weekly" in included:
                    # Legacy branch: per-window remaining figures.
                    windows = _parse_windows(included)
                elif "balance_usd" in included:
                    # Credits branch: oneOf variant.
                    included_balance_usd = _parse_usd(included.get("balance_usd"))
                    allowance_usd = _parse_usd(included.get("allowance_usd"))
                    raw_period = included.get("period")
                    if isinstance(raw_period, dict):
                        raw_until = raw_period.get("until")
                        if isinstance(raw_until, str):
                            included_period_until = _parse_iso_utc(raw_until)
                else:
                    LOGGER.warning(
                        "Ollama usage: balance 'included' has an unrecognized"
                        " shape; no windows parsed"
                    )

        # ---- Usage payloads ----
        requests_24h: int | None = None
        requests_7d: int | None = None
        current_hour_requests: int | None = None
        usage_from: datetime | None = None
        usage_until: datetime | None = None
        if isinstance(usage_24h_payload, dict):
            parsed_24h = _parse_usage(usage_24h_payload)
            requests_24h = parsed_24h.get("request_count")
            current_hour_requests = parsed_24h.get("current_hour_requests")
            usage_from = parsed_24h.get("from")
            usage_until = parsed_24h.get("until")
        if isinstance(usage_7d_payload, dict):
            parsed_7d = _parse_usage(usage_7d_payload)
            requests_7d = parsed_7d.get("request_count")

        data = OllamaUsageCoordinatorData(
            windows=windows,
            purchased_balance_usd=purchased_balance_usd,
            included_balance_usd=included_balance_usd,
            allowance_usd=allowance_usd,
            included_period_until=included_period_until,
            requests_24h=requests_24h,
            requests_7d=requests_7d,
            current_hour_requests=current_hour_requests,
            usage_from=usage_from,
            usage_until=usage_until,
            server_time=usage_until,
            anchor_divergence=self.data.anchor_divergence if self.data else False,
            reset_events=self.data.reset_events if self.data else {},
        )
        self.data = data
        self._check_clock_skew(now)
        self._check_divergence(windows, now)
        return data

    def _check_clock_skew(self, now: datetime) -> None:
        """Warn when the local clock disagrees with the server by > 120 s.

        The reset model depends on local clock correctness, so a large
        skew invalidates the predicted reset times.
        """
        if self.data is None or self.data.server_time is None:
            return
        skew = (now - self.data.server_time).total_seconds()
        if abs(skew) > 120:
            LOGGER.warning(
                "Ollama usage: clock skew between HA and ollama.com is %.0f s "
                "(> 120 s) — predicted reset times may be inaccurate",
                skew,
            )

    # ------------------------------------------------------------------
    # Public helpers for entities / config flow
    # ------------------------------------------------------------------

    def predicted_reset(self, window: str) -> datetime | None:
        """Predicted next reset for a window, or ``None`` if unmodeled."""
        return next_reset_for_window(window, dt_util.utcnow())

    @property
    def clock_skew_seconds(self) -> float | None:
        """Seconds between HA UTC now and the server time of the last poll."""
        if self.data is None or self.data.server_time is None:
            return None
        return (dt_util.utcnow() - self.data.server_time).total_seconds()

    async def async_shutdown(self) -> None:
        """Release coordinator resources on unload.

        The aiohttp session is owned by Home Assistant
        (``async_get_clientsession``) and must NOT be closed here —
        closing it would break every other consumer of the shared
        session.  Nothing to release; kept as an explicit no-op hook.
        """
        return None
