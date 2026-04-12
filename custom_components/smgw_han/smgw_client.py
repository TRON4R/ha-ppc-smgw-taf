"""Client for communicating with PPC Smart Meter Gateway via HAN interface."""

from __future__ import annotations

import logging
import re
import urllib.parse
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from .const import OBIS_EXPORT, OBIS_IMPORT

_LOGGER = logging.getLogger(__name__)


class SmgwClientError(Exception):
    """Base exception for SMGW client errors."""


class SmgwAuthError(SmgwClientError):
    """Authentication error."""


class SmgwConnectionError(SmgwClientError):
    """Connection error."""


class SmgwParseError(SmgwClientError):
    """HTML parsing error."""


@dataclass
class MeterReading:
    """A single meter reading from the SMGW."""

    timestamp: datetime
    obis_code: str
    value: float
    unit: str
    quality: str


@dataclass
class SmgwDeviceInfo:
    """Device information parsed from the SMGW."""

    meter_id: str  # e.g. "1lgz0072999211"
    firmware_version: str  # e.g. "00861-34788"


@dataclass
class DailyData:
    """Processed daily meter data."""

    date: date
    import_midnight: float
    import_tariff_switch: float
    import_next_midnight: float
    export_midnight: float
    export_next_midnight: float
    daily_import_total: float
    daily_import_go: float
    daily_import_standard: float
    daily_export_total: float
    raw_readings: list[MeterReading] = field(default_factory=list)


