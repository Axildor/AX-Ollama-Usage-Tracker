"""Config flow for the AX Ollama Usage Tracker integration.

Flow structure:
1. ``user`` — name, API key (password), scan interval.  The key is
   validated with a real ``GET /api/balance``; 401 surfaces as a friendly
   ``invalid_auth`` flow error; 403 (account suspended / team scope
   without admin) surfaces as the distinct ``suspended`` error — the key
   is valid, so reauth-style messaging would be wrong.
2. ``reauth`` — re-prompts only the API key.

The v0.2 ``verify`` step (pasted settings-page ``data-time`` values
cross-checked against the reverse-engineered reset model) is removed:
the server now returns ``resets_at`` directly, so there is nothing left
to verify.
"""

from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import (
    OllamaApiError,
    OllamaAuthError,
    OllamaClient,
    OllamaForbiddenError,
)
from .const import (
    CONF_API_KEY,
    CONF_ENABLE_WATCHDOG,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_ENABLE_WATCHDOG,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_SCAN_INTERVAL,
)

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)


class OllamaCloudUsageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the AX Ollama Usage Tracker config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: collect and validate the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Validate the key with a real GET /api/balance.
            session = async_get_clientsession(self.hass)
            client = OllamaClient(session)
            try:
                await client.async_get_balance(user_input[CONF_API_KEY])
            except OllamaAuthError:
                errors["base"] = "invalid_auth"
            except OllamaForbiddenError:
                errors["base"] = "suspended"
            except OllamaApiError as err:
                LOGGER.warning("Ollama usage: key validation failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._data = dict(user_input)
                return self.async_create_entry(
                    title=self._data.get(CONF_NAME, DEFAULT_NAME),
                    data=self._data,
                    options={},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "api_key_help": "Create at ollama.com → Settings → API keys"
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OllamaCloudUsageOptionsFlow:
        """Return the options flow (scan interval + watchdog toggle)."""
        return OllamaCloudUsageOptionsFlow(config_entry)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start the reauth flow (re-prompt only the API key)."""
        # NOTE: ``_reauth_entry_id`` is a reserved property on HA's
        # ConfigFlow; use a distinct attribute name.
        self._reauth_target: str = self.context["entry_id"]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauth with a new API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = OllamaClient(session)
            try:
                await client.async_get_balance(user_input[CONF_API_KEY])
            except OllamaAuthError:
                errors["base"] = "invalid_auth"
            except OllamaForbiddenError:
                errors["base"] = "suspended"
            except OllamaApiError as err:
                LOGGER.warning("Ollama usage: reauth validation failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                entry = self.hass.config_entries.async_get_entry(self._reauth_target)
                if entry is not None:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]},
                    )
                    await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )


class OllamaCloudUsageOptionsFlow(config_entries.OptionsFlow):
    """Options flow: scan interval + opt-in divergence watchdog."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self._entry.options.get(
                        CONF_SCAN_INTERVAL,
                        self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
                vol.Required(
                    CONF_ENABLE_WATCHDOG,
                    default=self._entry.options.get(
                        CONF_ENABLE_WATCHDOG, DEFAULT_ENABLE_WATCHDOG
                    ),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
