"""Cross-cutting correctness properties (design Properties 27-30, 45-46; Tasks 46-47).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``) unless noted otherwise.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import quantvolt
from quantvolt.curves.builder import CurveBuilder
from quantvolt.exceptions import EnergyQuantError
from quantvolt.models import instruments as instruments_module
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    ForwardContract,
    FuturesContract,
    InstrumentPriceRecord,
    SettlementType,
    SwapContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule, Granularity
from quantvolt.numerics.monte_carlo import asian_monte_carlo
from quantvolt.pricing.exotic import AsianOptionRequest, price_asian
from quantvolt.pricing.futures import price_futures
from quantvolt.pricing.mark_to_market import MtMPosition, mark_to_market
from quantvolt.pricing.spread_option import SpreadOptionRequest, price_spread_option
from quantvolt.pricing.swap import price_swap
from quantvolt.pricing.vanilla import VanillaOptionRequest, price_vanilla_option
from quantvolt.testing import assert_input_unchanged
from strategies import (
    MARKET_DATES,
    asian_option_requests,
    commodity_configs,
    discount_curves,
    futures_contracts,
    futures_pricing_cases,
    instrument_price_record_lists,
    mtm_positions,
    swap_contracts,
    swap_pricing_cases,
    vanilla_option_requests,
)

_FuturesCase = tuple[FuturesContract, ForwardCurve, date, DiscountCurve]
_SwapCase = tuple[SwapContract, ForwardCurve, DiscountCurve]
_MtMCase = tuple[list[MtMPosition], date, dict[tuple[str, DeliveryPeriod], float]]
_INTERPOLATIONS: tuple[str, ...] = ("piecewise_flat", "piecewise_linear", "cubic_spline")


@st.composite
def _mtm_cases(draw: st.DrawFn) -> _MtMCase:
    """A book of positions with a settlement price for every (commodity, period)."""
    positions = draw(st.lists(mtm_positions(), min_size=1, max_size=8))
    settlement_prices = {
        (position.commodity_id, position.delivery_period): draw(
            st.floats(min_value=-10_000.0, max_value=10_000.0)
        )
        for position in positions
    }
    return positions, draw(MARKET_DATES), settlement_prices


# --- Property 27 ---------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 27: Pricing Determinism
@given(futures_case=futures_pricing_cases(), swap_case=swap_pricing_cases())
@settings(max_examples=100)
def test_futures_and_swap_pricing_is_deterministic(
    futures_case: _FuturesCase, swap_case: _SwapCase
) -> None:
    contract, curve, valuation_date, discount_curve = futures_case
    assert price_futures(contract, curve, valuation_date, discount_curve) == price_futures(
        contract, curve, valuation_date, discount_curve
    )
    swap, swap_curve, swap_dc = swap_case
    assert price_swap(swap, swap_curve, swap_dc) == price_swap(swap, swap_curve, swap_dc)


# Feature: power-energy-quant-analysis, Property 27: Pricing Determinism
@given(
    vanilla=vanilla_option_requests(),
    asian=asian_option_requests(),
    mtm_case=_mtm_cases(),
)
@settings(max_examples=100)
def test_option_pricing_and_mark_to_market_are_deterministic(
    vanilla: VanillaOptionRequest, asian: AsianOptionRequest, mtm_case: _MtMCase
) -> None:
    assert price_vanilla_option(vanilla) == price_vanilla_option(vanilla)
    assert price_asian(asian) == price_asian(asian)
    positions, market_date, settlement_prices = mtm_case
    assert mark_to_market(positions, market_date, settlement_prices) == mark_to_market(
        positions, market_date, settlement_prices
    )


# Feature: power-energy-quant-analysis, Property 27: Pricing Determinism
# Small path count (2_000) keeps the native Monte Carlo kernel fast; the strike stays
# close enough to the forward that some paths always finish in the money, so two
# different seeds cannot both produce an identically-zero premium.
@given(
    strike=st.floats(min_value=80.0, max_value=105.0),
    sigma=st.floats(min_value=0.2, max_value=1.0),
    time_to_expiry=st.floats(min_value=0.1, max_value=2.0),
    discount_factor=st.floats(min_value=0.5, max_value=1.0),
    seed=st.integers(min_value=0, max_value=2**31 - 2),
)
@settings(max_examples=100, deadline=None)
def test_monte_carlo_honours_the_seed(
    strike: float, sigma: float, time_to_expiry: float, discount_factor: float, seed: int
) -> None:
    def run(run_seed: int) -> tuple[float, float]:
        return asian_monte_carlo(
            forward=100.0,
            strike=strike,
            sigma=sigma,
            time_to_expiry=time_to_expiry,
            discount_factor=discount_factor,
            averaging_points=12,
            option_type="call",
            geometric=False,
            seed=run_seed,
            path_count=2_000,
        )

    assert run(seed) == run(seed)
    assert run(seed) != run(seed + 1)


# --- Property 28 ---------------------------------------------------------------------


@st.composite
def _bounded_futures_books(
    draw: st.DrawFn,
) -> tuple[list[FuturesContract], ForwardCurve, date, DiscountCurve]:
    """Up to 50 futures against one curve, with |price| <= 100 and notional <= 10 so
    every NPV stays below ~2e3 and the float64 summation residual below 1e-8."""
    commodity = draw(commodity_configs())
    market_date = draw(MARKET_DATES)
    small_prices = st.floats(min_value=-100.0, max_value=100.0)
    indices = sorted(draw(st.sets(st.integers(2024 * 12, 2032 * 12 + 11), min_size=1, max_size=6)))
    nodes = tuple(
        CurveNode(
            period=DeliveryPeriod(year=i // 12, month=i % 12 + 1),
            price=draw(small_prices),
            status="observed",
        )
        for i in indices
    )
    curve = ForwardCurve(commodity=commodity, market_date=market_date, nodes=nodes)
    contract_count = draw(st.integers(min_value=1, max_value=50))
    contracts = [
        FuturesContract(
            commodity=commodity,
            delivery_period=draw(st.sampled_from(nodes)).period,
            contract_price=draw(small_prices),
            notional=draw(st.floats(min_value=0.01, max_value=10.0)),
        )
        for _ in range(contract_count)
    ]
    return contracts, curve, date(2023, 7, 1), draw(discount_curves())


# Feature: power-energy-quant-analysis, Property 28: Numerical Stability of NPV Summation
# The design quantifies over up to 500 NPVs; 50 keeps the property-suite runtime down
# (Task 46 note) while still exercising the same float64 summation behaviour.
@given(book=_bounded_futures_books())
@settings(max_examples=100)
def test_summing_npvs_then_subtracting_each_leaves_a_residual_below_1e_8(
    book: tuple[list[FuturesContract], ForwardCurve, date, DiscountCurve],
) -> None:
    contracts, curve, valuation_date, discount_curve = book
    npvs = [
        price_futures(contract, curve, valuation_date, discount_curve).npv for contract in contracts
    ]
    residual = sum(npvs)
    for npv in npvs:
        residual -= npv
    assert abs(residual) <= 1e-8


# --- Property 29 ---------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 29: Input Immutability
@given(
    instruments=instrument_price_record_lists(min_len=4, max_len=8),
    market_date=MARKET_DATES,
    interpolation=st.sampled_from(_INTERPOLATIONS),
)
@settings(max_examples=100)
def test_curve_build_leaves_its_inputs_unchanged(
    instruments: list[InstrumentPriceRecord], market_date: date, interpolation: str
) -> None:
    assert_input_unchanged(
        CurveBuilder().build,
        instruments[0].commodity,
        market_date,
        instruments,
        interpolation=interpolation,  # type: ignore[arg-type]
    )


# Feature: power-energy-quant-analysis, Property 29: Input Immutability
@given(futures_case=futures_pricing_cases(), swap_case=swap_pricing_cases())
@settings(max_examples=100)
def test_futures_and_swap_pricing_leave_their_inputs_unchanged(
    futures_case: _FuturesCase, swap_case: _SwapCase
) -> None:
    contract, curve, valuation_date, discount_curve = futures_case
    assert_input_unchanged(price_futures, contract, curve, valuation_date, discount_curve)
    swap, swap_curve, swap_dc = swap_case
    assert_input_unchanged(price_swap, swap, swap_curve, swap_dc)


# Feature: power-energy-quant-analysis, Property 29: Input Immutability
@given(request=vanilla_option_requests())
@settings(max_examples=100)
def test_vanilla_option_pricing_leaves_its_input_unchanged(
    request: VanillaOptionRequest,
) -> None:
    assert_input_unchanged(price_vanilla_option, request)


# Feature: power-energy-quant-analysis, Property 29: Input Immutability
@given(mtm_case=_mtm_cases())
@settings(max_examples=100)
def test_mark_to_market_leaves_its_inputs_unchanged(mtm_case: _MtMCase) -> None:
    positions, market_date, settlement_prices = mtm_case
    assert_input_unchanged(mark_to_market, positions, market_date, settlement_prices)


# --- Property 30 ---------------------------------------------------------------------

_COMMODITY = BUILT_IN_COMMODITIES["TTF"]
_BASE_VANILLA = VanillaOptionRequest(
    option_type="call",
    strike=50.0,
    notional=100.0,
    forward=55.0,
    sigma=0.3,
    time_to_expiry=1.0,
    discount_factor=0.95,
)
_BASE_SPREAD = SpreadOptionRequest(
    forward1=55.0,
    forward2=45.0,
    strike=5.0,
    sigma1=0.3,
    sigma2=0.25,
    correlation=0.5,
    time_to_expiry=1.0,
    discount_factor=0.95,
)
_TWO_RECORDS = [
    InstrumentPriceRecord("a", _COMMODITY, DeliveryPeriod(2025, 6), 50.0),
    InstrumentPriceRecord("b", _COMMODITY, DeliveryPeriod(2025, 7), 51.0),
]


@dataclass(frozen=True)
class _BadInputCase:
    parameter: str
    bad_values: st.SearchStrategy[float]
    invoke: Callable[[float], object]


_BAD_INPUT_CASES: tuple[_BadInputCase, ...] = (
    _BadInputCase(
        "notional",
        st.floats(min_value=-10_000.0, max_value=0.0),
        lambda bad: FuturesContract(
            commodity=_COMMODITY,
            delivery_period=DeliveryPeriod(2025, 6),
            contract_price=50.0,
            notional=bad,
        ),
    ),
    _BadInputCase(
        "sigma",
        st.floats(min_value=-10.0, max_value=0.0),
        lambda bad: price_vanilla_option(replace(_BASE_VANILLA, sigma=bad)),
    ),
    _BadInputCase(
        "strike",
        st.floats(min_value=-1_000.0, max_value=0.0),
        lambda bad: price_vanilla_option(replace(_BASE_VANILLA, strike=bad)),
    ),
    _BadInputCase(
        "time_to_expiry",
        st.floats(min_value=-5.0, max_value=0.0),
        lambda bad: price_vanilla_option(replace(_BASE_VANILLA, time_to_expiry=bad)),
    ),
    _BadInputCase(
        "discount_factor",
        st.one_of(
            st.floats(min_value=-1.0, max_value=0.0),
            st.floats(min_value=1.000001, max_value=5.0),
        ),
        lambda bad: price_vanilla_option(replace(_BASE_VANILLA, discount_factor=bad)),
    ),
    _BadInputCase(
        "tolerance",
        st.one_of(
            st.floats(min_value=-1.0, max_value=0.00099),
            st.floats(min_value=1.001, max_value=10.0),
        ),
        lambda bad: CurveBuilder().build(
            _COMMODITY, date(2025, 1, 15), _TWO_RECORDS, tolerance=bad
        ),
    ),
    _BadInputCase(
        "correlation",
        st.one_of(
            st.floats(min_value=-5.0, max_value=-1.0),
            st.floats(min_value=1.0, max_value=5.0),
        ),
        lambda bad: price_spread_option(replace(_BASE_SPREAD, correlation=bad)),
    ),
)


# Feature: power-energy-quant-analysis, Property 30: EnergyQuantError Hierarchy for All
# Validation Failures
@pytest.mark.parametrize("case", _BAD_INPUT_CASES, ids=[c.parameter for c in _BAD_INPUT_CASES])
@given(data=st.data())
@settings(max_examples=100)
def test_validation_failures_raise_energy_quant_errors_naming_parameter_and_constraint(
    case: _BadInputCase, data: st.DataObject
) -> None:
    bad_value = data.draw(case.bad_values, label=case.parameter)
    with pytest.raises(EnergyQuantError) as excinfo:
        case.invoke(bad_value)
    message = str(excinfo.value)
    assert case.parameter in message
    assert "must be" in message  # the violated constraint, e.g. "must be > 0"


# --- Property 45 ---------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 45: Physical vs Financial Settlement
# Distinction
@given(case=futures_pricing_cases())
@settings(max_examples=100)
def test_settlement_type_never_changes_the_npv_and_is_preserved(case: _FuturesCase) -> None:
    contract, curve, valuation_date, discount_curve = case
    financial = replace(contract, settlement_type=SettlementType.FINANCIAL)
    physical = replace(contract, settlement_type=SettlementType.PHYSICAL)
    financial_result = price_futures(financial, curve, valuation_date, discount_curve)
    physical_result = price_futures(physical, curve, valuation_date, discount_curve)
    assert financial_result == physical_result
    # Forwards (bilateral OTC) follow the same invariant.
    forward_financial = ForwardContract(
        commodity=contract.commodity,
        delivery_period=contract.delivery_period,
        contract_price=contract.contract_price,
        notional=contract.notional,
        settlement_type=SettlementType.FINANCIAL,
    )
    forward_physical = replace(forward_financial, settlement_type=SettlementType.PHYSICAL)
    assert price_futures(forward_financial, curve, valuation_date, discount_curve) == price_futures(
        forward_physical, curve, valuation_date, discount_curve
    )
    # settlement_type is preserved on the instruments through pricing.
    assert financial.settlement_type is SettlementType.FINANCIAL
    assert physical.settlement_type is SettlementType.PHYSICAL
    assert forward_physical.settlement_type is SettlementType.PHYSICAL


# --- Property 46 ---------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 46: Contract Granularity Validation
# The implementation models every delivery period as a calendar month, so the enum in
# models/schedule.py is the single source of granularity and MONTHLY consistency is
# structural: each period spans exactly one calendar month.
@given(contract=futures_contracts(), swap=swap_contracts())
@settings(max_examples=100)
def test_granularity_is_the_single_shared_enum_and_schedules_are_calendar_months(
    contract: FuturesContract, swap: SwapContract
) -> None:
    # Single source: instruments and the facade re-export the schedule module's enum.
    assert instruments_module.Granularity is Granularity
    assert quantvolt.Granularity is Granularity
    assert set(Granularity) == {"hourly", "daily", "monthly", "quarterly", "yearly"}
    # Every instrument's granularity is a member of that one enum.
    assert isinstance(contract.granularity, Granularity)
    assert contract.granularity in tuple(Granularity)
    assert isinstance(swap.granularity, Granularity)
    assert swap.granularity in tuple(Granularity)
    # Schedule consistency: each period is exactly one calendar month...
    for period in swap.schedule.periods:
        last_day = period.last_day
        assert (last_day.year, last_day.month) == (period.year, period.month)
        day_after = last_day + timedelta(days=1)
        assert day_after.day == 1  # last_day really is the end of the month
    # ...and re-validating the schedule's own periods is consistent (idempotent).
    assert DeliverySchedule(periods=swap.schedule.periods).periods == swap.schedule.periods
