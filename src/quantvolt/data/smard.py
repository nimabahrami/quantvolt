"""Timestamp-preserving SMARD day-ahead power-price adapter.

SMARD is the German Federal Network Agency's electricity-market platform.  Its
public chart-data endpoint requires no credential.  German day-ahead products
were hourly through 2025-09-30 and changed to 15-minute products on 2025-10-01;
``native_prices`` preserves that boundary instead of repeating hourly prices
four times and pretending they were historical quarter-hour products.
"""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import polars as pl

from .._validation import require_non_negative, require_positive
from ..exceptions import DataSourceError, DataUnavailableError, ValidationError
from .base import _get_with_retries, _raise_for_status, _require_https

_BASE_URL = "https://www.smard.de/app/chart_data"
_PRICE_FILTER = "4169"
_DEFAULT_ZONE = "DE-LU"
_LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
_NATIVE_QUARTER_HOUR_START = datetime(2025, 9, 30, 22, 0, tzinfo=UTC)


class SmardResolution(StrEnum):
    """Resolutions used by the SMARD chart-data endpoint."""

    HOURLY = "hour"
    QUARTER_HOURLY = "quarterhour"

    @property
    def minutes(self) -> int:
        return 60 if self is SmardResolution.HOURLY else 15


def _require_utc_range(start: datetime, end: datetime) -> None:
    for name, value in (("start", start), ("end", end)):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValidationError(f"{name} must be timezone-aware UTC, got {value!r}")
        if value.utcoffset() != timedelta(0):
            raise ValidationError(
                f"{name} must be expressed in UTC, got offset {value.utcoffset()}"
            )
    if end <= start:
        raise ValidationError(f"end must be strictly after start, got {start!r}..{end!r}")


