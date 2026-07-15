"""Unit tests for risk/parametric_var.py (Task 65, Req 14.1/14.2/14.4/14.5, Properties 47-48).

Covers:
* the exact hand-computed 2-factor delta-VaR ``z_c·√(δᵀΣδ)``;
* the design's mandated z-constants ``z₀.₉₅ = 1.645`` and ``z₀.₉₉ = 2.326`` exactly, and
  arbitrary confidences falling back to ``scipy.stats.norm.ppf``;
* dimension / non-square / non-symmetric / non-PSD validation, each raising before any
  math and naming the offending quantity (Req 14.1, 14.4);
* the delta-gamma cumulant moments against an independent computation;
* the ``Γ = 0`` collapse of ``delta_gamma_var`` onto ``parametric_var`` (bit-exact,
  Property 48) and the long-gamma VaR-reduction sign check;
* the method dispatch (unknown method raises, listing the registered ones);
* the 2000-factor timing budget (Req 14.5, loose bound);
* determinism and input immutability.
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.risk.parametric_var import (
    ParametricVaRResult,
    delta_gamma_var,
    parametric_var,
)
from quantvolt.testing import assert_input_unchanged

_Z95 = 1.645
_Z99 = 2.326


class TestDeltaVaR:
    def test_hand_computed_two_factor(self) -> None:
        # Σδ = [5, 10]; δᵀΣδ = 15; VaR_c = z_c·√15.
        deltas = np.array([1.0, 1.0])
        cov = np.array([[4.0, 1.0], [1.0, 9.0]])
        result = parametric_var(deltas, cov)
        std = np.sqrt(15.0)
        assert result.confidences == (0.95, 0.99)
        np.testing.assert_allclose(result.var_values, (_Z95 * std, _Z99 * std), rtol=0, atol=1e-12)
        assert result.method == "delta"
        assert result.pnl_mean == 0.0
        assert result.pnl_skewness == 0.0
        np.testing.assert_allclose(result.pnl_variance, 15.0, atol=1e-12)
        assert result.n_factors == 2

    def test_unit_variance_yields_exact_design_constants(self) -> None:
        # δᵀΣδ = 1 ⇒ VaR_95 == 1.645 and VaR_99 == 2.326 exactly (the design constants).
        result = parametric_var(np.array([1.0]), np.array([[1.0]]))
        assert result.var_at(0.95) == _Z95
        assert result.var_at(0.99) == _Z99

    def test_arbitrary_confidence_uses_norm_ppf(self) -> None:
        from scipy.stats import norm  # type: ignore[import-untyped]

        deltas = np.array([2.0, 0.0, 1.0])
        cov = np.diag([1.0, 4.0, 9.0])
        std = np.sqrt(2.0**2 * 1.0 + 1.0**2 * 9.0)  # δᵀΣδ = 4 + 9 = 13
        result = parametric_var(deltas, cov, confidences=(0.975,))
        np.testing.assert_allclose(result.var_at(0.975), float(norm.ppf(0.975)) * std, rtol=1e-12)

    def test_var_at_missing_level_raises(self) -> None:
        result = parametric_var(np.array([1.0]), np.array([[1.0]]))
        with pytest.raises(ValidationError, match="was not computed"):
            result.var_at(0.90)

    def test_zero_deltas_give_zero_var(self) -> None:
        result = parametric_var(np.zeros(3), np.eye(3))
        assert result.var_values == (0.0, 0.0)


class TestDeltaVaRValidation:
    def test_dimension_mismatch_names_both(self) -> None:
        with pytest.raises(ValidationError, match=r"len\(deltas\)=2.*3x3"):
            parametric_var(np.array([1.0, 2.0]), np.eye(3))

    def test_non_square_cov_raises(self) -> None:
        with pytest.raises(ValidationError, match="must be square"):
            parametric_var(np.array([1.0, 2.0]), np.ones((2, 3)))

    def test_non_symmetric_cov_names_offending_entry(self) -> None:
        cov = np.array([[1.0, 0.5], [0.9, 1.0]])  # asymmetric at [0,1] vs [1,0]
        with pytest.raises(ValidationError, match=r"symmetric.*\[0,1\]|\[1,0\]"):
            parametric_var(np.array([1.0, 1.0]), cov)

    def test_non_psd_cov_raises_naming_eigenvalue(self) -> None:
        cov = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3, -1
        with pytest.raises(ValidationError, match=r"positive semidefinite.*smallest eigenvalue"):
            parametric_var(np.array([1.0, 1.0]), cov)

    def test_singular_psd_cov_is_accepted(self) -> None:
        # Rank-1 (singular but PSD) covariance must not be rejected.
        cov = np.array([[1.0, 1.0], [1.0, 1.0]])  # eigenvalues 2, 0
        result = parametric_var(np.array([1.0, 0.0]), cov)
        np.testing.assert_allclose(result.var_at(0.95), _Z95 * 1.0, rtol=1e-12)

    def test_bad_confidence_raises(self) -> None:
        for bad in (0.0, 1.0, 1.5, -0.1):
            with pytest.raises(ValidationError, match="open interval"):
                parametric_var(np.array([1.0]), np.array([[1.0]]), confidences=(bad,))

    def test_empty_confidences_raises(self) -> None:
        with pytest.raises(ValidationError, match="at least one level"):
            parametric_var(np.array([1.0]), np.array([[1.0]]), confidences=())

    def test_non_1d_deltas_raises(self) -> None:
        with pytest.raises(ValidationError, match="1-D"):
            parametric_var(np.array([[1.0], [2.0]]), np.eye(2))

    def test_non_finite_inputs_raise(self) -> None:
        with pytest.raises(ValidationError, match="finite"):
            parametric_var(np.array([np.nan, 1.0]), np.eye(2))
        with pytest.raises(ValidationError, match="finite"):
            parametric_var(np.array([1.0, 1.0]), np.array([[np.inf, 0.0], [0.0, 1.0]]))


class TestDeltaGammaVaR:
    def test_zero_gamma_collapses_to_delta_var_exactly(self) -> None:
        # Property 48: with Γ = 0 the delta-gamma VaR equals the delta VaR bit-for-bit.
        rng = np.random.default_rng(1)
        n = 6
        a = rng.standard_normal((n, n))
        cov = (a @ a.T) / n
        deltas = rng.standard_normal(n)
        gamma = np.zeros((n, n))
        linear = parametric_var(deltas, cov, confidences=(0.95, 0.99, 0.90))
        quadratic = delta_gamma_var(deltas, gamma, cov, confidences=(0.95, 0.99, 0.90))
        assert quadratic.var_values == linear.var_values
        assert quadratic.pnl_mean == 0.0
        assert quadratic.pnl_skewness == 0.0

    def test_reported_moments_match_independent_cumulants(self) -> None:
        cov = np.array([[4.0, 0.6], [0.6, 1.0]])
        deltas = np.array([1.5, -0.8])
        gamma = np.array([[0.5, 0.2], [0.2, 0.3]])
        theta = gamma @ cov
        k1 = 0.5 * np.trace(theta)
        k2 = deltas @ cov @ deltas + 0.5 * np.trace(theta @ theta)
        k3 = 3.0 * (deltas @ cov @ gamma @ cov @ deltas) + np.trace(theta @ theta @ theta)
        result = delta_gamma_var(deltas, gamma, cov)
        np.testing.assert_allclose(result.pnl_mean, k1, rtol=1e-12)
        np.testing.assert_allclose(result.pnl_variance, k2, rtol=1e-12)
        np.testing.assert_allclose(result.pnl_skewness, k3 / k2**1.5, rtol=1e-12)
        assert result.method == "cornish_fisher"

    def test_var_matches_explicit_cornish_fisher(self) -> None:
        cov = np.array([[4.0, 0.6], [0.6, 1.0]])
        deltas = np.array([1.5, -0.8])
        gamma = np.array([[0.5, 0.2], [0.2, 0.3]])
        result = delta_gamma_var(deltas, gamma, cov, confidences=(0.95,))
        mean, variance, skewness = result.pnl_mean, result.pnl_variance, result.pnl_skewness
        std = np.sqrt(variance)
        loss_skew = -skewness
        w = _Z95 + (_Z95**2 - 1.0) / 6.0 * loss_skew
        expected = -mean + std * w
        np.testing.assert_allclose(result.var_at(0.95), expected, rtol=1e-12)

    def test_long_gamma_reduces_var(self) -> None:
        # Long gamma (Γ positive definite): the quadratic term only ever adds to P&L, so
        # the loss tail thins — delta-gamma VaR is below the delta-only VaR at every level.
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.array([[2.0, 0.0], [0.0, 2.0]])
        linear = parametric_var(deltas, cov)
        quadratic = delta_gamma_var(deltas, gamma, cov)
        assert quadratic.pnl_mean > 0.0
        assert quadratic.pnl_skewness > 0.0
        for confidence in (0.95, 0.99):
            assert quadratic.var_at(confidence) < linear.var_at(confidence)

    def test_gamma_need_not_be_psd(self) -> None:
        # An indefinite Γ (short some gammas) is accepted; only Σ must be PSD.
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.array([[1.0, 0.0], [0.0, -3.0]])  # eigenvalues 1, -3 (indefinite)
        result = delta_gamma_var(deltas, gamma, cov)
        assert isinstance(result, ParametricVaRResult)

    def test_gamma_non_symmetric_raises(self) -> None:
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.array([[1.0, 0.2], [0.9, 1.0]])
        with pytest.raises(ValidationError, match="gamma must be symmetric"):
            delta_gamma_var(deltas, gamma, cov)

    def test_gamma_non_conformable_raises(self) -> None:
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.eye(3)
        with pytest.raises(ValidationError, match=r"len\(deltas\)=2.*gamma is 3x3"):
            delta_gamma_var(deltas, gamma, cov)

    def test_unknown_method_raises_listing_registered(self) -> None:
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.zeros((2, 2))
        with pytest.raises(ValidationError, match=r"unknown delta-gamma method.*cornish_fisher"):
            delta_gamma_var(deltas, gamma, cov, method="normal")


class TestPerformanceAndInvariants:
    def test_two_thousand_factors_completes_quickly(self) -> None:
        # Req 14.5's hard 2 s SLA is gated in tests/benchmarks (isolated, calibrated runs).
        # This unit test only guards against gross regressions; the slack bound (6 s) keeps
        # it robust under parallel-suite CPU contention where the strict bound proved flaky.
        rng = np.random.default_rng(20260715)
        n = 2000
        a = rng.standard_normal((n, n))
        cov = (a @ a.T) / n
        deltas = rng.standard_normal(n)
        start = time.perf_counter()
        result = parametric_var(deltas, cov)
        elapsed = time.perf_counter() - start
        assert result.n_factors == n
        assert elapsed < 6.0, f"parametric_var(2000 factors) took {elapsed:.3f}s (slack budget 6 s)"

    def test_determinism(self) -> None:
        deltas = np.array([1.5, -0.8, 0.3])
        cov = np.array([[4.0, 0.6, 0.0], [0.6, 1.0, 0.1], [0.0, 0.1, 2.0]])
        gamma = np.array([[0.5, 0.2, 0.0], [0.2, 0.3, 0.1], [0.0, 0.1, 0.4]])
        assert parametric_var(deltas, cov) == parametric_var(deltas, cov)
        assert delta_gamma_var(deltas, gamma, cov) == delta_gamma_var(deltas, gamma, cov)

    def test_inputs_not_mutated(self) -> None:
        deltas = np.array([1.5, -0.8])
        cov = np.array([[4.0, 0.6], [0.6, 1.0]])
        gamma = np.array([[0.5, 0.2], [0.2, 0.3]])
        assert_input_unchanged(parametric_var, deltas, cov)
        assert_input_unchanged(delta_gamma_var, deltas, gamma, cov)


class TestPsdTolAndSymmetryRtolParameters:
    """psd_tol / symmetry_rtol (task: expose the hardcoded PSD/symmetry tolerances)."""

    def test_default_psd_tol_and_symmetry_rtol_match_previous_behaviour(self) -> None:
        deltas = np.array([1.0, 1.0])
        cov = np.array([[4.0, 1.0], [1.0, 9.0]])
        baseline = parametric_var(deltas, cov)
        defaulted = parametric_var(deltas, cov, psd_tol=1e-8, symmetry_rtol=1e-8)
        assert defaulted == baseline

    def test_looser_psd_tol_accepts_a_matrix_the_default_rejects(self) -> None:
        # A rotated diag(1.0, -1e-6): eigenvalues exactly (1.0, -1e-6). The default
        # psd_tol=1e-8 rejects it (-1e-6 < -1e-8), but a looser psd_tol=1e-4 accepts
        # the same matrix, proving the override has an effect.
        deltas = np.array([1.0, 1.0])
        cov = np.array([[0.4999995, 0.5000005], [0.5000005, 0.4999995]])
        with pytest.raises(ValidationError, match="positive semidefinite"):
            parametric_var(deltas, cov)
        result = parametric_var(deltas, cov, psd_tol=1e-4)
        assert isinstance(result, ParametricVaRResult)

    def test_looser_symmetry_rtol_accepts_a_matrix_the_default_rejects(self) -> None:
        # Off-diagonal entries differ by 1e-4 relative to a unit-scale matrix: the
        # default symmetry_rtol=1e-8 rejects it, but a looser symmetry_rtol=1e-3
        # accepts the same matrix, proving the override has an effect.
        deltas = np.array([1.0, 1.0])
        cov = np.array([[1.0, 0.5], [0.5 + 1e-4, 1.0]])
        with pytest.raises(ValidationError, match="symmetric"):
            parametric_var(deltas, cov)
        result = parametric_var(deltas, cov, symmetry_rtol=1e-3)
        assert isinstance(result, ParametricVaRResult)

    def test_delta_gamma_var_psd_tol_and_symmetry_rtol_default_unchanged(self) -> None:
        deltas = np.array([1.5, -0.8])
        cov = np.array([[4.0, 0.6], [0.6, 1.0]])
        gamma = np.array([[0.5, 0.2], [0.2, 0.3]])
        baseline = delta_gamma_var(deltas, gamma, cov)
        defaulted = delta_gamma_var(deltas, gamma, cov, psd_tol=1e-8, symmetry_rtol=1e-8)
        assert defaulted == baseline

    def test_delta_gamma_var_looser_symmetry_rtol_accepts_asymmetric_gamma(self) -> None:
        deltas = np.array([1.0, 1.0])
        cov = np.eye(2)
        gamma = np.array([[1.0, 0.2], [0.2 + 1e-4, 1.0]])
        with pytest.raises(ValidationError, match="gamma must be symmetric"):
            delta_gamma_var(deltas, gamma, cov)
        result = delta_gamma_var(deltas, gamma, cov, symmetry_rtol=1e-3)
        assert isinstance(result, ParametricVaRResult)
