"""Unit tests for the multifactor & multi-commodity forward-curve models (Task 82).

Exercises ``curvemodels.multifactor`` against Requirement 25.3-25.6 and design
Properties 71-72:

* Property 71 / Req 25.3 -- ``MultifactorForwardModel`` reproduces ``F(0, T)`` at ``t = 0``
  (exact, by construction) and carries no ``Q``-drift in ``F``: simulated ``E[F(t, T)] =
  F(0, T)`` within Monte Carlo tolerance (driven through the Task-62 correlated engine with
  drift ``-1/2·diag(C)``).
* Property 72 / Req 25.3, 25.4 -- the induced correlation lies in ``[-1, 1]``, is symmetric
  with unit diagonal and PSD, and the assembled cumulative covariance ``Gamma`` is PSD; the
  §33.3 option-variance-matching identity ``Gamma_ii(T) == sum_t sum_k sigma_k(t, T)^2·dt``
  holds exactly on a hand-built 2-factor example, and correlation-matching reproduces a
  target correlation on a constructible case.
* Req 25.5 -- the lognormal-not-for-power advisory (:class:`LognormalPowerWarning`) fires
  for power-like commodity ids.
* Req 25.6 / 11.2 -- determinism (per-seed identical paths); Req 11.4/11.5 -- input
  immutability (``assert_input_unchanged``) and validation naming the offending parameter.

Section citations refer to ``polished_energy_derivatives_modeling_specification.md`` §32-33.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantvolt.curvemodels.multifactor import (
    LognormalPowerWarning,
    MultifactorForwardModel,
    _is_power_like,
    cumulative_covariance,
    forward_matching_residual,
    induced_correlation,
    induced_covariance,
    matches_initial_curve,
    matches_option_variance,
    mc_inputs,
    option_variance,
    risk_neutral_drift,
    simulate_forwards,
    warn_if_power_like,
)
from quantvolt.exceptions import ValidationError
from quantvolt.numerics.monte_carlo import build_covariance, simulate_correlated_forwards
from quantvolt.testing import assert_input_unchanged

# A hand-built 2-factor, 2-tenor, 2-step model with a non-monthly dt so the identity tests
# do not accidentally pass on dt == 1.
_HAND_LOADINGS = np.array(
    [
        [[0.10, 0.20], [0.30, 0.05]],  # step 0: [factor0 over tenors], [factor1 over tenors]
        [[0.15, 0.10], [0.20, 0.25]],  # step 1
    ]
)
_HAND_DT = 0.5

# A constructible correlation-matching target (positive definite) and per-tenor vols.
_TARGET_CORR = np.array([[1.0, 0.5, -0.2], [0.5, 1.0, 0.3], [-0.2, 0.3, 1.0]])
_TARGET_VOLS = np.array([0.20, 0.25, 0.30])


def _hand_model() -> MultifactorForwardModel:
    return MultifactorForwardModel(_HAND_LOADINGS, dt=_HAND_DT)


def _corr_model(n_steps: int = 3) -> MultifactorForwardModel:
    return MultifactorForwardModel.from_target_correlation(
        _TARGET_CORR, _TARGET_VOLS, n_steps=n_steps, dt=1.0 / 12.0
    )


# --- construction & validation ---------------------------------------------------


def test_shape_properties_and_default_dt() -> None:
    model = _hand_model()
    assert (model.n_steps, model.n_factors, model.n_tenors) == (2, 2, 2)
    assert MultifactorForwardModel(_HAND_LOADINGS).dt == pytest.approx(1.0 / 12.0)


def test_constructor_copies_input_and_stores_read_only() -> None:
    src = _HAND_LOADINGS.copy()
    model = MultifactorForwardModel(src)
    # Stored array is a read-only copy: mutating the source does not leak in ...
    src[0, 0, 0] = 999.0
    assert model.loadings[0, 0, 0] == pytest.approx(_HAND_LOADINGS[0, 0, 0])
    # ... and the stored array cannot be mutated in place.
    with pytest.raises(ValueError, match="read-only"):
        model.loadings[0, 0, 0] = 1.0


@pytest.mark.parametrize(
    ("loadings", "dt", "match"),
    [
        (np.ones((2, 2)), 1.0, "3-D"),
        (np.ones((0, 2, 2)), 1.0, "non-empty"),
        (np.ones((2, 0, 2)), 1.0, "non-empty"),
        (np.ones((2, 2, 0)), 1.0, "non-empty"),
        (np.array([[[np.nan, 0.1], [0.2, 0.3]]]), 1.0, "finite"),
        (np.ones((1, 1, 1)), 0.0, "dt"),
        (np.ones((1, 1, 1)), -0.5, "dt"),
    ],
)
def test_constructor_rejects_bad_inputs(loadings: np.ndarray, dt: float, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        MultifactorForwardModel(loadings, dt=dt)


def test_equality_and_hash_by_value() -> None:
    a = MultifactorForwardModel(_HAND_LOADINGS, dt=_HAND_DT)
    b = MultifactorForwardModel(_HAND_LOADINGS.copy(), dt=_HAND_DT)
    c = MultifactorForwardModel(_HAND_LOADINGS, dt=0.25)
    assert a == b
    assert hash(a) == hash(b)
    assert a != c
    assert a != "not a model"


# --- Property 72: induced covariance / correlation (§32.2, §33.4) ----------------


def test_induced_covariance_is_gram_matrix_symmetric_and_psd() -> None:
    model = _hand_model()
    for step in range(model.n_steps):
        left = _HAND_LOADINGS[step]  # (K, D)
        expected = left.T @ left
        cov = induced_covariance(model, step)
        assert np.allclose(cov, expected, atol=1e-15)
        assert np.array_equal(cov, cov.T)
        assert float(np.linalg.eigvalsh(cov).min()) >= -1e-12


def test_induced_correlation_bounds_unit_diagonal_symmetric_psd() -> None:
    model = _corr_model()
    corr = induced_correlation(model, 0)
    assert np.all(corr >= -1.0) and np.all(corr <= 1.0)
    assert np.allclose(np.diag(corr), 1.0, atol=1e-12)
    assert np.array_equal(corr, corr.T)
    assert float(np.linalg.eigvalsh(corr).min()) >= -1e-12


def test_induced_correlation_zero_variance_tenor_has_unit_diagonal() -> None:
    """A tenor with all-zero loadings (expired, eq A.5) has undefined OFF-diagonal
    correlation with every other tenor (0), but its own diagonal entry is a unit-
    diagonal convention (1), not 0 -- regression: a 0 diagonal here is rejected by
    ``build_covariance``'s unit-diagonal check even though ``sigma_i = 0`` already
    zeroes that row/column of the covariance regardless of the diagonal value, which
    previously crashed ``simulate_forwards`` for any model with an expired tenor.
    """
    loadings = np.array([[[0.2, 0.0], [0.1, 0.0]]])  # tenor 1 has zero loadings
    model = MultifactorForwardModel(loadings)
    corr = induced_correlation(model, 0)
    assert corr[0, 0] == pytest.approx(1.0)
    assert corr[1, 1] == pytest.approx(1.0)
    assert corr[0, 1] == pytest.approx(0.0)
    assert np.all(np.isfinite(corr))


@pytest.mark.parametrize("step", [-1, 2, 99])
def test_induced_functions_reject_out_of_range_step(step: int) -> None:
    model = _hand_model()
    with pytest.raises(ValidationError, match="step"):
        induced_covariance(model, step)
    with pytest.raises(ValidationError, match="step"):
        induced_correlation(model, step)


# --- Property 72: cumulative covariance Gamma & option-variance identity (§33) ----


def test_cumulative_covariance_matches_manual_sum_and_is_psd() -> None:
    model = _hand_model()
    manual = sum(_HAND_LOADINGS[b].T @ _HAND_LOADINGS[b] for b in range(2)) * _HAND_DT
    gamma = cumulative_covariance(model)
    assert np.allclose(gamma, manual, atol=1e-15)
    assert np.array_equal(gamma, gamma.T)
    assert float(np.linalg.eigvalsh(gamma).min()) >= -1e-12


def test_cumulative_covariance_upto_step_partial_horizon() -> None:
    model = _hand_model()
    partial = cumulative_covariance(model, upto_step=1)
    expected = (_HAND_LOADINGS[0].T @ _HAND_LOADINGS[0]) * _HAND_DT
    assert np.allclose(partial, expected, atol=1e-15)


@pytest.mark.parametrize("upto_step", [0, 3, -1])
def test_cumulative_covariance_rejects_bad_upto_step(upto_step: int) -> None:
    with pytest.raises(ValidationError, match="upto_step"):
        cumulative_covariance(_hand_model(), upto_step=upto_step)


def test_option_variance_identity_hand_built_two_factor() -> None:
    # §33.3 LHS: Gamma_ii(T) == sum_t sum_k sigma_k(t, T_i)^2 · dt, exactly.
    model = _hand_model()
    manual = np.array(
        [
            sum(_HAND_LOADINGS[b, k, j] ** 2 for b in range(2) for k in range(2)) * _HAND_DT
            for j in range(2)
        ]
    )
    got = option_variance(model)
    assert np.allclose(got, manual, rtol=0.0, atol=1e-15)
    assert np.allclose(got, np.diag(cumulative_covariance(model)), atol=1e-15)


def test_matches_option_variance_true_for_constant_loadings() -> None:
    # from_target_correlation gives constant loadings, so Gamma_ii == v_i^2 · (n_steps·dt).
    n_steps = 4
    model = _corr_model(n_steps=n_steps)
    horizon = n_steps * (1.0 / 12.0)
    expiries = np.full(model.n_tenors, horizon)
    assert matches_option_variance(model, _TARGET_VOLS, expiries)
    # A wrong implied vol fails the identity.
    assert not matches_option_variance(model, _TARGET_VOLS * 1.5, expiries)


@pytest.mark.parametrize(
    ("vols", "expiries", "match"),
    [
        (np.ones(2), np.ones(3), "implied_vols"),
        (np.ones(3), np.ones(2), "expiries"),
        (np.ones(3), np.array([1.0, 0.0, 1.0]), "positive"),
    ],
)
def test_matches_option_variance_validates_shapes(
    vols: np.ndarray, expiries: np.ndarray, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        matches_option_variance(_corr_model(), vols, expiries)


# --- Property 72: correlation-matching constructor (§33.4) -----------------------


def test_from_target_correlation_reproduces_target_and_vols_exactly() -> None:
    model = _corr_model()
    assert model.n_factors == _TARGET_VOLS.shape[0]  # full-rank representation
    corr = induced_correlation(model, 0)
    assert np.allclose(corr, _TARGET_CORR, atol=1e-12)
    vols = np.sqrt(np.diag(induced_covariance(model, 0)))
    assert np.allclose(vols, _TARGET_VOLS, atol=1e-12)
    # Constant across steps.
    assert np.allclose(induced_correlation(model, 2), _TARGET_CORR, atol=1e-12)


def test_from_target_correlation_handles_psd_singular_target() -> None:
    # A rank-deficient (PSD but singular) target: eigen factorisation must not fail.
    singular = np.array([[1.0, 1.0], [1.0, 1.0]])
    model = MultifactorForwardModel.from_target_correlation(singular, np.array([0.2, 0.2]))
    corr = induced_correlation(model, 0)
    assert np.allclose(corr, singular, atol=1e-10)


@pytest.mark.parametrize(
    ("corr", "vols", "n_steps", "match"),
    [
        (np.array([[1.0, 0.5], [0.4, 1.0]]), np.ones(2), 1, "symmetric"),
        (np.array([[1.0, 2.0], [2.0, 1.0]]), np.ones(2), 1, r"\[-1, 1\]"),
        # In-range entries but indefinite (eigenvalues -0.8, 1.9, 1.9): hits the PSD gate.
        (
            np.array([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]]),
            np.ones(3),
            1,
            "positive semidefinite",
        ),
        (np.array([[1.0, 0.5], [0.5, 0.8]]), np.ones(2), 1, "unit diagonal"),
        (np.eye(3), np.ones(2), 1, "square"),
        (np.eye(2), np.array([0.2, -0.1]), 1, "non-negative"),
        (np.eye(2), np.ones(2), 0, "n_steps"),
    ],
)
def test_from_target_correlation_rejects_bad_inputs(
    corr: np.ndarray, vols: np.ndarray, n_steps: int, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        MultifactorForwardModel.from_target_correlation(corr, vols, n_steps=n_steps)


# --- new keyword-only tolerances: symmetry_tol, psd_eig_tol, unit_diagonal_tol ---


def test_tolerance_defaults_match_hardcoded_behaviour() -> None:
    baseline = MultifactorForwardModel.from_target_correlation(_TARGET_CORR, _TARGET_VOLS)
    explicit = MultifactorForwardModel.from_target_correlation(
        _TARGET_CORR,
        _TARGET_VOLS,
        symmetry_tol=1e-10,
        psd_eig_tol=1e-10,
        unit_diagonal_tol=1e-8,
    )
    assert baseline == explicit


def test_symmetry_tol_widened_accepts_a_previously_rejected_matrix() -> None:
    slightly_asymmetric = np.array([[1.0, 0.5], [0.5 + 1e-7, 1.0]])
    vols = np.array([0.2, 0.2])
    with pytest.raises(ValidationError, match="symmetric"):
        MultifactorForwardModel.from_target_correlation(slightly_asymmetric, vols)
    model = MultifactorForwardModel.from_target_correlation(
        slightly_asymmetric, vols, symmetry_tol=1e-5
    )
    assert model.n_factors == 2


def test_unit_diagonal_tol_widened_accepts_a_previously_rejected_matrix() -> None:
    # symmetry_tol is widened in both calls so only the diagonal tolerance is under
    # test (the "entries in [-1, 1]" check otherwise fires first at the default tol).
    off_unit_diagonal = np.array([[1.0 + 5e-7, 0.3], [0.3, 1.0]])
    vols = np.array([0.2, 0.2])
    with pytest.raises(ValidationError, match="unit diagonal"):
        MultifactorForwardModel.from_target_correlation(off_unit_diagonal, vols, symmetry_tol=1.0)
    model = MultifactorForwardModel.from_target_correlation(
        off_unit_diagonal, vols, symmetry_tol=1.0, unit_diagonal_tol=1e-4
    )
    assert model.n_factors == 2


def test_psd_eig_tol_widened_accepts_a_previously_rejected_matrix() -> None:
    # Slightly indefinite (min eigenvalue ~ -2e-7): rejected at the default 1e-10 gate.
    # symmetry_tol is widened so the unrelated "entries in [-1, 1]" check does not fire.
    slightly_indefinite = np.array([[1.0, 1.0 + 2e-7], [1.0 + 2e-7, 1.0]])
    vols = np.array([0.2, 0.2])
    with pytest.raises(ValidationError, match="positive semidefinite"):
        MultifactorForwardModel.from_target_correlation(slightly_indefinite, vols, symmetry_tol=1.0)
    model = MultifactorForwardModel.from_target_correlation(
        slightly_indefinite, vols, symmetry_tol=1.0, psd_eig_tol=1e-5
    )
    assert model.n_factors == 2


@pytest.mark.parametrize("kwarg", ["symmetry_tol", "psd_eig_tol", "unit_diagonal_tol"])
def test_tolerance_must_be_positive(kwarg: str) -> None:
    with pytest.raises(ValidationError, match=kwarg):
        MultifactorForwardModel.from_target_correlation(_TARGET_CORR, _TARGET_VOLS, **{kwarg: 0.0})


# --- Property 71: initial-curve match & martingale (Req 25.3) --------------------


def test_initial_curve_matched_by_construction_exact() -> None:
    model = _corr_model()
    f0 = np.array([100.0, 50.0, 75.0])
    paths = simulate_forwards(model, f0, steps=3, path_count=2_000, seed=1)
    assert paths.shape == (2_000, 4, 3)
    # Record 0 equals exp(log F0) on every path -- exact (bit-identical), not merely close.
    expected = np.broadcast_to(np.exp(np.log(f0)), (2_000, 3))
    assert np.array_equal(paths[:, 0, :], expected)


def test_forward_is_martingale_no_q_drift() -> None:
    # μ = -½·diag(C) carries no Q-drift in F: E^Q[F_T] = F(0, T) within MC tolerance.
    model = _corr_model()
    f0 = np.array([100.0, 50.0, 75.0])
    paths = simulate_forwards(model, f0, steps=3, path_count=100_000, seed=2024)
    expected_forward = paths[:, 3, :].mean(axis=0)
    residual = forward_matching_residual(f0, expected_forward)
    # Recorded numbers (seed=2024): E[F] within ~4e-5 relative of F0.
    assert np.all(np.abs(residual) / f0 < 2e-3), residual
    assert matches_initial_curve(f0, expected_forward, rtol=0.02)


def test_matches_initial_curve_uses_relative_tolerance() -> None:
    f0 = np.array([100.0, 50.0])
    # A 1% offset passes rtol=0.02 but a residual-vs-zero check (rtol against 0) would fail.
    assert matches_initial_curve(f0, f0 * 1.01, rtol=0.02)
    assert not matches_initial_curve(f0, f0 * 1.5, rtol=0.02)


def test_forward_matching_residual_shape_mismatch_raises() -> None:
    with pytest.raises(ValidationError, match="equal shape"):
        forward_matching_residual(np.ones(3), np.ones(2))


# --- bridge to the correlated MC engine (§2.20, Task 62) -------------------------


def test_mc_inputs_reconstruct_induced_covariance_via_build_covariance() -> None:
    model = _corr_model()
    sigma, corr = mc_inputs(model, 0)
    assert np.all(sigma >= 0.0)
    cov = build_covariance(sigma, corr, model.dt)  # accepts the structure (its own validation)
    assert np.allclose(cov, induced_covariance(model, 0) * model.dt, atol=1e-14)


def test_mc_structure_drives_engine_directly() -> None:
    model = _corr_model()
    f0 = np.array([100.0, 50.0, 75.0])
    sigma, corr = mc_inputs(model, 0)
    cov = build_covariance(sigma, corr, model.dt)
    drift = risk_neutral_drift(cov)
    paths = simulate_correlated_forwards(np.log(f0), drift, cov, steps=2, path_count=1_000, seed=7)
    # Same as going through simulate_forwards (which wraps exactly this).
    forward_paths = simulate_forwards(model, f0, steps=2, path_count=1_000, seed=7)
    assert np.allclose(np.exp(paths), forward_paths)


def test_simulate_forwards_holds_expired_tenor_fixed() -> None:
    """Regression: an expired tenor (all-zero loadings column, eq A.5) must not crash
    ``simulate_forwards`` via ``build_covariance``'s unit-diagonal check (previously the
    documented 0-diagonal encoding for zero-variance tenors was rejected there), and the
    simulator must hold that tenor's forward fixed at its initial value on every path
    and step, per ``build_covariance``/``simulate_correlated_forwards``'s own eq A.5
    expired-tenor masking.
    """
    loadings = np.array([[[0.2, 0.0], [0.1, 0.0]]])  # tenor 1 (index 1) has zero loadings.
    model = MultifactorForwardModel(loadings)
    f0 = np.array([100.0, 42.0])
    paths = simulate_forwards(model, f0, steps=3, path_count=200, seed=3)
    assert paths.shape == (200, 4, 2)
    # Expired tenor (index 1) is held fixed at its initial forward on every path/step
    # (to float round-off from the assembled-covariance symmetrization, not bit-exact).
    assert np.allclose(paths[:, :, 1], f0[1], atol=1e-10, rtol=0.0)
    # The non-expired tenor (index 0) actually moves.
    assert not np.allclose(paths[:, -1, 0], f0[0])


def test_risk_neutral_drift_is_minus_half_diag() -> None:
    cov = np.array([[0.04, 0.01], [0.01, 0.09]])
    assert np.allclose(risk_neutral_drift(cov), np.array([-0.02, -0.045]))


def test_risk_neutral_drift_rejects_non_square() -> None:
    with pytest.raises(ValidationError, match="square"):
        risk_neutral_drift(np.ones((2, 3)))


@pytest.mark.parametrize(
    ("initial", "match"),
    [
        (np.ones(2), r"shape"),
        (np.array([100.0, -1.0, 50.0]), "positive"),
        (np.array([100.0, np.inf, 50.0]), "finite"),
    ],
)
def test_simulate_forwards_validates_initial_curve(initial: np.ndarray, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        simulate_forwards(_corr_model(), initial, steps=2, path_count=100, seed=1)


# --- Req 25.5: lognormal-not-for-power advisory ----------------------------------


def test_warn_if_power_like_fires_for_power_ids() -> None:
    with pytest.warns(LognormalPowerWarning, match="power"):
        matched = warn_if_power_like(["EPEX_DE", "TTF", "EUA"])
    assert matched == ("EPEX_DE",)


def test_warn_if_power_like_silent_for_non_power() -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would raise
        matched = warn_if_power_like(["TTF", "NBP", "EUA"])
    assert matched == ()


def test_simulate_forwards_warns_when_commodity_ids_power_like() -> None:
    model = _corr_model()
    f0 = np.array([100.0, 50.0, 75.0])
    with pytest.warns(LognormalPowerWarning):
        simulate_forwards(
            model, f0, steps=2, path_count=200, seed=1, commodity_ids=["EEX_PHELIX_DE", "TTF", "X"]
        )


@pytest.mark.parametrize(
    ("cid", "expected"),
    [
        ("EPEX_DE", True),
        ("EEX_PHELIX_AT", True),
        ("nordpool_no", True),  # substring, case-insensitive
        ("SOME_POWER_HUB", True),
        ("TTF", False),
        ("NBP", False),
        ("EUA", False),
    ],
)
def test_is_power_like_classification(cid: str, expected: bool) -> None:
    assert _is_power_like(cid) is expected


# --- Req 25.6 / 11.2: determinism ------------------------------------------------


def test_simulate_forwards_is_deterministic_per_seed() -> None:
    model = _corr_model()
    f0 = np.array([100.0, 50.0, 75.0])
    a = simulate_forwards(model, f0, steps=4, path_count=5_000, seed=99)
    b = simulate_forwards(model, f0, steps=4, path_count=5_000, seed=99)
    assert np.array_equal(a, b)
    c = simulate_forwards(model, f0, steps=4, path_count=5_000, seed=100)
    assert not np.array_equal(a, c)


# --- Req 11.4: input immutability (assert_input_unchanged) -----------------------


def test_inputs_are_not_mutated() -> None:
    model = _corr_model()
    assert_input_unchanged(induced_covariance, model, 0)
    assert_input_unchanged(induced_correlation, model, 0)
    assert_input_unchanged(cumulative_covariance, model)
    assert_input_unchanged(option_variance, model)
    assert_input_unchanged(mc_inputs, model, 0)
    assert_input_unchanged(risk_neutral_drift, np.array([[0.04, 0.0], [0.0, 0.09]]))
    assert_input_unchanged(forward_matching_residual, np.ones(3), np.full(3, 1.1))
    assert_input_unchanged(
        MultifactorForwardModel.from_target_correlation, _TARGET_CORR, _TARGET_VOLS
    )
    assert_input_unchanged(warn_if_power_like, ["TTF", "NBP"])
