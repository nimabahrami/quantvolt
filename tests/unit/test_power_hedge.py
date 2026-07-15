"""Hand-computed realized power-hedge settlement tests."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    PowerDeliveryInterval,
    PowerHedgeContract,
    PowerHedgePosition,
    PowerHedgeType,
    settle_power_hedge_interval,
    settle_power_hedges_frame,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = _START + timedelta(hours=2)
_INTERVAL = PowerDeliveryInterval(_START, _START + timedelta(hours=1))


def _hedge(
    hedge_type: PowerHedgeType,
    *,
    position: PowerHedgePosition = PowerHedgePosition.LONG,
    strike: float = 70.0,
    upper: float | None = None,
    premium: float = 0.0,
) -> PowerHedgeContract:
    return PowerHedgeContract(
        hedge_id=f"{hedge_type.value}-{position.value}",
        hedge_type=hedge_type,
        position=position,
        start_utc=_START,
        end_utc=_END,
        volume_mwh=10.0,
        strike_per_mwh=strike,
        upper_strike_per_mwh=upper,
        allocated_premium_per_mwh=premium,
    )


@pytest.mark.parametrize(
    ("contract", "spot", "gross", "premium", "net"),
    [
        (_hedge(PowerHedgeType.FIXED_PRICE_SWAP), 100.0, -300.0, 0.0, -300.0),
        (_hedge(PowerHedgeType.FIXED_PRICE_SWAP), 40.0, 300.0, 0.0, 300.0),
        (_hedge(PowerHedgeType.CAP, premium=2.0), 100.0, 300.0, -20.0, 280.0),
        (_hedge(PowerHedgeType.FLOOR, premium=3.0), 40.0, 300.0, -30.0, 270.0),
        (_hedge(PowerHedgeType.COLLAR, strike=50.0, upper=90.0), 100.0, -100.0, 0.0, -100.0),
        (_hedge(PowerHedgeType.COLLAR, strike=50.0, upper=90.0), 40.0, 100.0, 0.0, 100.0),
        (
            _hedge(PowerHedgeType.FLOOR, position=PowerHedgePosition.SHORT, premium=3.0),
            40.0,
            -300.0,
            30.0,
            -270.0,
        ),
    ],
)
def test_realized_hedge_payoffs_by_hand(
    contract: PowerHedgeContract,
    spot: float,
    gross: float,
    premium: float,
    net: float,
) -> None:
    result = settle_power_hedge_interval(contract, _INTERVAL, spot)
    assert result.gross_payoff == gross
    assert result.premium_cashflow == premium
    assert result.net_cashflow == net
    assert result.gross_payoff + result.premium_cashflow == result.net_cashflow


def test_negative_power_price_is_supported() -> None:
    floor = _hedge(PowerHedgeType.FLOOR, strike=0.0)
    result = settle_power_hedge_interval(floor, _INTERVAL, -50.0)
    assert result.net_cashflow == 500.0


def test_frame_preserves_input_order_and_only_emits_active_hedges() -> None:
    first_only = PowerHedgeContract(
        hedge_id="first",
        hedge_type=PowerHedgeType.FLOOR,
        position=PowerHedgePosition.LONG,
        start_utc=_START,
        end_utc=_START + timedelta(hours=1),
        volume_mwh=2.0,
        strike_per_mwh=60.0,
    )
    both = _hedge(PowerHedgeType.CAP, strike=80.0)
    data = pl.DataFrame(
        {
            "start": [_START, _START + timedelta(hours=1)],
            "end": [_START + timedelta(hours=1), _END],
            "price": [50.0, 100.0],
        }
    )
    original = data.clone()

    result = settle_power_hedges_frame(
        [first_only, both],
        data,
        interval_start_column="start",
        interval_end_column="end",
        spot_price_column="price",
    )

    assert data.equals(original)
    assert result["input_row"].to_list() == [0, 0, 1]
    assert result["hedge_id"].to_list() == ["first", "cap-long", "cap-long"]
    assert result["net_cashflow"].to_list() == [20.0, 0.0, 200.0]


def test_contract_validation_rejects_ambiguous_terms() -> None:
    with pytest.raises(ValidationError, match="requires upper"):
        _hedge(PowerHedgeType.COLLAR)
    with pytest.raises(ValidationError, match="must exceed"):
        _hedge(PowerHedgeType.COLLAR, upper=60.0)
    with pytest.raises(ValidationError, match="only for a collar"):
        _hedge(PowerHedgeType.CAP, upper=90.0)


def test_frame_rejects_duplicate_ids_and_bad_market_data() -> None:
    hedge = _hedge(PowerHedgeType.FLOOR)
    data = pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_START + timedelta(hours=1)],
            "spot_price_per_mwh": [50.0],
        }
    )
    with pytest.raises(ValidationError, match="unique hedge_id"):
        settle_power_hedges_frame([hedge, hedge], data)
    with pytest.raises(ValidationError, match="spot_price_per_mwh"):
        settle_power_hedges_frame(
            [hedge], data.with_columns(pl.lit(float("nan")).alias("spot_price_per_mwh"))
        )
