"""Sensor platform for the AX Ollama Usage Tracker integration.

Entity layout (one device per config entry):

Per window W (created dynamically for every key in the balance payload's
legacy ``included`` branch):
- ``<W> Usage`` — %, MEASUREMENT, precision 1, icon ``mdi:gauge``;
  value = 100 - ``remaining_percent`` so existing automations keep their
  meaning; attributes: ``resets_at``, ``window_key``
- ``<W> Remaining`` — %, MEASUREMENT, icon ``mdi:gauge-empty``;
  value = ``remaining_percent`` (server-authoritative)
- ``<W> Resets At`` — ``device_class: timestamp``; value = the server's
  ``resets_at`` passthrough (authoritative); ``unknown`` when absent

Per entry (always present):
- ``Requests 24h`` — 24h ``totals.request_count``, MEASUREMENT (a
  rolling-window sum can decrease, so NOT ``total_increasing``);
  attribute ``current_hour_requests`` = the final partial bucket's
  count (live rate signal)
- ``Requests 7d`` — 7d ``totals.request_count``, MEASUREMENT
- ``Purchased Balance`` — USD, MONETARY, ``_attr_currency = "USD"``
- ``Clock Skew`` — seconds between HA UTC now and the server time
  (``EntityCategory.DIAGNOSTIC``)
- ``Anchor Divergence`` — on/off boolean, diagnostic
  (``EntityCategory.DIAGNOSTIC``)

Per entry (credits-branch balance variant only; ``unknown`` on legacy):
- ``Included Balance`` — USD, MONETARY, ``_attr_currency = "USD"``
- ``Included Allowance`` — USD, MONETARY, ``_attr_currency = "USD"``
- ``Included Resets At`` — ``device_class: timestamp`` (``period.until``)

Window keys that disappear from the balance payload leave their registry
entries in place; those entities report ``unavailable``.  The v0.2
Activity Cost and per-model Requests entities are removed and purged
from the registry on upgrade (see ``__init__.py``).

Naming: every entity carries a human-readable name. Window sensors use
a friendly label from :func:`.const.window_label` (``session`` →
"Session", unknown keys title-cased); static sensors use
``translation_key`` resolved through ``strings.json``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CURRENT_HOUR_REQUESTS,
    ATTR_RESETS_AT,
    ATTR_WINDOW_KEY,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SUFFIX_DIVERGENCE,
    SUFFIX_INCLUDED_ALLOWANCE,
    SUFFIX_INCLUDED_BALANCE,
    SUFFIX_INCLUDED_RESETS_AT,
    SUFFIX_PURCHASED_BALANCE,
    SUFFIX_REMAINING,
    SUFFIX_REQUESTS_7D,
    SUFFIX_REQUESTS_24H,
    SUFFIX_RESETS_AT,
    SUFFIX_SKEW,
    SUFFIX_USAGE,
    window_label,
)
from .coordinator import OllamaUsageUpdateCoordinator

if TYPE_CHECKING:
    from .coordinator import WindowData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for a config entry, including dynamic windows."""
    coordinator: OllamaUsageUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    known_windows: set[str] = set()

    def _add_new_entities() -> None:
        """Create entities for window keys not yet seen."""
        data = coordinator.data
        if data is None:
            return
        new_windows = set(data.windows) - known_windows
        entities: list[SensorEntity] = []
        for window in sorted(new_windows):
            entities.extend(
                [
                    OllamaUsageSensor(coordinator, entry, window),
                    OllamaRemainingSensor(coordinator, entry, window),
                    OllamaResetsAtSensor(coordinator, entry, window),
                ]
            )
        known_windows.update(new_windows)
        if entities:
            async_add_entities(entities)

    _add_new_entities()

    # Entry-level sensors (always present)
    async_add_entities(
        [
            OllamaRequests24hSensor(coordinator, entry),
            OllamaRequests7dSensor(coordinator, entry),
            OllamaPurchasedBalanceSensor(coordinator, entry),
            OllamaIncludedBalanceSensor(coordinator, entry),
            OllamaIncludedAllowanceSensor(coordinator, entry),
            OllamaIncludedResetsAtSensor(coordinator, entry),
            OllamaClockSkewSensor(coordinator, entry),
            OllamaAnchorDivergenceSensor(coordinator, entry),
        ]
    )

    # Listen for coordinator updates to add entities for new window keys.
    coordinator.async_add_listener(_add_new_entities)


class _OllamaUsageBaseEntity(CoordinatorEntity[OllamaUsageUpdateCoordinator]):
    """Base entity: shared device info and unique-id scheme."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        suffix: str,
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return the shared device for this entry."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            manufacturer=MANUFACTURER,
            model=MODEL,
            name=self._entry.title,
        )


class _WindowSensorBase(_OllamaUsageBaseEntity):
    """Base for per-window sensors."""

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
        suffix: str,
    ) -> None:
        """Initialize a per-window sensor."""
        _OllamaUsageBaseEntity.__init__(self, coordinator, entry, f"{window}_{suffix}")
        self._window = window

    def _window_data(self) -> WindowData | None:
        """Current WindowData for this sensor's window, or None if gone."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.windows.get(self._window)


