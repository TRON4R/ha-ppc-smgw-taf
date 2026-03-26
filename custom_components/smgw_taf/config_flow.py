"""Config flow for SMGW TAF integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_URL
from homeassistant.core import callback

from .const import (
    CONF_PASSWORD,
    CONF_TAF7_PROFILE_NAME,
    CONF_UPDATE_HOUR,
    CONF_UPDATE_MINUTE,
    CONF_USERNAME,
    DEFAULT_TAF7_PROFILE_NAME,
    DEFAULT_UPDATE_HOUR,
    DEFAULT_UPDATE_MINUTE,
    DEFAULT_URL,
    DOMAIN,
)
from .smgw_client import SmgwAuthError, SmgwClient, SmgwConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL, default=DEFAULT_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(
            CONF_TAF7_PROFILE_NAME, default=DEFAULT_TAF7_PROFILE_NAME
        ): str,
        vol.Optional(
            CONF_UPDATE_HOUR, default=DEFAULT_UPDATE_HOUR
        ): vol.All(int, vol.Range(min=0, max=23)),
        vol.Optional(
            CONF_UPDATE_MINUTE, default=DEFAULT_UPDATE_MINUTE
        ): vol.All(int, vol.Range(min=0, max=59)),
    }
)


class SmgwTafConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SMGW TAF."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SmgwTafOptionsFlow:
        """Get the options flow for this handler."""
        return SmgwTafOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Test connection
            client = SmgwClient(
                base_url=user_input[CONF_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                taf7_profile_name=user_input[CONF_TAF7_PROFILE_NAME],
            )

            try:
                can_connect = await client.async_test_connection()
                if not can_connect:
                    errors["base"] = "cannot_connect"
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                # Prevent duplicate entries for the same SMGW
                await self.async_set_unique_id(user_input[CONF_URL])
                self._abort_if_unique_id_configured()

                title = f"PPC SMGW ({user_input[CONF_URL].split('//')[1].split('/')[0]})"
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class SmgwTafOptionsFlow(OptionsFlow):
    """Handle options flow for SMGW TAF."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Merge new values into existing config data
            new_data = {**self._config_entry.data, **user_input}

            # Test connection with new credentials
            client = SmgwClient(
                base_url=new_data[CONF_URL],
                username=new_data[CONF_USERNAME],
                password=new_data[CONF_PASSWORD],
                taf7_profile_name=new_data[CONF_TAF7_PROFILE_NAME],
            )

            try:
                can_connect = await client.async_test_connection()
                if not can_connect:
                    errors["base"] = "cannot_connect"
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                # Update the config entry data
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                )
                return self.async_create_entry(title="", data={})

        # Pre-fill with current values
        current = self._config_entry.data
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_URL, default=current.get(CONF_URL, DEFAULT_URL)
                ): str,
                vol.Required(
                    CONF_USERNAME, default=current.get(CONF_USERNAME, "")
                ): str,
                vol.Required(
                    CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")
                ): str,
                vol.Optional(
                    CONF_TAF7_PROFILE_NAME,
                    default=current.get(
                        CONF_TAF7_PROFILE_NAME, DEFAULT_TAF7_PROFILE_NAME
                    ),
                ): str,
                vol.Optional(
                    CONF_UPDATE_HOUR,
                    default=current.get(CONF_UPDATE_HOUR, DEFAULT_UPDATE_HOUR),
                ): vol.All(int, vol.Range(min=0, max=23)),
                vol.Optional(
                    CONF_UPDATE_MINUTE,
                    default=current.get(
                        CONF_UPDATE_MINUTE, DEFAULT_UPDATE_MINUTE
                    ),
                ): vol.All(int, vol.Range(min=0, max=59)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )
