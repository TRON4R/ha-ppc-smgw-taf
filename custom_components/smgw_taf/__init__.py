"""The SMGW TAF integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import (
    CONF_PASSWORD,
    CONF_TAF7_PROFILE_NAME,
    CONF_URL,
    CONF_USERNAME,
    DEFAULT_TAF7_PROFILE_NAME,
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
        taf7_profile_name=entry.data.get(
            CONF_TAF7_PROFILE_NAME, DEFAULT_TAF7_PROFILE_NAME
        ),
    )

    coordinator = SmgwTafCoordinator(hass, entry, client)
    await coordinator.async_setup()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SmgwTafConfigEntry
) -> bool:
    """Unload a config entry."""
    await entry.runtime_data.async_unload()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
