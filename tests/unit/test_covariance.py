"""Unit tests for risk/covariance.py (Task 64, Req 14.3, Property 49).

Covers:
* EWMA against an exact hand-unrolled 2-asset, 3-step recursion;
* EWMA of i.i.d. samples approximating the true covariance (loose, fixed seed);
* the GARCH(1,1) stationarity guard raising on a constructed non-stationary series;
* the PSD + exact-symmetry invariants of both estimators on fixed-seed inputs;
* :func:`nearest_psd` repairing a small indefinite matrix; and
* the boundary validations (``lam`` range naming ``lam``; ``n_obs >= 2``).
"""

from __future__ import annotations

import numpy as np
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.risk.covariance import (
    ewma_covariance,
    garch11_covariance,
    nearest_psd,
)

_PSD_TOL = 1e-8


def _min_eigenvalue(matrix: np.ndarray) -> float:
    return float(np.linalg.eigvalsh((matrix + matrix.T) / 2.0)[0])


def _simulate_garch(omega: float, alpha: float, beta: float, n: int, seed: int) -> np.ndarray:
    """Simulate a single stationary GARCH(1,1) innovation series."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    h = np.empty(n)
    u = np.empty(n)
    h[0] = omega / (1.0 - alpha - beta)
    u[0] = np.sqrt(h[0]) * z[0]
    for t in range(1, n):
        h[t] = omega + alpha * u[t - 1] ** 2 + beta * h[t - 1]
        u[t] = np.sqrt(h[t]) * z[t]
    return u


class TestEwmaRecursion:
    def test_hand_unrolled_three_step(self) -> None:
        # Sigma_0 = r0 r0^T; then two convex updates. With lam=0.9:
        #   Sigma_2 = 0.9*(0.9*outer(r0)+0.1*outer(r1)) + 0.1*outer(r2)
        returns = np.array([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
        result = ewma_covariance(returns, lam=0.9)
        expected = np.array([[0.91, 0.10], [0.10, 0.19]])
        np.testing.assert_allclose(result, expected, atol=1e-12)

    def test_iid_samples_approximate_true_covariance(self) -> None:
        true_cov = np.array([[4.0, 1.0], [1.0, 2.0]])
        rng = np.random.default_rng(20260715)
        samples = rng.multivariate_normal([0.0, 0.0], true_cov, size=8000)
        # High decay (long effective window) + a loose tolerance: EWMA is genuinely noisy
        # (effective window ~ 1/(1-lam) ~ 100 obs), so this only checks scale/shape/sign.
        estimate = ewma_covariance(samples, lam=0.99)
        np.testing.assert_allclose(estimate, true_cov, rtol=0.30, atol=0.1)

    def test_shape_matches_asset_count(self) -> None:
        rng = np.random.default_rng(1)
        returns = rng.standard_normal((500, 4))
        assert ewma_covariance(returns).shape == (4, 4)

    def test_input_not_mutated(self) -> None:
        rng = np.random.default_rng(2)
        returns = rng.standard_normal((100, 3))
        before = returns.copy()
        ewma_covariance(returns)
        np.testing.assert_array_equal(returns, before)

    @pytest.mark.parametrize("seed", [0, 1, 2, 3])
    def test_psd_and_exact_symmetry(self, seed: int) -> None:
        rng = np.random.default_rng(seed)
        returns = rng.standard_normal((300, 5))
        cov = ewma_covariance(returns)
        np.testing.assert_array_equal(cov, cov.T)  # exact symmetry
        assert _min_eigenvalue(cov) >= -_PSD_TOL

    @pytest.mark.parametrize("lam", [0.0, 1.0, 1.5, -0.1])
    def test_lam_out_of_range_raises_naming_lam(self, lam: float) -> None:
        returns = np.array([[1.0, 0.0], [0.0, 1.0]])
        with pytest.raises(ValidationError, match="lam"):
            ewma_covariance(returns, lam=lam)

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ValidationError, match="observations"):
            ewma_covariance(np.array([[1.0, 2.0]]))

    def test_non_2d_raises(self) -> None:
        with pytest.raises(ValidationError, match="2-D"):
            ewma_covariance(np.array([1.0, 2.0, 3.0]))


class TestGarch11Covariance:
    def test_stationary_fit_is_psd_and_symmetric(self) -> None:
        # Two correlated assets, each a stationary GARCH(1,1): the fit must succeed and
        # return a symmetric PSD forecast.
        u0 = _simulate_garch(0.05, 0.10, 0.85, 2000, 10)
        u1 = _simulate_garch(0.05, 0.08, 0.88, 2000, 11)
        # Inject cross-correlation through a shared component.
        shared = _simulate_garch(0.05, 0.10, 0.85, 2000, 12)
        returns = np.column_stack([u0 + 0.5 * shared, u1 + 0.5 * shared])
        cov = garch11_covariance(returns)
        assert cov.shape == (2, 2)
        np.testing.assert_array_equal(cov, cov.T)
        assert _min_eigenvalue(cov) >= -_PSD_TOL
        assert cov[0, 1] > 0.0  # positive dependence via the shared component

    @pytest.mark.parametrize("seed", [20, 21, 22])
    def test_psd_property_on_simulated_inputs(self, seed: int) -> None:
        u0 = _simulate_garch(0.04, 0.09, 0.86, 1500, seed)
        u1 = _simulate_garch(0.06, 0.12, 0.80, 1500, seed + 100)
        returns = np.column_stack([u0, u1])
        cov = garch11_covariance(returns)
        np.testing.assert_array_equal(cov, cov.T)
        assert _min_eigenvalue(cov) >= -_PSD_TOL

    def test_stationarity_guard_raises_on_degenerate_input(self) -> None:
        # A structural break (near-zero variance regime followed by a high-variance regime)
        # is non-stationary in variance; the GARCH MLE drives alpha + beta >= 1, so the
        # stationarity guard must fire and name the constraint.
        rng = np.random.default_rng(3)
        low = rng.standard_normal(400) * 0.1
        high = rng.standard_normal(400) * 10.0
        degenerate = np.concatenate([low, high])
        returns = np.column_stack([degenerate, np.concatenate([high, low])])
        with pytest.raises(ValidationError, match="alpha \\+ beta < 1"):
            garch11_covariance(returns)

    def test_zero_variance_series_raises(self) -> None:
        returns = np.column_stack([np.zeros(200), np.random.default_rng(4).standard_normal(200)])
        with pytest.raises(ValidationError, match="zero variance"):
            garch11_covariance(returns)

    def test_too_few_observations_raises(self) -> None:
        with pytest.raises(ValidationError, match="observations"):
            garch11_covariance(np.array([[1.0, 2.0]]))


# --- psd_tol forwarding (task: expose the hardcoded PSD tolerance) ------------


class TestPsdTolParameter:
    def test_ewma_default_psd_tol_matches_previous_behaviour(self) -> None:
        rng = np.random.default_rng(2026)
        returns = rng.standard_normal((300, 4))
        baseline = ewma_covariance(returns)
        defaulted = ewma_covariance(returns, psd_tol=1e-8)
        np.testing.assert_array_equal(defaulted, baseline)

    def test_ewma_psd_tol_is_forwarded_to_the_psd_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import quantvolt.risk.covariance as covariance_module

        captured: dict[str, float] = {}
        original = covariance_module._require_psd

        def spy(
            matrix: np.ndarray, *, name: str, tol: float = covariance_module._PSD_TOL
        ) -> np.ndarray:
            captured["tol"] = tol
            return original(matrix, name=name, tol=tol)

        monkeypatch.setattr(covariance_module, "_require_psd", spy)
        rng = np.random.default_rng(1)
        returns = rng.standard_normal((50, 2))
        covariance_module.ewma_covariance(returns, psd_tol=0.5)
        assert captured["tol"] == 0.5

    def test_garch_default_psd_tol_matches_previous_behaviour(self) -> None:
        u0 = _simulate_garch(0.05, 0.10, 0.85, 500, 40)
        u1 = _simulate_garch(0.05, 0.08, 0.88, 500, 41)
        returns = np.column_stack([u0, u1])
        baseline = garch11_covariance(returns)
        defaulted = garch11_covariance(returns, psd_tol=1e-8)
        np.testing.assert_array_equal(defaulted, baseline)

    def test_garch_psd_tol_is_forwarded_to_the_psd_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import quantvolt.risk.covariance as covariance_module

        captured: dict[str, float] = {}
        original = covariance_module._require_psd

        def spy(
            matrix: np.ndarray, *, name: str, tol: float = covariance_module._PSD_TOL
        ) -> np.ndarray:
            captured["tol"] = tol
            return original(matrix, name=name, tol=tol)

        monkeypatch.setattr(covariance_module, "_require_psd", spy)
        u0 = _simulate_garch(0.05, 0.10, 0.85, 500, 50)
        u1 = _simulate_garch(0.05, 0.08, 0.88, 500, 51)
        returns = np.column_stack([u0, u1])
        covariance_module.garch11_covariance(returns, psd_tol=0.25)
        assert captured["tol"] == 0.25


class TestNearestPsd:
    def test_repairs_small_indefinite_matrix(self) -> None:
        indefinite = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3 and -1
        assert _min_eigenvalue(indefinite) < 0.0  # precondition: indefinite
        repaired = nearest_psd(indefinite)
        np.testing.assert_array_equal(repaired, repaired.T)  # exact symmetry
        assert _min_eigenvalue(repaired) >= -_PSD_TOL  # now PSD
        # Spectral projection clips the -1 eigenvalue to 0, keeping the +3 eigenspace.
        np.testing.assert_allclose(repaired, np.array([[1.5, 1.5], [1.5, 1.5]]), atol=1e-12)

    def test_already_psd_matrix_is_unchanged(self) -> None:
        psd = np.array([[2.0, 0.5], [0.5, 1.0]])
        np.testing.assert_allclose(nearest_psd(psd), psd, atol=1e-12)

    def test_non_square_raises(self) -> None:
        with pytest.raises(ValidationError, match="square"):
            nearest_psd(np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]))
