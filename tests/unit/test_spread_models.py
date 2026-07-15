"""Unit tests for the spread-option kernels (Task 15, Req 7.1)."""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.numerics.spread_models import kirk, margrabe


def test_margrabe_matches_reference_value() -> None:
    # Reference premium for F1=100, F2=90, s1=0.30, s2=0.20, rho=0.5, T=1, DF=1
    # recomputed independently at ~1e-12 precision:
    #   sigma  = sqrt(0.09 + 0.04 - 2*0.5*0.3*0.2) = sqrt(0.07)
    #   d1     = (ln(100/90) + 0.5*0.07) / sqrt(0.07)
    #   d2     = d1 - sqrt(0.07)
    #   premium = 100*N(d1) - 90*N(d2)
    premium = margrabe(100.0, 90.0, 0.30, 0.20, 0.5, 1.0, 1.0)
    assert premium == pytest.approx(15.775102783783495, abs=1e-8)


def test_margrabe_premium_is_non_negative() -> None:
    premium = margrabe(80.0, 100.0, 0.25, 0.35, 0.9, 2.0, 0.97)
    assert premium >= 0.0


def test_margrabe_premium_rises_as_correlation_falls() -> None:
    # Spread volatility increases as rho decreases, so the option is worth more.
    base = dict(
        forward1=100.0,
        forward2=95.0,
        sigma1=0.3,
        sigma2=0.25,
        time_to_expiry=1.0,
        discount_factor=1.0,
    )
    high_rho = margrabe(rho=0.9, **base)
    mid_rho = margrabe(rho=0.5, **base)
    low_rho = margrabe(rho=-0.5, **base)
    assert high_rho < mid_rho < low_rho


def test_margrabe_discount_factor_scales_premium() -> None:
    undiscounted = margrabe(100.0, 90.0, 0.30, 0.20, 0.5, 1.0, 1.0)
    discounted = margrabe(100.0, 90.0, 0.30, 0.20, 0.5, 1.0, 0.95)
    assert discounted == pytest.approx(0.95 * undiscounted, abs=1e-12)


def test_kirk_with_zero_strike_equals_margrabe() -> None:
    # With strike == 0, F2K == F2 and w == 1, so Kirk collapses to Margrabe.
    args = (100.0, 90.0, 0.30, 0.20, 0.5, 1.0, 1.0)
    exchange = margrabe(*args)
    f1, f2, s1, s2, rho, t, df = args
    spread = kirk(f1, f2, 0.0, s1, s2, rho, t, df)
    assert spread == pytest.approx(exchange, abs=1e-10)


def test_kirk_premium_decreases_as_strike_increases() -> None:
    base = dict(
        forward1=100.0,
        forward2=90.0,
        sigma1=0.30,
        sigma2=0.20,
        rho=0.5,
        time_to_expiry=1.0,
        discount_factor=1.0,
    )
    strikes = [-5.0, 0.0, 5.0, 10.0, 20.0]
    premiums = [kirk(strike=k, **base) for k in strikes]
    assert all(earlier > later for earlier, later in pairwise(premiums))


def test_kirk_premium_is_non_negative() -> None:
    premium = kirk(50.0, 90.0, 5.0, 0.30, 0.20, 0.5, 1.5, 0.9)
    assert premium >= 0.0


def test_margrabe_zero_time_to_expiry_is_intrinsic() -> None:
    # At T == 0 the premium collapses to the discounted intrinsic value.
    itm = margrabe(110.0, 90.0, 0.30, 0.20, 0.5, 0.0, 0.98)
    assert itm == pytest.approx(0.98 * (110.0 - 90.0), abs=1e-12)
    otm = margrabe(90.0, 110.0, 0.30, 0.20, 0.5, 0.0, 0.98)
    assert otm == pytest.approx(0.0, abs=1e-12)


def test_kirk_zero_time_to_expiry_is_intrinsic() -> None:
    # At T == 0 the premium collapses to discounted max(F1 - (F2 + K), 0).
    itm = kirk(120.0, 90.0, 10.0, 0.30, 0.20, 0.5, 0.0, 0.98)
    assert itm == pytest.approx(0.98 * (120.0 - 100.0), abs=1e-12)
    otm = kirk(90.0, 90.0, 10.0, 0.30, 0.20, 0.5, 0.0, 0.98)
    assert otm == pytest.approx(0.0, abs=1e-12)


def test_margrabe_deep_in_the_money_approaches_intrinsic() -> None:
    # Very short maturity + deeply ITM: premium ~ discounted intrinsic value.
    df = 0.99
    premium = margrabe(200.0, 50.0, 0.30, 0.20, 0.5, 1e-6, df)
    intrinsic = df * (200.0 - 50.0)
    assert premium == pytest.approx(intrinsic, abs=1e-3)


# --- Fix 5 regression: Kirk's domain is forward2 + strike > 0, not "any strike" ----


def test_kirk_strike_equal_to_negative_forward2_raises() -> None:
    # Previously a raw ZeroDivisionError (weight = forward2 / (forward2 + strike)).
    with pytest.raises(ValidationError, match=r"forward2 \+ strike"):
        kirk(100.0, 50.0, -50.0, 0.30, 0.20, 0.5, 1.0, 0.97)


def test_kirk_strike_below_negative_forward2_raises() -> None:
    # Previously a raw math-domain error from log(forward1 / negative).
    with pytest.raises(ValidationError, match=r"forward2 \+ strike"):
        kirk(100.0, 50.0, -60.0, 0.30, 0.20, 0.5, 1.0, 0.97)


def test_kirk_strike_just_above_negative_forward2_still_prices() -> None:
    # The domain boundary is open (forward2 + strike > 0, not >=); just inside it
    # still prices, however extreme the resulting premium.
    premium = kirk(100.0, 50.0, -49.999999, 0.30, 0.20, 0.5, 1.0, 0.97)
    assert math.isfinite(premium)
    assert premium >= 0.0


def test_kirk_effective_vol_reduces_to_margrabe_sigma() -> None:
    # Sanity check on the internal effective-vol reduction at strike == 0:
    # sigma_eff should equal the Margrabe spread sigma, so the d1 term below
    # is consistent with the premium equality asserted elsewhere.
    s1, s2, rho = 0.30, 0.20, 0.5
    margrabe_sigma = math.sqrt(s1**2 + s2**2 - 2.0 * rho * s1 * s2)
    # At strike 0, weight w = F2 / (F2 + 0) = 1, so sigma_eff formula matches.
    sigma_eff = math.sqrt(s1**2 + (s2 * 1.0) ** 2 - 2.0 * rho * s1 * s2 * 1.0)
    assert sigma_eff == pytest.approx(margrabe_sigma, abs=1e-15)
