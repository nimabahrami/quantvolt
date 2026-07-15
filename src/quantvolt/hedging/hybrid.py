"""Hybrid-model power-price hedging (Task 71, Requirement 18.5).

A *hybrid* (structural) power-price model represents the power price ``p_t`` as a
**deterministic stack transformation** ``s^bid`` of fundamental drivers plus a
**stochastic residual** ``epsilon_t`` (Chapter 10, "Hedging with Hybrid Models",
eq 10.26):

    p_t = s^bid(D_t, g_t, l_t, Omega_t, E_t, S_t; OPC_t) + epsilon_t

where the dynamic drivers are system demand ``D_t``, the natural-gas price
``g_t``, the oil price ``l_t``, the outage vector ``Omega_t``, the emissions
prices ``E_t`` and the weather vector ``S_t``; ``OPC_t`` are the (deterministic)
operational characteristics of the generation stack that parameterise
``s^bid``. Each dynamic driver can in turn be written as a deterministic function
of *liquidly traded* instruments at expiration plus its own residual (eqs
10.27-10.28) -- e.g. gas as ``g(BOM, C_monthly, C_daily) + epsilon^g`` -- so the
whole price reduces to a payoff function of tradables plus residuals.

**Economics / measure discipline.** Hedging the tradable drivers hedges the
*model-explained* part of the price; the residual ``epsilon_t`` is the
**unhedgeable remainder** and is what makes the market incomplete (Req 18.5,
Req 18.6). Two things follow, and this module provides one kernel for each:

* The local variance-minimizing hedge ratios are the sensitivities of the
  deterministic stack to each tradable driver, obtained by the chain rule /
  Ito's lemma (source: "Ito's lemma ... gives the optimal local
  variance-minimizing dynamic hedge"). :func:`hybrid_deltas` computes these.
* The *quality* of a hybrid representation is measured by the size of its
  residual: "the smaller its variance, the better the representation" (source
  text after eq 10.28). :func:`residual_variance` computes this metric, and
  **smaller means a better hedge** (Property 57). In the limit of a zero residual
  variance the price is fully hedgeable and any derivative on it can be valued
  under the risk-neutral distributions of the tradables alone (source, after eq
  10.28); with a non-zero residual the hedge is only an *optimal statistical*
  (local variance-minimizing) hedge, and the residual's expectation -- where it
  is needed for valuation -- requires an explicit corporate risk adjustment
  (Req 18.6, handled by :func:`quantvolt.hedging.variance_min.decomposed_delta`,
  not here). :func:`residual_variance` is a physical-measure (``P``) descriptive
  statistic used only to *rank* representations, so it carries no risk
  adjustment of its own.

Following the ``hedging`` convention (see the package docstring), import these
kernels from this module directly, e.g.
``from quantvolt.hedging.hybrid import hybrid_deltas``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

from .._validation import require_non_empty, require_positive
from ..exceptions import InsufficientDataError, ValidationError
from ..numerics.rootfind import finite_difference_bump

#: A hybrid stack: the deterministic transformation ``s^bid`` mapping a mapping of
#: driver values ``{name: value}`` to the (scalar) power price (eq 10.26).
StackFn = Callable[[Mapping[str, float]], float]


def hybrid_deltas(stack_fn: StackFn, drivers: Mapping[str, float], bump: float) -> dict[str, float]:
    """Chain-rule deltas of a hybrid power-price model to each tradable driver (eq 10.26, Req 18.5).

    The hybrid price is ``p = s^bid(drivers) + epsilon`` (eq 10.26). The local
    variance-minimizing hedge to a tradable driver ``k`` is the partial derivative
    of the deterministic stack with respect to that driver, ``partial p / partial
    driver_k`` (the residual ``epsilon`` is, by construction, independent of the
    drivers and drops out of the derivative). Applying this to each driver gives,
    by the chain rule / Ito's lemma (source, after eq 10.28), the delta vector.

    When ``drivers`` are the tradable variables themselves -- or the tradable
    proxies through which the fundamental drivers are expressed (eqs 10.27-10.28,
    e.g. gas via its ``BOM`` / option contracts) -- each returned partial is
    directly the hedge ratio to that tradable. Each partial is one link of the
    chain rule; the total first-order price move is their sum,
    ``dp = sum_k (partial p / partial driver_k) d(driver_k)`` (Property 57,
    "chain-rule deltas sum consistently across drivers").

    Each partial is estimated by a central finite difference (via
    :func:`quantvolt.numerics.rootfind.finite_difference_bump`): each driver is
    bumped by ``+/- bump`` while the others are held fixed. Choose ``bump`` small
    relative to the driver's scale but large enough to avoid round-off; for an
    exactly linear stack the central difference is exact.

    The caller's ``drivers`` mapping is never mutated: a fresh mapping is built for
    every bumped evaluation.

    Args:
        stack_fn: The deterministic stack ``s^bid`` -- a pure callable mapping a
            driver mapping ``{name: value}`` to the scalar power price (eq 10.26).
        drivers: The current driver values ``{name: value}`` at which the deltas
            are evaluated. Must be non-empty.
        bump: Strictly positive central-difference step applied to each driver.

    Returns:
        A ``dict`` with one entry per driver name, mapping it to
        ``partial p / partial driver`` at ``drivers``.

    Raises:
        ValidationError: If ``stack_fn`` is not callable, ``bump`` is not strictly
            positive, or ``drivers`` is empty.
    """
    if not callable(stack_fn):
        raise ValidationError(
            "stack_fn must be callable: Mapping[str, float] -> power price (eq 10.26)"
        )
    require_positive("bump", bump)
    require_non_empty("drivers", drivers)

    deltas: dict[str, float] = {}
    for name, value in drivers.items():

        def bumped_stack(x: float, _name: str = name) -> float:
            # Fresh mapping each call: never mutate the caller's ``drivers``.
            perturbed = dict(drivers)
            perturbed[_name] = x
            return stack_fn(perturbed)

        deltas[name] = finite_difference_bump(bumped_stack, float(value), bump)
    return deltas


def residual_variance(
    stack_fn: StackFn,
    drivers: Mapping[str, Sequence[float]],
    realized: Sequence[float],
) -> float:
    """Hybrid hedge-quality metric: variance of the residual ``epsilon_t`` (eq 10.26, Req 18.5).

    From ``p_t = s^bid(drivers_t) + epsilon_t`` (eq 10.26) the residual is
    ``epsilon_t = p_t - s^bid(drivers_t)``. This applies the deterministic stack to
    each observation of the driver series, subtracts it from the realized power
    price, and returns the (unbiased, ``ddof=1``) sample variance of the residual.

    **Smaller is better** (Property 57). The residual is the unhedgeable part of
    the price; a representation that explains more of the price leaves a smaller
    residual, and "the smaller its variance, the better the representation"
    (source text after eq 10.28). A zero residual variance means the price is
    fully spanned by the drivers and is completely hedgeable. This metric ranks
    competing hybrid representations of the *same* realized price series; pass the
    same ``drivers`` / ``realized`` with different ``stack_fn`` transformations to
    compare them.

    This is a physical-measure (``P``) descriptive statistic and carries no risk
    adjustment (the risk-adjusted valuation of the unhedgeable residual lives in
    :func:`quantvolt.hedging.variance_min.decomposed_delta`, Req 18.6).

    The caller's inputs are never mutated.

    Args:
        stack_fn: The deterministic stack ``s^bid`` -- a pure callable mapping a
            per-observation driver mapping ``{name: value}`` to the scalar power
            price (eq 10.26).
        drivers: The driver series, column-oriented as ``{name: series}`` (the same
            driver keys ``stack_fn`` reads, each carrying one value per
            observation). Must be non-empty, and every series must have the same
            length as ``realized``.
        realized: The observed power prices ``p_t``, in observation order. At least
            two observations are required.

    Returns:
        The sample variance (``ddof=1``) of the residual
        ``epsilon_t = realized_t - s^bid(drivers_t)``.

    Raises:
        ValidationError: If ``stack_fn`` is not callable, ``drivers`` is empty,
            ``realized`` is not 1-D, or any driver series length does not match
            ``realized``.
        InsufficientDataError: If fewer than two observations are supplied (the
            ``n >= 2`` constraint required to estimate a sample variance).
    """
    if not callable(stack_fn):
        raise ValidationError(
            "stack_fn must be callable: Mapping[str, float] -> power price (eq 10.26)"
        )
    require_non_empty("drivers", drivers)

    realized_arr = np.asarray(realized, dtype=np.float64)
    if realized_arr.ndim != 1:
        raise ValidationError(
            f"realized must be a 1-D sequence of power prices, got ndim={realized_arr.ndim}"
        )
    n = int(realized_arr.size)
    if n < 2:
        raise InsufficientDataError(
            f"realized must have at least 2 observations (n >= 2) to estimate a sample "
            f"residual variance, got n={n}"
        )

    columns: dict[str, NDArray[np.float64]] = {}
    for name, series in drivers.items():
        col = np.asarray(series, dtype=np.float64)
        if col.ndim != 1:
            raise ValidationError(
                f"driver {name!r} series must be a 1-D sequence, got ndim={col.ndim}"
            )
        if col.size != n:
            raise ValidationError(
                f"driver {name!r} series has length {col.size}, expected {n} to match realized"
            )
        columns[name] = col

    stack_prices = np.array(
        [stack_fn({name: float(col[t]) for name, col in columns.items()}) for t in range(n)],
        dtype=np.float64,
    )
    residuals = realized_arr - stack_prices
    return float(np.var(residuals, ddof=1))