class SmgwClient:
    """Client for PPC SMGW HAN interface."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
    ) -> None:
        """Initialize the SMGW client."""
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                verify=False,  # SMGW uses self-signed certificates
                timeout=30.0,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _login(self) -> str:
        """Log in to the SMGW and obtain session cookie + CSRF token.

        Returns the login page HTML for further parsing (e.g. firmware).
        All httpx exceptions are wrapped into SmgwClientError subtypes.
        """
        client = await self._get_client()
        try:
            response = await client.get(
                self._base_url,
                auth=httpx.DigestAuth(self._username, self._password),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            if err.response.status_code in (401, 403):
                raise SmgwAuthError(
                    f"Authentication failed: {err.response.status_code}"
                ) from err
            raise SmgwConnectionError(
                f"HTTP error during login: {err.response.status_code}"
            ) from err
        except (httpx.ConnectError, httpx.RemoteProtocolError) as err:
            raise SmgwConnectionError(
                f"Cannot connect to SMGW at {self._base_url}: {err}"
            ) from err
        except httpx.TimeoutException as err:
            raise SmgwConnectionError(
                f"Timeout connecting to SMGW: {err}"
            ) from err
        except httpx.RequestError as err:
            # Catch-all for any other httpx request errors
            raise SmgwConnectionError(
                f"Request error during login: {err}"
            ) from err

        self._token = self._parse_token(response.text)
        if not self._token:
            raise SmgwParseError("Could not extract CSRF token from login page")

        _LOGGER.debug("SMGW login successful, token obtained")
        return response.text

    async def _post(self, data: dict) -> str:
        """Send a POST request with the current session.

        All httpx exceptions are wrapped into SmgwClientError subtypes.
        """
        if not self._token:
            raise SmgwClientError("Not logged in - no CSRF token available")

        client = await self._get_client()
        post_data = {"tkn": self._token, **data}

        try:
            response = await client.post(
                self._base_url,
                data=post_data,
                auth=httpx.DigestAuth(self._username, self._password),
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as err:
            raise SmgwConnectionError(
                f"HTTP error: {err.response.status_code}"
            ) from err
        except (httpx.ConnectError, httpx.RemoteProtocolError) as err:
            raise SmgwConnectionError(
                f"Connection lost during request: {err}"
            ) from err
        except httpx.TimeoutException as err:
            raise SmgwConnectionError(
                f"Timeout during request: {err}"
            ) from err
        except httpx.RequestError as err:
            raise SmgwConnectionError(
                f"Request error: {err}"
            ) from err

        new_token = self._parse_token(response.text)
        if new_token:
            self._token = new_token

        return response.text

    async def _logout(self) -> None:
        """Log out from the SMGW."""
        try:
            await self._post({"action": "logout"})
            _LOGGER.debug("SMGW logout successful")
        except SmgwClientError:
            _LOGGER.debug("Logout failed (non-critical)")
        finally:
            await self.close()
            self._token = None

    def _parse_token(self, html: str) -> str | None:
        """Extract CSRF token from HTML hidden input field.

        Improved regex fallback to handle any attribute order.
        """
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "tkn"})
        if token_input and token_input.get("value"):
            return token_input["value"]
        # Fallback regex: match name=tkn and value= in any order
        match = re.search(
            r'<input[^>]*name=["\']tkn["\'][^>]*value=["\']([^"\']+)["\']',
            html,
        )
        if match:
            return match.group(1)
        # Try reversed order (value before name)
        match = re.search(
            r'<input[^>]*value=["\']([^"\']+)["\'][^>]*name=["\']tkn["\']',
            html,
        )
        return match.group(1) if match else None

    @staticmethod
    def _parse_firmware(html: str) -> str:
        """Extract firmware version from the footer."""
        soup = BeautifulSoup(html, "html.parser")
        fw_div = soup.find("p", id="div_fwversion")
        if fw_div:
            return fw_div.get_text(strip=True)
        return "unknown"

    @staticmethod
    def parse_host_from_url(url: str) -> str:
        """Safely extract host from URL."""
        try:
            parsed = urllib.parse.urlparse(url)
            return parsed.hostname or "unknown"
        except Exception:
            return "unknown"

    async def _navigate_to_meter(self) -> tuple[str, str]:
        """Navigate to the meter page and return (mid, meter_id).

        Fetches the meterform page and extracts the session mid and the
        physical meter ID from the dropdown option text, e.g.:
        "01005e318002.1lgz0072999211.sm" → meter_id "1lgz0072999211"
        """
        html = await self._post({"action": "meterform"})
        soup = BeautifulSoup(html, "html.parser")

        select = soup.find("select", id="meterform_select_meter")
        if not select:
            select = soup.find("select", {"name": "mid"})
        if not select:
            raise SmgwParseError("Could not find meter dropdown in meterform")

        option = select.find("option")
        if not option:
            raise SmgwParseError("No meter found in meter dropdown")

        mid = option.get("value")
        if not mid:
            raise SmgwParseError("Could not extract mid from meter dropdown")

        # Strip trailing ".sm", then take the last dot-separated segment
        option_text = option.get_text(strip=True)
        meter_id = option_text.removesuffix(".sm").rsplit(".", 1)[-1]
        if not meter_id:
            raise SmgwParseError(
                f"Could not extract meter ID from dropdown text: {option_text}"
            )

        _LOGGER.debug("Found meter mid=%s, meter_id=%s", mid, meter_id)
        return mid, meter_id

    async def _get_meter_values_mid(self, mid: str) -> str:
        """Get the session mid needed for showMeterValues requests.

        The mid from the meter dropdown is not directly usable for data
        requests — a fresh mid is issued by the showMeterValuesForm page.
        """
        html = await self._post({"action": "showMeterValuesForm", "mid": mid})
        soup = BeautifulSoup(html, "html.parser")

        # Prefer the mid inside the data form specifically
        form = soup.find("form", {"name": "input_metervalues"})
        if form:
            mid_input = form.find("input", {"name": "mid", "type": "hidden"})
        else:
            mid_input = soup.find("input", {"name": "mid", "type": "hidden"})

        if not mid_input or not mid_input.get("value"):
            raise SmgwParseError(
                "Could not find hidden mid in showMeterValuesForm"
            )

        values_mid = mid_input["value"]
        _LOGGER.debug("Got meter values mid=%s", values_mid)
        return values_mid

    def _parse_meter_values_table(self, html: str) -> list[MeterReading]:
        """Parse the Zählerstand HTML table into MeterReading objects.

        Rows come in pairs: line1 (import, with timestamp) followed by
        line2 (export, timestamp cell empty — inherits line1 timestamp).
        Values are plain text in <td> cells, not in <input> buttons.
        Data is in descending chronological order.
        """
        soup = BeautifulSoup(html, "html.parser")
        readings: list[MeterReading] = []

        table = soup.find("table", id="metervalue")
        if not table:
            _LOGGER.warning("No meter values table found in HTML response")
            return readings

        rows = table.find_all(
            "tr", id=lambda x: x and x.startswith("table_metervalues_line")
        )
        if not rows:
            _LOGGER.warning("No meter value rows found in table")
            return readings

        last_timestamp: datetime | None = None

        for row in rows:
            ts_td = row.find("td", id="table_metervalues_col_timestamp")
            value_td = row.find("td", id="table_metervalues_col_wert")
            unit_td = row.find("td", id="table_metervalues_col_einheit")
            obis_td = row.find("td", id="table_metervalues_col_obis")

            # Update running timestamp when a new one appears (line1 rows only)
            if ts_td:
                ts_str = ts_td.get_text(strip=True)
                if ts_str:
                    try:
                        last_timestamp = datetime.strptime(
                            ts_str, "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError:
                        _LOGGER.debug("Cannot parse timestamp: %s", ts_str)

            if not all([value_td, obis_td, last_timestamp]):
                continue

            obis_str = obis_td.get_text(strip=True)
            if obis_str not in (OBIS_IMPORT, OBIS_EXPORT):
                continue

            value_str = value_td.get_text(strip=True)
            unit_str = unit_td.get_text(strip=True) if unit_td else "kWh"

            try:
                readings.append(
                    MeterReading(
                        timestamp=last_timestamp,
                        obis_code=obis_str,
                        value=float(value_str),
                        unit=unit_str,
                        quality="valid",
                    )
                )
            except (ValueError, TypeError) as err:
                _LOGGER.debug("Skipping unparseable row: %s", err)

        _LOGGER.debug(
            "Parsed %d meter readings from Zählerstand data", len(readings)
        )
        return readings

    async def async_validate_and_get_device_info(self) -> SmgwDeviceInfo:
        """Validate connection and return device info."""
        try:
            login_html = await self._login()
            firmware = self._parse_firmware(login_html)

            _mid, meter_id = await self._navigate_to_meter()

            _LOGGER.info(
                "SMGW validated: meter_id=%s, firmware=%s",
                meter_id,
                firmware,
            )

            return SmgwDeviceInfo(
                meter_id=meter_id,
                firmware_version=firmware,
            )
        finally:
            await self._logout()

    async def async_fetch_daily_data(
        self,
        target_date: date,
        tariff_switch_hour: int = 5,
        tariff_switch_minute: int = 0,
    ) -> DailyData:
        """Fetch and process daily data for a given date."""
        try:
            await self._login()

            mid_dropdown, _meter_id = await self._navigate_to_meter()
            mid = await self._get_meter_values_mid(mid_dropdown)

            next_day = target_date + timedelta(days=1)
            # Use explicit datetime strings matching the SMGW form format.
            # to includes 00:15:00 of next_day to safely capture the 00:00:01
            # closing reading within the 7-minute tolerance window.
            from_str = target_date.strftime("%Y-%m-%d") + " 00:00:00"
            to_str = next_day.strftime("%Y-%m-%d") + " 00:15:00"

            _LOGGER.debug(
                "Fetching Zählerstand data from %s to %s", from_str, to_str
            )

            html = await self._post(
                {
                    "action": "showMeterValues",
                    "mid": mid,
                    "from": from_str,
                    "to": to_str,
                }
            )

            all_readings = self._parse_meter_values_table(html)

            if not all_readings:
                raise SmgwParseError(
                    f"No meter readings found for {target_date}"
                )

            return self._process_readings(
                target_date, all_readings,
                tariff_switch_hour, tariff_switch_minute,
            )

        finally:
            await self._logout()

    def _process_readings(
        self,
        target_date: date,
        readings: list[MeterReading],
        tariff_switch_hour: int = 5,
        tariff_switch_minute: int = 0,
    ) -> DailyData:
        """Process raw readings into DailyData with tariff calculations.

        Finds the reading closest to the target time (hour:minute) within
        a tolerance window of +/- 7 minutes to match the 15-minute grid.
        """
        next_day = target_date + timedelta(days=1)

        import_readings = [r for r in readings if r.obis_code == OBIS_IMPORT]
        export_readings = [r for r in readings if r.obis_code == OBIS_EXPORT]

        def find_closest_value(
            meter_readings: list[MeterReading],
            target_dt: datetime,
            tolerance_minutes: int = 7,
        ) -> float | None:
            """Find reading closest to target_dt within tolerance."""
            best: MeterReading | None = None
            best_delta = timedelta.max
            for r in meter_readings:
                delta = abs(r.timestamp - target_dt)
                if (
                    delta <= timedelta(minutes=tolerance_minutes)
                    and delta < best_delta
                ):
                    best = r
                    best_delta = delta
            return best.value if best else None

        # Target timestamps
        midnight_start = datetime(
            target_date.year, target_date.month, target_date.day, 0, 0, 1
        )
        tariff_switch = datetime(
            target_date.year, target_date.month, target_date.day,
            tariff_switch_hour, tariff_switch_minute, 1,
        )
        midnight_end = datetime(
            next_day.year, next_day.month, next_day.day, 0, 0, 1
        )

        import_a = find_closest_value(import_readings, midnight_start)
        import_b = find_closest_value(import_readings, tariff_switch)
        import_c = find_closest_value(import_readings, midnight_end)
        export_a = find_closest_value(export_readings, midnight_start)
        export_c = find_closest_value(export_readings, midnight_end)

        tariff_str = f"{tariff_switch_hour:02d}:{tariff_switch_minute:02d}"

        # Import readings are mandatory
        missing = []
        if import_a is None:
            missing.append(f"Import at 00:00 on {target_date}")
        if import_b is None:
            missing.append(f"Import at {tariff_str} on {target_date}")
        if import_c is None:
            missing.append(f"Import at 00:00 on {next_day}")

        if missing:
            all_timestamps = sorted(
                set(r.timestamp for r in import_readings + export_readings)
            )
            raise SmgwParseError(
                f"Missing required meter readings: {', '.join(missing)}. "
                f"Available timestamps: {all_timestamps}"
            )

        # Export readings are optional (not all meters have PV / feed-in)
        if export_a is None or export_c is None:
            if not export_readings:
                _LOGGER.info(
                    "No export (2.8.0) readings found for %s — "
                    "assuming no feed-in (no PV system)",
                    target_date,
                )
            else:
                _LOGGER.warning(
                    "Incomplete export readings for %s "
                    "(start=%s, end=%s) — setting feed-in to 0",
                    target_date, export_a, export_c,
                )
            export_a = export_a or 0.0
            export_c = export_c or 0.0

        daily_import_go = round(import_b - import_a, 4)
        daily_import_standard = round(import_c - import_b, 4)
        daily_import_total = round(import_c - import_a, 4)
        daily_export_total = round(export_c - export_a, 4)

        for label, val in [
            ("Go import", daily_import_go),
            ("Standard import", daily_import_standard),
            ("Total import", daily_import_total),
            ("Total export", daily_export_total),
        ]:
            if val < 0:
                _LOGGER.warning(
                    "%s is negative (%.4f kWh) for %s - "
                    "meter readings may be inconsistent",
                    label,
                    val,
                    target_date,
                )

        return DailyData(
            date=target_date,
            import_midnight=import_a,
            import_tariff_switch=import_b,
            import_next_midnight=import_c,
            export_midnight=export_a,
            export_next_midnight=export_c,
            daily_import_total=daily_import_total,
            daily_import_go=daily_import_go,
            daily_import_standard=daily_import_standard,
            daily_export_total=daily_export_total,
            raw_readings=readings,
        )
