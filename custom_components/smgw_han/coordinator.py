"""Data coordinator for SMGW HAN integration."""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_TARIFF_SWITCH_HOUR,
    CONF_TARIFF_SWITCH_MINUTE,
    CONF_UPDATE_TIME,
    DEFAULT_TARIFF_SWITCH_HOUR,
    DEFAULT_TARIFF_SWITCH_MINUTE,
    DEFAULT_UPDATE_TIME,
    DOMAIN,
    SENSOR_DAILY_CONSUMPTION_SLOT_1,
    SENSOR_DAILY_CONSUMPTION_SLOT_2,
    SENSOR_DAILY_CONSUMPTION_TOTAL,
    SENSOR_DAILY_FEEDIN_TOTAL,
    SENSOR_DATE,
    SENSOR_METER_CONSUMPTION_PREV_DAY_CLOSE,
    SENSOR_METER_CONSUMPTION_SWITCH_1,
    SENSOR_METER_FEEDIN_PREV_DAY_CLOSE,
    STORE_VERSION,
)
from .smgw_client import DailyData, SmgwAuthError, SmgwClient, SmgwClientError

_LOGGER = logging.getLogger(__name__)



class SmgwTafCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for daily SMGW HAN data fetching.

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
        # Store per entry to avoid collisions
        store_key = f"{DOMAIN}_{config_entry.entry_id}"
        self._store = Store(hass, STORE_VERSION, store_key)
        self._unsub_time_listener: CALLBACK_TYPE | None = None

    async def async_setup(self) -> None:
        """Set up the coordinator: load stored data, schedule daily fetch."""
        # Load persisted data (NotImplementedError = version mismatch, discard)
        try:
            stored = await self._store.async_load()
        except NotImplementedError:
            _LOGGER.info(
                "Stored data version incompatible with current version %d"
                " - discarding and refetching",
                STORE_VERSION,
            )
            await self._store.async_remove()
            stored = None
        if stored and isinstance(stored, dict):
            self.async_set_updated_data(stored)
            _LOGGER.debug(
                "Loaded stored data for date: %s",
                stored.get(SENSOR_DATE, "unknown"),
            )

        # Schedule the daily fetch
        self._schedule_daily_fetch()

        # Check if we need to fetch: either no data at all, or stale data,
        # or tariff time has changed since last fetch
        yesterday = dt_util.now().date() - timedelta(days=1)
        stored_date = self.data.get(SENSOR_DATE) if self.data else None
        needs_fetch = False

        if not self.data:
            _LOGGER.info(
                "No stored data found - attempting initial data fetch"
            )
            needs_fetch = True
        elif stored_date != yesterday.isoformat():
            _LOGGER.info(
                "Stored data is for %s but yesterday is %s - fetching update",
                stored_date,
                yesterday,
            )
            needs_fetch = True
        else:
            # Check if tariff time has changed since last stored data
            current_tariff = (
                int(self.config_entry.data.get(
                    CONF_TARIFF_SWITCH_HOUR, DEFAULT_TARIFF_SWITCH_HOUR
                )),
                int(self.config_entry.data.get(
                    CONF_TARIFF_SWITCH_MINUTE, DEFAULT_TARIFF_SWITCH_MINUTE
                )),
            )
            stored_tariff = (
                self.data.get("_tariff_hour"),
                self.data.get("_tariff_minute"),
            )
            if stored_tariff != current_tariff:
                _LOGGER.info(
                    "Tariff time changed from %s to %s - refetching data",
                    stored_tariff,
                    current_tariff,
                )
                needs_fetch = True

        if needs_fetch:
            try:
                await self._async_do_daily_fetch()
            except UpdateFailed as err:
                _LOGGER.warning(
                    "Startup fetch failed (will retry at scheduled time): %s",
                    err,
                )

    def _schedule_daily_fetch(self) -> None:
        """Register a time-based trigger for the daily data fetch."""
        if self._unsub_time_listener:
            self._unsub_time_listener()

        time_str = self.config_entry.data.get(
            CONF_UPDATE_TIME, DEFAULT_UPDATE_TIME
        )
        try:
            fetch_time = time.fromisoformat(time_str)
        except ValueError:
            _LOGGER.warning(
                "Invalid time format '%s', falling back to 00:15", time_str
            )
            fetch_time = time(0, 15)

        self._unsub_time_listener = async_track_time_change(
            self.hass,
            self._handle_daily_fetch,
            hour=fetch_time.hour,
            minute=fetch_time.minute,
            second=0,
        )

        _LOGGER.info(
            "Scheduled daily SMGW data fetch at %02d:%02d",
            fetch_time.hour,
            fetch_time.minute,
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
        yesterday = dt_util.now().date() - timedelta(days=1)

        # Skip if we already have data for yesterday with same tariff time
        tariff_hour = int(self.config_entry.data.get(
            CONF_TARIFF_SWITCH_HOUR, DEFAULT_TARIFF_SWITCH_HOUR
        ))
        tariff_minute = int(self.config_entry.data.get(
            CONF_TARIFF_SWITCH_MINUTE, DEFAULT_TARIFF_SWITCH_MINUTE
        ))

        if (
            self.data
            and self.data.get(SENSOR_DATE) == yesterday.isoformat()
            and self.data.get("_tariff_hour") == tariff_hour
            and self.data.get("_tariff_minute") == tariff_minute
        ):
            _LOGGER.debug(
                "Already have data for %s, skipping fetch", yesterday
            )
            return

        try:
            daily_data = await self._client.async_fetch_daily_data(
                yesterday,
                tariff_switch_hour=tariff_hour,
                tariff_switch_minute=tariff_minute,
            )
        except SmgwAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except SmgwClientError as err:
            raise UpdateFailed(
                f"Failed to fetch SMGW data for {yesterday}: {err}"
            ) from err

        data = self._daily_data_to_dict(daily_data)

        # Store tariff time alongside data for change detection
        data["_tariff_hour"] = tariff_hour
        data["_tariff_minute"] = tariff_minute

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
        return self.data if self.data is not None else {}

    @staticmethod
    def _daily_data_to_dict(daily_data: DailyData) -> dict[str, Any]:
        """Convert DailyData to a flat dict for coordinator.data."""
        return {
            SENSOR_DATE: daily_data.date.isoformat(),
            SENSOR_DAILY_CONSUMPTION_TOTAL: daily_data.daily_import_total,
            SENSOR_DAILY_CONSUMPTION_SLOT_1: daily_data.daily_import_go,
            SENSOR_DAILY_CONSUMPTION_SLOT_2: daily_data.daily_import_standard,
            SENSOR_DAILY_FEEDIN_TOTAL: daily_data.daily_export_total,
            SENSOR_METER_CONSUMPTION_PREV_DAY_CLOSE: daily_data.import_midnight,
            SENSOR_METER_CONSUMPTION_SWITCH_1: daily_data.import_tariff_switch,
            SENSOR_METER_FEEDIN_PREV_DAY_CLOSE: daily_data.export_midnight,
        }

    async def async_unload(self) -> None:
        """Clean up on unload."""
        if self._unsub_time_listener:
            self._unsub_time_listener()
            self._unsub_time_listener = None
        await self._client.close()
