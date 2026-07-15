"""Hedging & risk-adjustment correctness properties (design Properties 54-59; Task 77).

Covers the variance-minimizing hedge (Property 54), the incomplete-market decomposed delta
(Property 55), local/global mean-variance coincidence (Property 56), hybrid hedge-quality
monotonicity and chain-rule deltas (Property 57), the price-of-risk identities
(Property 58), and the physical-drift guard (Property 59).

These are deterministic algebraic identities, so every test runs the full 100-example
profile (``tests/conftest.py``) unless noted.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.hedging.hybrid import hybrid_deltas, residual_variance
from quantvolt.hedging.mean_variance import global_mean_variance, local_mean_variance
from quantvolt.hedging.variance_min import (
    decomposed_delta,
    linear_cross_hedge,
    variance_min_hedge,
)
from quantvolt.numerics.risk_adjustment import (
    DriftKind,
    PriceOfRiskKind,
    price_of_risk,
    require_physical_drift,
    risk_adjusted_drift,
    tradable_price_of_risk,
)
from strategies import spd_covariances

_FINITE = st.floats(min_value=-1_000.0, max_value=1_000.0, allow_nan=False, allow_infinity=False)
_VOLS = st.floats(min_value=0.05, max_value=2.0)
_CORR = st.floats(min_value=-0.99, max_value=0.99)


# ---------------------------------------------------------------------------------------
# Property 54: Variance-Minimizing Hedge Identity.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 54: Variance-Minimizing Hedge Identity
@given(sigma_hh=spd_covariances(min_dim=1, max_dim=5), data=st.data())
@settings(max_examples=100)
def test_property_54_hedge_solves_the_normal_equations(
    sigma_hh: npt.NDArray[np.float64], data: st.DataObject
) -> None:
    n = int(sigma_hh.shape[0])
    sigma_ht = np.array(data.draw(st.lists(_FINITE, min_size=n, max_size=n)), dtype=np.float64)
    hedge = variance_min_hedge(sigma_hh, sigma_ht)
    # Independent solve of Σ_hh·h* = Σ_ht (the module claims h* = Σ_hh⁻¹ Σ_ht).
    expected = np.linalg.solve(sigma_hh, sigma_ht)
    assert hedge == pytest.approx(expected, rel=1e-7, abs=1e-9)


# Feature: power-energy-quant-analysis, Property 54: Variance-Minimizing Hedge Identity
# The one-hedge-instrument (two-asset) case collapses to rho·sigma_target/sigma_hedge.
@given(rho=_CORR, sigma_target=_VOLS, sigma_hedge=_VOLS)
@settings(max_examples=100)
def test_property_54_two_asset_case_equals_rho_sigma_ratio(
    rho: float, sigma_target: float, sigma_hedge: float
) -> None:
    sigma_hh = np.array([[sigma_hedge**2]], dtype=np.float64)
    sigma_ht = np.array([rho * sigma_target * sigma_hedge], dtype=np.float64)
    expected = rho * sigma_target / sigma_hedge
    assert float(variance_min_hedge(sigma_hh, sigma_ht)[0]) == pytest.approx(expected, rel=1e-9)
    assert linear_cross_hedge(rho, sigma_target, sigma_hedge) == pytest.approx(expected, rel=1e-12)


# ---------------------------------------------------------------------------------------
# Property 55: Decomposed Hedge Differs From Complete-Market Delta.
# ---------------------------------------------------------------------------------------


def _quadratic_value(forward: float, basis: float) -> float:
    """A non-linear structure coupling F to the basis: Ṽ = 0.5·(F + basis)²."""
    return 0.5 * (forward + basis) ** 2


def _linear_value(forward: float, basis: float) -> float:
    """A linear structure with an additive basis: Ṽ = 3·F + basis."""
    return 3.0 * forward + basis


# Feature: power-energy-quant-analysis, Property 55: Decomposed Hedge Differs From
# Complete-Market Delta
# For the non-linear structure Ṽ = 0.5·(F + b)² the decomposed delta is ∂Ṽ/∂F = F + b,
# whereas the complete-market delta (zero basis) is F: the decomposed delta differs from the
# complete-market delta by *exactly the basis* — non-zero iff the basis is non-zero, so a
# zero basis is the only case in which they coincide.
@given(
    forward=st.floats(min_value=1.0, max_value=500.0),
    basis=st.one_of(st.just(0.0), st.floats(min_value=-50.0, max_value=50.0)),
)
@settings(max_examples=100)
def test_property_55_nonlinear_basis_shifts_the_delta(forward: float, basis: float) -> None:
    bump = 1e-2
    decomposed = decomposed_delta(
        _quadratic_value, forward, basis, bump, risk_adjustment=PriceOfRiskKind.CORPORATE
    )
    complete_market = decomposed_delta(
        _quadratic_value, forward, 0.0, bump, risk_adjustment=PriceOfRiskKind.CORPORATE
    )
    assert decomposed == pytest.approx(forward + basis, rel=1e-7, abs=1e-6)
    assert complete_market == pytest.approx(forward, rel=1e-7, abs=1e-6)
    # The incomplete-market delta differs from the complete-market delta by exactly the
    # basis (coincidence holds precisely when the basis is zero).
    assert (decomposed - complete_market) == pytest.approx(basis, rel=1e-6, abs=1e-6)
    if basis == 0.0:
        assert decomposed == complete_market


# Feature: power-energy-quant-analysis, Property 55: Decomposed Hedge Differs From
# Complete-Market Delta
# For a linear product the basis enters only additively, so it drops out of ∂Ṽ/∂F and the
# decomposed delta is invariant to the basis (they coincide even for a non-zero basis).
@given(
    forward=st.floats(min_value=1.0, max_value=500.0),
    basis=st.floats(min_value=-50.0, max_value=50.0),
)
@settings(max_examples=100)
def test_property_55_linear_product_delta_is_basis_invariant(forward: float, basis: float) -> None:
    bump = 1e-2
    with_basis = decomposed_delta(
        _linear_value, forward, basis, bump, risk_adjustment=PriceOfRiskKind.CORPORATE
    )
    zero_basis = decomposed_delta(
        _linear_value, forward, 0.0, bump, risk_adjustment=PriceOfRiskKind.CORPORATE
    )
    assert with_basis == pytest.approx(3.0, rel=1e-6, abs=1e-6)
    assert with_basis == pytest.approx(zero_basis, rel=1e-9, abs=1e-9)


# Feature: power-energy-quant-analysis, Property 55: Decomposed Hedge Differs From
# Complete-Market Delta
# The unhedgeable basis has no market price of risk, so only an explicit CORPORATE risk
# adjustment is accepted (Req 18.6); a MARKET-tagged one is rejected.
def test_property_55_market_risk_adjustment_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"CORPORATE|corporate"):
        decomposed_delta(_quadratic_value, 50.0, 5.0, 1e-2, risk_adjustment=PriceOfRiskKind.MARKET)


# ---------------------------------------------------------------------------------------
# Property 56: Local/Global Mean-Variance Coincidence.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 56: Local/Global Mean-Variance Coincidence
# For a linear product with constant correlation/vols, the disjoint Brownian increments make
# both C = sigma_G²·dt·I and M = rho·sigma_P·sigma_G·dt·I diagonal, so the local and global
# hedges coincide and equal rho·sigma_P/sigma_G every period.
@given(
    rho=_CORR,
    sigma_p=_VOLS,
    sigma_g=_VOLS,
    n=st.integers(min_value=1, max_value=8),
    dt=st.floats(min_value=1e-3, max_value=1.0),
)
@settings(max_examples=100)
def test_property_56_local_and_global_coincide_on_a_linear_product(
    rho: float, sigma_p: float, sigma_g: float, n: int, dt: float
) -> None:
    identity = np.eye(n)
    cov_hedge = sigma_g**2 * dt * identity  # C
    cov_target_hedge = rho * sigma_p * sigma_g * dt * identity  # M
    expected = rho * sigma_p / sigma_g

    local = local_mean_variance(cov_target_hedge, cov_hedge)
    global_ = global_mean_variance(cov_target_hedge, cov_hedge)
    assert local == pytest.approx(np.full(n, expected), rel=1e-9, abs=1e-12)
    assert global_ == pytest.approx(np.full(n, expected), rel=1e-9, abs=1e-12)
    assert local == pytest.approx(global_, rel=1e-9, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 56: Local/Global Mean-Variance Coincidence
# Cross-period correlation (off-diagonal mass in C) is exactly what makes the two hedges
# diverge — the contrapositive of the diagonal coincidence condition.
def test_property_56_off_diagonal_hedge_covariance_makes_them_diverge() -> None:
    cov_hedge = np.array([[1.0, 0.7], [0.7, 1.0]])  # serially correlated hedge increments
    cov_target_hedge = np.array([[0.5, 0.0], [0.0, 0.5]])  # diagonal M
    local = local_mean_variance(cov_target_hedge, cov_hedge)
    global_ = global_mean_variance(cov_target_hedge, cov_hedge)
    assert not np.allclose(local, global_)


# ---------------------------------------------------------------------------------------
# Property 57: Hybrid Hedge-Quality Monotonicity.
# ---------------------------------------------------------------------------------------


@st.composite
def _hybrid_cases(
    draw: st.DrawFn,
) -> tuple[dict[str, float], Mapping[str, Sequence[float]], list[float]]:
    """Weights, a per-driver series, and the exactly-explained realized price series."""
    names = draw(
        st.lists(st.sampled_from(("demand", "gas", "oil")), min_size=1, max_size=3, unique=True)
    )
    n_obs = draw(st.integers(min_value=2, max_value=8))
    weights = {name: draw(st.floats(min_value=-5.0, max_value=5.0)) for name in names}
    series = {
        name: draw(
            st.lists(
                st.floats(min_value=-20.0, max_value=20.0, allow_nan=False, allow_infinity=False),
                min_size=n_obs,
                max_size=n_obs,
            )
        )
        for name in names
    }
    realized = [sum(weights[name] * series[name][t] for name in names) for t in range(n_obs)]
    return weights, series, realized


# Feature: power-energy-quant-analysis, Property 57: Hybrid Hedge-Quality Monotonicity
# A representation that explains the realized price leaves a smaller residual variance and
# is the better hedge; a driver-blind (constant-mean) representation leaves the full
# realized variance.
@given(case=_hybrid_cases())
@settings(max_examples=100)
def test_property_57_smaller_residual_variance_is_the_better_representation(
    case: tuple[dict[str, float], Mapping[str, Sequence[float]], list[float]],
) -> None:
    weights, series, realized = case
    mean_realized = float(np.mean(realized))

    def good_stack(drivers: Mapping[str, float]) -> float:
        return sum(weights[name] * drivers[name] for name in weights)

    def blind_stack(_drivers: Mapping[str, float]) -> float:
        return mean_realized

    good = residual_variance(good_stack, series, realized)
    blind = residual_variance(blind_stack, series, realized)
    assert good == pytest.approx(0.0, abs=1e-9)  # exactly explained
    assert good <= blind + 1e-12
    if not np.allclose(realized, realized[0]):  # realized genuinely varies
        assert good < blind


# Feature: power-energy-quant-analysis, Property 57: Hybrid Hedge-Quality Monotonicity
# The chain-rule deltas equal the stack sensitivities and sum consistently: the first-order
# price move from bumping every driver equals the sum of delta·bump across drivers.
@given(case=_hybrid_cases())
@settings(max_examples=100)
def test_property_57_chain_rule_deltas_sum_consistently(
    case: tuple[dict[str, float], Mapping[str, Sequence[float]], list[float]],
) -> None:
    weights, series, _ = case
    point = {name: float(series[name][0]) for name in weights}

    def stack(drivers: Mapping[str, float]) -> float:
        return sum(weights[name] * drivers[name] for name in weights)

    deltas = hybrid_deltas(stack, point, bump=1e-2)
    assert set(deltas) == set(weights)
    for name, weight in weights.items():
        assert deltas[name] == pytest.approx(weight, rel=1e-6, abs=1e-6)

    # Sum consistency: dp = Σ_k (∂p/∂driver_k)·Δ(driver_k), exact for the linear stack.
    bumps = {name: 0.1 * (idx + 1) for idx, name in enumerate(weights)}
    perturbed = {name: point[name] + bumps[name] for name in weights}
    total_move = stack(perturbed) - stack(point)
    delta_sum = sum(deltas[name] * bumps[name] for name in weights)
    assert total_move == pytest.approx(delta_sum, rel=1e-6, abs=1e-6)


# ---------------------------------------------------------------------------------------
# Property 58: Price-of-Risk Identities.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 58: Price-of-Risk Identities
@given(
    mu=st.floats(min_value=-1.0, max_value=1.0),
    y=st.floats(min_value=-0.5, max_value=0.5),
    r=st.floats(min_value=-0.2, max_value=0.5),
    sigma=st.floats(min_value=0.01, max_value=2.0),
)
@settings(max_examples=100)
def test_property_58_tradable_risk_adjusted_drift_equals_r_minus_y(
    mu: float, y: float, r: float, sigma: float
) -> None:
    lambda_s = tradable_price_of_risk(mu, y, r, sigma)
    assert risk_adjusted_drift(mu, lambda_s, sigma) == pytest.approx(r - y, rel=1e-9, abs=1e-12)
    # The non-convenience-yield price of risk lambda = (mu - r)/sigma likewise gives drift r.
    lambda_m = price_of_risk(mu, r, sigma)
    assert risk_adjusted_drift(mu, lambda_m, sigma) == pytest.approx(r, rel=1e-9, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 58: Price-of-Risk Identities
@given(mu=st.floats(-1.0, 1.0), y=st.floats(-0.5, 0.5), r=st.floats(-0.2, 0.5))
@settings(max_examples=50)
def test_property_58_zero_volatility_is_rejected(mu: float, y: float, r: float) -> None:
    with pytest.raises(ValidationError, match="sigma"):
        tradable_price_of_risk(mu, y, r, 0.0)
    with pytest.raises(ValidationError, match="sigma"):
        risk_adjusted_drift(mu, 1.0, 0.0)


# ---------------------------------------------------------------------------------------
# Property 59: Physical-Drift Guard.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 59: Physical-Drift Guard
# ``require_physical_drift`` is the single guard the MC-VaR / CFaR / dispatch engines route
# their drift tag through: a RISK_NEUTRAL drift is rejected (naming the field), a PHYSICAL
# drift is accepted silently. (The MC-VaR wiring is exercised in Property 50.)
@given(field_name=st.sampled_from(("physical_drift", "drift", "mu")))
@settings(max_examples=50)
def test_property_59_risk_neutral_drift_triggers_the_guard(field_name: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        require_physical_drift(DriftKind.RISK_NEUTRAL, field_name)
    message = str(excinfo.value)
    assert field_name in message
    assert "physical" in message.lower()
    # A physical drift passes the guard silently (returns None).
    assert require_physical_drift(DriftKind.PHYSICAL, field_name) is None
