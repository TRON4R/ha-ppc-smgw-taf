"""Sensor platform for SMGW TAF integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    CONF_METER_ID,
    DOMAIN,
    SENSOR_DAILY_EXPORT_TOTAL,
    SENSOR_DAILY_IMPORT_GO,
    SENSOR_DAILY_IMPORT_STANDARD,
    SENSOR_DAILY_IMPORT_TOTAL,
    SENSOR_DATE,
    SENSOR_METER_EXPORT_MIDNIGHT,
    SENSOR_METER_IMPORT_0500,
    SENSOR_METER_IMPORT_MIDNIGHT,
)
from .coordinator import SmgwTafCoordinator


@dataclass(frozen=True, kw_only=True)
class SmgwTafSensorEntityDescription(SensorEntityDescription):
    """Describe a SMGW TAF sensor."""

    data_key: str
    is_daily_value: bool = False


SENSOR_DESCRIPTIONS: tuple[SmgwTafSensorEntityDescription, ...] = (
    # --- Daily consumption values (for Energy Dashboard) ---
    SmgwTafSensorEntityDescription(
        key="daily_import_total",
        translation_key="daily_import_total",
        data_key=SENSOR_DAILY_IMPORT_TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        is_daily_value=True,
    ),
    SmgwTafSensorEntityDescription(
        key="daily_import_go",
        translation_key="daily_import_go",
        data_key=SENSOR_DAILY_IMPORT_GO,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        is_daily_value=True,
    ),
    SmgwTafSensorEntityDescription(
        key="daily_import_standard",
        translation_key="daily_import_standard",
        data_key=SENSOR_DAILY_IMPORT_STANDARD,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        is_daily_value=True,
    ),
    SmgwTafSensorEntityDescription(
        key="daily_export_total",
        translation_key="daily_export_total",
        data_key=SENSOR_DAILY_EXPORT_TOTAL,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=4,
        is_daily_value=True,
    ),
    # --- Absolute meter readings (informational) ---
    SmgwTafSensorEntityDescription(
        key="meter_import_midnight",
        translation_key="meter_import_midnight",
        data_key=SENSOR_METER_IMPORT_MIDNIGHT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=4,
        entity_registry_enabled_default=False,
    ),
    SmgwTafSensorEntityDescription(
        key="meter_import_0500",
        translation_key="meter_import_0500",
        data_key=SENSOR_METER_IMPORT_0500,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=4,
        entity_registry_enabled_default=False,
    ),
    SmgwTafSensorEntityDescription(
        key="meter_export_midnight",
        translation_key="meter_export_midnight",
        data_key=SENSOR_METER_EXPORT_MIDNIGHT,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=4,
        entity_registry_enabled_default=False,
    ),
    # --- Date sensor (informational) ---
    SmgwTafSensorEntityDescription(
        key="date",
        translation_key="date",
        data_key=SENSOR_DATE,
        device_class=SensorDeviceClass.DATE,
        icon="mdi:calendar",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SMGW TAF sensors from a config entry."""
    coordinator: SmgwTafCoordinator = config_entry.runtime_data

    entities = [
        SmgwTafSensor(coordinator, description, config_entry)
        for description in SENSOR_DESCRIPTIONS
    ]

    async_add_entities(entities)


class SmgwTafSensor(CoordinatorEntity[SmgwTafCoordinator], SensorEntity):
    """Sensor for SMGW TAF daily meter values."""

    entity_description: SmgwTafSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SmgwTafCoordinator,
        description: SmgwTafSensorEntityDescription,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        meter_id = config_entry.data.get(CONF_METER_ID, config_entry.entry_id)
        self._attr_unique_id = f"{meter_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, meter_id)},
            name=f"Smart Meter {meter_id}",
            manufacturer="PPC",
            model="Smart Meter Gateway",
            serial_number=meter_id,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None
        value = self.coordinator.data.get(self.entity_description.data_key)
        # For DATE sensors, return a date object instead of string
        if (
            self.entity_description.device_class == SensorDeviceClass.DATE
            and isinstance(value, str)
        ):
            try:
                return date_type.fromisoformat(value)
            except ValueError:
                return None
        return value

    @property
    def last_reset(self) -> datetime | None:
        """Return the time when the sensor was last reset.

        For daily value sensors, this is midnight of the measured date.
        Returns timezone-aware datetime using HA's timezone (Fix #1).
        """
        if not self.entity_description.is_daily_value:
            return None
        if self.coordinator.data is None:
            return None
        date_str = self.coordinator.data.get(SENSOR_DATE)
        if date_str:
            # Create timezone-aware datetime using HA's configured timezone
            naive = datetime.fromisoformat(date_str + "T00:00:00")
            return dt_util.as_local(
                naive.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
            )
        return None
