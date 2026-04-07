"""Constants for the SMGW HAN integration."""

DOMAIN = "smgw_han"

# Config flow keys
CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_TIME = "update_time"
CONF_TARIFF_SWITCH_HOUR = "tariff_switch_hour"
CONF_TARIFF_SWITCH_MINUTE = "tariff_switch_minute"
CONF_METER_ID = "meter_id"  # Parsed from SMGW during setup

# Defaults
DEFAULT_URL = "https://192.168.100.100/cgi-bin/hanservice.cgi"
DEFAULT_UPDATE_TIME = "00:15:00"
DEFAULT_TARIFF_SWITCH_HOUR = 5
DEFAULT_TARIFF_SWITCH_MINUTE = 0

# OBIS codes
OBIS_IMPORT = "1-0:1.8.0"  # Verbrauch / Grid import
OBIS_EXPORT = "1-0:2.8.0"  # Einspeisung / Grid export

# Store
STORE_VERSION = 4

# Sensor keys (used in coordinator.data dict)
SENSOR_DAILY_CONSUMPTION_TOTAL = "daily_consumption_total"
SENSOR_DAILY_CONSUMPTION_SLOT_1 = "daily_consumption_slot_1"
SENSOR_DAILY_CONSUMPTION_SLOT_2 = "daily_consumption_slot_2"
SENSOR_DAILY_FEEDIN_TOTAL = "daily_feedin_total"
SENSOR_METER_CONSUMPTION_PREV_DAY_CLOSE = "meter_consumption_prev_day_close"
SENSOR_METER_CONSUMPTION_SWITCH_1 = "meter_consumption_switch_1"
SENSOR_METER_FEEDIN_PREV_DAY_CLOSE = "meter_feedin_prev_day_close"
SENSOR_DATE = "date"
