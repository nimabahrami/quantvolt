"""Unit tests for the two-factor Schwartz-Smith model (Task 81).

Coverage maps to Requirement 25 and design Properties 69-70:

* Property 69 / Req 25.1 — ``forward_curve`` reproduces the §31.2 closed form. The
  reference ``A(tau)`` here is computed by an *independent route* (plain per-element
  ``math.exp`` arithmetic) from the boxed §31.2 equation, whereas the module uses
  vectorised ``np.expm1``.
* Property 70 / Req 25.1 — as ``kappa*tau -> inf`` the short-factor loading
  ``e^(-kappa*tau) -> 0``, so long-dated forwards are insensitive to ``chi``.
* Property 70 / Req 25.2 — calibration round-trip: curves simulated from known
  parameters are Kalman-filter calibrated and the *identified* parameters
  (``kappa, sigma_chi, sigma_xi, rho, mu_xi_star``) are recovered within documented
  loose tolerances; diagnostics are reported. The individual drift/premium split
  (``mu_xi`` vs ``lambda_xi``) is only weakly identified — the model spec documents
  this — so only the risk-neutral combination ``mu_xi_star`` is asserted.
* Req 25.5 — the initial-curve mismatch flag fires on deliberately inconsistent
  (non-two-factor, seasonally humped) input, and the lognormal-power caveat is present.
* Req 25.6 / 11.2 — ``simulate`` is bit-deterministic under a seed and its moments match
  the exact OU / arithmetic-BM closed forms; ``calibrate`` is deterministic.
* Req 11.5 — every validation error names the offending parameter.

Runtime: exactly one expensive calibration (the module-scoped ``roundtrip`` fixture,
90 weekly observations x 5 tenors, ~10 s); every other test uses tiny data.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from quantvolt.curvemodels.schwartz_smith import (
    CalibrationDiagnostics,
    SchwartzSmithParams,
    calibrate,
    forward_curve,
    log_forward_curve,
    simulate,
)
from quantvolt.exceptions import InsufficientDataError, ValidationError

_PARAMS = SchwartzSmithParams(
    kappa=1.2,
    sigma_chi=0.30,
    sigma_xi=0.15,
    mu_xi=0.02,
    rho=-0.3,
    lambda_chi=0.05,
    lambda_xi=0.01,
)


def _a_tau_reference(p: SchwartzSmithParams, tau: float) -> float:
    """Independent per-element A(tau) straight off the boxed §31.2 equation.

    Uses plain ``math.exp`` (the module uses ``np.expm1``), so agreement is a genuine
    cross-check of the implementation, not a tautology.
    """
    k = p.kappa
    return (
        (p.mu_xi - p.lambda_xi) * tau
        - (p.lambda_chi / k) * (1.0 - math.exp(-k * tau))
        + 0.5
        * (
            p.sigma_chi**2 / (2.0 * k) * (1.0 - math.exp(-2.0 * k * tau))
            + p.sigma_xi**2 * tau
            + 2.0 * p.rho * p.sigma_chi * p.sigma_xi / k * (1.0 - math.exp(-k * tau))
        )
    )


def _exact_transition_moments(
    p: SchwartzSmithParams, dt: float
) -> tuple[float, float, float, float, float]:
    """Exact one-step Q moments ``(E-decay, chi drift, Var chi, Var xi, Cov)`` for testing.

    Written out independently from the OU / arithmetic-BM solutions rather than imported
    from the module under test.
    """
    k = p.kappa
    decay = math.exp(-k * dt)
    drift_chi = -(p.lambda_chi / k) * (1.0 - decay)
    var_chi = p.sigma_chi**2 * (1.0 - math.exp(-2.0 * k * dt)) / (2.0 * k)
    var_xi = p.sigma_xi**2 * dt
    cov = p.rho * p.sigma_chi * p.sigma_xi * (1.0 - decay) / k
    return decay, drift_chi, var_chi, var_xi, cov


# --- SchwartzSmithParams validation (Req 11.5) ------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("kappa", 0.0, "kappa"),
        ("kappa", -1.0, "kappa"),
        ("sigma_chi", 0.0, "sigma_chi"),
        ("sigma_chi", -0.2, "sigma_chi"),
        ("sigma_xi", 0.0, "sigma_xi"),
        ("rho", 1.0, "rho"),
        ("rho", -1.0, "rho"),
        ("rho", 1.5, "rho"),
        ("mu_xi", math.nan, "mu_xi"),
        ("lambda_chi", math.inf, "lambda_chi"),
        ("lambda_xi", -math.inf, "lambda_xi"),
    ],
)
def test_params_validation_names_parameter(field: str, value: float, match: str) -> None:
    kwargs = {
        "kappa": 1.0,
        "sigma_chi": 0.3,
        "sigma_xi": 0.15,
        "mu_xi": 0.02,
        "rho": 0.0,
        "lambda_chi": 0.0,
        "lambda_xi": 0.0,
    }
    kwargs[field] = value
    with pytest.raises(ValidationError, match=match):
        SchwartzSmithParams(**kwargs)  # type: ignore[arg-type]


def test_mu_xi_star_is_risk_neutral_drift() -> None:
    assert _PARAMS.mu_xi_star == pytest.approx(_PARAMS.mu_xi - _PARAMS.lambda_xi)


# --- Property 69: closed form vs independent reference ----------------------------


def test_forward_curve_matches_independent_reference() -> None:
    chi, xi, t = 0.25, 3.1, 0.5
    maturities = np.array([0.5, 0.75, 1.0, 1.5, 2.5, 4.0])
    expected = np.array(
        [
            math.exp(
                math.exp(-_PARAMS.kappa * (m - t)) * chi + xi + _a_tau_reference(_PARAMS, m - t)
            )
            for m in maturities
        ]
    )
    got = forward_curve(_PARAMS, chi, xi, t, maturities)
    assert got == pytest.approx(expected, rel=1e-12)


def test_forward_curve_second_parameter_set() -> None:
    # A different (positive-rho, slow-reversion) parameter set against the same reference.
    p = SchwartzSmithParams(
        kappa=0.4,
        sigma_chi=0.5,
        sigma_xi=0.1,
        mu_xi=-0.01,
        rho=0.6,
        lambda_chi=-0.02,
        lambda_xi=0.03,
    )
    chi, xi = -0.4, 2.0
    maturities = np.array([0.1, 1.0, 5.0, 10.0])
    expected = np.array(
        [math.exp(math.exp(-p.kappa * m) * chi + xi + _a_tau_reference(p, m)) for m in maturities]
    )
    assert forward_curve(p, chi, xi, 0.0, maturities) == pytest.approx(expected, rel=1e-12)


def test_zero_tenor_forward_is_spot() -> None:
    # A(0) = 0 exactly, so F(t, t) = exp(chi + xi) = S_t (§31.1 decomposition).
    chi, xi = 0.3, 2.5
    got = forward_curve(_PARAMS, chi, xi, 1.0, np.array([1.0]))
    assert got[0] == pytest.approx(math.exp(chi + xi), rel=1e-14)


def test_log_forward_is_log_of_forward() -> None:
    maturities = np.array([0.5, 1.0, 2.0])
    log_f = log_forward_curve(_PARAMS, 0.2, 3.0, 0.0, maturities)
    f = forward_curve(_PARAMS, 0.2, 3.0, 0.0, maturities)
    assert np.log(f) == pytest.approx(log_f, abs=1e-14)


# --- Property 70: short-factor decay as kappa*tau -> inf ---------------------------


def test_long_tenor_forwards_insensitive_to_chi() -> None:
    # At kappa*tau = 30 the loading e^(-30) ~ 9e-14: chi = +5 vs chi = 0 is indistinguishable.
    far = np.array([30.0 / _PARAMS.kappa])
    with_chi = log_forward_curve(_PARAMS, 5.0, 3.0, 0.0, far)
    without_chi = log_forward_curve(_PARAMS, 0.0, 3.0, 0.0, far)
    assert abs(with_chi[0] - without_chi[0]) < 1e-10


def test_chi_sensitivity_decays_monotonically_at_rate_kappa() -> None:
    maturities = np.array([0.5, 1.0, 2.0, 4.0, 8.0])
    delta = log_forward_curve(_PARAMS, 1.0, 3.0, 0.0, maturities) - log_forward_curve(
        _PARAMS, 0.0, 3.0, 0.0, maturities
    )
    assert np.all(np.diff(delta) < 0.0), "chi sensitivity must decay with tenor"
    assert delta == pytest.approx(np.exp(-_PARAMS.kappa * maturities), rel=1e-12)


# --- forward_curve input validation ------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"chi": math.nan}, "chi"),
        ({"xi": math.inf}, "xi"),
        ({"t": math.nan}, "t must be finite"),
        ({"tenors": np.array([])}, "tenors"),
        ({"tenors": np.array([[1.0]])}, "tenors"),
        ({"tenors": np.array([math.nan])}, "tenors"),
        ({"t": 2.0, "tenors": np.array([1.0])}, "tenor"),  # maturity before valuation time
    ],
)
def test_forward_curve_validation(kwargs: dict[str, object], match: str) -> None:
    defaults: dict[str, object] = {"chi": 0.1, "xi": 3.0, "t": 0.0, "tenors": np.array([1.0])}
    defaults.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        forward_curve(_PARAMS, **defaults)  # type: ignore[arg-type]


# --- simulate: determinism, shape, exact moments (Req 25.6 / 11.2) -----------------


def test_simulate_deterministic_under_seed() -> None:
    a = simulate(_PARAMS, 0.2, 3.0, 1 / 52, steps=10, path_count=64, seed=42)
    b = simulate(_PARAMS, 0.2, 3.0, 1 / 52, steps=10, path_count=64, seed=42)
    assert np.array_equal(a, b), "identical seed must give bit-identical paths"
    c = simulate(_PARAMS, 0.2, 3.0, 1 / 52, steps=10, path_count=64, seed=43)
    assert not np.array_equal(a, c), "different seed must give different paths"


def test_simulate_shape_and_initial_record() -> None:
    paths = simulate(_PARAMS, 0.2, 3.0, 1 / 12, steps=6, path_count=17, seed=1)
    assert paths.shape == (17, 7, 2)
    assert np.all(paths[:, 0, 0] == 0.2)
    assert np.all(paths[:, 0, 1] == 3.0)


def test_simulate_moments_match_ou_and_bm_closed_forms() -> None:
    """MC moments vs theoretical moments (independent cross-check, loose tol, fixed seed).

    Over horizon T: E[chi_T] = e^(-kT)*chi0 - (l_chi/k)(1 - e^(-kT)) (decay toward the
    Q-mean at rate kappa), Var[chi_T] = s_chi^2 (1 - e^(-2kT))/(2k);
    E[xi_T] = xi0 + mu_xi_star*T, Var[xi_T] = s_xi^2 T.
    """
    chi0, xi0, dt, steps, n_paths = 0.5, 3.0, 0.02, 25, 20_000
    horizon = dt * steps
    paths = simulate(_PARAMS, chi0, xi0, dt, steps, n_paths, seed=7)
    chi_final, xi_final = paths[:, -1, 0], paths[:, -1, 1]

    k = _PARAMS.kappa
    e_chi = math.exp(-k * horizon) * chi0 - (_PARAMS.lambda_chi / k) * (1 - math.exp(-k * horizon))
    v_chi = _PARAMS.sigma_chi**2 * (1 - math.exp(-2 * k * horizon)) / (2 * k)
    e_xi = xi0 + _PARAMS.mu_xi_star * horizon
    v_xi = _PARAMS.sigma_xi**2 * horizon

    assert float(np.mean(chi_final)) == pytest.approx(e_chi, abs=4 * math.sqrt(v_chi / n_paths))
    assert float(np.mean(xi_final)) == pytest.approx(e_xi, abs=4 * math.sqrt(v_xi / n_paths))
    assert float(np.var(chi_final)) == pytest.approx(v_chi, rel=0.05)
    assert float(np.var(xi_final)) == pytest.approx(v_xi, rel=0.05)


def test_simulate_one_step_innovation_correlation() -> None:
    # The joint step draws correlated shocks; the innovation correlation implied by the
    # exact one-step covariances must be reproduced (loose tol, fixed seed).
    dt = 1 / 52
    decay, drift_chi, v_chi, v_xi, cov = _exact_transition_moments(_PARAMS, dt)
    paths = simulate(_PARAMS, 0.2, 3.0, dt, steps=20, path_count=5_000, seed=11)
    eps_chi = paths[:, 1:, 0] - decay * paths[:, :-1, 0] - drift_chi
    eps_xi = paths[:, 1:, 1] - paths[:, :-1, 1] - _PARAMS.mu_xi_star * dt
    got = float(np.corrcoef(eps_chi.ravel(), eps_xi.ravel())[0, 1])
    expected = cov / math.sqrt(v_chi * v_xi)
    assert got == pytest.approx(expected, abs=0.03)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"dt": 0.0}, "dt"),
        ({"dt": -1.0}, "dt"),
        ({"chi0": math.nan}, "chi0"),
        ({"xi0": math.inf}, "xi0"),
        ({"steps": 0}, "steps"),
        ({"path_count": 0}, "path_count"),
        ({"seed": -1}, "seed"),
    ],
)
def test_simulate_validation(kwargs: dict[str, object], match: str) -> None:
    defaults: dict[str, object] = {
        "chi0": 0.1,
        "xi0": 3.0,
        "dt": 1 / 52,
        "steps": 2,
        "path_count": 2,
        "seed": 0,
    }
    defaults.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        simulate(_PARAMS, **defaults)  # type: ignore[arg-type]


# --- Property 70: calibration round-trip (Req 25.2, 25.6) ---------------------------


def _synthetic_history(
    p: SchwartzSmithParams,
    n_obs: int,
    tau: np.ndarray,
    dt: float,
    seed: int,
    meas_sigma: float = 0.005,
) -> np.ndarray:
    """Simulate an observed forward-curve history from known parameters.

    The latent factors evolve under the physical measure P (chi reverts to 0, xi drifts at
    mu_xi) and each date's curve is the Q closed form plus iid measurement noise — exactly
    the state-space model `calibrate` assumes, built independently in the test.
    """
    rng = np.random.default_rng(seed)
    decay, _, v_chi, v_xi, cov = _exact_transition_moments(p, dt)
    chol = np.linalg.cholesky(np.array([[v_chi, cov], [cov, v_xi]]))
    chi = np.zeros(n_obs)
    xi = np.zeros(n_obs)
    chi[0], xi[0] = 0.2, 3.0
    for n in range(1, n_obs):
        w = chol @ rng.standard_normal(2)
        chi[n] = decay * chi[n - 1] + w[0]  # P-dynamics: no risk-premium drift
        xi[n] = xi[n - 1] + p.mu_xi * dt + w[1]
    log_curves = np.array(
        [log_forward_curve(p, chi[n], xi[n], 0.0, tau) for n in range(n_obs)]
    ) + meas_sigma * rng.standard_normal((n_obs, tau.size))
    return np.exp(log_curves)


@pytest.fixture(scope="module")
def roundtrip() -> tuple[SchwartzSmithParams, SchwartzSmithParams, CalibrationDiagnostics]:
    """The single expensive calibration: 90 weekly curves x 5 tenors from known params."""
    tau = np.linspace(1 / 12, 3.0, 5)
    observed = _synthetic_history(_PARAMS, n_obs=90, tau=tau, dt=1 / 52, seed=11)
    fitted, diagnostics = calibrate(observed, tau, dt=1 / 52)
    return _PARAMS, fitted, diagnostics


def test_calibration_recovers_identified_parameters(
    roundtrip: tuple[SchwartzSmithParams, SchwartzSmithParams, CalibrationDiagnostics],
) -> None:
    """Documented loose tolerances (90 weekly obs): the diffusion/reversion parameters and
    the risk-neutral drift combination are identified; observed recovery at seed 11 is
    kappa ~2%, sigma_chi ~7%, sigma_xi ~12%, rho abs ~0.03, mu_xi_star abs ~0.004."""
    true, fitted, _ = roundtrip
    assert fitted.kappa == pytest.approx(true.kappa, rel=0.15)
    assert fitted.sigma_chi == pytest.approx(true.sigma_chi, rel=0.20)
    assert fitted.sigma_xi == pytest.approx(true.sigma_xi, rel=0.25)
    assert fitted.rho == pytest.approx(true.rho, abs=0.20)
    assert fitted.mu_xi_star == pytest.approx(true.mu_xi_star, abs=0.03)


def test_calibration_reports_diagnostics(
    roundtrip: tuple[SchwartzSmithParams, SchwartzSmithParams, CalibrationDiagnostics],
) -> None:
    _, _, diag = roundtrip
    assert diag.converged
    assert math.isfinite(diag.log_likelihood)
    assert diag.n_iterations > 0
    assert diag.residual_rmse < 0.02, "filtered log-price residuals should be near meas noise"
    assert 0.001 < diag.measurement_sigma < 0.05  # true value 0.005
    assert set(diag.param_std_errors) == {
        "kappa",
        "sigma_chi",
        "sigma_xi",
        "mu_xi",
        "rho",
        "lambda_chi",
        "lambda_xi",
    }
    # The diffusion parameters are sharply identified; their SEs must be finite.
    for name in ("kappa", "sigma_chi", "sigma_xi", "rho"):
        assert math.isfinite(diag.param_std_errors[name]), f"{name} SE must be finite"
    assert "power" in diag.lognormal_power_caveat.lower()  # Req 25.5 caveat
    assert math.isfinite(diag.initial_curve_max_abs_mismatch)


# --- Req 25.5: initial-curve mismatch flag + determinism ---------------------------


def _humped_history() -> tuple[np.ndarray, np.ndarray, float]:
    """Deliberately inconsistent curves: a strong seasonal hump in tenor that no
    two-factor (chi, xi) curve — monotone-ish in tau — can reproduce."""
    tau = np.array([0.25, 0.5, 0.75, 1.0])
    hump = 0.4 * np.sin(2.0 * math.pi * tau)
    rng = np.random.default_rng(5)
    levels = 3.0 + 0.01 * rng.standard_normal(12).cumsum()
    log_curves = levels[:, None] + hump[None, :] + 0.002 * rng.standard_normal((12, tau.size))
    return np.exp(log_curves), tau, 1 / 52


def test_initial_curve_mismatch_flag_fires_on_inconsistent_input() -> None:
    observed, tau, dt = _humped_history()
    _, diag = calibrate(observed, tau, dt)
    assert not diag.fits_initial_curve
    assert diag.initial_curve_max_abs_mismatch > 0.05, (
        "a 0.4 log-price seasonal hump cannot be matched by the two-factor closed form"
    )


def test_calibrate_deterministic() -> None:
    observed, tau, dt = _humped_history()
    fit_a, diag_a = calibrate(observed, tau, dt)
    fit_b, diag_b = calibrate(observed, tau, dt)
    assert fit_a == fit_b
    assert diag_a.log_likelihood == diag_b.log_likelihood


# --- calibrate input validation ----------------------------------------------------


def test_calibrate_validation_paths() -> None:
    observed = np.full((5, 3), 20.0)
    tau = np.array([0.25, 0.5, 1.0])
    with pytest.raises(ValidationError, match="dt"):
        calibrate(observed, tau, dt=0.0)
    with pytest.raises(ValidationError, match="observed_forwards"):
        calibrate(np.full((5, 3, 1), 20.0), tau, dt=1 / 52)
    with pytest.raises(ValidationError, match="observed_forwards"):
        calibrate(np.full((5, 3), -1.0), tau, dt=1 / 52)  # non-positive prices
    with pytest.raises(ValidationError, match="time_to_maturity"):
        calibrate(observed, np.array([0.25, 0.5]), dt=1 / 52)  # shape mismatch
    with pytest.raises(ValidationError, match="time_to_maturity"):
        calibrate(observed, np.array([0.25, 0.5, -1.0]), dt=1 / 52)  # negative tau
    with pytest.raises(InsufficientDataError, match="3 observation dates"):
        calibrate(observed[:2], tau, dt=1 / 52)


# --- new keyword-only parameters: initial_curve_tol, diffuse_prior_var, optimizer_method


def test_new_keyword_defaults_match_hardcoded_behaviour() -> None:
    observed, tau, dt = _humped_history()
    baseline_params, baseline_diag = calibrate(observed, tau, dt)
    explicit_params, explicit_diag = calibrate(
        observed,
        tau,
        dt,
        initial_curve_tol=1e-6,
        diffuse_prior_var=10.0,
        optimizer_method="L-BFGS-B",
    )
    assert explicit_params == baseline_params
    assert explicit_diag == baseline_diag


def test_initial_curve_tol_override_can_flip_fits_initial_curve() -> None:
    observed, tau, dt = _humped_history()
    _, baseline_diag = calibrate(observed, tau, dt)
    assert not baseline_diag.fits_initial_curve
    # Widen the tolerance past the reported mismatch: now it "fits".
    _, widened_diag = calibrate(
        observed, tau, dt, initial_curve_tol=baseline_diag.initial_curve_max_abs_mismatch * 2.0
    )
    assert widened_diag.fits_initial_curve


def test_initial_curve_tol_must_be_positive() -> None:
    observed, tau, dt = _humped_history()
    with pytest.raises(ValidationError, match="initial_curve_tol"):
        calibrate(observed, tau, dt, initial_curve_tol=0.0)


def test_diffuse_prior_var_override_changes_fit() -> None:
    observed, tau, dt = _humped_history()
    baseline_params, _ = calibrate(observed, tau, dt)
    changed_params, _ = calibrate(observed, tau, dt, diffuse_prior_var=1e-3)
    assert changed_params != baseline_params


def test_diffuse_prior_var_must_be_positive() -> None:
    observed, tau, dt = _humped_history()
    with pytest.raises(ValidationError, match="diffuse_prior_var"):
        calibrate(observed, tau, dt, diffuse_prior_var=0.0)


def test_optimizer_method_override_still_converges() -> None:
    observed, tau, dt = _humped_history()
    _, diag = calibrate(observed, tau, dt, optimizer_method="Nelder-Mead", max_iter=2000)
    assert math.isfinite(diag.log_likelihood)


def test_optimizer_method_empty_string_rejected() -> None:
    observed, tau, dt = _humped_history()
    with pytest.raises(ValidationError, match="optimizer_method"):
        calibrate(observed, tau, dt, optimizer_method="")


def test_optimizer_method_without_nit_attribute_falls_back_to_nfev() -> None:
    """Regression: COBYLA's scipy.optimize.OptimizeResult carries no ``nit``
    attribute at all (unlike gradient-based methods), so ``int(result.nit)``
    raised ``AttributeError`` after an otherwise-successful calibration.
    ``n_iterations`` must fall back to ``result.nfev`` instead.
    """
    observed, tau, dt = _humped_history()
    _, diag = calibrate(observed, tau, dt, optimizer_method="COBYLA", max_iter=2000)
    assert math.isfinite(diag.log_likelihood)
    assert diag.n_iterations > 0
