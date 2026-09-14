"""Data update coordinator for the Ollama Cloud Usage integration.

One GET per tick against the undocumented ``/api/usage`` endpoint.
Responsibilities:

- Parse the payload into :class:`OllamaUsageCoordinatorData` with a
  **dynamic** ``windows`` dict — the window key list is never hardcoded
  (observed variants: ``session``+``weekly``, ``daily``+``weekly``,
  ``monthly``-only, arbitrary unknown keys).
- Parse ``activity.cost`` from its JSON-string form (``"0.00000"``).
- Capture ``activity.period.ending_at`` (nanosecond-precision ISO UTC)
  as ``server_time`` for the clock-skew diagnostic.
- Exponential backoff on HTTP 429/5xx (double per consecutive failure,
  capped at 1 hour); ``UpdateFailed`` on network/timeout errors so
  sensors go unavailable but the coordinator never raises past itself.
- Divergence watchdog: track previous usage fractions per window; when a
  poll shows a large drop (``new < old * 0.5``) record a reset event and
  compare it against the reset model's prediction.  A deviation greater
  than 30 minutes sets ``anchor_divergence`` and logs a warning — the
  model itself is never modified.
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

from .api import OllamaApiError, OllamaAuthError, OllamaClient, OllamaRateLimitError
from .const import (
    BACKOFF_MAX,
    DEFAULT_SCAN_INTERVAL,
    DIVERGENCE_TOLERANCE,
    DROP_THRESHOLD,
    LOGGER,
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
    """Parsed state for one usage window (e.g. ``session``, ``weekly``)."""

    usage_fraction: float
    models: dict[str, int]
    raw_key: str


@dataclass
class OllamaUsageCoordinatorData:
    """Snapshot read by all entities.

    ``windows`` is dynamic — keys are whatever the API returned on the
    latest successful poll.  Windows that disappear from the payload are
    dropped from this dict; the sensor platform keeps their registry
    entries and reports them ``unavailable``.
    """

    windows: dict[str, WindowData] = field(default_factory=dict)
    activity_cost: float | None = None
    activity_period: dict[str, Any] | None = None
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


def _parse_models(raw_models: Any) -> dict[str, int]:
    """Parse the ``models`` list into a ``{name: request_count}`` dict."""
    result: dict[str, int] = {}
    if not isinstance(raw_models, list):
        return result
    for entry in raw_models:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        count = entry.get("request_count")
        if isinstance(name, str) and isinstance(count, (int, float)):
            result[name] = int(count)
    return result


class OllamaUsageUpdateCoordinator(DataUpdateCoordinator[OllamaUsageCoordinatorData]):
    """Coordinator polling ``GET /api/usage`` for one account."""

    def __init__(self, hass, entry: ConfigEntry) -> None:
        """Initialize the coordinator for a config entry."""
        scan_interval = entry.options.get(
            "scan_interval", entry.data.get("scan_interval", DEFAULT_SCAN_INTERVAL)
        )
        super().__init__(
            hass,
            LOGGER,
            name=f"Ollama Cloud Usage ({entry.title})",
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
        # Watchdog: previous usage fraction per window key
        self._previous_usage: dict[str, float] = {}

    # ------------------------------------------------------------------
    # Backoff
    # ------------------------------------------------------------------

    def _apply_backoff(self) -> None:
        """Double the update interval per consecutive 429/5xx, cap 1 h."""
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
        """Detect usage drops, record reset events, compare with the model.

        - A drop (``new < old * 0.5``) records a reset event at ``now``.
        - If the observed reset deviates from the model's prediction by
          more than 30 minutes, set ``anchor_divergence`` and log a
          warning.  The model is never modified.
        - A predicted reset passing with no drop is normal (usage may be
          zero) and does not flag.
        """
        data = self.data
        for window, wdata in windows.items():
            old = self._previous_usage.get(window)
            new = wdata.usage_fraction
            if old is not None and new < old * DROP_THRESHOLD:
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
            self._previous_usage[window] = new

    # ------------------------------------------------------------------
    # Poll
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> OllamaUsageCoordinatorData:
        """Fetch and parse one usage payload."""
        now = dt_util.utcnow()
        try:
            payload = await self._client.async_get_usage(self._api_key)
        except OllamaAuthError as err:
            raise ConfigEntryAuthFailed(
                "Ollama API key rejected (invalid credentials)"
            ) from err
        except OllamaRateLimitError as err:
            self._apply_backoff()
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

        windows: dict[str, WindowData] = {}
        limits = payload.get("limits")
        if isinstance(limits, dict):
            # Iterate whatever window keys are present — never hardcode.
            for window_key, raw_window in limits.items():
                if not isinstance(raw_window, dict):
                    continue
                usage = raw_window.get("usage")
                if not isinstance(usage, (int, float)):
                    LOGGER.warning(
                        "Ollama usage: window '%s' has no numeric 'usage'; skipped",
                        window_key,
                    )
                    continue
                windows[window_key] = WindowData(
                    usage_fraction=float(usage),
                    models=_parse_models(raw_window.get("models")),
                    raw_key=window_key,
                )

        activity = payload.get("activity")
        cost: float | None = None
        period: dict[str, Any] | None = None
        server_time: datetime | None = None
        if isinstance(activity, dict):
            raw_cost = activity.get("cost")
            if isinstance(raw_cost, str):
                try:
                    cost = float(raw_cost)
                except ValueError:
                    LOGGER.warning(
                        "Ollama usage: cannot parse activity.cost %r", raw_cost
                    )
            elif isinstance(raw_cost, (int, float)):
                cost = float(raw_cost)
            raw_period = activity.get("period")
            if isinstance(raw_period, dict):
                period = raw_period
                ending_at = raw_period.get("ending_at")
                if isinstance(ending_at, str):
                    server_time = _parse_iso_utc(ending_at)

        data = OllamaUsageCoordinatorData(
            windows=windows,
            activity_cost=cost,
            activity_period=period,
            server_time=server_time,
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
        """Close the API client on unload."""
        await self._client.close()
