"""Local & global mean-variance hedging (Task 70, Requirement 18.4).

Dynamic mean-variance hedging of a position whose risk is only partially spanned
by a traded instrument (Chapter 10, "Mean-Variance Optimization", source pages
25-26). The horizon is split into ``n`` rebalancing periods ``t = 0, ..., n-1``.
Over period ``t`` the *target* position has a random increment ``ΔV_t`` and the
traded *hedge instrument* has a random increment ``ΔH_t``. A hedging strategy
holds ``g_t`` units of the instrument over period ``t``; the hedged terminal P&L
is

    ``Π = ΔV_total - Σ_t g_t·ΔH_t``,   with ``ΔV_total = Σ_t ΔV_t``.

The full second-order structure of the increments is described by two matrices
(the *only* inputs both kernels need):

- ``cov_hedge`` -- the ``(n, n)`` auto-covariance matrix ``C`` of the hedge
  increments, ``C[s, t] = Cov(ΔH_s, ΔH_t)``. Its diagonal is ``Var(ΔH_t)``.
- ``cov_target_hedge`` -- the ``(n, n)`` cross-covariance matrix ``M`` with
  ``M[s, t] = Cov(ΔV_s, ΔH_t)`` (the target increment in period ``s`` against the
  hedge increment in period ``t``). This is a cross-covariance between *two
  different* processes and is **not** required to be symmetric.

**Local mean-variance (:func:`local_mean_variance`, the DEFAULT).** Minimise each
period's one-step variance ``Var(ΔV_t - g·ΔH_t)`` independently
(Föllmer-Sondermann, 1986). The minimiser is the per-period projection
coefficient

    ``g_local_t = Cov(ΔV_t, ΔH_t) / Var(ΔH_t) = M[t, t] / C[t, t]``.

It reads only the *diagonals* of ``M`` and ``C``. Because each period is a scalar
projection, the local hedge **always exists** whenever every per-period hedge
variance ``Var(ΔH_t) > 0`` -- it needs no matrix inversion and is unaffected by
cross-period correlations or by ``C`` being singular. This tractability and
guaranteed existence are why the local formulation is the default.

**Global mean-variance (:func:`global_mean_variance`).** Minimise the *total*
terminal variance ``Var(ΔV_total - gᵀ·ΔH)`` jointly over the whole strategy
vector ``g ∈ ℝⁿ``. Setting the gradient to zero gives the normal equations

    ``C·g = b``,   with ``b_t = Cov(ΔH_t, ΔV_total) = Σ_s M[s, t]``

(``b`` is the column-sum vector of ``M``), so ``g_global = C⁻¹·b``. This is the
more natural objective -- it targets overall exposure -- but the joint optimum
exists only when ``C`` is invertible (no perfectly collinear hedge increments
across periods). A singular / ill-conditioned ``C`` raises
:class:`~quantvolt.exceptions.ValidationError` naming the invertibility condition
rather than returning a meaningless pseudo-inverse solution.

**When local == global (Req 18.4).** ``g_global = C⁻¹·b`` collapses to
``g_local_t = M[t, t]/C[t, t]`` exactly when both ``C`` and ``M`` are **diagonal**
-- i.e. the increments are *uncorrelated across periods*. That holds under
**independent increments / a martingale hedge instrument** (disjoint-interval
increments are then uncorrelated, zeroing every off-diagonal of both matrices)
and, in particular, for a **linear payoff with constant correlation and
volatilities**. If either matrix carries off-diagonal mass -- serially correlated
(e.g. mean-reverting) hedge increments in ``C``, or cross-period target/hedge
covariance in ``M`` -- the global optimum exploits it and the two hedges diverge.

**Property 56 (linear-product triple identity).** For the two-asset linear
product of Example 10.2 -- ``dF_P = sigma_P·dW_P``, ``dF_G = sigma_G·dW_G``,
``dW_P·dW_G = rho·dt`` (eq 10.21) -- discretised into equal periods, independent
Brownian increments make both ``C = sigma_G²·Δt·I`` and ``M = rho·sigma_P·sigma_G·Δt·I``
diagonal, so every period's local and global ratio equals

    ``rho·sigma_P/sigma_G``   (eq 10.22),

the constant hedge of :func:`quantvolt.hedging.variance_min.linear_cross_hedge`.
Hence for a linear product ``local == global == rho·sigma_target/sigma_hedge``.

House-style note (matching :mod:`quantvolt.hedging.variance_min`): these public
entry points validate their inputs up front through
:mod:`quantvolt._validation` and raise
:class:`~quantvolt.exceptions.ValidationError`, and never mutate their inputs.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from .._validation import require_positive
from ..exceptions import ValidationError
from ._conditioning import CONDITION_LIMIT as _CONDITION_LIMIT
from ._conditioning import require_well_conditioned as _require_well_conditioned


def _validate_increment_covariances(
    cov_target_hedge: NDArray[np.float64], cov_hedge: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Validate and coerce the shared ``(M, C)`` increment second-moment inputs.

    Checks both are non-empty square 2-D matrices of the same size ``n``, contain
    only finite values, and that ``cov_hedge`` (``C``, an auto-covariance matrix)
    is symmetric. ``cov_target_hedge`` (``M``) is a cross-covariance between two
    different processes and is deliberately **not** required to be symmetric.

    Returns:
        ``(M, C)`` as fresh ``float64`` arrays (never the caller's objects).
    """
    m = np.asarray(cov_target_hedge, dtype=np.float64)
    c = np.asarray(cov_hedge, dtype=np.float64)

    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        raise ValidationError(
            f"cov_hedge must be a square 2-D covariance matrix, got shape {c.shape}"
        )
    n = c.shape[0]
    if n == 0:
        raise ValidationError("cov_hedge must be non-empty (at least one hedging period)")
    if m.shape != (n, n):
        raise ValidationError(
            f"cov_target_hedge must be conformable with cov_hedge: expected shape "
            f"({n}, {n}), got shape {m.shape}"
        )
    if not np.all(np.isfinite(c)):
        raise ValidationError("cov_hedge must contain only finite values (no NaN or inf)")
    if not np.all(np.isfinite(m)):
        raise ValidationError("cov_target_hedge must contain only finite values (no NaN or inf)")
    if not np.allclose(c, c.T):
        raise ValidationError(
            "cov_hedge must be symmetric (an auto-covariance matrix of the hedge increments), "
            "got a non-symmetric array"
        )
    return m, c


