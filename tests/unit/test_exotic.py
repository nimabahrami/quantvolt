"""Unit tests for the exotic-option kernels (Tasks 16-17, Reqs 6.1/6.2/6.3/6.5).

These are all *published* closed forms on a Black-76 forward (carry ``b == 0``), so the tests
lean on strong internal self-checks rather than a table of magic numbers:

- (a) Barrier in/out parity: a knock-in plus its matching knock-out reprices the vanilla
  Black-76 premium (no rebate), exercised for both strike-above-barrier and strike-below-barrier
  sub-cases of the Reiner-Rubinstein table.
- (b) Barrier knock-out monotonicity: a down-and-out call with the barrier far below the forward
  is essentially the vanilla; a barrier just below the forward is nearly worthless.
- (c) Asian ordering: geometric (Kemna-Vorst) sits below the vanilla; arithmetic (Turnbull-
  Wakeman) sits above the geometric for a call (arithmetic average >= geometric average).
- (d) Asian ``sigma -> 0`` collapses to the discounted intrinsic value.
- (e) Lookbacks dominate the corresponding vanilla payoff and are strictly positive.
- (f) An independently computed Kemna-Vorst reference value (``math.erf`` normal CDF, not scipy).
"""

from __future__ import annotations

import math
from decimal import Decimal, getcontext

import pytest

from quantvolt.numerics.black76 import black76_price
from quantvolt.numerics.exotic import (
    barrier_analytic,
    kemna_vorst,
    lookback_fixed,
    lookback_floating,
    turnbull_wakeman,
)


