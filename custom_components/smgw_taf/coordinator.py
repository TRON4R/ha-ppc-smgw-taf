"""Data coordinator for SMGW TAF integration."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_UPDATE_TIME,
    DEFAULT_UPDATE_TIME,
    DOMAIN,
    SENSOR_DAILY_EXPORT_TOTAL,
    SENSOR_DAILY_IMPORT_GO,
    SENSOR_DAILY_IMPORT_STANDARD,
    SENSOR_DAILY_IMPORT_TOTAL,
    SENSOR_DATE,
    SENSOR_METER_EXPORT_MIDNIGHT,
    SENSOR_METER_IMPORT_0500,
    SENSOR_METER_IMPORT_MIDNIGHT,
    STORE_VERSION,
)
from .smgw_client import DailyData, SmgwClient, SmgwClientError

_LOGGER = logging.getLogger(__name__)


class SmgwTafCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for daily SMGW TAF data fetching.

    Uses async_track_time_change to trigger exactly at the configured
    time (default 00:15) instead of polling with update_interval.
    """

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        client: SmgwClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # No automatic polling
        )
        self.config_entry = config_entry
        self._client = client
        # Store per entry to avoid collisions (Fix #1)
        store_key = f"{DOMAIN}_{config_entry.entry_id}"
        self._store = Store(hass, STORE_VERSION, store_key)
        self._unsub_time_listener: callback | None = None

    async def async_setup(self) -> None:
        """Set up the coordinator: load stored data, schedule daily fetch."""
        # Load persisted data
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict):
            self.async_set_updated_data(stored)
            _LOGGER.debug(
                "Loaded stored data for date: %s",
                stored.get(SENSOR_DATE, "unknown"),
            )

        # Schedule the daily fetch
        self._schedule_daily_fetch()

        # If we have no data yet (first start), try an immediate fetch
        if not self.data:
            _LOGGER.info(
                "No stored data found - attempting initial data fetch"
            )
            try:
                await self._async_do_daily_fetch()
            except UpdateFailed as err:
                _LOGGER.warning(
                    "Initial fetch failed (will retry at scheduled time): %s",
                    err,
                )

    def _schedule_daily_fetch(self) -> None:
        """Register a time-based trigger for the daily data fetch."""
        # Unregister previous listener if any
        if self._unsub_time_listener:
            self._unsub_time_listener()

        time_str = self.config_entry.data.get(
            CONF_UPDATE_TIME, DEFAULT_UPDATE_TIME
        )
        parts = time_str.split(":")
        hour = int(parts[0]) if len(parts) > 0 else 0
        minute = int(parts[1]) if len(parts) > 1 else 15

        self._unsub_time_listener = async_track_time_change(
            self.hass,
            self._handle_daily_fetch,
            hour=hour,
            minute=minute,
            second=0,
        )

        _LOGGER.info(
            "Scheduled daily SMGW data fetch at %02d:%02d", hour, minute
        )

    async def _handle_daily_fetch(self, now: datetime) -> None:
        """Handle the scheduled daily fetch."""
        _LOGGER.info("Starting scheduled daily SMGW data fetch")
        try:
            await self._async_do_daily_fetch()
        except UpdateFailed as err:
            _LOGGER.error("Scheduled daily fetch failed: %s", err)

    async def _async_do_daily_fetch(self) -> None:
        """Perform the actual daily data fetch for yesterday."""
        # Use HA timezone-aware date (Fix #9)
        yesterday = dt_util.now().date() - timedelta(days=1)

        # Skip if we already have data for yesterday
        if (
            self.data
            and self.data.get(SENSOR_DATE) == yesterday.isoformat()
        ):
            _LOGGER.debug(
                "Already have data for %s, skipping fetch", yesterday
            )
            return

        try:
            daily_data = await self._client.async_fetch_daily_data(yesterday)
        except SmgwClientError as err:
            raise UpdateFailed(
                f"Failed to fetch SMGW data for {yesterday}: {err}"
            ) from err

        # Convert to dict for coordinator.data
        data = self._daily_data_to_dict(daily_data)

        # Persist to store
        await self._store.async_save(dict(data))

        _LOGGER.info(
            "Successfully fetched SMGW data for %s: "
            "Import total=%.4f kWh (Go=%.4f, Standard=%.4f), "
            "Export total=%.4f kWh",
            yesterday,
            daily_data.daily_import_total,
            daily_data.daily_import_go,
            daily_data.daily_import_standard,
            daily_data.daily_export_total,
        )

        # Update coordinator data (triggers sensor updates)
        self.async_set_updated_data(data)

    async def _async_update_data(self) -> dict[str, Any]:
        """Called for manual refreshes from the UI."""
        await self._async_do_daily_fetch()
        return self.data or {}

    @staticmethod
    def _daily_data_to_dict(daily_data: DailyData) -> dict[str, Any]:
        """Convert DailyData to a flat dict for coordinator.data."""
        return {
            SENSOR_DATE: daily_data.date.isoformat(),
            SENSOR_DAILY_IMPORT_TOTAL: daily_data.daily_import_total,
            SENSOR_DAILY_IMPORT_GO: daily_data.daily_import_go,
            SENSOR_DAILY_IMPORT_STANDARD: daily_data.daily_import_standard,
            SENSOR_DAILY_EXPORT_TOTAL: daily_data.daily_export_total,
            SENSOR_METER_IMPORT_MIDNIGHT: daily_data.import_midnight,
            SENSOR_METER_IMPORT_0500: daily_data.import_0500,
            SENSOR_METER_EXPORT_MIDNIGHT: daily_data.export_midnight,
        }

    async def async_unload(self) -> None:
        """Clean up on unload."""
        if self._unsub_time_listener:
            self._unsub_time_listener()
            self._unsub_time_listener = None
        await self._client.close()
