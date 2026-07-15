"""Unit tests for the vanilla and cap/floor pricers (Task 27, Reqs 5.4-5.6).

Covers: (a) premium == kernel price * notional and the cap->call / floor->put
mapping; (b) Greeks scale linearly with notional; (c) every validation path
raises ValidationError naming the offending parameter; (d) Property 16 — the
cap/floor aggregate equals the sum of the per-period results exactly; (e) the
120-period cap and the empty/mismatched-strip rejections; (f) the <50 ms
single-option budget (Req 5.5); (g) input immutability.
"""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Literal

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.greeks import Greeks
from quantvolt.numerics.black76 import black76_greeks, black76_price
from quantvolt.pricing.vanilla import (
    CapFloorRequest,
    VanillaOptionRequest,
    price_cap_floor,
    price_vanilla_option,
)
from quantvolt.testing import assert_input_unchanged

_BASE = VanillaOptionRequest(
    option_type="call",
    strike=95.0,
    notional=1.0,
    forward=100.0,
    sigma=0.25,
    time_to_expiry=0.5,
    discount_factor=0.97,
)


def _caplets(
    count: int, option_type: Literal["call", "put", "cap", "floor"] = "cap"
) -> tuple[VanillaOptionRequest, ...]:
    """A strip of `count` distinct caplets (own forward/sigma/ttm/DF per period)."""
    return tuple(
        VanillaOptionRequest(
            option_type=option_type,
            strike=50.0,
            notional=10.0,
            forward=48.0 + i,
            sigma=0.30 + 0.01 * i,
            time_to_expiry=0.25 * (i + 1),
            discount_factor=1.0 - 0.002 * (i + 1),
        )
        for i in range(count)
    )


# --- (a) premium matches the kernel, scaled by notional ---------------------


@pytest.mark.parametrize(
    ("option_type", "kernel_side"),
    [("call", "call"), ("put", "put"), ("cap", "call"), ("floor", "put")],
)
def test_premium_is_kernel_price_times_notional(
    option_type: Literal["call", "put", "cap", "floor"],
    kernel_side: Literal["call", "put"],
) -> None:
    request = replace(_BASE, option_type=option_type, notional=1500.0)
    expected = 1500.0 * black76_price(
        kernel_side,
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    assert price_vanilla_option(request).premium == expected


def test_cap_prices_as_call_and_floor_as_put() -> None:
    # A caplet is a call on the floating price, a floorlet a put.
    call = price_vanilla_option(replace(_BASE, option_type="call"))
    cap = price_vanilla_option(replace(_BASE, option_type="cap"))
    put = price_vanilla_option(replace(_BASE, option_type="put"))
    floor = price_vanilla_option(replace(_BASE, option_type="floor"))
    assert cap == call
    assert floor == put
    assert cap != floor


# --- (b) Greeks scale with notional -----------------------------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_greeks_are_kernel_greeks_scaled_by_notional(option_type: Literal["call", "put"]) -> None:
    notional = 250.0
    request = replace(_BASE, option_type=option_type, notional=notional)
    expected = black76_greeks(
        option_type,
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    ).scale(notional)
    assert price_vanilla_option(request).greeks == expected


def test_greeks_scale_linearly_between_notionals() -> None:
    unit = price_vanilla_option(replace(_BASE, notional=1.0))
    sized = price_vanilla_option(replace(_BASE, notional=1000.0))
    assert sized.greeks == unit.greeks.scale(1000.0)
    assert sized.premium == pytest.approx(1000.0 * unit.premium, rel=1e-12)


# --- (c) every invalid domain raises ValidationError naming the parameter ---


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("forward", 0.0),
        ("forward", -100.0),
        ("strike", 0.0),
        ("strike", -95.0),
        ("sigma", 0.0),
        ("sigma", -0.25),
        ("time_to_expiry", 0.0),
        ("time_to_expiry", -0.5),
        ("discount_factor", 0.0),
        ("discount_factor", -0.5),
        ("discount_factor", 1.5),
        ("notional", 0.0),
        ("notional", -1.0),
    ],
)
def test_invalid_domain_raises_naming_parameter(field: str, bad_value: float) -> None:
    bad = replace(_BASE, **{field: bad_value})
    with pytest.raises(ValidationError, match=field):
        price_vanilla_option(bad)


@pytest.mark.parametrize(("field", "bad_value"), [("strike", 0.0), ("notional", -10.0)])
def test_cap_floor_strip_level_domains_validated(field: str, bad_value: float) -> None:
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(2))
    with pytest.raises(ValidationError, match=field):
        price_cap_floor(replace(request, **{field: bad_value}))


def test_cap_floor_rejects_caplet_strike_diverging_from_strip() -> None:
    """Regression: strip-level strike must not be validated then silently
    ignored while a divergent caplet strike drives pricing unnoticed."""
    caplets = (*_caplets(2), replace(_caplets(1)[0], strike=999.0))
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=caplets)
    with pytest.raises(ValidationError, match=r"caplets\[2\]\.strike"):
        price_cap_floor(request)


