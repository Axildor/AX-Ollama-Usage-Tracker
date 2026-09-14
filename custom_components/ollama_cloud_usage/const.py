"""Constants for the Ollama Cloud Usage integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "ollama_cloud_usage"
LOGGER: Final = logging.getLogger(__package__)

MANUFACTURER: Final = "Ollama"
MODEL: Final = "Ollama Cloud"

CONF_API_KEY: Final = "api_key"
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_NAME: Final = "name"
CONF_VERIFY_DATA_TIMES: Final = "verify_data_times"

DEFAULT_NAME: Final = "Ollama Cloud"
DEFAULT_SCAN_INTERVAL: Final = 300
MIN_SCAN_INTERVAL: Final = 60

# HTTP client behaviour
API_BASE_URL: Final = "https://ollama.com"
SETTINGS_URL: Final = f"{API_BASE_URL}/settings"
USAGE_ENDPOINT: Final = "/api/usage"
REQUEST_TIMEOUT: Final = 15
USER_AGENT: Final = "ha-ollama-cloud-usage/0.1.0"

# Backoff (429 / 5xx): double per consecutive failure, capped at 1 hour.
BACKOFF_MAX: Final = 3600

# Divergence watchdog thresholds
DIVERGENCE_TOLERANCE: Final = 1800  # 30 minutes, seconds
VERIFY_TOLERANCE: Final = 300  # 5 minutes, seconds
DROP_THRESHOLD: Final = 0.5  # new < old * 0.5 counts as a reset event

# Clock-skew diagnostic threshold (seconds)
CLOCK_SKEW_WARN: Final = 120

# Reset model (reverse-engineered — see reset_math.py docstring)
SESSION_BUCKET_SECONDS: Final = 18000  # 5 hours
WEEKLY_ANCHOR_WEEKDAY: Final = 0  # Monday

# Window keys with a known (reverse-engineered) reset model.
WINDOW_SESSION: Final = "session"
WINDOW_WEEKLY: Final = "weekly"

# Sensor suffixes
SUFFIX_USAGE: Final = "usage"
SUFFIX_REMAINING: Final = "remaining"
SUFFIX_RESETS_AT: Final = "resets_at"
SUFFIX_REQUESTS: Final = "requests"
SUFFIX_COST: Final = "activity_cost"
SUFFIX_SKEW: Final = "clock_skew"
SUFFIX_DIVERGENCE: Final = "anchor_divergence"

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
ATTR_MODELS: Final = "models"
ATTR_PREDICTED_RESET: Final = "predicted_reset_utc"
ATTR_WINDOW_KEY: Final = "window_key"

# Platform
PLATFORMS: Final = ["sensor"]
