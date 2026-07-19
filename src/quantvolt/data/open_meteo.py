"""Open-Meteo (free, keyless) — daily temperatures for the weather module.

Open-Meteo is **keyless**: no token is required and none is ever transmitted. A
``Credentials`` object is still accepted (and ``QUANTVOLT_OPEN_METEO_TOKEN`` read) purely for
constructor uniformity with the other adapters — it is optional and unused.

:meth:`OpenMeteoSource.temperatures` queries the historical archive API for the daily mean
2-metre temperature (``daily=temperature_2m_mean``) and returns a ``pl.DataFrame`` with
columns ``[location, date, temp_celsius]`` — exactly the shape
:func:`quantvolt.market.weather.degree_days` consumes, so fetched and caller-supplied
temperature data are interchangeable.

Open-Meteo is a weather source: this adapter exposes no ``forward_curve`` method.
Tests use ``httpx.MockTransport`` — no live calls in CI.
"""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl

from ..exceptions import DataSourceError, DataUnavailableError, ValidationError
from .base import (
    Credentials,
    _http_get,
    _json_object,
    _raise_for_status,
    _require_https,
    _validate_retry_config,
)

_BASE_URL = "https://archive-api.open-meteo.com/v1/archive"
_TIMEOUT_SECONDS = 30.0


def _parse_location(location: str) -> tuple[float, float]:
    """Parse a ``"lat,lon"`` location string into ``(latitude, longitude)`` floats."""
    parts = location.split(",")
    if len(parts) != 2:
        raise ValidationError(f'location must be "lat,lon" (e.g. "52.37,4.90"), got {location!r}')
    try:
        latitude, longitude = float(parts[0]), float(parts[1])
    except ValueError:
        raise ValidationError(
            f'location must be "lat,lon" with numeric parts, got {location!r}'
        ) from None
    if not -90.0 <= latitude <= 90.0:
        raise ValidationError(f"location latitude must be in [-90, 90], got {latitude}")
    if not -180.0 <= longitude <= 180.0:
        raise ValidationError(f"location longitude must be in [-180, 180], got {longitude}")
    return latitude, longitude


class OpenMeteoSource:
    """Keyless Open-Meteo adapter: daily mean temperatures as a ``pl.DataFrame``.

    No ``forward_curve`` method — free sources are never forward-curve sources.
    """

    provider = "open_meteo"

    def __init__(
        self,
        credentials: Credentials | None = None,
        transport: httpx.BaseTransport | None = None,
        *,
        base_url: str = _BASE_URL,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        max_retries: int = 0,
        backoff_seconds: float = 1.0,
        daily_variable: str = "temperature_2m_mean",
        timezone: str = "UTC",
    ) -> None:
        """Open-Meteo needs no credential; ``credentials`` is optional and never transmitted.

        ``transport`` exists for tests (``httpx.MockTransport``); ``None`` uses real HTTPS.

        Args:
            base_url: The Open-Meteo archive endpoint (default the production API).
            timeout_seconds: Per-request HTTP timeout (default ``30.0``); must be ``> 0``.
            max_retries: Retries on a transient failure (connection error, HTTP 5xx/429)
                before giving up (default ``0``, i.e. today's single-attempt behaviour);
                must be ``>= 0``. Non-transient errors are never retried.
            backoff_seconds: Base of the deterministic exponential backoff between
                retries, ``backoff_seconds * 2**attempt`` (default ``1.0``); must be
                ``>= 0``.
            daily_variable: The Open-Meteo ``daily`` query variable requested and parsed
                from the response (default ``"temperature_2m_mean"``).
            timezone: The Open-Meteo ``timezone`` query parameter (default ``"UTC"``).
        """
        _validate_retry_config(timeout_seconds, max_retries, backoff_seconds)
        self._credentials = credentials or Credentials.from_env("open_meteo")
        self._transport = transport
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._daily_variable = daily_variable
        self._timezone = timezone

    def temperatures(self, location: str, start: date, end: date) -> pl.DataFrame:
        """Daily mean temperatures for ``location`` (``"lat,lon"``) over ``[start, end]``.

        Returns a frame with columns ``[location, date, temp_celsius]`` (days the provider
        reports no value are dropped), directly consumable by
        :func:`quantvolt.market.weather.degree_days`.

        Raises:
            ValidationError: If ``location`` is not a valid ``"lat,lon"`` string.
            DataUnavailableError: If the provider reports no temperatures for the query.
            RateLimitError: On HTTP 429.
            DataSourceError: On any other HTTP error or a malformed payload.
        """
        latitude, longitude = _parse_location(location)
        _require_https(self._base_url)
        params = {
            "latitude": f"{latitude}",
            "longitude": f"{longitude}",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": self._daily_variable,
            "timezone": self._timezone,
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
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            raise DataUnavailableError(
                f"{self.provider}: no daily temperature data for location {location!r} "
                f"in [{start.isoformat()}, {end.isoformat()}]"
            )
        days = daily.get("time")
        temps = daily.get(self._daily_variable)
        if not isinstance(days, list) or not isinstance(temps, list):
            raise DataSourceError(f"{self.provider}: malformed daily payload")
        if len(days) != len(temps):
            raise DataSourceError(
                f"{self.provider}: daily payload lengths differ "
                f"({len(days)} dates vs {len(temps)} temperatures)"
            )
        locations: list[str] = []
        dates: list[date] = []
        values: list[float] = []
        for day, temp in zip(days, temps, strict=True):
            if temp is None:
                continue
            try:
                parsed_day = date.fromisoformat(str(day))
            except ValueError as exc:
                raise DataSourceError(
                    f"{self.provider}: daily payload has an invalid date"
                ) from exc
            locations.append(location)
            dates.append(parsed_day)
            values.append(float(temp))
        if not values:
            raise DataUnavailableError(
                f"{self.provider}: no temperatures reported for location {location!r} "
                f"in [{start.isoformat()}, {end.isoformat()}]"
            )
        return pl.DataFrame({"location": locations, "date": dates, "temp_celsius": values})
