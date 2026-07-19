"""Short-side correctness properties (design Properties 104-105;
`.kiro/specs/short-side-instruments/` Tasks 3).

Each test is tagged with its design Property number and runs the default Hypothesis
profile (``quantvolt`` in ``tests/conftest.py``, 100 examples, no deadline).

- **Property 104 — side sign-flip parity (SHORT == -LONG exactly, all fields).** For any
  valid ``FuturesContract`` / ``ForwardContract`` / ``SwapContract`` and consistent
  ``MarketData``, the SHORT ``PricedPosition`` equals the LONG one with ``npv`` and every
  ``delta`` entry negated and ``reference_prices`` identical (unscaled).
- **Property 105 — long/short netting.** A two-position portfolio holding the same contract
  once LONG and once SHORT nets to ``total_npv == 0.0`` and an ``aggregate_delta`` of ``0.0``
  in every cell.
"""

from __future__ import annotations

import dataclasses
from datetime import date

from hypothesis import given
from hypothesis import strategies as st

from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    ForwardContract,
    FuturesContract,
    OptionSide,
    SwapContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.portfolio.model import Portfolio, Position
from quantvolt.portfolio.valuation import MarketData, value_portfolio
from quantvolt.risk.aggregation import aggregate_delta

TTF = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
VALUATION_DATE = date(2025, 12, 1)
PERIODS = tuple(DeliveryPeriod(2026, month) for month in range(1, 7))

_PRICES = st.floats(min_value=-500.0, max_value=1_000.0)
_NOTIONALS = st.floats(min_value=0.01, max_value=10_000.0)


def _market_data(forward_prices: dict[DeliveryPeriod, float]) -> MarketData:
    """A MarketData whose TTF curve carries the drawn forward per period and whose discount
    curve covers every period's settlement (last) day."""
    curve = ForwardCurve(
        commodity=TTF,
        market_date=VALUATION_DATE,
        nodes=tuple(CurveNode(period, forward_prices[period], "observed") for period in PERIODS),
    )
    # Strictly decreasing discount factors in (0, 1], one tenor per period's last day.
    tenors = tuple(period.last_day for period in PERIODS)
    factors = tuple(0.99 - 0.01 * index for index in range(len(PERIODS)))
    discount_curve = DiscountCurve(reference_date=VALUATION_DATE, tenors=tenors, factors=factors)
    return MarketData(
        forward_curves={"TTF": curve},
        discount_curve=discount_curve,
        valuation_date=VALUATION_DATE,
    )


@st.composite
def _forward_prices(draw: st.DrawFn) -> dict[DeliveryPeriod, float]:
    return {period: draw(_PRICES) for period in PERIODS}


@st.composite
def _futures_cases(
    draw: st.DrawFn,
) -> tuple[FuturesContract | ForwardContract, MarketData]:
    forward_prices = draw(_forward_prices())
    period = draw(st.sampled_from(PERIODS))
    contract_price = draw(_PRICES)
    notional = draw(_NOTIONALS)
    cls = draw(st.sampled_from((FuturesContract, ForwardContract)))
    contract = cls(
        commodity=TTF,
        delivery_period=period,
        contract_price=contract_price,
        notional=notional,
    )
    return contract, _market_data(forward_prices)


@st.composite
def _swap_cases(draw: st.DrawFn) -> tuple[SwapContract, MarketData]:
    forward_prices = draw(_forward_prices())
    periods = tuple(sorted(draw(st.sets(st.sampled_from(PERIODS), min_size=1, max_size=6))))
    contract = SwapContract(
        commodity=TTF,
        fixed_rate=draw(_PRICES),
        floating_index="TTF_DA",
        notional=draw(_NOTIONALS),
        schedule=DeliverySchedule(periods),
    )
    return contract, _market_data(forward_prices)


_ANY_CASE = st.one_of(_futures_cases(), _swap_cases())


# --- Property 104: side sign-flip parity (SHORT == -LONG exactly) ---------------------


# Feature: short-side-instruments, Property 104: side sign-flip parity
@given(case=_ANY_CASE)
def test_short_position_is_the_exact_negation_of_long(
    case: tuple[FuturesContract | ForwardContract | SwapContract, MarketData],
) -> None:
    contract, market_data = case
    long_contract = dataclasses.replace(contract, side=OptionSide.LONG)
    short_contract = dataclasses.replace(contract, side=OptionSide.SHORT)

    long_priced = value_portfolio(
        Portfolio(positions=(Position(long_contract),)), market_data
    ).priced[0]
    short_priced = value_portfolio(
        Portfolio(positions=(Position(short_contract),)), market_data
    ).priced[0]

    assert short_priced.npv == -long_priced.npv
    assert long_priced.delta.keys() == short_priced.delta.keys()
    for key, long_delta in long_priced.delta.items():
        assert short_priced.delta[key] == -long_delta
    # reference_prices are the raw observed forwards — identical, never sign-flipped.
    assert short_priced.reference_prices == long_priced.reference_prices


# Feature: short-side-instruments, Property 104: LONG default is byte-identical
@given(case=_ANY_CASE)
def test_default_side_is_long_and_byte_identical(
    case: tuple[FuturesContract | ForwardContract | SwapContract, MarketData],
) -> None:
    contract, market_data = case  # drawn with the default side (LONG)
    explicit_long = dataclasses.replace(contract, side=OptionSide.LONG)

    default_priced = value_portfolio(
        Portfolio(positions=(Position(contract),)), market_data
    ).priced[0]
    long_priced = value_portfolio(
        Portfolio(positions=(Position(explicit_long),)), market_data
    ).priced[0]

    assert default_priced.npv == long_priced.npv
    assert default_priced.delta == long_priced.delta
    assert default_priced.reference_prices == long_priced.reference_prices


# --- Property 105: long/short netting -------------------------------------------------


# Feature: short-side-instruments, Property 105: long + short nets to zero
@given(case=_ANY_CASE)
def test_long_plus_short_same_contract_nets_to_zero(
    case: tuple[FuturesContract | ForwardContract | SwapContract, MarketData],
) -> None:
    contract, market_data = case
    long_contract = dataclasses.replace(contract, side=OptionSide.LONG)
    short_contract = dataclasses.replace(contract, side=OptionSide.SHORT)
    portfolio = Portfolio(positions=(Position(long_contract), Position(short_contract)))

    valuation = value_portfolio(portfolio, market_data)

    assert valuation.total_npv == 0.0
    matrix = aggregate_delta(list(valuation.priced))
    for commodity in matrix.commodities:
        for period in matrix.periods:
            assert matrix.delta_at(commodity, period) == 0.0
