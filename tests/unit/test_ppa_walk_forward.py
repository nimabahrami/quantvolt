"""Repeated PPA nomination calibration without future leakage."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    PpaContract,
    PpaNominationColumns,
    PpaNominationObjective,
    PpaVolumeBasis,
    walk_forward_ppa_nomination,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2025, 1, 1, tzinfo=UTC)


def _data() -> pl.DataFrame:
    starts = [_START + timedelta(hours=i) for i in range(6)]
    return pl.DataFrame(
        {
            "from": starts,
            "to": [start + timedelta(hours=1) for start in starts],
            "generation": [0.0, 2.0, 0.0, 0.0, 2.0, 2.0],
            "short": [80.0] * 6,
            "excess": [40.0] * 6,
        }
    )


_COLUMNS = PpaNominationColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    metered_generation_mwh="generation",
    shortfall_price_per_mwh="short",
    excess_price_per_mwh="excess",
)


def _contract() -> PpaContract:
    return PpaContract(
        "ppa",
        "DE-LU",
        70.0,
        _START,
        _START + timedelta(days=1),
        PpaVolumeBasis.BASELOAD,
    )


def test_expanding_walk_forward_refits_and_labels_every_evaluation_row() -> None:
    source = _data()
    original = source.clone()
    result = walk_forward_ppa_nomination(
        _contract(),
        source,
        [_START + timedelta(hours=2), _START + timedelta(hours=4)],
        evaluation_end_utc=_START + timedelta(hours=6),
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
        objective=PpaNominationObjective.MAX_MEAN_CASHFLOW,
        grid_steps=2,
    )
    assert source.equals(original)
    assert len(result.fits) == 2
    assert [fit.calibration_rows for fit in result.fits] == [2, 4]
    assert result.evaluation["walk_forward_fit_index"].to_list() == [0, 0, 1, 1]
    assert result.evaluation["contracted_mwh"].to_list() == [2.0, 2.0, 0.0, 0.0]


def test_rolling_lookback_limits_each_fit_sample() -> None:
    result = walk_forward_ppa_nomination(
        _contract(),
        _data(),
        [_START + timedelta(hours=2), _START + timedelta(hours=4)],
        evaluation_end_utc=_START + timedelta(hours=6),
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
        lookback=timedelta(hours=2),
        grid_steps=2,
    )
    assert [fit.calibration_rows for fit in result.fits] == [2, 2]


def test_rebalance_boundaries_must_be_ordered_utc_and_have_evaluation_rows() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        walk_forward_ppa_nomination(
            _contract(),
            _data(),
            [_START + timedelta(hours=4), _START + timedelta(hours=2)],
            evaluation_end_utc=_START + timedelta(hours=6),
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )
    with pytest.raises(ValidationError, match="expressed in UTC"):
        walk_forward_ppa_nomination(
            _contract(),
            _data(),
            [datetime(2025, 1, 1, 2)],
            evaluation_end_utc=_START + timedelta(hours=6),
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )


def test_interval_crossing_rebalance_is_rejected() -> None:
    crossing = _data().with_columns(
        pl.when(pl.int_range(pl.len()) == 1)
        .then(pl.col("to") + timedelta(minutes=30))
        .otherwise(pl.col("to"))
        .alias("to")
    )
    with pytest.raises(ValidationError, match="crosses rebalance"):
        walk_forward_ppa_nomination(
            _contract(),
            crossing,
            [_START + timedelta(hours=2)],
            evaluation_end_utc=_START + timedelta(hours=6),
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )
