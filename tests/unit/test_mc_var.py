"""Unit tests for monte_carlo_var (Task 66, Req 15.1-15.5, Properties 50-51).

Covers, on a small linear two-futures book:

* delta-normal consistency (Property 50-style) — at a short horizon and large path
  count the full-revaluation MC VaR matches the analytic parametric (delta-normal) VaR,
  because the book is linear and ``sigma*sqrt(h)`` is small so the lognormal factor moves
  are near-Gaussian. The analytic value is computed independently in the test from the
  price-change covariance ``F0_a F0_b sigma_a sigma_b rho_ab h``;
* the required, measure-tagged ``physical_drift``: a ``RISK_NEUTRAL`` tag and a
  dimension mismatch are both rejected naming the field (Req 15.2);
* ``path_count = 999`` rejected *before* any simulation, proven by patching the engine
  entry points to fail if reached (Req 15.5);
* exact determinism under a fixed ``seed`` (Req 15.3 / Property 51);
* standard errors present, positive, and shrinking from 1000 to 8000 paths (Req 15.4 /
  Property 51);
* the GBM positivity limitation (non-positive current forward rejected);
* input immutability via ``quantvolt.testing.assert_input_unchanged`` (Req 11.4).
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.numerics.risk_adjustment import DriftKind
from quantvolt.portfolio.model import Position
from quantvolt.portfolio.valuation import MarketData
from quantvolt.risk import mc_var
from quantvolt.risk.mc_var import (
    FactorModel,
    McVaRResult,
    TaggedDrift,
    monte_carlo_var,
)
from quantvolt.testing import assert_input_unchanged

_COMMODITY = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
_COMMODITY_ID = "EEX_PHELIX_DE"
_VALUATION_DATE = date(2026, 1, 1)
_P_JUN = DeliveryPeriod(2026, 6)
_P_DEC = DeliveryPeriod(2026, 12)

# Current forwards, per-factor vols, and cross-factor correlation.
_F0 = np.array([100.0, 110.0])
_SIGMA = np.array([0.25, 0.20])
_CORR = np.array([[1.0, 0.6], [0.6, 1.0]])
# Discount factors at each settlement date (the last day of the delivery month).
_DF_JUN = 0.99
_DF_DEC = 0.98
# One-trading-day horizon: sigma*sqrt(h) is small, so the linear-book MC VaR is close to
# the Gaussian delta-normal VaR (documented consistency check).
_HOLDING_PERIOD = 1.0 / 252.0
_FACTORS = ((_COMMODITY_ID, _P_JUN), (_COMMODITY_ID, _P_DEC))


def _factor_model() -> FactorModel:
    curve = ForwardCurve(
        commodity=_COMMODITY,
        market_date=_VALUATION_DATE,
        nodes=(
            CurveNode(_P_JUN, float(_F0[0]), "observed"),
            CurveNode(_P_DEC, float(_F0[1]), "observed"),
        ),
    )
    discount = DiscountCurve(
        reference_date=_VALUATION_DATE,
        tenors=(_P_JUN.last_day, _P_DEC.last_day),
        factors=(_DF_JUN, _DF_DEC),
    )
    market_data = MarketData(
        forward_curves={_COMMODITY_ID: curve},
        discount_curve=discount,
        valuation_date=_VALUATION_DATE,
    )
    return FactorModel(
        market_data=market_data, factors=_FACTORS, sigma=_SIGMA.copy(), corr=_CORR.copy()
    )


def _positions() -> list[Position]:
    long_jun = FuturesContract(
        commodity=_COMMODITY, delivery_period=_P_JUN, contract_price=95.0, notional=10.0
    )
    long_dec = FuturesContract(
        commodity=_COMMODITY, delivery_period=_P_DEC, contract_price=100.0, notional=5.0
    )
    return [Position(instrument=long_jun), Position(instrument=long_dec)]


def _physical_drift() -> TaggedDrift:
    # Explicit zero physical drift (allowed; only *defaulting* to zero is forbidden).
    return TaggedDrift(values=np.zeros(2), kind=DriftKind.PHYSICAL)


def _analytic_delta_normal() -> tuple[float, float]:
    """Independent delta-normal VaR (95/99) for the linear two-futures book.

    Delta w.r.t. each forward price is ``discount_factor * notional``; the price-change
    covariance over the horizon is ``F0_a F0_b sigma_a sigma_b rho_ab h`` (first-order
    lognormal move). VaR = z * sqrt(delta^T Sigma delta), zero-mean.
    """
    delta = np.array([_DF_JUN * 10.0, _DF_DEC * 5.0])
    price_cov = np.array(
        [
            [
                _F0[a] * _F0[b] * _SIGMA[a] * _SIGMA[b] * _CORR[a, b] * _HOLDING_PERIOD
                for b in range(2)
            ]
            for a in range(2)
        ]
    )
    std = float(np.sqrt(delta @ price_cov @ delta))
    return 1.645 * std, 2.326 * std


# --- Property 50: delta-normal consistency (Req 15.1) -------------------------


def test_mc_var_matches_analytic_delta_normal_for_linear_book() -> None:
    analytic_95, analytic_99 = _analytic_delta_normal()
    result = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        path_count=8000,
        seed=20260714,
    )
    # Full-revaluation MC on a linear book with small sigma*sqrt(h) converges to the
    # Gaussian delta-normal VaR; agreement to ~5% (MC sampling + O(sigma^2 h) lognormal
    # drift bias) is the documented consistency criterion.
    assert result.var_95 == pytest.approx(analytic_95, rel=0.05)
    assert result.var_99 == pytest.approx(analytic_99, rel=0.05)
    assert result.cvar_975 >= result.var_95  # tail mean at/above the 95% quantile


# --- Req 15.2 / Property 50: physical_drift required and measure-tagged -------


def test_risk_neutral_drift_rejected_naming_the_field() -> None:
    risk_neutral = TaggedDrift(values=np.zeros(2), kind=DriftKind.RISK_NEUTRAL)
    with pytest.raises(ValidationError) as excinfo:
        monte_carlo_var(
            _positions(),
            _factor_model(),
            risk_neutral,
            _HOLDING_PERIOD,
            path_count=1000,
            seed=1,
        )
    message = str(excinfo.value)
    assert "physical_drift" in message
    assert "physical" in message


def test_drift_dimension_mismatch_rejected_naming_the_field() -> None:
    wrong_length = TaggedDrift(values=np.zeros(3), kind=DriftKind.PHYSICAL)
    with pytest.raises(ValidationError, match=r"physical_drift\.values must have shape"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            wrong_length,
            _HOLDING_PERIOD,
            path_count=1000,
            seed=1,
        )


# --- Req 15.5: path_count < 1000 raises BEFORE simulating ---------------------


def test_path_count_below_1000_raises_before_any_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_if_called(*args: object, **kwargs: object) -> object:
        raise AssertionError("simulation must not run when path_count < 1000")

    monkeypatch.setattr(mc_var, "simulate_correlated_forwards", _fail_if_called)
    monkeypatch.setattr(mc_var, "build_covariance", _fail_if_called)

    with pytest.raises(ValidationError, match="path_count must be >= 1000"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            path_count=999,
            seed=1,
        )


def test_holding_period_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="holding_period must be > 0"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            0.0,
            path_count=1000,
            seed=1,
        )


# --- Req 15.3 / Property 51: determinism under seed ---------------------------


def test_same_seed_gives_identical_result() -> None:
    first = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 1000, seed=99
    )
    second = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 1000, seed=99
    )
    assert first == second
    assert isinstance(first, McVaRResult)


def test_different_seeds_give_different_results() -> None:
    a = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 1000, seed=1
    )
    b = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 1000, seed=2
    )
    assert (a.var_95, a.var_99) != (b.var_95, b.var_99)


# --- Req 15.4 / Property 51: standard errors present, positive, shrinking -----


def test_standard_errors_present_positive_and_shrink_with_path_count() -> None:
    low = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 1000, seed=7
    )
    high = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 8000, seed=7
    )
    for result in (low, high):
        assert result.var_95_se > 0.0
        assert result.var_99_se > 0.0
        assert result.cvar_975_se > 0.0
    # More paths => smaller sampling error for every reported quantile.
    assert high.var_95_se < low.var_95_se
    assert high.var_99_se < low.var_99_se
    assert high.cvar_975_se < low.cvar_975_se


# --- GBM positivity limitation ------------------------------------------------


def test_non_positive_forward_rejected() -> None:
    curve = ForwardCurve(
        commodity=_COMMODITY,
        market_date=_VALUATION_DATE,
        nodes=(
            CurveNode(_P_JUN, -5.0, "observed"),  # negative power price: valid curve, bad for GBM
            CurveNode(_P_DEC, 110.0, "observed"),
        ),
    )
    discount = DiscountCurve(
        reference_date=_VALUATION_DATE,
        tenors=(_P_JUN.last_day, _P_DEC.last_day),
        factors=(_DF_JUN, _DF_DEC),
    )
    market_data = MarketData(
        forward_curves={_COMMODITY_ID: curve},
        discount_curve=discount,
        valuation_date=_VALUATION_DATE,
    )
    factor_model = FactorModel(
        market_data=market_data, factors=_FACTORS, sigma=_SIGMA.copy(), corr=_CORR.copy()
    )
    with pytest.raises(ValidationError, match="strictly positive"):
        monte_carlo_var(
            _positions(), factor_model, _physical_drift(), _HOLDING_PERIOD, 1000, seed=1
        )


# --- Req 11.4: input immutability ---------------------------------------------


def test_inputs_are_not_mutated() -> None:
    result = assert_input_unchanged(
        monte_carlo_var,
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        1000,
        seed=3,
    )
    assert result.var_95 > 0.0


# --- caller-configurable parameters (task: expose hardcoded values) -----------


def test_default_confidences_and_cvar_confidence_match_previous_behaviour() -> None:
    baseline = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 2000, seed=11
    )
    defaulted = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=11,
        confidences=(0.95, 0.99),
        cvar_confidence=0.975,
    )
    assert defaulted == baseline


def test_overriding_confidences_changes_reported_var() -> None:
    default_result = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 4000, seed=21
    )
    overridden = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        4000,
        seed=21,
        confidences=(0.50, 0.90),
        cvar_confidence=0.80,
    )
    assert overridden.var_95 != default_result.var_95
    assert overridden.var_99 != default_result.var_99
    assert overridden.cvar_975 != default_result.cvar_975
    # A lower confidence level must yield a smaller quantile of the same loss sample.
    assert overridden.var_95 < default_result.var_95


def test_confidences_must_have_exactly_two_levels() -> None:
    with pytest.raises(ValidationError, match="exactly 2 levels"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            1000,
            seed=1,
            confidences=(0.95,),
        )


def test_default_antithetic_and_bootstrap_replicates_match_previous_behaviour() -> None:
    baseline = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 2000, seed=5
    )
    defaulted = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=5,
        antithetic=False,
        bootstrap_replicates=500,
        min_path_count=1000,
    )
    assert defaulted == baseline


def test_enabling_antithetic_changes_simulated_paths() -> None:
    iid = monte_carlo_var(
        _positions(), _factor_model(), _physical_drift(), _HOLDING_PERIOD, 2000, seed=42
    )
    antithetic = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=42,
        antithetic=True,
    )
    assert (antithetic.var_95, antithetic.var_99) != (iid.var_95, iid.var_99)


def test_overriding_bootstrap_replicates_changes_standard_errors() -> None:
    few = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=8,
        bootstrap_replicates=10,
    )
    many = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=8,
        bootstrap_replicates=2000,
    )
    # Same underlying loss sample (identical seed/path_count) but a different bootstrap
    # replicate count must change the estimated standard errors.
    assert few.var_95_se != many.var_95_se
    assert few.var_95 == many.var_95  # the point estimates are unaffected


def test_bootstrap_replicates_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="bootstrap_replicates"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            1000,
            seed=1,
            bootstrap_replicates=0,
        )


def test_bootstrap_replicates_of_one_is_rejected() -> None:
    """FIX: bootstrap_replicates=1 used to pass require_positive and then silently
    produce a NaN SE from std(ddof=1) over a single replicate."""
    with pytest.raises(ValidationError, match="bootstrap_replicates"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            1000,
            seed=1,
            bootstrap_replicates=1,
        )


# --- FIX: antithetic bootstrap resamples whole (+eps, -eps) pairs, not individual --
# --- paths, so within-pair correlation no longer biases the reported SE -----------


def test_antithetic_bootstrap_pair_resampling_differs_from_naive_iid_resampling() -> None:
    """Construct losses with strong within-adjacent-pair anti-correlation (mimicking
    the simulator's (2k, 2k+1) antithetic pairing) and show the pair-aware bootstrap
    (antithetic=True) gives a different SE than naive iid resampling of the same
    array (antithetic=False) would."""
    rng = np.random.default_rng(2026)
    n_pairs = 500
    base = rng.standard_normal(n_pairs) * 100.0
    noise = rng.standard_normal(n_pairs) * 1.0  # small idiosyncratic wobble per pair
    plus = base + noise
    minus = -base + noise  # strongly anti-correlated with `plus` within each pair
    losses = np.empty(2 * n_pairs, dtype=np.float64)
    losses[0::2] = plus
    losses[1::2] = minus

    pair_se = mc_var._bootstrap_standard_errors(
        losses,
        seed=7,
        var_lo_pct=95.0,
        var_hi_pct=99.0,
        cvar_pct=97.5,
        bootstrap_replicates=500,
        antithetic=True,
    )
    iid_se = mc_var._bootstrap_standard_errors(
        losses,
        seed=7,
        var_lo_pct=95.0,
        var_hi_pct=99.0,
        cvar_pct=97.5,
        bootstrap_replicates=500,
        antithetic=False,
    )
    assert pair_se != iid_se


def test_default_antithetic_false_bootstrap_is_bit_identical_to_before_the_fix() -> None:
    """Regression: the antithetic=False (default) code path must be untouched by the
    pair-bootstrap fix — same iid-per-path resampling as before."""
    rng = np.random.default_rng(11)
    losses = rng.standard_normal(1000) * 50.0

    result = mc_var._bootstrap_standard_errors(
        losses,
        seed=3,
        var_lo_pct=95.0,
        var_hi_pct=99.0,
        cvar_pct=97.5,
        bootstrap_replicates=200,
        antithetic=False,
    )

    # Hand-reproduce the pre-fix iid bootstrap exactly (same RNG construction/order).
    n = losses.shape[0]
    bootstrap_rng = np.random.default_rng([3, mc_var._BOOTSTRAP_SALT])
    replicates = np.empty((200, 3), dtype=np.float64)
    for row in range(200):
        resample = losses[bootstrap_rng.integers(0, n, size=n)]
        replicates[row] = mc_var._loss_metrics(resample, 95.0, 99.0, 97.5)
    expected = tuple(float(v) for v in replicates.std(axis=0, ddof=1))

    assert result == expected


def test_enabling_antithetic_still_returns_positive_finite_standard_errors() -> None:
    """End-to-end: monte_carlo_var(antithetic=True) does not crash or NaN-out now
    that the bootstrap resamples pairs instead of individual (correlated) paths."""
    result = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        2000,
        seed=42,
        antithetic=True,
    )
    for se in (result.var_95_se, result.var_99_se, result.cvar_975_se):
        assert math.isfinite(se)
        assert se > 0.0


def test_swapped_confidences_are_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly ascending"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            1000,
            seed=1,
            confidences=(0.99, 0.95),
        )


def test_equal_confidences_are_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly ascending"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            1000,
            seed=1,
            confidences=(0.95, 0.95),
        )


def test_overriding_min_path_count_changes_the_rejection_threshold() -> None:
    with pytest.raises(ValidationError, match="path_count must be >= 500"):
        monte_carlo_var(
            _positions(),
            _factor_model(),
            _physical_drift(),
            _HOLDING_PERIOD,
            path_count=499,
            seed=1,
            min_path_count=500,
        )
    # A path_count that would have been rejected under the default floor now succeeds.
    result = monte_carlo_var(
        _positions(),
        _factor_model(),
        _physical_drift(),
        _HOLDING_PERIOD,
        path_count=500,
        seed=1,
        min_path_count=500,
    )
    assert isinstance(result, McVaRResult)
