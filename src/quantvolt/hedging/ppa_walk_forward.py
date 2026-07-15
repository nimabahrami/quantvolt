"""Leakage-safe repeated PPA nomination calibration and application."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import polars as pl

from .._validation import require_integer_at_least, require_non_empty, require_non_negative
from ..exceptions import ValidationError
from ..models.ppa import PpaContract
from .ppa_nomination import (
    PpaNominationColumns,
    PpaNominationFit,
    PpaNominationObjective,
    apply_ppa_nomination,
    calibrate_ppa_nomination,
)


@dataclass(frozen=True, slots=True)
class PpaWalkForwardResult:
    """All fitted windows and the row-level out-of-sample nomination trace."""

    fits: tuple[PpaNominationFit, ...]
    evaluation: pl.DataFrame

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation", self.evaluation.clone())


def walk_forward_ppa_nomination(
    contract: PpaContract,
    data: pl.DataFrame,
    rebalance_utc: Sequence[datetime],
    *,
    evaluation_end_utc: datetime,
    capacity_mwh_per_interval: float,
    columns: PpaNominationColumns | None = None,
    lookback: timedelta | None = None,
    objective: PpaNominationObjective = PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
    risk_aversion: float = 1.0,
    confidence_level: float = 0.95,
    grid_steps: int = 100,
) -> PpaWalkForwardResult:
    """Refit at each cutoff and apply only until the next cutoff.

    ``lookback=None`` uses an expanding window. A positive ``lookback`` uses a
    rolling window. Intervals crossing a rebalance boundary are rejected rather
    than assigned partly in-sample and partly out-of-sample.
    """
    if not isinstance(data, pl.DataFrame):
        raise ValidationError("data must be a polars DataFrame")
    require_non_empty("rebalance_utc", rebalance_utc)
    require_integer_at_least("grid_steps", grid_steps, 1)
    require_non_negative("risk_aversion", risk_aversion)
    if lookback is not None and lookback <= timedelta(0):
        raise ValidationError("lookback must be positive")
    cutoffs = tuple(rebalance_utc)
    dated_boundaries = [("rebalance_utc", cutoff) for cutoff in cutoffs]
    dated_boundaries.append(("evaluation_end_utc", evaluation_end_utc))
    for name, value in dated_boundaries:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValidationError(f"{name} values must be expressed in UTC")
    if tuple(sorted(cutoffs)) != cutoffs or len(set(cutoffs)) != len(cutoffs):
        raise ValidationError("rebalance_utc must be strictly increasing and unique")
    if evaluation_end_utc <= cutoffs[-1]:
        raise ValidationError("evaluation_end_utc must be after the final rebalance")
    columns = columns or PpaNominationColumns()
    required = {columns.interval_start_utc, columns.interval_end_utc}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValidationError(f"data is missing interval columns: {', '.join(missing)}")
    for cutoff in cutoffs:
        crossing = data.filter(
            (pl.col(columns.interval_start_utc) < cutoff)
            & (pl.col(columns.interval_end_utc) > cutoff)
        )
        if crossing.height:
            raise ValidationError(f"an interval crosses rebalance cutoff {cutoff!r}")

    fits: list[PpaNominationFit] = []
    evaluation_frames: list[pl.DataFrame] = []
    for fit_index, cutoff in enumerate(cutoffs):
        next_cutoff = cutoffs[fit_index + 1] if fit_index + 1 < len(cutoffs) else evaluation_end_utc
        calibration = data.filter(pl.col(columns.interval_end_utc) <= cutoff)
        if lookback is not None:
            calibration = calibration.filter(
                pl.col(columns.interval_start_utc) >= cutoff - lookback
            )
        evaluation = data.filter(
            (pl.col(columns.interval_start_utc) >= cutoff)
            & (pl.col(columns.interval_start_utc) < next_cutoff)
        )
        if evaluation.height == 0:
            raise ValidationError(f"no evaluation observations for cutoff {cutoff!r}")
        fit = calibrate_ppa_nomination(
            contract,
            calibration,
            calibration_end_utc=cutoff,
            capacity_mwh_per_interval=capacity_mwh_per_interval,
            columns=columns,
            objective=objective,
            risk_aversion=risk_aversion,
            confidence_level=confidence_level,
            grid_steps=grid_steps,
        )
        applied = apply_ppa_nomination(
            fit,
            evaluation,
            interval_start_column=columns.interval_start_utc,
            interval_end_column=columns.interval_end_utc,
            output_column="contracted_mwh",
        ).with_columns(
            pl.lit(fit_index).alias("walk_forward_fit_index"),
            pl.lit(cutoff).alias("walk_forward_calibration_end_utc"),
            pl.lit(calibration[columns.interval_start_utc].min()).alias(
                "walk_forward_calibration_start_utc"
            ),
        )
        fits.append(fit)
        evaluation_frames.append(applied)
    result = pl.concat(evaluation_frames, how="vertical")
    if result.height and not result[columns.interval_start_utc].is_sorted():
        raise AssertionError("walk-forward evaluation output lost chronological order")
    return PpaWalkForwardResult(tuple(fits), result)
