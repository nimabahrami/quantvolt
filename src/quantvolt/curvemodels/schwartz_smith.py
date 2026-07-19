"""Two-factor Schwartz-Smith forward-curve model.

The log spot price is split into a short-term mean-reverting deviation ``chi`` and a
long-term random-walk level ``xi``::

    ln S_t = chi_t + xi_t

Under the risk-neutral measure Q the factors follow::

    d chi_t = (-kappa*chi_t - lambda_chi) dt + sigma_chi dW_chi^Q          (mean-reverting)
    d  xi_t = (mu_xi - lambda_xi)          dt + sigma_xi  dW_xi^Q          (random walk)
    dW_chi^Q dW_xi^Q = rho dt

``lambda_chi`` and ``lambda_xi`` are risk-premium adjustments, so ``mu_xi - lambda_xi``
is the risk-neutral long-term drift (exposed as :attr:`SchwartzSmithParams.mu_xi_star`).

Because forward prices are Q-expectations of the spot, the integrated forward curve has the
closed form of the Schwartz-Smith forward curve equation, with ``tau = T - t``::

    F(t, T) = exp[ e^(-kappa*tau)*chi_t + xi_t + A(tau) ]

    A(tau) = (mu_xi - lambda_xi)*tau - (lambda_chi/kappa)*(1 - e^(-kappa*tau))
             + 0.5*[ sigma_chi^2/(2 kappa)*(1 - e^(-2 kappa*tau))
                     + sigma_xi^2*tau
                     + 2 rho sigma_chi sigma_xi/kappa*(1 - e^(-kappa*tau)) ]

This module implements ``A(tau)`` verbatim (``_a_tau``) and exposes:

* ``forward_curve`` / ``log_forward_curve``: the closed form above.
  As ``kappa*tau -> inf`` the short-factor loading ``e^(-kappa*tau) -> 0``, so long-dated
  forwards depend only on ``xi`` and ``A(tau)``.
* ``simulate``: exact joint discretisation of the (chi, xi) dynamics under Q, deterministic
  under a given seed.
* ``calibrate``: a hand-rolled linear-Gaussian Kalman filter over the latent
  (chi, xi), fitted by Gaussian maximum likelihood, returning parameters + diagnostics and
  flagging any initial-curve mismatch.

Measure discipline. ``forward_curve`` and ``simulate`` use the risk-neutral
dynamics under measure Q. In ``calibrate`` the measurement equation is the Q
closed form (``A(tau)`` carries ``lambda_chi``/``lambda_xi``), while the transition of the
latent state is under the physical measure P (``chi`` reverts to 0, ``xi`` drifts at
``mu_xi``): the standard Schwartz-Smith state-space split of P-dynamics from a Q-priced
cross-section. The risk premia are what map one to the other and are identified only through
the cross-sectional shape of ``A(tau)``.

Caveat. Lognormal forward models are not automatically appropriate for
spiky power prices, and the two-factor model does not fit an arbitrary initial forward curve
exactly; ``calibrate`` reports the residual mismatch rather than hiding it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import minimize  # type: ignore[import-untyped]

from .._validation import require_correlation, require_positive
from ..exceptions import InsufficientDataError, ValidationError

_LOGNORMAL_POWER_CAVEAT = (
    "Lognormal Schwartz-Smith forwards are not automatically appropriate for spiky power "
    "prices (§31.3); assess suitability per commodity. The two-factor model also does not "
    "fit an arbitrary initial forward curve exactly."
)
# The filtered initial curve is deemed an exact match only within this (log-price) tolerance.
_INITIAL_CURVE_TOL = 1e-6
# Diffuse prior variance for the non-stationary long-term factor xi in the Kalman filter.
_DIFFUSE_VAR = 10.0
# Ordered parameter names for diagnostics (matches the calibration state vector).
_PARAM_NAMES = ("kappa", "sigma_chi", "sigma_xi", "mu_xi", "rho", "lambda_chi", "lambda_xi")

__all__ = [
    "CalibrationDiagnostics",
    "SchwartzSmithParams",
    "calibrate",
    "forward_curve",
    "log_forward_curve",
    "simulate",
]


@dataclass(frozen=True, slots=True)
class SchwartzSmithParams:
    """Risk-neutral parameters of the two-factor Schwartz-Smith model.

    * ``kappa`` — short-factor mean-reversion speed (``> 0``).
    * ``sigma_chi`` — short-factor volatility (``> 0``).
    * ``sigma_xi`` — long-factor volatility (``> 0``).
    * ``mu_xi`` — physical long-term drift of ``xi`` (unconstrained).
    * ``rho`` — instantaneous correlation of the two Brownian factors, ``in (-1, 1)``.
    * ``lambda_chi`` — short-factor risk premium (unconstrained).
    * ``lambda_xi`` — long-factor risk premium (unconstrained).

    ``mu_xi_star`` = ``mu_xi - lambda_xi`` is the risk-neutral long-term drift that
    enters the forward curve.
    """

    kappa: float
    sigma_chi: float
    sigma_xi: float
    mu_xi: float
    rho: float
    lambda_chi: float
    lambda_xi: float

    def __post_init__(self) -> None:
        require_positive("kappa", self.kappa)
        require_positive("sigma_chi", self.sigma_chi)
        require_positive("sigma_xi", self.sigma_xi)
        require_correlation("rho", self.rho)
        for name in ("mu_xi", "lambda_chi", "lambda_xi"):
            value = getattr(self, name)
            if not math.isfinite(value):
                raise ValidationError(f"{name} must be finite, got {value!r}")

    @property
    def mu_xi_star(self) -> float:
        """Risk-neutral long-term drift ``mu_xi - lambda_xi`` (the drift entering ``A(tau)``)."""
        return self.mu_xi - self.lambda_xi


def _a_tau(params: SchwartzSmithParams, tau: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """The closed-form ``A(tau)`` of the Schwartz-Smith forward curve equation.

    ``1 - e^(-k*tau)`` and ``1 - e^(-2 k*tau)`` are evaluated with :func:`numpy.expm1`
    (``1 - e^x = -expm1(x)``) so the ``tau -> 0`` limit ``A(0) = 0`` is exact.
    """
    k = params.kappa
    one_minus_e = -np.expm1(-k * tau)  # 1 - e^(-k*tau)
    one_minus_e2 = -np.expm1(-2.0 * k * tau)  # 1 - e^(-2 k*tau)
    return (
        params.mu_xi_star * tau
        - (params.lambda_chi / k) * one_minus_e
        + 0.5
        * (
            params.sigma_chi**2 / (2.0 * k) * one_minus_e2
            + params.sigma_xi**2 * tau
            + 2.0 * params.rho * params.sigma_chi * params.sigma_xi / k * one_minus_e
        )
    )


def _time_to_maturity(t: float, tenors: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Return ``tau = T - t`` for maturities ``tenors`` (absolute times ``T``, in years).

    Validates that ``t`` is finite and every ``tau >= 0`` (no past maturities), raising
    :class:`ValidationError` naming the violation.
    """
    if not math.isfinite(t):
        raise ValidationError(f"t must be finite, got {t!r}")
    maturities = np.ascontiguousarray(tenors, dtype=np.float64)
    if maturities.ndim != 1 or maturities.size == 0:
        raise ValidationError(f"tenors must be a non-empty 1-D array, got shape {maturities.shape}")
    if not bool(np.all(np.isfinite(maturities))):
        raise ValidationError("tenors must be finite")
    tau = maturities - t
    if bool(np.any(tau < 0.0)):
        raise ValidationError(
            f"every tenor (maturity T) must satisfy T >= t = {t!r}; got a negative tau = T - t"
        )
    return tau


