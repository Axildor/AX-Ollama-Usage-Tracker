"""The AX Ollama Usage Tracker integration.

Exposes ollama.com cloud usage/balance as sensors, authenticated with the
user's Ollama Cloud API key (not session cookies, not device keys) and
polling the documented balance + usage endpoints (live-validated
2026-10-07).
"""

from __future__ import annotations

from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)

from .const import DOMAIN, PLATFORMS, SUFFIX_COST, SUFFIX_REQUESTS
from .coordinator import OllamaUsageUpdateCoordinator

__all__ = ["async_migrate_entry", "async_setup_entry", "async_unload_entry"]

# v0.2 unique_id suffixes that no longer exist in v0.3.  Entities carrying
# them are purged from the entity registry once at setup so they do not
# linger as permanent "unavailable" ghosts.  Exact-match on the suffix
# shape — v0.3's own suffixes (requests_24h / requests_7d) must survive.
_REMOVED_SUFFIXES: Final = (SUFFIX_COST, SUFFIX_REQUESTS)


def _purge_removed_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove v0.2-era registry entities (Activity Cost, per-model Requests).

    Runs once at setup per entry.  Matches by unique_id suffix:
    ``{entry_id}_activity_cost`` and ``{entry_id}_{window}_{model}_requests``.
    The v0.3 ``requests_24h`` / ``requests_7d`` suffixes do not end in the
    bare ``_requests`` token, so they are never matched.
    """
    registry = async_get(hass)
    for reg_entry in async_entries_for_config_entry(registry, entry.entry_id):
        unique_id = reg_entry.unique_id or ""
        if not unique_id.startswith(f"{entry.entry_id}_"):
            continue
        suffix = unique_id[len(entry.entry_id) + 1 :]
        if suffix == SUFFIX_COST or suffix.endswith(f"_{SUFFIX_REQUESTS}"):
            registry.async_remove(reg_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AX Ollama Usage Tracker from a config entry."""
    _purge_removed_entities(hass, entry)
    coordinator = OllamaUsageUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: OllamaUsageUpdateCoordinator = hass.data[DOMAIN].pop(
            entry.entry_id
        )
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
