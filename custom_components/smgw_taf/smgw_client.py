"""Client for communicating with PPC Smart Meter Gateway via HAN interface."""

from __future__ import annotations

import logging
import re
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
    taf7_profile_validated: bool = False


@dataclass
class DailyData:
    """Processed daily meter data."""

    date: date
    # Absolute meter readings at key timestamps
    import_midnight: float  # A: Verbrauch at 00:00
    import_0500: float  # B: Verbrauch at 05:00
    import_next_midnight: float  # C: Verbrauch at 00:00 next day
    export_midnight: float  # Einspeisung at 00:00
    export_next_midnight: float  # Einspeisung at 00:00 next day
    # Calculated daily values
    daily_import_total: float  # C - A
    daily_import_go: float  # B - A (00:00-05:00)
    daily_import_standard: float  # C - B (05:00-00:00)
    daily_export_total: float  # export_next_midnight - export_midnight
    # All raw readings for archival (optional)
    raw_readings: list[MeterReading] = field(default_factory=list)


class SmgwClient:
    """Client for PPC SMGW HAN interface."""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        taf7_profile_name: str,
    ) -> None:
        """Initialize the SMGW client."""
        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._taf7_profile_name = taf7_profile_name
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
        except httpx.ConnectError as err:
            raise SmgwConnectionError(
                f"Cannot connect to SMGW at {self._base_url}: {err}"
            ) from err
        except httpx.TimeoutException as err:
            raise SmgwConnectionError(
                f"Timeout connecting to SMGW: {err}"
            ) from err

        # Extract CSRF token from HTML
        self._token = self._parse_token(response.text)
        if not self._token:
            raise SmgwParseError("Could not extract CSRF token from login page")

        _LOGGER.debug("SMGW login successful, token obtained")
        return response.text

    async def _post(self, data: dict) -> str:
        """Send a POST request with the current session.

        Wraps all httpx exceptions into SmgwClientError subtypes (Fix #6).
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
        except httpx.ConnectError as err:
            raise SmgwConnectionError(
                f"Connection lost during request: {err}"
            ) from err
        except httpx.TimeoutException as err:
            raise SmgwConnectionError(
                f"Timeout during request: {err}"
            ) from err

        # Update token from response (it may change)
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
        """Extract CSRF token from HTML hidden input field."""
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "tkn"})
        if token_input and token_input.get("value"):
            return token_input["value"]
        # Fallback: regex
        match = re.search(r'name=["\']tkn["\']\s+value=["\']([^"\']+)', html)
        return match.group(1) if match else None

    @staticmethod
    def _parse_firmware(html: str) -> str:
        """Extract firmware version from the footer."""
        soup = BeautifulSoup(html, "html.parser")
        fw_div = soup.find("p", id="div_fwversion")
        if fw_div:
            return fw_div.get_text(strip=True)
        return "unknown"

    async def _get_taf7_dropdown_tid(self) -> str:
        """Get the dropdown tid for the configured TAF7 profile.

        POSTs action=tariffform to get the profile list, then finds the
        dropdown value for the configured profile name.
        """
        html = await self._post({"action": "tariffform"})
        soup = BeautifulSoup(html, "html.parser")

        # Find the dropdown
        select = soup.find("select", id="tarifform_select_profile")
        if not select:
            select = soup.find("select")

        if not select:
            raise SmgwParseError("Could not find profile dropdown in tariffform")

        dropdown_tid = None
        for option in select.find_all("option"):
            option_text = option.get_text(strip=True)
            if self._taf7_profile_name in option_text:
                dropdown_tid = option.get("value")
                break

        if not dropdown_tid:
            available = [
                opt.get_text(strip=True) for opt in select.find_all("option")
            ]
            raise SmgwParseError(
                f"TAF7 profile '{self._taf7_profile_name}' not found. "
                f"Available profiles: {available}"
            )

        _LOGGER.debug(
            "Found TAF7 profile '%s' with dropdown tid=%s",
            self._taf7_profile_name,
            dropdown_tid,
        )

        return dropdown_tid

    async def _navigate_to_taf7_profile(self) -> tuple[str, str]:
        """Navigate to TAF7 profile and return (dropdown_tid, profile_html).

        Flow:
        1. POST action=tariffform -> get dropdown with profile options
        2. Find the TAF7 profile's dropdown value
        3. POST action=showTariffProfile with that value -> get profile details page
        """
        dropdown_tid = await self._get_taf7_dropdown_tid()

        # Load the profile detail page (contains meter domain info)
        profile_html = await self._post(
            {"action": "showTariffProfile", "tid": dropdown_tid}
        )

        return dropdown_tid, profile_html

    @staticmethod
    def _parse_meter_id(profile_html: str) -> str:
        """Parse meter ID from the TAF7 profile detail page.

        Looks for the domain column in the tafvalues table,
        e.g. "1lgz0072999211.sm" -> "1lgz0072999211"
        """
        soup = BeautifulSoup(profile_html, "html.parser")

        # Look in the tafvalues table for domain column
        domain_td = soup.find("td", id="table_tafvalues_col_domain")
        if domain_td:
            domain_text = domain_td.get_text(strip=True)
            # Strip the ".sm" suffix
            meter_id = domain_text.removesuffix(".sm")
            if meter_id:
                return meter_id

        raise SmgwParseError(
            "Could not find meter ID (Zähler-Domänenname) in TAF7 profile"
        )

    async def _get_taf7_tid(self, dropdown_tid: str) -> str:
        """Get the tid needed for data (showTarification) requests.

        From the tariffform page, navigate to showTarificationForm
        which has a different tid in a hidden field.
        """
        html = await self._post(
            {"action": "showTarificationForm", "tid": dropdown_tid}
        )
        soup = BeautifulSoup(html, "html.parser")

        tid_input = soup.find("input", {"name": "tid", "type": "hidden"})
        if not tid_input:
            tid_input = soup.find("input", {"name": "tid"})

        if not tid_input or not tid_input.get("value"):
            raise SmgwParseError(
                "Could not find hidden tid field in showTarificationForm"
            )

        actual_tid = tid_input["value"]
        _LOGGER.debug("Got actual TAF7 tid=%s", actual_tid)
        return actual_tid

    def _parse_tarification_table(self, html: str) -> list[MeterReading]:
        """Parse the tarification HTML table into MeterReading objects."""
        soup = BeautifulSoup(html, "html.parser")
        readings: list[MeterReading] = []

        rows = soup.find_all("tr", id="table_tafregister_line")
        if not rows:
            table = soup.find("table", id="tarification")
            if table:
                rows = table.find_all("tr")

        if not rows:
            _LOGGER.warning("No tarification data rows found in HTML response")
            return readings

        for row in rows:
            try:
                reading = self._parse_row(row)
                if reading:
                    readings.append(reading)
            except (ValueError, TypeError, AttributeError) as err:
                _LOGGER.debug("Skipping unparseable row: %s", err)
                continue

        _LOGGER.debug("Parsed %d meter readings from TAF7 data", len(readings))
        return readings

    def _parse_row(self, row) -> MeterReading | None:
        """Parse a single table row into a MeterReading."""

        def cell_value(td) -> str | None:
            if td is None:
                return None
            inp = td.find("input", id="button_tarification_register")
            if inp and inp.get("value"):
                return inp["value"].strip()
            inp = td.find("input")
            if inp and inp.get("value"):
                return inp["value"].strip()
            text = td.get_text(strip=True)
            return text if text else None

        ts_td = row.find("td", id="table_tafregister_col_zeitstempel")
        value_td = row.find("td", id="table_tafregister_col_wert")
        unit_td = row.find("td", id="table_tafregister_col_einheit")
        obis_td = row.find("td", id="table_tafregister_col_obis")
        quality_td = row.find("td", id="table_tafregister_col_qualitaet")

        ts_str = cell_value(ts_td)
        value_str = cell_value(value_td)
        obis_str = cell_value(obis_td)

        if not all([ts_str, value_str, obis_str]):
            return None

        if obis_str not in (OBIS_IMPORT, OBIS_EXPORT):
            return None

        try:
            timestamp = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            _LOGGER.debug("Cannot parse timestamp: %s", ts_str)
            return None

        return MeterReading(
            timestamp=timestamp,
            obis_code=obis_str,
            value=float(value_str),
            unit=cell_value(unit_td) or "kWh",
            quality=cell_value(quality_td) or "",
        )

    async def async_validate_and_get_device_info(self) -> SmgwDeviceInfo:
        """Validate connection, TAF7 profile, and return device info.

        Used during config flow setup. Tests login, navigates to
        TAF7 profile, extracts meter ID and firmware version.
        """
        try:
            login_html = await self._login()
            firmware = self._parse_firmware(login_html)

            # Navigate to TAF7 profile (validates profile exists)
            _dropdown_tid, profile_html = await self._navigate_to_taf7_profile()

            # Parse meter ID
            meter_id = self._parse_meter_id(profile_html)

            _LOGGER.info(
                "SMGW validated: meter_id=%s, firmware=%s",
                meter_id,
                firmware,
            )

            return SmgwDeviceInfo(
                meter_id=meter_id,
                firmware_version=firmware,
                taf7_profile_validated=True,
            )
        finally:
            await self._logout()

    async def async_fetch_daily_data(self, target_date: date) -> DailyData:
        """Fetch and process daily data for a given date.

        Queries TAF7 for the full target_date (00:00 to next day)
        to get all 15-minute interval readings.
        """
        try:
            await self._login()

            # Get the dropdown_tid directly (no profile detail page needed)
            dropdown_tid = await self._get_taf7_dropdown_tid()
            tid = await self._get_taf7_tid(dropdown_tid)

            from_str = target_date.strftime("%Y-%m-%d")
            next_day = target_date + timedelta(days=1)
            to_str = next_day.strftime("%Y-%m-%d")

            _LOGGER.debug(
                "Fetching TAF7 data from %s to %s", from_str, to_str
            )

            html = await self._post(
                {
                    "action": "showTarification",
                    "tid": tid,
                    "from": from_str,
                    "to": to_str,
                }
            )

            all_readings = self._parse_tarification_table(html)

            if not all_readings:
                raise SmgwParseError(
                    f"No meter readings found for {target_date}"
                )

            return self._process_readings(target_date, all_readings)

        finally:
            await self._logout()

    def _process_readings(
        self, target_date: date, readings: list[MeterReading]
    ) -> DailyData:
        """Process raw readings into DailyData with tariff calculations.

        Uses exact timestamp matching (Fix #5):
        Finds the reading closest to XX:00:00 within each target hour,
        with minute < 15 to avoid picking up e.g. 00:15 or 05:15 values.

        A = earliest reading at hour 0 on target_date
        B = earliest reading at hour 5 on target_date
        C = earliest reading at hour 0 on target_date + 1
        """
        next_day = target_date + timedelta(days=1)

        # Group readings by (date, hour, obis_code), keep the earliest minute
        import_by_hour: dict[tuple[date, int], list[MeterReading]] = {}
        export_by_hour: dict[tuple[date, int], list[MeterReading]] = {}

        for r in readings:
            key = (r.timestamp.date(), r.timestamp.hour)
            if r.obis_code == OBIS_IMPORT:
                import_by_hour.setdefault(key, []).append(r)
            elif r.obis_code == OBIS_EXPORT:
                export_by_hour.setdefault(key, []).append(r)

        def earliest_value(
            lookup: dict[tuple[date, int], list[MeterReading]],
            d: date,
            h: int,
        ) -> float | None:
            """Get value of earliest reading in given hour, minute < 15."""
            candidates = lookup.get((d, h), [])
            # Filter to readings with minute < 15 (i.e. close to XX:00)
            valid = [r for r in candidates if r.timestamp.minute < 15]
            if not valid:
                # Fallback: accept any reading in that hour
                valid = candidates
            if not valid:
                return None
            # Sort by timestamp, take earliest
            valid.sort(key=lambda r: r.timestamp)
            return valid[0].value

        # Extract A, B, C
        import_a = earliest_value(import_by_hour, target_date, 0)
        import_b = earliest_value(import_by_hour, target_date, 5)
        import_c = earliest_value(import_by_hour, next_day, 0)
        export_a = earliest_value(export_by_hour, target_date, 0)
        export_c = earliest_value(export_by_hour, next_day, 0)

        # Validate all required values are present
        missing = []
        if import_a is None:
            missing.append(f"Import at 00:00 on {target_date}")
        if import_b is None:
            missing.append(f"Import at 05:00 on {target_date}")
        if import_c is None:
            missing.append(f"Import at 00:00 on {next_day}")
        if export_a is None:
            missing.append(f"Export at 00:00 on {target_date}")
        if export_c is None:
            missing.append(f"Export at 00:00 on {next_day}")

        if missing:
            available_import = sorted(import_by_hour.keys())
            available_export = sorted(export_by_hour.keys())
            raise SmgwParseError(
                f"Missing required meter readings: {', '.join(missing)}. "
                f"Available import hours: {available_import}, "
                f"Available export hours: {available_export}"
            )

        # Calculate daily values
        daily_import_go = round(import_b - import_a, 4)
        daily_import_standard = round(import_c - import_b, 4)
        daily_import_total = round(import_c - import_a, 4)
        daily_export_total = round(export_c - export_a, 4)

        # Sanity checks
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
            import_0500=import_b,
            import_next_midnight=import_c,
            export_midnight=export_a,
            export_next_midnight=export_c,
            daily_import_total=daily_import_total,
            daily_import_go=daily_import_go,
            daily_import_standard=daily_import_standard,
            daily_export_total=daily_export_total,
            raw_readings=readings,
        )