def log_forward_curve(
    params: SchwartzSmithParams,
    chi: float,
    xi: float,
    t: float,
    tenors: npt.ArrayLike,
) -> npt.NDArray[np.float64]:
    """Log-forward curve ``ln F(t, T) = e^(-kappa*tau)*chi + xi + A(tau)``, ``tau = T - t``.

    This is the measurement space of the model (linear in the latent factors), so the
    short-factor loading ``e^(-kappa*tau)`` is exposed directly: as ``kappa*tau -> inf`` it
    decays to 0 and the long-dated log-forward depends only on ``xi`` and ``A(tau)``.

    Args:
        params: Risk-neutral model parameters.
        chi: Short-term factor value ``chi_t`` at valuation time ``t``.
        xi: Long-term factor value ``xi_t`` at valuation time ``t``.
        t: Valuation time in years.
        tenors: 1-D array of **maturities ``T``** (absolute times in years); ``tau = T - t``
            must be non-negative for every entry.

    Returns:
        A ``float64`` array of log-forward prices aligned with ``tenors``.
    """
    if not math.isfinite(chi) or not math.isfinite(xi):
        raise ValidationError(f"chi and xi must be finite, got chi={chi!r}, xi={xi!r}")
    tau = _time_to_maturity(t, tenors)
    loading = np.exp(-params.kappa * tau)
    return loading * chi + xi + _a_tau(params, tau)


