"""Interpolation kernels (Strategy via Protocol + dispatch dict) — Task 13.

Pure array algorithms over a numeric time axis (months-from-market-date). The
strategy seam is a :class:`typing.Protocol` and each method is a module-level
function; callers select one via the :data:`INTERPOLATION_METHODS` dispatch
``dict`` (Strategy realised as functions — see ``steering/coding-style.md``).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray
from scipy.interpolate import CubicSpline  # type: ignore[import-untyped]

from ..exceptions import NumericalError


class InterpolationMethod(Protocol):
    def __call__(
        self,
        knot_times: NDArray[np.float64],
        knot_prices: NDArray[np.float64],
        query_times: NDArray[np.float64],
    ) -> NDArray[np.float64]: ...


def piecewise_flat(
    knot_times: NDArray[np.float64],
    knot_prices: NDArray[np.float64],
    query_times: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Step function: each query holds the price of the nearest knot at-or-below it.

    A query landing exactly on a knot takes that knot's price; a query before the
    first knot takes the first knot's price; a query past the last knot holds the
    last knot's price. Vectorised via :func:`numpy.searchsorted` (no Python loops).
    """
    # side="right" then -1 gives the index of the last knot <= query; clip the
    # -1 produced for pre-first-knot queries up to the first knot.
    indices = np.searchsorted(knot_times, query_times, side="right") - 1
    indices = np.clip(indices, 0, None)
    return np.asarray(knot_prices[indices], dtype=np.float64)


def piecewise_linear(
    knot_times: NDArray[np.float64],
    knot_prices: NDArray[np.float64],
    query_times: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Linear interpolation between knots via :func:`numpy.interp`.

    Queries outside the knot range are clamped to the nearest endpoint value.
    """
    return np.asarray(np.interp(query_times, knot_times, knot_prices), dtype=np.float64)


# Boundary conditions scipy's CubicSpline accepts as a plain string (a tuple form
# for per-side derivative conditions also exists upstream but is out of scope for
# this string-typed parameter).
_BC_TYPES = frozenset({"not-a-knot", "periodic", "clamped", "natural"})


def cubic_spline(
    knot_times: NDArray[np.float64],
    knot_prices: NDArray[np.float64],
    query_times: NDArray[np.float64],
    *,
    bc_type: str = "natural",
) -> NDArray[np.float64]:
    """Cubic spline through the knots via :class:`scipy.interpolate.CubicSpline`.

    ``bc_type`` selects the boundary condition (default ``"natural"``, which sets
    the second derivative to zero at both ends). The spline passes through every
    knot exactly regardless of ``bc_type``.

    Args:
        knot_times: Strictly increasing knot times.
        knot_prices: Knot prices, same length as ``knot_times``.
        query_times: Times at which to evaluate the spline.
        bc_type: One of ``"not-a-knot"``, ``"periodic"``, ``"clamped"``,
            ``"natural"`` — the boundary condition passed to
            :class:`scipy.interpolate.CubicSpline`.

    Raises:
        NumericalError: If ``bc_type`` is not one of the supported string values,
            or if :class:`scipy.interpolate.CubicSpline` itself rejects the knots
            (e.g. non-increasing ``knot_times``, mismatched lengths, too few knots,
            or mismatched periodic endpoints) — mirroring
            :func:`~quantvolt.numerics.rootfind.brent_root`'s wrapping of scipy
            errors, so no raw ``ValueError`` escapes this package's exception
            hierarchy.
    """
    if bc_type not in _BC_TYPES:
        raise NumericalError(f"bc_type must be one of {sorted(_BC_TYPES)}, got {bc_type!r}")
    try:
        spline = CubicSpline(knot_times, knot_prices, bc_type=bc_type)
    except ValueError as error:
        raise NumericalError(str(error)) from error
    return np.asarray(spline(query_times), dtype=np.float64)


INTERPOLATION_METHODS: dict[str, InterpolationMethod] = {
    "piecewise_flat": piecewise_flat,
    "piecewise_linear": piecewise_linear,
    "cubic_spline": cubic_spline,
}
