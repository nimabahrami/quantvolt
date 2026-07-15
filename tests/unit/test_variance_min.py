"""Unit tests for hedging/variance_min.py (Task 69): incomplete-market hedging.

Validates Requirements 18.1, 18.2, 18.3, 18.6 and Correctness Properties 54
(variance-minimizing hedge identity) and 55 (decomposed hedge differs from the
complete-market delta). The linear-product tests reproduce Example 10.2 of the
source chapter: the direct formula (eq 10.22) and the decomposition procedure
(eqs 10.23-10.25) yield the same hedge ``rho·sigma_P/sigma_G``.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.hedging.variance_min import (
    decomposed_delta,
    linear_cross_hedge,
    variance_min_hedge,
)
from quantvolt.numerics.risk_adjustment import PriceOfRiskKind
from quantvolt.testing import assert_input_unchanged


class TestVarianceMinHedge:
    """Req 18.1 / Property 54: h* = Σ_hh⁻¹ Σ_ht (raise if Σ_hh singular)."""

    def test_hand_computed_2x2_exact_solve(self) -> None:
        # Σ_hh = [[4, 1], [1, 2]], Σ_ht = [5, 3].  det = 7, and
        # Σ_hh @ [1, 1] = [5, 3] = Σ_ht, so the exact solution is [1, 1].
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        result = variance_min_hedge(sigma_hh, sigma_ht)
        np.testing.assert_allclose(result, np.array([1.0, 1.0]))
        # Cross-check: the solve reproduces the right-hand side exactly.
        np.testing.assert_allclose(sigma_hh @ result, sigma_ht)

    def test_reduces_to_linear_cross_hedge_1d(self) -> None:
        # Single instrument: Σ_hh = [[sigma_h²]], Σ_ht = [rho·sigma_t·sigma_h]
        #   =>  h* = rho·sigma_t/sigma_h.
        rho, sigma_t, sigma_h = 0.8, 0.3, 0.2
        sigma_hh = np.array([[sigma_h**2]])
        sigma_ht = np.array([rho * sigma_t * sigma_h])
        result = variance_min_hedge(sigma_hh, sigma_ht)
        assert result.shape == (1,)
        assert result[0] == pytest.approx(linear_cross_hedge(rho, sigma_t, sigma_h))
        assert result[0] == pytest.approx(1.2)

    def test_singular_matrix_raises_naming_condition(self) -> None:
        # Perfectly collinear instruments => singular Σ_hh; must raise (no silent pinv).
        sigma_hh = np.array([[1.0, 1.0], [1.0, 1.0]])
        sigma_ht = np.array([1.0, 1.0])
        with pytest.raises(ValidationError, match="sigma_hh"):
            variance_min_hedge(sigma_hh, sigma_ht)
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_ill_conditioned_matrix_raises(self) -> None:
        # Near-collinear: tiny off-diagonal perturbation keeps the condition number huge.
        sigma_hh = np.array([[1.0, 1.0], [1.0, 1.0 + 1e-16]])
        sigma_ht = np.array([1.0, 1.0])
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_non_square_raises_naming_square(self) -> None:
        sigma_hh = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        sigma_ht = np.array([1.0, 2.0])
        with pytest.raises(ValidationError, match="square"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_non_symmetric_raises_naming_symmetric(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [2.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        with pytest.raises(ValidationError, match="symmetric"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_nonconformable_sigma_ht_raises(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0, 1.0])  # length 3 vs 2x2
        with pytest.raises(ValidationError, match="conformable"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_sigma_ht_must_be_1d(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([[5.0], [3.0]])  # 2-D column, not a 1-D vector
        with pytest.raises(ValidationError, match="conformable"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_non_finite_raises(self) -> None:
        sigma_hh = np.array([[4.0, np.nan], [np.nan, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        with pytest.raises(ValidationError, match="finite"):
            variance_min_hedge(sigma_hh, sigma_ht)

    def test_returns_float64_ndarray(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        result = variance_min_hedge(sigma_hh, sigma_ht)
        assert isinstance(result, np.ndarray)
        assert result.dtype == np.float64
        assert result.shape == (2,)

    def test_deterministic(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        first = variance_min_hedge(sigma_hh, sigma_ht)
        second = variance_min_hedge(sigma_hh, sigma_ht)
        assert np.array_equal(first, second)

    def test_input_unchanged(self) -> None:
        sigma_hh = np.array([[4.0, 1.0], [1.0, 2.0]])
        sigma_ht = np.array([5.0, 3.0])
        result = assert_input_unchanged(variance_min_hedge, sigma_hh, sigma_ht)
        np.testing.assert_allclose(result, np.array([1.0, 1.0]))


class TestConditionLimitParameter:
    """condition_limit (task: expose the hardcoded 1/eps ill-conditioning bound)."""

    def test_default_condition_limit_matches_previous_behaviour(self) -> None:
        sigma_hh = np.diag([1.0, 1e-3])
        sigma_ht = np.array([1.0, 1.0])
        baseline = variance_min_hedge(sigma_hh, sigma_ht)
        defaulted = variance_min_hedge(
            sigma_hh, sigma_ht, condition_limit=1.0 / np.finfo(np.float64).eps
        )
        np.testing.assert_array_equal(defaulted, baseline)

    def test_tighter_condition_limit_rejects_a_matrix_the_default_accepts(self) -> None:
        sigma_hh = np.diag([1.0, 1e-6])  # 2-norm condition number 1e6
        sigma_ht = np.array([1.0, 1.0])
        accepted = variance_min_hedge(sigma_hh, sigma_ht)  # default limit ~4.5e15
        assert isinstance(accepted, np.ndarray)
        with pytest.raises(ValidationError, match="singular or ill-conditioned"):
            variance_min_hedge(sigma_hh, sigma_ht, condition_limit=1e5)

    def test_condition_limit_must_be_positive(self) -> None:
        with pytest.raises(ValidationError, match="condition_limit"):
            variance_min_hedge(np.eye(2), np.array([1.0, 1.0]), condition_limit=0.0)


class TestLinearCrossHedge:
    """Req 18.2 / eq 10.22: linear two-asset cross-commodity hedge rho·sigma_t/sigma_h."""

    def test_eq_10_22_hand_computed(self) -> None:
        # rho·sigma_t/sigma_h = 0.8 * 0.3 / 0.2 = 1.2.
        assert linear_cross_hedge(rho=0.8, sigma_target=0.3, sigma_hedge=0.2) == pytest.approx(1.2)

    def test_negative_correlation(self) -> None:
        assert linear_cross_hedge(rho=-0.5, sigma_target=0.4, sigma_hedge=0.2) == pytest.approx(
            -1.0
        )

    def test_equal_vols_gives_correlation(self) -> None:
        # With sigma_t == sigma_h the hedge ratio is just rho.
        assert linear_cross_hedge(rho=0.35, sigma_target=0.25, sigma_hedge=0.25) == pytest.approx(
            0.35
        )

    def test_reproduces_example_10_2(self) -> None:
        """Example 10.2: eq 10.25 (decomposition) == eq 10.22 (direct formula).

        The decomposition (eqs 10.23-10.24) writes the linear structure value as
        ``V(F_G) = rho·(sigma_P/sigma_G)·F_G + sigma_P·√(1-rho²)·E^RA[W̃]`` where the second term
        is an additive constant in F_G. Its variance-minimizing delta (eq 10.17)
        is therefore rho·sigma_P/sigma_G (eq 10.25), identical to eq 10.22.
        """
        rho, sigma_p, sigma_g = 0.8, 0.3, 0.2
        f_g = 50.0  # current hedge forward
        ra_basis = 2.5  # E^RA[W̃]: risk-adjusted basis expectation (a constant in F_G)

        direct = linear_cross_hedge(rho=rho, sigma_target=sigma_p, sigma_hedge=sigma_g)

        def linear_value(forward: float, basis_ra_expectation: float) -> float:
            # eq 10.24, ignoring discounting as in the source example.
            hedgeable = rho * (sigma_p / sigma_g) * forward
            unhedgeable = sigma_p * math.sqrt(1.0 - rho**2) * basis_ra_expectation
            return hedgeable + unhedgeable

        via_decomposition = decomposed_delta(
            linear_value,
            forward=f_g,
            basis_ra_expectation=ra_basis,
            bump=1e-4,
            risk_adjustment=PriceOfRiskKind.CORPORATE,
        )

        assert direct == pytest.approx(1.2)
        assert via_decomposition == pytest.approx(direct)

    def test_decomposition_independent_of_risk_adjusted_basis(self) -> None:
        # For a linear product the delta is invariant to the risk-adjusted basis term
        # (it is an additive constant in the forward): the indirect risk-adjustment
        # effect noted after eq 10.18 does not change the linear hedge coefficient.
        rho, sigma_p, sigma_g = 0.6, 0.5, 0.4

        def linear_value(forward: float, basis_ra_expectation: float) -> float:
            return rho * (sigma_p / sigma_g) * forward + 3.0 * basis_ra_expectation

        delta_a = decomposed_delta(
            linear_value, 20.0, 0.0, 1e-4, risk_adjustment=PriceOfRiskKind.CORPORATE
        )
        delta_b = decomposed_delta(
            linear_value, 20.0, 9.9, 1e-4, risk_adjustment=PriceOfRiskKind.CORPORATE
        )
        assert delta_a == pytest.approx(delta_b)
        assert delta_a == pytest.approx(linear_cross_hedge(rho, sigma_p, sigma_g))

    def test_rho_out_of_range_raises_naming_rho(self) -> None:
        for bad_rho in (1.0, -1.0, 1.5, -2.0):
            with pytest.raises(ValidationError, match="rho"):
                linear_cross_hedge(rho=bad_rho, sigma_target=0.3, sigma_hedge=0.2)

    def test_sigma_target_non_positive_raises_naming_sigma_target(self) -> None:
        with pytest.raises(ValidationError, match="sigma_target"):
            linear_cross_hedge(rho=0.5, sigma_target=0.0, sigma_hedge=0.2)
        with pytest.raises(ValidationError, match="sigma_target"):
            linear_cross_hedge(rho=0.5, sigma_target=-0.3, sigma_hedge=0.2)

    def test_sigma_hedge_non_positive_raises_naming_sigma_hedge(self) -> None:
        with pytest.raises(ValidationError, match="sigma_hedge"):
            linear_cross_hedge(rho=0.5, sigma_target=0.3, sigma_hedge=0.0)
        with pytest.raises(ValidationError, match="sigma_hedge"):
            linear_cross_hedge(rho=0.5, sigma_target=0.3, sigma_hedge=-0.2)

    def test_deterministic(self) -> None:
        first = linear_cross_hedge(0.8, 0.3, 0.2)
        second = linear_cross_hedge(0.8, 0.3, 0.2)
        assert first == second

    def test_input_unchanged(self) -> None:
        result = assert_input_unchanged(
            linear_cross_hedge, rho=0.8, sigma_target=0.3, sigma_hedge=0.2
        )
        assert result == pytest.approx(1.2)


class TestDecomposedDelta:
    """Req 18.3 / 18.6 / Property 55: ∂Ṽ/∂F via the risk-adjusted basis expectation."""

    def test_linear_value_equals_slope_exactly(self) -> None:
        # Ṽ(F) = 3·F + 7·b. Central difference of an exactly linear function is exact.
        def linear_value(forward: float, basis_ra_expectation: float) -> float:
            return 3.0 * forward + 7.0 * basis_ra_expectation

        delta = decomposed_delta(
            linear_value,
            forward=2.0,
            basis_ra_expectation=1.5,
            bump=0.5,
            risk_adjustment=PriceOfRiskKind.CORPORATE,
        )
        assert delta == 3.0

    def test_nonlinear_value_matches_analytic_derivative(self) -> None:
        # Ṽ(F) = exp(F) + b  =>  ∂Ṽ/∂F = exp(F). Central difference error is O(bump²).
        def nonlinear_value(forward: float, basis_ra_expectation: float) -> float:
            return math.exp(forward) + basis_ra_expectation

        forward = 1.0
        delta = decomposed_delta(
            nonlinear_value,
            forward=forward,
            basis_ra_expectation=4.0,
            bump=1e-5,
            risk_adjustment=PriceOfRiskKind.CORPORATE,
        )
        assert delta == pytest.approx(math.exp(forward), rel=1e-8)

    def test_property_55_differs_from_complete_market_delta(self) -> None:
        # Ṽ(F, b) = 0.5·F² + b·F couples the basis to F, so ∂Ṽ/∂F = F + b.
        # The complete-market delta uses a ZERO basis (eq 10.13): ∂V/∂F = F.
        def value(forward: float, basis_ra_expectation: float) -> float:
            return 0.5 * forward**2 + basis_ra_expectation * forward

        forward = 5.0
        basis_mean = 2.0
        decomposed = decomposed_delta(
            value, forward, basis_mean, 1e-5, risk_adjustment=PriceOfRiskKind.CORPORATE
        )
        complete_market = decomposed_delta(
            value, forward, 0.0, 1e-5, risk_adjustment=PriceOfRiskKind.CORPORATE
        )
        # eq 10.18: Δ̃_t ≠ Δ_t when the basis has a non-zero mean.
        assert decomposed == pytest.approx(forward + basis_mean)
        assert complete_market == pytest.approx(forward)
        assert decomposed != pytest.approx(complete_market)
        assert decomposed - complete_market == pytest.approx(basis_mean)

    def test_property_55_zero_basis_coincides(self) -> None:
        # With a zero basis, E^RA[Payoff] = Payoff, so Ṽ = V and Δ̃ = Δ (Property 55).
        def value(forward: float, basis_ra_expectation: float) -> float:
            return 0.5 * forward**2 + basis_ra_expectation * forward

        forward = 5.0
        decomposed = decomposed_delta(
            value, forward, 0.0, 1e-5, risk_adjustment=PriceOfRiskKind.CORPORATE
        )
        assert decomposed == pytest.approx(forward)

    def test_market_risk_adjustment_rejected(self) -> None:
        # Req 18.6: the unhedgeable basis requires an explicit CORPORATE adjustment;
        # a MARKET (risk-neutral) kind is rejected.
        def value(forward: float, basis_ra_expectation: float) -> float:
            return forward + basis_ra_expectation

        with pytest.raises(ValidationError, match="risk_adjustment"):
            decomposed_delta(value, 1.0, 0.0, 1e-4, risk_adjustment=PriceOfRiskKind.MARKET)
        with pytest.raises(ValidationError, match="corporate"):
            decomposed_delta(value, 1.0, 0.0, 1e-4, risk_adjustment=PriceOfRiskKind.MARKET)

    def test_corporate_risk_adjustment_accepted(self) -> None:
        def value(forward: float, basis_ra_expectation: float) -> float:
            return 2.0 * forward + basis_ra_expectation

        delta = decomposed_delta(value, 1.0, 0.0, 1e-4, risk_adjustment=PriceOfRiskKind.CORPORATE)
        assert delta == pytest.approx(2.0)

    def test_bump_non_positive_raises_naming_bump(self) -> None:
        def value(forward: float, basis_ra_expectation: float) -> float:
            return forward + basis_ra_expectation

        with pytest.raises(ValidationError, match="bump"):
            decomposed_delta(value, 1.0, 0.0, 0.0, risk_adjustment=PriceOfRiskKind.CORPORATE)
        with pytest.raises(ValidationError, match="bump"):
            decomposed_delta(value, 1.0, 0.0, -1e-4, risk_adjustment=PriceOfRiskKind.CORPORATE)

    def test_non_callable_value_fn_raises(self) -> None:
        with pytest.raises(ValidationError, match="value_fn"):
            decomposed_delta(
                "not callable",  # type: ignore[arg-type]
                1.0,
                0.0,
                1e-4,
                risk_adjustment=PriceOfRiskKind.CORPORATE,
            )

    def test_deterministic(self) -> None:
        def value(forward: float, basis_ra_expectation: float) -> float:
            return math.exp(forward) + basis_ra_expectation

        first = decomposed_delta(value, 1.0, 0.5, 1e-5, risk_adjustment=PriceOfRiskKind.CORPORATE)
        second = decomposed_delta(value, 1.0, 0.5, 1e-5, risk_adjustment=PriceOfRiskKind.CORPORATE)
        assert first == second

    def test_input_unchanged(self) -> None:
        def value(forward: float, basis_ra_expectation: float) -> float:
            return 3.0 * forward + 7.0 * basis_ra_expectation

        result = assert_input_unchanged(
            decomposed_delta,
            value,
            2.0,
            1.5,
            0.5,
            risk_adjustment=PriceOfRiskKind.CORPORATE,
        )
        assert result == 3.0