def forward_curve(
    params: SchwartzSmithParams,
    chi: float,
    xi: float,
    t: float,
    tenors: npt.ArrayLike,
) -> npt.NDArray[np.float64]:
    """Closed-form forward curve ``F(t, T) = exp[e^(-kappa*tau)*chi + xi + A(tau)]``.

    The lightest faithful surface: a ``float64`` array of forward prices
    ``F(t, T)`` aligned with ``tenors``. No ``quantvolt.models.ForwardCurve`` is built
    because this signature carries no commodity/delivery-period context; the caller wraps the
    result if a full curve object is wanted.

    See :func:`log_forward_curve` for argument semantics (``tenors`` are maturities ``T``).
    """
    return np.exp(log_forward_curve(params, chi, xi, t, tenors))


def _transition_covariance(params: SchwartzSmithParams, dt: float) -> npt.NDArray[np.float64]:
    """Exact one-step (integrated) covariance of the (chi, xi) increments over ``dt``.

    From the exact solutions of the OU and arithmetic-BM factors (diffusion is
    measure-invariant, so this holds under both P and Q)::

        Var(chi) = sigma_chi^2*(1 - e^(-2 kappa dt))/(2 kappa)
        Var(xi)  = sigma_xi^2*dt
        Cov      = rho*sigma_chi*sigma_xi*(1 - e^(-kappa dt))/kappa
    """
    k = params.kappa
    var_chi = params.sigma_chi**2 * (-math.expm1(-2.0 * k * dt)) / (2.0 * k)
    var_xi = params.sigma_xi**2 * dt
    cov = params.rho * params.sigma_chi * params.sigma_xi * (-math.expm1(-k * dt)) / k
    return np.array([[var_chi, cov], [cov, var_xi]], dtype=np.float64)


