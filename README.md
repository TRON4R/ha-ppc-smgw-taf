# ha-ppc-smgw-taf

<img src="custom_components/smgw_taf/brand/icon.png" alt="SMGW Icon" width="128" align="left" style="margin-right: 16px;">

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

Home Assistant custom integration for reading **certified daily meter values** from PPC Smart Meter Gateways via the HAN interface.

<br clear="left">

## What it does

This integration connects to your PPC SMGW once per day and retrieves the official, calibration-grade daily meter readings from the TAF7 evaluation profile. It calculates:

- **Daily grid import (total)** — total electricity consumed
- **Daily grid import (Go tariff)** — consumption during the reduced-rate period (default: 00:00–04:59)
- **Daily grid import (Standard tariff)** — consumption during the standard-rate period (default: 05:00–23:59)
- **Daily grid export (total)** — total electricity fed back to grid

All sensors are compatible with the Home Assistant **Energy Dashboard**.

## How does this differ from ha-ppc-smgw?

The existing [ha-ppc-smgw](https://github.com/jannickfahlbusch/ha-ppc-smgw) integration polls current meter readings at fix 10 minute intervals (ignoring the respective setting). Some users have reported being locked out of their SMGW due to the high frequency of requests. This integration takes a different approach:

- **One fetch per day** (5 HTTP requests total, at a configurable time)
- **Certified values** from TAF7 interval readings (not live meter snapshots)
- **Accurate tariff split** using the exact meter reading at the configurable tariff switch time from the SMGW
- **No timing issues** — values come from the SMGW's own daily boundaries, not HA's clock

## Requirements

- PPC Smart Meter Gateway with HAN interface enabled
- HAN credentials (username + password) from your electricity provider
- A TAF7 evaluation profile configured in the SMGW (e.g., "TAF7_OCT_B+E")

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Go to Integrations → three-dot menu → Custom repositories
3. Add `https://github.com/TRON4R/ha-ppc-smgw-taf` as an Integration
4. Install "PPC SMGW TAF Daily Import"
5. Restart Home Assistant

### Manual

1. Copy `custom_components/smgw_taf/` to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings → Devices & Services → Add Integration
2. Search for "PPC SMGW"
3. Enter:
   - **URL**: Your SMGW HAN interface URL (default: `https://192.168.100.100/cgi-bin/hanservice.cgi`)
   - **Username** and **Password**: Your HAN credentials
   - **TAF7 profile name**: The name of your TAF7 evaluation profile (default: `TAF7_OCT_B+E`)
   - **Standard tariff start time**: When the standard tariff begins (default: 05:00, configurable)
   - **Fetch time**: Time of the daily data fetch (default: 00:15)

## Sensors

| Sensor | Description | Device Class | State Class |
|---|---|---|---|
| Daily consumption total | Yesterday's total consumption | `energy` | `total` |
| Daily consumption slot 1 | Consumption during slot 1 (midnight → tariff switch) | `energy` | `total` |
| Daily consumption slot 2 | Consumption during slot 2 (tariff switch → midnight) | `energy` | `total` |
| Daily feed-in total | Yesterday's total feed-in | `energy` | `total` |
| Meter consumption previous day closing | Absolute reading at start of day (00:00) | `energy` | `total_increasing` |
| Meter consumption tariff switch 1 | Absolute reading at tariff switch time | `energy` | `total_increasing` |
| Meter feed-in previous day closing | Absolute export reading at start of day (00:00) | `energy` | `total_increasing` |
| Daily date | Date of the last fetched data | `date` | — |

The meter reading sensors are disabled by default and can be enabled in the entity settings if needed.

## Intended use case

This integration was developed for the **Octopus Energy Go tariff** in Germany, which offers a reduced electricity rate between **00:00 and 04:59:59** (Go tariff) and a standard rate from **05:00 to 23:59:59**. The tariff split time is configurable. If you are using a very different tariff structure or a totally different tariff switch time, please [open an issue](https://github.com/TRON4R/ha-ppc-smgw-taf/issues) or better a [pull request](https://github.com/TRON4R/ha-ppc-smgw-taf/pulls) to discuss how to make this work for your setup.

## License

MIT License — see [LICENSE](LICENSE) for details.
