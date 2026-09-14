"""Config flow for the Ollama Cloud Usage integration.

Flow structure:
1. ``user`` — name, API key (password), scan interval.  The key is
   validated with a real ``GET /api/usage``; 401 surfaces as a friendly
   ``invalid_auth`` flow error.
2. ``verify`` (optional) — displays the computed next session and weekly
   resets (ISO UTC) and offers a free-text field to paste ``data-time``
   attribute values from https://ollama.com/settings.  Pasted values
   disagreeing with the model by more than 5 minutes set the divergence
   flag and log a warning — but setup still completes.  Empty = skip.
3. ``reauth`` — re-prompts only the API key.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import OllamaApiError, OllamaAuthError, OllamaClient
from .const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_DATA_TIMES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MIN_SCAN_INTERVAL,
    SETTINGS_URL,
    VERIFY_TOLERANCE,
)
from .reset_math import next_session_reset, next_weekly_reset

_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)
        ),
    }
)

_VERIFY_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_VERIFY_DATA_TIMES, default=""): str,
    }
)


def _parse_pasted_times(raw: str) -> list[datetime]:
    """Parse whitespace/comma-separated ``data-time`` values into datetimes."""
    parsed: list[datetime] = []
    for token in raw.replace(",", " ").split():
        try:
            dt = datetime.fromisoformat(token.replace("Z", "+00:00"))
        except ValueError:
            LOGGER.warning("Ollama usage verify: cannot parse pasted time %r", token)
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        parsed.append(dt)
    return parsed


class OllamaCloudUsageConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the Ollama Cloud Usage config flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._data: dict[str, Any] = {}
        self._divergence: bool = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: collect and validate the API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Validate the key with a real GET /api/usage.
            session = async_get_clientsession(self.hass)
            client = OllamaClient(session)
            try:
                await client.async_get_usage(user_input[CONF_API_KEY])
            except OllamaAuthError:
                errors["base"] = "invalid_auth"
            except OllamaApiError as err:
                LOGGER.warning("Ollama usage: key validation failed: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._data = dict(user_input)
                return await self.async_step_verify()
            finally:
                # The shared session must not be closed here — it is owned
                # by the helper.  Nothing to do; kept for clarity.
                pass

        return self.async_show_form(
            step_id="user",
            data_schema=_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "api_key_help": "Create at ollama.com → Settings → API keys"
            },
        )

    async def async_step_verify(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2 (optional): show computed resets, accept pasted data-times."""
        now = datetime.now(tz=UTC)
        predicted_session = next_session_reset(now)
        predicted_weekly = next_weekly_reset(now)

        if user_input is not None:
            raw = user_input.get(CONF_VERIFY_DATA_TIMES, "")
            if raw.strip():
                pasted = _parse_pasted_times(raw)
                for dt in pasted:
                    # Compare against both models; a match within tolerance
                    # for either window counts as agreement.
                    best = min(
                        (
                            abs((dt - predicted_session).total_seconds()),
                            abs((dt - predicted_weekly).total_seconds()),
                        )
                    )
                    if best > VERIFY_TOLERANCE:
                        self._divergence = True
                        LOGGER.warning(
                            "Ollama usage verify: pasted data-time %s disagrees "
                            "with the reset model by %.0f s (> %d s) — "
                            "divergence flag set; setup continues",
                            dt.isoformat(),
                            best,
                            VERIFY_TOLERANCE,
                        )
            return self.async_create_entry(
                title=self._data.get(CONF_NAME, DEFAULT_NAME),
                data=self._data,
                options={},
            )

        return self.async_show_form(
            step_id="verify",
            data_schema=_VERIFY_SCHEMA,
            description_placeholders={
                "session_reset": predicted_session.isoformat(),
                "weekly_reset": predicted_weekly.isoformat(),
                "settings_url": SETTINGS_URL,
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OllamaCloudUsageOptionsFlow:
        """Return the options flow (scan interval only)."""
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
                await client.async_get_usage(user_input[CONF_API_KEY])
            except OllamaAuthError:
                errors["base"] = "invalid_auth"
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
    """Options flow: adjust the scan interval."""

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
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
