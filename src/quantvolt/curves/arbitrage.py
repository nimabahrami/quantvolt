"""Arbitrage-violation detection for forward curves.

Storage (cost-of-carry) consistency rule
-----------------------------------------
For a *storable* commodity, carrying inventory forward costs ``storage_cost`` per
unit per month. That carry bounds how far the later (far) forward price may sit
*below* the earlier (near) forward price. Writing the calendar/time spread of a
consecutive pair ``p_early < p_late`` as *far minus near*::

    time_spread = price(p_late) - price(p_early)

the cost of carry can account for a near-to-far price decline of at most
``storage_cost * months_between`` — i.e. the no-arbitrage consistency condition is::

    time_spread >= -storage_cost * months_between(p_early, p_late)
    <=>  price(p_late) >= price(p_early) - storage_cost * months_between

A **violation** is a *negative time spread the carry cannot explain* — the far
contract priced below the near contract by more than the total storage cost::

    price(p_late) < price(p_early) - storage_cost * months_between - EPS

Such an unexplained near-to-far decline lets an operator lift the cheap far-dated
contract against the richer near-dated exposure, capturing the excess beyond
legitimate carry — a negative time spread inconsistent with storage.
Each offending consecutive pair is *localised* to its two identifiable nodes and
returned as an :class:`ArbitrageWarning`. Contango (far above near) and inversions
within the carry band are clean. With the default ``storage_cost=0.0`` any strict
price inversion between consecutive periods is flagged.

``EPS`` is a small absolute numerical guard so that a spread exactly at the carry
bound is treated as clean rather than a floating-point false positive.

Unattributable violations
--------------------------
When a node price is non-finite (``NaN`` / ``±inf``) the time spreads are undefined:
the curve is plainly inconsistent, yet no violation can be attributed to a specific
identifiable pair. This raises ``ArbitrageError`` rather than
silently returning a clean result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .._validation import require_non_negative, require_positive
from ..exceptions import ArbitrageError
from ..models.curve import ForwardCurve
from ..models.schedule import DeliveryPeriod

# Absolute numerical tolerance: spreads within EPS of the carry bound are clean.
_ARBITRAGE_EPS = 1e-9


@dataclass(frozen=True, slots=True)
class ArbitrageWarning:
    """A localised storage-arbitrage violation between identifiable curve nodes.

    ``periods`` holds the offending consecutive pair ``(p_early, p_late)``; ``message``
    describes the negative time spread and the cost of carry it exceeds.
    """

    periods: tuple[DeliveryPeriod, ...]
    message: str


def check_arbitrage(
    curve: ForwardCurve,
    storage_cost: float = 0.0,
    *,
    eps: float = _ARBITRAGE_EPS,
) -> list[ArbitrageWarning]:
    """Return one :class:`ArbitrageWarning` per consecutive pair violating carry.

    The exact inequality flagged for a consecutive pair ``p_early < p_late`` is::

        price(p_late) < price(p_early) - storage_cost * months_between - eps

    i.e. a negative time spread (far below near) steeper than the cost of carry
    can explain. Returns an empty list when the curve is clean.

    Args:
        curve: The forward curve to check.
        storage_cost: Cost of carry per unit per month, non-negative (default
            0.0: any strict price inversion is flagged).
        eps: Absolute numerical slack so a spread exactly at the carry bound
            is treated as clean rather than a floating-point false positive,
            positive (default ``1e-9``).

    Raises:
        ValidationError: If ``storage_cost`` is negative (or non-finite), or
            ``eps`` is not strictly positive.
        ArbitrageError: if any node price is non-finite, so time spreads are
            undefined and no violation can be attributed to identifiable nodes.
    """
    require_non_negative("storage_cost", storage_cost)
    require_positive("eps", eps)
    nodes = curve.nodes
    prices: NDArray[np.float64] = np.array([node.price for node in nodes], dtype=np.float64)

    finite_mask = np.isfinite(prices)
    if not bool(finite_mask.all()):
        non_finite = np.nonzero(~finite_mask)[0]
        bad_periods = tuple(nodes[int(index)].period for index in non_finite)
        raise ArbitrageError(
            "cannot check arbitrage: non-finite forward prices at periods "
            f"{bad_periods!r} make the calendar time spreads undefined, so a "
            "violation cannot be attributed to identifiable nodes"
        )

    # Numeric axis (whole-month index) is monotone in period; consecutive
    # differences give the far-minus-near spread and the month gap per pair.
    month_index: NDArray[np.float64] = np.array(
        [node.period.year * 12 + node.period.month for node in nodes], dtype=np.float64
    )
    time_spread = np.diff(prices)  # price(p_late) - price(p_early)
    months = np.diff(month_index)
    # slack >= 0 is clean; slack < 0 is a carry-unexplained negative spread.
    slack = time_spread + storage_cost * months
    offenders = np.nonzero(slack < -eps)[0]

    warnings: list[ArbitrageWarning] = []
    for index in offenders:
        early = nodes[int(index)]
        late = nodes[int(index) + 1]
        gap = int(month_index[int(index) + 1] - month_index[int(index)])
        allowance = storage_cost * gap
        warnings.append(
            ArbitrageWarning(
                periods=(early.period, late.period),
                message=(
                    "negative time spread inconsistent with storage: "
                    f"price({late.period!r})={late.price:.6g} is below "
                    f"price({early.period!r})={early.price:.6g} by "
                    f"{early.price - late.price:.6g}, exceeding the cost of carry "
                    f"{allowance:.6g} (storage_cost={storage_cost:.6g} over "
                    f"{gap} month(s))"
                ),
            )
        )
    return warnings


class ArbitrageChecker:
    """Thin class alias over ``check_arbitrage``.

    A stateless single-method class delegating to ``check_arbitrage``; kept
    only because it is part of the public facade and directly exercised by
    tests as ``ArbitrageChecker().check(...)``.
    """

    def check(
        self,
        curve: ForwardCurve,
        storage_cost: float = 0.0,
        *,
        eps: float = _ARBITRAGE_EPS,
    ) -> list[ArbitrageWarning]:
        """See :func:`check_arbitrage`."""
        return check_arbitrage(curve, storage_cost, eps=eps)
