"""Constants for the SMGW TAF integration."""

DOMAIN = "smgw_taf"

# Config flow keys
CONF_URL = "url"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_UPDATE_HOUR = "update_hour"
CONF_UPDATE_MINUTE = "update_minute"
CONF_TAF7_PROFILE_NAME = "taf7_profile_name"

# Defaults
DEFAULT_URL = "https://192.168.100.100/cgi-bin/hanservice.cgi"
DEFAULT_UPDATE_HOUR = 0
DEFAULT_UPDATE_MINUTE = 15
DEFAULT_TAF7_PROFILE_NAME = "TAF7_OCT_B+E"

# OBIS codes
OBIS_IMPORT = "1-0:1.8.0"  # Verbrauch / Grid import
OBIS_EXPORT = "1-0:2.8.0"  # Einspeisung / Grid export

# Tariff boundary (hour, inclusive start of Standard tariff)
TARIFF_SWITCH_HOUR = 5  # Go: 00:00-04:59, Standard: 05:00-23:59

# Store
STORE_KEY = f"{DOMAIN}_data"
STORE_VERSION = 1

# Sensor keys (used in coordinator.data dict)
SENSOR_DAILY_IMPORT_TOTAL = "daily_import_total"
SENSOR_DAILY_IMPORT_GO = "daily_import_go"
SENSOR_DAILY_IMPORT_STANDARD = "daily_import_standard"
SENSOR_DAILY_EXPORT_TOTAL = "daily_export_total"
SENSOR_METER_IMPORT_MIDNIGHT = "meter_import_midnight"
SENSOR_METER_IMPORT_0500 = "meter_import_0500"
SENSOR_METER_EXPORT_MIDNIGHT = "meter_export_midnight"
SENSOR_DATE = "date"
