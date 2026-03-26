"""Constants for the SMGW TAF integration."""

DOMAIN = "smgw_taf"

# Config flow keys
CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_TIME = "update_time"
CONF_TARIFF_SWITCH_TIME = "tariff_switch_time"
CONF_TAF7_PROFILE_NAME = "taf7_profile_name"
CONF_METER_ID = "meter_id"  # Parsed from SMGW during setup

# Defaults
DEFAULT_URL = "https://192.168.100.100/cgi-bin/hanservice.cgi"
DEFAULT_UPDATE_TIME = "00:15:00"
DEFAULT_TARIFF_SWITCH_TIME = "05:00:00"
DEFAULT_TAF7_PROFILE_NAME = "TAF7_OCT_B+E"

# OBIS codes
OBIS_IMPORT = "1-0:1.8.0"  # Verbrauch / Grid import
OBIS_EXPORT = "1-0:2.8.0"  # Einspeisung / Grid export

# Store
# Bumped to 2 in v1.1.0: sensor keys were renamed (meter_import_midnight →
# meter_import_prev_day_close, meter_import_0500 → meter_import_tariff_1,
# meter_export_midnight → meter_export_prev_day_close). HA's Store discards
# data from older versions, triggering a fresh fetch with the new key schema.
STORE_VERSION = 2

# Sensor keys (used in coordinator.data dict)
SENSOR_DAILY_IMPORT_TOTAL = "daily_import_total"
SENSOR_DAILY_IMPORT_GO = "daily_import_go"
SENSOR_DAILY_IMPORT_STANDARD = "daily_import_standard"
SENSOR_DAILY_EXPORT_TOTAL = "daily_export_total"
SENSOR_METER_IMPORT_PREV_DAY_CLOSE = "meter_import_prev_day_close"
SENSOR_METER_IMPORT_TARIFF_1 = "meter_import_tariff_1"
SENSOR_METER_EXPORT_PREV_DAY_CLOSE = "meter_export_prev_day_close"
SENSOR_DATE = "date"
