"""Root-finding and finite differences.

Pure numeric kernels: ``float`` in, ``float`` out. No domain types and no
domain validation live here. Numerical precondition and convergence failures use
:class:`~quantvolt.exceptions.NumericalError`, which remains compatible with
``ValueError`` while belonging to the package-wide error hierarchy.
"""

from __future__ import annotations

from collections.abc import Callable

from scipy.optimize import brentq  # type: ignore[import-untyped]

from ..exceptions import NumericalError


def brent_root(
    f: Callable[[float], float], a: float, b: float, tol: float = 1e-4, max_iter: int = 100
) -> float:
    """Find a root of ``f`` in ``[a, b]`` via Brent's method.

    Thin wrapper over :func:`scipy.optimize.brentq`. Brent's method is a
    bracketing solver, chosen over Newton-Raphson for implied-vol inversion so
    that it cannot diverge near zero vega.

    Args:
        f: Continuous scalar function to solve ``f(x) == 0``.
        a: Lower bracket endpoint.
        b: Upper bracket endpoint.
        tol: Absolute x-tolerance (``xtol``) for convergence.
        max_iter: Maximum number of iterations (``maxiter``).

    Returns:
        The located root ``x`` in ``[a, b]``.

    Raises:
        NumericalError: If ``f(a)`` and ``f(b)`` share the same sign and therefore
            do not bracket a root.
    """
    # brentq itself evaluates f(a) and f(b) to check the bracket, and raises
    # ValueError if they share a sign; pre-evaluating them here first (as a
    # previous version of this function did) double-counted those two
    # evaluations for any caller counting objective calls (e.g.
    # pricing.implied_vol.implied_vol's iteration_count), so the bracket is now
    # checked only inside brentq's own call.
    try:
        return float(brentq(f, a, b, xtol=tol, maxiter=max_iter))
    except ValueError as error:
        if "different signs" in str(error):
            # Re-evaluate the endpoints only on this (already-failing) path, to
            # preserve the previous, more informative message naming both
            # endpoint values.
            fa = f(a)
            fb = f(b)
            raise NumericalError(
                "f(a) and f(b) must have opposite signs to bracket a root; "
                f"got f({a}) = {fa} and f({b}) = {fb}"
            ) from error
        raise NumericalError(str(error)) from error


def finite_difference_bump(f: Callable[[float], float], x: float, bump: float) -> float:
    """Central difference: ``(f(x + bump) - f(x - bump)) / (2 * bump)``."""
    return (f(x + bump) - f(x - bump)) / (2.0 * bump)
