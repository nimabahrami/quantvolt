"""Property 93: analytic-vs-Monte-Carlo convergence (Requirement 8).

End-to-end checks of the native Rust Monte Carlo engine against QuantVolt's *own* closed forms.
Every test is **seeded** (Req 11.2 of the base spec — deterministic Rust RNG) and expresses its
tolerance as ``k x reported_standard_error`` for a stated ``k`` (never a bare magic number).

The six tests (design "test_mc_convergence.py"):

* (a) Black-76 vanilla vs ``asian_monte_carlo(averaging_points=1)`` — a single terminal fixing at
  ``T`` degenerates the Asian to a vanilla, validating the whole Rust GBM + discounting path
  (verified at monte_carlo.py:167-168 that ``averaging_points >= 1`` is accepted).
* (b) Margrabe (exact) vs correlated-forwards MC at ``K = 0`` — first cross-correlation-vs-closed-
  form check (``build_covariance`` + ``simulate_correlated_forwards``).
* (c) Kirk (approximation) vs the same MC at ``K != 0`` — measures Kirk's bias with a documented
  allowance.
* (d) Turnbull-Wakeman vs arithmetic-Asian MC — looser documented band (no closed reference; MC
  uses 252 discrete fixings to approximate continuous averaging).
* (e) MC put-call parity ``call - put = DF*(F - K)`` within the combined standard error.
* (f) Storage extrinsic -> 0 as ``sigma -> 1e-4``:
  ``storage_value(...).total ~= storage_intrinsic``.
* (g) Bachelier vanilla vs exact-terminal normal MC — ``F_T = F0 + sigma_N sqrt(T) Z`` sampled
  directly (no discretisation bias, since arithmetic BM has an exact terminal law), discounted
  payoff mean vs ``bachelier_price`` within ``k x SE``, **including a negative-forward case**.

**Not implemented (documented limitation, Requirement 8.8).** Barrier/lookback
analytic-vs-discrete-MC comparisons are deliberately omitted: the continuous-monitoring closed
forms (``barrier_analytic`` / lookback in ``numerics/exotic.py``) require a Broadie-Glasserman-Kou
discretisation correction to be comparable to a discretely-monitored MC. Recorded as a limitation
in ``docs/validation.md`` rather than tested here.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from quantvolt.assets.storage import (
    StorageFactorModel,
    StorageModel,
    storage_intrinsic,
    storage_value,
)
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.numerics.bachelier import bachelier_price
from quantvolt.numerics.black76 import black76_price
from quantvolt.numerics.exotic import turnbull_wakeman
from quantvolt.numerics.monte_carlo import (
    asian_monte_carlo,
    build_covariance,
    simulate_correlated_forwards,
)
from quantvolt.numerics.spread_models import kirk, margrabe


def _assert_within_k_se(mc: float, closed: float, se: float, k: float) -> None:
    """Assert ``|mc - closed| <= k * se`` with an informative message (Property 93)."""
    assert abs(mc - closed) <= k * se, (
        f"|{mc} - {closed}| = {abs(mc - closed):.4f} > {k}*SE = {k * se:.4f}"
    )


def _spread_mc(
    forward1: float,
    forward2: float,
    strike: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    t: float,
    df: float,
    seed: int,
    path_count: int,
) -> tuple[float, float]:
    """Discounted spread-call MC premium and antithetic-pair-aware standard error.

    Correlated GBM forwards under Q (martingale drift ``-1/2 diag(C)``): one step of length
    ``T`` via ``build_covariance`` + ``simulate_correlated_forwards`` (Appendix A). Payoff
    ``max(F1_T - F2_T - K, 0)``. The SE uses the ``n/2`` antithetic pair means (the engine draws
    ``(+eps, -eps)`` pairs), matching ``assets/storage.py:_standard_error``.
    """
    cov = build_covariance(np.array([sigma1, sigma2]), np.array([[1.0, rho], [rho, 1.0]]), t)
    drift = -0.5 * np.diag(cov)
    z0 = np.log([forward1, forward2])
    paths = simulate_correlated_forwards(z0, drift, cov, steps=1, path_count=path_count, seed=seed)
    terminal = np.exp(paths[:, 1, :])
    discounted = df * np.maximum(terminal[:, 0] - terminal[:, 1] - strike, 0.0)
    pair_means = 0.5 * (discounted[0::2] + discounted[1::2])
    se = float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
    return float(discounted.mean()), se


# --- (a) Black-76 vanilla vs single-fixing Asian MC --------------------------------------
def test_black76_vanilla_vs_mc_single_fixing() -> None:
    forward, strike, sigma, t, df = 100.0, 100.0, 0.20, 1.0, 0.97
    seed, paths, k = 42, 200_000, 5.0
    mc, se = asian_monte_carlo(forward, strike, sigma, t, df, 1, "call", False, seed, paths)
    closed = black76_price("call", forward, strike, sigma, t, df)
    _assert_within_k_se(mc, closed, se, k)


# --- (b) Margrabe (exact) vs correlated-forwards MC at K=0 -------------------------------
def test_margrabe_vs_mc_zero_strike() -> None:
    f1, f2, s1, s2, rho, t, df = 45.0, 30.0, 0.50, 0.40, 0.30, 1.0, 0.97
    seed, paths, k = 12_345, 400_000, 5.0
    mc, se = _spread_mc(f1, f2, 0.0, s1, s2, rho, t, df, seed, paths)
    exact = margrabe(f1, f2, s1, s2, rho, t, df)
    _assert_within_k_se(mc, exact, se, k)


# --- (c) Kirk (approximation) vs the same MC at K!=0 -------------------------------------
@pytest.mark.parametrize("strike", [2.5, 5.0, 10.0])
def test_kirk_vs_mc_measures_bias(strike: float) -> None:
    """Kirk is an approximation; its bias vs the (unbiased) MC is bounded by a documented band.

    Empirically Kirk slightly over-prices this spread (~0.15% relative, ~1 SE) here. The allowed
    band is ``max(0.01*kirk, 4*SE)`` — 1% of the Kirk value (the documented Kirk-approximation
    allowance) or 4 standard errors of the MC, whichever is larger.
    """
    f1, f2, s1, s2, rho, t, df = 45.0, 30.0, 0.50, 0.40, 0.30, 1.0, 0.97
    seed, paths = 12_345, 400_000
    mc, se = _spread_mc(f1, f2, strike, s1, s2, rho, t, df, seed, paths)
    approx = kirk(f1, f2, strike, s1, s2, rho, t, df)
    bias = approx - mc
    allowance = max(0.01 * approx, 4.0 * se)
    assert abs(bias) <= allowance, (
        f"Kirk bias {bias:+.5f} exceeds documented allowance {allowance:.5f} "
        f"(4*SE={4 * se:.5f}, 1%*kirk={0.01 * approx:.5f})"
    )


# --- (d) Turnbull-Wakeman vs arithmetic-Asian MC ----------------------------------------
def test_turnbull_wakeman_vs_arithmetic_mc() -> None:
    """TW (continuous arithmetic average, moment-matched) vs discrete arithmetic-Asian MC.

    No closed reference exists for the discrete arithmetic average, so this is a looser band:
    the MC uses 252 daily fixings to approximate TW's continuous average, and ``k = 5`` absorbs
    both the residual discrete-vs-continuous discretisation and the Monte Carlo error.
    """
    forward, strike, sigma, t, df = 100.0, 100.0, 0.30, 1.0, 0.97
    seed, paths, fixings, k = 777, 500_000, 252, 5.0
    mc, se = asian_monte_carlo(forward, strike, sigma, t, df, fixings, "call", False, seed, paths)
    closed = turnbull_wakeman(forward, strike, sigma, t, df, "call")
    _assert_within_k_se(mc, closed, se, k)


# --- (e) MC put-call parity -------------------------------------------------------------
def test_mc_put_call_parity() -> None:
    forward, strike, sigma, t, df = 100.0, 105.0, 0.25, 0.75, 0.96
    seed, paths, k = 2024, 300_000, 5.0
    call, se_call = asian_monte_carlo(forward, strike, sigma, t, df, 1, "call", False, seed, paths)
    put, se_put = asian_monte_carlo(forward, strike, sigma, t, df, 1, "put", False, seed, paths)
    parity = df * (forward - strike)
    residual = (call - put) - parity
    combined_se = se_call + se_put
    assert abs(residual) <= k * combined_se, (
        f"parity residual {residual:+.5f} > {k}*combinedSE={k * combined_se:.5f}"
    )


# --- (f) Storage extrinsic -> 0 as sigma -> 1e-4 ----------------------------------------
def _storage_curve() -> ForwardCurve:
    gas = CommodityConfig(
        commodity_id="TTF",
        price_unit="EUR/MWh",
        hub=Hub(hub_id="TTF", exchange="ICE", price_unit="EUR/MWh"),
    )
    prices = [20.0, 22.0, 25.0, 30.0, 28.0, 24.0]
    nodes = tuple(
        CurveNode(period=DeliveryPeriod(year=2026, month=i + 1), price=p, status="observed")
        for i, p in enumerate(prices)
    )
    return ForwardCurve(commodity=gas, market_date=date(2026, 1, 1), nodes=nodes)


def test_storage_extrinsic_vanishes_at_low_vol() -> None:
    model = StorageModel(
        min_inventory=0.0,
        max_inventory=4.0,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda inv: 2.0,
        withdrawal_rate=lambda inv: 2.0,
    )
    curve = _storage_curve()
    intrinsic = storage_intrinsic(model, curve, inventory_step=1.0)
    factor = StorageFactorModel(volatility=1e-4, dt=1.0 / 12.0, path_count=4000)
    value = storage_value(model, curve, factor, seed=123, inventory_step=1.0)
    # extrinsic must vanish: within a few SE, with a small absolute floor for the SE==0 case.
    tolerance = max(3.0 * value.standard_error, 1e-6)
    assert abs(value.extrinsic) <= tolerance, (
        f"extrinsic {value.extrinsic:.3e} should vanish (tol {tolerance:.3e})"
    )
    assert value.total == pytest.approx(intrinsic.value, abs=tolerance)


# --- (g) Bachelier vanilla vs exact-terminal normal MC ----------------------------------
def _bachelier_mc(
    option_type: str,
    forward: float,
    strike: float,
    normal_sigma: float,
    t: float,
    df: float,
    seed: int,
    path_count: int,
) -> tuple[float, float]:
    """Discounted Bachelier-payoff MC premium and standard error via exact terminal sampling.

    Arithmetic Brownian motion has an exact terminal law ``F_T = F0 + sigma_N sqrt(T) Z``,
    ``Z ~ N(0, 1)`` — so there is no time-discretisation bias, the MC error is pure sampling
    error. Antithetic pairs ``(+Z, -Z)`` reduce variance; the SE uses the ``n/2`` pair means
    (matching ``_spread_mc``/``assets/storage.py:_standard_error``).
    """
    rng = np.random.default_rng(seed)
    half = path_count // 2
    z = rng.standard_normal(half)
    z_full = np.concatenate([z, -z])
    terminal = forward + normal_sigma * math.sqrt(t) * z_full
    if option_type == "call":
        payoff = np.maximum(terminal - strike, 0.0)
    else:
        payoff = np.maximum(strike - terminal, 0.0)
    discounted = df * payoff
    pair_means = 0.5 * (discounted[:half] + discounted[half:])
    se = float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
    return float(discounted.mean()), se


@pytest.mark.parametrize(
    ("option_type", "forward", "strike"),
    [
        ("call", -25.0, -30.0),  # negative forward AND strike — the model's raison d'etre
        ("put", -5.0, 10.0),  # negative forward, positive strike
        ("call", 45.0, 50.0),  # ordinary positive energy case
    ],
)
def test_bachelier_vanilla_vs_exact_terminal_mc(
    option_type: str, forward: float, strike: float
) -> None:
    normal_sigma, t, df = 20.0, 1.0, 0.97
    seed, paths, k = 20200, 400_000, 5.0
    mc, se = _bachelier_mc(option_type, forward, strike, normal_sigma, t, df, seed, paths)
    closed = bachelier_price(option_type, forward, strike, normal_sigma, t, df)
    _assert_within_k_se(mc, closed, se, k)
