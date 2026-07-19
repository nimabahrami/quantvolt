"""Thin wrapper over the native Rust Monte Carlo engine `quantvolt._core`.

Task 59 exposed the single-asset Asian pricer (`asian_monte_carlo`). Task 62 adds the
correlated multi-commodity forward engine (Appendix A): `build_covariance` assembles
``C = diag(sigma)·R·diag(sigma)·Δt`` (eq A.8) and `simulate_correlated_forwards` drives the
Rust kernel that draws ``ΔZ = μ + L·ε`` with ``L = chol(C)`` (eqs A.9-A.13). The
positive-semidefiniteness gate and the opt-in nearest-PSD repair live
here at the Python boundary so a non-PSD covariance raises a clear ``ValidationError``
*before* any Cholesky runs — the Rust factor is never asked to go complex.

The core imports fine without the compiled extension; calling an MC function before
`maturin develop` raises a clear error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import numpy.typing as npt

from .._validation import require_finite, require_integer_at_least, require_positive
from ..exceptions import NativeExtensionError, NumericalError, ValidationError

try:  # native extension, built by maturin
    from quantvolt import _core

    _HAVE_CORE = True
except ImportError:  # pragma: no cover - pure-Python install / not yet built
    _core = None  # type: ignore[assignment]
    _HAVE_CORE = False

# Symmetry / PSD tolerances. The PSD eigenvalue tolerance is scaled by the covariance
# magnitude in `_validate_covariance`; correlation-matrix checks are scale-free.
_SYMMETRY_TOL = 1e-10
_PSD_EIG_TOL = 1e-10
_UNIT_DIAGONAL_TOL = 1e-8


def _require_finite_vector(name: str, arr: npt.NDArray[np.float64]) -> None:
    """Validate ``arr`` is a non-empty, finite, 1-D vector, naming ``name`` in errors.

    Shared by :func:`build_covariance`, :func:`simulate_correlated_forwards`, and
    :func:`simulate_correlated_term_structure`, each of which validates one
    array-like input against exactly this shape/finiteness contract.
    """
    if arr.ndim != 1:
        raise ValidationError(f"{name} must be 1-D, got shape {arr.shape}")
    if arr.size == 0:
        raise ValidationError(f"{name} must be non-empty")
    if not bool(np.all(np.isfinite(arr))):
        raise ValidationError(f"{name} must be finite")


def _request_field_equal(a: object, b: object) -> bool:
    """Value-equality for one :class:`CorrelatedSimulationRequest` field.

    Array-like fields (``z0``, ``drift_steps``, ``covariance_steps``, ``active_steps``)
    need :func:`numpy.array_equal` — a plain ``==`` on two arrays returns an elementwise
    array, whose truth value is ambiguous (``ValueError``) inside a boolean ``__eq__``.
    Scalar fields (``path_count``, ``seed``, ``antithetic``, ``repair``,
    ``symmetry_tol``, ``psd_tol``) and the ``active_steps=None`` default fall through to
    plain ``==``.
    """
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if a is None or b is None:
            return a is b
        return bool(np.array_equal(np.asarray(a), np.asarray(b)))
    return bool(a == b)


@dataclass(frozen=True, slots=True, eq=False)
class CorrelatedSimulationRequest:
    """Inputs for a time-varying correlated state simulation.

    Rows of ``drift_steps`` and ``covariance_steps`` are Appendix A's ``mu_t`` and
    ``C_t``. ``active_steps[t, d]`` represents the advancing live-tenor set: an inactive
    coordinate is held fixed during that step. If omitted, positive step variance defines
    activity. Arrays are copied at the public boundary before entering the native kernel.

    ``symmetry_tol`` and ``psd_tol`` gate the per-step covariance validation; defaults
    match the module's standard tolerances.

    ``eq=False`` disables the auto-generated field-tuple ``__eq__`` (Fix 9): dataclass
    equality by default compares fields with plain ``==``, and NumPy arrays make that
    ambiguous (``ValueError: The truth value of an array ... is ambiguous``) — which broke
    both ``req == deepcopy(req)`` and the shipped
    :func:`~quantvolt.testing.assert_input_unchanged` on this request type, since that
    utility's mutation check falls back to plain ``==`` for a non-array, non-Polars input.
    :meth:`__eq__` below compares array fields via :func:`numpy.array_equal` and every
    other field via plain ``==``. With ``eq=False`` dataclass leaves ``__hash__``
    untouched (falling back to ``object``'s identity-based hash); this request is a bag of
    mutable-looking array-like fields with no principled value-hash, so identity hashing
    is an acceptable, documented consequence, not a further defect.
    """

    z0: npt.ArrayLike
    drift_steps: npt.ArrayLike
    covariance_steps: npt.ArrayLike
    path_count: int
    seed: int
    active_steps: npt.ArrayLike | None = None
    antithetic: bool = True
    repair: bool = False
    symmetry_tol: float = field(default=_SYMMETRY_TOL, kw_only=True)
    psd_tol: float = field(default=_PSD_EIG_TOL, kw_only=True)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CorrelatedSimulationRequest):
            return NotImplemented
        return (
            _request_field_equal(self.z0, other.z0)
            and _request_field_equal(self.drift_steps, other.drift_steps)
            and _request_field_equal(self.covariance_steps, other.covariance_steps)
            and self.path_count == other.path_count
            and self.seed == other.seed
            and _request_field_equal(self.active_steps, other.active_steps)
            and self.antithetic == other.antithetic
            and self.repair == other.repair
            and self.symmetry_tol == other.symmetry_tol
            and self.psd_tol == other.psd_tol
        )

    # Defining __eq__ makes Python set __hash__ to None automatically (the standard
    # data-model rule), which would make this frozen dataclass unhashable. dataclass's
    # own eq=False leaves __hash__ "untouched" (falling back to the superclass), so
    # this restores that identical, documented fallback (object's identity-based hash)
    # rather than leaving the type unexpectedly unhashable.
    __hash__ = object.__hash__


def asian_monte_carlo(
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    averaging_points: int,
    option_type: Literal["call", "put"],
    geometric: bool,
    seed: int,
    path_count: int,
    *,
    antithetic: bool = True,
) -> tuple[float, float]:
    """Return ``(premium, standard_error)`` via the Rust MC kernel.

    Args:
        antithetic: Draw paths in ``(+eps, -eps)`` antithetic-variate pairs
            (default ``True``, matching the kernel's previous always-on
            behavior). ``False`` draws every path independently.
    """
    if not _HAVE_CORE:
        raise NativeExtensionError("quantvolt._core not built; run `maturin develop` (Task 59).")
    for name, value in (
        ("forward", forward),
        ("strike", strike),
        ("sigma", sigma),
        ("discount_factor", discount_factor),
    ):
        require_finite(name, value)
    # time_to_expiry must be strictly positive, not merely finite: the closed-form
    # kernels already reject T <= 0, but this wrapper previously only required_finite
    # it, so a negative T reached the Rust kernel as NaN and silently returned (0.0,
    # 0.0) instead of raising (Fix 2, verified).
    require_positive("time_to_expiry", time_to_expiry)
    require_integer_at_least("averaging_points", averaging_points, 1)
    require_integer_at_least("seed", seed, 0)
    require_integer_at_least("path_count", path_count, 1)
    if option_type not in ("call", "put"):
        raise ValidationError(f"option_type must be 'call' or 'put', got {option_type!r}")
    try:
        return _core.asian_monte_carlo(
            forward,
            strike,
            sigma,
            time_to_expiry,
            discount_factor,
            averaging_points,
            option_type == "call",
            geometric,
            seed,
            path_count,
            antithetic,
        )
    except (ValueError, OverflowError) as error:
        raise NumericalError(str(error)) from error


def simulate_ou_paths(
    x0: float,
    kappa: float,
    mu: float,
    sigma: float,
    dt: float,
    steps: int,
    path_count: int,
    *,
    seed: int,
) -> npt.NDArray[np.float64]:
    """Simulate seeded Ornstein-Uhlenbeck (mean-reverting) paths via the Rust kernel.

    Euler recursion ``x_{t+dt} = x_t + kappa*(mu - x_t)*dt + sigma*sqrt(dt)*z``. Returns a
    ``float64`` array of shape ``(path_count, steps + 1)`` with ``x0`` in column 0.
    Deterministic per ``seed`` — seeded-Rust-RNG reproducible, not
    NumPy-matching. Complements the OU *fit* in ``stats/mean_reversion.py`` (this is the
    forward simulation). Raises ``NativeExtensionError`` if ``_core`` is not built and
    ``ValidationError`` for non-finite params, ``dt <= 0``, or ``steps``/``path_count`` < 1.
    """
    if not _HAVE_CORE:
        raise NativeExtensionError("quantvolt._core not built; run `maturin develop` (Task 59).")
    for name, value in (("x0", x0), ("kappa", kappa), ("mu", mu), ("sigma", sigma)):
        require_finite(name, value)
    require_positive("dt", dt)
    require_integer_at_least("steps", steps, 1)
    require_integer_at_least("path_count", path_count, 1)
    try:
        return np.asarray(
            _core.simulate_ou(x0, kappa, mu, sigma, dt, steps, seed, path_count),
            dtype=np.float64,
        )
    except (ValueError, OverflowError) as error:
        raise NumericalError(str(error)) from error


def build_covariance(
    sigma: npt.ArrayLike,
    corr: npt.ArrayLike,
    dt: float,
    *,
    symmetry_tol: float = _SYMMETRY_TOL,
    unit_diagonal_tol: float = _UNIT_DIAGONAL_TOL,
) -> npt.NDArray[np.float64]:
    """Assemble the one-step covariance ``C = diag(sigma)·R·diag(sigma)·Δt`` (Appendix A, eq A.8).

    ``sigma`` is the flat per-index instantaneous volatility vector over the flattened
    commodity/tenor state, ``corr`` the ``(D, D)`` cross-commodity/cross-tenor
    correlation matrix ``R`` (eq A.7), and ``dt`` the step length ``Δt``. Entry
    ``C[a, b] = sigma_a · R[a, b] · sigma_b · Δt``.

    A per-index ``sigma = 0`` marks an **expired tenor** (eq A.5): it zeroes that row and
    column of ``C``, and the simulator then holds that state fixed. Validation is eager:
    ``dt > 0``; ``sigma`` finite and non-negative; ``corr`` square, finite,
    symmetric (within ``symmetry_tol``), unit-diagonal (within ``unit_diagonal_tol``),
    entries in ``[-1, 1]``. The assembled matrix is *not* PSD-checked here — that gate
    lives in :func:`simulate_correlated_forwards`, which consumes it.

    Args:
        sigma: Flat per-index volatility vector.
        corr: ``(D, D)`` correlation matrix ``R``.
        dt: Step length ``Δt``, positive.
        symmetry_tol: Maximum tolerated ``max(|R - Rᵀ|)`` asymmetry.
        unit_diagonal_tol: Maximum tolerated deviation of ``diag(R)`` from 1.
    """
    require_positive("dt", dt)
    require_positive("symmetry_tol", symmetry_tol)
    require_positive("unit_diagonal_tol", unit_diagonal_tol)
    sig = np.ascontiguousarray(sigma, dtype=np.float64)
    r = np.ascontiguousarray(corr, dtype=np.float64)
    _require_finite_vector("sigma", sig)
    d = int(sig.shape[0])
    if bool(np.any(sig < 0.0)):
        raise ValidationError("sigma must be non-negative (per-tenor volatility; 0 = expired)")
    if r.shape != (d, d):
        raise ValidationError(f"corr must be square ({d}, {d}) to match sigma, got shape {r.shape}")
    if not bool(np.all(np.isfinite(r))):
        raise ValidationError("corr must be finite")
    asym = float(np.max(np.abs(r - r.T)))
    if asym > symmetry_tol:
        raise ValidationError(f"corr must be symmetric (max asymmetry {asym:.3e})")
    if float(np.max(np.abs(r))) > 1.0 + symmetry_tol:
        raise ValidationError("corr entries must lie in [-1, 1]")
    diag_dev = float(np.max(np.abs(np.diag(r) - 1.0)))
    if diag_dev > unit_diagonal_tol:
        raise ValidationError(f"corr must have unit diagonal (max deviation {diag_dev:.3e})")
    cov = (sig[:, None] * r * sig[None, :]) * float(dt)
    # Enforce exact symmetry against float round-off before it reaches the PSD gate.
    return np.ascontiguousarray(0.5 * (cov + cov.T), dtype=np.float64)


def _nearest_psd(cov: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Higham-style nearest-PSD projection: symmetrize, then clip eigenvalues at 0.

    Diagonalize the symmetric part ``S = ½(C + Cᵀ) = V·Λ·Vᵀ``, replace every negative
    eigenvalue with zero, and rebuild ``V·Λ⁺·Vᵀ``. This is the eigenvalue-clipping
    projection onto the PSD cone in the Frobenius norm (Higham 2002); it is not a full
    unit-diagonal correlation repair, which is unnecessary for a covariance.
    """
    sym = 0.5 * (cov + cov.T)
    vals, vecs = np.linalg.eigh(sym)
    clipped = np.clip(vals, 0.0, None)
    repaired = (vecs * clipped) @ vecs.T
    return np.ascontiguousarray(0.5 * (repaired + repaired.T), dtype=np.float64)


def _validate_covariance(
    cov: npt.ArrayLike,
    *,
    repair: bool,
    symmetry_tol: float = _SYMMETRY_TOL,
    psd_tol: float = _PSD_EIG_TOL,
) -> npt.NDArray[np.float64]:
    """Return a symmetric PSD ``float64`` covariance, or raise naming the violation.

    Property 61 / Req 20.3: a non-symmetric or non-PSD matrix raises ``ValidationError``
    naming the offending matrix property (never a complex Cholesky). With ``repair=True``
    the matrix is symmetrized and/or projected to the nearest PSD matrix instead.
    ``symmetry_tol`` gates the asymmetry check; ``psd_tol`` scales the minimum-eigenvalue
    gate (relative to the matrix's diagonal magnitude).

    With ``repair=True`` *any* negative minimum eigenvalue is clipped to exactly PSD
    (via :func:`_nearest_psd`) before the matrix reaches the native Cholesky, including
    one within ``psd_tol`` of zero: the native factorization has no tolerance of its own
    and rejects even a tiny negative pivot, so passing such a matrix through unrepaired
    would defeat ``repair=True``. With ``repair=False`` only a minimum eigenvalue below
    ``-tol`` raises here; a tiny negative eigenvalue *within* ``psd_tol`` is intentionally
    passed through unmodified (Property 61's gate is deliberately loose there) and *may
    still be rejected downstream* by the native Cholesky's exact (zero-tolerance) pivot
    check, surfacing as :class:`~quantvolt.exceptions.NumericalError` rather than
    ``ValidationError`` — callers who need to allow such matrices through must use
    ``repair=True``.
    """
    c = np.ascontiguousarray(cov, dtype=np.float64)
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValidationError(f"cov must be a square 2-D matrix, got shape {c.shape}")
    if not bool(np.all(np.isfinite(c))):
        raise ValidationError("cov must be finite")
    asym = float(np.max(np.abs(c - c.T)))
    if asym > symmetry_tol:
        if not repair:
            raise ValidationError(
                f"cov must be symmetric (max asymmetry {asym:.3e}); "
                "pass repair=True to symmetrize and project to the nearest PSD matrix"
            )
        c = 0.5 * (c + c.T)
    sym = 0.5 * (c + c.T)
    min_eig = float(np.linalg.eigvalsh(sym).min())
    max_diag = float(np.max(np.abs(np.diag(sym))))
    tol = psd_tol * max(1.0, max_diag)
    if min_eig < -tol:
        if not repair:
            raise ValidationError(
                f"cov must be positive semidefinite (min eigenvalue {min_eig:.3e}); "
                "pass repair=True for a nearest-PSD projection"
            )
        c = _nearest_psd(c)
    elif min_eig < 0.0 and repair:
        # min_eig sits in (-tol, 0): within the Python gate's tolerance, but still a
        # genuine negative eigenvalue. Left alone, the native Cholesky factorization
        # has no tolerance of its own and rejects it as a negative pivot, so
        # repair=True must clip it to exactly PSD here rather than pass through
        # (Fix 3, verified: a matrix with min eigenvalue ~-1.6e-10 raised even with
        # repair=True because it never reached this branch).
        c = _nearest_psd(c)
    return np.ascontiguousarray(c, dtype=np.float64)


def simulate_correlated_forwards(
    z0: npt.ArrayLike,
    drift: npt.ArrayLike,
    cov: npt.ArrayLike,
    steps: int,
    path_count: int,
    seed: int,
    antithetic: bool = True,
    *,
    repair: bool = False,
    symmetry_tol: float = _SYMMETRY_TOL,
    psd_tol: float = _PSD_EIG_TOL,
) -> npt.NDArray[np.float64]:
    """Simulate correlated multi-commodity log-forward curves (Appendix A, GBM).

    Given the initial log-forward vector ``z0 = log F(0, ·)`` (flattened over the
    commodity/tenor state, dimension ``D``), a per-step drift ``μ`` (``drift``, length
    ``D``), and the assembled covariance ``C`` (``cov``, ``(D, D)``), each of ``steps``
    steps draws ``ε ~ N(0, I)`` and updates ``Z ← Z + μ + L·ε`` where ``L = chol(C)``
    (eqs A.9-A.13). Returns a ``float64`` array of shape ``(n_paths, steps + 1, D)``;
    record 0 of each path is ``z0``.

    Conventions (see ``rust/src/paths.rs``):

    * **Measure-agnostic.** The caller supplies ``μ`` under its own measure — physical
      ``P`` for VaR/scenarios, risk-neutral ``Q`` for pricing (where
      ``μ = -½·diag(C)`` makes the forward a martingale).
    * **Expired-tenor masking (eq A.5).** A state index with zero variance
      (``C[d, d] == 0``, i.e. ``sigma_d = 0``) is held fixed at ``z0[d]`` on every path and
      step — drift and noise both suppressed.
    * **Antithetic variates (default on).** Paths are drawn in ``(+ε, -ε)`` pairs; each
      pair counts as 2 toward ``path_count`` and an odd ``path_count`` rounds up.
    * **Determinism.** Identical inputs and ``seed`` give bit-identical paths across
      runs of the same native-extension build; the Rust RNG stream does not match
      NumPy's.

    PSD gate: a non-symmetric or non-PSD ``cov`` raises ``ValidationError`` naming the
    violated constraint; ``repair=True`` opts into a nearest-PSD (Higham
    eigenvalue-clipping) projection instead. ``symmetry_tol`` and ``psd_tol`` gate that
    check (defaults match the module's standard tolerances).
    """
    if not _HAVE_CORE:
        raise NativeExtensionError("quantvolt._core not built; run `maturin develop` (Task 62).")
    require_positive("symmetry_tol", symmetry_tol)
    require_positive("psd_tol", psd_tol)
    z = np.ascontiguousarray(z0, dtype=np.float64)
    mu = np.ascontiguousarray(drift, dtype=np.float64)
    _require_finite_vector("z0", z)
    d = int(z.shape[0])
    if mu.shape != (d,):
        raise ValidationError(f"drift must have shape ({d},) to match z0, got {mu.shape}")
    if not bool(np.all(np.isfinite(mu))):
        raise ValidationError("drift must be finite")
    c = _validate_covariance(cov, repair=repair, symmetry_tol=symmetry_tol, psd_tol=psd_tol)
    if c.shape != (d, d):
        raise ValidationError(f"cov must have shape ({d}, {d}) to match z0, got {c.shape}")
    require_integer_at_least("steps", steps, 1)
    require_integer_at_least("path_count", path_count, 1)
    require_integer_at_least("seed", seed, 0)
    try:
        return np.asarray(
            _core.simulate_correlated_forwards(z, mu, c, steps, path_count, seed, antithetic),
            dtype=np.float64,
        )
    except (ValueError, OverflowError) as error:
        raise NumericalError(str(error)) from error


def simulate_correlated_term_structure(
    request: CorrelatedSimulationRequest,
) -> npt.NDArray[np.float64]:
    """Simulate Appendix-A paths with step-specific dynamics and tenor activity.

    This is the source-faithful time-inhomogeneous counterpart to
    :func:`simulate_correlated_forwards`. It accepts a parameter object because the
    dynamics, sampling controls, and expiry mask form one related input clump.
    """
    if not _HAVE_CORE:
        raise NativeExtensionError("quantvolt._core not built; run `maturin develop`.")
    require_positive("symmetry_tol", request.symmetry_tol)
    require_positive("psd_tol", request.psd_tol)
    z0 = np.array(request.z0, dtype=np.float64, copy=True, order="C")
    drift = np.array(request.drift_steps, dtype=np.float64, copy=True, order="C")
    covariances = np.array(request.covariance_steps, dtype=np.float64, copy=True, order="C")
    _require_finite_vector("z0", z0)
    if drift.ndim != 2 or drift.shape[1] != z0.size or drift.shape[0] < 1:
        raise ValidationError(f"drift_steps must have shape (steps, {z0.size}), got {drift.shape}")
    steps, dimension = drift.shape
    if covariances.shape != (steps, dimension, dimension):
        raise ValidationError(
            "covariance_steps must have shape "
            f"({steps}, {dimension}, {dimension}), got {covariances.shape}"
        )
    if not bool(np.all(np.isfinite(drift))):
        raise ValidationError("drift_steps must be finite")
    validated = np.empty_like(covariances)
    for step in range(steps):
        validated[step] = _validate_covariance(
            covariances[step],
            repair=request.repair,
            symmetry_tol=request.symmetry_tol,
            psd_tol=request.psd_tol,
        )
    if request.active_steps is None:
        active = np.diagonal(validated, axis1=1, axis2=2) > 0.0
    else:
        active = np.array(request.active_steps, dtype=np.bool_, copy=True, order="C")
        if active.shape != (steps, dimension):
            raise ValidationError(
                f"active_steps must have shape ({steps}, {dimension}), got {active.shape}"
            )
        variance = np.diagonal(validated, axis1=1, axis2=2)
        if bool(np.any(active & (variance <= 0.0))):
            raise ValidationError("active_steps cannot activate a zero-variance coordinate")
    require_integer_at_least("path_count", request.path_count, 1)
    require_integer_at_least("seed", request.seed, 0)
    try:
        return np.asarray(
            _core.simulate_correlated_forwards_term(
                z0,
                drift,
                np.ascontiguousarray(validated),
                np.ascontiguousarray(active),
                request.path_count,
                request.seed,
                request.antithetic,
            ),
            dtype=np.float64,
        )
    except (ValueError, OverflowError) as error:
        raise NumericalError(str(error)) from error
