"""Tests for the v0.2→v0.3 entity-registry purge in __init__.py.

Removed v0.2 entities (Activity Cost, per-model Requests) must be
deleted from the registry on upgrade — not left as permanent
"unavailable" ghosts.  The v0.3 requests_24h / requests_7d entities
must survive.

Uses the REAL entity registry from the harness ``hass`` fixture so the
genuine registry code path (async_get_or_create / async_remove) is
exercised.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_registry import (
    async_entries_for_config_entry,
    async_get,
)
import pytest

from custom_components.ax_ollama_usage.__init__ import _purge_removed_entities
from custom_components.ax_ollama_usage.const import DOMAIN


@pytest.fixture
async def entry(hass) -> ConfigEntry:
    """A real config entry registered in the harness hass."""
    entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Purge Test",
        data={"api_key": "k", "scan_interval": 300},
        options={},
        source="user",
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
    await hass.config_entries.async_add(entry)
    return entry


def _register(hass, entry: ConfigEntry, suffix: str) -> str:
    """Create a real registry entity for the entry; return its entity_id."""
    registry = async_get(hass)
    reg_entry = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_{suffix}",
        config_entry=entry,
        suggested_object_id=suffix,
    )
    return reg_entry.entity_id


def _entity_ids(hass, entry: ConfigEntry) -> set[str]:
    registry = async_get(hass)
    return {
        e.entity_id for e in async_entries_for_config_entry(registry, entry.entry_id)
    }


def test_purge_removes_activity_cost_and_per_model(hass, entry) -> None:
    """Old activity_cost + per-model _requests entities are removed."""
    a = _register(hass, entry, "activity_cost")
    b = _register(hass, entry, "session_glm-5.3-flash_requests")
    c = _register(hass, entry, "weekly_qwen3_requests")
    assert {a, b, c} <= _entity_ids(hass, entry)

    _purge_removed_entities(hass, entry)

    remaining = _entity_ids(hass, entry)
    assert a not in remaining
    assert b not in remaining
    assert c not in remaining


def test_purge_keeps_v03_entities(hass, entry) -> None:
    """v0.3 unique_ids (requests_24h / requests_7d) are never matched."""
    d = _register(hass, entry, "requests_24h")
    e = _register(hass, entry, "requests_7d")
    f = _register(hass, entry, "session_usage")
    g = _register(hass, entry, "session_resets_at")
    h = _register(hass, entry, "purchased_balance")

    _purge_removed_entities(hass, entry)

    remaining = _entity_ids(hass, entry)
    assert {d, e, f, g, h} <= remaining


def test_purge_mixed_registry(hass, entry) -> None:
    """A mixed registry: only the removed shapes go, everything else stays."""
    removed_1 = _register(hass, entry, "activity_cost")
    removed_2 = _register(hass, entry, "session_glm-5.3_requests")
    kept_1 = _register(hass, entry, "requests_24h")
    kept_2 = _register(hass, entry, "weekly_remaining")
    kept_3 = _register(hass, entry, "clock_skew")

    _purge_removed_entities(hass, entry)

    remaining = _entity_ids(hass, entry)
    assert removed_1 not in remaining
    assert removed_2 not in remaining
    assert {kept_1, kept_2, kept_3} <= remaining


async def test_purge_ignores_foreign_unique_ids(hass, entry) -> None:
    """Entries whose unique_id lacks the entry_id prefix are untouched."""
    # Register under a DIFFERENT config entry so the prefix check skips it.
    other = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="Other",
        data={},
        options={},
        source="user",
        unique_id=None,
        discovery_keys={},
        subentries_data=[],
    )
    await hass.config_entries.async_add(other)
    foreign = _register(hass, other, "activity_cost")

    _purge_removed_entities(hass, entry)

    assert foreign in _entity_ids(hass, other)
