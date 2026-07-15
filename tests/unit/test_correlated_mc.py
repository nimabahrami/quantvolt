"""Unit / property tests for the correlated multi-commodity MC engine (Task 62).

Exercises ``numerics.monte_carlo.build_covariance`` and ``simulate_correlated_forwards``
— the Python boundary over the Rust ``quantvolt._core`` correlated forward kernel
(Appendix A, eqs A.5, A.8-A.13). Coverage maps to Requirement 20 and design Properties
60-61:

* Property 60 / Req 20.1, 20.4 — increment law ``ΔZ = μ + L·ε``, empirical covariance of
  ``ΔZ`` converges to ``C``, per-seed determinism, antithetic variates.
* Property 61 / Req 20.3 — a non-symmetric or non-PSD covariance raises ``ValidationError``
  naming the violated property; ``repair=True`` opts into a nearest-PSD projection.
* Req 20.2 — only unexpired tenors (``sigma > 0``) are simulated; expired tenors stay frozen.
* Req 20.5 — GBM lognormal dynamics: under the risk-neutral drift ``μ = -½·diag(C)`` the
  simulated forward ``exp(Z)`` is a martingale (an independent moment cross-check).

Conventions (see ``rust/src/paths.rs`` / ``_core.pyi``): antithetic on by default with
``(+ε, -ε)`` pairing (odd ``path_count`` rounds up); the returned array is
``(n_paths, steps + 1, D)`` with record 0 equal to ``z0``; determinism is per-seed for
the Rust RNG (the stream does not match NumPy's).
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from quantvolt.exceptions import NumericalError, ValidationError
from quantvolt.numerics.monte_carlo import (
    CorrelatedSimulationRequest,
    _nearest_psd,
    build_covariance,
    simulate_correlated_forwards,
    simulate_correlated_term_structure,
)
from quantvolt.testing import assert_input_unchanged

_SIGMA = np.array([0.20, 0.30])
_CORR = np.array([[1.0, 0.5], [0.5, 1.0]])
_DT = 1.0 / 12.0
_Z0 = np.array([np.log(100.0), np.log(50.0)])


def _cov() -> np.ndarray:
    return build_covariance(_SIGMA, _CORR, _DT)


# --- build_covariance (eq A.8) ---------------------------------------------------


def test_build_covariance_matches_diag_r_diag_dt() -> None:
    sigma = np.array([0.2, 0.3, 0.25])
    corr = np.array([[1.0, 0.4, -0.2], [0.4, 1.0, 0.1], [-0.2, 0.1, 1.0]])
    dt = 0.1
    expected = np.diag(sigma) @ corr @ np.diag(sigma) * dt
    got = build_covariance(sigma, corr, dt)
    assert np.allclose(got, expected, atol=1e-15)
    assert np.array_equal(got, got.T), "assembled covariance must be exactly symmetric"


def test_build_covariance_zero_sigma_zeroes_row_and_column() -> None:
    # An expired tenor (sigma = 0) zeroes its row/column regardless of correlation.
    cov = build_covariance(np.array([0.0, 0.3]), _CORR, _DT)
    assert np.allclose(cov[0, :], 0.0)
    assert np.allclose(cov[:, 0], 0.0)
    assert cov[1, 1] == pytest.approx(0.3**2 * _DT)


@pytest.mark.parametrize(
    ("sigma", "corr", "dt", "match"),
    [
        (np.array([0.2, 0.3]), np.array([[1.0, 0.5], [0.4, 1.0]]), _DT, "symmetric"),
        (np.array([0.2, 0.3]), np.array([[1.0, 1.5], [1.5, 1.0]]), _DT, r"\[-1, 1\]"),
        (np.array([0.2, 0.3]), np.array([[1.0, 0.5], [0.5, 0.8]]), _DT, "unit diagonal"),
        (np.array([-0.2, 0.3]), _CORR, _DT, "non-negative"),
        (_SIGMA, _CORR, 0.0, "dt"),
        (_SIGMA, np.eye(3), _DT, "square"),
    ],
)
def test_build_covariance_rejects_bad_inputs(
    sigma: np.ndarray, corr: np.ndarray, dt: float, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        build_covariance(sigma, corr, dt)


# --- keyword-only symmetry_tol / unit_diagonal_tol overrides (build_covariance) ---


def test_build_covariance_default_tolerances_match_explicit_defaults() -> None:
    implicit = build_covariance(_SIGMA, _CORR, _DT)
    explicit = build_covariance(_SIGMA, _CORR, _DT, symmetry_tol=1e-10, unit_diagonal_tol=1e-8)
    assert np.array_equal(implicit, explicit)


def test_unit_diagonal_tol_override_accepts_previously_rejected_matrix() -> None:
    sigma = np.array([0.2, 0.3])
    # Diagonal deviates by 1e-7: outside the default 1e-8 tolerance, inside a
    # relaxed 1e-6 tolerance.
    corr = np.array([[1.0, 0.5], [0.5, 0.9999999]])
    with pytest.raises(ValidationError, match="unit diagonal"):
        build_covariance(sigma, corr, _DT)
    relaxed = build_covariance(sigma, corr, _DT, unit_diagonal_tol=1e-6)
    assert relaxed.shape == (2, 2)


def test_symmetry_tol_override_accepts_previously_rejected_matrix() -> None:
    sigma = np.array([0.2, 0.3])
    # Off-diagonal asymmetry of 5e-9: outside the default 1e-10 tolerance,
    # inside a relaxed 1e-8 tolerance.
    corr = np.array([[1.0, 0.5 + 5e-9], [0.5, 1.0]])
    with pytest.raises(ValidationError, match="symmetric"):
        build_covariance(sigma, corr, _DT)
    relaxed = build_covariance(sigma, corr, _DT, symmetry_tol=1e-8)
    assert relaxed.shape == (2, 2)


# --- Property 60: determinism & increment law (Req 20.1, 20.4) -------------------


def test_same_seed_gives_identical_paths() -> None:
    cov = _cov()
    mu = -0.5 * np.diag(cov)
    a = simulate_correlated_forwards(_Z0, mu, cov, steps=6, path_count=5_000, seed=2024)
    b = simulate_correlated_forwards(_Z0, mu, cov, steps=6, path_count=5_000, seed=2024)
    assert np.array_equal(a, b)


def test_different_seeds_give_different_paths() -> None:
    cov = _cov()
    mu = np.zeros(2)
    a = simulate_correlated_forwards(_Z0, mu, cov, steps=6, path_count=2_000, seed=1)
    b = simulate_correlated_forwards(_Z0, mu, cov, steps=6, path_count=2_000, seed=2)
    assert not np.array_equal(a, b)


def test_shape_and_initial_record_and_odd_path_count_rounds_up() -> None:
    cov = _cov()
    mu = np.zeros(2)
    paths = simulate_correlated_forwards(
        _Z0, mu, cov, steps=4, path_count=999, seed=7, antithetic=True
    )
    assert paths.shape == (1000, 5, 2)  # 999 rounds up to the next even pair count
    assert np.array_equal(paths[:, 0, :], np.broadcast_to(_Z0, (1000, 2)))
    plain = simulate_correlated_forwards(
        _Z0, mu, cov, steps=4, path_count=999, seed=7, antithetic=False
    )
    assert plain.shape == (999, 5, 2)


def test_empirical_covariance_of_increments_converges_to_c() -> None:
    # Property 60: sample covariance of the first-step increment ΔZ → C.
    cov = _cov()
    mu = np.zeros(2)
    n = 300_000
    paths = simulate_correlated_forwards(
        _Z0, mu, cov, steps=1, path_count=n, seed=2024, antithetic=False
    )
    dz = paths[:, 1, :] - paths[:, 0, :]
    empirical = np.cov(dz, rowvar=False, ddof=1)
    assert np.allclose(empirical, cov, rtol=0.03, atol=1e-5)


def test_antithetic_recovers_drift_exactly() -> None:
    # Under (+ε, -ε) pairing the L·ε terms cancel, so the mean increment equals μ to
    # floating-point exactness — a strong determinism/increment-law check.
    cov = _cov()
    mu = np.array([0.013, -0.021])
    paths = simulate_correlated_forwards(
        _Z0, mu, cov, steps=1, path_count=4_000, seed=11, antithetic=True
    )
    mean_increment = (paths[:, 1, :] - paths[:, 0, :]).mean(axis=0)
    assert np.allclose(mean_increment, mu, atol=1e-12)


def test_antithetic_pairs_sum_to_twice_drift() -> None:
    cov = _cov()
    mu = np.array([0.013, -0.021])
    steps = 3
    paths = simulate_correlated_forwards(
        _Z0, mu, cov, steps=steps, path_count=200, seed=5, antithetic=True
    )
    incr = np.diff(paths, axis=1)  # (n_paths, steps, D)
    plus, minus = incr[0::2], incr[1::2]
    assert np.allclose(plus + minus, 2.0 * mu, atol=1e-12)


# --- Req 20.5: GBM lognormal martingale cross-check ------------------------------


def test_forward_is_martingale_under_risk_neutral_drift() -> None:
    # μ = -½·diag(C) makes exp(Z) a martingale: E[F_T] = F_0 = exp(z0).
    cov = _cov()
    mu = -0.5 * np.diag(cov)
    steps = 3
    paths = simulate_correlated_forwards(
        _Z0, mu, cov, steps=steps, path_count=200_000, seed=2024, antithetic=True
    )
    terminal_forward = np.exp(paths[:, steps, :]).mean(axis=0)
    assert np.allclose(terminal_forward, np.exp(_Z0), rtol=0.01)


# --- Req 20.2: unexpired-tenor masking (eq A.5) ----------------------------------


def test_expired_tenor_stays_frozen() -> None:
    # Asset 0 expired (sigma = 0) yet carries a nonzero drift; it must stay at z0 on every
    # path and step, while the active asset 1 moves.
    cov = build_covariance(np.array([0.0, 0.3]), _CORR, _DT)
    z0 = np.array([7.0, 3.0])
    drift = np.array([0.5, 0.1])  # drift on the expired tenor must be ignored
    paths = simulate_correlated_forwards(
        z0, drift, cov, steps=5, path_count=400, seed=3, antithetic=True
    )
    assert np.all(paths[:, :, 0] == 7.0), "expired tenor must not move"
    assert np.any(np.abs(paths[:, :, 1] - 3.0) > 1e-9), "active tenor must move"


def test_term_structure_changes_covariance_and_advances_expiry_mask() -> None:
    covariance = np.stack(
        [build_covariance([0.1, 0.2], _CORR, 0.1), build_covariance([0.4, 0.3], _CORR, 0.1)]
    )
    paths = simulate_correlated_term_structure(
        CorrelatedSimulationRequest(
            z0=np.array([2.0, 3.0]),
            drift_steps=np.zeros((2, 2)),
            covariance_steps=covariance,
            active_steps=np.array([[True, True], [False, True]]),
            path_count=100_000,
            seed=17,
            antithetic=False,
        )
    )
    first = paths[:, 1, :] - paths[:, 0, :]
    second = paths[:, 2, :] - paths[:, 1, :]
    assert np.var(second[:, 0]) == 0.0
    assert np.allclose(np.cov(first, rowvar=False), covariance[0], rtol=0.04, atol=2e-5)
    assert np.var(second[:, 1], ddof=1) == pytest.approx(covariance[1, 1, 1], rel=0.04)


def test_term_structure_is_seed_deterministic() -> None:
    covariance = np.stack([_cov(), 2.0 * _cov()])
    request = CorrelatedSimulationRequest(_Z0, np.zeros((2, 2)), covariance, path_count=200, seed=9)
    assert np.array_equal(
        simulate_correlated_term_structure(request), simulate_correlated_term_structure(request)
    )


# --- Property 61: non-PSD rejection & opt-in repair (Req 20.3) -------------------


def test_non_symmetric_covariance_raises_naming_symmetry() -> None:
    cov = np.array([[1.0, 0.5], [0.3, 1.0]])
    with pytest.raises(ValidationError, match="symmetric"):
        simulate_correlated_forwards(_Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1)


def test_non_psd_covariance_raises_naming_psd() -> None:
    cov = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3, -1 → indefinite
    with pytest.raises(ValidationError, match="positive semidefinite"):
        simulate_correlated_forwards(_Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1)


def test_repair_projects_to_psd_and_runs() -> None:
    cov = np.array([[1.0, 2.0], [2.0, 1.0]])  # indefinite
    # Without repair: rejected. With repair: nearest-PSD projection, then simulates.
    with pytest.raises(ValidationError):
        simulate_correlated_forwards(_Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1)
    paths = simulate_correlated_forwards(
        _Z0, np.zeros(2), cov, steps=2, path_count=1_000, seed=1, repair=True
    )
    assert paths.shape == (1000, 3, 2)
    assert np.all(np.isfinite(paths))


def test_repair_true_clips_a_within_tolerance_negative_eigenvalue() -> None:
    # Fix 3 regression: min eigenvalue sits at ~-1.6e-10, *inside* the default psd_tol
    # gate (so it never reached the `min_eig < -tol` branch), yet the native Cholesky
    # has no tolerance of its own and rejected it even with repair=True (verified).
    # repair=True must now clip the matrix to exactly PSD before it reaches Rust.
    cov = np.array([[1.0, 1.0 + 8e-11], [1.0 + 8e-11, 1.0]])
    min_eig = float(np.linalg.eigvalsh(cov).min())
    assert -1e-8 < min_eig < 0.0  # within the default (scaled) psd_tol, still negative

    paths = simulate_correlated_forwards(
        np.zeros(2), np.zeros(2), cov, steps=2, path_count=1_000, seed=1, repair=True
    )
    assert paths.shape == (1000, 3, 2)
    assert np.all(np.isfinite(paths))

    # repair=False: the documented behavior is unchanged — the Python gate still
    # passes the matrix through (within tolerance), and the native Cholesky's
    # zero-tolerance pivot check rejects it, surfacing as NumericalError.
    with pytest.raises(NumericalError):
        simulate_correlated_forwards(
            np.zeros(2), np.zeros(2), cov, steps=2, path_count=1_000, seed=1, repair=False
        )


def test_nearest_psd_is_symmetric_and_psd() -> None:
    cov = np.array([[1.0, 2.0], [2.0, 1.0]])
    repaired = _nearest_psd(cov)
    assert np.allclose(repaired, repaired.T)
    assert float(np.linalg.eigvalsh(repaired).min()) >= -1e-12


# --- keyword-only symmetry_tol / psd_tol overrides (simulate_correlated_forwards) --


def test_default_symmetry_and_psd_tol_match_explicit_defaults() -> None:
    cov = _cov()
    mu = np.zeros(2)
    implicit = simulate_correlated_forwards(_Z0, mu, cov, steps=2, path_count=100, seed=1)
    explicit = simulate_correlated_forwards(
        _Z0, mu, cov, steps=2, path_count=100, seed=1, symmetry_tol=1e-10, psd_tol=1e-10
    )
    assert np.array_equal(implicit, explicit)


def test_psd_tol_override_changes_which_layer_rejects_the_covariance() -> None:
    # Min eigenvalue ~ -5e-9: outside the default 1e-10 (scaled) Python-boundary
    # tolerance, so the default raises ValidationError naming "positive
    # semidefinite" before ever reaching the native kernel. A relaxed psd_tol
    # widens the Python-side gate to let the matrix through; the native Rust
    # Cholesky then applies its own fixed backstop tolerance (out of scope for
    # this task, see rust/src/paths.rs) and raises NumericalError instead — a
    # different failure mode, proving psd_tol changed the code path taken.
    cov = np.array([[1.0, 1.000000005], [1.000000005, 1.0]])
    with pytest.raises(ValidationError, match="positive semidefinite"):
        simulate_correlated_forwards(_Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1)
    with pytest.raises(NumericalError):
        simulate_correlated_forwards(
            _Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1, psd_tol=1e-7
        )


def test_symmetry_tol_override_accepts_a_previously_rejected_covariance() -> None:
    # Off-diagonal asymmetry of 5e-9: outside the default 1e-10 tolerance,
    # inside a relaxed 1e-8 tolerance.
    cov = np.array([[1.0, 0.5 + 5e-9], [0.5, 1.0]])
    with pytest.raises(ValidationError, match="symmetric"):
        simulate_correlated_forwards(_Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1)
    paths = simulate_correlated_forwards(
        _Z0, np.zeros(2), cov, steps=2, path_count=100, seed=1, symmetry_tol=1e-8
    )
    assert paths.shape == (100, 3, 2)


# --- Boundary validation (Req 11.5) ----------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"drift": np.zeros(3)}, "drift"),
        ({"cov": np.zeros((3, 3))}, "match z0"),
        ({"steps": 0}, "steps"),
        ({"path_count": 0}, "path_count"),
        ({"seed": -1}, "seed"),
    ],
)
def test_simulate_rejects_bad_inputs(kwargs: dict, match: str) -> None:
    base = {
        "z0": _Z0,
        "drift": np.zeros(2),
        "cov": _cov(),
        "steps": 2,
        "path_count": 100,
        "seed": 1,
    }
    base.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        simulate_correlated_forwards(**base)


# --- Fix 9: CorrelatedSimulationRequest equality over array fields ---------------


def _sample_request() -> CorrelatedSimulationRequest:
    covariance = np.stack([_cov(), 2.0 * _cov()])
    return CorrelatedSimulationRequest(
        z0=_Z0,
        drift_steps=np.zeros((2, 2)),
        covariance_steps=covariance,
        path_count=200,
        seed=9,
        active_steps=np.array([[True, True], [True, True]]),
    )


def test_request_equals_its_deepcopy() -> None:
    # Previously a raw dataclass __eq__ compared array fields with plain ==, raising
    # ValueError: "The truth value of an array ... is ambiguous" (verified).
    request = _sample_request()
    assert request == copy.deepcopy(request)


def test_request_equality_detects_a_differing_array_field() -> None:
    request = _sample_request()
    other = copy.deepcopy(request)
    other = CorrelatedSimulationRequest(
        z0=other.z0 + 1.0,
        drift_steps=other.drift_steps,
        covariance_steps=other.covariance_steps,
        path_count=other.path_count,
        seed=other.seed,
        active_steps=other.active_steps,
    )
    assert request != other


def test_request_equality_detects_a_differing_scalar_field() -> None:
    request = _sample_request()
    other = copy.deepcopy(request)
    other = CorrelatedSimulationRequest(
        z0=other.z0,
        drift_steps=other.drift_steps,
        covariance_steps=other.covariance_steps,
        path_count=other.path_count,
        seed=other.seed + 1,
        active_steps=other.active_steps,
    )
    assert request != other


def test_request_is_hashable_by_identity() -> None:
    # Defining __eq__ would otherwise make the frozen dataclass unhashable; the
    # documented fallback is object's identity-based hash (matching dataclass's own
    # eq=False semantics, which leave __hash__ "untouched").
    request = _sample_request()
    assert hash(request) == object.__hash__(request)


def test_assert_input_unchanged_passes_on_the_documented_entry_point() -> None:
    # The shipped immutability utility falls back to plain == for non-array,
    # non-Polars inputs; this previously raised the same ValueError as the bare
    # equality check above (verified).
    request = _sample_request()
    result = assert_input_unchanged(simulate_correlated_term_structure, request)
    assert result.shape[0] == request.path_count
