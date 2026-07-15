"""Unit tests for the Black-76 kernel (Task 14, Reqs 5.1-5.3).

Covers: (a) a known example checked against an independently computed closed
form; (b) Property 14 premium <-> implied-vol round-trip; (c) Property 15 Greek
relationships plus finite-difference cross-checks of delta/theta/rho; (d) the
no-arbitrage bounds precondition on implied vol; (e) the sigma -> 0 / T -> 0
fall-back to discounted intrinsic value.
"""

from __future__ import annotations

import math

import pytest

from quantvolt.numerics.black76 import (
    black76_greeks,
    black76_implied_vol,
    black76_price,
)
from quantvolt.numerics.rootfind import finite_difference_bump


def _norm_cdf(x: float) -> float:
    """Independent standard normal CDF via ``math.erf`` (not scipy)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# --- (a) known example vs an independently computed closed form ------------


def test_price_call_matches_independent_closed_form() -> None:
    forward, strike, sigma, ttm, df = 100.0, 95.0, 0.25, 0.5, 0.97
    sqrt_t = math.sqrt(ttm)
    d1 = (math.log(forward / strike) + 0.5 * sigma**2 * ttm) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    expected = df * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
    assert black76_price("call", forward, strike, sigma, ttm, df) == pytest.approx(
        expected, abs=1e-10
    )


def test_price_put_matches_independent_closed_form() -> None:
    forward, strike, sigma, ttm, df = 100.0, 95.0, 0.25, 0.5, 0.97
    sqrt_t = math.sqrt(ttm)
    d1 = (math.log(forward / strike) + 0.5 * sigma**2 * ttm) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    expected = df * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))
    assert black76_price("put", forward, strike, sigma, ttm, df) == pytest.approx(
        expected, abs=1e-10
    )


def test_price_atm_reference_value() -> None:
    # F == K, sigma = 0.2, T = 1, DF = 1: d1 = 0.1, d2 = -0.1.
    d1, d2 = 0.1, -0.1
    expected = 100.0 * _norm_cdf(d1) - 100.0 * _norm_cdf(d2)
    assert black76_price("call", 100.0, 100.0, 0.2, 1.0, 1.0) == pytest.approx(expected, abs=1e-10)


def test_put_call_parity_of_price() -> None:
    # call - put = DF*(F - K) for a European option on a forward.
    forward, strike, sigma, ttm, df = 105.0, 100.0, 0.3, 1.5, 0.94
    call = black76_price("call", forward, strike, sigma, ttm, df)
    put = black76_price("put", forward, strike, sigma, ttm, df)
    assert call - put == pytest.approx(df * (forward - strike), abs=1e-10)


# --- (b) Property 14: premium <-> implied-vol round-trip -------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize(
    ("forward", "strike", "sigma0", "ttm", "df"),
    [
        (100.0, 100.0, 0.20, 1.00, 1.000),
        (100.0, 90.0, 0.35, 0.50, 0.980),
        (50.0, 60.0, 0.45, 2.00, 0.930),
        (120.0, 100.0, 0.15, 0.25, 0.995),
        (80.0, 85.0, 0.60, 3.00, 0.900),
    ],
)
def test_implied_vol_round_trip_recovers_sigma(
    option_type: str, forward: float, strike: float, sigma0: float, ttm: float, df: float
) -> None:
    premium = black76_price(option_type, forward, strike, sigma0, ttm, df)
    recovered = black76_implied_vol(option_type, premium, forward, strike, ttm, df)
    assert recovered == pytest.approx(sigma0, abs=1e-4)


# --- (c) Property 15: Greek relationships + finite-difference checks --------


def test_call_and_put_share_gamma_and_vega() -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    call = black76_greeks("call", forward, strike, sigma, ttm, df)
    put = black76_greeks("put", forward, strike, sigma, ttm, df)
    assert call.gamma == pytest.approx(put.gamma, abs=1e-12)
    assert call.vega == pytest.approx(put.vega, abs=1e-12)


def test_delta_put_call_parity_equals_discount_factor() -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    call = black76_greeks("call", forward, strike, sigma, ttm, df)
    put = black76_greeks("put", forward, strike, sigma, ttm, df)
    assert call.delta - put.delta == pytest.approx(df, abs=1e-12)


def test_vega_positive_and_theta_negative_for_long_option() -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    for option_type in ("call", "put"):
        greeks = black76_greeks(option_type, forward, strike, sigma, ttm, df)
        assert greeks.vega > 0.0
        assert greeks.theta < 0.0


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_delta_matches_finite_difference(option_type: str) -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    analytic = black76_greeks(option_type, forward, strike, sigma, ttm, df).delta
    numeric = finite_difference_bump(
        lambda x: black76_price(option_type, x, strike, sigma, ttm, df), forward, 1e-3
    )
    assert analytic == pytest.approx(numeric, abs=1e-5)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_theta_matches_negative_time_derivative(option_type: str) -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    analytic = black76_greeks(option_type, forward, strike, sigma, ttm, df).theta
    rate = -math.log(df) / ttm
    # theta is -d(price)/d(T) as the *total* derivative with r held fixed and
    # DF = exp(-r*T), so the finite difference must let DF track T (not stay put).
    dprice_dt = finite_difference_bump(
        lambda x: black76_price(option_type, forward, strike, sigma, x, math.exp(-rate * x)),
        ttm,
        1e-4,
    )
    assert analytic == pytest.approx(-dprice_dt, abs=1e-4)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_rho_matches_finite_difference_in_rate(option_type: str) -> None:
    forward, strike, sigma, ttm, df = 100.0, 105.0, 0.30, 1.25, 0.96
    analytic = black76_greeks(option_type, forward, strike, sigma, ttm, df).rho
    rate = -math.log(df) / ttm
    # rho = d(price)/d(r) with the forward held fixed and DF = exp(-r*T).
    numeric = finite_difference_bump(
        lambda r: black76_price(option_type, forward, strike, sigma, ttm, math.exp(-r * ttm)),
        rate,
        1e-5,
    )
    assert analytic == pytest.approx(numeric, abs=1e-4)


# --- (d) no-arbitrage bounds precondition ----------------------------------


def test_implied_vol_call_below_intrinsic_raises() -> None:
    forward, strike, ttm, df = 100.0, 90.0, 1.0, 0.98
    lower = df * (forward - strike)  # discounted intrinsic
    with pytest.raises(ValueError, match="no-arbitrage"):
        black76_implied_vol("call", lower - 1.0, forward, strike, ttm, df)


def test_implied_vol_call_above_forward_raises() -> None:
    forward, strike, ttm, df = 100.0, 90.0, 1.0, 0.98
    upper = df * forward
    with pytest.raises(ValueError, match="no-arbitrage"):
        black76_implied_vol("call", upper + 1.0, forward, strike, ttm, df)


def test_implied_vol_put_below_intrinsic_raises() -> None:
    forward, strike, ttm, df = 90.0, 100.0, 1.0, 0.98
    lower = df * (strike - forward)
    with pytest.raises(ValueError, match="no-arbitrage"):
        black76_implied_vol("put", lower - 1.0, forward, strike, ttm, df)


def test_implied_vol_put_above_strike_raises() -> None:
    forward, strike, ttm, df = 90.0, 100.0, 1.0, 0.98
    upper = df * strike
    with pytest.raises(ValueError, match="no-arbitrage"):
        black76_implied_vol("put", upper + 1.0, forward, strike, ttm, df)


def test_implied_vol_exact_bound_raises() -> None:
    # The bounds are open: the premium must be strictly inside them.
    forward, strike, ttm, df = 100.0, 90.0, 1.0, 0.98
    with pytest.raises(ValueError):
        black76_implied_vol("call", df * forward, forward, strike, ttm, df)
    with pytest.raises(ValueError):
        black76_implied_vol("call", df * (forward - strike), forward, strike, ttm, df)


# --- (e) sigma -> 0 / T -> 0 fall back to discounted intrinsic --------------


def test_zero_sigma_is_discounted_intrinsic() -> None:
    df = 0.97
    assert black76_price("call", 105.0, 100.0, 0.0, 1.0, df) == pytest.approx(df * 5.0, abs=1e-12)
    assert black76_price("put", 105.0, 100.0, 0.0, 1.0, df) == pytest.approx(0.0, abs=1e-12)
    # Out-of-the-money call, in-the-money put.
    assert black76_price("call", 95.0, 100.0, 0.0, 1.0, df) == pytest.approx(0.0, abs=1e-12)
    assert black76_price("put", 95.0, 100.0, 0.0, 1.0, df) == pytest.approx(df * 5.0, abs=1e-12)


def test_zero_time_to_expiry_is_discounted_intrinsic() -> None:
    assert black76_price("call", 110.0, 100.0, 0.30, 0.0, 1.0) == pytest.approx(10.0, abs=1e-12)
    assert black76_price("put", 110.0, 100.0, 0.30, 0.0, 1.0) == pytest.approx(0.0, abs=1e-12)


# --- Fix 4 regression: black76_greeks lacked the sigma*sqrt(T) == 0 fallback ------


@pytest.mark.parametrize(
    ("sigma", "ttm"), [(0.0, 1.0), (0.30, 0.0)], ids=["zero_sigma", "zero_time"]
)
@pytest.mark.parametrize("option_type", ["call", "put"])
@pytest.mark.parametrize(
    ("forward", "strike", "moneyness"),
    [(110.0, 100.0, "in_or_out"), (90.0, 100.0, "out_or_in"), (100.0, 100.0, "atm")],
)
def test_greeks_degenerate_limit_prices_without_error(
    sigma: float, ttm: float, option_type: str, forward: float, strike: float, moneyness: str
) -> None:
    # Previously raised a raw ZeroDivisionError (verified) at both sigma=0 and ttm=0.
    df = 0.97
    greeks = black76_greeks(option_type, forward, strike, sigma, ttm, df)
    assert greeks.gamma == 0.0
    assert greeks.vega == 0.0
    price = black76_price(option_type, forward, strike, sigma, ttm, df)
    assert greeks.rho == pytest.approx(-ttm * price, abs=1e-12)


def test_greeks_degenerate_delta_is_a_step_at_the_strike() -> None:
    df = 0.97
    # Call: DF in the money, 0 out of the money.
    assert black76_greeks("call", 110.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(df)
    assert black76_greeks("call", 90.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(0.0)
    assert black76_greeks("call", 110.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(df)
    assert black76_greeks("call", 90.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(0.0)
    # Put: -DF in the money, 0 out of the money.
    assert black76_greeks("put", 90.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(-df)
    assert black76_greeks("put", 110.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(0.0)
    assert black76_greeks("put", 90.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(-df)
    assert black76_greeks("put", 110.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(0.0)


def test_greeks_degenerate_atm_delta_is_half_discount_factor_by_convention() -> None:
    # Documented convention: the continuous sigma -> 0+ limit at F == K, N(0) = 0.5.
    df = 0.97
    assert black76_greeks("call", 100.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(0.5 * df)
    assert black76_greeks("call", 100.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(0.5 * df)
    assert black76_greeks("put", 100.0, 100.0, 0.0, 1.0, df).delta == pytest.approx(-0.5 * df)
    assert black76_greeks("put", 100.0, 100.0, 0.30, 0.0, df).delta == pytest.approx(-0.5 * df)


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_greeks_zero_sigma_theta_matches_carry_only(option_type: str) -> None:
    # theta = rate*price with the vega-driven term dropped, matching the continuous
    # sigma -> 0 limit of the normal-branch formula (the second term vanishes with sigma).
    forward, strike, ttm, df = 105.0, 100.0, 1.25, 0.96
    rate = -math.log(df) / ttm
    price = black76_price(option_type, forward, strike, 0.0, ttm, df)
    expected_theta = rate * price
    assert black76_greeks(option_type, forward, strike, 0.0, ttm, df).theta == pytest.approx(
        expected_theta, abs=1e-12
    )


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_greeks_zero_time_theta_is_zero(option_type: str) -> None:
    # rate = -ln(DF)/T is undefined at T == 0 (0/0); the carry contribution is defined
    # to be exactly 0 there (a matured position has no further time decay).
    greeks = black76_greeks(option_type, 105.0, 100.0, 0.30, 0.0, 0.96)
    assert greeks.theta == 0.0


def test_greeks_zero_sigma_delta_matches_small_sigma_limit() -> None:
    # Continuity sanity check: as sigma -> 0+ with T fixed, the analytic (non-degenerate)
    # delta converges to the degenerate-branch value at the same (F, K).
    forward, strike, ttm, df = 100.0, 100.0, 1.0, 0.97
    tiny = black76_greeks("call", forward, strike, 1e-6, ttm, df).delta
    zero = black76_greeks("call", forward, strike, 0.0, ttm, df).delta
    assert tiny == pytest.approx(zero, abs=1e-6)


# --- (f) keyword-only Brent bracket / max_iter overrides --------------------


def test_implied_vol_default_bracket_matches_explicit_defaults() -> None:
    # The defaults (vol_lower=1e-9, vol_upper=10.0, max_iter=100) must reproduce
    # the previously hardcoded bracket bit-for-bit.
    forward, strike, sigma0, ttm, df = 100.0, 90.0, 0.35, 0.5, 0.98
    premium = black76_price("call", forward, strike, sigma0, ttm, df)
    implicit = black76_implied_vol("call", premium, forward, strike, ttm, df)
    explicit = black76_implied_vol(
        "call", premium, forward, strike, ttm, df, vol_lower=1e-9, vol_upper=10.0, max_iter=100
    )
    assert implicit == explicit


def test_vol_upper_override_rejects_premium_needing_higher_vol() -> None:
    # A premium that requires sigma above a tightened vol_upper cannot be
    # bracketed, so Brent's precondition raises instead of silently searching
    # [1e-9, 10.0].
    forward, strike, sigma0, ttm, df = 100.0, 90.0, 2.0, 0.5, 0.98
    premium = black76_price("call", forward, strike, sigma0, ttm, df)
    with pytest.raises(ValueError):
        black76_implied_vol("call", premium, forward, strike, ttm, df, vol_upper=0.5)


def test_vol_lower_must_be_positive() -> None:
    with pytest.raises(ValueError, match="vol_lower"):
        black76_implied_vol("call", 5.0, 100.0, 95.0, 1.0, 0.98, vol_lower=0.0)


def test_vol_upper_must_exceed_vol_lower() -> None:
    with pytest.raises(ValueError, match="vol_upper"):
        black76_implied_vol("call", 5.0, 100.0, 95.0, 1.0, 0.98, vol_lower=1.0, vol_upper=1.0)


def test_max_iter_override_changes_convergence_behavior() -> None:
    forward, strike, sigma0, ttm, df = 100.0, 90.0, 0.35, 0.5, 0.98
    premium = black76_price("call", forward, strike, sigma0, ttm, df)
    # A generous max_iter converges normally.
    recovered = black76_implied_vol("call", premium, forward, strike, ttm, df, max_iter=100)
    assert recovered == pytest.approx(sigma0, abs=1e-4)
    # A single iteration is not enough for scipy's brentq to satisfy its
    # tolerance from this bracket, so it raises instead of returning silently.
    with pytest.raises(RuntimeError):
        black76_implied_vol("call", premium, forward, strike, ttm, df, max_iter=1)