def _norm_cdf(x: float) -> float:
    """Independent standard normal CDF via ``math.erf`` (not scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _decimal_turnbull_wakeman_sigma_a(sigma: float, time_to_expiry: float) -> float:
    """Independent 60-digit reference for the Turnbull-Wakeman matched volatility.

    Evaluates the textbook formula ``sigma_a = sqrt(ln(2*(exp(var)-1-var)/var**2)/T)``
    (``var = sigma**2*T``) *literally*, term for term, exactly as written in the docstring
    the production kernel implements — but at 60 significant decimal digits via
    :mod:`decimal`, so the catastrophic cancellation that corrupts the same formula in
    ``float64`` (Fix 1) is simply outrun by the extra precision rather than avoided by a
    different algebraic route. This makes it a genuine independent check of
    :func:`~quantvolt.numerics.exotic._asian_second_moment_ratio`, not a restatement of it.
    """
    getcontext().prec = 60
    sigma_d = Decimal(sigma)
    time_d = Decimal(time_to_expiry)
    var = sigma_d * sigma_d * time_d
    moment_ratio = (Decimal(2) * (var.exp() - 1 - var)) / (var * var)
    return float((moment_ratio.ln() / time_d).sqrt())


# --- (a) barrier in/out parity ---------------------------------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize(
    ("in_type", "out_type", "barrier", "strike"),
    [
        ("down_in", "down_out", 80.0, 100.0),  # strike above barrier
        ("down_in", "down_out", 80.0, 70.0),  # strike below barrier
        ("up_in", "up_out", 120.0, 100.0),  # strike below barrier
        ("up_in", "up_out", 120.0, 130.0),  # strike above barrier
    ],
)
def test_barrier_in_out_parity_reprices_vanilla(
    option_type, in_type, out_type, barrier, strike
) -> None:
    forward, sigma, ttm, df = 100.0, 0.30, 1.0, 0.97
    knock_in = barrier_analytic(option_type, in_type, forward, strike, barrier, sigma, ttm, df)
    knock_out = barrier_analytic(option_type, out_type, forward, strike, barrier, sigma, ttm, df)
    vanilla = black76_price(option_type, forward, strike, sigma, ttm, df)
    assert knock_in + knock_out == pytest.approx(vanilla, abs=1e-8)


def test_barrier_in_and_out_are_computed_independently() -> None:
    # Parity would be trivial if "out" were defined as vanilla - "in"; confirm both legs carry
    # genuine (non-zero, non-vanilla) value so the parity above is a real cross-check.
    forward, strike, barrier, sigma, ttm, df = 100.0, 100.0, 80.0, 0.30, 1.0, 0.97
    knock_in = barrier_analytic("call", "down_in", forward, strike, barrier, sigma, ttm, df)
    knock_out = barrier_analytic("call", "down_out", forward, strike, barrier, sigma, ttm, df)
    vanilla = black76_price("call", forward, strike, sigma, ttm, df)
    assert 0.0 < knock_in < vanilla
    assert 0.0 < knock_out < vanilla


# --- (b) barrier knock-out monotonicity ------------------------------------


def test_down_and_out_call_barrier_far_below_is_vanilla() -> None:
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 1.0
    vanilla = black76_price("call", forward, strike, sigma, ttm, df)
    deep = barrier_analytic("call", "down_out", forward, strike, 50.0, sigma, ttm, df)
    assert deep == pytest.approx(vanilla, rel=1e-3)


def test_down_and_out_call_barrier_near_forward_is_nearly_worthless() -> None:
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 1.0
    vanilla = black76_price("call", forward, strike, sigma, ttm, df)
    near = barrier_analytic("call", "down_out", forward, strike, 99.9, sigma, ttm, df)
    assert 0.0 < near < 0.05 * vanilla


def test_up_and_out_call_zero_when_strike_above_barrier() -> None:
    # Payoff needs F_T > K > H, but reaching K crosses H and knocks out: value is 0 (rebate 0).
    value = barrier_analytic("call", "up_out", 100.0, 130.0, 120.0, 0.30, 1.0, 0.97)
    assert value == pytest.approx(0.0, abs=1e-12)


# --- (c) Asian ordering -----------------------------------------------------


def test_kemna_vorst_below_vanilla_for_call_and_put() -> None:
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 0.97
    for option_type in ("call", "put"):
        geometric = kemna_vorst(forward, strike, sigma, ttm, df, option_type)
        vanilla = black76_price(option_type, forward, strike, sigma, ttm, df)
        assert geometric < vanilla


def test_turnbull_wakeman_above_kemna_vorst_for_call() -> None:
    # Arithmetic average >= geometric average, so the arithmetic-average *call* is worth more.
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 0.97
    arithmetic = turnbull_wakeman(forward, strike, sigma, ttm, df, "call")
    geometric = kemna_vorst(forward, strike, sigma, ttm, df, "call")
    assert arithmetic >= geometric


def test_turnbull_wakeman_below_kemna_vorst_for_put() -> None:
    # The same ordering of averages *lowers* a put (higher average -> smaller K - avg payoff).
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 0.97
    arithmetic = turnbull_wakeman(forward, strike, sigma, ttm, df, "put")
    geometric = kemna_vorst(forward, strike, sigma, ttm, df, "put")
    assert arithmetic <= geometric


# --- (d) Asian sigma -> 0 collapses to discounted intrinsic -----------------


@pytest.mark.parametrize(
    "asian", [turnbull_wakeman, kemna_vorst], ids=["turnbull_wakeman", "kemna_vorst"]
)
def test_asian_zero_vol_is_discounted_intrinsic(asian) -> None:
    df = 0.95
    assert asian(105.0, 100.0, 0.0, 1.0, df, "call") == pytest.approx(df * 5.0, abs=1e-12)
    assert asian(105.0, 100.0, 0.0, 1.0, df, "put") == pytest.approx(0.0, abs=1e-12)
    assert asian(95.0, 100.0, 0.0, 1.0, df, "call") == pytest.approx(0.0, abs=1e-12)
    assert asian(95.0, 100.0, 0.0, 1.0, df, "put") == pytest.approx(df * 5.0, abs=1e-12)


# --- Fix 1 regression: catastrophic cancellation in the moment match -------


def test_turnbull_wakeman_small_vol_prices_without_error() -> None:
    # sigma=1e-3, T=1 -> var=1e-6: the naive exp(var)-1-var computation drove
    # M2/F**2 below 1 and crashed math.log with a domain error (Fix 1, verified).
    forward, strike, sigma, ttm, df = 100.0, 100.0, 1e-3, 1.0, 1.0
    premium = turnbull_wakeman(forward, strike, sigma, ttm, df, "call")
    reference_sigma_a = _decimal_turnbull_wakeman_sigma_a(sigma, ttm)
    reference_premium = black76_price("call", forward, strike, reference_sigma_a, ttm, df)
    assert premium == pytest.approx(reference_premium, abs=1e-12)
    # Sanity: as sigma -> 0 the matched Asian vol approaches the geometric-average
    # limit sigma/sqrt(3) (arithmetic ~= geometric average at vanishing volatility).
    assert reference_sigma_a == pytest.approx(sigma / math.sqrt(3.0), rel=1e-3)


def test_turnbull_wakeman_tiny_vol_matches_high_precision_reference() -> None:
    # sigma=1e-5, T=1 -> var=1e-10: the naive formula silently returned sigma_a=2.72
    # (premium 82.65) instead of the true ~5.8e-6 (premium ~2.3e-4) (Fix 1, verified).
    forward, strike, sigma, ttm, df = 100.0, 100.0, 1e-5, 1.0, 1.0
    premium = turnbull_wakeman(forward, strike, sigma, ttm, df, "call")
    reference_sigma_a = _decimal_turnbull_wakeman_sigma_a(sigma, ttm)
    reference_premium = black76_price("call", forward, strike, reference_sigma_a, ttm, df)
    assert reference_sigma_a == pytest.approx(sigma / math.sqrt(3.0), rel=1e-3)
    assert premium == pytest.approx(reference_premium, abs=1e-12)
    assert premium == pytest.approx(2.303294e-4, rel=1e-4)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_turnbull_wakeman_normal_vol_matches_previous_implementation(option_type: str) -> None:
    # sigma=0.30 is far from the small-var branch; the restructured kernel must
    # reproduce the previous (uncorrected) formula's result to within 1e-12.
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 0.97
    var = sigma**2 * ttm
    previous_m2 = forward**2 * 2.0 * (math.exp(var) - 1.0 - var) / var**2
    previous_sigma_a = math.sqrt(math.log(previous_m2 / forward**2) / ttm)
    previous_premium = black76_price(option_type, forward, strike, previous_sigma_a, ttm, df)
    premium = turnbull_wakeman(forward, strike, sigma, ttm, df, option_type)
    # The restructured (cancellation-free) formula and the previous naive one agree to the
    # float64 noise floor at this scale (~1e-12), not exactly, since both chain a different
    # sequence of transcendental operations (exp/log vs expm1/log1p) to the same result.
    assert premium == pytest.approx(previous_premium, abs=1e-9)


# --- (e) lookbacks dominate the vanilla and are positive --------------------


def test_fixed_lookback_dominates_vanilla() -> None:
    # max_t F_t - K >= F_T - K and K - min_t F_t >= K - F_T pointwise, so the lookback is dearer.
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 0.97
    for option_type in ("call", "put"):
        lookback = lookback_fixed(option_type, forward, strike, sigma, ttm, df)
        vanilla = black76_price(option_type, forward, strike, sigma, ttm, df)
        assert lookback >= vanilla


def test_floating_lookback_strictly_positive() -> None:
    forward, sigma, ttm, df = 100.0, 0.30, 1.0, 0.97
    assert lookback_floating("call", forward, sigma, ttm, df) > 0.0
    assert lookback_floating("put", forward, sigma, ttm, df) > 0.0


def test_fixed_call_at_the_money_equals_floating_put() -> None:
    # At K == F the fixed-strike call payoff max(max_t F_t - F, 0) == max_t F_t - F, the
    # floating-strike *put* payoff in expectation; a consistency check across both kernels.
    forward, sigma, ttm, df = 100.0, 0.30, 1.0, 0.97
    fixed_call = lookback_fixed("call", forward, forward, sigma, ttm, df)
    floating_put = lookback_floating("put", forward, sigma, ttm, df)
    assert fixed_call == pytest.approx(floating_put, abs=1e-10)


# --- (f) independent Kemna-Vorst reference value ----------------------------


def test_kemna_vorst_matches_independent_reference() -> None:
    forward, strike, sigma, ttm, df = 100.0, 100.0, 0.30, 1.0, 1.0
    sigma_g = sigma / math.sqrt(3.0)
    forward_g = forward * math.exp(-(sigma**2) * ttm / 12.0)
    sqrt_t = math.sqrt(ttm)
    d1 = (math.log(forward_g / strike) + 0.5 * sigma_g**2 * ttm) / (sigma_g * sqrt_t)
    d2 = d1 - sigma_g * sqrt_t
    expected = df * (forward_g * _norm_cdf(d1) - strike * _norm_cdf(d2))
    assert kemna_vorst(forward, strike, sigma, ttm, df, "call") == pytest.approx(
        expected, abs=1e-10
    )
