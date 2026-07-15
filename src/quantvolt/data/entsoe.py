"""ENTSO-E Transparency (free token) — day-ahead power, load, generation (Task 54).

Free-token provider: request a personal token from the ENTSO-E Transparency Platform and
supply it as ``Credentials(token=...)`` or via ``QUANTVOLT_ENTSOE_TOKEN`` (explicit wins,
Req 12.3). The token is sent only to ENTSO-E, only over HTTPS, as the ``securityToken``
query parameter.

The adapter parses a deliberately **minimal, documented subset** of the ENTSO-E XML:
``*_MarketDocument -> TimeSeries -> Period -> Point``, where each ``Point`` carries a
``position`` plus either a ``price.amount`` (day-ahead prices, document ``A44``) or a
``quantity`` (load ``A65`` / generation ``A75``). ``TimeSeries`` and, within each, ``Period``
are ordered chronologically by their ``timeInterval`` start (not by document order — the
Transparency Platform does not guarantee document order is chronological), and ``Point``\\ s
are ordered by ``position`` within their ``Period``; everything else in the payload is
ignored. Under curve type ``A03`` (the standard for day-ahead prices since the 2024 15-minute
go-live) a ``Point`` is omitted from the document whenever its value repeats the previous
position's value; omitted positions are forward-filled from the previous position's value
(the standard guarantees position 1 is always present). An ``Acknowledgement_MarketDocument``
(ENTSO-E's "no matching data" reply) maps to :class:`~quantvolt.exceptions.DataUnavailableError`.

**Local delivery-day semantics.** ``price_frame``/``load_frame``/``generation_frame`` take
``start``/``end`` as calendar delivery days in the bidding zone's **local** time (CET/CEST,
BST, etc. — matching how a trader reads "the day-ahead auction for 1 January"), not as UTC
calendar days. Local midnight is converted to UTC before being sent as the ``periodStart``/
``periodEnd`` query parameters the Transparency API expects, using each hub's IANA timezone
(see ``_AREA_TIMEZONE``, overridable via ``timezone_overrides``).

ENTSO-E is a spot/fundamentals source: this adapter exposes **no** ``forward_curve`` method.
Forward/futures curves come only from commercial providers or caller-supplied data (Req 12.8).

Tests use ``httpx.MockTransport`` with recorded-style payloads — no live calls in CI.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import polars as pl

from .._validation import require_non_negative, require_positive
from ..exceptions import DataSourceError, DataUnavailableError
from ..models.commodity import CommodityConfig
from .base import Credentials, _get_with_retries, _raise_for_status, _require_https

_BASE_URL = "https://web-api.tp.entsoe.eu/api"
_TIMEOUT_SECONDS = 30.0

# Minimal bidding-zone map for the built-in power commodities (hub_id -> EIC area code).
_AREA_EIC: dict[str, str] = {
    "EEX_PHELIX_DE": "10Y1001A1001A82H",  # DE-LU bidding zone
    "EEX_PHELIX_AT": "10YAT-APG------L",
    "EPEX_DE": "10Y1001A1001A82H",
    "EPEX_FR": "10YFR-RTE------C",
    "EPEX_NL": "10YNL----------L",
    "EPEX_BE": "10YBE----------2",
    "EPEX_GB": "10YGB----------A",
}

# Local IANA timezone for each hub's bidding zone, used to interpret the caller's start/end
# dates as local calendar delivery days (see module docstring). One entry per hub above.
_AREA_TIMEZONE: dict[str, str] = {
    "EEX_PHELIX_DE": "Europe/Berlin",
    "EEX_PHELIX_AT": "Europe/Vienna",
    "EPEX_DE": "Europe/Berlin",
    "EPEX_FR": "Europe/Paris",
    "EPEX_NL": "Europe/Amsterdam",
    "EPEX_BE": "Europe/Brussels",
    "EPEX_GB": "Europe/London",
}


def _area_code(area_eic: Mapping[str, str], commodity: CommodityConfig) -> str:
    """EIC bidding-zone code for a power commodity's hub, or a clear error naming the hub."""
    try:
        return area_eic[commodity.hub.hub_id]
    except KeyError:
        supported = ", ".join(sorted(area_eic))
        raise DataSourceError(
            f"entsoe: hub {commodity.hub.hub_id!r} has no known ENTSO-E bidding zone "
            f"(ENTSO-E covers power only); supported hubs: {supported}"
        ) from None