def _parse_json(provider: str, text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataSourceError(f"{provider}: provider returned unparseable JSON") from exc
    if not isinstance(payload, dict):
        raise DataSourceError(f"{provider}: provider JSON must be an object")
    return payload


def _price_frame(
    payload: dict[str, Any],
    bidding_zone: str,
    resolution: SmardResolution,
) -> pl.DataFrame:
    """Parse one recorded SMARD payload into an ordered, timestamped frame."""
    raw_series = payload.get("series")
    if not isinstance(raw_series, list):
        raise DataSourceError("smard: response has no series list")

    rows: list[dict[str, Any]] = []
    seen: set[datetime] = set()
    duration = timedelta(minutes=resolution.minutes)
    for index, point in enumerate(raw_series):
        if not isinstance(point, list | tuple) or len(point) != 2:
            raise DataSourceError(f"smard: malformed series point at index {index}")
        epoch_ms, raw_price = point
        if raw_price is None:
            continue
        try:
            start_utc = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=UTC)
            price = float(raw_price)
        except (TypeError, ValueError, OverflowError) as exc:
            raise DataSourceError(f"smard: invalid series point at index {index}") from exc
        if not math.isfinite(price):
            raise DataSourceError(f"smard: non-finite price at index {index}: {price!r}")
        if start_utc in seen:
            raise DataSourceError(f"smard: duplicate interval start {start_utc.isoformat()}")
        seen.add(start_utc)
        local = start_utc.astimezone(_LOCAL_TIMEZONE)
        offset = local.utcoffset()
        if offset is None:  # defensive: ZoneInfo-aware datetimes always have an offset
            raise DataSourceError(f"smard: local timezone has no offset at {start_utc.isoformat()}")
        rows.append(
            {
                "interval_start_utc": start_utc,
                "interval_end_utc": start_utc + duration,
                "local_start": local.isoformat(),
                "local_date": local.date(),
                "utc_offset_minutes": int(offset.total_seconds() // 60),
                "duration_minutes": resolution.minutes,
                "bidding_zone": bidding_zone,
                "price_eur_per_mwh": price,
                "source": "Bundesnetzagentur | SMARD.de",
            }
        )
    if not rows:
        raise DataUnavailableError("smard: response contained no price points")
    rows.sort(key=lambda row: row["interval_start_utc"])
    return pl.DataFrame(rows)


class SmardSource:
    """Public SMARD adapter for timestamped German day-ahead prices."""

    provider = "smard"

    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        *,
        base_url: str = _BASE_URL,
        bidding_zone: str = _DEFAULT_ZONE,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
    ) -> None:
        require_positive("timeout_seconds", timeout_seconds)
        require_non_negative("max_retries", max_retries)
        require_non_negative("backoff_seconds", backoff_seconds)
        if not bidding_zone:
            raise ValidationError("bidding_zone must be non-empty")
        self._transport = transport
        self._base_url = base_url.rstrip("/")
        self._bidding_zone = bidding_zone
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    def prices(
        self,
        start: datetime,
        end: datetime,
        resolution: SmardResolution = SmardResolution.HOURLY,
    ) -> pl.DataFrame:
        """Return day-ahead prices overlapping ``[start, end)`` at one resolution."""
        _require_utc_range(start, end)
        resolution = SmardResolution(resolution)
        index_url = (
            f"{self._base_url}/{_PRICE_FILTER}/{self._bidding_zone}/index_{resolution.value}.json"
        )
        index_payload = self._get_json(index_url)
        raw_timestamps = index_payload.get("timestamps")
        if not isinstance(raw_timestamps, list):
            raise DataSourceError("smard: index response has no timestamps list")
        try:
            chunk_starts = sorted(
                datetime.fromtimestamp(float(value) / 1000.0, tz=UTC) for value in raw_timestamps
            )
        except (TypeError, ValueError, OverflowError) as exc:
            raise DataSourceError("smard: index contains an invalid timestamp") from exc

        selected: list[datetime] = []
        for index, chunk_start in enumerate(chunk_starts):
            chunk_end = (
                chunk_starts[index + 1]
                if index + 1 < len(chunk_starts)
                else chunk_start + timedelta(days=7)
            )
            if chunk_start < end and chunk_end > start:
                selected.append(chunk_start)
        if not selected:
            raise DataUnavailableError("smard: requested range is outside available data")

        frames: list[pl.DataFrame] = []
        for chunk_start in selected:
            epoch_ms = int(chunk_start.timestamp() * 1000)
            url = (
                f"{self._base_url}/{_PRICE_FILTER}/{self._bidding_zone}/"
                f"{_PRICE_FILTER}_{self._bidding_zone}_{resolution.value}_{epoch_ms}.json"
            )
            frames.append(_price_frame(self._get_json(url), self._bidding_zone, resolution))
        combined = pl.concat(frames).unique(subset=["interval_start_utc"], keep="first")
        return combined.filter(
            (pl.col("interval_start_utc") >= start) & (pl.col("interval_start_utc") < end)
        ).sort("interval_start_utc")

    def native_prices(self, start: datetime, end: datetime) -> pl.DataFrame:
        """Return native hourly then native quarter-hour products across the 2025 boundary."""
        _require_utc_range(start, end)
        frames: list[pl.DataFrame] = []
        hourly_end = min(end, _NATIVE_QUARTER_HOUR_START)
        if start < hourly_end:
            frames.append(self.prices(start, hourly_end, SmardResolution.HOURLY))
        quarter_start = max(start, _NATIVE_QUARTER_HOUR_START)
        if quarter_start < end:
            frames.append(self.prices(quarter_start, end, SmardResolution.QUARTER_HOURLY))
        if not frames:
            raise DataUnavailableError("smard: requested range contained no native products")
        return pl.concat(frames).sort("interval_start_utc")

    def _get_json(self, url: str) -> dict[str, Any]:
        _require_https(url)
        with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
            response = _get_with_retries(
                client,
                url,
                {},
                max_retries=self._max_retries,
                backoff_seconds=self._backoff_seconds,
            )
        _raise_for_status(self.provider, response.status_code)
        return _parse_json(self.provider, response.text)
