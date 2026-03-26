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
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
    TimeSelectorConfig,
)

from .const import (
    CONF_METER_ID,
    CONF_PASSWORD,
    CONF_TAF7_PROFILE_NAME,
    CONF_UPDATE_TIME,
    CONF_URL,
    CONF_USERNAME,
    DEFAULT_TAF7_PROFILE_NAME,
    DEFAULT_UPDATE_TIME,
    DEFAULT_URL,
    DOMAIN,
)
from .smgw_client import (
    SmgwAuthError,
    SmgwClient,
    SmgwConnectionError,
    SmgwParseError,
)

_LOGGER = logging.getLogger(__name__)


def _build_schema(
    defaults: dict[str, Any] | None = None,
) -> vol.Schema:
    """Build the data schema with optional defaults."""
    d = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_URL, default=d.get(CONF_URL, DEFAULT_URL)
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
            vol.Required(
                CONF_USERNAME, default=d.get(CONF_USERNAME, "")
            ): TextSelector(
                TextSelectorConfig(autocomplete="username")
            ),
            vol.Required(
                CONF_PASSWORD, default=d.get(CONF_PASSWORD, "")
            ): TextSelector(
                TextSelectorConfig(
                    type=TextSelectorType.PASSWORD,
                    autocomplete="current-password",
                )
            ),
            vol.Optional(
                CONF_TAF7_PROFILE_NAME,
                default=d.get(CONF_TAF7_PROFILE_NAME, DEFAULT_TAF7_PROFILE_NAME),
            ): str,
            vol.Optional(
                CONF_UPDATE_TIME,
                default=d.get(CONF_UPDATE_TIME, DEFAULT_UPDATE_TIME),
            ): TimeSelector(TimeSelectorConfig()),
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
            client = SmgwClient(
                base_url=user_input[CONF_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                taf7_profile_name=user_input[CONF_TAF7_PROFILE_NAME],
            )

            try:
                # Full validation: login + TAF7 profile + meter ID (Fix #4)
                device_info = await client.async_validate_and_get_device_info()
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except SmgwParseError as err:
                _LOGGER.error("TAF7 profile validation failed: %s", err)
                errors["base"] = "invalid_profile"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                # Use meter_id as unique_id (Fix #3)
                await self.async_set_unique_id(device_info.meter_id)
                self._abort_if_unique_id_configured()

                # Store meter_id and firmware in config data
                user_input[CONF_METER_ID] = device_info.meter_id

                host = user_input[CONF_URL].split("//")[1].split("/")[0]
                return self.async_create_entry(
                    title=f"PPC SMGW ({host})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(),
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
            new_data = {**self._config_entry.data, **user_input}

            client = SmgwClient(
                base_url=new_data[CONF_URL],
                username=new_data[CONF_USERNAME],
                password=new_data[CONF_PASSWORD],
                taf7_profile_name=new_data[CONF_TAF7_PROFILE_NAME],
            )

            try:
                device_info = await client.async_validate_and_get_device_info()
                new_data[CONF_METER_ID] = device_info.meter_id
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except SmgwParseError as err:
                _LOGGER.error("TAF7 profile validation failed: %s", err)
                errors["base"] = "invalid_profile"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data=new_data,
                )
                # Reload the integration to apply changes (Fix #2)
                await self.hass.config_entries.async_reload(
                    self._config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(dict(self._config_entry.data)),
            errors=errors,
        )
