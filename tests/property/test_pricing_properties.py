"""Pricing correctness properties (design Properties 10-17; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ExpiredContractError, ValidationError
from quantvolt.models.curve import ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.greeks import Greeks
from quantvolt.models.instruments import FuturesContract, SwapContract
from quantvolt.models.schedule import DeliverySchedule
from quantvolt.numerics.black76 import black76_greeks, black76_implied_vol, black76_price
from quantvolt.pricing.exotic import BarrierOptionRequest, price_barrier
from quantvolt.pricing.futures import price_futures
from quantvolt.pricing.swap import price_swap
from quantvolt.pricing.vanilla import (
    CapFloorRequest,
    VanillaOptionRequest,
    price_cap_floor,
    price_vanilla_option,
)
from strategies import (
    barrier_option_requests,
    delivery_schedules,
    futures_pricing_cases,
    swap_pricing_cases,
    vanilla_option_requests,
)

_FuturesCase = tuple[FuturesContract, ForwardCurve, date, DiscountCurve]
_SwapCase = tuple[SwapContract, ForwardCurve, DiscountCurve]


# Feature: power-energy-quant-analysis, Property 10: Futures NPV Formula
@given(case=futures_pricing_cases())
@settings(max_examples=100)
def test_futures_npv_equals_df_times_price_difference_times_notional(
    case: _FuturesCase,
) -> None:
    contract, curve, valuation_date, discount_curve = case
    result = price_futures(contract, curve, valuation_date, discount_curve)
    settlement_date = contract.delivery_period.last_day
    forward_price = curve.price_at(contract.delivery_period)
    discount_factor = discount_curve.discount_factor(settlement_date)
    expected_npv = discount_factor * (forward_price - contract.contract_price) * contract.notional
    assert result.npv == pytest.approx(expected_npv, rel=1e-12, abs=1e-12)
    # The NPV is linear in the forward price, so delta is exactly df * notional.
    assert result.delta == pytest.approx(discount_factor * contract.notional, rel=1e-9, abs=1e-9)


# Feature: power-energy-quant-analysis, Property 11: Expired Contract Rejection
@given(case=futures_pricing_cases(), days_after=st.integers(min_value=1, max_value=1_000))
@settings(max_examples=100)
def test_valuation_after_delivery_period_end_raises_expired_contract_error(
    case: _FuturesCase, days_after: int
) -> None:
    contract, curve, _, discount_curve = case
    expired_valuation = contract.delivery_period.last_day + timedelta(days=days_after)
    with pytest.raises(ExpiredContractError) as excinfo:
        price_futures(contract, curve, expired_valuation, discount_curve)
    assert repr(contract.delivery_period) in str(excinfo.value)


# Feature: power-energy-quant-analysis, Property 12: Swap NPV and Greeks Consistency
# The implementation's per-period fraction is identically 1 (whole-month cash flows),
# so the design's `fraction_i` term drops out of the oracle below.
@given(case=swap_pricing_cases())
@settings(max_examples=100)
def test_swap_npv_is_sum_of_discounted_cash_flows_and_delta_is_df_times_notional(
    case: _SwapCase,
) -> None:
    swap, curve, discount_curve = case
    result = price_swap(swap, curve, discount_curve)
    expected_cash_flows = [
        discount_curve.discount_factor(period.last_day)
        * (curve.price_at(period) - swap.fixed_rate)
        * swap.notional
        for period in swap.schedule.periods
    ]
    assert result.npv == pytest.approx(sum(expected_cash_flows), rel=1e-9, abs=1e-6)
    assert len(result.delta) == len(swap.schedule.periods)
    for delta_i, period in zip(result.delta, swap.schedule.periods, strict=True):
        expected_delta = discount_curve.discount_factor(period.last_day) * swap.notional
        assert delta_i == pytest.approx(expected_delta, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 13: Overlapping Swap Schedule Rejection
# Delivery periods are whole calendar months, so an "overlap" is a duplicated month;
# DeliverySchedule itself rejects it at construction (ValidationError), which is why an
# overlapping schedule can never reach price_swap through a valid SwapContract.
@given(schedule=delivery_schedules(max_len=8), data=st.data())
@settings(max_examples=100)
def test_schedule_with_duplicate_period_is_rejected_at_construction(
    schedule: DeliverySchedule, data: st.DataObject
) -> None:
    periods = list(schedule.periods)
    duplicated = data.draw(st.sampled_from(periods), label="duplicated")
    insert_at = data.draw(st.integers(0, len(periods)), label="insert_at")
    overlapping = (*periods[:insert_at], duplicated, *periods[insert_at:])
    with pytest.raises(ValidationError) as excinfo:
        DeliverySchedule(periods=overlapping)
    message = str(excinfo.value)
    assert "periods" in message
    assert "strictly increasing" in message


# Feature: power-energy-quant-analysis, Property 14: Black-76 Premium and Implied
# Volatility Round-Trip
@given(request=vanilla_option_requests(option_types=("call", "put")))
@settings(max_examples=100)
def test_implied_vol_recovers_the_pricing_vol_within_one_basis_point(
    request: VanillaOptionRequest,
) -> None:
    option_type = request.option_type
    premium = black76_price(
        option_type,  # type: ignore[arg-type]
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    greeks = black76_greeks(
        option_type,  # type: ignore[arg-type]
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    # Inversion is well-posed only where the premium responds to vol in float64.
    assume(greeks.vega >= 1e-6)
    if option_type == "call":
        lower = request.discount_factor * max(request.forward - request.strike, 0.0)
        upper = request.discount_factor * request.forward
    else:
        lower = request.discount_factor * max(request.strike - request.forward, 0.0)
        upper = request.discount_factor * request.strike
    assume(lower < premium < upper)
    recovered = black76_implied_vol(
        option_type,  # type: ignore[arg-type]
        premium,
        request.forward,
        request.strike,
        request.time_to_expiry,
        request.discount_factor,
        tol=1e-6,
    )
    assert recovered == pytest.approx(request.sigma, abs=1e-4)


# Feature: power-energy-quant-analysis, Property 15: Greek Relationships
@given(request=vanilla_option_requests(option_types=("call",)))
@settings(max_examples=100)
def test_call_put_greek_relationships(request: VanillaOptionRequest) -> None:
    call = black76_greeks(
        "call",
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    put = black76_greeks(
        "put",
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    # (a) put-call delta parity: delta_call - delta_put == DF.
    assert call.delta - put.delta == pytest.approx(request.discount_factor, abs=1e-12)
    # (b) gamma and vega are side-independent (identical formulas), and vega > 0.
    assert call.gamma == put.gamma
    assert call.vega == put.vega
    assert call.vega > 0.0
    # (c) time decay: theta < 0 for long positions is guaranteed at zero rates
    # (DF == 1). With r > 0 the carry term r*price can legitimately dominate the
    # decay term for deep-ITM options, so the design's sign claim is checked there.
    zero_rate_call = black76_greeks(
        "call", request.forward, request.strike, request.sigma, request.time_to_expiry, 1.0
    )
    zero_rate_put = black76_greeks(
        "put", request.forward, request.strike, request.sigma, request.time_to_expiry, 1.0
    )
    assert zero_rate_call.theta < 0.0
    assert zero_rate_put.theta < 0.0


@st.composite
def _cap_floor_requests(draw: st.DrawFn) -> CapFloorRequest:
    """A cap/floor strip whose caplets price on the strip's own call/put side and
    share the strip's own strike/notional -- per Req 5.6, only ``forward``,
    ``discount_factor`` and ``time_to_expiry`` vary caplet-by-caplet; a strip has
    one strike and one notional (``price_cap_floor`` rejects any caplet whose
    strike/notional diverges from the strip's).
    """
    strip_type = draw(st.sampled_from(("cap", "floor")))
    side_types: tuple[str, ...] = ("call", "cap") if strip_type == "cap" else ("put", "floor")
    strike = draw(st.floats(min_value=0.01, max_value=1_000.0))
    notional = draw(st.floats(min_value=0.01, max_value=1_000.0))
    raw_caplets = draw(
        st.lists(
            vanilla_option_requests(option_types=side_types),  # type: ignore[arg-type]
            min_size=1,
            max_size=15,
        )
    )
    caplets = tuple(replace(caplet, strike=strike, notional=notional) for caplet in raw_caplets)
    return CapFloorRequest(
        option_type=strip_type,  # type: ignore[arg-type]
        strike=strike,
        notional=notional,
        caplets=caplets,
    )


# Feature: power-energy-quant-analysis, Property 16: Cap/Floor Strip Aggregation
@given(request=_cap_floor_requests())
@settings(max_examples=100)
def test_strip_aggregate_equals_sum_of_independently_priced_periods(
    request: CapFloorRequest,
) -> None:
    result = price_cap_floor(request)
    expected_per_period = tuple(price_vanilla_option(caplet) for caplet in request.caplets)
    assert result.per_period == expected_per_period
    assert result.premium == sum(period.premium for period in expected_per_period)
    expected_greeks = Greeks.zero()
    for period_result in expected_per_period:
        expected_greeks = expected_greeks + period_result.greeks
    assert result.greeks == expected_greeks


@st.composite
def _breached_barrier_requests(draw: st.DrawFn) -> BarrierOptionRequest:
    """An INVALID barrier request: an up barrier at or below the forward, or a down
    barrier at or above it (already breached at inception)."""
    valid = draw(barrier_option_requests())
    if valid.barrier_type.startswith("up"):
        bad_barrier = valid.forward * draw(st.floats(min_value=0.4, max_value=1.0))
    else:
        bad_barrier = valid.forward * draw(st.floats(min_value=1.0, max_value=2.5))
    return replace(valid, barrier=bad_barrier)


# Feature: power-energy-quant-analysis, Property 17: Barrier Option Barrier-Level Validation
@given(request=_breached_barrier_requests())
@settings(max_examples=100)
def test_barrier_on_the_wrong_side_of_the_forward_is_rejected(
    request: BarrierOptionRequest,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        price_barrier(request)
    assert "barrier" in str(excinfo.value)


# Feature: power-energy-quant-analysis, Property 17: Barrier Option Barrier-Level Validation
@given(request=barrier_option_requests())
@settings(max_examples=100)
def test_valid_barriers_price_and_knock_in_plus_knock_out_reprices_the_vanilla(
    request: BarrierOptionRequest,
) -> None:
    direction = "up" if request.barrier_type.startswith("up") else "down"
    knock_in = replace(request, barrier_type=f"{direction}_in")
    knock_out = replace(request, barrier_type=f"{direction}_out")
    premium_in = price_barrier(knock_in).premium  # type: ignore[arg-type]
    premium_out = price_barrier(knock_out).premium  # type: ignore[arg-type]
    vanilla = black76_price(
        request.option_type,
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert premium_in + premium_out == pytest.approx(vanilla, abs=1e-6)
