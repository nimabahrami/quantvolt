"""Unit tests for hedging/mean_variance.py (Task 70): local & global mean-variance hedging.

Validates Requirement 18.4 and Correctness Property 56. The kernels split the
hedging horizon into ``n`` rebalancing periods described by two increment
second-moment matrices: ``cov_hedge`` (``C[s, t] = Cov(ΔH_s, ΔH_t)``) and
``cov_target_hedge`` (``M[s, t] = Cov(ΔV_s, ΔH_t)``).

- ``local_mean_variance`` (default) is the per-period Föllmer-Sondermann
  projection ``diag(M)/diag(C)`` -- always exists given positive per-period hedge
  variance.
- ``global_mean_variance`` solves the total-horizon normal equations
  ``C·g = b`` with ``b = M.sum(axis=0)`` -- exists only when ``C`` is invertible.

Property 56 (linear-product triple identity) is checked directly against
``linear_cross_hedge`` (eq 10.22) from Task 69. A correlated-increments
counterexample demonstrates that ``local != global`` in general.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.hedging.mean_variance import global_mean_variance, local_mean_variance
from quantvolt.hedging.variance_min import linear_cross_hedge
from quantvolt.testing import assert_input_unchanged


def _linear_product_increment_moments(
    rho: float, sigma_p: float, sigma_g: float, dt: float, n: int
) -> tuple[np.ndarray, np.ndarray]:
    """Increment second moments for Example 10.2's linear two-asset product (eq 10.21).

    Target = F_P (``dF_P = sigma_P·dW_P``), hedge = F_G (``dF_G = sigma_G·dW_G``),
    ``dW_P·dW_G = rho·dt``. Over ``n`` equal periods the independent Brownian
    increments make both matrices diagonal:

        ``C = sigma_G²·Δt·I``   (Var(ΔH_t) = sigma_G²·Δt),
        ``M = rho·sigma_P·sigma_G·Δt·I``   (Cov(ΔV_t, ΔH_t) = rho·sigma_P·sigma_G·Δt;
    increments are independent across periods, so the off-diagonals are zero).
    """
    cov_hedge = (sigma_g**2 * dt) * np.eye(n)
    cov_target_hedge = (rho * sigma_p * sigma_g * dt) * np.eye(n)
    return cov_target_hedge, cov_hedge


class TestLocalMeanVariance:
    """Req 18.4: local one-step hedge diag(M)/diag(C); always exists (Föllmer-Sondermann)."""

    def test_hand_computed_uses_diagonals_only(self) -> None:
        # M = diag(0.6, 0.6); C has off-diagonal 0.5 that the local hedge ignores.
        # g_local_t = M[t,t] / C[t,t] = 0.6 / 1.0 = 0.6.
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        cov_hedge = np.array([[1.0, 0.5], [0.5, 1.0]])
        result = local_mean_variance(cov_target_hedge, cov_hedge)
        np.testing.assert_allclose(result, np.array([0.6, 0.6]))

    def test_off_diagonal_of_M_and_C_are_ignored(self) -> None:
        # Changing only off-diagonals must not change the local (per-period) hedge.
        base_m = np.array([[0.4, 0.0], [0.0, 0.9]])
        base_c = np.array([[2.0, 0.0], [0.0, 3.0]])
        expected = np.array([0.4 / 2.0, 0.9 / 3.0])
        np.testing.assert_allclose(local_mean_variance(base_m, base_c), expected)

        perturbed_m = np.array([[0.4, 0.7], [-0.3, 0.9]])  # off-diagonals now nonzero
        perturbed_c = np.array([[2.0, 1.1], [1.1, 3.0]])
        np.testing.assert_allclose(local_mean_variance(perturbed_m, perturbed_c), expected)

    def test_exists_where_global_system_is_singular(self) -> None:
        # C = [[1, 1], [1, 1]] is singular (perfectly collinear increments), so the
        # global system has no solution -- but the local hedge only needs the
        # diagonals and is well defined.
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        singular_cov_hedge = np.array([[1.0, 1.0], [1.0, 1.0]])
        result = local_mean_variance(cov_target_hedge, singular_cov_hedge)
        np.testing.assert_allclose(result, np.array([0.6, 0.6]))
        # Confirm the same C genuinely defeats the global optimiser.
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            global_mean_variance(cov_target_hedge, singular_cov_hedge)

    def test_single_period_matches_scalar_projection(self) -> None:
        result = local_mean_variance(np.array([[0.048]]), np.array([[0.04]]))
        assert result.shape == (1,)
        assert result[0] == pytest.approx(1.2)

    def test_returns_float64_ndarray(self) -> None:
        result = local_mean_variance(np.eye(3) * 0.6, np.eye(3) * 2.0)
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float64
        assert result.shape == (3,)

    def test_non_positive_hedge_variance_raises_naming_period(self) -> None:
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        zero_variance_c = np.array([[1.0, 0.0], [0.0, 0.0]])  # Var(ΔH_1) = 0
        with pytest.raises(ValidationError, match="per-period hedge variance"):
            local_mean_variance(cov_target_hedge, zero_variance_c)
        negative_variance_c = np.array([[-1.0, 0.0], [0.0, 1.0]])  # Var(ΔH_0) < 0
        with pytest.raises(ValidationError, match="per-period hedge variance"):
            local_mean_variance(cov_target_hedge, negative_variance_c)

    def test_deterministic(self) -> None:
        m = np.array([[0.6, 0.1], [0.2, 0.5]])
        c = np.array([[1.0, 0.3], [0.3, 2.0]])
        assert np.array_equal(local_mean_variance(m, c), local_mean_variance(m, c))

    def test_input_unchanged(self) -> None:
        m = np.array([[0.6, 0.1], [0.2, 0.5]])
        c = np.array([[1.0, 0.3], [0.3, 2.0]])
        result = assert_input_unchanged(local_mean_variance, m, c)
        np.testing.assert_allclose(result, np.array([0.6, 0.25]))


class TestGlobalMeanVariance:
    """Req 18.4: global total-horizon hedge C·g = b (b = column sums of M)."""

    def test_hand_computed_2x2(self) -> None:
        # C = [[1, 0.5], [0.5, 1]], M = diag(0.6, 0.6) => b = column sums = [0.6, 0.6].
        # C⁻¹ = (1/0.75)·[[1, -0.5], [-0.5, 1]], so g = C⁻¹·b = (1/0.75)·[0.3, 0.3] = [0.4, 0.4].
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        cov_hedge = np.array([[1.0, 0.5], [0.5, 1.0]])
        result = global_mean_variance(cov_target_hedge, cov_hedge)
        np.testing.assert_allclose(result, np.array([0.4, 0.4]))
        # Cross-check: the solve reproduces the right-hand side b = M.sum(axis=0).
        np.testing.assert_allclose(cov_hedge @ result, cov_target_hedge.sum(axis=0))

    def test_uses_column_sums_of_M_as_rhs(self) -> None:
        # C = I so g = b = column sums of M; this fixes the b = Cov(ΔH_t, ΔV_total)
        # convention (sum over the target-period index, axis=0).
        cov_target_hedge = np.array([[0.5, 0.2], [0.1, 0.7]])
        result = global_mean_variance(cov_target_hedge, np.eye(2))
        np.testing.assert_allclose(result, np.array([0.5 + 0.1, 0.2 + 0.7]))

    def test_singular_cov_hedge_raises_naming_condition(self) -> None:
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        singular_cov_hedge = np.array([[1.0, 1.0], [1.0, 1.0]])
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            global_mean_variance(cov_target_hedge, singular_cov_hedge)

    def test_returns_float64_ndarray(self) -> None:
        result = global_mean_variance(np.eye(3) * 0.6, np.eye(3) * 2.0)
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float64
        assert result.shape == (3,)

    def test_deterministic(self) -> None:
        m = np.array([[0.6, 0.1], [0.2, 0.5]])
        c = np.array([[1.0, 0.3], [0.3, 2.0]])
        assert np.array_equal(global_mean_variance(m, c), global_mean_variance(m, c))

    def test_input_unchanged(self) -> None:
        m = np.array([[0.6, 0.0], [0.0, 0.6]])
        c = np.array([[1.0, 0.5], [0.5, 1.0]])
        result = assert_input_unchanged(global_mean_variance, m, c)
        np.testing.assert_allclose(result, np.array([0.4, 0.4]))


class TestLocalVsGlobalCoincidence:
    """Property 56: when local == global, and the linear-product triple identity."""

    def test_property_56_linear_product_triple_identity(self) -> None:
        """Linear product => local == global == rho·sigma_P/sigma_G (eq 10.22)."""
        rho, sigma_p, sigma_g, dt, n = 0.8, 0.3, 0.2, 1.0 / 12.0, 3
        cov_target_hedge, cov_hedge = _linear_product_increment_moments(
            rho, sigma_p, sigma_g, dt, n
        )

        local = local_mean_variance(cov_target_hedge, cov_hedge)
        glob = global_mean_variance(cov_target_hedge, cov_hedge)
        expected = linear_cross_hedge(rho=rho, sigma_target=sigma_p, sigma_hedge=sigma_g)

        assert expected == pytest.approx(1.2)
        # Triple equality, every period: local == global == rho·sigma_P/sigma_G.
        np.testing.assert_allclose(local, np.full(n, expected))
        np.testing.assert_allclose(glob, np.full(n, expected))
        np.testing.assert_allclose(local, glob)

    def test_property_56_holds_for_various_linear_parameters(self) -> None:
        for rho, sigma_p, sigma_g in [(-0.5, 0.4, 0.2), (0.35, 0.25, 0.25), (0.9, 0.5, 0.8)]:
            m, c = _linear_product_increment_moments(rho, sigma_p, sigma_g, dt=0.25, n=4)
            expected = linear_cross_hedge(rho=rho, sigma_target=sigma_p, sigma_hedge=sigma_g)
            np.testing.assert_allclose(local_mean_variance(m, c), np.full(4, expected))
            np.testing.assert_allclose(global_mean_variance(m, c), np.full(4, expected))

    def test_coincide_under_independent_increments_non_identical_periods(self) -> None:
        # Independent increments => both M and C diagonal (but periods need not be
        # identical). local == global elementwise.
        cov_target_hedge = np.diag([0.6, 0.4, 0.9])
        cov_hedge = np.diag([2.0, 1.0, 3.0])
        local = local_mean_variance(cov_target_hedge, cov_hedge)
        glob = global_mean_variance(cov_target_hedge, cov_hedge)
        np.testing.assert_allclose(local, glob)
        np.testing.assert_allclose(local, np.array([0.3, 0.4, 0.3]))


class TestLocalVsGlobalDivergence:
    """Property 56 (contrapositive): with correlated increments, local != global."""

    def test_correlated_hedge_increments_diverge(self) -> None:
        # C off-diagonal (serially correlated hedge increments), M diagonal.
        # local = diag(M)/diag(C) = [0.6, 0.6];
        # global: b = [0.6, 0.6], g = C⁻¹·b = [0.4, 0.4].  They differ.
        cov_target_hedge = np.array([[0.6, 0.0], [0.0, 0.6]])
        cov_hedge = np.array([[1.0, 0.5], [0.5, 1.0]])
        local = local_mean_variance(cov_target_hedge, cov_hedge)
        glob = global_mean_variance(cov_target_hedge, cov_hedge)
        np.testing.assert_allclose(local, np.array([0.6, 0.6]))
        np.testing.assert_allclose(glob, np.array([0.4, 0.4]))
        assert not np.allclose(local, glob)
        # Positive autocorrelation shrinks the global positions vs the naive local hedge.
        assert np.all(np.abs(glob) < np.abs(local))

    def test_cross_period_target_hedge_covariance_diverges(self) -> None:
        # C diagonal, but M carries cross-period mass: M[0,1] = Cov(ΔV_0, ΔH_1) = 0.2.
        # local = [0.6, 0.6]; global: b = column sums = [0.6, 0.8], C = I => g = [0.6, 0.8].
        cov_target_hedge = np.array([[0.6, 0.2], [0.0, 0.6]])
        cov_hedge = np.eye(2)
        local = local_mean_variance(cov_target_hedge, cov_hedge)
        glob = global_mean_variance(cov_target_hedge, cov_hedge)
        np.testing.assert_allclose(local, np.array([0.6, 0.6]))
        np.testing.assert_allclose(glob, np.array([0.6, 0.8]))
        assert not np.allclose(local, glob)


class TestValidation:
    """Shared input validation via _validation.py; parameters named; no mutation."""

    def test_non_square_cov_hedge_raises(self) -> None:
        with pytest.raises(ValidationError, match="cov_hedge"):
            local_mean_variance(np.zeros((2, 3)), np.zeros((2, 3)))
        with pytest.raises(ValidationError, match="cov_hedge"):
            global_mean_variance(np.zeros((2, 3)), np.zeros((2, 3)))

    def test_empty_raises(self) -> None:
        with pytest.raises(ValidationError, match="non-empty"):
            local_mean_variance(np.zeros((0, 0)), np.zeros((0, 0)))
        with pytest.raises(ValidationError, match="non-empty"):
            global_mean_variance(np.zeros((0, 0)), np.zeros((0, 0)))

    def test_non_conformable_cov_target_hedge_raises(self) -> None:
        with pytest.raises(ValidationError, match="cov_target_hedge"):
            local_mean_variance(np.eye(3), np.eye(2))
        with pytest.raises(ValidationError, match="cov_target_hedge"):
            global_mean_variance(np.eye(3), np.eye(2))

    def test_non_finite_raises(self) -> None:
        good = np.eye(2)
        with pytest.raises(ValidationError, match="cov_hedge"):
            local_mean_variance(good, np.array([[1.0, 0.0], [0.0, np.inf]]))
        with pytest.raises(ValidationError, match="cov_target_hedge"):
            global_mean_variance(np.array([[np.nan, 0.0], [0.0, 1.0]]), good)

    def test_non_symmetric_cov_hedge_raises(self) -> None:
        asymmetric = np.array([[1.0, 0.3], [0.9, 1.0]])
        with pytest.raises(ValidationError, match="symmetric"):
            local_mean_variance(np.eye(2), asymmetric)
        with pytest.raises(ValidationError, match="symmetric"):
            global_mean_variance(np.eye(2), asymmetric)

    def test_cov_target_hedge_need_not_be_symmetric(self) -> None:
        # M is a cross-covariance between two different processes, so asymmetry is fine.
        asymmetric_m = np.array([[0.6, 0.2], [0.0, 0.6]])
        symmetric_c = np.eye(2)
        # Both kernels accept it without raising.
        local_mean_variance(asymmetric_m, symmetric_c)
        global_mean_variance(asymmetric_m, symmetric_c)


class TestConditionLimitParameter:
    """condition_limit (task: expose the hardcoded 1/eps ill-conditioning bound)."""

    def test_default_condition_limit_matches_previous_behaviour(self) -> None:
        cov_target_hedge = np.eye(2) * 0.5
        cov_hedge = np.diag([1.0, 1e-3])
        baseline = global_mean_variance(cov_target_hedge, cov_hedge)
        defaulted = global_mean_variance(
            cov_target_hedge, cov_hedge, condition_limit=1.0 / np.finfo(np.float64).eps
        )
        np.testing.assert_array_equal(defaulted, baseline)

    def test_tighter_condition_limit_rejects_a_matrix_the_default_accepts(self) -> None:
        cov_target_hedge = np.eye(2) * 0.5
        cov_hedge = np.diag([1.0, 1e-6])  # 2-norm condition number 1e6
        accepted = global_mean_variance(cov_target_hedge, cov_hedge)  # default limit ~4.5e15
        assert isinstance(accepted, np.ndarray)
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            global_mean_variance(cov_target_hedge, cov_hedge, condition_limit=1e5)

    def test_condition_limit_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="condition_limit"):
            global_mean_variance(np.eye(2), np.eye(2), condition_limit=0.0)