def test_cap_floor_rejects_caplet_notional_diverging_from_strip() -> None:
    """Regression: strip-level notional must not be validated then silently
    ignored while a divergent caplet notional drives pricing unnoticed."""
    caplets = (*_caplets(2), replace(_caplets(1)[0], notional=999.0))
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=caplets)
    with pytest.raises(ValidationError, match=r"caplets\[2\]\.notional"):
        price_cap_floor(request)


def test_cap_floor_propagates_bad_caplet_domain() -> None:
    caplets = (*_caplets(2), replace(_caplets(1)[0], sigma=-0.3))
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=caplets)
    with pytest.raises(ValidationError, match="sigma"):
        price_cap_floor(request)


# --- (d) Property 16: aggregate == sum of per-period (exact) -----------------


@pytest.mark.parametrize(("strip_type", "caplet_type"), [("cap", "cap"), ("floor", "floor")])
def test_strip_aggregate_equals_sum_of_per_period(
    strip_type: Literal["cap", "floor"],
    caplet_type: Literal["call", "put", "cap", "floor"],
) -> None:
    request = CapFloorRequest(
        option_type=strip_type, strike=50.0, notional=10.0, caplets=_caplets(3, caplet_type)
    )
    result = price_cap_floor(request)

    assert len(result.per_period) == 3
    for caplet, per in zip(request.caplets, result.per_period, strict=True):
        assert per == price_vanilla_option(caplet)

    assert result.premium == sum(per.premium for per in result.per_period)
    expected_greeks = Greeks.zero()
    for per in result.per_period:
        expected_greeks = expected_greeks + per.greeks
    assert result.greeks == expected_greeks


def test_strip_accepts_call_put_labels_on_matching_side() -> None:
    # "call" caplets in a cap strip price on the same side as "cap" caplets.
    as_cap = price_cap_floor(
        CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(3, "cap"))
    )
    as_call = price_cap_floor(
        CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(3, "call"))
    )
    assert as_cap == as_call


# --- (e) strip-shape rejections ----------------------------------------------


def test_strip_of_exactly_120_periods_is_accepted() -> None:
    result = price_cap_floor(
        CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(120))
    )
    assert len(result.per_period) == 120


def test_strip_over_120_periods_rejected_before_pricing() -> None:
    caplets = _caplets(121)
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=caplets)
    with pytest.raises(ValidationError, match=r"caplets.*120"):
        price_cap_floor(request)


def test_empty_strip_rejected() -> None:
    request = CapFloorRequest(option_type="floor", strike=50.0, notional=10.0, caplets=())
    with pytest.raises(ValidationError, match="caplets"):
        price_cap_floor(request)


def test_caplet_on_wrong_side_of_strip_rejected() -> None:
    mixed = _caplets(2) + _caplets(1, "put")
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=mixed)
    with pytest.raises(ValidationError, match=r"caplets\[2\]\.option_type"):
        price_cap_floor(request)


# --- (f) Req 5.5: single option well under 50 ms -----------------------------


def test_single_option_prices_well_under_50_ms() -> None:
    price_vanilla_option(_BASE)  # warm-up: first call pays scipy dispatch setup
    start = time.perf_counter()
    price_vanilla_option(_BASE)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.05


# --- (g) immutability of inputs ----------------------------------------------


def test_pricers_do_not_mutate_inputs() -> None:
    assert_input_unchanged(price_vanilla_option, _BASE)
    strip = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(3))
    assert_input_unchanged(price_cap_floor, strip)


# --- (new) max_strip_periods keyword-only parameter --------------------------


def test_max_strip_periods_default_matches_hardcoded_120() -> None:
    strip = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(3))
    baseline = price_cap_floor(strip)
    explicit = price_cap_floor(strip, max_strip_periods=120)
    assert explicit == baseline


def test_max_strip_periods_default_still_rejects_over_120() -> None:
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(121))
    with pytest.raises(ValidationError, match=r"caplets.*120"):
        price_cap_floor(request)


def test_max_strip_periods_override_allows_a_longer_strip() -> None:
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(121))
    result = price_cap_floor(request, max_strip_periods=121)
    assert len(result.per_period) == 121


def test_max_strip_periods_override_rejects_a_shorter_strip() -> None:
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(5))
    with pytest.raises(ValidationError, match=r"caplets.*3"):
        price_cap_floor(request, max_strip_periods=3)


def test_max_strip_periods_below_one_rejected() -> None:
    request = CapFloorRequest(option_type="cap", strike=50.0, notional=10.0, caplets=_caplets(1))
    with pytest.raises(ValidationError, match="max_strip_periods"):
        price_cap_floor(request, max_strip_periods=0)
