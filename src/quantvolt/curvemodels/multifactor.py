"""Multifactor & multi-commodity lognormal forward-curve models.

Model specification
-------------------
::

    model_id: multifactor-forward-curve
    model_version: 1.0.0
    purpose: valuation | scenario
    state_variables: [ln F(t, T_j) for each tenor/(commodity, month) j]
    probability_measure: Q          # risk-neutral; martingale forward dynamics
    dynamics:
      equation_ids: ["§32 Multifactor Forward-Curve Dynamics",
                     "§32 Integrated Multifactor Forward Curve",
                     "§33.1 Multi-Commodity Monthly Forward Dynamics"]
    parameters: [sigma_k(t, T) factor loadings, dt]
    observables: [F(0, T) initial curve, sigma_impl option vols, target correlation]
    latent_variables: [W_k Brownian factors]
    initial_conditions: [F(0, T) matched by construction]
    calibration_targets: [initial curve (§33.2), option variance (§33.3),
                          correlation structure (§33.4)]
    numerical_method: correlated GBM Monte Carlo (numerics.monte_carlo, §2.20)
    assumptions: [lognormal forwards -> F > 0; NOT suited to spiky/negative power]
    known_failure_modes: [power spikes, negative prices, heavy tails]

The polished-spec risk-neutral multifactor forward model (§32) is

.. math::  dF(t, T) / F(t, T) = \\sum_{k=1}^{K} \\sigma_k(t, T)\\, dW_{k,t}^{Q},

whose integrated (lognormal) solution

.. math::  F(t, T) = F(0, T)\\,\\exp\\!\\big[-\\tfrac12\\!\\int_0^t\\!\\sum_k \\sigma_k^2\\,ds
                    + \\sum_k\\!\\int_0^t \\sigma_k\\,dW_k^{Q}\\big]

**matches the initial curve** ``F(0, T)`` by construction and carries no ``Q``-drift in
``F`` (a martingale). This specialises to monthly multi-commodity prices
with loadings ``sigma_(i,k,m)`` (commodity ``i``, delivery month ``k``, factor ``m``) and
three matching conditions: forward-matching, option-variance-matching,
and correlation-matching, plus the cumulative covariance ``Gamma``.

Loadings representation
-----------------------
:class:`MultifactorForwardModel` is a frozen config over a single 3-D array
``loadings`` of shape ``(n_steps, n_factors, n_tenors)``: ``loadings[b, k, j]`` is the
instantaneous loading ``sigma_k(t_b, T_j)`` held constant over time bucket ``b`` of width
``dt``. The last axis is the flattened forward state -- a plain tenor grid ``T_j`` for the
§32 single-commodity model, or the flattened ``(commodity i, month k)`` state for the §33
multi-commodity model (both use the identical array; only the labelling of the last axis
differs). ``dt`` defaults to ``1/12`` (monthly, per §33). An expired tenor is encoded by
zero loadings from its expiry bucket onward (Appendix A, eq A.5), which also makes the
cumulative variance integrate only up to expiry.

The model does not re-implement simulation: :func:`mc_inputs` hands the PSD
volatility/correlation structure to ``numerics.monte_carlo.build_covariance`` /
``simulate_correlated_forwards`` (§2.20), and :func:`simulate_forwards` is a thin bridge
over that engine.
"""

from __future__ import annotations

import warnings
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .._validation import require_positive
from ..exceptions import ValidationError
from ..numerics.monte_carlo import build_covariance, simulate_correlated_forwards

# Symmetry / PSD tolerances, aligned with numerics.monte_carlo so a structure that passes
# here also passes the engine's own PSD gate.
_SYMMETRY_TOL = 1e-10
_PSD_EIG_TOL = 1e-10
_UNIT_DIAGONAL_TOL = 1e-8

# Power-like commodity ids (from models.commodity.BUILT_IN_COMMODITIES) and substrings that
# flag a power market, used only by the lognormal-not-for-power advisory (Req 25.5).
_POWER_IDS: frozenset[str] = frozenset(
    {
        "EEX_PHELIX_DE",
        "EEX_PHELIX_AT",
        "EPEX_DE",
        "EPEX_FR",
        "EPEX_NL",
        "EPEX_BE",
        "EPEX_GB",
    }
)
_POWER_ID_SUBSTRINGS: tuple[str, ...] = ("EPEX", "PHELIX", "POWER", "NORDPOOL", "NORD_POOL")


