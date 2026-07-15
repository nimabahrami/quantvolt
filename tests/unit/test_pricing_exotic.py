"""Unit tests for the exotic-option pricers (Tasks 28-29, Reqs 6.1-6.5; Property 17).

Covers: (a) each dispatch path returns *exactly* the premium of the corresponding
``numerics.exotic`` kernel (arithmetic/geometric defaults, explicit methods, all four
barrier types, floating/fixed lookbacks); (b) a mismatched Asian method/averaging pair
is rejected; (c) the Monte Carlo path — ``seed``/``path_count`` validated eagerly, and
a *valid* MC request prices through the native Rust engine (Task 59): deterministic per
seed, positive standard error, premium within statistical reach of the matching closed
form; (d) every Task 29 validation path for all three pricers, each error naming the
offending parameter; (e) barrier-vs-forward validation in both directions
(Property 17); (f) finite-difference Greeks sanity and the exact ``rho = -T * premium``
convention; (g) the Req 6.5 closed-form budget (well under 2 s — the closed forms are
schedule-free, so the 252-period benchmark collapses to a single call); (h) input
immutability via the shipped ``assert_input_unchanged``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Literal

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.greeks import Greeks
from quantvolt.numerics.exotic import (
    barrier_analytic,
    kemna_vorst,
    lookback_fixed,
    lookback_floating,
    turnbull_wakeman,
)
from quantvolt.pricing.exotic import (
    AsianOptionRequest,
    BarrierOptionRequest,
    LookbackOptionRequest,
    price_asian,
    price_barrier,
    price_lookback,
)
from quantvolt.testing import assert_input_unchanged

_ASIAN = AsianOptionRequest(
    option_type="call",
    averaging="arithmetic",
    strike=95.0,
    forward=100.0,
    sigma=0.25,
    time_to_expiry=0.5,
    discount_factor=0.97,
)

_BARRIER = BarrierOptionRequest(
    option_type="call",
    barrier_type="up_out",
    strike=95.0,
    barrier=130.0,
    forward=100.0,
    sigma=0.25,
    time_to_expiry=0.5,
    discount_factor=0.97,
)

_LOOKBACK = LookbackOptionRequest(
    option_type="call",
    strike_type="floating",
    forward=100.0,
    sigma=0.25,
    time_to_expiry=0.5,
    discount_factor=0.97,
)


# --- (a) premiums match the numerics kernels exactly, per dispatch path ------


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize(
    ("averaging", "method", "kernel"),
    [
        ("arithmetic", None, turnbull_wakeman),  # default for arithmetic
        ("arithmetic", "turnbull_wakeman", turnbull_wakeman),
        ("geometric", None, kemna_vorst),  # default for geometric
        ("geometric", "kemna_vorst", kemna_vorst),
    ],
)
def test_asian_dispatch_prices_selected_kernel_exactly(
    option_type: Literal["call", "put"],
    averaging: Literal["arithmetic", "geometric"],
    method: Literal["turnbull_wakeman", "kemna_vorst"] | None,
    kernel: object,
) -> None:
    request = replace(_ASIAN, option_type=option_type, averaging=averaging, method=method)
    result = price_asian(request)
    assert result.premium == kernel(  # type: ignore[operator]
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
        option_type,
    )
    assert result.standard_error is None


def test_asian_defaults_differ_by_averaging() -> None:
    arithmetic = price_asian(_ASIAN)
    geometric = price_asian(replace(_ASIAN, averaging="geometric"))
    # Distinct kernels: geometric averaging prices strictly below arithmetic for a call.
    assert geometric.premium < arithmetic.premium


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize(
    ("barrier_type", "barrier"),
    [("up_in", 130.0), ("up_out", 130.0), ("down_in", 70.0), ("down_out", 70.0)],
)
def test_barrier_prices_kernel_exactly(
    option_type: Literal["call", "put"],
    barrier_type: Literal["up_in", "up_out", "down_in", "down_out"],
    barrier: float,
) -> None:
    request = replace(_BARRIER, option_type=option_type, barrier_type=barrier_type, barrier=barrier)
    result = price_barrier(request)
    assert result.premium == barrier_analytic(
        option_type,
        barrier_type,
        request.forward,
        request.strike,
        barrier,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert result.standard_error is None


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_floating_lookback_prices_gsg_kernel_exactly(
    option_type: Literal["call", "put"],
) -> None:
    request = replace(_LOOKBACK, option_type=option_type)
    result = price_lookback(request)
    assert result.premium == lookback_floating(
        option_type,
        request.forward,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert result.standard_error is None


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize("strike", [90.0, 105.0])  # both sides of the forward
def test_fixed_lookback_prices_conze_viswanathan_kernel_exactly(
    option_type: Literal["call", "put"],
    strike: float,
) -> None:
    request = replace(_LOOKBACK, option_type=option_type, strike_type="fixed", strike=strike)
    result = price_lookback(request)
    assert result.premium == lookback_fixed(
        option_type,
        request.forward,
        strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )


# --- (b) mismatched Asian method/averaging is rejected ------------------------


@pytest.mark.parametrize(
    ("averaging", "method"),
    [("arithmetic", "kemna_vorst"), ("geometric", "turnbull_wakeman")],
)
def test_mismatched_method_and_averaging_rejected(
    averaging: Literal["arithmetic", "geometric"],
    method: Literal["turnbull_wakeman", "kemna_vorst"],
) -> None:
    request = replace(_ASIAN, averaging=averaging, method=method)
    with pytest.raises(ValidationError, match=r"method.*averaging"):
        price_asian(request)


# --- (c) Monte Carlo path ------------------------------------------------------


def test_monte_carlo_without_seed_rejected() -> None:
    request = replace(_ASIAN, method="monte_carlo")  # seed defaults to None
    with pytest.raises(ValidationError, match="seed"):
        price_asian(request)


def test_monte_carlo_path_count_below_1000_rejected() -> None:
    request = replace(_ASIAN, method="monte_carlo", seed=42, path_count=999)
    with pytest.raises(ValidationError, match="path_count"):
        price_asian(request)


@pytest.mark.parametrize(
    ("averaging", "closed_form"),
    [("arithmetic", turnbull_wakeman), ("geometric", kemna_vorst)],
)
def test_valid_monte_carlo_request_prices_through_native_engine(
    averaging: Literal["arithmetic", "geometric"],
    closed_form: Callable[[float, float, float, float, float, Literal["call", "put"]], float],
) -> None:
    """A fully valid MC request prices through the native Rust kernel (Task 59).

    The premium must sit within 4 standard errors of the matching closed form — a
    deliberately generous bound: Turnbull-Wakeman is a moment-matched approximation
    and the closed forms assume *continuous* averaging while MC uses 252 discrete
    fixings. Greeks stay ``Greeks.zero()`` until MC Greeks ship.
    """
    request = replace(_ASIAN, averaging=averaging, method="monte_carlo", seed=42, path_count=50_000)
    result = price_asian(request)
    assert result.standard_error is not None
    assert result.standard_error > 0.0
    assert result.greeks == Greeks.zero()
    reference = closed_form(
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
        request.option_type,
    )
    assert abs(result.premium - reference) < 4.0 * result.standard_error


def test_monte_carlo_identical_requests_are_deterministic() -> None:
    # Req 11.2 (Property 27): the seeded native RNG makes repeat pricings identical.
    request = replace(_ASIAN, method="monte_carlo", seed=42, path_count=10_000)
    first = price_asian(request)
    second = price_asian(request)
    assert first.premium == second.premium
    assert first.standard_error == second.standard_error


def test_path_count_floor_only_binds_for_monte_carlo() -> None:
    # Closed forms ignore seed/path_count: the MC-only constraints must not leak.
    result = price_asian(replace(_ASIAN, path_count=1))
    assert result.premium > 0.0


# --- (d) Task 29: every validation path names the parameter -------------------

_BAD_DOMAINS: list[tuple[str, float]] = [
    ("forward", 0.0),
    ("forward", -100.0),
    ("sigma", 0.0),
    ("sigma", -0.25),
    ("time_to_expiry", 0.0),
    ("time_to_expiry", -0.5),
    ("discount_factor", 0.0),
    ("discount_factor", -0.5),
    ("discount_factor", 1.5),
]


@pytest.mark.parametrize(
    ("field", "bad_value"), [*_BAD_DOMAINS, ("strike", 0.0), ("strike", -95.0)]
)
def test_asian_invalid_domain_raises_naming_parameter(field: str, bad_value: float) -> None:
    with pytest.raises(ValidationError, match=field):
        price_asian(replace(_ASIAN, **{field: bad_value}))


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [*_BAD_DOMAINS, ("strike", 0.0), ("strike", -95.0), ("barrier", 0.0), ("barrier", -130.0)],
)
def test_barrier_invalid_domain_raises_naming_parameter(field: str, bad_value: float) -> None:
    with pytest.raises(ValidationError, match=field):
        price_barrier(replace(_BARRIER, **{field: bad_value}))


@pytest.mark.parametrize(("field", "bad_value"), _BAD_DOMAINS)
def test_lookback_invalid_domain_raises_naming_parameter(field: str, bad_value: float) -> None:
    with pytest.raises(ValidationError, match=field):
        price_lookback(replace(_LOOKBACK, **{field: bad_value}))


def test_validation_happens_before_method_dispatch() -> None:
    # A bad domain must win over a bad MC setup: validation is eager and ordered
    # before any method-specific handling.
    request = replace(_ASIAN, sigma=-1.0, method="monte_carlo")  # seed also missing
    with pytest.raises(ValidationError, match="sigma"):
        price_asian(request)


# --- (e) Property 17: barrier-vs-forward, both directions ----------------------


@pytest.mark.parametrize("barrier_type", ["up_in", "up_out"])
@pytest.mark.parametrize("barrier", [90.0, 100.0])  # below and exactly at the forward
def test_up_barrier_not_above_forward_rejected(
    barrier_type: Literal["up_in", "up_out"],
    barrier: float,
) -> None:
    request = replace(_BARRIER, barrier_type=barrier_type, barrier=barrier)
    with pytest.raises(ValidationError, match=r"barrier.*forward"):
        price_barrier(request)


@pytest.mark.parametrize("barrier_type", ["down_in", "down_out"])
@pytest.mark.parametrize("barrier", [110.0, 100.0])  # above and exactly at the forward
def test_down_barrier_not_below_forward_rejected(
    barrier_type: Literal["down_in", "down_out"],
    barrier: float,
) -> None:
    request = replace(_BARRIER, barrier_type=barrier_type, barrier=barrier)
    with pytest.raises(ValidationError, match=r"barrier.*forward"):
        price_barrier(request)


# --- lookback strike/strike_type pairing ---------------------------------------


def test_floating_lookback_with_strike_rejected() -> None:
    request = replace(_LOOKBACK, strike=105.0)
    with pytest.raises(ValidationError, match="strike"):
        price_lookback(request)


def test_fixed_lookback_without_strike_rejected() -> None:
    request = replace(_LOOKBACK, strike_type="fixed")  # strike stays None
    with pytest.raises(ValidationError, match="strike"):
        price_lookback(request)


@pytest.mark.parametrize("strike", [0.0, -105.0])
def test_fixed_lookback_non_positive_strike_rejected(strike: float) -> None:
    request = replace(_LOOKBACK, strike_type="fixed", strike=strike)
    with pytest.raises(ValidationError, match="strike"):
        price_lookback(request)


# --- (f) finite-difference Greeks sanity ----------------------------------------


def test_asian_call_greeks_sanity() -> None:
    greeks = price_asian(_ASIAN).greeks
    assert greeks.delta > 0.0  # call gains with the forward
    assert greeks.vega > 0.0  # long optionality is long vol
    assert greeks.gamma > 0.0  # convex payoff


def test_asian_put_delta_negative() -> None:
    greeks = price_asian(replace(_ASIAN, option_type="put")).greeks
    assert greeks.delta < 0.0
    assert greeks.vega > 0.0


def test_lookback_is_long_vol() -> None:
    assert price_lookback(_LOOKBACK).greeks.vega > 0.0


def test_rho_is_minus_expiry_times_premium() -> None:
    # Documented convention (matches black76_greeks): every closed-form premium is
    # proportional to DF, so rho = d(price)/dr = -T * premium exactly.
    for result in (price_asian(_ASIAN), price_barrier(_BARRIER), price_lookback(_LOOKBACK)):
        assert result.greeks.rho == -_ASIAN.time_to_expiry * result.premium


# --- (g) Req 6.5: closed form well under the 2 s budget --------------------------


def test_closed_form_asian_well_under_two_seconds() -> None:
    # The closed forms are schedule-free (continuous averaging), so the 252-period
    # benchmark request is a single kernel call plus finite-difference Greeks.
    price_asian(_ASIAN)  # warm-up: first call pays scipy dispatch setup
    start = time.perf_counter()
    price_asian(_ASIAN)
    assert time.perf_counter() - start < 2.0


# --- (h) immutability of inputs ---------------------------------------------------


def test_pricers_do_not_mutate_inputs() -> None:
    assert_input_unchanged(price_asian, _ASIAN)
    assert_input_unchanged(price_barrier, _BARRIER)
    assert_input_unchanged(price_lookback, _LOOKBACK)
    assert_input_unchanged(price_lookback, replace(_LOOKBACK, strike_type="fixed", strike=105.0))


# --- new keyword-only bump / schedule parameters -------------------------------


def test_asian_bump_defaults_match_hardcoded_behaviour() -> None:
    baseline = price_asian(_ASIAN)
    explicit = price_asian(
        _ASIAN,
        forward_bump_fraction=1e-4,
        vol_bump=1e-4,
        time_bump=1e-6,
        averaging_points=252,
    )
    assert explicit == baseline


def test_asian_forward_bump_fraction_override_changes_greeks() -> None:
    baseline = price_asian(_ASIAN).greeks
    wider = price_asian(_ASIAN, forward_bump_fraction=0.05).greeks
    assert wider.delta != baseline.delta
    assert wider.gamma != baseline.gamma


def test_asian_vol_bump_override_changes_vega() -> None:
    baseline = price_asian(_ASIAN).greeks.vega
    wider = price_asian(_ASIAN, vol_bump=0.05).greeks.vega
    assert wider != baseline


def test_asian_time_bump_override_changes_theta() -> None:
    baseline = price_asian(_ASIAN).greeks.theta
    wider = price_asian(_ASIAN, time_bump=0.05).greeks.theta
    assert wider != baseline


def test_asian_averaging_points_override_changes_monte_carlo_premium() -> None:
    request = replace(_ASIAN, method="monte_carlo", seed=42, path_count=20_000)
    baseline = price_asian(request)
    fewer_fixings = price_asian(request, averaging_points=12)
    assert fewer_fixings.premium != baseline.premium


def test_asian_averaging_points_does_not_affect_closed_form() -> None:
    # Closed forms are schedule-free (continuous averaging): averaging_points is unused.
    baseline = price_asian(_ASIAN)
    changed = price_asian(_ASIAN, averaging_points=12)
    assert changed == baseline


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [
        ("forward_bump_fraction", 0.0),
        ("forward_bump_fraction", -1e-4),
        ("vol_bump", 0.0),
        ("time_bump", 0.0),
    ],
)
def test_asian_bump_validation_names_parameter(kwarg: str, value: float) -> None:
    with pytest.raises(ValidationError, match=kwarg):
        price_asian(_ASIAN, **{kwarg: value})


def test_asian_averaging_points_below_one_rejected() -> None:
    with pytest.raises(ValidationError, match="averaging_points"):
        price_asian(_ASIAN, averaging_points=0)


def test_barrier_bump_defaults_match_hardcoded_behaviour() -> None:
    baseline = price_barrier(_BARRIER)
    explicit = price_barrier(_BARRIER, forward_bump_fraction=1e-4, vol_bump=1e-4, time_bump=1e-6)
    assert explicit == baseline


def test_barrier_forward_bump_fraction_override_changes_delta() -> None:
    baseline = price_barrier(_BARRIER).greeks.delta
    wider = price_barrier(_BARRIER, forward_bump_fraction=0.05).greeks.delta
    assert wider != baseline


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [("forward_bump_fraction", 0.0), ("vol_bump", -0.1), ("time_bump", 0.0)],
)
def test_barrier_bump_validation_names_parameter(kwarg: str, value: float) -> None:
    with pytest.raises(ValidationError, match=kwarg):
        price_barrier(_BARRIER, **{kwarg: value})


def test_lookback_bump_defaults_match_hardcoded_behaviour() -> None:
    baseline = price_lookback(_LOOKBACK)
    explicit = price_lookback(_LOOKBACK, forward_bump_fraction=1e-4, vol_bump=1e-4, time_bump=1e-6)
    assert explicit == baseline


def test_lookback_vol_bump_override_changes_vega() -> None:
    baseline = price_lookback(_LOOKBACK).greeks.vega
    wider = price_lookback(_LOOKBACK, vol_bump=0.05).greeks.vega
    assert wider != baseline


@pytest.mark.parametrize(
    ("kwarg", "value"),
    [("forward_bump_fraction", 0.0), ("vol_bump", 0.0), ("time_bump", -1e-6)],
)
def test_lookback_bump_validation_names_parameter(kwarg: str, value: float) -> None:
    with pytest.raises(ValidationError, match=kwarg):
        price_lookback(_LOOKBACK, **{kwarg: value})
