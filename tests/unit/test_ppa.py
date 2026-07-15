"""Hand-computed PPA settlement and realised power-option cash flows."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from quantvolt import (
    MissingImbalancePricePolicy,
    PowerDeliveryInterval,
    PowerHedgeContract,
    PowerHedgePosition,
    PowerHedgeType,
    PpaContract,
    PpaDataColumns,
    PpaSettlementType,
    PpaVolumeBasis,
    power_cap_payoff,
    power_floor_payoff,
    settle_ppa_frame,
    settle_ppa_interval,
)
from quantvolt.exceptions import ValidationError

_START = datetime(2026, 1, 1, tzinfo=UTC)
_END = _START + timedelta(days=1)
_INTERVAL = PowerDeliveryInterval(_START, _START + timedelta(hours=1))


def _contract(
    *,
    volume_basis: PpaVolumeBasis = PpaVolumeBasis.BASELOAD,
    settlement_type: PpaSettlementType = PpaSettlementType.PHYSICAL,
) -> PpaContract:
    return PpaContract(
        contract_id="ppa-1",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=70.0,
        start_utc=_START,
        end_utc=_END,
        volume_basis=volume_basis,
        settlement_type=settlement_type,
    )


def test_physical_shortfall_cashflow_reconciles_by_hand() -> None:
    # Contract 10 MWh at 70; generate 8; buy 2 short at 100.
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=8.0,
        spot_price_per_mwh=90.0,
        shortfall_price_per_mwh=100.0,
        hedge_cashflow=30.0,
        option_payoff=20.0,
        option_premium=5.0,
        variable_cost=80.0,
        transaction_cost=2.0,
    )

    assert result.own_generation_delivered_mwh == 8.0
    assert result.shortfall_mwh == 2.0
    assert result.excess_mwh == 0.0
    assert result.ppa_cashflow == 700.0
    assert result.imbalance_cashflow == -200.0
    assert result.net_cashflow == 700.0 - 200.0 + 30.0 + 20.0 - 5.0 - 80.0 - 2.0
    assert result.component_sum == result.net_cashflow


def test_physical_excess_generation_is_sold_at_explicit_price() -> None:
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=12.0,
        spot_price_per_mwh=50.0,
        excess_price_per_mwh=45.0,
    )

    assert result.shortfall_mwh == 0.0
    assert result.excess_mwh == 2.0
    assert result.ppa_cashflow == 700.0
    assert result.spot_cashflow == 90.0
    assert result.net_cashflow == 790.0


def test_negative_spot_price_flows_through_without_log_normal_assumption() -> None:
    result = settle_ppa_interval(
        _contract(),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=12.0,
        spot_price_per_mwh=-50.0,
    )

    assert result.spot_cashflow == -100.0
    assert result.net_cashflow == 600.0
    assert power_floor_payoff(-50.0, 0.0, 2.0) == 100.0
    assert power_cap_payoff(-50.0, 0.0, 2.0) == 0.0


def test_financial_cfd_equals_fixed_revenue_when_generation_matches_volume() -> None:
    result = settle_ppa_interval(
        _contract(settlement_type=PpaSettlementType.FINANCIAL_CFD),
        _INTERVAL,
        contracted_mwh=10.0,
        metered_generation_mwh=10.0,
        spot_price_per_mwh=100.0,
    )

    assert result.spot_cashflow == 1_000.0
    assert result.ppa_cashflow == -300.0
    assert result.net_cashflow == 700.0
    assert result.shortfall_mwh == result.excess_mwh == 0.0


def test_pay_as_produced_requires_metered_volume() -> None:
    with pytest.raises(ValidationError, match="pay_as_produced"):
        settle_ppa_interval(
            _contract(volume_basis=PpaVolumeBasis.PAY_AS_PRODUCED),
            _INTERVAL,
            contracted_mwh=10.0,
            metered_generation_mwh=9.0,
            spot_price_per_mwh=50.0,
        )


def test_interval_outside_term_and_negative_volume_are_rejected() -> None:
    outside = PowerDeliveryInterval(_END, _END + timedelta(hours=1))
    with pytest.raises(ValidationError, match="outside PPA term"):
        settle_ppa_interval(
            _contract(),
            outside,
            contracted_mwh=1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=50.0,
        )
    with pytest.raises(ValidationError, match="contracted_mwh"):
        settle_ppa_interval(
            _contract(),
            _INTERVAL,
            contracted_mwh=-1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=50.0,
        )


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_market_inputs_are_rejected(bad: float) -> None:
    with pytest.raises(ValidationError, match="spot_price_per_mwh"):
        settle_ppa_interval(
            _contract(),
            _INTERVAL,
            contracted_mwh=1.0,
            metered_generation_mwh=1.0,
            spot_price_per_mwh=bad,
        )


def _caller_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "from": [_START, _START + timedelta(hours=1)],
            "to": [_START + timedelta(hours=1), _START + timedelta(hours=2)],
            "nomination": [10.0, 10.0],
            "meter": [8.0, 12.0],
            "day_ahead": [90.0, 50.0],
            "buy_imbalance": [100.0, 110.0],
            "sell_imbalance": [40.0, 45.0],
        }
    )


_CALLER_COLUMNS = PpaDataColumns(
    interval_start_utc="from",
    interval_end_utc="to",
    contracted_mwh="nomination",
    metered_generation_mwh="meter",
    spot_price_per_mwh="day_ahead",
    shortfall_price_per_mwh="buy_imbalance",
    excess_price_per_mwh="sell_imbalance",
)


def test_frame_settlement_accepts_caller_column_mapping_and_reconciles() -> None:
    source = _caller_frame()
    original = source.clone()

    ledger = settle_ppa_frame(_contract(), source, columns=_CALLER_COLUMNS)

    assert source.equals(original)
    assert ledger["input_row"].to_list() == [0, 1]
    assert ledger["shortfall_mwh"].to_list() == [2.0, 0.0]
    assert ledger["excess_mwh"].to_list() == [0.0, 2.0]
    assert ledger["net_cashflow"].to_list() == [500.0, 790.0]
    component_sum = ledger.select(
        pl.col("ppa_cashflow")
        + pl.col("spot_cashflow")
        + pl.col("imbalance_cashflow")
        + pl.col("hedge_cashflow")
        + pl.col("option_payoff")
        - pl.col("option_premium")
        - pl.col("variable_cost")
        - pl.col("transaction_cost")
    ).to_series()
    assert component_sum.equals(ledger["net_cashflow"])


def test_physical_frame_requires_real_imbalance_prices_by_default() -> None:
    data = _caller_frame().drop("buy_imbalance", "sell_imbalance")

    with pytest.raises(ValidationError, match="missing required columns"):
        settle_ppa_frame(_contract(), data, columns=_CALLER_COLUMNS)

    ledger = settle_ppa_frame(
        _contract(),
        data,
        columns=_CALLER_COLUMNS,
        imbalance_policy=MissingImbalancePricePolicy.USE_SPOT,
    )
    assert ledger["net_cashflow"].to_list() == [520.0, 800.0]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda frame: frame.reverse(), "sorted"),
        (lambda frame: pl.concat([frame, frame.head(1)]), "duplicate"),
        (
            lambda frame: frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 1)
                .then(pl.col("from") + timedelta(minutes=15))
                .otherwise(pl.col("from"))
                .alias("from")
            ),
            "gap or overlap",
        ),
        (
            lambda frame: frame.with_columns(
                pl.when(pl.int_range(pl.len()) == 0)
                .then(None)
                .otherwise(pl.col("meter"))
                .alias("meter")
            ),
            "nulls",
        ),
    ],
)
def test_frame_rejects_unsafe_alignment(
    mutate: Callable[[pl.DataFrame], pl.DataFrame], message: str
) -> None:
    bad = mutate(_caller_frame())
    with pytest.raises(ValidationError, match=message):
        settle_ppa_frame(_contract(), bad, columns=_CALLER_COLUMNS)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_frame_rejects_non_finite_user_volumes(bad: float) -> None:
    data = _caller_frame().with_columns(pl.lit(bad).alias("meter"))
    with pytest.raises(ValidationError, match="metered_generation_mwh"):
        settle_ppa_frame(_contract(), data, columns=_CALLER_COLUMNS)


def test_frame_rejects_non_numeric_columns_and_invalid_policy() -> None:
    text_prices = _caller_frame().with_columns(pl.col("day_ahead").cast(pl.String))
    with pytest.raises(ValidationError, match="must be numeric"):
        settle_ppa_frame(_contract(), text_prices, columns=_CALLER_COLUMNS)
    with pytest.raises(ValidationError, match="invalid imbalance_policy"):
        settle_ppa_frame(
            _contract(),
            _caller_frame(),
            columns=_CALLER_COLUMNS,
            imbalance_policy="error",  # type: ignore[arg-type]
        )


def test_column_mapping_must_be_unambiguous() -> None:
    with pytest.raises(ValidationError, match="distinct column names"):
        PpaDataColumns(contracted_mwh="energy", metered_generation_mwh="energy")


def test_contract_rejects_non_finite_fixed_price() -> None:
    with pytest.raises(ValidationError, match="fixed_price_per_mwh"):
        PpaContract(
            contract_id="bad",
            bidding_zone="DE-LU",
            fixed_price_per_mwh=float("nan"),
            start_utc=_START,
            end_utc=_END,
            volume_basis=PpaVolumeBasis.BASELOAD,
        )


def test_typed_hedge_flows_into_ppa_ledger_without_double_counting() -> None:
    floor = PowerHedgeContract(
        hedge_id="revenue-floor",
        hedge_type=PowerHedgeType.FLOOR,
        position=PowerHedgePosition.LONG,
        start_utc=_START,
        end_utc=_END,
        volume_mwh=10.0,
        strike_per_mwh=80.0,
        allocated_premium_per_mwh=2.0,
    )
    ledger = settle_ppa_frame(
        _contract(), _caller_frame(), columns=_CALLER_COLUMNS, hedges=[floor]
    )
    assert ledger["hedge_cashflow"].to_list() == [-20.0, 280.0]
    assert ledger["net_cashflow"].to_list() == [480.0, 1_070.0]

    with pytest.raises(ValidationError, match="double count"):
        settle_ppa_frame(
            _contract(),
            _caller_frame().with_columns(pl.lit(1.0).alias("manual_hedge")),
            columns=PpaDataColumns(
                interval_start_utc="from",
                interval_end_utc="to",
                contracted_mwh="nomination",
                metered_generation_mwh="meter",
                spot_price_per_mwh="day_ahead",
                shortfall_price_per_mwh="buy_imbalance",
                excess_price_per_mwh="sell_imbalance",
                hedge_cashflow="manual_hedge",
            ),
            hedges=[floor],
        )
