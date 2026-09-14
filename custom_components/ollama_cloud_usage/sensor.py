"""Sensor platform for the Ollama Cloud Usage integration.

Entity layout (one device per config entry):

Per window W (created dynamically for every key in ``coordinator.data.windows``):
- ``<W> Usage`` — %, MEASUREMENT, precision 1, icon ``mdi:gauge``;
  attributes: ``models``, ``predicted_reset_utc``, ``window_key``
- ``<W> Remaining`` — %, MEASUREMENT, icon ``mdi:gauge-empty``
- ``<W> Resets At`` — ``device_class: timestamp``; ``unknown`` for
  unmodeled windows (``daily``, ``monthly``, unknown keys)

Per entry (diagnostics):
- ``Activity Cost`` — USD over the rolling 4-week period
- ``Clock Skew`` — seconds between HA UTC now and the server time
- ``Anchor Divergence`` — on/off boolean, diagnostic

Window keys that disappear from the API payload leave their registry
entries in place; those entities report ``unavailable``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_MODELS,
    ATTR_PREDICTED_RESET,
    ATTR_WINDOW_KEY,
    DOMAIN,
    MANUFACTURER,
    MODEL,
    SUFFIX_COST,
    SUFFIX_DIVERGENCE,
    SUFFIX_REMAINING,
    SUFFIX_RESETS_AT,
    SUFFIX_SKEW,
    SUFFIX_USAGE,
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
        if not new_windows:
            return
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
        async_add_entities(entities)

    _add_new_entities()

    # Entry-level diagnostics (always present)
    async_add_entities(
        [
            OllamaActivityCostSensor(coordinator, entry),
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
    """``<W> Usage`` — used fraction as a percentage."""

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the usage sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_USAGE)

    _attr_icon = "mdi:gauge"
    _attr_state_class = "measurement"
    _attr_suggested_display_precision = 1
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Usage percentage for this window."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return round(wdata.usage_fraction * 100, 1)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Attributes: models, predicted_reset_utc, window_key."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return {
            ATTR_MODELS: wdata.models,
            ATTR_PREDICTED_RESET: (
                predicted.isoformat()
                if (predicted := self.coordinator.predicted_reset(self._window))
                else None
            ),
            ATTR_WINDOW_KEY: self._window,
        }


class OllamaRemainingSensor(_WindowSensorBase, SensorEntity):
    """``<W> Remaining`` — 100% minus usage."""

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the remaining sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_REMAINING)

    _attr_icon = "mdi:gauge-empty"
    _attr_state_class = "measurement"
    _attr_suggested_display_precision = 1
    _attr_native_unit_of_measurement = "%"

    @property
    def native_value(self) -> float | None:
        """Remaining percentage for this window."""
        wdata = self._window_data()
        if wdata is None:
            return None
        return round(max(0.0, (1.0 - wdata.usage_fraction)) * 100, 1)


class OllamaResetsAtSensor(_WindowSensorBase, SensorEntity):
    """``<W> Resets At`` — computed UTC reset time (timestamp device class)."""

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
        window: str,
    ) -> None:
        """Initialize the resets-at sensor."""
        _WindowSensorBase.__init__(self, coordinator, entry, window, SUFFIX_RESETS_AT)

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Predicted reset datetime, or None (unknown) for unmodeled windows."""
        return self.coordinator.predicted_reset(self._window)


class OllamaActivityCostSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Activity Cost`` — USD over the rolling 4-week period."""

    _attr_icon = "mdi:cash"
    _attr_state_class = "total"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(
        self,
        coordinator: OllamaUsageUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the cost sensor."""
        super().__init__(coordinator, entry, SUFFIX_COST)

    @property
    def native_value(self) -> float | None:
        """Parsed activity cost."""
        data = self.coordinator.data
        if data is None:
            return None
        return data.activity_cost


class OllamaClockSkewSensor(_OllamaUsageBaseEntity, SensorEntity):
    """``Clock Skew`` — seconds between HA UTC now and the server time."""

    _attr_icon = "mdi:clock-outline"
    _attr_state_class = "measurement"
    _attr_native_unit_of_measurement = "s"

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
