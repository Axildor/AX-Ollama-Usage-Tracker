"""Constants for the Ollama Cloud Usage integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "ax_ollama_usage"
LOGGER: Final = logging.getLogger(__package__)

MANUFACTURER: Final = "Axildor"
MODEL: Final = "AX Ollama Usage Tracker"

CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_NAME: Final = "name"
CONF_ENABLE_WATCHDOG: Final = "enable_watchdog"

DEFAULT_NAME: Final = "Ollama Cloud"
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 60
DEFAULT_ENABLE_WATCHDOG: Final = False

# HTTP client behaviour
API_BASE_URL: Final = "https://ollama.com"
SETTINGS_URL: Final = f"{API_BASE_URL}/settings"
BALANCE_ENDPOINT: Final = "/api/balance"
USAGE_ENDPOINT: Final = "/api/usage"
USAGE_RANGE_24H: Final = "24h"
USAGE_RANGE_7D: Final = "7d"
REQUEST_TIMEOUT: Final = 15
USER_AGENT: Final = "ha-ollama-cloud-usage/0.3.0"

# Backoff (429 / 5xx): double per consecutive failure, capped at 1 hour.
# A 429 carrying a Retry-After header overrides the exponential path with
# exactly that many seconds (still capped, never multiplied).
BACKOFF_MAX: Final = 3600

# Divergence watchdog thresholds
DIVERGENCE_TOLERANCE: Final = 1800  # 30 minutes, seconds
DROP_THRESHOLD: Final = 0.5  # legacy (v0.2) usage-fraction drop threshold
# v0.3 watchdog: a reset is a jump-up of remaining_percent by more than
# this many points between consecutive polls.
RESET_JUMP_THRESHOLD: Final = 25.0

# Clock-skew diagnostic threshold (seconds)
CLOCK_SKEW_WARN: Final = 120

# Reset model (reverse-engineered — see reset_math.py docstring)
SESSION_BUCKET_SECONDS: Final = 18000  # 5 hours, epoch-anchored
WEEKLY_ANCHOR_WEEKDAY: Final = 0  # Monday

# Window keys with a known (reverse-engineered) reset model.
WINDOW_SESSION: Final = "session"
WINDOW_WEEKLY: Final = "weekly"

# Sensor suffixes
SUFFIX_USAGE: Final = "usage"
SUFFIX_REMAINING: Final = "remaining"
SUFFIX_RESETS_AT: Final = "resets_at"
SUFFIX_REQUESTS_24H: Final = "requests_24h"
SUFFIX_REQUESTS_7D: Final = "requests_7d"
SUFFIX_PURCHASED_BALANCE: Final = "purchased_balance"
SUFFIX_INCLUDED_BALANCE: Final = "included_balance"
SUFFIX_INCLUDED_ALLOWANCE: Final = "included_allowance"
SUFFIX_INCLUDED_RESETS_AT: Final = "included_resets_at"
SUFFIX_SKEW: Final = "clock_skew"
SUFFIX_DIVERGENCE: Final = "anchor_divergence"

# Removed in v0.3 — kept ONLY for the upgrade-time registry purge in
# __init__.py (entities created by v0.2 must be deleted, not orphaned).
SUFFIX_COST: Final = "activity_cost"
SUFFIX_REQUESTS: Final = "requests"

# Friendly labels for known window keys. Unknown keys are title-cased
# with underscores converted to spaces (e.g. "last_4_weeks" →
# "Last 4 Weeks") so every entity gets a legible name.
WINDOW_LABELS: Final[dict[str, str]] = {
    WINDOW_SESSION: "Session",
    WINDOW_WEEKLY: "Weekly",
    "daily": "Daily",
    "monthly": "Monthly",
}


def window_label(window: str) -> str:
    """Human-readable label for a window key."""
    return WINDOW_LABELS.get(window) or window.replace("_", " ").title()


# Usage sensor attribute keys
ATTR_RESETS_AT: Final = "resets_at"
ATTR_CURRENT_HOUR_REQUESTS: Final = "current_hour_requests"
ATTR_WINDOW_KEY: Final = "window_key"

# Platform
PLATFORMS: Final = ["sensor"]