def simulate(
    params: SchwartzSmithParams,
    chi0: float,
    xi0: float,
    dt: float,
    steps: int,
    path_count: int,
    seed: int,
) -> npt.NDArray[np.float64]:
    """Simulate the joint (chi, xi) factor paths under Q by exact discretisation.

    The short factor is an Ornstein-Uhlenbeck process and the long factor an arithmetic
    Brownian motion; the **exact** joint transition over a step ``dt`` is::

        chi_{n+1} = e^(-kappa*dt)*chi_n - (lambda_chi/kappa)*(1 - e^(-kappa*dt)) + eps_chi
        xi_{n+1}  = xi_n + (mu_xi - lambda_xi)*dt + eps_xi
        (eps_chi, eps_xi) ~ N(0, Q)     # Q from `_transition_covariance`

    The correlated innovations are sampled jointly from the exact transition covariance.
    This gives an exact discretisation for any ``dt`` and deterministic paths for a fixed
    ``seed``.

    Args:
        params: Risk-neutral model parameters.
        chi0: Initial short-term factor value.
        xi0: Initial long-term factor value.
        dt: Step length in years (``> 0``).
        steps: Number of steps (``>= 1``).
        path_count: Number of paths (``>= 1``).
        seed: Non-negative RNG seed. Repeated calls with the same inputs, seed,
            QuantVolt version, architecture and native build give identical paths.

    Returns:
        A ``float64`` array of shape ``(path_count, steps + 1, 2)``.
        ``[:, :, 0]`` is ``chi``, ``[:, :, 1]`` is ``xi``; record 0 of every
        path is ``(chi0, xi0)``.
    """
    require_positive("dt", dt)
    if not math.isfinite(chi0) or not math.isfinite(xi0):
        raise ValidationError(f"chi0 and xi0 must be finite, got chi0={chi0!r}, xi0={xi0!r}")
    if steps < 1:
        raise ValidationError(f"steps must be >= 1, got {steps}")
    if path_count < 1:
        raise ValidationError(f"path_count must be >= 1, got {path_count}")
    if seed < 0:
        raise ValidationError(f"seed must be a non-negative integer, got {seed}")

    decay = math.exp(-params.kappa * dt)
    drift_chi = -(params.lambda_chi / params.kappa) * (1.0 - decay)
    drift_xi = params.mu_xi_star * dt
    chol = np.linalg.cholesky(_transition_covariance(params, dt))

    rng = np.random.default_rng(seed)
    # Draw all shocks up front, then apply the correlation via the Cholesky factor.
    shocks = rng.standard_normal((steps, path_count, 2)) @ chol.T

    out = np.empty((path_count, steps + 1, 2), dtype=np.float64)
    out[:, 0, 0] = chi0
    out[:, 0, 1] = xi0
    for n in range(steps):
        out[:, n + 1, 0] = decay * out[:, n, 0] + drift_chi + shocks[n, :, 0]
        out[:, n + 1, 1] = out[:, n, 1] + drift_xi + shocks[n, :, 1]
    return out


@dataclass(frozen=True, slots=True)
class CalibrationDiagnostics:
    """Fit diagnostics returned alongside calibrated :class:`SchwartzSmithParams`.

    * ``converged`` / ``optimizer_message`` / ``n_iterations`` — MLE termination status.
      ``n_iterations`` is ``result.nit`` when the chosen ``optimizer_method`` reports it;
      methods that don't (e.g. COBYLA has no ``nit`` attribute at all) fall back to
      ``result.nfev`` (the function-evaluation count) as the nearest available proxy for
      how much optimizer work occurred before termination.
    * ``log_likelihood`` — maximised Gaussian log-likelihood (prediction-error decomposition).
    * ``gradient_norm`` — ``||grad NLL||`` at the optimum (near 0 at a good stationary point).
    * ``hessian_condition_number`` — condition number of the observed information; large values
      warn of weakly identified parameters (typically the drift/risk-premium terms).
    * ``param_std_errors`` — asymptotic MLE standard errors keyed by parameter name (``nan``
      where the information matrix is singular, i.e. the parameter is not identified).
    * ``measurement_sigma`` — fitted per-tenor log-price measurement-noise standard deviation.
    * ``filtered_initial_state`` — filtered ``(chi_0, xi_0)`` at the first observation date.
    * ``residual_rmse`` — RMSE of the log-price measurement residuals (filtered fit).
    * ``initial_curve_max_abs_mismatch`` — max ``|model - observed|`` log-forward at the first
      date; ``fits_initial_curve`` is ``True`` only if it is within tolerance.
    * ``lognormal_power_caveat`` — the lognormal-vs-spiky-power suitability warning.
    """

    converged: bool
    optimizer_message: str
    n_iterations: int
    log_likelihood: float
    gradient_norm: float
    hessian_condition_number: float
    param_std_errors: dict[str, float]
    measurement_sigma: float
    filtered_initial_state: tuple[float, float]
    residual_rmse: float
    initial_curve_max_abs_mismatch: float
    fits_initial_curve: bool
    lognormal_power_caveat: str


