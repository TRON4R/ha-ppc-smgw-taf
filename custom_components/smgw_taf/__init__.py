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
    DOMAIN,
)
from .coordinator import SmgwTafCoordinator
from .smgw_client import SmgwClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: SmgwTafCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_unload()

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    ):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
