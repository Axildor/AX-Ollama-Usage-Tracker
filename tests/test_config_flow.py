"""Tests for the config flow (user, reauth, options).

The live key-validation call is patched at the OllamaClient boundary so
no HTTP mocking library is needed (aioresponses/respx are incompatible
with the aiohttp 3.14 pin in HA 2026.x).  Validation hits
``GET /api/balance`` since v0.3.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
import pytest

from custom_components.ax_ollama_usage.api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaForbiddenError,
)
from custom_components.ax_ollama_usage.const import (
    CONF_API_KEY,
    CONF_ENABLE_WATCHDOG,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DOMAIN,
)

from .conftest import SAMPLE_BALANCE_LEGACY

USER_INPUT: dict[str, Any] = {
    CONF_NAME: "Ollama Cloud",
    CONF_API_KEY: "good-key",
    CONF_SCAN_INTERVAL: 300,
}

_PATCH_TARGET = (
    "custom_components.ax_ollama_usage.config_flow.OllamaClient.async_get_balance"
)

# The pytest-homeassistant-custom-component harness provides the
# ``enable_custom_integrations`` fixture; tests below request it directly.

_SETUP_PATCH = "homeassistant.config_entries.ConfigEntries.async_setup"
_RELOAD_PATCH = "homeassistant.config_entries.ConfigEntries.async_reload"


@pytest.mark.parametrize(
    ("side_effect", "expected_error"),
    [
        (OllamaAuthError("invalid credentials"), "invalid_auth"),
        (OllamaForbiddenError("account suspended"), "suspended"),
        (OllamaApiError("HTTP 503"), "cannot_connect"),
    ],
)
async def test_user_step_rejects_bad_key(
    hass, enable_custom_integrations, side_effect: Exception, expected_error: str
) -> None:
    """A bad key surfaces a friendly flow error and re-shows the form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(_PATCH_TARGET, side_effect=side_effect):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result2["type"] == FlowResultType.FORM
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": expected_error}


async def test_user_step_good_key_creates_entry(
    hass, enable_custom_integrations
) -> None:
    """A good key creates the entry directly (the verify step is gone)."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with (
        patch(_PATCH_TARGET, new=AsyncMock(return_value=SAMPLE_BALANCE_LEGACY)),
        patch(_SETUP_PATCH, return_value=True) as mock_setup,
        patch(_RELOAD_PATCH, return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert mock_setup.call_count == 1
    assert result2["data"][CONF_API_KEY] == "good-key"
    assert result2["data"][CONF_SCAN_INTERVAL] == 300


async def test_options_flow_scan_interval_and_watchdog(
    hass, enable_custom_integrations
) -> None:
    """The options flow offers scan_interval + the watchdog toggle."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Ollama Cloud",
        data={CONF_API_KEY: "k", CONF_SCAN_INTERVAL: 300},
        options={},
        source=config_entries.SOURCE_USER,
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
    await hass.config_entries.async_add(entry)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    schema_keys = list(result["data_schema"].schema)
    assert CONF_SCAN_INTERVAL in schema_keys
    assert CONF_ENABLE_WATCHDOG in schema_keys
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_SCAN_INTERVAL: 600, CONF_ENABLE_WATCHDOG: True},
    )
    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 600
    assert entry.options[CONF_ENABLE_WATCHDOG] is True


async def test_reauth_flow_prompts_key_only(hass, enable_custom_integrations) -> None:
    """The reauth flow re-prompts only the API key and updates the entry."""
    entry = config_entries.ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Ollama Cloud",
        data={CONF_API_KEY: "old", CONF_SCAN_INTERVAL: 300},
        options={},
        source=config_entries.SOURCE_USER,
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
    await hass.config_entries.async_add(entry)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id},
        data={CONF_API_KEY: "old"},
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    schema_keys = list(result["data_schema"].schema)
    assert len(schema_keys) == 1  # only the API key is re-prompted
    with (
        patch(_PATCH_TARGET, new=AsyncMock(return_value=SAMPLE_BALANCE_LEGACY)),
        patch(_RELOAD_PATCH, return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_API_KEY: "new-key"}
        )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "new-key"