def _area_timezone(timezones: Mapping[str, str], commodity: CommodityConfig) -> ZoneInfo:
    """IANA local timezone for a power commodity's hub, or a clear error naming the hub."""
    try:
        return ZoneInfo(timezones[commodity.hub.hub_id])
    except KeyError:
        supported = ", ".join(sorted(timezones))
        raise DataSourceError(
            f"entsoe: hub {commodity.hub.hub_id!r} has no known local delivery-day timezone "
            f"(ENTSO-E covers power only); supported hubs: {supported}"
        ) from None


def _period_stamp(day: date, zone: ZoneInfo) -> str:
    """UTC ``yyyyMMddHHmm`` stamp for local midnight of delivery day ``day`` in ``zone``.

    ``day`` is a calendar delivery day in the bidding zone's local time (Req 12.2-style
    market convention: "the day-ahead auction for 1 January" means CET/CEST midnight in
    Germany, not UTC midnight). The Transparency Platform's ``periodStart``/``periodEnd``
    parameters are UTC timestamps, so local midnight must be converted to UTC before
    formatting — a naive local-clock stamp silently shifts every CET/CEST query window by
    1-2 hours (more on DST transition days) versus the intended local delivery day.
    """
    local_midnight = datetime(day.year, day.month, day.day, tzinfo=zone)
    return f"{local_midnight.astimezone(UTC):%Y%m%d%H%M}"


def _local_name(tag: str) -> str:
    """Strip the XML namespace, keeping only the local tag name."""
    return tag.rsplit("}", 1)[-1]


