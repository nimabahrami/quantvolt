"""Bachelier (normal) model correctness properties 98-101 (spec ``bachelier-negative-forwards``).

Continues the global Correctness-Property sequence catalogued in
``power-energy-quant-analysis/design.md`` (1-74) and extended through 97. Each property is verified
to hold from source Eq. (1) before encoding (see the spec design's derivations):

- **Property 98 — put-call parity.** ``C - P = DF*(F - K)`` for arbitrary (including negative)
  ``F``, ``K`` (from ``N(d) + N(-d) = 1``).
- **Property 99 — monotonicity in forward.** Call premium non-decreasing, put premium
  non-increasing in ``F``; ``0 <= delta_call <= DF`` and ``-DF <= delta_put <= 0``.
- **Property 100 — negative-translation invariance.** ``C(F, K) = C(F + c, K + c)`` for any real
  shift ``c`` — a distinctive arithmetic-Brownian property (``F - K`` and ``d_N`` are
  shift-invariant).
- **Property 101 — Black-76 <-> Bachelier ATM consistency.** At ``F = K``, the ``sigma_N``
  recovered from a Black-76 ATM premium via Eq. (2) satisfies ``sigma_N = sigma_BS*F0*g(v)`` with
  ``v = sigma_BS*sqrt(T)`` and ``g(v) -> 1`` as ``v -> 0``; documented bound: relative error
  ``<= 1.04e-2`` for ``v <= 0.5``.

All prices use the pure kernel :mod:`quantvolt.numerics.bachelier`; negative forwards/strikes are
deliberately in the sampled domain — the whole point of the model.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.numerics.bachelier import (
    bachelier_atm_seed,
    bachelier_greeks,
    bachelier_implied_vol,
    bachelier_price,
)
from quantvolt.numerics.black76 import black76_price

# Real-line forwards/strikes (the point of Bachelier), finite normal vols, tenors and DFs.
_forwards = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_strikes = st.floats(min_value=-200.0, max_value=200.0, allow_nan=False, allow_infinity=False)
_sigmas = st.floats(min_value=0.5, max_value=100.0, allow_nan=False, allow_infinity=False)
_tenors = st.floats(min_value=0.01, max_value=5.0, allow_nan=False, allow_infinity=False)
_dfs = st.floats(min_value=0.5, max_value=1.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=200)
@given(
    forward=_forwards,
    strike=_strikes,
    sigma=_sigmas,
    t=_tenors,
    df=_dfs,
)
def test_property_98_put_call_parity(
    forward: float, strike: float, sigma: float, t: float, df: float
) -> None:
    """Property 98: ``C - P = DF*(F - K)`` for arbitrary (incl. negative) F, K."""
    call = bachelier_price("call", forward, strike, sigma, t, df)
    put = bachelier_price("put", forward, strike, sigma, t, df)
    expected = df * (forward - strike)
    assert (call - put) == expected or abs((call - put) - expected) <= 1e-9 * max(
        abs(expected), 1.0
    )


@settings(max_examples=200)
@given(
    forward=_forwards,
    strike=_strikes,
    sigma=_sigmas,
    t=_tenors,
    df=_dfs,
    bump=st.floats(min_value=1e-3, max_value=50.0, allow_nan=False, allow_infinity=False),
)
def test_property_99_monotonic_in_forward(
    forward: float, strike: float, sigma: float, t: float, df: float, bump: float
) -> None:
    """Property 99: call premium non-decreasing, put non-increasing in F; delta bounds hold."""
    call_lo = bachelier_price("call", forward, strike, sigma, t, df)
    call_hi = bachelier_price("call", forward + bump, strike, sigma, t, df)
    put_lo = bachelier_price("put", forward, strike, sigma, t, df)
    put_hi = bachelier_price("put", forward + bump, strike, sigma, t, df)
    # Non-strict monotonicity (allow a tiny numerical slack).
    assert call_hi - call_lo >= -1e-9 * max(abs(call_lo), 1.0)
    assert put_hi - put_lo <= 1e-9 * max(abs(put_lo), 1.0)
    greeks_call = bachelier_greeks("call", forward, strike, sigma, t, df)
    greeks_put = bachelier_greeks("put", forward, strike, sigma, t, df)
    assert -1e-12 <= greeks_call.delta <= df + 1e-12
    assert -df - 1e-12 <= greeks_put.delta <= 1e-12


@settings(max_examples=200)
@given(
    option_type=st.sampled_from(["call", "put"]),
    forward=_forwards,
    strike=_strikes,
    sigma=_sigmas,
    t=_tenors,
    df=_dfs,
    shift=st.floats(min_value=-150.0, max_value=150.0, allow_nan=False, allow_infinity=False),
)
def test_property_100_negative_translation_invariance(
    option_type: str, forward: float, strike: float, sigma: float, t: float, df: float, shift: float
) -> None:
    """Property 100: ``C(F, K) = C(F + c, K + c)`` — distinctive arithmetic-Brownian invariance."""
    base = bachelier_price(option_type, forward, strike, sigma, t, df)
    shifted = bachelier_price(option_type, forward + shift, strike + shift, sigma, t, df)
    assert abs(base - shifted) <= 1e-9 * max(abs(base), 1.0) + 1e-12


@settings(max_examples=200)
@given(
    forward=st.floats(min_value=1.0, max_value=200.0, allow_nan=False, allow_infinity=False),
    sigma_bs=st.floats(min_value=0.01, max_value=0.7, allow_nan=False, allow_infinity=False),
    t=st.floats(min_value=0.02, max_value=2.0, allow_nan=False, allow_infinity=False),
)
def test_property_101_black_bachelier_atm_consistency(
    forward: float, sigma_bs: float, t: float
) -> None:
    """Property 101: ATM ``sigma_N`` from Eq. (2) agrees with ``sigma_BS*F0`` to a v-bounded error.

    At the money (``F = K``) the Black-76 undiscounted premium implies, via source Eq. (2)
    ``sigma_N = C_N(F0) sqrt(2*pi/T)``, a normal vol ``sigma_N = sigma_BS*F0*g(v)`` with
    ``v = sigma_BS*sqrt(T)`` and ``g(v) = (2N(v/2) - 1)*sqrt(2*pi)/v -> 1`` as ``v -> 0``. The
    error depends only on ``v``; the documented bound is relative error ``<= 1.04e-2`` for
    ``v <= 0.5``.
    """
    strike = forward  # at the money
    df = 1.0  # undiscounted; the ATM relation is a property of the undiscounted premium
    black_atm = black76_price("call", forward, strike, sigma_bs, t, df)
    # Recover sigma_N two ways and check they agree, then check the sigma_BS*F0 approximation.
    sigma_n_seed = bachelier_atm_seed(black_atm, t)
    sigma_n_inverted = bachelier_implied_vol(
        "call", black_atm, forward, strike, t, df, tol=1e-12, vol_upper=1e5
    )
    # Eq. (2) seed is exact at the money, so it must reproduce the Brent inversion.
    assert sigma_n_inverted == pytest.approx(sigma_n_seed, rel=1e-6)

    approx = sigma_bs * forward
    v = sigma_bs * math.sqrt(t)
    rel_err = abs(sigma_n_inverted - approx) / approx
    if v <= 0.5:
        assert rel_err <= 1.04e-2
    # In all cases the error shrinks toward 0 as v -> 0: bound it by ~v^2/24 * 3 (generous).
    assert rel_err <= 0.05 + v * v
