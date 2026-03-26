"""Client for communicating with PPC Smart Meter Gateway via HAN interface."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
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
    raw_readings: list[MeterReading] | None = None


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

    async def _login(self) -> None:
        """Log in to the SMGW and obtain session cookie + CSRF token."""
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

    async def _post(self, data: dict) -> str:
        """Send a POST request with the current session."""
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

    async def _get_taf7_tid(self) -> str:
        """Navigate to TAF7 profile and get the tid for data requests.

        Flow:
        1. POST action=tariffform -> get dropdown with profile options
        2. Find the TAF7 profile's dropdown value
        3. POST action=showTarificationForm with that value -> get hidden tid
        """
        # Step 1: Get profile list
        html = await self._post({"action": "tariffform"})
        soup = BeautifulSoup(html, "html.parser")

        # Find the dropdown and look for our TAF7 profile
        select = soup.find("select", id="tarifform_select_profile")
        if not select:
            # Try without specific ID
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

        # Step 2: Load the tarification form to get the actual tid
        html = await self._post(
            {"action": "showTarificationForm", "tid": dropdown_tid}
        )
        soup = BeautifulSoup(html, "html.parser")

        # The actual tid is in a hidden input field
        tid_input = soup.find("input", {"name": "tid", "type": "hidden"})
        if not tid_input:
            # Try broader search
            tid_input = soup.find("input", {"name": "tid"})

        if not tid_input or not tid_input.get("value"):
            raise SmgwParseError(
                "Could not find hidden tid field in showTarificationForm"
            )

        actual_tid = tid_input["value"]
        _LOGGER.debug("Got actual TAF7 tid=%s", actual_tid)
        return actual_tid

    def _parse_tarification_table(self, html: str) -> list[MeterReading]:
        """Parse the tarification HTML table into MeterReading objects.

        Values are inside <input type='submit'> buttons within <td> elements,
        NOT as text nodes.
        """
        soup = BeautifulSoup(html, "html.parser")
        readings: list[MeterReading] = []

        # Find all table rows with tarification data
        rows = soup.find_all("tr", id="table_tafregister_line")
        if not rows:
            # Try alternate: find table and iterate rows
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
        # Helper to extract value from a cell (check for input button first)
        def cell_value(td) -> str | None:
            if td is None:
                return None
            # Values are in input buttons
            inp = td.find("input", id="button_tarification_register")
            if inp and inp.get("value"):
                return inp["value"].strip()
            inp = td.find("input")
            if inp and inp.get("value"):
                return inp["value"].strip()
            # Fallback to text content
            text = td.get_text(strip=True)
            return text if text else None

        # Extract cell values by their IDs
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

        # Only process import and export OBIS codes
        if obis_str not in (OBIS_IMPORT, OBIS_EXPORT):
            return None

        # Parse timestamp (format: "2026-03-24 00:00:01")
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

    async def async_fetch_daily_data(
        self, target_date: date
    ) -> DailyData:
        """Fetch and process daily data for a given date.

        Queries TAF7 for the full target_date (00:00 to 00:15 next day)
        to get all 15-minute interval readings.

        Args:
            target_date: The date to fetch data for (typically yesterday).

        Returns:
            DailyData with calculated tariff values.

        """
        try:
            # Login
            await self._login()

            # Get TAF7 profile tid
            tid = await self._get_taf7_tid()

            # Query full day: from target_date 00:00 to next day 00:15
            # This gives us all readings including the 00:00:01 of the next day
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

            # Parse all readings
            all_readings = self._parse_tarification_table(html)

            if not all_readings:
                raise SmgwParseError(
                    f"No meter readings found for {target_date}"
                )

            # Extract the three key timestamps
            return self._process_readings(target_date, all_readings)

        finally:
            await self._logout()

    def _process_readings(
        self, target_date: date, readings: list[MeterReading]
    ) -> DailyData:
        """Process raw readings into DailyData with tariff calculations.

        Needs three timestamps:
        A = 00:00:01 on target_date (import + export)
        B = 05:00:01 on target_date (import only, for tariff split)
        C = 00:00:01 on target_date + 1 (import + export)
        """
        next_day = target_date + timedelta(days=1)

        # Build lookup: (date, hour, obis) -> value
        # We match by date and hour, accepting any second offset (01-04)
        import_values: dict[tuple[date, int], float] = {}
        export_values: dict[tuple[date, int], float] = {}

        for r in readings:
            key = (r.timestamp.date(), r.timestamp.hour)
            if r.obis_code == OBIS_IMPORT:
                # For 00:00 timestamps, only keep the first one per day
                if key not in import_values:
                    import_values[key] = r.value
            elif r.obis_code == OBIS_EXPORT:
                if key not in export_values:
                    export_values[key] = r.value

        # Extract A, B, C
        a_key = (target_date, 0)  # 00:00 target date
        b_key = (target_date, 5)  # 05:00 target date
        c_key = (next_day, 0)  # 00:00 next day

        import_a = import_values.get(a_key)
        import_b = import_values.get(b_key)
        import_c = import_values.get(c_key)
        export_a = export_values.get(a_key)
        export_c = export_values.get(c_key)

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
            raise SmgwParseError(
                f"Missing required meter readings: {', '.join(missing)}. "
                f"Available import timestamps: "
                f"{sorted(import_values.keys())}, "
                f"Available export timestamps: "
                f"{sorted(export_values.keys())}"
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

    async def async_test_connection(self) -> bool:
        """Test if the SMGW is reachable and credentials are valid."""
        try:
            await self._login()
            return True
        except SmgwClientError:
            return False
        finally:
            await self._logout()