class LognormalPowerWarning(UserWarning):
    """Advisory that a lognormal (``dF/F``) forward model is being used on power.

    Lognormal forward dynamics keep forwards strictly positive and impose Gaussian
    log-returns; they cannot reproduce the price spikes, negative prices, and heavy tails
    of spot power. The model is not *rejected* -- it may be appropriate for smooth,
    far-dated power forwards -- but callers are warned so the choice is deliberate.
    """


@dataclass(frozen=True, slots=True, eq=False)
class MultifactorForwardModel:
    """Frozen configuration of factor loadings ``sigma_k(t, T)``.

    Attributes:
        loadings: ``(n_steps, n_factors, n_tenors)`` ``float64`` array; ``loadings[b, k, j]``
            is ``sigma_k(t_b, T_j)``, the instantaneous loading of factor ``k`` on tenor
            (or ``(commodity, month)``) ``j`` over time bucket ``b`` of width ``dt``. Copied
            and made read-only at construction so the config is genuinely immutable.
        dt: Uniform time-step ``Delta t`` in years over which each bucket's loadings hold.
            Defaults to ``1/12`` (monthly). Must be ``> 0``.

    The initial curve ``F(0, T)`` is not stored: it is supplied to ``simulate_forwards``
    and matched by construction (the dynamics are a driftless-in-``F`` martingale from any
    positive ``F(0, T)``). Validation is eager: 3-D shape with every
    axis non-empty, all-finite loadings, and ``dt > 0``.
    """

    loadings: npt.NDArray[np.float64]
    dt: float = 1.0 / 12.0

    def __post_init__(self) -> None:
        arr = np.array(self.loadings, dtype=np.float64)  # defensive copy (no input aliasing)
        if arr.ndim != 3:
            raise ValidationError(
                f"loadings must be 3-D (n_steps, n_factors, n_tenors), got shape {arr.shape}"
            )
        n_steps, n_factors, n_tenors = arr.shape
        if n_steps < 1 or n_factors < 1 or n_tenors < 1:
            raise ValidationError(
                "loadings must have every axis non-empty (n_steps, n_factors, n_tenors "
                f">= 1), got shape {arr.shape}"
            )
        if not bool(np.all(np.isfinite(arr))):
            raise ValidationError("loadings must be finite")
        require_positive("dt", self.dt)
        arr = np.ascontiguousarray(arr)
        arr.setflags(write=False)
        object.__setattr__(self, "loadings", arr)

    @property
    def n_steps(self) -> int:
        """Number of discrete time buckets on the loading grid."""
        return int(self.loadings.shape[0])

    @property
    def n_factors(self) -> int:
        """Number of common Brownian factors."""
        return int(self.loadings.shape[1])

    @property
    def n_tenors(self) -> int:
        """Size of the flattened forward state ``D`` (tenors, or ``(commodity, month)``)."""
        return int(self.loadings.shape[2])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MultifactorForwardModel):
            return NotImplemented
        return self.dt == other.dt and bool(np.array_equal(self.loadings, other.loadings))

    def __hash__(self) -> int:
        return hash((self.loadings.shape, self.dt, self.loadings.tobytes()))

    @classmethod
    def from_target_correlation(
        cls,
        target_corr: npt.ArrayLike,
        instantaneous_vols: npt.ArrayLike,
        *,
        n_steps: int = 1,
        dt: float = 1.0 / 12.0,
        symmetry_tol: float = _SYMMETRY_TOL,
        psd_eig_tol: float = _PSD_EIG_TOL,
        unit_diagonal_tol: float = _UNIT_DIAGONAL_TOL,
    ) -> MultifactorForwardModel:
        """Build loadings whose induced structure reproduces a target correlation.

        Given a target correlation matrix ``R`` (``(D, D)``, symmetric, unit-diagonal, PSD)
        and per-tenor instantaneous volatilities ``v`` (``sigma`` of each forward's log
        return, length ``D``, ``>= 0``), factor an ``R = Q Lambda Qᵀ`` (eigen-decomposition,
        PSD-safe) and set the single-bucket loading matrix ``L = (diag(v) · Q · sqrt(Lambda))ᵀ``.
        Then the induced covariance rate ``LᵀL = diag(v)·R·diag(v)`` has diagonal ``v_i^2``
        and :func:`induced_correlation` recovers ``R`` exactly (up to round-off). ``n_factors``
        equals ``D`` (a full-rank representation). The loadings are constant across the
        ``n_steps`` buckets, so the cumulative variance to horizon ``T = n_steps·dt`` is
        ``v_i^2·T``, matching the total variance implied by ``v``.

        Args:
            target_corr: ``(D, D)`` target correlation matrix.
            instantaneous_vols: Length-``D`` per-tenor instantaneous vols, ``>= 0``.
            n_steps: Number of buckets over which the loadings are held constant,
                ``>= 1``.
            dt: Uniform time-step in years, ``> 0``.
            symmetry_tol: Max allowed asymmetry ``max|R - Rᵀ|`` (default ``1e-10``,
                matching ``numerics.monte_carlo``'s own gate).
            psd_eig_tol: Min eigenvalue slack for the PSD check (default
                ``1e-10``); eigenvalues below ``-psd_eig_tol`` are rejected.
            unit_diagonal_tol: Max allowed deviation of the diagonal from 1.0
                (default ``1e-8``).
        """
        require_positive("symmetry_tol", symmetry_tol)
        require_positive("psd_eig_tol", psd_eig_tol)
        require_positive("unit_diagonal_tol", unit_diagonal_tol)
        r = np.ascontiguousarray(target_corr, dtype=np.float64)
        v = np.ascontiguousarray(instantaneous_vols, dtype=np.float64)
        if v.ndim != 1 or v.shape[0] < 1:
            raise ValidationError(
                f"instantaneous_vols must be a non-empty 1-D array, got shape {v.shape}"
            )
        d = int(v.shape[0])
        if bool(np.any(v < 0.0)):
            raise ValidationError("instantaneous_vols must be non-negative")
        _validate_correlation(r, d, symmetry_tol, psd_eig_tol, unit_diagonal_tol)
        if n_steps < 1:
            raise ValidationError(f"n_steps must be >= 1, got {n_steps}")
        eigvals, eigvecs = np.linalg.eigh(0.5 * (r + r.T))
        eigvals = np.clip(eigvals, 0.0, None)
        root = eigvecs * np.sqrt(eigvals)  # B with B·Bᵀ = R
        factor = v[:, None] * root  # diag(v) · B, so (diag(v)·B)(diag(v)·B)ᵀ = diag(v)·R·diag(v)
        single = np.ascontiguousarray(factor.T)  # loadings[b]: LᵀL = factor·factorᵀ
        loadings = np.repeat(single[None, :, :], n_steps, axis=0)
        return cls(loadings=loadings, dt=dt)


