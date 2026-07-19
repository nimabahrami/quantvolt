"""Leakage-safe calibration of a constant physical-PPA nomination."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from enum import StrEnum

import numpy as np
import polars as pl

from .._validation import (
    require_finite,
    require_integer_at_least,
    require_non_empty,
    require_non_negative,
    require_positive,
)
from ..exceptions import ValidationError
from ..models.interval import PowerDeliveryInterval
from ..models.ppa import PpaContract, PpaSettlementType, PpaVolumeBasis


class PpaNominationObjective(StrEnum):
    """Transparent in-sample criterion used to select the nomination."""

    MAX_MEAN_CASHFLOW = "max_mean_cashflow"
    MAX_MEAN_MINUS_CFAR = "max_mean_minus_cfar"


@dataclass(frozen=True, slots=True)
class PpaNominationColumns:
    """Map caller-owned calibration columns to nomination inputs."""

    interval_start_utc: str = "interval_start_utc"
    interval_end_utc: str = "interval_end_utc"
    metered_generation_mwh: str = "metered_generation_mwh"
    shortfall_price_per_mwh: str = "shortfall_price_per_mwh"
    excess_price_per_mwh: str = "excess_price_per_mwh"

    def __post_init__(self) -> None:
        mappings = [(field.name, getattr(self, field.name)) for field in fields(self)]
        for field_name, column_name in mappings:
            require_non_empty(field_name, column_name)
        if len(mappings) != len({column_name for _, column_name in mappings}):
            raise ValidationError("PpaNominationColumns mappings must be distinct")


@dataclass(frozen=True, slots=True)
class PpaNominationCandidate:
    """Diagnostics for one candidate constant interval nomination."""

    contracted_mwh: float
    mean_cashflow: float
    lower_percentile_cashflow: float
    cfar: float
    objective_value: float


@dataclass(frozen=True, slots=True)
class PpaNominationFit:
    """Fitted nomination plus its immutable calibration audit trail."""

    contract_id: str
    calibration_end_utc: datetime
    calibration_rows: int
    delivery_interval_minutes: int
    capacity_mwh_per_interval: float
    selected_mwh_per_interval: float
    objective: PpaNominationObjective
    risk_aversion: float
    confidence_level: float
    candidates: tuple[PpaNominationCandidate, ...]


def _validate_calibration_data(
    data: pl.DataFrame,
    columns: PpaNominationColumns,
    calibration_end_utc: datetime,
) -> int:
    if not isinstance(data, pl.DataFrame):
        raise ValidationError(f"data must be a polars DataFrame, got {type(data).__name__}")
    if data.height == 0:
        raise ValidationError("calibration data must be non-empty")
    if calibration_end_utc.tzinfo is None or calibration_end_utc.utcoffset() is None:
        raise ValidationError("calibration_end_utc must be timezone-aware")
    if calibration_end_utc.utcoffset() != timedelta(0):
        raise ValidationError("calibration_end_utc must be expressed in UTC")
    required = {getattr(columns, field.name) for field in fields(columns)}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValidationError(f"calibration data is missing columns: {', '.join(missing)}")
    numeric = required - {columns.interval_start_utc, columns.interval_end_utc}
    non_numeric = sorted(name for name in numeric if not data.schema[name].is_numeric())
    if non_numeric:
        raise ValidationError(f"calibration columns must be numeric: {', '.join(non_numeric)}")
    nulls = data.select(pl.col(sorted(required)).null_count()).row(0)
    if any(nulls):
        raise ValidationError("calibration data contains null inputs")
    starts = data[columns.interval_start_utc]
    ends = data[columns.interval_end_utc]
    if starts.n_unique() != data.height:
        raise ValidationError("calibration data contains duplicate interval starts")
    if not starts.is_sorted():
        raise ValidationError("calibration intervals must be sorted")
    try:
        if any(end > calibration_end_utc for end in ends):
            raise ValidationError("calibration data extends beyond calibration_end_utc")
        durations = {
            PowerDeliveryInterval(start, end).duration_minutes
            for start, end in zip(starts, ends, strict=True)
        }
        if len(durations) != 1:
            raise ValidationError("calibration data mixes delivery interval durations")
    except TypeError as exc:
        raise ValidationError(
            "calibration interval timestamps must be timezone-compatible"
        ) from exc
    return durations.pop()


def calibrate_ppa_nomination(
    contract: PpaContract,
    calibration_data: pl.DataFrame,
    *,
    calibration_end_utc: datetime,
    capacity_mwh_per_interval: float,
    columns: PpaNominationColumns | None = None,
    objective: PpaNominationObjective = PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
    risk_aversion: float = 1.0,
    confidence_level: float = 0.95,
    grid_steps: int = 100,
) -> PpaNominationFit:
    """Fit a constant baseload nomination using calibration observations only.

    Candidate physical cash flow is
    ``q*fixed + max(g-q,0)*excess - max(q-g,0)*shortfall``.
    CFaR follows the package convention ``max(mean - lower_percentile, 0)``.
    Ties resolve to the smaller nomination, avoiding accidental over-contracting.
    """
    if contract.settlement_type is not PpaSettlementType.PHYSICAL:
        raise ValidationError("nomination calibration requires a physical PPA")
    if contract.volume_basis is not PpaVolumeBasis.BASELOAD:
        raise ValidationError("constant nomination calibration requires BASELOAD volume_basis")
    if not isinstance(objective, PpaNominationObjective):
        raise ValidationError(f"invalid objective: {objective!r}")
    require_positive("capacity_mwh_per_interval", capacity_mwh_per_interval)
    require_non_negative("risk_aversion", risk_aversion)
    if not 0.0 < confidence_level < 1.0:
        raise ValidationError("confidence_level must be in (0, 1)")
    require_integer_at_least("grid_steps", grid_steps, 1)
    columns = columns or PpaNominationColumns()
    interval_minutes = _validate_calibration_data(calibration_data, columns, calibration_end_utc)

    generation = calibration_data[columns.metered_generation_mwh].to_numpy().astype(float)
    shortfall_price = calibration_data[columns.shortfall_price_per_mwh].to_numpy().astype(float)
    excess_price = calibration_data[columns.excess_price_per_mwh].to_numpy().astype(float)
    for name, values in (
        ("metered_generation_mwh", generation),
        ("shortfall_price_per_mwh", shortfall_price),
        ("excess_price_per_mwh", excess_price),
    ):
        if not bool(np.all(np.isfinite(values))):
            raise ValidationError(f"calibration {name} must be finite")
    if bool(np.any(generation < 0.0)):
        raise ValidationError("calibration metered_generation_mwh must be >= 0")

    lower_percentile = (1.0 - confidence_level) * 100.0
    diagnostics: list[PpaNominationCandidate] = []
    for volume in np.linspace(0.0, capacity_mwh_per_interval, grid_steps + 1):
        cashflows = (
            volume * contract.fixed_price_per_mwh
            + np.maximum(generation - volume, 0.0) * excess_price
            - np.maximum(volume - generation, 0.0) * shortfall_price
        )
        mean = float(np.mean(cashflows))
        lower = float(np.percentile(cashflows, lower_percentile))
        cfar = max(mean - lower, 0.0)
        value = mean
        if objective is PpaNominationObjective.MAX_MEAN_MINUS_CFAR:
            value -= risk_aversion * cfar
        for name, result in (("mean_cashflow", mean), ("objective_value", value)):
            require_finite(name, result)
        diagnostics.append(PpaNominationCandidate(float(volume), mean, lower, cfar, value))
    selected = max(diagnostics, key=lambda item: (item.objective_value, -item.contracted_mwh))
    return PpaNominationFit(
        contract_id=contract.contract_id,
        calibration_end_utc=calibration_end_utc,
        calibration_rows=calibration_data.height,
        delivery_interval_minutes=interval_minutes,
        capacity_mwh_per_interval=capacity_mwh_per_interval,
        selected_mwh_per_interval=selected.contracted_mwh,
        objective=objective,
        risk_aversion=risk_aversion,
        confidence_level=confidence_level,
        candidates=tuple(diagnostics),
    )


def apply_ppa_nomination(
    fit: PpaNominationFit,
    evaluation_data: pl.DataFrame,
    *,
    interval_start_column: str = "interval_start_utc",
    interval_end_column: str = "interval_end_utc",
    output_column: str = "contracted_mwh",
) -> pl.DataFrame:
    """Add the fitted volume to strictly out-of-sample caller observations."""
    if not isinstance(evaluation_data, pl.DataFrame):
        raise ValidationError("evaluation_data must be a polars DataFrame")
    require_non_empty("interval_start_column", interval_start_column)
    require_non_empty("interval_end_column", interval_end_column)
    require_non_empty("output_column", output_column)
    missing = sorted({interval_start_column, interval_end_column} - set(evaluation_data.columns))
    if missing:
        raise ValidationError(f"evaluation data is missing columns: {', '.join(missing)}")
    if interval_start_column == interval_end_column:
        raise ValidationError("evaluation interval column mappings must be distinct")
    if output_column in evaluation_data.columns:
        raise ValidationError(f"evaluation data already contains output column: {output_column}")
    if evaluation_data.height == 0:
        raise ValidationError("evaluation data must be non-empty")
    starts = evaluation_data[interval_start_column]
    ends = evaluation_data[interval_end_column]
    if starts.null_count() or ends.null_count():
        raise ValidationError("evaluation interval timestamps contain nulls")
    try:
        for start, end in zip(starts, ends, strict=True):
            interval = PowerDeliveryInterval(start, end)
            if interval.duration_minutes != fit.delivery_interval_minutes:
                raise ValidationError(
                    "evaluation interval duration differs from calibrated duration"
                )
            if start < fit.calibration_end_utc:
                raise ValidationError(
                    "evaluation data begins before calibration_end_utc (look-ahead)"
                )
    except TypeError as exc:
        raise ValidationError("evaluation timestamps must be timezone-compatible") from exc
    return evaluation_data.with_columns(pl.lit(fit.selected_mwh_per_interval).alias(output_column))
