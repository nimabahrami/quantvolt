"""Correlated-simulation correctness properties (design Properties 60-61; Task 77).

Covers the covariance recovery / determinism of the native correlated Monte-Carlo engine
(Property 60) and its non-PSD covariance gate (Property 61).

Both properties drive the compiled Rust kernel, so they use reduced example counts with
small state dimensions and single (large) samples per example — kept well under the added
runtime budget while still exercising convergence at the scale the design quantifies.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.numerics.monte_carlo import build_covariance, simulate_correlated_forwards
from strategies import correlation_matrices

# ---------------------------------------------------------------------------------------
# Property 60: Correlated MC Covariance Recovery.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 60: Correlated MC Covariance Recovery
# A large simulated sample of one-step increments ΔZ must have empirical covariance
# converging to C = diag(sigma)·R·diag(sigma)·Δt, and an identical seed must reproduce the
# paths bit-for-bit. Reduced examples (each draws 40k paths through the Rust kernel).
@given(corr=correlation_matrices(min_dim=2, max_dim=3), data=st.data())
@settings(max_examples=10, deadline=None)
def test_property_60_empirical_covariance_recovers_c_and_seed_is_reproducible(
    corr: npt.NDArray[np.float64], data: st.DataObject
) -> None:
    n = int(corr.shape[0])
    sigma = np.array(
        data.draw(st.lists(st.floats(min_value=0.1, max_value=1.0), min_size=n, max_size=n)),
        dtype=np.float64,
    )
    dt = data.draw(st.floats(min_value=0.05, max_value=1.0))
    cov = build_covariance(sigma, corr, dt)

    z0 = np.zeros(n)
    drift = np.zeros(n)
    path_count, seed = 40_000, 20240715
    paths = simulate_correlated_forwards(z0, drift, cov, steps=1, path_count=path_count, seed=seed)
    increments = paths[:, 1, :] - paths[:, 0, :]  # ΔZ = μ + L·ε with μ = 0
    empirical = np.cov(increments, rowvar=False)

    max_diag = float(np.max(np.diag(cov)))
    assert empirical == pytest.approx(cov, rel=0.12, abs=0.04 * max_diag + 1e-9)

    # Determinism (Req 20.4): identical seed -> bit-identical paths.
    again = simulate_correlated_forwards(z0, drift, cov, steps=1, path_count=path_count, seed=seed)
    assert np.array_equal(paths, again)


# ---------------------------------------------------------------------------------------
# Property 61: Non-PSD Covariance Rejected.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 61: Non-PSD Covariance Rejected
# A symmetric matrix with an injected negative eigenvalue must be rejected (naming the PSD
# violation) rather than producing a complex Cholesky factor; ``repair=True`` opts into a
# nearest-PSD projection and then succeeds.
@given(seed=st.integers(min_value=0, max_value=2**31 - 1), n=st.integers(min_value=2, max_value=3))
@settings(max_examples=25, deadline=None)
def test_property_61_non_psd_covariance_rejected_unless_repaired(seed: int, n: int) -> None:
    rng = np.random.default_rng(seed)
    orthogonal, _ = np.linalg.qr(rng.standard_normal((n, n)))
    eigenvalues = rng.uniform(0.1, 1.0, size=n)
    eigenvalues[0] = -rng.uniform(0.1, 2.0)  # force a clearly negative eigenvalue -> not PSD
    cov = orthogonal @ np.diag(eigenvalues) @ orthogonal.T
    cov = 0.5 * (cov + cov.T)  # exact symmetry so only the PSD gate can trip
    z0, drift = np.zeros(n), np.zeros(n)

    with pytest.raises(ValidationError, match="positive semidefinite"):
        simulate_correlated_forwards(z0, drift, cov, steps=1, path_count=64, seed=1)

    repaired = simulate_correlated_forwards(
        z0, drift, cov, steps=1, path_count=64, seed=1, repair=True
    )
    assert repaired.shape == (64, 2, n)
    assert np.all(np.isfinite(repaired))


# Feature: power-energy-quant-analysis, Property 61: Non-PSD Covariance Rejected
# A non-symmetric covariance trips the symmetry gate first; with repair it is symmetrised
# and then projected to the nearest PSD matrix.
def test_property_61_non_symmetric_covariance_rejected_unless_repaired() -> None:
    cov = np.array([[1.0, 0.0], [5.0, 1.0]])  # asymmetric; symmetric part is non-PSD too
    z0, drift = np.zeros(2), np.zeros(2)
    with pytest.raises(ValidationError, match="symmetric"):
        simulate_correlated_forwards(z0, drift, cov, steps=1, path_count=64, seed=1)
    repaired = simulate_correlated_forwards(
        z0, drift, cov, steps=1, path_count=64, seed=1, repair=True
    )
    assert repaired.shape == (64, 2, 2)