def local_mean_variance(
    cov_target_hedge: NDArray[np.float64], cov_hedge: NDArray[np.float64]
) -> NDArray[np.float64]:
    """Local (one-step) mean-variance hedge ratios -- the default (Req 18.4, Property 56).

    Minimises each rebalancing period's one-step variance ``Var(ΔV_t - g·ΔH_t)``
    separately (Föllmer-Sondermann, 1986), returning the per-period projection
    coefficients

        ``g_local_t = Cov(ΔV_t, ΔH_t) / Var(ΔH_t) = M[t, t] / C[t, t]``.

    Only the *diagonals* of the two input matrices are used, so the local hedge
    **always exists** whenever every per-period hedge variance is strictly
    positive -- it requires no matrix inversion and is indifferent to cross-period
    correlations or to ``cov_hedge`` being singular. This is why it is the default
    of the two mean-variance formulations.

    Args:
        cov_target_hedge: The ``(n, n)`` cross-covariance matrix ``M`` with
            ``M[s, t] = Cov(ΔV_s, ΔH_t)``. Only the diagonal ``M[t, t] =
            Cov(ΔV_t, ΔH_t)`` is read; it need not be symmetric.
        cov_hedge: The ``(n, n)`` auto-covariance matrix ``C`` of the hedge
            increments, ``C[s, t] = Cov(ΔH_s, ΔH_t)``. Must be square, symmetric
            and finite; only the diagonal ``C[t, t] = Var(ΔH_t)`` is read, and
            each diagonal entry must be strictly positive.

    Returns:
        The ``(n,)`` ``float64`` array of per-period local hedge ratios.

    Raises:
        ValidationError: If the inputs are not conformable non-empty square finite
            matrices, ``cov_hedge`` is not symmetric, or any per-period hedge
            variance ``Var(ΔH_t) = cov_hedge[t, t]`` is not strictly positive.
    """
    m, c = _validate_increment_covariances(cov_target_hedge, cov_hedge)

    var_hedge = np.diag(c)
    for t, variance in enumerate(var_hedge):
        require_positive(
            f"cov_hedge[{t}, {t}] (per-period hedge variance Var(ΔH_{t}))", float(variance)
        )

    return np.asarray(np.diag(m) / var_hedge, dtype=np.float64)