class OllamaUsageSensor(_WindowSensorBase, SensorEntity):
    """``<W> Usage`` — used percentage (100 - remaining_percent)."""

    _attr_icon = "mdi:gauge"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the usage sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_USAGE)
        self._attr_name = f"{window_label(window)} Usage"

    @property
    def native_value(self) -> float | None:
        """Used percentage for this window."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return round(wdata.used_percent, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes: resets_at (passthrough), window_key."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return {
            ATTR_RESETS_AT: (wdata.resets_at.isoformat() if wdata.resets_at else None),
            ATTR_WINDOW_KEY: self._window,
        }


class OllamaRemainingSensor(_WindowSensorBase, SensorEntity):
    """``<W> Remaining`` — the server's remaining_percent."""

    _attr_icon = "mdi:gauge-empty"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    _attr_native_unit_of_measurement = "%"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the remaining sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_REMAINING)
        self._attr_name = f"{window_label(window)} Remaining"

    @property
    def native_value(self) -> float | None:
        """Remaining percentage for this window."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return round(wdata.remaining_percent, 1)


class OllamaResetsAtSensor(_WindowSensorBase, SensorEntity):
    """``<W> Resets At`` — server ``resets_at`` passthrough (timestamp)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the resets-at sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_RESETS_AT)
        self._attr_name = f"{window_label(window)} Resets At"

    @property
    def native_value(self) -> datetime | None:
        """Server-authoritative reset datetime, or None (unknown)."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return wdata.resets_at


class OllamaRequests24hSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Requests 24h`` — 24h totals.request_count (rolling window)."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "requests"
    _attr_translation_key = "requests_24h"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the 24h requests sensor."""
        super().__init__(coordinator, entry, SUFFIX_REQUESTS_24H)

    @property
    def native_value(self) -> int | None:
        """24h request count."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.requests_24h

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attribute: current_hour_requests (final partial bucket)."""
        data = self.coordinator.data
        if data is None:
            return None
        return {ATTR_CURRENT_HOUR_REQUESTS: data.current_hour_requests}


class OllamaRequests7dSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Requests 7d`` — 7d totals.request_count (rolling window)."""

    _attr_icon = "mdi:counter"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "requests"
    _attr_translation_key = "requests_7d"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the 7d requests sensor."""
        super().__init__(coordinator, entry, SUFFIX_REQUESTS_7D)

    @property
    def native_value(self) -> int | None:
        """7d request count."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.requests_7d


class OllamaPurchasedBalanceSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Purchased Balance`` — purchased.balance_usd (USD)."""

    _attr_icon = "mdi:cash"
    _attr_state_class = SensorStateClass.TOTAL
    # ISO4217 unit — for MONETARY sensors the unit IS the currency signal
    # (this HA build has no separate currency entity attribute).
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_translation_key = "purchased_balance"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the purchased-balance sensor."""
        super().__init__(coordinator, entry, SUFFIX_PURCHASED_BALANCE)

    @property
    def native_value(self) -> float | None:
        """Purchased balance in USD."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.purchased_balance_usd


class OllamaIncludedBalanceSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Included Balance`` — credits-branch included.balance_usd (USD)."""

    _attr_icon = "mdi:cash-multiple"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_translation_key = "included_balance"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the included-balance sensor."""
        super().__init__(coordinator, entry, SUFFIX_INCLUDED_BALANCE)

    @property
    def native_value(self) -> float | None:
        """Included balance in USD (None on the legacy branch)."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.included_balance_usd


class OllamaIncludedAllowanceSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Included Allowance`` — credits-branch allowance_usd (USD)."""

    _attr_icon = "mdi:cash-check"
    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_translation_key = "included_allowance"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the included-allowance sensor."""
        super().__init__(coordinator, entry, SUFFIX_INCLUDED_ALLOWANCE)

    @property
    def native_value(self) -> float | None:
        """Included allowance in USD (None on the legacy branch)."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.allowance_usd


class OllamaIncludedResetsAtSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Included Resets At`` — credits-branch period.until (timestamp)."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "included_resets_at"

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the included-resets-at sensor."""
        super().__init__(coordinator, entry, SUFFIX_INCLUDED_RESETS_AT)

    @property
    def native_value(self) -> datetime | None:
        """Included-period end (None on the legacy branch)."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.included_period_until


class OllamaClockSkewSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Clock Skew`` — seconds between HA UTC now and the server time."""

    _attr_icon = "mdi:clock-outline"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "s"
    _attr_translation_key = "clock_skew"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the skew sensor."""
        super().__init__(coordinator, entry, SUFFIX_SKEW)

    @property
    def native_value(self) -> float | None:
        """Current clock skew in seconds."""
        return self.coordinator.clock_skew_seconds


class OllamaAnchorDivergenceSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Anchor Divergence`` — on/off boolean, diagnostic."""

    _attr_icon = "mdi:alert-octagon"
    _attr_translation_key = "anchor_divergence"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the divergence sensor."""
        super().__init__(coordinator, entry, SUFFIX_DIVERGENCE)

    @property
    def native_value(self) -> bool | None:
        """True when an observed reset deviated from the model."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.anchor_divergence
