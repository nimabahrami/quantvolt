"""Portfolio-level realized settlement for PPA and power-hedge positions."""

from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    BUILT_IN_COMMODITIES,
    DeliveryPeriod,
    FuturesContract,
    Portfolio,
    Position,
    PowerHedgeContract,
    PowerHedgeDataColumns,
    PowerHedgePosition,
    PowerHedgeType,
    PpaContract,
    PpaVolumeBasis,
    settle_energy_portfolio,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = _START + timedelta(hours=1)
_PPA = PpaContract(
    "ppa",
    "DE-LU",
    70.0,
    _START,
    _END,
    PpaVolumeBasis.BASELOAD,
)
_FLOOR = PowerHedgeContract(
    "floor",
    PowerHedgeType.FLOOR,
    PowerHedgePosition.LONG,
    _START,
    _END,
    2.0,
    80.0,
)
_FUTURE = FuturesContract(BUILT_IN_COMMODITIES["TTF"], DeliveryPeriod(2026, 1), 30.0, 10.0)


def _ppa_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_END],
            "contracted_mwh": [10.0],
            "metered_generation_mwh": [8.0],
            "spot_price_per_mwh": [50.0],
            "shortfall_price_per_mwh": [100.0],
            "excess_price_per_mwh": [40.0],
        }
    )


def _hedge_data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "interval_start_utc": [_START],
            "interval_end_utc": [_END],
            "spot_price_per_mwh": [50.0],
        }
    )


def test_portfolio_aggregates_ppa_and_separate_hedge_positions() -> None:
    ppa_position = Position(_PPA, position_id="ppa-pos")
    hedge_position = Position(_FLOOR, position_id="floor-pos")
    future_position = Position(_FUTURE, position_id="future-pos")
    portfolio = Portfolio((ppa_position, hedge_position, future_position), "energy-book")
    ppa_input = _ppa_data()
    hedge_input = _hedge_data()
    ppa_original = ppa_input.clone()
    hedge_original = hedge_input.clone()

    result = settle_energy_portfolio(
        portfolio,
        {"ppa-pos": ppa_input, "floor-pos": hedge_input},
    )

    assert ppa_input.equals(ppa_original)
    assert hedge_input.equals(hedge_original)
    assert [item.position for item in result.settled] == [ppa_position, hedge_position]
    assert [item.total_cashflow for item in result.settled] == [500.0, 60.0]
    assert result.total_cashflow == 560.0
    assert result.unsettled == (future_position,)


def test_interval_positions_require_unique_ids_and_complete_exact_data_mapping() -> None:
    with pytest.raises(ValidationError, match="require a non-empty position_id"):
        settle_energy_portfolio(Portfolio((Position(_PPA),)), {})

    duplicate = Portfolio(
        (Position(_PPA, position_id="same"), Position(_FLOOR, position_id="same"))
    )
    with pytest.raises(ValidationError, match="must be unique"):
        settle_energy_portfolio(duplicate, {"same": _ppa_data()})

    portfolio = Portfolio((Position(_PPA, position_id="ppa-pos"),))
    with pytest.raises(ValidationError, match="missing position_id"):
        settle_energy_portfolio(portfolio, {})
    with pytest.raises(ValidationError, match="unknown position_id"):
        settle_energy_portfolio(portfolio, {"ppa-pos": _ppa_data(), "typo": _ppa_data()})


def test_settled_position_defensively_copies_ledger() -> None:
    position = Position(_PPA, position_id="ppa-pos")
    result = settle_energy_portfolio(Portfolio((position,)), {"ppa-pos": _ppa_data()})
    ledger = result.settled[0].ledger
    modified = ledger.with_columns(pl.lit(-999.0).alias("net_cashflow"))
    assert modified["net_cashflow"].item() == -999.0
    assert result.settled[0].ledger["net_cashflow"].item() == 500.0


def test_portfolio_accepts_caller_column_mapping_for_hedge_data() -> None:
    position = Position(_FLOOR, position_id="floor-pos")
    caller_data = pl.DataFrame({"from": [_START], "to": [_END], "day_ahead": [50.0]})
    result = settle_energy_portfolio(
        Portfolio((position,)),
        {"floor-pos": caller_data},
        hedge_columns={
            "floor-pos": PowerHedgeDataColumns(
                interval_start_utc="from",
                interval_end_utc="to",
                spot_price_per_mwh="day_ahead",
            )
        },
    )
    assert result.total_cashflow == 60.0