def _validate_correlation(
    r: npt.NDArray[np.float64],
    d: int,
    symmetry_tol: float = _SYMMETRY_TOL,
    psd_eig_tol: float = _PSD_EIG_TOL,
    unit_diagonal_tol: float = _UNIT_DIAGONAL_TOL,
) -> None:
    """Raise if ``r`` is not a valid ``(d, d)`` correlation matrix (symmetric, unit-diag, PSD)."""
    if r.shape != (d, d):
        raise ValidationError(f"target_corr must be square ({d}, {d}), got shape {r.shape}")
    if not bool(np.all(np.isfinite(r))):
        raise ValidationError("target_corr must be finite")
    asym = float(np.max(np.abs(r - r.T)))
    if asym > symmetry_tol:
        raise ValidationError(f"target_corr must be symmetric (max asymmetry {asym:.3e})")
    if float(np.max(np.abs(r))) > 1.0 + symmetry_tol:
        raise ValidationError("target_corr entries must lie in [-1, 1]")
    diag_dev = float(np.max(np.abs(np.diag(r) - 1.0)))
    if diag_dev > unit_diagonal_tol:
        raise ValidationError(f"target_corr must have unit diagonal (max deviation {diag_dev:.3e})")
    min_eig = float(np.linalg.eigvalsh(0.5 * (r + r.T)).min())
    if min_eig < -psd_eig_tol:
        raise ValidationError(
            f"target_corr must be positive semidefinite (min eigenvalue {min_eig:.3e})"
        )


def _check_step(model: MultifactorForwardModel, step: int) -> int:
    if not (0 <= step < model.n_steps):
        raise ValidationError(f"step must be in [0, {model.n_steps}), got {step}")
    return step