def _unpack(theta: npt.NDArray[np.float64]) -> tuple[SchwartzSmithParams, float]:
    """Map the unconstrained optimiser vector to (params, measurement_sigma).

    Transforms keep the domains: ``exp`` for the strictly-positive scales, ``tanh`` for
    ``rho in (-1, 1)``, identity for the unconstrained drifts/premia.
    """
    kappa = math.exp(theta[0])
    sigma_chi = math.exp(theta[1])
    sigma_xi = math.exp(theta[2])
    mu_xi = float(theta[3])
    rho = math.tanh(theta[4])
    lambda_chi = float(theta[5])
    lambda_xi = float(theta[6])
    meas_sigma = math.exp(theta[7])
    params = SchwartzSmithParams(
        kappa=kappa,
        sigma_chi=sigma_chi,
        sigma_xi=sigma_xi,
        mu_xi=mu_xi,
        rho=rho,
        lambda_chi=lambda_chi,
        lambda_xi=lambda_xi,
    )
    return params, meas_sigma


def _kalman_filter(
    params: SchwartzSmithParams,
    meas_sigma: float,
    obs_log: npt.NDArray[np.float64],
    tau: npt.NDArray[np.float64],
    dt: float,
    diffuse_prior_var: float = _DIFFUSE_VAR,
) -> tuple[float, npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Run the linear-Gaussian Kalman filter; return (log-likelihood, filtered states, resid).

    State ``s = [chi, xi]``. Measurement (Q closed form)::

        y_n = design @ s_n + A(tau) + e_n,   e_n ~ N(0, meas_sigma^2 * I)
        design[j] = [e^(-kappa*tau_j), 1]

    Transition (physical measure P — the latent factors evolve under real-world dynamics)::

        s_n = trans @ s_{n-1} + [0, mu_xi*dt] + w_n,   w_n ~ N(0, Q)
        trans = diag(e^(-kappa*dt), 1)

    The Gaussian log-likelihood is accumulated by the prediction-error decomposition. The
    long-term factor is non-stationary, so it is given a diffuse prior of variance
    ``diffuse_prior_var``.
    """
    n_obs, n_tenors = obs_log.shape
    decay = math.exp(-params.kappa * dt)
    design = np.column_stack((np.exp(-params.kappa * tau), np.ones(n_tenors)))
    intercept = _a_tau(params, tau)
    trans = np.array([[decay, 0.0], [0.0, 1.0]], dtype=np.float64)
    trans_intercept = np.array([0.0, params.mu_xi * dt], dtype=np.float64)
    q_cov = _transition_covariance(params, dt)
    h_cov = meas_sigma**2 * np.eye(n_tenors)

    # Prior: chi at its stationary mean 0, xi diffuse around the first curve's average level.
    state = np.array([0.0, float(np.mean(obs_log[0] - intercept))], dtype=np.float64)
    cov = np.array(
        [[params.sigma_chi**2 / (2.0 * params.kappa), 0.0], [0.0, diffuse_prior_var]],
        dtype=np.float64,
    )

    log_lik = 0.0
    filtered = np.empty((n_obs, 2), dtype=np.float64)
    residuals = np.empty((n_obs, n_tenors), dtype=np.float64)
    two_pi = 2.0 * math.pi
    for n in range(n_obs):
        if n > 0:  # predict
            state = trans @ state + trans_intercept
            cov = trans @ cov @ trans.T + q_cov
        innovation = obs_log[n] - (design @ state + intercept)
        innovation_cov = design @ cov @ design.T + h_cov
        chol = np.linalg.cholesky(innovation_cov)
        solved = np.linalg.solve(chol, innovation)
        log_det = 2.0 * float(np.sum(np.log(np.diag(chol))))
        log_lik += -0.5 * (n_tenors * math.log(two_pi) + log_det + float(solved @ solved))
        gain = np.linalg.solve(innovation_cov, design @ cov).T  # cov @ design.T @ inv(S)
        state = state + gain @ innovation
        cov = cov - gain @ design @ cov
        filtered[n] = state
        residuals[n] = obs_log[n] - (design @ state + intercept)
    return log_lik, filtered, residuals


def _negloglik(
    theta: npt.NDArray[np.float64],
    obs_log: npt.NDArray[np.float64],
    tau: npt.NDArray[np.float64],
    dt: float,
    diffuse_prior_var: float = _DIFFUSE_VAR,
) -> float:
    """Negative Gaussian log-likelihood for the optimiser; ``+inf`` on any numerical failure."""
    try:
        params, meas_sigma = _unpack(theta)
        log_lik, _, _ = _kalman_filter(params, meas_sigma, obs_log, tau, dt, diffuse_prior_var)
    except (ValidationError, np.linalg.LinAlgError, ValueError, OverflowError):
        return math.inf
    if not math.isfinite(log_lik):
        return math.inf
    return -log_lik


def _initial_theta(obs_log: npt.NDArray[np.float64], dt: float) -> npt.NDArray[np.float64]:
    """Data-driven starting point for the optimiser (unconstrained space).

    Diffusions are seeded from the realised volatility of the long-tenor level and of the
    short-minus-long spread (a proxy for the mean-reverting factor); the rest use neutral
    defaults (``kappa = 1``, zero drifts/premia/correlation, small measurement noise).
    """
    sqrt_dt = math.sqrt(dt)
    long_changes = np.diff(obs_log[:, -1])
    spread_changes = np.diff(obs_log[:, 0] - obs_log[:, -1])
    sigma_xi = max(float(np.std(long_changes)) / sqrt_dt, 0.05) if long_changes.size else 0.2
    sigma_chi = max(float(np.std(spread_changes)) / sqrt_dt, 0.05) if spread_changes.size else 0.3
    return np.array(
        [math.log(1.0), math.log(sigma_chi), math.log(sigma_xi), 0.0, 0.0, 0.0, 0.0, math.log(0.01)]
    )


def _standard_errors(
    theta: npt.NDArray[np.float64],
    params: SchwartzSmithParams,
    obs_log: npt.NDArray[np.float64],
    tau: npt.NDArray[np.float64],
    dt: float,
    diffuse_prior_var: float = _DIFFUSE_VAR,
) -> tuple[dict[str, float], float]:
    """Asymptotic MLE standard errors of the natural parameters + Hessian condition number.

    A central-difference Hessian of the NLL is taken in the **natural** parameterisation at
    the optimum (the observed information). Its inverse diagonal gives the variances; a
    singular/indefinite information matrix (a weakly identified parameter) yields ``nan``
    rather than a fabricated precision.
    """
    natural = np.array(
        [
            params.kappa,
            params.sigma_chi,
            params.sigma_xi,
            params.mu_xi,
            params.rho,
            params.lambda_chi,
            params.lambda_xi,
            math.exp(theta[7]),
        ]
    )

    def nll_natural(vec: npt.NDArray[np.float64]) -> float:
        with np.errstate(all="ignore"):
            k, s_chi, s_xi, mu, r, l_chi, l_xi, meas = (float(v) for v in vec)
            if k <= 0 or s_chi <= 0 or s_xi <= 0 or meas <= 0 or not -1.0 < r < 1.0:
                return math.inf
            try:
                trial = SchwartzSmithParams(k, s_chi, s_xi, mu, r, l_chi, l_xi)
                log_lik, _, _ = _kalman_filter(trial, meas, obs_log, tau, dt, diffuse_prior_var)
            except (ValidationError, np.linalg.LinAlgError, ValueError):
                return math.inf
        return -log_lik if math.isfinite(log_lik) else math.inf

    n = natural.size
    step = np.maximum(np.abs(natural) * 1e-4, 1e-6)
    hessian = np.zeros((n, n))
    base = nll_natural(natural)
    for i in range(n):
        for j in range(i, n):
            ei = np.zeros(n)
            ej = np.zeros(n)
            ei[i] = step[i]
            ej[j] = step[j]
            if i == j:
                fp = nll_natural(natural + ei)
                fm = nll_natural(natural - ei)
                value = (fp - 2.0 * base + fm) / (step[i] ** 2)
            else:
                fpp = nll_natural(natural + ei + ej)
                fpm = nll_natural(natural + ei - ej)
                fmp = nll_natural(natural - ei + ej)
                fmm = nll_natural(natural - ei - ej)
                value = (fpp - fpm - fmp + fmm) / (4.0 * step[i] * step[j])
            hessian[i, j] = value
            hessian[j, i] = value

    errors = {name: math.nan for name in _PARAM_NAMES}
    condition = math.inf
    if bool(np.all(np.isfinite(hessian))):
        try:
            eig = np.linalg.eigvalsh(hessian)
            if eig[0] > 0:
                condition = float(eig[-1] / eig[0])
            cov = np.linalg.inv(hessian)
            variances = np.diag(cov)
            for idx, name in enumerate(_PARAM_NAMES):
                var = float(variances[idx])
                errors[name] = math.sqrt(var) if var > 0 else math.nan
        except np.linalg.LinAlgError:
            pass
    return errors, condition


def calibrate(
    observed_forwards: npt.ArrayLike,
    time_to_maturity: npt.ArrayLike,
    dt: float,
    *,
    max_iter: int = 500,
    initial_curve_tol: float = _INITIAL_CURVE_TOL,
    diffuse_prior_var: float = _DIFFUSE_VAR,
    optimizer_method: str = "L-BFGS-B",
) -> tuple[SchwartzSmithParams, CalibrationDiagnostics]:
    """Calibrate the model from a history of observed forward curves.

    A linear-Gaussian Kalman filter (see :func:`_kalman_filter`) treats the latent
    ``(chi, xi)`` as the state and the log-forward cross-sections as measurements, and its
    prediction-error decomposition is maximised by :func:`scipy.optimize.minimize`
    (``optimizer_method``, default L-BFGS-B, over an unconstrained transform of the
    parameters).

    Args:
        observed_forwards: History of observed forward **prices**, shape
            ``(n_obs, n_tenors)`` — one row per observation date (chronological), one column
            per constant time-to-maturity. Must be strictly positive (logs are taken).
        time_to_maturity: 1-D array of the constant times-to-maturity ``tau`` (years) for the
            columns; the same ``tau`` applies to every observation date (a constant-maturity
            "rolling" curve history), so the measurement matrix is time-invariant.
        dt: Time between consecutive observation dates (years, ``> 0``).
        max_iter: Maximum optimiser iterations.
        initial_curve_tol: Log-price tolerance below which the filtered initial
            curve is deemed an exact match (``fits_initial_curve``), positive
            (default ``1e-6``).
        diffuse_prior_var: Diffuse prior variance for the non-stationary
            long-term factor ``xi`` in the Kalman filter, positive (default
            ``10.0``).
        optimizer_method: :func:`scipy.optimize.minimize` method name, a
            non-empty string (default ``"L-BFGS-B"``).

    Returns:
        ``(params, diagnostics)`` — the fitted :class:`SchwartzSmithParams` and a
        :class:`CalibrationDiagnostics`. The diagnostics flag any initial-curve mismatch
        and report identifiability via standard errors / Hessian conditioning.

    Raises:
        ValidationError: if ``dt <= 0``, ``initial_curve_tol <= 0``,
            ``diffuse_prior_var <= 0``, ``optimizer_method`` is empty, shapes are
            inconsistent, any ``tau`` is negative, any observed forward is
            non-positive, or the MLE fails to converge.
        InsufficientDataError: if fewer than three observation dates are supplied (the
            transition dynamics cannot be identified from fewer).
    """
    require_positive("dt", dt)
    require_positive("initial_curve_tol", initial_curve_tol)
    require_positive("diffuse_prior_var", diffuse_prior_var)
    if not optimizer_method:
        raise ValidationError(
            f"optimizer_method must be a non-empty string, got {optimizer_method!r}"
        )
    forwards = np.ascontiguousarray(observed_forwards, dtype=np.float64)
    tau = np.ascontiguousarray(time_to_maturity, dtype=np.float64)
    if forwards.ndim != 2:
        raise ValidationError(
            f"observed_forwards must be 2-D (n_obs, n_tenors), got shape {forwards.shape}"
        )
    n_obs, n_tenors = forwards.shape
    if n_obs < 3:
        raise InsufficientDataError(
            f"calibration needs at least 3 observation dates to identify the transition "
            f"dynamics, got {n_obs}"
        )
    if tau.shape != (n_tenors,):
        raise ValidationError(
            f"time_to_maturity must have shape ({n_tenors},) to match observed_forwards, "
            f"got {tau.shape}"
        )
    if not bool(np.all(np.isfinite(forwards))):
        raise ValidationError("observed_forwards must be finite")
    if bool(np.any(forwards <= 0.0)):
        raise ValidationError("observed_forwards must be strictly positive (log-forwards taken)")
    if bool(np.any(tau < 0.0)):
        raise ValidationError("time_to_maturity entries must be non-negative")

    obs_log = np.log(forwards)
    theta0 = _initial_theta(obs_log, dt)
    result = minimize(
        _negloglik,
        theta0,
        args=(obs_log, tau, dt, diffuse_prior_var),
        method=optimizer_method,
        options={"maxiter": max_iter},
    )
    theta = np.asarray(result.x, dtype=np.float64)
    params, meas_sigma = _unpack(theta)
    if not bool(np.all(np.isfinite(theta))):
        raise ValidationError(
            f"Schwartz-Smith calibration produced non-finite parameters ({result.message})"
        )

    log_lik, filtered, residuals = _kalman_filter(
        params, meas_sigma, obs_log, tau, dt, diffuse_prior_var
    )
    # Not every scipy.optimize.minimize method reports a Jacobian (e.g. Nelder-Mead
    # carries no `jac` attribute at all, rather than `jac=None`); getattr covers both.
    jac = getattr(result, "jac", None)
    grad = np.asarray(jac, dtype=np.float64) if jac is not None else np.array([])
    gradient_norm = float(np.linalg.norm(grad)) if grad.size else math.nan
    errors, condition = _standard_errors(theta, params, obs_log, tau, dt, diffuse_prior_var)
    # Not every scipy.optimize.minimize method reports `nit` (e.g. COBYLA carries no
    # `nit` attribute at all, so `result.nit` raises AttributeError); every method
    # DOES report `nfev` (function evaluation count), so it is the fallback -- a
    # coarser but still meaningful proxy for "how much optimizer work occurred
    # before termination" (see CalibrationDiagnostics.n_iterations docstring).
    nit = getattr(result, "nit", None)
    n_iterations = int(nit) if nit is not None else int(result.nfev)

    # Initial-curve mismatch (Req 25.5): model curve at the filtered first state vs the first
    # observed curve, in log space. The two-factor model generally cannot fit it exactly.
    chi0, xi0 = float(filtered[0, 0]), float(filtered[0, 1])
    model_initial = log_forward_curve(params, chi0, xi0, 0.0, tau)
    initial_mismatch = float(np.max(np.abs(model_initial - obs_log[0])))

    diagnostics = CalibrationDiagnostics(
        converged=bool(result.success),
        optimizer_message=str(result.message),
        n_iterations=n_iterations,
        log_likelihood=float(log_lik),
        gradient_norm=gradient_norm,
        hessian_condition_number=condition,
        param_std_errors=errors,
        measurement_sigma=meas_sigma,
        filtered_initial_state=(chi0, xi0),
        residual_rmse=float(np.sqrt(np.mean(residuals**2))),
        initial_curve_max_abs_mismatch=initial_mismatch,
        fits_initial_curve=initial_mismatch <= initial_curve_tol,
        lognormal_power_caveat=_LOGNORMAL_POWER_CAVEAT,
    )
    return params, diagnostics
