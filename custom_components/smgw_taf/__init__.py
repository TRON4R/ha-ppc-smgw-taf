"""The SMGW TAF integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
)
from .coordinator import SmgwTafCoordinator
from .smgw_client import SmgwClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type SmgwTafConfigEntry = ConfigEntry[SmgwTafCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: SmgwTafConfigEntry
) -> bool:
    """Set up SMGW TAF from a config entry."""
    client = SmgwClient(
        base_url=entry.data[CONF_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
    )

    coordinator = SmgwTafCoordinator(hass, entry, client)
    await coordinator.async_setup()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    config_entry: SmgwTafConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removal of a device from the UI."""
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmgwTafConfigEntry
) -> bool:
    """Unload a config entry.

    Platforms are unloaded first, then the coordinator is cleaned up.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )

    if unload_ok:
        await entry.runtime_data.async_unload()

    return unload_ok