def induced_covariance(model: MultifactorForwardModel, step: int) -> npt.NDArray[np.float64]:
    """Instantaneous induced covariance-rate matrix at bucket ``step``.

    Returns the ``(D, D)`` matrix ``Sigma[i, j] = sum_k sigma_k(t_step, T_i)·sigma_k(t_step, T_j)``
    -- the coefficient of ``dt`` in ``d<ln F(·,T_i), ln F(·,T_j)>_t``. It is the Gram
    matrix ``LᵀL`` of the loading slice ``L = loadings[step]``
    (shape ``(K, D)``) and is therefore symmetric and positive semidefinite **by
    construction**. Multiply by ``model.dt`` for the one-step covariance consumed by the MC
    engine (equivalently :func:`cumulative_covariance` over a single bucket).
    """
    left = model.loadings[_check_step(model, step)]  # (K, D)
    cov = left.T @ left  # (D, D) Gram -> symmetric PSD
    return np.ascontiguousarray(0.5 * (cov + cov.T))


def induced_correlation(model: MultifactorForwardModel, step: int) -> npt.NDArray[np.float64]:
    """Instantaneous induced correlation matrix at bucket ``step``.

    Normalises :func:`induced_covariance` to correlations
    ``rho[i, j] = Sigma[i, j] / (sqrt(Sigma[i, i])·sqrt(Sigma[j, j]))``. By
    Cauchy-Schwarz on the Gram matrix ``rho in [-1, 1]`` with
    ``rho[i, i] = 1`` for every tenor of non-zero variance; the result is clipped to
    ``[-1, 1]`` to absorb float round-off, so the bound holds exactly. A tenor
    with zero instantaneous variance (expired, eq A.5) has an undefined off-diagonal
    correlation with every other tenor, so those entries are set to ``0``; its OWN diagonal
    entry, however, is set to ``1`` (a unit-diagonal convention, not a claim of unit
    variance) rather than ``0``. This matters because ``sigma_i = 0`` already zeroes that
    row/column of the *covariance* ``C = diag(sigma)·R·diag(sigma)`` regardless of
    ``R[i, i]`` (:func:`~quantvolt.numerics.monte_carlo.build_covariance`, which the
    simulator uses to hold expired tenors fixed) -- so a ``0`` diagonal here would only
    fail that function's own unit-diagonal validation without changing the covariance at
    all. Consumers other than :func:`mc_inputs`/:func:`simulate_forwards` should treat a
    zero-variance tenor's diagonal entry as "undefined, not a correlation of 1" and check
    :func:`induced_covariance`'s diagonal (or the model's per-tenor ``sigma``) directly if
    they need to detect expiry.
    """
    cov = induced_covariance(model, step)
    var = np.clip(np.diag(cov), 0.0, None)
    std = np.sqrt(var)
    outer = np.outer(std, std)
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = np.where(outer > 0.0, cov / outer, 0.0)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)
    return np.ascontiguousarray(0.5 * (corr + corr.T))


def cumulative_covariance(
    model: MultifactorForwardModel, upto_step: int | None = None
) -> npt.NDArray[np.float64]:
    """Cumulative covariance ``Gamma`` over ``[0, T*]``.

    Returns ``Gamma[i, j] = sum_{b < n} sum_k sigma_k(t_b, T_i)·sigma_k(t_b, T_j)·dt`` -- the
    Riemann sum of the induced covariance rate over the first ``n`` buckets, i.e. the discrete
    ``integral_0^{T*} sum_k sigma_k(s, T_i) sigma_k(s, T_j) ds`` with ``T* = n·dt``. With
    ``upto_step is None`` the whole horizon (all ``n_steps`` buckets) is used. As a sum of
    Gram matrices scaled by ``dt > 0``, ``Gamma`` is symmetric and positive semidefinite by
    construction.
    """
    if upto_step is None:
        n = model.n_steps
    elif not (1 <= upto_step <= model.n_steps):
        raise ValidationError(f"upto_step must be in [1, {model.n_steps}], got {upto_step}")
    else:
        n = upto_step
    left = model.loadings[:n]  # (n, K, D)
    gamma = np.einsum("bki,bkj->ij", left, left) * model.dt
    return np.ascontiguousarray(0.5 * (gamma + gamma.T))


def option_variance(
    model: MultifactorForwardModel, upto_step: int | None = None
) -> npt.NDArray[np.float64]:
    """Cumulative per-tenor variance ``Gamma_ii`` to the selected horizon.

    Returns the diagonal of :func:`cumulative_covariance`,
    ``Gamma_ii = sum_b sum_k sigma_k(t_b, T_i)^2·dt`` -- the total-variance quantity
    ``integral sum_m sigma_(i,k,m)^2 ds =
    [sigma_impl]^2·(T - t)``.
    """
    return np.ascontiguousarray(np.diag(cumulative_covariance(model, upto_step)).copy())


