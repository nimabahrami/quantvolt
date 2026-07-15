"""Variance-minimizing & cross-commodity hedges (Task 69, Requirement 18).

Incomplete-market hedging kernels for the case where a position's risk is only
partially spanned by traded instruments (Chapter 10, "Hedging"):

- :func:`variance_min_hedge` -- the multi-instrument local variance-minimizing
  hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54). Uses an explicit
  conditioning check plus :func:`numpy.linalg.solve`; a singular / ill-conditioned
  ``Σ_hh`` raises :class:`~quantvolt.exceptions.ValidationError` rather than
  silently falling back to a pseudo-inverse.
- :func:`linear_cross_hedge` -- the linear two-asset cross-commodity hedge ratio
  ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2). The one-instrument special case of the
  variance-minimizing hedge.
- :func:`decomposed_delta` -- the incomplete-market delta ``∂Ṽ/∂F`` (eq 10.17)
  when a non-linear structure is decomposed into a hedgeable component and an
  uncorrelated unhedgeable basis (eq 10.15) whose expectation is taken under an
  *explicit corporate* risk adjustment (eq 10.16, Req 18.3 / 18.6, Property 55).

**Measure discipline (Req 18.6).** The unhedgeable basis is, by construction, not
spanned by traded instruments, so there is no market price of risk to imply for
it. Its expectation therefore requires an explicit *corporate* risk preference
(eq 10.16 text: "it requires explicit corporate risk preferences"). Rather than
accept a bare float with implicit meaning, :func:`decomposed_delta` routes this
choice through the Task 63 :class:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind`
vocabulary and *requires* :attr:`PriceOfRiskKind.CORPORATE`; a
:attr:`PriceOfRiskKind.MARKET` (risk-neutral) kind is rejected.

House-style note: unlike the pure ``numerics/`` kernels, these public hedging
entry points validate their inputs up front through the shared
:mod:`quantvolt._validation` helpers and raise
:class:`~quantvolt.exceptions.ValidationError`, matching the ``risk/`` numpy
validation style.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from .._validation import require_correlation, require_positive
from ..exceptions import ValidationError
from ..numerics.risk_adjustment import PriceOfRiskKind
from ..numerics.rootfind import finite_difference_bump

#: Upper bound on the 2-norm condition number of ``Σ_hh`` before it is treated as
#: numerically singular. ``1/eps`` is the point past which the linear solve loses
#: all significant digits, so beyond it a returned hedge would be meaningless.
_CONDITION_LIMIT: float = 1.0 / np.finfo(np.float64).eps


def variance_min_hedge(
    sigma_hh: NDArray[np.float64],
    sigma_ht: NDArray[np.float64],
    *,
    condition_limit: float = _CONDITION_LIMIT,
) -> NDArray[np.float64]:
    """Variance-minimizing hedge ratios ``h* = Σ_hh⁻¹ Σ_ht`` (Req 18.1, Property 54).

    Given a target exposure and ``n`` hedge instruments described by their return
    covariance with the target (``Σ_ht``) and with each other (``Σ_hh``), returns
    the ratios ``h*`` that minimise the local variance of the hedged position.
    ``h*`` solves the normal-equation system ``Σ_hh·h* = Σ_ht``.

    The system is solved with :func:`numpy.linalg.solve` after an explicit
    conditioning check: a singular or ill-conditioned ``Σ_hh`` raises rather than
    silently returning a pseudo-inverse solution (a pseudo-inverse would hide the
    fact that the hedge instruments are collinear and the ratios are not
    identified).

    Args:
        sigma_hh: The ``(n, n)`` covariance matrix of the hedge instruments with
            each other. Must be square, symmetric, finite and non-singular.
        sigma_ht: The length-``n`` covariance vector of the hedge instruments with
            the target exposure. Must be conformable with ``sigma_hh``.
        condition_limit: Upper bound on the 2-norm condition number of ``sigma_hh``
            before it is treated as numerically singular; defaults to ``1/eps``, the
            point past which the linear solve loses all significant digits.

    Returns:
        The ``(n,)`` ``float64`` array of variance-minimizing hedge ratios. For a
        single instrument (``n == 1``) this collapses to
        :func:`linear_cross_hedge`'s ``rho·sigma_t/sigma_h`` (Property 54).

    Raises:
        ValidationError: If ``sigma_hh`` is not a non-empty square 2-D matrix, is
            not symmetric, contains non-finite values, is singular or
            ill-conditioned; if ``condition_limit`` is not strictly positive; or if
            ``sigma_ht`` is not a finite 1-D vector conformable with ``sigma_hh``.
    """
    hh = np.asarray(sigma_hh, dtype=np.float64)
    ht = np.asarray(sigma_ht, dtype=np.float64)

    if hh.ndim != 2 or hh.shape[0] != hh.shape[1]:
        raise ValidationError(
            f"sigma_hh must be a square 2-D covariance matrix, got shape {hh.shape}"
        )
    n = hh.shape[0]
    if n == 0:
        raise ValidationError("sigma_hh must be non-empty (at least one hedge instrument)")
    if not np.all(np.isfinite(hh)):
        raise ValidationError("sigma_hh must contain only finite values (no NaN or inf)")
    if not np.allclose(hh, hh.T):
        raise ValidationError(
            "sigma_hh must be symmetric (a covariance matrix), got a non-symmetric array"
        )
    if ht.ndim != 1 or ht.shape[0] != n:
        raise ValidationError(
            f"sigma_ht must be a 1-D vector conformable with sigma_hh: expected shape "
            f"({n},), got shape {ht.shape}"
        )
    if not np.all(np.isfinite(ht)):
        raise ValidationError("sigma_ht must contain only finite values (no NaN or inf)")
    require_positive("condition_limit", condition_limit)

    condition_number = float(np.linalg.cond(hh))
    if not np.isfinite(condition_number) or condition_number > condition_limit:
        raise ValidationError(
            f"sigma_hh is singular or ill-conditioned (2-norm condition number "
            f"{condition_number:.3e} exceeds the limit {condition_limit:.3e}): the "
            f"variance-minimizing system Σ_hh·h* = Σ_ht cannot be solved stably. No silent "
            f"pseudo-inverse is used -- supply hedge instruments whose covariance matrix is "
            f"non-singular (i.e. no perfectly collinear instruments)."
        )

    return np.asarray(np.linalg.solve(hh, ht), dtype=np.float64)


def linear_cross_hedge(rho: float, sigma_target: float, sigma_hedge: float) -> float:
    """Linear two-asset cross-commodity hedge ratio ``rho·sigma_t/sigma_h`` (eq 10.22, Req 18.2).

    The optimal local variance-minimizing hedge of one forward (the target, with
    volatility ``sigma_t``) with another (the hedge instrument, volatility ``sigma_h``)
    when the two follow jointly arithmetic Brownian motions with correlation
    ``rho`` (eq 10.21). For a linear product the hedge is constant in ``rho``, ``sigma_t``
    and ``sigma_h``. This is the one-instrument special case of
    :func:`variance_min_hedge`: with ``Σ_hh = [[sigma_h²]]`` and
    ``Σ_ht = [rho·sigma_t·sigma_h]``, ``Σ_hh⁻¹ Σ_ht = rho·sigma_t/sigma_h``.

    Args:
        rho: Correlation between the target and hedge returns, in ``(-1, 1)``.
        sigma_target: Volatility ``sigma_t`` of the target, strictly positive.
        sigma_hedge: Volatility ``sigma_h`` of the hedge instrument, strictly positive.

    Returns:
        The hedge ratio ``rho·sigma_t/sigma_h``.

    Raises:
        ValidationError: If ``rho`` is not in ``(-1, 1)`` or either volatility is
            not strictly positive.
    """
    require_correlation("rho", rho)
    require_positive("sigma_target", sigma_target)
    require_positive("sigma_hedge", sigma_hedge)
    return rho * sigma_target / sigma_hedge


def decomposed_delta(
    value_fn: Callable[[float, float], float],
    forward: float,
    basis_ra_expectation: float,
    bump: float,
    *,
    risk_adjustment: PriceOfRiskKind,
) -> float:
    """Incomplete-market delta ``∂Ṽ/∂F`` under a risk-adjusted basis expectation (eqs 10.15-10.18).

    For a non-linear structure whose payoff depends on a spot price decomposed
    into a hedgeable component and an *uncorrelated* unhedgeable basis (eq 10.15),
    the structure value is

        ``Ṽ(F) = df · E*[ E^RA_ε[Payoff] ]``    (eq 10.16)

    -- a risk-neutral expectation over the hedgeable forward ``F`` of a
    *risk-adjusted* expectation over the basis ``ε``. Because the basis is
    independent of ``F``, the local variance-minimizing hedge is simply

        ``Δ̃_t = ∂Ṽ(F)/∂F``    (eq 10.17)

    which this function computes by central finite difference in ``F`` (via
    :func:`quantvolt.numerics.rootfind.finite_difference_bump`), holding the
    risk-adjusted basis expectation fixed under the bump (it does not co-move with
    ``F``, by eq 10.15).

    **The Caller supplies the value function and the basis summary.** ``value_fn``
    takes ``(forward, basis_ra_expectation)`` and returns the scalar structure
    value ``Ṽ`` -- it closes over the payoff, discounting, and the risk-neutral
    expectation over ``F``. ``basis_ra_expectation`` is the *already-computed*
    risk-adjusted expectation of the unhedgeable basis (a scalar summary such as
    its risk-adjusted mean); passing the risk-adjusted expectation itself makes
    the corporate risk adjustment explicit at the call site.

    **Divergence from the complete-market delta (Req 18.6 / eq 10.18).** The
    complete-market delta ``Δ_t = ∂V/∂F`` (eq 10.14) is taken on the fully
    hedgeable value ``V = df · E*[Payoff]`` (eq 10.13), which knows nothing of the
    basis. The forms of eqs 10.14 and 10.17 are *identical*, but their values
    differ because eqs 10.13 and 10.16 differ whenever the basis has a non-zero
    mean or variance -- hence in general ``Δ̃_t ≠ Δ_t`` (eq 10.18, Property 55).
    Only for a *zero* basis (zero mean and variance) does ``E^RA_ε[Payoff] =
    Payoff``, so ``Ṽ = V`` and the two deltas coincide. For a *linear* product the
    basis enters ``Ṽ`` only as an additive constant in ``F``, so it drops out of
    the derivative and ``Δ̃_t`` reduces to ``rho·sigma_t/sigma_h`` regardless of the risk
    adjustment (Example 10.2, eq 10.25); for a non-linear product the basis
    couples to ``F`` and the delta genuinely shifts.

    **Explicit corporate risk adjustment (Req 18.6).** ``risk_adjustment`` is a
    required keyword routed through the Task 63
    :class:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind` vocabulary. Only
    :attr:`PriceOfRiskKind.CORPORATE` is accepted: the unhedgeable basis is not
    spanned by traded instruments, so a market/risk-neutral price of risk cannot
    be implied for it, and this function never silently assumes risk-neutrality.

    Args:
        value_fn: Callable ``(forward, basis_ra_expectation) -> Ṽ`` returning the
            risk-adjusted structure value (eq 10.16).
        forward: The hedgeable forward price ``F`` at which the delta is evaluated.
        basis_ra_expectation: The risk-adjusted expectation of the unhedgeable
            basis, held fixed while ``forward`` is bumped.
        bump: Strictly positive central-difference step in ``forward``.
        risk_adjustment: Provenance of the basis risk adjustment; must be
            :attr:`PriceOfRiskKind.CORPORATE` (Req 18.6).

    Returns:
        The incomplete-market delta ``∂Ṽ/∂F`` (eq 10.17).

    Raises:
        ValidationError: If ``value_fn`` is not callable, ``bump`` is not strictly
            positive, or ``risk_adjustment`` is not
            :attr:`PriceOfRiskKind.CORPORATE`.
    """
    if not callable(value_fn):
        raise ValidationError("value_fn must be callable: (forward, basis_ra_expectation) -> value")
    require_positive("bump", bump)
    if risk_adjustment != PriceOfRiskKind.CORPORATE:
        raise ValidationError(
            f"risk_adjustment must be {PriceOfRiskKind.CORPORATE!r} for the unhedgeable basis "
            f"of an incomplete-market hedge (Req 18.6): the basis is not spanned by traded "
            f"instruments, so its expectation E^RA requires an explicit corporate risk "
            f"preference and is never silently risk-neutral (eq 10.16); got {risk_adjustment!r}"
        )

    def value_at(f: float) -> float:
        return value_fn(f, basis_ra_expectation)

    return finite_difference_bump(value_at, forward, bump)
