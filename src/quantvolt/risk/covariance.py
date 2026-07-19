"""Covariance forecasting — EWMA and diagonal GARCH(1,1)+CCC.

Two forward-looking covariance estimators over a Caller-supplied return matrix, plus the
positive-semidefinite (PSD) machinery the parametric-VaR path consumes. Both
estimators return a symmetric, PSD ``np.ndarray`` (design §2.16, Property 49):

* :func:`ewma_covariance` — the RiskMetrics exponentially-weighted recursion (eq. U10.1).
* :func:`garch11_covariance` — a diagonal GARCH(1,1) fit per asset (eqs. U10.2-U10.3) with
  a constant conditional correlation (CCC, Bollerslev 1990) linking the series.

Orientation convention (both estimators): ``returns`` is a 2-D array of shape
``(n_obs, n_assets)`` — one row per observation (time step, **oldest first**) and one
column per asset. Returns are treated as the model innovations: :func:`ewma_covariance`
follows the RiskMetrics zero-mean convention (no centring), while
:func:`garch11_covariance` de-means each column before fitting.

PSD policy: every returned matrix is first symmetrised, then its smallest eigenvalue is
required to be ``>= -1e-8`` by the private :func:`_require_psd` guard. :func:`nearest_psd`
is exposed as an optional Higham-style repair utility (projection onto the PSD cone).

This module deliberately keeps its **own** private PSD assertion rather than importing one
from ``numerics/monte_carlo.py`` (Task 62, developed concurrently); a later cleanup may
unify them (see tasks.md Task 64).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import minimize  # type: ignore[import-untyped]

from ..exceptions import ValidationError

#: Absolute tolerance on the smallest eigenvalue when asserting positive semidefiniteness.
_PSD_TOL = 1e-8

#: (alpha, beta) starting guess for the GARCH(1,1) MLE; omega is set by variance targeting.
_GARCH_ALPHA0 = 0.05
_GARCH_BETA0 = 0.90

#: Floor on omega during the MLE so the conditional-variance recursion stays strictly positive.
_OMEGA_FLOOR = 1e-12


def _validate_returns(returns: NDArray[np.float64], *, min_obs: int) -> NDArray[np.float64]:
    """Coerce ``returns`` to a finite ``float64`` (n_obs, n_assets) matrix or raise.

    Returns a fresh ``float64`` array (the Caller's input is never mutated).
    """
    data = np.asarray(returns, dtype=np.float64)
    if data.ndim != 2:
        raise ValidationError(
            f"returns must be a 2-D (n_obs, n_assets) array, got ndim={data.ndim}"
        )
    n_obs, n_assets = data.shape
    if n_assets < 1:
        raise ValidationError(f"returns must have at least 1 asset column, got n_assets={n_assets}")
    if n_obs < min_obs:
        raise ValidationError(
            f"returns must have at least {min_obs} observations (rows), got n_obs={n_obs}"
        )
    if not np.all(np.isfinite(data)):
        raise ValidationError("returns must contain only finite values (no NaN or inf)")
    return data


def _require_psd(
    matrix: NDArray[np.float64], *, name: str, tol: float = _PSD_TOL
) -> NDArray[np.float64]:
    """Symmetrise ``matrix`` and require it to be positive semidefinite.

    The matrix is first symmetrised as ``(M + Mᵀ)/2`` (removing floating-point asymmetry),
    then its smallest eigenvalue (via :func:`numpy.linalg.eigvalsh`, which assumes symmetry)
    must be ``>= -tol``. Returns the symmetrised matrix so callers can rely on exact
    symmetry of the result.

    Raises:
        ValidationError: if the smallest eigenvalue is below ``-tol``.
    """
    symmetric = (matrix + matrix.T) / 2.0
    min_eigenvalue = float(np.linalg.eigvalsh(symmetric)[0])
    if min_eigenvalue < -tol:
        raise ValidationError(
            f"{name} is not positive semidefinite: smallest eigenvalue {min_eigenvalue!r} < -{tol}"
        )
    return symmetric


def nearest_psd(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the nearest symmetric positive-semidefinite matrix (Higham-style repair).

    Symmetrises the input, then projects onto the PSD cone by clipping negative
    eigenvalues to zero and reconstructing ``V·max(Λ, 0)·Vᵀ``. For a symmetric input this
    is exactly the nearest PSD matrix in the Frobenius norm (Higham 1988). Use it to repair
    a covariance/correlation matrix that a Caller knows to be only marginally indefinite
    (e.g. from finite-precision estimation); it is *not* applied automatically by the
    estimators, which raise instead so the Caller stays in control.

    Raises:
        ValidationError: if ``matrix`` is not a square 2-D array.
    """
    data = np.asarray(matrix, dtype=np.float64)
    if data.ndim != 2 or data.shape[0] != data.shape[1]:
        raise ValidationError(f"matrix must be a square 2-D array, got shape {data.shape}")
    symmetric = (data + data.T) / 2.0
    eigenvalues, eigenvectors = np.linalg.eigh(symmetric)
    clipped = np.clip(eigenvalues, 0.0, None)
    repaired = eigenvectors @ np.diag(clipped) @ eigenvectors.T
    return np.asarray((repaired + repaired.T) / 2.0, dtype=np.float64)


def ewma_covariance(
    returns: NDArray[np.float64], lam: float = 0.94, *, psd_tol: float = _PSD_TOL
) -> NDArray[np.float64]:
    """RiskMetrics exponentially-weighted covariance forecast (eq. U10.1).

    Iterates the recursion ``Σ_t = λ·Σ_{t-1} + (1-λ)·r_t·r_tᵀ`` over the rows of
    ``returns`` (oldest first) and returns the final ``Σ`` — the one-step-ahead covariance
    forecast. Following the RiskMetrics convention the returns are treated as zero-mean
    innovations (no centring). The recursion is **initialised from the first observation's
    outer product** ``Σ_0 = r_0·r_0ᵀ``; because each update is a convex combination of
    rank-1 PSD outer products, every ``Σ_t`` — and hence the result — is PSD by
    construction.

    Args:
        returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first.
        lam: RiskMetrics decay factor in the open interval ``(0, 1)``; the default
            ``0.94`` is the RiskMetrics daily value.
        psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting
            covariance forecast when asserting positive semidefiniteness; defaults to
            ``1e-8``.

    Returns:
        The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.

    Raises:
        ValidationError: if ``lam`` is not in ``(0, 1)``; if ``returns`` is not a 2-D
            array with at least 2 observations and 1 asset; if it holds non-finite
            values; or if the result fails the PSD check within ``psd_tol``.
    """
    if not 0.0 < lam < 1.0:
        raise ValidationError(f"lam must be in (0, 1), got {lam!r}")
    data = _validate_returns(returns, min_obs=2)

    cov = np.outer(data[0], data[0])
    for observation in data[1:]:
        cov = lam * cov + (1.0 - lam) * np.outer(observation, observation)
    return _require_psd(cov, name="ewma_covariance", tol=psd_tol)


def _garch_variance_path(
    omega: float, alpha: float, beta: float, u: NDArray[np.float64], h0: float
) -> NDArray[np.float64]:
    """Conditional-variance path ``h_t = omega + alpha·u²_{t-1} + beta·h_{t-1}`` (``h_0 = h0``)."""
    n = u.size
    h = np.empty(n, dtype=np.float64)
    h[0] = h0
    for t in range(1, n):
        h[t] = omega + alpha * u[t - 1] ** 2 + beta * h[t - 1]
    return h


def _garch_negloglik(params: NDArray[np.float64], u: NDArray[np.float64], h0: float) -> float:
    """Gaussian GARCH(1,1) negative log-likelihood (constant terms retained)."""
    omega, alpha, beta = float(params[0]), float(params[1]), float(params[2])
    h = _garch_variance_path(omega, alpha, beta, u, h0)
    if not np.all(np.isfinite(h)):  # explosive parameters overflow h; steer the optimiser away
        return 1e12
    return 0.5 * float(np.sum(np.log(2.0 * np.pi) + np.log(h) + u * u / h))


def _fit_garch11(
    u: NDArray[np.float64], asset_index: int
) -> tuple[float, float, float, NDArray[np.float64]]:
    """Fit a univariate GARCH(1,1) to a de-meaned series ``u`` by Gaussian MLE.

    Maximises the Gaussian likelihood of ``h_t = omega + alpha·u²_{t-1} + beta·h_{t-1}``
    with :func:`scipy.optimize.minimize` (L-BFGS-B), the recursion seeded at the sample
    variance ``h_0``. Bounds keep ``omega >= 1e-12, alpha >= 0, beta >= 0`` so the
    likelihood is always well defined, but ``alpha + beta`` is left free to exceed 1 so a
    genuinely non-stationary series is detected rather than silently clipped. The fitted
    parameters are then validated strictly.

    Returns:
        ``(omega, alpha, beta, h)`` where ``h`` is the in-sample conditional-variance path.

    Raises:
        ValidationError: if the series has zero variance; if the MLE fails to converge; or
            if the fit violates ``omega > 0``, ``alpha >= 0``, ``beta >= 0``, or the
            stationarity constraint ``alpha + beta < 1`` — naming the violated constraint.
    """
    sample_var = float(np.var(u))
    if sample_var <= 0.0:
        raise ValidationError(
            f"asset {asset_index}: return series has zero variance; GARCH(1,1) is not identified"
        )

    x0 = np.array([sample_var * (1.0 - _GARCH_ALPHA0 - _GARCH_BETA0), _GARCH_ALPHA0, _GARCH_BETA0])
    bounds = [(_OMEGA_FLOOR, None), (0.0, 1.0), (0.0, 1.0)]
    result = minimize(_garch_negloglik, x0, args=(u, sample_var), method="L-BFGS-B", bounds=bounds)

    solution = np.asarray(result.x, dtype=np.float64)
    if not bool(result.success) or not np.all(np.isfinite(solution)):
        raise ValidationError(
            f"asset {asset_index}: GARCH(1,1) MLE failed to converge ({result.message})"
        )
    omega, alpha, beta = float(solution[0]), float(solution[1]), float(solution[2])
    if not omega > 0.0:
        raise ValidationError(f"asset {asset_index}: GARCH(1,1) requires omega > 0, got {omega!r}")
    if alpha < 0.0:
        raise ValidationError(f"asset {asset_index}: GARCH(1,1) requires alpha >= 0, got {alpha!r}")
    if beta < 0.0:
        raise ValidationError(f"asset {asset_index}: GARCH(1,1) requires beta >= 0, got {beta!r}")
    if not alpha + beta < 1.0:
        raise ValidationError(
            f"asset {asset_index}: GARCH(1,1) stationarity requires alpha + beta < 1, "
            f"got alpha + beta = {alpha + beta!r}"
        )

    h = _garch_variance_path(omega, alpha, beta, u, sample_var)
    return omega, alpha, beta, h


def _correlation_of(std_residuals: NDArray[np.float64]) -> NDArray[np.float64]:
    """Sample correlation matrix of the standardised-residual columns (PSD by construction)."""
    if std_residuals.shape[1] == 1:
        return np.array([[1.0]], dtype=np.float64)
    corr = np.asarray(np.corrcoef(std_residuals, rowvar=False), dtype=np.float64)
    corr = (corr + corr.T) / 2.0
    np.fill_diagonal(corr, 1.0)
    return corr


def garch11_covariance(
    returns: NDArray[np.float64], *, psd_tol: float = _PSD_TOL
) -> NDArray[np.float64]:
    """Diagonal GARCH(1,1) + constant-conditional-correlation covariance forecast.

    Estimator (Bollerslev 1990 CCC-GARCH), per the design §2.16 (eqs. U10.2-U10.3):

    1. **De-mean** each asset column to obtain innovations ``u_j``.
    2. **Fit** a univariate GARCH(1,1)
       ``h_{j,t} = omega_j + alpha_j·u²_{j,t-1} + beta_j·h_{j,t-1}`` to each column by
       Gaussian MLE (:func:`_fit_garch11`), enforcing ``omega_j > 0``, ``alpha_j >= 0``,
       ``beta_j >= 0``, ``alpha_j + beta_j < 1``.
    3. **Standardise** the residuals ``e_{j,t} = u_{j,t} / √h_{j,t}`` and take their sample
       correlation matrix ``R`` as the constant conditional correlation.
    4. **Forecast** each asset's one-step-ahead conditional variance
       ``h_{j,T+1} = omega_j + alpha_j·u²_{j,T} + beta_j·h_{j,T}`` and assemble
       ``Sigma = D·R·D`` with ``D = diag(√h_{j,T+1})``.

    ``Σ`` is PSD because ``R`` (a sample correlation matrix) is PSD and ``D·R·D`` is a
    congruence transform with a real diagonal.

    Args:
        returns: ``(n_obs, n_assets)`` array of periodic returns, oldest row first. A long
            series is needed for a meaningful fit.
        psd_tol: Absolute tolerance on the smallest eigenvalue of the resulting
            covariance forecast when asserting positive semidefiniteness; defaults to
            ``1e-8``.

    Returns:
        The symmetric PSD ``(n_assets, n_assets)`` covariance forecast.

    Raises:
        ValidationError: if ``returns`` is not a valid finite 2-D array with at least 2
            observations; if any per-asset series is degenerate; if any GARCH fit fails
            to converge or violates ``omega > 0, alpha >= 0, beta >= 0, alpha + beta < 1``
            (the message names the offending asset and constraint); or if the result
            fails the PSD check within ``psd_tol``.
    """
    data = _validate_returns(returns, min_obs=2)
    n_assets = data.shape[1]

    demeaned = data - data.mean(axis=0)
    conditional_var = np.empty(n_assets, dtype=np.float64)
    variances = np.empty_like(demeaned)

    for j in range(n_assets):
        column = demeaned[:, j]
        omega, alpha, beta, h = _fit_garch11(column, j)
        variances[:, j] = h
        conditional_var[j] = omega + alpha * column[-1] ** 2 + beta * h[-1]

    standardised = demeaned / np.sqrt(variances)
    correlation = _correlation_of(standardised)

    forecast_std = np.sqrt(conditional_var)
    cov = correlation * np.outer(forecast_std, forecast_std)
    return _require_psd(cov, name="garch11_covariance", tol=psd_tol)
