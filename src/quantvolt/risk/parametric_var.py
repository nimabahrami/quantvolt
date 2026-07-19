"""Parametric (variance-covariance) VaR: delta and delta-gamma.

Analytical VaR for large, mildly non-linear books: no full revaluation, so a portfolio
mapped onto ~2000 risk factors is priced well inside a tight time budget. Two surfaces,
result co-located here:

* ``parametric_var``: first-order (delta) VaR ``VaR_c = z_c*sqrt(deltaT Sigma delta)``.
* ``delta_gamma_var``: second-order (delta-gamma) VaR from a Cornish-Fisher moment
  match on the quadratic P&L ``dP ~= delta.df + 0.5*dfT Gamma df``.

Risk specification
------------------
* ``risk_measure_id``: ``parametric-delta-var`` / ``parametric-delta-gamma-var``.
* ``confidence_level``: caller-supplied; the documented defaults are 95% and 99%.
* ``holding_period``: implicit in the caller's inputs. ``deltas`` and ``Sigma`` must be
  expressed over the same horizon (e.g. one-day deltas with a one-day covariance); this
  function performs no time scaling.
* ``distribution_method``: analytical. Risk factors ``df`` are assumed jointly
  ``N(0, Sigma)`` (zero mean over the horizon).
* ``probability_measure``: physical (the covariance is a real-world forecast).
* ``revaluation_method``: ``delta`` (``parametric_var``) / ``delta-gamma``
  (``delta_gamma_var``); no full revaluation.
* ``outputs``: per-confidence VaR plus the P&L distribution's first moments
  (``ParametricVaRResult``).

Sign convention
---------------
Loss is ``L = -dP`` and VaR at confidence ``c`` is the ``c``-quantile of ``L``, a
non-negative currency amount for the ordinary delta case. For the delta case
``dP = delta.df ~ N(0, deltaT Sigma delta)`` is symmetric and zero-mean, so
``VaR_c = z_c*sqrt(deltaT Sigma delta)``. For the delta-gamma case the loss quantile is
obtained from the Cornish-Fisher expansion of the quadratic-form distribution (see
``delta_gamma_var``); it can, for a strongly long-gamma / low-variance book, be negative,
an expected gain even in the tail, which is reported as-is rather than floored.

z-scores
--------
The two canonical levels use fixed, rounded constants exactly: ``z_0.95 = 1.645`` and
``z_0.99 = 2.326``. Any other confidence uses ``scipy.stats.norm.ppf``. A confidence of
exactly ``0.95`` therefore yields ``1.645``, marginally different from
``norm.ppf(0.95) = 1.6449``; this is intentional, so the formula matches the documented
constants.

Covariance validation
----------------------
``Sigma`` is validated square, symmetric, and positive semidefinite (within a ``1e-8``
absolute tolerance) before any VaR arithmetic. To keep the 2000-factor path fast the PSD
test is a Cholesky factorisation of ``Sigma + 1e-8*I`` rather than a full
eigendecomposition: ``Sigma + tol*I`` is positive definite iff
``lambda_min(Sigma) > -tol``, an exact restatement of ``quantvolt.risk.covariance``'s
PSD convention. Only when that Cholesky fails is the (slow) exact smallest eigenvalue
computed, purely to name it in the ``ValidationError``. This module keeps its own
private PSD guard rather than importing the covariance module's private one.

Limitations
-----------
* Normality of ``df`` understates tail risk for fat-tailed energy factors.
* The delta / delta-gamma approximations are local; for materially non-linear physical
  assets prefer full-revaluation Monte Carlo VaR.
* The third-order Cornish-Fisher expansion is reliable only for moderate skewness; for
  large third moments the mapping from confidence to quantile can lose monotonicity.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.stats import norm  # type: ignore[import-untyped]

from ..exceptions import ValidationError

#: Absolute tolerance on the smallest eigenvalue of Σ (matches ``risk/covariance.py``).
_PSD_TOL = 1e-8

#: Relative tolerance (against the matrix scale) for the symmetry check.
_SYMMETRY_RTOL = 1e-8

#: Fixed rounded z-scores for the two canonical confidence levels.
_CANONICAL_Z: dict[float, float] = {0.95: 1.645, 0.99: 2.326}

#: Documented default confidence levels for both surfaces.
DEFAULT_CONFIDENCES: tuple[float, ...] = (0.95, 0.99)


@dataclass(frozen=True, slots=True)
class ParametricVaRResult:
    """Outcome of a parametric-VaR computation.

    ``confidences`` and ``var_values`` are parallel tuples in the caller's request order;
    ``var_values[i]`` is the VaR (a loss, in the currency units of ``deltas``) at
    ``confidences[i]``; use ``var_at`` for a keyed lookup. ``method`` records the
    quantile method (``"delta"`` for ``parametric_var``; the delta-gamma method name,
    e.g. ``"cornish_fisher"``, for ``delta_gamma_var``) so the reported figure is
    self-documenting.

    ``pnl_mean`` / ``pnl_variance`` / ``pnl_skewness`` are the first three moments of the
    P&L (``ΔP``, not the loss) distribution under the model: for the linear case they are
    ``(0.0, δᵀΣδ, 0.0)``; for the delta-gamma case they are the quadratic-form cumulants
    ``(κ₁, κ₂, κ₃/κ₂^1.5)``. ``n_factors`` is the number of risk factors.
    """

    confidences: tuple[float, ...]
    var_values: tuple[float, ...]
    method: str
    pnl_mean: float
    pnl_variance: float
    pnl_skewness: float
    n_factors: int

    def var_at(self, confidence: float) -> float:
        """VaR at a computed ``confidence``; raise if that level was not requested."""
        try:
            index = self.confidences.index(confidence)
        except ValueError:
            raise ValidationError(
                f"confidence {confidence!r} was not computed; available levels: {self.confidences}"
            ) from None
        return self.var_values[index]


def _z_score(confidence: float) -> float:
    """Normal quantile for ``confidence``: the mandated constant for 0.95/0.99, else ppf."""
    canonical = _CANONICAL_Z.get(confidence)
    if canonical is not None:
        return canonical
    return float(norm.ppf(confidence))


def _validate_confidences(confidences: Sequence[float]) -> tuple[float, ...]:
    """Coerce to a non-empty tuple of levels each strictly inside ``(0, 1)``."""
    levels = tuple(float(c) for c in confidences)
    if not levels:
        raise ValidationError("confidences must contain at least one level, got none")
    for confidence in levels:
        if not 0.0 < confidence < 1.0:
            raise ValidationError(
                f"each confidence must be in the open interval (0, 1), got {confidence!r}"
            )
    return levels


def _as_delta_vector(deltas: NDArray[np.float64]) -> NDArray[np.float64]:
    """Coerce ``deltas`` to a finite 1-D ``float64`` vector (the input is never mutated)."""
    vector = np.asarray(deltas, dtype=np.float64)
    if vector.ndim != 1:
        raise ValidationError(f"deltas must be a 1-D vector, got ndim={vector.ndim}")
    if vector.size == 0:
        raise ValidationError("deltas must contain at least one risk factor, got length 0")
    if not np.all(np.isfinite(vector)):
        raise ValidationError("deltas must contain only finite values (no NaN or inf)")
    return vector


def _require_square_symmetric(
    matrix: NDArray[np.float64], *, name: str, n: int, symmetry_rtol: float = _SYMMETRY_RTOL
) -> NDArray[np.float64]:
    """Coerce and validate a square, symmetric, conformable matrix; return the symmetrised copy.

    Validates (in order): 2-D and finite; square; dimension equal to ``n`` (the delta
    length, naming both dimensions); symmetric within ``symmetry_rtol`` (naming the
    offending entry). PSD is not asserted here: ``Σ`` adds a Cholesky test in
    ``_require_psd_cov``, whereas ``Γ`` may legitimately be indefinite.
    """
    data = np.asarray(matrix, dtype=np.float64)
    if data.ndim != 2:
        raise ValidationError(f"{name} must be a 2-D matrix, got ndim={data.ndim}")
    if not np.all(np.isfinite(data)):
        raise ValidationError(f"{name} must contain only finite values (no NaN or inf)")
    if data.shape[0] != data.shape[1]:
        raise ValidationError(f"{name} must be square, got shape {data.shape}")
    if data.shape[0] != n:
        raise ValidationError(
            f"delta-vector length and {name} dimension do not match: len(deltas)={n} "
            f"but {name} is {data.shape[0]}x{data.shape[1]}"
        )
    asymmetry = np.abs(data - data.T)
    max_asymmetry = float(asymmetry.max())
    scale = max(float(np.abs(data).max()), 1.0)
    if max_asymmetry > symmetry_rtol * scale:
        i, j = (int(x) for x in np.unravel_index(int(np.argmax(asymmetry)), data.shape))
        raise ValidationError(
            f"{name} must be symmetric: entry [{i},{j}]={data[i, j]!r} != [{j},{i}]={data[j, i]!r}"
        )
    return (data + data.T) / 2.0


def _require_psd_cov(
    cov: NDArray[np.float64],
    *,
    n: int,
    psd_tol: float = _PSD_TOL,
    symmetry_rtol: float = _SYMMETRY_RTOL,
) -> NDArray[np.float64]:
    """Validate ``cov`` square/symmetric/conformable/PSD; return the symmetrised copy.

    The PSD test is a Cholesky factorisation of ``symmetric + psd_tol·I`` — positive
    definite iff ``λ_min > -psd_tol`` — chosen so a 2000-factor covariance stays fast.
    Only on failure is the exact smallest eigenvalue computed, to name it in the raised
    error.
    """
    symmetric = _require_square_symmetric(cov, name="cov", n=n, symmetry_rtol=symmetry_rtol)
    try:
        np.linalg.cholesky(symmetric + psd_tol * np.eye(n))
    except np.linalg.LinAlgError:
        min_eigenvalue = float(np.linalg.eigvalsh(symmetric)[0])
        raise ValidationError(
            f"cov is not positive semidefinite: smallest eigenvalue {min_eigenvalue!r} < -{psd_tol}"
        ) from None
    return symmetric


def _cornish_fisher_quantile(z: float, skewness: float) -> float:
    """Third-order Cornish-Fisher standardised quantile from a normal quantile ``z``.

    ``w = z + (z² - 1)/6 · γ₁`` where ``γ₁`` is the skewness of the (standardised)
    distribution being quantiled. Reduces to ``z`` when ``γ₁ = 0``.
    """
    return z + (z * z - 1.0) / 6.0 * skewness


#: Delta-gamma quantile methods (dispatch, no if/elif). A future "normal" method — which
#: keeps the second-order mean/variance but ignores skewness — slots in as ``lambda z, _: z``.
_DELTA_GAMMA_METHODS: dict[str, Callable[[float, float], float]] = {
    "cornish_fisher": _cornish_fisher_quantile,
}


def parametric_var(
    deltas: NDArray[np.float64],
    cov: NDArray[np.float64],
    confidences: Sequence[float] = DEFAULT_CONFIDENCES,
    *,
    psd_tol: float = _PSD_TOL,
    symmetry_rtol: float = _SYMMETRY_RTOL,
) -> ParametricVaRResult:
    """First-order (delta) parametric VaR ``VaR_c = z_c·√(δᵀΣδ)``.

    Validates all inputs before any arithmetic: ``deltas`` is a finite 1-D vector;
    ``cov`` is square, symmetric (within ``symmetry_rtol``), conformable with
    ``deltas`` (a mismatch names both dimensions), and positive semidefinite within
    ``psd_tol`` (a violation names the offending smallest eigenvalue). See the module
    docstring for the sign convention, the z-score policy, and the fast PSD test.

    Args:
        deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.
        cov: The ``n x n`` factor covariance forecast ``Σ`` over the loss horizon
            (e.g. from ``quantvolt.risk.covariance``).
        confidences: Confidence levels; defaults to ``(0.95, 0.99)``. Each must be in
            ``(0, 1)``; ``0.95`` / ``0.99`` use the fixed constants ``1.645`` / ``2.326``.
        psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD
            check; defaults to ``1e-8``.
        symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry
            check on ``Σ``; defaults to ``1e-8``.

    Returns:
        A ``ParametricVaRResult`` with ``method="delta"`` and a zero-mean,
        zero-skew P&L description (``pnl_variance = δᵀΣδ``).

    Raises:
        ValidationError: on any dimension, symmetry, PSD, or confidence violation, naming
            the offending quantity.
    """
    vector = _as_delta_vector(deltas)
    covariance = _require_psd_cov(cov, n=vector.size, psd_tol=psd_tol, symmetry_rtol=symmetry_rtol)
    levels = _validate_confidences(confidences)

    # Associate as δᵀ(Σδ) — the same order delta_gamma_var uses — so the Γ = 0 case of
    # delta_gamma_var collapses to this bit-for-bit (Property 48).
    variance = float(vector @ (covariance @ vector))
    variance = max(variance, 0.0)  # PSD guarantees ≥ 0; clamp float round-off at the boundary
    std = math.sqrt(variance)

    var_values = tuple(_z_score(confidence) * std for confidence in levels)
    return ParametricVaRResult(
        confidences=levels,
        var_values=var_values,
        method="delta",
        pnl_mean=0.0,
        pnl_variance=variance,
        pnl_skewness=0.0,
        n_factors=vector.size,
    )


def delta_gamma_var(
    deltas: NDArray[np.float64],
    gamma: NDArray[np.float64],
    cov: NDArray[np.float64],
    confidences: Sequence[float] = DEFAULT_CONFIDENCES,
    method: str = "cornish_fisher",
    *,
    psd_tol: float = _PSD_TOL,
    symmetry_rtol: float = _SYMMETRY_RTOL,
) -> ParametricVaRResult:
    """Second-order (delta-gamma) parametric VaR via moment matching.

    The quadratic P&L ``ΔP = δᵀΔf + ½·Δfᵀ Γ Δf`` with ``Δf ~ N(0, Σ)`` has, writing
    ``Θ = Γ Σ``, the standard delta-gamma-normal cumulants (Britten-Jones & Schaefer,
    "Non-linear Value-at-Risk", 1999, eqs. 6-8; Zangari, RiskMetrics Monitor 1996;
    verified here against Monte Carlo):

    * ``κ₁ = ½·tr(Θ)`` — mean;
    * ``κ₂ = δᵀΣδ + ½·tr(Θ²)`` — variance;
    * ``κ₃ = 3·δᵀΣΓΣδ + tr(Θ³)`` — third cumulant.

    The loss ``L = -ΔP`` has mean ``-κ₁``, standard deviation ``√κ₂`` and skewness
    ``-κ₃/κ₂^1.5``; its ``c``-quantile is ``VaR_c = -κ₁ + √κ₂ · w(z_c, -γ₁)`` where ``w``
    is the third-order Cornish-Fisher map ``w = z + (z²-1)/6·γ₁`` (dispatched by
    ``method``). With ``Γ = 0`` all higher cumulants vanish and this collapses exactly
    to ``parametric_var``.

    Sign sanity: a long-gamma book (``Γ`` positive definite) has ``κ₁ > 0`` (the quadratic
    term only ever adds to P&L) and positive P&L skewness, so both the mean shift and the
    skewness correction *reduce* VaR relative to the delta-only figure — the expected
    direction.

    Args:
        deltas: Portfolio delta by risk factor, a 1-D vector of length ``n``.
        gamma: The ``n x n`` gamma matrix ``Γ``; must be square, symmetric, and conformable
            with ``deltas`` — but need **not** be PSD (a book may be long some gammas and
            short others).
        cov: The ``n x n`` factor covariance ``Σ`` (validated square/symmetric/PSD).
        confidences: Confidence levels; defaults to ``(0.95, 0.99)``.
        method: Delta-gamma quantile method; defaults to ``"cornish_fisher"``. Must be a
            registered method (currently only ``"cornish_fisher"``).
        psd_tol: Absolute tolerance on the smallest eigenvalue of ``Σ`` used by the PSD
            check; defaults to ``1e-8``.
        symmetry_rtol: Relative tolerance (against the matrix scale) for the symmetry
            checks on ``Σ`` and ``Γ``; defaults to ``1e-8``.

    Returns:
        A ``ParametricVaRResult`` carrying ``method`` and the P&L cumulant moments
        ``(κ₁, κ₂, κ₃/κ₂^1.5)``.

    Raises:
        ValidationError: on any dimension, symmetry, PSD, confidence, or unknown-``method``
            violation, naming the offending quantity.
    """
    if method not in _DELTA_GAMMA_METHODS:
        raise ValidationError(
            f"unknown delta-gamma method {method!r}; available methods: "
            f"{sorted(_DELTA_GAMMA_METHODS)}"
        )

    vector = _as_delta_vector(deltas)
    covariance = _require_psd_cov(cov, n=vector.size, psd_tol=psd_tol, symmetry_rtol=symmetry_rtol)
    gamma_matrix = _require_square_symmetric(
        gamma, name="gamma", n=vector.size, symmetry_rtol=symmetry_rtol
    )
    levels = _validate_confidences(confidences)

    # Cumulants of ΔP (Θ = Γ Σ). Two O(n³) matmuls; the traces are O(n²) reductions.
    cov_delta = covariance @ vector  # Σδ
    linear_variance = float(vector @ cov_delta)  # δᵀΣδ
    theta = gamma_matrix @ covariance  # Θ = Γ Σ
    theta_squared = theta @ theta
    tr_theta = float(np.trace(theta))
    tr_theta2 = float(np.trace(theta_squared))
    tr_theta3 = float(np.sum(theta_squared * theta.T))  # tr(Θ³) = Σ_ij (Θ²)_ij Θ_ji
    delta_sgs = float(cov_delta @ (gamma_matrix @ cov_delta))  # δᵀΣΓΣδ = (Σδ)ᵀΓ(Σδ)

    mean = 0.5 * tr_theta
    variance = max(linear_variance + 0.5 * tr_theta2, 0.0)
    third_cumulant = 3.0 * delta_sgs + tr_theta3
    std = math.sqrt(variance)
    # Guard on variance**1.5, not variance: for subnormal-scale inputs variance can be
    # positive while variance**1.5 underflows to exactly 0.0, and a bare ZeroDivisionError
    # would violate the EnergyQuantError contract (Req 11.5).
    variance_pow = variance**1.5
    skewness = third_cumulant / variance_pow if variance_pow > 0.0 else 0.0

    quantile = _DELTA_GAMMA_METHODS[method]
    var_values = tuple(
        -mean + std * quantile(_z_score(confidence), -skewness) for confidence in levels
    )
    return ParametricVaRResult(
        confidences=levels,
        var_values=var_values,
        method=method,
        pnl_mean=mean,
        pnl_variance=variance,
        pnl_skewness=skewness,
        n_factors=vector.size,
    )
