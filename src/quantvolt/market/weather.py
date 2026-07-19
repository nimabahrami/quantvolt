"""Weather / degree days. Pure computation — caller supplies temperature data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from .._validation import require_non_empty
from ..exceptions import ValidationError

if TYPE_CHECKING:
    import polars as pl

_REQUIRED_COLUMNS = ("location", "date", "temp_celsius")


def _degree_days(deviation: float) -> float:
    """``max(0, deviation)`` — the shared degree-day clip, applied to a signed deviation.

    ``heating_degree_days`` passes ``base - temp`` and ``cooling_degree_days`` passes
    ``temp - base``; this is the one place the ``max(0, ...)`` formula is written.
    """
    return max(0.0, deviation)


@dataclass(frozen=True, slots=True)
class TemperatureData:
    """A single location/day temperature observation.

    ``base_celsius`` is the degree-day base temperature used by
    :attr:`heating_degree_days` / :attr:`cooling_degree_days` (default 18.0 °C, the
    same default as :func:`degree_days`).
    """

    location: str
    day: date
    temp_celsius: float
    temp_normal: float
    base_celsius: float = 18.0

    @property
    def heating_degree_days(self) -> float:
        return _degree_days(self.base_celsius - self.temp_celsius)

    @property
    def cooling_degree_days(self) -> float:
        return _degree_days(self.temp_celsius - self.base_celsius)


def degree_days(temperatures: pl.DataFrame, base_celsius: float = 18.0) -> pl.DataFrame:
    """Compute heating- and cooling-degree-days from caller-supplied temperature data.

    The library performs no fetching or I/O — temperature data is passed in. Degree days
    feed load/seasonality analysis and stress-scenario generation downstream.

    Args:
        temperatures: Frame with columns ``location``, ``date``, ``temp_celsius``.
        base_celsius: Degree-day base temperature (default 18.0 °C).

    Returns:
        A new frame (input is never mutated) with the input columns plus
        ``hdd = max(0, base_celsius - temp_celsius)`` and
        ``cdd = max(0, temp_celsius - base_celsius)``.

    Raises:
        ValidationError: If a required column is missing, or ``temperatures`` is empty.
    """
    import polars as pl

    for column in _REQUIRED_COLUMNS:
        if column not in temperatures.columns:
            raise ValidationError(
                f"temperatures is missing required column {column!r} "
                f"(required: {list(_REQUIRED_COLUMNS)}, got: {temperatures.columns})"
            )
    require_non_empty("temperatures", temperatures)

    temp = pl.col("temp_celsius")
    return temperatures.with_columns(
        (base_celsius - temp).clip(lower_bound=0.0).alias("hdd"),
        (temp - base_celsius).clip(lower_bound=0.0).alias("cdd"),
    )
