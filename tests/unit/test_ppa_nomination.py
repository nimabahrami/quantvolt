"""Leakage guards and hand-computed PPA nomination objectives."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    PpaContract,
    PpaNominationColumns,
    PpaNominationObjective,
    PpaSettlementType,
    PpaVolumeBasis,
    apply_ppa_nomination,
    calibrate_ppa_nomination,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2025, 1, 1, tzinfo=UTC)
_CUTOFF = _START + timedelta(hours=2)
_END = _START + timedelta(days=1)


def _contract() -> PpaContract:
    return PpaContract(
        contract_id="ppa",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_END,
        volume_basis=PpaVolumeBasis.BASELOAD,
    )


def _calibration() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "from": [_START, _START + timedelta(hours=1)],
            "to": [_START + timedelta(hours=1), _CUTOFF],
            "meter": [0.0, 2.0],
            "short_buy": [80.0, 80.0],
            "excess_sell": [40.0, 40.0],
        }
    )


_COLUMNS = PpaNominationColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    metered_generation_mwh="meter",
    shortfall_price_per_mwh="short_buy",
    excess_price_per_mwh="excess_sell",
)


def test_mean_objective_selects_hand_computed_profit_maximum() -> None:
    fit = calibrate_ppa_nomination(
        _contract(),
        _calibration(),
        calibration_end_utc=_CUTOFF,
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
        objective=PpaNominationObjective.MAX_MEAN_CASHFLOW,
        grid_steps=2,
    )
    assert [candidate.mean_cashflow for candidate in fit.candidates] == [40.0, 50.0, 60.0]
    assert fit.selected_mwh_per_interval == 2.0
    assert fit.calibration_rows == 2
    assert fit.delivery_interval_minutes == 60


def test_cfar_penalty_can_reduce_over_nomination() -> None:
    fit = calibrate_ppa_nomination(
        _contract(),
        _calibration(),
        calibration_end_utc=_CUTOFF,
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
        objective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
        risk_aversion=1.0,
        confidence_level=0.75,
        grid_steps=2,
    )
    assert [candidate.cfar for candidate in fit.candidates] == [20.0, 30.0, 40.0]
    assert [candidate.objective_value for candidate in fit.candidates] == [20.0, 20.0, 20.0]
    assert fit.selected_mwh_per_interval == 0.0  # conservative tie-break


def test_apply_is_out_of_sample_and_does_not_mutate_input() -> None:
    fit = calibrate_ppa_nomination(
        _contract(),
        _calibration(),
        calibration_end_utc=_CUTOFF,
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
        grid_steps=2,
    )
    evaluation = pl.DataFrame(
        {
            "delivery": [_CUTOFF, _CUTOFF + timedelta(hours=1)],
            "delivery_end": [
                _CUTOFF + timedelta(hours=1),
                _CUTOFF + timedelta(hours=2),
            ],
        }
    )
    original = evaluation.clone()
    result = apply_ppa_nomination(
        fit,
        evaluation,
        interval_start_column="delivery",
        interval_end_column="delivery_end",
        output_column="nomination",
    )
    assert evaluation.equals(original)
    assert result["nomination"].to_list() == [fit.selected_mwh_per_interval] * 2

    leaked = pl.DataFrame(
        {
            "delivery": [_CUTOFF - timedelta(hours=1)],
            "delivery_end": [_CUTOFF],
        }
    )
    with pytest.raises(ValidationError, match="look-ahead"):
        apply_ppa_nomination(
            fit,
            leaked,
            interval_start_column="delivery",
            interval_end_column="delivery_end",
        )


def test_apply_rejects_resolution_change() -> None:
    fit = calibrate_ppa_nomination(
        _contract(),
        _calibration(),
        calibration_end_utc=_CUTOFF,
        capacity_mwh_per_interval=2.0,
        columns=_COLUMNS,
    )
    quarter_hour = pl.DataFrame(
        {
            "start": [_CUTOFF],
            "end": [_CUTOFF + timedelta(minutes=15)],
        }
    )
    with pytest.raises(ValidationError, match="duration differs"):
        apply_ppa_nomination(
            fit,
            quarter_hour,
            interval_start_column="start",
            interval_end_column="end",
        )


def test_calibration_rejects_rows_after_declared_cutoff() -> None:
    data = _calibration().with_columns(
        pl.when(pl.int_range(pl.len()) == 1)
        .then(pl.col("to") + timedelta(minutes=15))
        .otherwise(pl.col("to"))
        .alias("to")
    )
    with pytest.raises(ValidationError, match="extends beyond"):
        calibrate_ppa_nomination(
            _contract(),
            data,
            calibration_end_utc=_CUTOFF,
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )


def test_calibration_rejects_mixed_interval_resolutions() -> None:
    mixed = _calibration().with_columns(
        pl.when(pl.int_range(pl.len()) == 0)
        .then(pl.col("from") + timedelta(minutes=15))
        .otherwise(pl.col("from"))
        .alias("from")
    )
    with pytest.raises(ValidationError, match="mixes delivery interval durations"):
        calibrate_ppa_nomination(
            _contract(),
            mixed,
            calibration_end_utc=_CUTOFF,
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )


@pytest.mark.parametrize(
    "contract",
    [
        PpaContract(
            contract_id="cfd",
            bidding_zone="DE-LU",
            fixed_price_per_mwh=70.0,
            start_utc=_START,
            end_utc=_END,
            volume_basis=PpaVolumeBasis.BASELOAD,
            settlement_type=PpaSettlementType.FINANCIAL_CFD,
        ),
        PpaContract(
            contract_id="pap",
            bidding_zone="DE-LU",
            fixed_price_per_mwh=70.0,
            start_utc=_START,
            end_utc=_END,
            volume_basis=PpaVolumeBasis.PAY_AS_PRODUCED,
        ),
    ],
)
def test_calibration_rejects_inapplicable_contract(contract: PpaContract) -> None:
    with pytest.raises(ValidationError, match=r"physical PPA|BASELOAD"):
        calibrate_ppa_nomination(
            contract,
            _calibration(),
            calibration_end_utc=_CUTOFF,
            capacity_mwh_per_interval=2.0,
            columns=_COLUMNS,
        )


def test_non_finite_and_negative_generation_fail_loudly() -> None:
    for bad in (float("nan"), -1.0):
        data = _calibration().with_columns(pl.lit(bad).alias("meter"))
        with pytest.raises(ValidationError, match="metered_generation_mwh"):
            calibrate_ppa_nomination(
                _contract(),
                data,
                calibration_end_utc=_CUTOFF,
                capacity_mwh_per_interval=2.0,
                columns=_COLUMNS,
            )
