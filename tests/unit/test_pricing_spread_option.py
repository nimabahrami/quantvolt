"""Unit tests for the spread-option pricer (Task 30; Req 7.1-7.4; Properties 18, 19)."""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.numerics.spread_models import kirk, margrabe
from quantvolt.pricing.spread_option import (
    SpreadOptionRequest,
    price_spark_spread_option,
    price_spread_option,
)
from quantvolt.testing import assert_input_unchanged


def make_request(**overrides: float) -> SpreadOptionRequest:
    params: dict[str, float] = {
        "forward1": 100.0,
        "forward2": 90.0,
        "strike": 5.0,
        "sigma1": 0.30,
        "sigma2": 0.20,
        "correlation": 0.5,
        "time_to_expiry": 1.0,
        "discount_factor": 0.95,
        "notional": 2.0,
    }
    params.update(overrides)
    return SpreadOptionRequest(**params)


# --- Model selection (Property 18, Req 7.1) ---


def test_zero_strike_premium_equals_margrabe_times_notional() -> None:
    request = make_request(strike=0.0)
    result = price_spread_option(request)
    expected = request.notional * margrabe(
        request.forward1,
        request.forward2,
        request.sigma1,
        request.sigma2,
        request.correlation,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert result.premium == expected


def test_nonzero_strike_premium_equals_kirk_times_notional() -> None:
    request = make_request(strike=5.0)
    result = price_spread_option(request)
    expected = request.notional * kirk(
        request.forward1,
        request.forward2,
        request.strike,
        request.sigma1,
        request.sigma2,
        request.correlation,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert result.premium == expected


# --- Correlation rejection (Property 19, Req 7.4) ---


@pytest.mark.parametrize("rho", [-1.0, 1.0, -1.5, 1.0001])
def test_correlation_outside_open_interval_raises(rho: float) -> None:
    with pytest.raises(ValidationError, match="correlation"):
        price_spread_option(make_request(correlation=rho))


@pytest.mark.parametrize("rho", [-1.0, 1.0])
def test_spark_spread_rejects_boundary_correlation(rho: float) -> None:
    with pytest.raises(ValidationError, match="correlation"):
        price_spark_spread_option(make_request(correlation=rho), heat_rate=2.0)


# --- Domain validation names the offending parameter (Req 7.1) ---


@pytest.mark.parametrize(
    ("param", "value"),
    [
        ("forward1", 0.0),
        ("forward1", -100.0),
        ("forward2", 0.0),
        ("strike", -1.0),
        ("sigma1", 0.0),
        ("sigma2", -0.2),
        ("time_to_expiry", 0.0),
        ("discount_factor", 0.0),
        ("discount_factor", 1.5),
        ("notional", 0.0),
    ],
)
def test_domain_validation_raises_naming_parameter(param: str, value: float) -> None:
    with pytest.raises(ValidationError, match=param):
        price_spread_option(make_request(**{param: value}))


@pytest.mark.parametrize("heat_rate", [0.0, -2.0])
def test_spark_spread_heat_rate_must_be_positive(heat_rate: float) -> None:
    with pytest.raises(ValidationError, match="heat_rate"):
        price_spark_spread_option(make_request(), heat_rate)


# --- Sensitivity signs and behaviour (Req 7.2) ---


def test_call_spread_sensitivity_signs() -> None:
    result = price_spread_option(make_request())
    assert result.delta1 > 0.0
    assert result.delta2 < 0.0
    assert result.vega1 > 0.0
    assert result.vega2 > 0.0
    assert result.correlation_sensitivity < 0.0


def test_premium_decreases_as_correlation_rises() -> None:
    premiums = [
        price_spread_option(make_request(correlation=rho)).premium for rho in (-0.5, 0.0, 0.5, 0.9)
    ]
    assert all(lower_rho > higher_rho for lower_rho, higher_rho in pairwise(premiums))


def test_correlation_bump_is_clamped_near_boundary() -> None:
    # rho + 1e-4 would leave (-1, 1); the clamped bump must still give a finite value.
    result = price_spread_option(make_request(correlation=0.99995))
    assert math.isfinite(result.correlation_sensitivity)


# --- Sensitivity consistency with the premium (Property 18) ---


def test_delta1_consistent_with_premium_finite_difference() -> None:
    request = make_request()
    result = price_spread_option(request)
    bump = 0.01 * request.forward1
    up = price_spread_option(replace(request, forward1=request.forward1 + bump)).premium
    down = price_spread_option(replace(request, forward1=request.forward1 - bump)).premium
    assert result.delta1 == pytest.approx((up - down) / (2.0 * bump), rel=1e-2)


# --- Spark spread transformation (Req 7.3) ---


def test_spark_spread_equals_manually_transformed_plain_request_except_delta2() -> None:
    """Every field but ``delta2`` matches the manually transformed plain spread
    option exactly. ``delta2`` differs by the ``heat_rate`` factor: it is
    chain-ruled back onto the RAW gas forward the caller passed
    (``request.forward2``), not the internally scaled ``heat_rate x F_gas``
    (Req 7.2) -- matching the convention :mod:`quantvolt.pricing.tolling` uses
    for its own chain-ruled fuel/EUA deltas.
    """
    heat_rate = 2.0
    power_vs_gas = make_request(forward1=120.0, forward2=45.0)  # F1 = power, F2 = gas
    spark = price_spark_spread_option(power_vs_gas, heat_rate)
    manual = price_spread_option(replace(power_vs_gas, forward2=power_vs_gas.forward2 * heat_rate))
    assert spark == replace(manual, delta2=manual.delta2 * heat_rate)


def test_spark_spread_delta2_matches_finite_difference_on_raw_gas_forward() -> None:
    """delta2 is the sensitivity to the RAW gas forward the caller passed (Req 7.2):
    a central finite difference bumping ``request.forward2`` directly (with the
    spark-spread transform reapplied each time) must match ``result.delta2``.
    """
    heat_rate = 2.0
    request = make_request(forward1=120.0, forward2=45.0)
    result = price_spark_spread_option(request, heat_rate)
    bump = 0.01 * request.forward2
    up = price_spark_spread_option(
        replace(request, forward2=request.forward2 + bump), heat_rate
    ).premium
    down = price_spark_spread_option(
        replace(request, forward2=request.forward2 - bump), heat_rate
    ).premium
    assert result.delta2 == pytest.approx((up - down) / (2.0 * bump), rel=1e-2)


def test_spark_spread_with_unit_heat_rate_is_plain_spread() -> None:
    request = make_request()
    assert price_spark_spread_option(request, 1.0) == price_spread_option(request)


# --- Immutability (coding-style section 7) ---


def test_inputs_are_not_mutated() -> None:
    assert_input_unchanged(price_spread_option, make_request())
    assert_input_unchanged(price_spark_spread_option, make_request(), 2.5)


# --- new keyword-only bump parameters (default-unchanged / override-has-effect) ---


def test_bump_defaults_match_hardcoded_behaviour() -> None:
    request = make_request()
    baseline = price_spread_option(request)
    explicit = price_spread_option(
        request, forward_bump_fraction=1e-4, vol_bump=1e-4, correlation_bump=1e-4
    )
    assert explicit == baseline


def test_forward_bump_fraction_override_changes_delta1() -> None:
    request = make_request()
    baseline = price_spread_option(request).delta1
    wider = price_spread_option(request, forward_bump_fraction=0.05).delta1
    assert wider != baseline


def test_vol_bump_override_changes_vega1() -> None:
    request = make_request()
    baseline = price_spread_option(request).vega1
    wider = price_spread_option(request, vol_bump=0.05).vega1
    assert wider != baseline


def test_correlation_bump_override_changes_correlation_sensitivity() -> None:
    request = make_request()
    baseline = price_spread_option(request).correlation_sensitivity
    wider = price_spread_option(request, correlation_bump=0.2).correlation_sensitivity
    assert wider != baseline


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [
        ("forward_bump_fraction", 0.0),
        ("forward_bump_fraction", -1e-4),
        ("vol_bump", 0.0),
        ("correlation_bump", 0.0),
    ],
)
def test_bump_validation_names_parameter(kwarg: str, value: float) -> None:
    with pytest.raises(ValidationError, match=kwarg):
        price_spread_option(make_request(), **{kwarg: value})


def test_spark_spread_bump_defaults_match_hardcoded_behaviour() -> None:
    request = make_request()
    baseline = price_spark_spread_option(request, 2.0)
    explicit = price_spark_spread_option(
        request, 2.0, forward_bump_fraction=1e-4, vol_bump=1e-4, correlation_bump=1e-4
    )
    assert explicit == baseline


def test_spark_spread_forward_bump_fraction_override_changes_delta1() -> None:
    request = make_request()
    baseline = price_spark_spread_option(request, 2.0).delta1
    wider = price_spark_spread_option(request, 2.0, forward_bump_fraction=0.05).delta1
    assert wider != baseline
