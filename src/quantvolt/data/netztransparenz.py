"""Official German reBAP imbalance prices from the Netztransparenz WebAPI.

The adapter is optional infrastructure: callers may instead attach their own
validated price frame with :func:`attach_rebap_prices`.  Both routes feed the
same canonical PPA settlement columns.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import UTC, datetime, time, timedelta
from typing import Any
from urllib.parse import quote

import httpx
import polars as pl

from .._validation import require_non_negative, require_positive
from ..exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    ValidationError,
)
from .base import OAuthClientCredentials, _get_with_retries, _raise_for_status, _require_https

_TOKEN_URL = "https://identity.netztransparenz.de/users/connect/token"
_REBAP_URL = "https://ds.netztransparenz.de/api/v1/data/NrvSaldo/reBAP/Qualitaetsgesichert"
_PROVIDER = "netztransparenz"
_PRICE_COLUMNS = ("shortfall_price_per_mwh", "excess_price_per_mwh")


def _normalise_header(value: str) -> str:
    return value.lstrip("\ufeff").strip().lower().replace("ä", "ae").replace("ü", "ue")


def _parse_decimal(value: str | None, *, row_number: int, column: str) -> float:
    if value is None or not value.strip():
        raise DataUnavailableError(
            f"{_PROVIDER}: missing {column} at CSV row {row_number}"
        )
    try:
        parsed = float(value.strip().replace(".", "").replace(",", "."))
    except ValueError as exc:
        raise DataUnavailableError(
            f"{_PROVIDER}: unavailable {column} at CSV row {row_number}"
        ) from exc
    if not math.isfinite(parsed):
        raise DataSourceError(f"{_PROVIDER}: non-finite {column} at CSV row {row_number}")
    return parsed


def parse_rebap_csv(text: str) -> pl.DataFrame:
    """Parse official Format 9 CSV into exact UTC quarter-hour settlement prices."""
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    if reader.fieldnames is None:
        raise DataSourceError(f"{_PROVIDER}: CSV has no header")
    headers = {_normalise_header(name): name for name in reader.fieldnames}
    required = {
        "datum",
        "zeitzone",
        "von",
        "bis",
        "einheit",
        "rebap unterdeckt",
        "rebap ueberdeckt",
    }
    missing = sorted(required - headers.keys())
    if missing:
        raise DataSourceError(f"{_PROVIDER}: CSV is missing columns: {', '.join(missing)}")

    rows: list[dict[str, Any]] = []
    seen: set[tuple[datetime, datetime]] = set()
    for row_number, raw in enumerate(reader, start=2):
        row = {
            _normalise_header(name): (value or "").strip()
            for name, value in raw.items()
            if name is not None
        }

        field = row.__getitem__

        if field("zeitzone").upper() != "UTC":
            raise DataSourceError(
                f"{_PROVIDER}: timezone must be UTC at CSV row {row_number}"
            )
        if field("einheit").upper() != "EUR/MWH":
            raise DataSourceError(
                f"{_PROVIDER}: unit must be EUR/MWh at CSV row {row_number}"
            )
        try:
            day = datetime.strptime(field("datum"), "%d.%m.%Y").date()
            start_clock = time.fromisoformat(field("von"))
            end_clock = time.fromisoformat(field("bis"))
        except ValueError as exc:
            raise DataSourceError(
                f"{_PROVIDER}: invalid date or time at CSV row {row_number}"
            ) from exc
        start = datetime.combine(day, start_clock, tzinfo=UTC)
        end = datetime.combine(day, end_clock, tzinfo=UTC)
        if end <= start:
            end += timedelta(days=1)
        if end - start != timedelta(minutes=15):
            raise DataSourceError(
                f"{_PROVIDER}: interval at CSV row {row_number} is not exactly 15 minutes"
            )
        key = (start, end)
        if key in seen:
            raise DataSourceError(
                f"{_PROVIDER}: duplicate interval beginning {start.isoformat()}"
            )
        seen.add(key)
        rows.append(
            {
                "interval_start_utc": start,
                "interval_end_utc": end,
                "shortfall_price_per_mwh": _parse_decimal(
                    field("rebap unterdeckt"), row_number=row_number, column="under-covered reBAP"
                ),
                "excess_price_per_mwh": _parse_decimal(
                    field("rebap ueberdeckt"), row_number=row_number, column="over-covered reBAP"
                ),
                "unit": "EUR/MWh",
                "source": "Netztransparenz.de reBAP Qualitätsgesichert",
            }
        )
    if not rows:
        raise DataUnavailableError(f"{_PROVIDER}: response contained no reBAP intervals")
    rows.sort(key=lambda item: item["interval_start_utc"])
    return pl.DataFrame(rows)


def attach_rebap_prices(
    data: pl.DataFrame,
    rebap: pl.DataFrame,
    *,
    interval_start_column: str = "interval_start_utc",
    interval_end_column: str = "interval_end_utc",
) -> pl.DataFrame:
    """Attach reBAP prices by exact interval keys; reject every unpriced caller row."""
    keys = [interval_start_column, interval_end_column]
    missing_data = [name for name in keys if name not in data.columns]
    if missing_data:
        raise ValidationError(f"data is missing interval columns: {', '.join(missing_data)}")
    existing = [name for name in _PRICE_COLUMNS if name in data.columns]
    if existing:
        raise ValidationError(f"data already contains reBAP price columns: {', '.join(existing)}")
    required_rebap = {"interval_start_utc", "interval_end_utc", *_PRICE_COLUMNS}
    missing_rebap = sorted(required_rebap - set(rebap.columns))
    if missing_rebap:
        raise ValidationError(f"rebap is missing columns: {', '.join(missing_rebap)}")
    has_duplicates = rebap.select(
        pl.struct(["interval_start_utc", "interval_end_utc"]).is_duplicated().any()
    ).item()
    if has_duplicates:
        raise ValidationError("rebap contains duplicate interval keys")

    prices = rebap.select(
        pl.col("interval_start_utc").alias(interval_start_column),
        pl.col("interval_end_utc").alias(interval_end_column),
        *_PRICE_COLUMNS,
    )
    marker = "__quantvolt_rebap_matched"
    joined = data.join(prices.with_columns(pl.lit(True).alias(marker)), on=keys, how="left")
    if joined[marker].null_count():
        raise DataUnavailableError(
            f"{_PROVIDER}: {joined[marker].null_count()} caller intervals have no exact reBAP match"
        )
    return joined.drop(marker)


class NetztransparenzSource:
    """OAuth-authenticated source for quality-assured German reBAP prices."""

    provider = _PROVIDER

    def __init__(
        self,
        credentials: OAuthClientCredentials | None = None,
        transport: httpx.BaseTransport | None = None,
        *,
        token_url: str = _TOKEN_URL,
        rebap_url: str = _REBAP_URL,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
    ) -> None:
        require_positive("timeout_seconds", timeout_seconds)
        require_non_negative("max_retries", max_retries)
        require_non_negative("backoff_seconds", backoff_seconds)
        self._credentials = credentials or OAuthClientCredentials.from_env(self.provider)
        self._transport = transport
        self._token_url = token_url
        self._rebap_url = rebap_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    def rebap(self, start: datetime, end: datetime) -> pl.DataFrame:
        """Fetch quality-assured reBAP intervals whose starts lie in ``[start, end)``."""
        for name, value in (("start", start), ("end", end)):
            if value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ValidationError(f"{name} must be timezone-aware UTC")
        if end <= start:
            raise ValidationError("end must be strictly after start")
        client_id, client_secret = self._credentials.require(self.provider)
        _require_https(self._token_url)
        _require_https(self._rebap_url)
        with httpx.Client(transport=self._transport, timeout=self._timeout_seconds) as client:
            token_response = client.post(
                self._token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            if token_response.status_code in (400, 401, 403):
                raise AuthenticationError(
                    f"{self.provider}: OAuth client credentials were rejected; check "
                    "QUANTVOLT_NETZTRANSPARENZ_CLIENT_ID and "
                    "QUANTVOLT_NETZTRANSPARENZ_CLIENT_SECRET"
                )
            _raise_for_status(self.provider, token_response.status_code)
            try:
                payload = json.loads(token_response.text)
                token = payload["access_token"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise AuthenticationError(
                    f"{self.provider}: token response did not contain an access token"
                ) from exc
            if not isinstance(token, str) or not token:
                raise AuthenticationError(
                    f"{self.provider}: token response did not contain an access token"
                )
            stamp = "%Y-%m-%dT%H:%M:%S"
            url = (
                f"{self._rebap_url}/{quote(start.strftime(stamp), safe='')}/"
                f"{quote(end.strftime(stamp), safe='')}"
            )
            response = _get_with_retries(
                client,
                url,
                {},
                headers={"Authorization": f"Bearer {token}"},
                max_retries=self._max_retries,
                backoff_seconds=self._backoff_seconds,
            )
        _raise_for_status(self.provider, response.status_code)
        frame = parse_rebap_csv(response.text)
        selected = frame.filter(
            (pl.col("interval_start_utc") >= start) & (pl.col("interval_start_utc") < end)
        )
        if selected.is_empty():
            raise DataUnavailableError(
                f"{self.provider}: response contained no reBAP intervals in the requested range"
            )
        return selected
