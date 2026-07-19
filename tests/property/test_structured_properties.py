"""Structured-product correctness properties (design Properties 18-20; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import PlantConfig
from quantvolt.models.schedule import DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.spread_models import kirk, margrabe
from quantvolt.pricing.spread_option import SpreadOptionRequest, price_spread_option
from quantvolt.pricing.tolling import price_tolling_agreement
from strategies import delivery_schedules, discount_curves, spread_option_requests

_TollingCase = tuple[
    PlantConfig,
    ForwardCurve,
    ForwardCurve,
    ForwardCurve,
    VolatilitySurface,
    np.ndarray,
    DeliverySchedule,
    DiscountCurve,
]

# The tolling module's fixed [power, fuel, eua] commodity roles (Req 8.1 ordering).
_POWER_ID, _FUEL_ID, _EUA_ID = "EEX_PHELIX_DE", "TTF", "EUA"
_TOLLING_MARKET_DATE = date(2023, 1, 1)
_TOLLING_RHO = st.floats(min_value=-0.9, max_value=0.9)


# Feature: power-energy-quant-analysis, Property 18: Spread Option Model Selection and
# Sensitivity Consistency
@given(request=spread_option_requests())
@settings(max_examples=100)
def test_zero_strike_prices_via_margrabe_and_nonzero_via_kirk(
    request: SpreadOptionRequest,
) -> None:
    result = price_spread_option(request)
    if request.strike == 0.0:
        expected_kernel = margrabe(
            request.forward1,
            request.forward2,
            request.sigma1,
            request.sigma2,
            request.correlation,
            request.time_to_expiry,
            request.discount_factor,
        )
    else:
        expected_kernel = kirk(
            request.forward1,
            request.forward2,
            request.strike,
            request.sigma1,
            request.sigma2,
            request.correlation,
            request.time_to_expiry,
            request.discount_factor,
        )
    assert result.premium == pytest.approx(request.notional * expected_kernel, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 18: Spread Option Model Selection and
# Sensitivity Consistency
# delta1 is representative of the five sensitivities: the pricer computes them all
# through the same central finite-difference helper. The oracle is an OUTER central
# difference over the whole pricer at a bump size distinct from the pricer's own
# (5e-4*F1 vs the pricer's internal 1e-4*F1), so agreement is a loose-tolerance
# recomputation, not an arithmetic identity.
#
# Numerical rationale for the bump size (AMENDED 2026-07-19, code review FIX 6):
# central-FD truncation error scales as bump**2 * P'''/6. In a deep-OTM tail (e.g.
# the Margrabe example forward1=414, forward2=432, sigma1=sigma2=0.0625, rho=0.75,
# T=0.0625, where delta1 = df*N(d1) ~ 5.99e-5), the delta is itself so small that a
# 1e-3*F1 outer bump made the O(bump**2) truncation term ~2% of the delta --
# breaching both the 1e-2 relative and the 1e-6*notional absolute tolerance at
# once, even though the pricer's reported delta1 matches the exact closed-form
# N(d1) to ~2e-4 relative. An earlier 2e-4*F1 choice was only 2x the pricer's own
# internal 1e-4*F1 bump, leaving a blind spot: if the pricer's internal bump were
# ever accidentally doubled to 2e-4*F1 too, this oracle would silently collapse
# into the identity it is meant to independently check. 5e-4*F1 restores a clean
# 5x separation from the internal bump (guarding the doubling blind spot) while
# still landing ~4x below the previously-failing 1e-3*F1 truncation level, cutting
# the deep-OTM truncation to a comfortable margin under the 1e-2 relative /
# 1e-6*notional absolute tolerance. Cancellation headroom remains ample: at
# 5e-4*F1 the up/down premium difference retains well over 10 significant figures.
@given(request=spread_option_requests())
@settings(max_examples=100)
def test_delta1_is_consistent_with_an_outer_finite_difference(
    request: SpreadOptionRequest,
) -> None:
    result = price_spread_option(request)
    bump = 5e-4 * request.forward1
    premium_up = price_spread_option(replace(request, forward1=request.forward1 + bump)).premium
    premium_down = price_spread_option(replace(request, forward1=request.forward1 - bump)).premium
    outer_delta1 = (premium_up - premium_down) / (2.0 * bump)
    assert result.delta1 == pytest.approx(outer_delta1, rel=1e-2, abs=1e-6 * request.notional)


# Feature: power-energy-quant-analysis, Property 19: Correlation Out-of-Range Rejection
@given(
    request=spread_option_requests(),
    bad_correlation=st.one_of(
        st.floats(min_value=-5.0, max_value=-1.0),
        st.floats(min_value=1.0, max_value=5.0),
    ),
)
@settings(max_examples=100)
def test_spread_option_correlation_outside_the_open_unit_interval_is_rejected(
    request: SpreadOptionRequest, bad_correlation: float
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        price_spread_option(replace(request, correlation=bad_correlation))
    message = str(excinfo.value)
    assert "correlation" in message
    assert "must be" in message


@st.composite
def _tolling_cases(draw: st.DrawFn) -> _TollingCase:
    """A fully consistent tolling valuation case: positive forwards on every curve so
    both spread-option legs stay in the pricer's domain, a symmetric unit-diagonal
    3x3 correlation matrix, full vol/discount coverage of the schedule."""
    schedule = draw(delivery_schedules(min_len=1, max_len=6))
    periods = schedule.periods

    def curve(commodity_id: str, low: float, high: float) -> ForwardCurve:
        return ForwardCurve(
            commodity=BUILT_IN_COMMODITIES[commodity_id],
            market_date=_TOLLING_MARKET_DATE,
            nodes=tuple(
                CurveNode(
                    period=period,
                    price=draw(st.floats(min_value=low, max_value=high)),
                    status="observed",
                )
                for period in periods
            ),
        )

    power_curve = curve(_POWER_ID, 5.0, 300.0)
    fuel_curve = curve(_FUEL_ID, 1.0, 60.0)
    eua_curve = curve(_EUA_ID, 1.0, 100.0)
    vol_surface = VolatilitySurface(
        commodity=BUILT_IN_COMMODITIES[_POWER_ID],
        tenors=tuple(
            VolatilityTenor(period=period, sigma=draw(st.floats(0.05, 1.0))) for period in periods
        ),
    )
    rho_pf, rho_pe, rho_fe = draw(_TOLLING_RHO), draw(_TOLLING_RHO), draw(_TOLLING_RHO)
    matrix = np.array(
        [[1.0, rho_pf, rho_pe], [rho_pf, 1.0, rho_fe], [rho_pe, rho_fe, 1.0]],
        dtype=np.float64,
    )
    plant = PlantConfig(
        heat_rate=draw(st.floats(min_value=0.5, max_value=3.0)),
        variable_om_cost=draw(st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=20.0))),
        emissions_intensity=draw(st.floats(min_value=0.0, max_value=1.0)),
        fuel_type=draw(st.sampled_from(("gas", "coal"))),
    )
    return (
        plant,
        power_curve,
        fuel_curve,
        eua_curve,
        vol_surface,
        matrix,
        schedule,
        draw(discount_curves()),
    )


# Feature: power-energy-quant-analysis, Property 19: Correlation Out-of-Range Rejection
@given(
    case=_tolling_cases(),
    bad_correlation=st.one_of(
        st.floats(min_value=-5.0, max_value=-1.0),
        st.floats(min_value=1.0, max_value=5.0),
    ),
)
@settings(max_examples=100)
def test_tolling_correlation_matrix_entry_outside_the_open_unit_interval_is_rejected(
    case: _TollingCase, bad_correlation: float
) -> None:
    plant, power, fuel, eua, vols, matrix, schedule, discount = case
    bad_matrix = matrix.copy()
    bad_matrix[0, 1] = bad_correlation
    bad_matrix[1, 0] = bad_correlation
    with pytest.raises(ValidationError) as excinfo:
        price_tolling_agreement(plant, power, fuel, eua, vols, bad_matrix, schedule, discount)
    message = str(excinfo.value)
    assert "correlation_matrix[0, 1]" in message
    assert "must be" in message


# Feature: power-energy-quant-analysis, Property 20: Tolling Agreement NPV Decomposition
# Invariants
@given(case=_tolling_cases())
@settings(max_examples=100)
def test_tolling_npv_decomposition_and_aggregate_delta_invariants(
    case: _TollingCase,
) -> None:
    plant, power, fuel, eua, vols, matrix, schedule, discount = case
    result = price_tolling_agreement(plant, power, fuel, eua, vols, matrix, schedule, discount)
    # (a) time_value = npv - intrinsic_value, and npv is the per-period sum: both are
    # computed by exactly that arithmetic, so the invariants hold to the float.
    assert result.time_value == result.npv - result.intrinsic_value
    assert result.npv == sum(result.per_period_values)
    # (b) intrinsic = sum(max(0, spread_i) x unit notional) from the current forwards.
    fuel_leg_weight = plant.heat_rate
    eua_leg_weight = plant.emissions_intensity * plant.heat_rate
    expected_intrinsic = 0.0
    for period in schedule.periods:
        leg = fuel_leg_weight * fuel.price_at(period) + eua_leg_weight * eua.price_at(period)
        expected_intrinsic += max(0.0, power.price_at(period) - leg - plant.variable_om_cost)
    assert result.intrinsic_value == pytest.approx(expected_intrinsic, rel=1e-12, abs=1e-12)
    # (c) aggregate_deltas[commodity] == sum(per_period_deltas[commodity]) exactly.
    assert set(result.aggregate_deltas) == {"power", "fuel", "eua"}
    for commodity, per_period in result.per_period_deltas.items():
        assert len(per_period) == len(schedule.periods)
        assert result.aggregate_deltas[commodity] == sum(per_period)
