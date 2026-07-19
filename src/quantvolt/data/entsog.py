"""ENTSOG Transparency Platform (free, keyless) — gas flows.

The ENTSOG TP API is **keyless**: no token is required and none is ever transmitted. A
``Credentials`` object is still accepted (and ``QUANTVOLT_ENTSOG_TOKEN`` read) purely for
constructor uniformity with the other adapters — it is optional and unused.

The adapter queries the documented ``operationalData`` endpoint (JSON) for daily physical
flows at a network point and returns a ``pl.DataFrame`` with columns
``[point, direction, date, value, unit]``, ready for the core's fundamentals analysis.

ENTSOG is a fundamentals source: this adapter exposes no ``forward_curve`` method.
Tests use ``httpx.MockTransport`` — no live calls in CI.
"""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl

from ..exceptions import DataSourceError, DataUnavailableError
from .base import (
    Credentials,
    _http_get,
    _json_object,
    _raise_for_status,
    _require_https,
    _validate_retry_config,
)

_BASE_URL = "https://transparency.entsog.eu/api/v4/operationalData"
_TIMEOUT_SECONDS = 30.0


class EntsogSource:
    """Keyless ENTSOG adapter: daily physical gas flows as a ``pl.DataFrame``.

    No ``forward_curve`` method — free sources are never forward-curve sources.
    """

    provider = "entsog"

    def __init__(
        self,
        credentials: Credentials | None = None,
        transport: httpx.BaseTransport | None = None,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
    ) -> None:
        """ENTSOG needs no credential; ``credentials`` is optional and never transmitted.

        ``transport`` exists for tests (``httpx.MockTransport``); ``None`` uses real HTTPS.

        Args:
            base_url: The ENTSOG operationalData endpoint (default the production API).
            timeout_seconds: Per-request HTTP timeout (default ``30.0``); must be ``> 0``.
            max_retries: Retries on a transient failure (connection error, HTTP 5xx/429)
                before giving up (default ``0``, i.e. today's single-attempt behaviour);
                must be ``>= 0``. Non-transient errors are never retried.
            backoff_seconds: Base of the deterministic exponential backoff between
                retries, ``backoff_seconds * 2**attempt`` (default ``1.0``); must be
                ``>= 0``.
        """
        _validate_retry_config(timeout_seconds, max_retries, backoff_seconds)
        self._credentials = credentials or Credentials.from_env("entsog")
        self._transport = transport
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

    def flows(
        self,
        point_key: str,
        start: date,
        end: date,
        direction: str = "entry",
        *,
        period_type: str = "day",
        indicator: str = "Physical Flow",
        limit: int = -1,
    ) -> pl.DataFrame:
        """Daily physical flows at network point ``point_key`` over ``[start, end]``.

        Queries ``indicator`` (default ``"Physical Flow"``) at ``period_type``
        granularity (default ``"day"``) for the given ``direction`` (``"entry"`` or
        ``"exit"``). Returns one row per record with columns
        ``[point, direction, date, value, unit]``; a missing flow value is a null.

        Args:
            point_key: The ENTSOG network point key.
            start: Query start date (inclusive).
            end: Query end date (inclusive).
            direction: ``"entry"`` or ``"exit"``.
            period_type: The ENTSOG ``periodType`` query parameter (default ``"day"``).
            indicator: The ENTSOG ``indicator`` query parameter (default
                ``"Physical Flow"``).
            limit: The ENTSOG ``limit`` query parameter (default ``-1``, meaning no
                provider-side limit).

        Raises:
            DataUnavailableError: If the provider returns no records for the query.
            RateLimitError: On HTTP 429.
            AuthenticationError: On HTTP 401/403 (unexpected for this keyless API).
            DataSourceError: On any other HTTP error or a malformed payload.
        """
        _require_https(self._base_url)
        params = {
            "indicator": indicator,
            "periodType": period_type,
            "pointKey": point_key,
            "directionKey": direction,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "limit": str(limit),
        }
        response = _http_get(
            self._transport,
            self._base_url,
            params,
            timeout_seconds=self._timeout_seconds,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        )
        _raise_for_status(self.provider, response.status_code)
        payload = _json_object(self.provider, response)
        records = payload.get("operationalData")
        if not isinstance(records, list) or not records:
            raise DataUnavailableError(
                f"{self.provider}: no flow data for point {point_key!r} "
                f"({direction}) in [{start.isoformat()}, {end.isoformat()}]"
            )
        points: list[str] = []
        directions: list[str] = []
        dates: list[date] = []
        values: list[float | None] = []
        units: list[str | None] = []
        for record in records:
            if not isinstance(record, dict):
                raise DataSourceError(f"{self.provider}: malformed flow record in payload")
            try:
                day = date.fromisoformat(str(record.get("periodFrom", ""))[:10])
            except ValueError as exc:
                raise DataSourceError(
                    f"{self.provider}: flow record has an invalid periodFrom date"
                ) from exc
            raw_value = record.get("value")
            raw_point_key = record.get("pointKey")
            raw_direction_key = record.get("directionKey")
            points.append(str(raw_point_key) if raw_point_key is not None else point_key)
            directions.append(
                str(raw_direction_key) if raw_direction_key is not None else direction
            )
            dates.append(day)
            values.append(float(raw_value) if raw_value is not None else None)
            units.append(str(record["unit"]) if record.get("unit") is not None else None)
        return pl.DataFrame(
            {
                "point": points,
                "direction": directions,
                "date": dates,
                "value": pl.Series(values, dtype=pl.Float64),
                "unit": units,
            }
        )
