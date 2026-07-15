"""VaR-family correctness properties (design Properties 47-53; Task 77).

Covers the parametric delta / delta-gamma VaR (Properties 47-48), the EWMA / GARCH(1,1)
covariance estimators (Property 49), Monte-Carlo VaR determinism and the physical-drift
guard (Properties 50-51), CFaR (Property 52), and credit VaR (Property 53).

Each test is tagged with its design Property number. The deterministic-identity properties
(47, 48, 52) run the full 100-example profile (``tests/conftest.py``); the
simulation-heavy ones (49 GARCH MLE, 50/51 full-revaluation MC-VaR, 53 copula MC) use
reduced example counts and small workloads, as noted at each test, to keep total added
runtime modest.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import ForwardContract, FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.numerics.risk_adjustment import DriftKind
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.portfolio.valuation import MarketData
from quantvolt.risk.cfar import cash_flow_at_risk
from quantvolt.risk.covariance import _fit_garch11, ewma_covariance, garch11_covariance
from quantvolt.risk.credit_var import credit_var
from quantvolt.risk.mc_var import FactorModel, TaggedDrift, monte_carlo_var
from quantvolt.risk.parametric_var import delta_gamma_var, parametric_var
from strategies import deltas_and_covariance, return_matrices, symmetric_matrices

# House rounded z-scores (Req 14.1 / Property 47); reused as the independent oracle.
_Z95, _Z99 = 1.645, 2.326


# ---------------------------------------------------------------------------------------
# Property 47: Parametric Delta-VaR Formula and PSD Covariance.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 47: Parametric Delta-VaR Formula and PSD
# Covariance
@given(case=deltas_and_covariance(max_dim=6))
@settings(max_examples=100)
def test_property_47_delta_var_equals_z_times_root_quadratic_form(
    case: tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]],
) -> None:
    deltas, cov = case
    result = parametric_var(deltas, cov, confidences=(0.95, 0.99))
    # Independent oracle: z_c * sqrt(deltaᵀ Σ delta), with the mandated rounded z-scores.
    variance = float(deltas @ (cov @ deltas))
    std = math.sqrt(max(variance, 0.0))
    assert result.var_at(0.95) == pytest.approx(_Z95 * std, rel=1e-9, abs=1e-9)
    assert result.var_at(0.99) == pytest.approx(_Z99 * std, rel=1e-9, abs=1e-9)
    assert result.pnl_variance == pytest.approx(variance, rel=1e-9, abs=1e-12)
    assert result.pnl_mean == 0.0
    assert result.pnl_skewness == 0.0
    assert result.method == "delta"
    assert result.n_factors == deltas.size


# Feature: power-energy-quant-analysis, Property 47: Parametric Delta-VaR Formula and PSD
# Covariance
# A non-PSD covariance and a covariance whose dimension does not conform to the delta
# vector must both raise before any VaR arithmetic (Req 14.4).
@pytest.mark.parametrize(
    ("deltas", "cov", "match"),
    [
        # [[1, 2], [2, 1]] has eigenvalues 3 and -1 -> not PSD.
        (np.array([1.0, 1.0]), np.array([[1.0, 2.0], [2.0, 1.0]]), "positive semidefinite"),
        # 3x3 covariance does not conform to a length-2 delta vector.
        (np.array([1.0, 1.0]), np.eye(3), "do not match"),
    ],
)
def test_property_47_non_psd_or_non_conforming_covariance_raises(
    deltas: npt.NDArray[np.float64], cov: npt.NDArray[np.float64], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        parametric_var(deltas, cov)


# ---------------------------------------------------------------------------------------
# Property 48: Delta-Gamma-VaR Second-Order Consistency.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 48: Delta-Gamma-VaR Second-Order
# Consistency
@given(case=deltas_and_covariance(max_dim=5))
@settings(max_examples=100)
def test_property_48_zero_gamma_reduces_to_parametric_var(
    case: tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]],
) -> None:
    deltas, cov = case
    zero_gamma = np.zeros((deltas.size, deltas.size), dtype=np.float64)
    dg = delta_gamma_var(deltas, zero_gamma, cov, confidences=(0.95, 0.99))
    pv = parametric_var(deltas, cov, confidences=(0.95, 0.99))
    # The module documents a bit-for-bit collapse when Gamma = 0 (same association order).
    assert dg.var_values == pv.var_values
    assert dg.pnl_mean == 0.0
    assert dg.pnl_skewness == 0.0
    assert dg.pnl_variance == pytest.approx(pv.pnl_variance, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 48: Delta-Gamma-VaR Second-Order
# Consistency
# For Gamma != 0 the reported quantile must reflect the quadratic-form cumulants: mean,
# variance and skewness are recomputed here from an independent numpy transcription of
# the delta-gamma-normal cumulant formulas, then fed through the Cornish-Fisher map.
@given(case=deltas_and_covariance(max_dim=4), data=st.data())
@settings(max_examples=100)
def test_property_48_nonzero_gamma_reflects_the_second_order_term(
    case: tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]], data: st.DataObject
) -> None:
    deltas, cov = case
    gamma = data.draw(symmetric_matrices(int(deltas.size)))
    result = delta_gamma_var(deltas, gamma, cov, confidences=(0.95, 0.99))

    theta = gamma @ cov
    cov_delta = cov @ deltas
    kappa1 = 0.5 * float(np.trace(theta))
    kappa2 = max(float(deltas @ cov_delta) + 0.5 * float(np.trace(theta @ theta)), 0.0)
    kappa3 = 3.0 * float(cov_delta @ (gamma @ cov_delta)) + float(np.trace(theta @ theta @ theta))
    std = math.sqrt(kappa2)
    skew = kappa3 / kappa2**1.5 if kappa2 > 0.0 else 0.0

    assert result.pnl_mean == pytest.approx(kappa1, rel=1e-7, abs=1e-7)
    assert result.pnl_variance == pytest.approx(kappa2, rel=1e-7, abs=1e-7)
    assert result.pnl_skewness == pytest.approx(skew, rel=1e-7, abs=1e-7)
    for confidence, z in ((0.95, _Z95), (0.99, _Z99)):
        # Loss skewness is -skew; the third-order Cornish-Fisher map is w = z + (z²-1)/6·γ₁.
        w = z + (z * z - 1.0) / 6.0 * (-skew)
        assert result.var_at(confidence) == pytest.approx(-kappa1 + std * w, rel=1e-7, abs=1e-7)


# ---------------------------------------------------------------------------------------
# Property 49: Covariance-Estimator PSD and GARCH Stationarity.
# ---------------------------------------------------------------------------------------


def _is_symmetric_psd(matrix: npt.NDArray[np.float64], tol: float = 1e-8) -> bool:
    symmetric = np.allclose(matrix, matrix.T, atol=1e-10)
    min_eig = float(np.linalg.eigvalsh(0.5 * (matrix + matrix.T)).min())
    return symmetric and min_eig >= -tol


# Feature: power-energy-quant-analysis, Property 49: Covariance-Estimator PSD and GARCH
# Stationarity
@given(returns=return_matrices(min_obs=2, max_obs=30, max_assets=4))
@settings(max_examples=100)
def test_property_49_ewma_covariance_is_symmetric_psd(
    returns: npt.NDArray[np.float64],
) -> None:
    cov = ewma_covariance(returns)
    n_assets = returns.shape[1]
    assert cov.shape == (n_assets, n_assets)
    assert _is_symmetric_psd(cov)


def _simulate_garch(
    rng: np.random.Generator, n: int, omega: float, alpha: float, beta: float
) -> npt.NDArray[np.float64]:
    """One stationary GARCH(1,1) innovation series (unconditional-variance start)."""
    h = omega / (1.0 - alpha - beta)
    u = np.empty(n, dtype=np.float64)
    prev_u2 = h
    for t in range(n):
        h = omega + alpha * prev_u2 + beta * h
        u[t] = math.sqrt(h) * float(rng.standard_normal())
        prev_u2 = u[t] ** 2
    return u


# Feature: power-energy-quant-analysis, Property 49: Covariance-Estimator PSD and GARCH
# Stationarity
# GARCH is estimated by Gaussian MLE, so this uses a small, seeded set of stationary GARCH
# series (moderate persistence alpha+beta = 0.9) rather than a 100-example hypothesis run:
# the fit is expensive and pathological random returns would spuriously fail to converge.
# ``garch11_covariance`` raises unless the fit satisfies omega>0, alpha,beta>=0, alpha+beta<1,
# so a non-raising call already witnesses the stationarity constraint; the constraints are
# then also read back directly off the ``_fit_garch11`` kernel.
@pytest.mark.parametrize("seed", range(5))
def test_property_49_garch_covariance_symmetric_psd_and_stationary(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n_obs = 400
    returns = np.column_stack(
        [
            _simulate_garch(rng, n_obs, omega=0.10, alpha=0.10, beta=0.80) + 0.02,
            _simulate_garch(rng, n_obs, omega=0.05, alpha=0.08, beta=0.82) - 0.01,
        ]
    )
    cov = garch11_covariance(returns)  # raises if the stationarity constraint is violated
    assert cov.shape == (2, 2)
    assert _is_symmetric_psd(cov)

    demeaned = returns - returns.mean(axis=0)
    for j in range(2):
        omega, alpha, beta, _ = _fit_garch11(demeaned[:, j], j)
        assert omega > 0.0
        assert alpha >= 0.0
        assert beta >= 0.0
        assert alpha + beta < 1.0


# ---------------------------------------------------------------------------------------
# Properties 50-51: Monte Carlo VaR determinism, physical-drift guard, standard errors.
# ---------------------------------------------------------------------------------------

_MC_COMMODITY = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
_MC_COMMODITY_ID = "EEX_PHELIX_DE"
_MC_VALUATION_DATE = date(2026, 1, 1)
_MC_JUN = DeliveryPeriod(2026, 6)
_MC_DEC = DeliveryPeriod(2026, 12)
_MC_HORIZON = 1.0 / 252.0


def _mc_factor_model() -> FactorModel:
    curve = ForwardCurve(
        commodity=_MC_COMMODITY,
        market_date=_MC_VALUATION_DATE,
        nodes=(CurveNode(_MC_JUN, 100.0, "observed"), CurveNode(_MC_DEC, 110.0, "observed")),
    )
    discount = DiscountCurve(
        reference_date=_MC_VALUATION_DATE,
        tenors=(_MC_JUN.last_day, _MC_DEC.last_day),
        factors=(0.99, 0.98),
    )
    market_data = MarketData(
        forward_curves={_MC_COMMODITY_ID: curve},
        discount_curve=discount,
        valuation_date=_MC_VALUATION_DATE,
    )
    return FactorModel(
        market_data=market_data,
        factors=((_MC_COMMODITY_ID, _MC_JUN), (_MC_COMMODITY_ID, _MC_DEC)),
        sigma=np.array([0.25, 0.20]),
        corr=np.array([[1.0, 0.6], [0.6, 1.0]]),
    )


def _mc_positions() -> list[Position]:
    return [
        Position(
            instrument=FuturesContract(
                commodity=_MC_COMMODITY, delivery_period=_MC_JUN, contract_price=95.0, notional=10.0
            )
        ),
        Position(
            instrument=FuturesContract(
                commodity=_MC_COMMODITY, delivery_period=_MC_DEC, contract_price=100.0, notional=5.0
            )
        ),
    ]


# Feature: power-energy-quant-analysis, Property 50: Monte Carlo VaR Determinism and
# Physical Drift
# Reduced examples: each call fully revalues the book over 1000 paths. Determinism is a
# structural per-seed guarantee, so a handful of seeds suffices.
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=6, deadline=None)
def test_property_50_mc_var_reproducible_under_seed(seed: int) -> None:
    positions, factor_model = _mc_positions(), _mc_factor_model()
    drift = TaggedDrift(values=np.zeros(2), kind=DriftKind.PHYSICAL)
    first = monte_carlo_var(positions, factor_model, drift, _MC_HORIZON, path_count=1000, seed=seed)
    second = monte_carlo_var(
        positions, factor_model, drift, _MC_HORIZON, path_count=1000, seed=seed
    )
    assert first == second


# Feature: power-energy-quant-analysis, Property 50: Monte Carlo VaR Determinism and
# Physical Drift
def test_property_50_risk_neutral_drift_is_rejected() -> None:
    positions, factor_model = _mc_positions(), _mc_factor_model()
    risk_neutral = TaggedDrift(values=np.zeros(2), kind=DriftKind.RISK_NEUTRAL)
    with pytest.raises(ValidationError, match="physical"):
        monte_carlo_var(positions, factor_model, risk_neutral, _MC_HORIZON, path_count=1000, seed=1)


# Feature: power-energy-quant-analysis, Property 51: MC VaR Standard Error Reported
# Single expensive example (mirrors the unit test): each reported quantile carries a
# positive bootstrap standard error that shrinks as path_count grows (SE ~ 1/sqrt(n)).
def test_property_51_standard_errors_present_and_shrink_with_path_count() -> None:
    positions, factor_model = _mc_positions(), _mc_factor_model()
    drift = TaggedDrift(values=np.zeros(2), kind=DriftKind.PHYSICAL)
    small = monte_carlo_var(positions, factor_model, drift, _MC_HORIZON, path_count=1000, seed=7)
    large = monte_carlo_var(positions, factor_model, drift, _MC_HORIZON, path_count=8000, seed=7)
    for se in (small.var_95_se, small.var_99_se, small.cvar_975_se):
        assert se > 0.0
    assert large.var_95_se < small.var_95_se
    assert large.var_99_se < small.var_99_se


# ---------------------------------------------------------------------------------------
# Property 52: CFaR Horizon Consistency and Determinism.
# ---------------------------------------------------------------------------------------


def _cashflow_model(horizon: int) -> object:
    """A pure per-period cash-flow model of length ``horizon`` reading one scenario."""

    def model(scenario: Mapping[str, float]) -> npt.NDArray[np.float64]:
        base = scenario.get("margin", 0.0)
        return np.array([base * (t + 1) for t in range(horizon)], dtype=np.float64)

    return model


@st.composite
def _scenario_cases(
    draw: st.DrawFn,
) -> tuple[Sequence[Mapping[str, float]], int]:
    horizon = draw(st.integers(min_value=1, max_value=6))
    margins = draw(
        st.lists(
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
            min_size=1,
            max_size=20,
        )
    )
    scenarios = [{"margin": m} for m in margins]
    return scenarios, horizon


# Feature: power-energy-quant-analysis, Property 52: CFaR Horizon Consistency and
# Determinism
@given(case=_scenario_cases(), seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=100)
def test_property_52_cfar_deterministic_and_shortfall_identity(
    case: tuple[Sequence[Mapping[str, float]], int], seed: int
) -> None:
    scenarios, horizon = case
    model = _cashflow_model(horizon)
    first = cash_flow_at_risk(model, scenarios, horizon, seed)  # type: ignore[arg-type]
    second = cash_flow_at_risk(model, scenarios, horizon, seed)  # type: ignore[arg-type]
    assert first == second  # exhaustive scenario set -> structurally deterministic
    assert first.cfar_95 == pytest.approx(max(0.0, first.expected - first.p5), rel=1e-12, abs=1e-12)
    assert first.cfar_95 >= 0.0
    assert first.horizon == horizon
    assert first.seed == seed


# Feature: power-energy-quant-analysis, Property 52: CFaR Horizon Consistency and
# Determinism
@given(horizon=st.integers(min_value=1, max_value=6), bad_delta=st.sampled_from((-1, 1)))
@settings(max_examples=20)
def test_property_52_cashflow_vector_length_mismatch_raises(horizon: int, bad_delta: int) -> None:
    wrong_length = max(horizon + bad_delta, 0)

    def bad_model(_scenario: Mapping[str, float]) -> npt.NDArray[np.float64]:
        return np.zeros(wrong_length, dtype=np.float64)

    if wrong_length == horizon:  # degenerate draw (horizon 1, delta -1 -> 0 != 1): skip
        return
    with pytest.raises(ValidationError, match="horizon"):
        cash_flow_at_risk(bad_model, [{"margin": 1.0}], horizon, 0)


# ---------------------------------------------------------------------------------------
# Property 53: Credit VaR Probability Validation and Determinism.
# ---------------------------------------------------------------------------------------

_TTF = BUILT_IN_COMMODITIES["TTF"]
_CREDIT_PERIOD = DeliveryPeriod(2026, 1)


def _forward_position(counterparty: str, npv: float) -> PricedPosition:
    forward = ForwardContract(
        _TTF, _CREDIT_PERIOD, contract_price=30.0, notional=100.0, counterparty=counterparty
    )
    return PricedPosition(position=Position(forward), npv=npv)


def _riskfree_position(npv: float) -> PricedPosition:
    futures = FuturesContract(_TTF, _CREDIT_PERIOD, contract_price=30.0, notional=100.0)
    return PricedPosition(position=Position(futures), npv=npv)


# Feature: power-energy-quant-analysis, Property 53: Credit VaR Probability Validation and
# Determinism
# Reduced examples with a small path count: the copula MC is vectorised but re-running it
# per example is wasteful, and determinism is a structural per-seed guarantee.
@given(seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=10, deadline=None)
def test_property_53_reproducible_and_counterparty_less_flagged(seed: int) -> None:
    positions = [
        _forward_position("A", npv=1000.0),
        _forward_position("B", npv=500.0),
        _riskfree_position(npv=200.0),
    ]
    transition = {"A": [0.9, 0.1], "B": [0.95, 0.05]}
    first = credit_var(positions, transition, seed=seed, path_count=2000)
    second = credit_var(positions, transition, seed=seed, path_count=2000)
    assert first == second  # Req 17.3: reproducible under seed
    # The counterparty-less position is reported, not dropped (Req 17.2).
    assert len(first.credit_risk_free) == 1
    assert first.credit_risk_free[0] is positions[2]
    assert {d.counterparty for d in first.per_counterparty} == {"A", "B"}
    assert first.credit_var_99 >= first.credit_var_95 >= 0.0


# Feature: power-energy-quant-analysis, Property 53: Credit VaR Probability Validation and
# Determinism
# Rows must have probabilities in [0, 1] and sum to 1 within 1e-9 (Req 17.4); each
# violation raises before any simulation, naming the offending counterparty.
@pytest.mark.parametrize(
    ("transition", "match"),
    [
        ({"A": [0.8, 0.1]}, "sum to 1"),  # sums to 0.9
        ({"A": [1.2, -0.2]}, r"\[0, 1\]"),  # out-of-range probabilities
    ],
)
def test_property_53_invalid_transition_rows_raise(
    transition: Mapping[str, list[float]], match: str
) -> None:
    positions = [_forward_position("A", npv=1000.0)]
    with pytest.raises(ValidationError, match=match):
        credit_var(positions, transition, path_count=100)