def matches_option_variance(
    model: MultifactorForwardModel,
    implied_vols: npt.ArrayLike,
    expiries: npt.ArrayLike,
    *,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> bool:
    """Check the option-variance condition ``Gamma_ii(T) == sigma_impl^2·T``.

    Compares the model's cumulative per-tenor variance :func:`option_variance` (over the
    full horizon) against the quoted Black total variance ``[sigma_impl]^2·(T_k)`` for each
    tenor. Because expired-tenor loadings are zero past expiry (eq A.5), the full-horizon
    ``Gamma_ii`` equals the integral only up to each tenor's own expiry ``T_k``, so a single
    per-tenor ``expiries`` vector suffices. Returns ``True`` iff every tenor matches within
    ``(rtol, atol)``.
    """
    iv = np.ascontiguousarray(implied_vols, dtype=np.float64)
    expiry = np.ascontiguousarray(expiries, dtype=np.float64)
    d = model.n_tenors
    if iv.shape != (d,):
        raise ValidationError(f"implied_vols must have shape ({d},), got {iv.shape}")
    if expiry.shape != (d,):
        raise ValidationError(f"expiries must have shape ({d},), got {expiry.shape}")
    if bool(np.any(expiry <= 0.0)):
        raise ValidationError("expiries must be strictly positive")
    target = iv**2 * expiry
    return bool(np.allclose(option_variance(model), target, rtol=rtol, atol=atol))


def forward_matching_residual(
    initial_forwards: npt.ArrayLike, expected_forwards: npt.ArrayLike
) -> npt.NDArray[np.float64]:
    """Residual of the forward-matching condition ``E^Q[F(t)] - F(0)``.

    The forward-matching condition is ``E^Q[F_(i,k)(t)] = F_(i,k)(0)``. This returns
    ``expected_forwards - initial_forwards``,
    which is zero in expectation for the martingale dynamics and should be ~0 for a
    simulated Monte Carlo mean. At ``t = 0`` it is exactly zero by construction.
    """
    f0 = np.ascontiguousarray(initial_forwards, dtype=np.float64)
    ef = np.ascontiguousarray(expected_forwards, dtype=np.float64)
    if f0.shape != ef.shape:
        raise ValidationError(
            f"initial_forwards {f0.shape} and expected_forwards {ef.shape} must have equal shape"
        )
    return ef - f0


def matches_initial_curve(
    initial_forwards: npt.ArrayLike,
    expected_forwards: npt.ArrayLike,
    *,
    rtol: float = 1e-2,
    atol: float = 1e-8,
) -> bool:
    """Check ``E^Q[F(t)] == F(0)`` within tolerance.

    Returns ``True`` iff ``expected_forwards`` matches ``initial_forwards`` within
    ``(rtol, atol)``. The default ``rtol`` accommodates a Monte Carlo mean; at ``t = 0`` the
    match is exact. ``rtol`` is applied against ``initial_forwards`` (comparing the two
    curves directly), not against a residual, so a relative tolerance is meaningful.
    """
    forward_matching_residual(initial_forwards, expected_forwards)  # shape-check both curves
    f0 = np.ascontiguousarray(initial_forwards, dtype=np.float64)
    ef = np.ascontiguousarray(expected_forwards, dtype=np.float64)
    return bool(np.allclose(ef, f0, rtol=rtol, atol=atol))


def risk_neutral_drift(cov: npt.ArrayLike) -> npt.NDArray[np.float64]:
    """Per-step risk-neutral log-drift ``mu = -1/2 · diag(C)`` under ``Q``.

    The integrated multifactor solution carries the Ito correction ``-1/2 integral sum_k
    sigma_k^2 ds`` in log space, so under ``Q`` the per-step drift of ``ln F`` is
    ``-1/2·diag(C)`` where ``C`` is the one-step covariance. This drift makes the simulated
    ``F = exp(Z)`` a martingale, ``E^Q[F(t, T)] = F(0, T)``. Feed it as the
    ``drift`` argument of ``simulate_correlated_forwards``.
    """
    c = np.ascontiguousarray(cov, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValidationError(f"cov must be a square 2-D matrix, got shape {c.shape}")
    return np.ascontiguousarray(-0.5 * np.diag(c).copy())


def mc_inputs(
    model: MultifactorForwardModel, step: int
) -> tuple[npt.NDArray[np.float64], npt.NDArray[np.float64]]:
    """Produce the ``(sigma, corr)`` structure for the correlated MC engine.

    Decomposes the bucket-``step`` induced covariance rate into the per-index instantaneous
    volatility ``sigma_i = sqrt(Sigma[i, i])`` and the induced correlation ``R`` so the caller
    can assemble the one-step covariance with
    ``numerics.monte_carlo.build_covariance(sigma, corr, model.dt)`` -- which reproduces
    ``induced_covariance(model, step)·dt`` exactly. ``sigma`` is non-negative and ``corr`` is
    symmetric, unit-diagonal, and PSD, so it passes ``build_covariance``'s validation and the
    engine's PSD gate. Expired tenors surface as ``sigma_i = 0`` (eq A.5).
    """
    cov = induced_covariance(model, step)
    sigma = np.sqrt(np.clip(np.diag(cov), 0.0, None))
    corr = induced_correlation(model, step)
    return np.ascontiguousarray(sigma), corr


def warn_if_power_like(commodity_ids: Sequence[str]) -> tuple[str, ...]:
    """Emit the lognormal-not-for-power advisory for any power-like id.

    A lognormal ``dF/F`` forward model is *not automatically appropriate for spiky power
    prices*. This scans ``commodity_ids`` (against the built-in power ids and power-market
    substrings such as ``EPEX``/``PHELIX``/``POWER``) and, if any match, issues a
    :class:`LognormalPowerWarning` naming them. Returns the tuple of matched ids (possibly
    empty) so callers can branch or assert on the outcome.
    """
    matched = tuple(cid for cid in commodity_ids if _is_power_like(cid))
    if matched:
        warnings.warn(
            "lognormal (dF/F) forward models are not automatically appropriate for spiky "
            "power prices; they cannot capture spikes, negative prices, or heavy tails for "
            f"power-like commodities {list(matched)}. Consider a regime/spike or "
            "structural model (Req 25.5).",
            LognormalPowerWarning,
            stacklevel=2,
        )
    return matched


def _is_power_like(commodity_id: str) -> bool:
    upper = commodity_id.upper()
    return commodity_id in _POWER_IDS or any(token in upper for token in _POWER_ID_SUBSTRINGS)


def simulate_forwards(
    model: MultifactorForwardModel,
    initial_forwards: npt.ArrayLike,
    *,
    steps: int,
    path_count: int,
    seed: int,
    step: int = 0,
    commodity_ids: Sequence[str] | None = None,
    antithetic: bool = True,
) -> npt.NDArray[np.float64]:
    """Simulate risk-neutral forward-price paths with correlated Monte Carlo.

    Assembles the one-step covariance ``C = build_covariance(*mc_inputs(model, step), dt)``,
    sets the martingale drift ``mu = -1/2·diag(C)`` (:func:`risk_neutral_drift`), and drives
    ``numerics.monte_carlo.simulate_correlated_forwards`` from ``z0 = ln F(0, ·)``. Returns
    **forward prices** ``F = exp(Z)`` of shape ``(n_paths, steps + 1, D)``; record 0 of every
    path equals ``initial_forwards`` exactly by construction. ``initial_forwards`` must be
    strictly positive (lognormal support). The bucket
    ``step`` loading slice is held constant across all ``steps`` because the engine consumes a
    single covariance; for genuinely time-varying loadings the caller assembles a per-step
    covariance itself. If ``commodity_ids`` is given, the lognormal-not-for-power advisory
    (:func:`warn_if_power_like`) fires first.
    """
    if commodity_ids is not None:
        warn_if_power_like(commodity_ids)
    f0 = np.ascontiguousarray(initial_forwards, dtype=np.float64)
    d = model.n_tenors
    if f0.shape != (d,):
        raise ValidationError(f"initial_forwards must have shape ({d},), got {f0.shape}")
    if not bool(np.all(np.isfinite(f0))):
        raise ValidationError("initial_forwards must be finite")
    if bool(np.any(f0 <= 0.0)):
        raise ValidationError("initial_forwards must be strictly positive (lognormal support)")
    sigma, corr = mc_inputs(model, step)
    cov = build_covariance(sigma, corr, model.dt)
    drift = risk_neutral_drift(cov)
    z0 = np.log(f0)
    log_paths = simulate_correlated_forwards(
        z0, drift, cov, steps, path_count, seed, antithetic=antithetic
    )
    return np.ascontiguousarray(np.exp(log_paths))