def global_mean_variance(
    cov_target_hedge: NDArray[np.float64],
    cov_hedge: NDArray[np.float64],
    *,
    condition_limit: float = _CONDITION_LIMIT,
) -> NDArray[np.float64]:
    """Global (total-horizon) mean-variance hedge ratios (Req 18.4, Property 56).

    Minimises the *total* terminal variance ``Var(ΔV_total - gᵀ·ΔH)`` jointly over
    the whole strategy vector ``g ∈ ℝⁿ`` (``ΔV_total = Σ_t ΔV_t``). The normal
    equations are

        ``C·g = b``,   with ``b_t = Cov(ΔH_t, ΔV_total) = Σ_s M[s, t]``,

    i.e. ``b`` is the column-sum vector of ``cov_target_hedge`` and
    ``g_global = C⁻¹·b``. Unlike the local hedge, the global optimum exists only
    when ``C`` is invertible; the system is solved with :func:`numpy.linalg.solve`
    after an explicit conditioning check, and a singular / ill-conditioned ``C``
    raises rather than returning a pseudo-inverse solution.

    Coincides with :func:`local_mean_variance` exactly when both ``M`` and ``C``
    are diagonal (uncorrelated increments across periods) -- e.g. under
    independent increments / a martingale hedge instrument, and in particular for
    a linear product with constant correlation and volatilities, where the common
    ratio is ``rho·sigma_target/sigma_hedge`` (eq 10.22, Property 56).

    Args:
        cov_target_hedge: The ``(n, n)`` cross-covariance matrix ``M`` with
            ``M[s, t] = Cov(ΔV_s, ΔH_t)``. Its column sums form the right-hand
            side ``b_t = Cov(ΔH_t, ΔV_total)``; it need not be symmetric.
        cov_hedge: The ``(n, n)`` auto-covariance matrix ``C`` of the hedge
            increments, ``C[s, t] = Cov(ΔH_s, ΔH_t)``. Must be square, symmetric,
            finite and non-singular.
        condition_limit: Upper bound on the 2-norm condition number of ``C`` before
            it is treated as numerically singular; defaults to ``1/eps``, the point
            past which the linear solve loses all significant digits.

    Returns:
        The ``(n,)`` ``float64`` array of global (total-horizon) hedge ratios.

    Raises:
        ValidationError: If the inputs are not conformable non-empty square finite
            matrices, ``cov_hedge`` is not symmetric, ``condition_limit`` is not
            strictly positive, or ``cov_hedge`` is singular / ill-conditioned (the
            joint variance-minimising strategy then does not exist).
    """
    m, c = _validate_increment_covariances(cov_target_hedge, cov_hedge)
    require_positive("condition_limit", condition_limit)

    _require_well_conditioned(
        c,
        condition_limit,
        lambda condition_number: (
            f"cov_hedge is singular or ill-conditioned (2-norm condition number "
            f"{condition_number:.3e} exceeds the limit {condition_limit:.3e}): the global "
            f"variance-minimising system C·g = b cannot be solved stably, so the joint "
            f"total-horizon strategy does not exist. No silent pseudo-inverse is used -- "
            f"supply hedge increments whose covariance matrix is non-singular (no perfectly "
            f"collinear increments across periods), or use local_mean_variance, which needs "
            f"only per-period variances and always exists."
        ),
    )

    b = m.sum(axis=0)
    return np.asarray(np.linalg.solve(c, b), dtype=np.float64)
