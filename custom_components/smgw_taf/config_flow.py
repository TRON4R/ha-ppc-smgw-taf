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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
    TimeSelectorConfig,
)

from .const import (
    CONF_METER_ID,
    CONF_PASSWORD,
    CONF_TARIFF_SWITCH_HOUR,
    CONF_TARIFF_SWITCH_MINUTE,
    CONF_UPDATE_TIME,
    CONF_URL,
    CONF_USERNAME,
    DEFAULT_TARIFF_SWITCH_HOUR,
    DEFAULT_TARIFF_SWITCH_MINUTE,
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

# Hour options: 0-23
HOUR_OPTIONS = [
    {"value": str(h), "label": f"{h:02d}"} for h in range(24)
]

# Minute options: 0, 15, 30, 45 (matching 15-minute meter resolution)
MINUTE_OPTIONS = [
    {"value": "0", "label": "00"},
    {"value": "15", "label": "15"},
    {"value": "30", "label": "30"},
    {"value": "45", "label": "45"},
]


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
                CONF_TARIFF_SWITCH_HOUR,
                default=str(d.get(CONF_TARIFF_SWITCH_HOUR, DEFAULT_TARIFF_SWITCH_HOUR)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=HOUR_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(
                CONF_TARIFF_SWITCH_MINUTE,
                default=str(d.get(CONF_TARIFF_SWITCH_MINUTE, DEFAULT_TARIFF_SWITCH_MINUTE)),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=MINUTE_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
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
        return SmgwTafOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Convert string values from dropdowns to int for storage
            user_input[CONF_TARIFF_SWITCH_HOUR] = int(
                user_input.get(CONF_TARIFF_SWITCH_HOUR, DEFAULT_TARIFF_SWITCH_HOUR)
            )
            user_input[CONF_TARIFF_SWITCH_MINUTE] = int(
                user_input.get(CONF_TARIFF_SWITCH_MINUTE, DEFAULT_TARIFF_SWITCH_MINUTE)
            )

            client = SmgwClient(
                base_url=user_input[CONF_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
            )

            try:
                device_info = await client.async_validate_and_get_device_info()
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except SmgwParseError as err:
                _LOGGER.error("SMGW validation failed: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                await self.async_set_unique_id(device_info.meter_id)
                self._abort_if_unique_id_configured()

                user_input[CONF_METER_ID] = device_info.meter_id

                host = SmgwClient.parse_host_from_url(user_input[CONF_URL])
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

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Convert string values from dropdowns to int for storage
            user_input[CONF_TARIFF_SWITCH_HOUR] = int(
                user_input.get(CONF_TARIFF_SWITCH_HOUR, DEFAULT_TARIFF_SWITCH_HOUR)
            )
            user_input[CONF_TARIFF_SWITCH_MINUTE] = int(
                user_input.get(CONF_TARIFF_SWITCH_MINUTE, DEFAULT_TARIFF_SWITCH_MINUTE)
            )

            new_data = {**self.config_entry.data, **user_input}

            client = SmgwClient(
                base_url=new_data[CONF_URL],
                username=new_data[CONF_USERNAME],
                password=new_data[CONF_PASSWORD],
            )

            try:
                device_info = await client.async_validate_and_get_device_info()
                old_meter_id = self.config_entry.data.get(CONF_METER_ID)
                if old_meter_id and device_info.meter_id != old_meter_id:
                    _LOGGER.warning(
                        "Meter ID changed from %s to %s - this may indicate "
                        "a different physical meter. Updating entry.",
                        old_meter_id,
                        device_info.meter_id,
                    )
                new_data[CONF_METER_ID] = device_info.meter_id
            except SmgwAuthError:
                errors["base"] = "invalid_auth"
            except SmgwConnectionError:
                errors["base"] = "cannot_connect"
            except SmgwParseError as err:
                _LOGGER.error("SMGW validation failed: %s", err)
                errors["base"] = "unknown"
            except Exception:
                _LOGGER.exception("Unexpected error during connection test")
                errors["base"] = "unknown"
            finally:
                await client.close()

            if not errors:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=new_data,
                )
                await self.hass.config_entries.async_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(dict(self.config_entry.data)),
            errors=errors,
        )