_RESOLUTION = re.compile(r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?$")


def _utc_timestamp(text: str, provider: str) -> datetime:
    """Parse one ENTSO-E ISO-8601 timestamp and require an explicit UTC offset."""
    try:
        stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataSourceError(f"{provider}: invalid period timestamp {text!r}") from exc
    if stamp.tzinfo is None:
        raise DataSourceError(f"{provider}: period timestamp has no UTC offset: {text!r}")
    return stamp.astimezone(UTC)


def _resolution_delta(text: str, provider: str) -> timedelta:
    """Parse the fixed intraday resolutions used by the Transparency Platform."""
    match = _RESOLUTION.fullmatch(text)
    if match is None:
        raise DataSourceError(f"{provider}: unsupported ENTSO-E resolution {text!r}")
    delta = timedelta(
        hours=int(match.group("hours") or 0), minutes=int(match.group("minutes") or 0)
    )
    if delta <= timedelta(0):
        raise DataSourceError(f"{provider}: resolution must be positive, got {text!r}")
    return delta


def _child_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if _local_name(child.tag) == name and child.text is not None:
            return child.text.strip()
    return None


def _gap_filled_points(
    provider: str,
    period: ET.Element,
    value_tag: str,
    period_start: datetime,
    period_end: datetime,
    resolution: timedelta,
) -> list[tuple[int, float]]:
    """Points for one ``Period``, forward-filled to the full resolution grid (A03 semantics).

    Under curve type ``A03`` (standard for day-ahead prices since 2024) a ``Point`` is
    omitted from the document whenever its value repeats the previous position's value.
    Every omitted position in ``[1, expected_count]`` is forward-filled from the previous
    position's value; position 1 is required by the standard, so a document that omits it is
    malformed and raises rather than guessing a value.
    """
    raw_points: list[tuple[int, float]] = []
    for point in (el for el in period if _local_name(el.tag) == "Point"):
        position: int | None = None
        value: float | None = None
        for child in point:
            name = _local_name(child.tag)
            if name == "position" and child.text is not None:
                position = int(child.text)
            elif name == value_tag and child.text is not None:
                value = float(child.text)
        if position is not None and value is not None:
            raw_points.append((position, value))
    raw_points.sort()
    positions = [position for position, _ in raw_points]
    if len(positions) != len(set(positions)):
        raise DataSourceError(f"{provider}: duplicate Point position in Period")
    for position, _ in raw_points:
        if position < 1:
            raise DataSourceError(f"{provider}: Point position must be >= 1")

    existing = dict(raw_points)
    if 1 not in existing:
        raise DataSourceError(
            f"{provider}: Period is missing its first Point (position 1 is always present)"
        )

    resolution_seconds = resolution.total_seconds()
    total_seconds = (period_end - period_start).total_seconds()
    if total_seconds % resolution_seconds != 0:
        raise DataSourceError(
            f"{provider}: Period duration is not a whole number of resolution steps"
        )
    expected_count = int(total_seconds // resolution_seconds)
    if max(existing) > expected_count:
        raise DataSourceError(f"{provider}: Point position lies outside Period")

    filled: list[tuple[int, float]] = []
    last_value = existing[1]
    for position in range(1, expected_count + 1):
        if position in existing:
            last_value = existing[position]
        filled.append((position, last_value))
    return filled


def _parse_interval_points(provider: str, xml_text: str, value_tag: str) -> pl.DataFrame:
    """Extract values with their exact physical delivery intervals in UTC.

    ``TimeSeries`` elements and, within each, ``Period`` elements are processed in
    chronological order of their ``timeInterval`` start rather than document order, since the
    Transparency Platform does not guarantee the document lists them chronologically.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise DataSourceError(f"{provider}: provider returned unparseable XML") from exc
    if _local_name(root.tag) == "Acknowledgement_MarketDocument":
        raise DataUnavailableError(
            f"{provider}: no matching data for the requested query "
            "(provider returned an acknowledgement document)"
        )

    rows: list[dict[str, object]] = []
    time_series = [el for el in root.iter() if _local_name(el.tag) == "TimeSeries"]

    parsed_series: list[tuple[str, list[tuple[datetime, datetime, timedelta, ET.Element]]]] = []
    for series in time_series:
        series_id = _child_text(series, "mRID") or str(len(parsed_series) + 1)
        parsed_periods: list[tuple[datetime, datetime, timedelta, ET.Element]] = []
        for period in (el for el in series if _local_name(el.tag) == "Period"):
            start_text = _child_text(period, "start")
            end_text = _child_text(period, "end")
            resolution_text = _child_text(period, "resolution")
            if start_text is None or end_text is None or resolution_text is None:
                raise DataSourceError(f"{provider}: Period is missing interval or resolution")
            period_start = _utc_timestamp(start_text, provider)
            period_end = _utc_timestamp(end_text, provider)
            resolution = _resolution_delta(resolution_text, provider)
            if period_end <= period_start:
                raise DataSourceError(f"{provider}: Period end must be after start")
            parsed_periods.append((period_start, period_end, resolution, period))
        parsed_periods.sort(key=lambda item: item[0])
        parsed_series.append((series_id, parsed_periods))

    _far_future = datetime.max.replace(tzinfo=UTC)
    parsed_series.sort(key=lambda item: item[1][0][0] if item[1] else _far_future)

    for series_index, (series_id, parsed_periods) in enumerate(parsed_series):
        for period_index, (period_start, period_end, resolution, period) in enumerate(
            parsed_periods
        ):
            points = _gap_filled_points(
                provider, period, value_tag, period_start, period_end, resolution
            )
            for position, value in points:
                interval_start = period_start + (position - 1) * resolution
                interval_end = interval_start + resolution
                rows.append(
                    {
                        "time_series_id": series_id,
                        "time_series_index": series_index,
                        "period_index": period_index,
                        "position": position,
                        "interval_start_utc": interval_start,
                        "interval_end_utc": interval_end,
                        "duration_hours": resolution.total_seconds() / 3600.0,
                        "value": value,
                    }
                )
    if not rows:
        raise DataUnavailableError(f"{provider}: response contained no data points")
    return pl.DataFrame(rows).sort(
        "interval_start_utc", "time_series_index", "period_index", "position"
    )


def _parse_points(provider: str, xml_text: str, value_tag: str) -> list[float]:
    """Compatibility value-only parser; new code should retain the interval frame."""
    return _parse_interval_points(provider, xml_text, value_tag)["value"].to_list()


class EntsoeSource:
    """Free-token ENTSO-E adapter: day-ahead prices, load, and generation as ``pl.Series``.

    No ``forward_curve`` method — free sources are never forward-curve sources (Req 12.8).
    """

    provider = "entsoe"

    def __init__(
        self,
        credentials: Credentials | None = None,
        transport: httpx.BaseTransport | None = None,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
        bidding_zone_overrides: Mapping[str, str] | None = None,
        timezone_overrides: Mapping[str, str] | None = None,
    ) -> None:
        """Explicit ``credentials`` win; otherwise ``QUANTVOLT_ENTSOE_TOKEN`` is read.

        ``transport`` exists for tests (``httpx.MockTransport``); ``None`` uses real HTTPS.

        Args:
            base_url: The Transparency Platform endpoint (default the production API).
            timeout_seconds: Per-request HTTP timeout (default ``30.0``); must be ``> 0``.
            max_retries: Retries on a transient failure (connection error, HTTP 5xx/429)
                before giving up (default ``0``, i.e. today's single-attempt behaviour);
                must be ``>= 0``. Non-transient errors are never retried.
            backoff_seconds: Base of the deterministic exponential backoff between
                retries, ``backoff_seconds * 2**attempt`` (default ``1.0``); must be
                ``>= 0``.
            bidding_zone_overrides: Additional or overriding ``hub_id -> EIC`` entries
                merged over the built-in bidding-zone map (Req 1.6-style caller
                extension), so a caller can add a hub this adapter doesn't yet know.
            timezone_overrides: Additional or overriding ``hub_id -> IANA timezone`` entries
                (e.g. ``"Europe/Berlin"``) merged over the built-in map, mirroring
                ``bidding_zone_overrides`` (Req 1.6-style caller extension). Needed for any
                hub added via ``bidding_zone_overrides`` so its local delivery day can be
                converted to UTC (see module docstring).
        """
        require_positive("timeout_seconds", timeout_seconds)
        require_non_negative("max_retries", max_retries)
        require_non_negative("backoff_seconds", backoff_seconds)
        self._credentials = credentials or Credentials.from_env("entsoe")
        self._transport = transport
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._area_eic: dict[str, str] = {**_AREA_EIC, **(bidding_zone_overrides or {})}
        self._area_timezone: dict[str, str] = {**_AREA_TIMEZONE, **(timezone_overrides or {})}

    def price_series(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series:
        """Day-ahead prices (document ``A44``) for ``[start, end)`` as a float series.

        The series is named after ``commodity.commodity_id`` so it is directly usable
        wherever the core accepts a caller-supplied price series (Req 12.2).
        """
        frame = self.price_frame(commodity, start, end)
        return frame["value"].rename(commodity.commodity_id)

    def price_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame:
        """Day-ahead prices with exact UTC delivery starts, ends, and durations.

        ``start``/``end`` are local calendar delivery days in the hub's bidding zone (see
        module docstring); they are converted to UTC before being sent to the Transparency
        Platform.
        """
        area = _area_code(self._area_eic, commodity)
        zone = _area_timezone(self._area_timezone, commodity)
        return self._fetch_frame(
            {"documentType": "A44", "in_Domain": area, "out_Domain": area},
            start,
            end,
            value_tag="price.amount",
            zone=zone,
        )

    def load(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series:
        """Actual total load (document ``A65``, process ``A16``) as a float series."""
        frame = self.load_frame(commodity, start, end)
        return frame["value"].rename(f"{commodity.commodity_id}_load")

    def load_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame:
        """Actual total load with exact UTC delivery intervals.

        ``start``/``end`` are local calendar delivery days in the hub's bidding zone (see
        module docstring).
        """
        zone = _area_timezone(self._area_timezone, commodity)
        return self._fetch_frame(
            {
                "documentType": "A65",
                "processType": "A16",
                "outBiddingZone_Domain": _area_code(self._area_eic, commodity),
            },
            start,
            end,
            value_tag="quantity",
            zone=zone,
        )

    def generation(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series:
        """Actual aggregated generation (document ``A75``, process ``A16``) as a float series."""
        frame = self.generation_frame(commodity, start, end)
        return frame["value"].rename(f"{commodity.commodity_id}_generation")

    def generation_frame(self, commodity: CommodityConfig, start: date, end: date) -> pl.DataFrame:
        """Actual generation with intervals and source TimeSeries identity preserved.

        ``start``/``end`` are local calendar delivery days in the hub's bidding zone (see
        module docstring).
        """
        zone = _area_timezone(self._area_timezone, commodity)
        return self._fetch_frame(
            {
                "documentType": "A75",
                "processType": "A16",
                "in_Domain": _area_code(self._area_eic, commodity),
            },
            start,
            end,
            value_tag="quantity",
            zone=zone,
        )

    def _fetch_frame(
        self,
        params: dict[str, str],
        start: date,
        end: date,
        value_tag: str,
        *,
        zone: ZoneInfo,
    ) -> pl.DataFrame:
        """One HTTPS GET parsed without discarding ENTSO-E delivery timestamps.

        ``start``/``end`` are interpreted as local calendar delivery days in ``zone`` and
        converted to UTC before being sent as ``periodStart``/``periodEnd`` (see module
        docstring and :func:`_period_stamp`).
        """
        token = self._credentials.require_token(self.provider)
        _require_https(self._base_url)
        query = {
            **params,
            "periodStart": _period_stamp(start, zone),
            "periodEnd": _period_stamp(end, zone),
            "securityToken": token,
        }
        with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
            response = _get_with_retries(
                client,
                self._base_url,
                query,
                max_retries=self._max_retries,
                backoff_seconds=self._backoff_seconds,
            )
        _raise_for_status(self.provider, response.status_code)
        return _parse_interval_points(self.provider, response.text, value_tag)
