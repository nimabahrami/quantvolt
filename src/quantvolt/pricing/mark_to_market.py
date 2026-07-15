"""Mark-to-market valuation (Tasks 37-38; Req 10; design §2.12).

Pure and deterministic: no timestamps, no mutable state, no randomness — re-running
the same call with identical inputs returns an identical result (idempotence,
Req 10.5 / Property 27). Price resolution realises the Chain-of-Responsibility
*intent* (coding-style.md §2) as an ordered-fallback function, not handler objects:
settlement price → same-commodity forward-curve node → :class:`NoPricingDataError`.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date
from typing import Literal

from .._validation import require_positive
from ..exceptions import MissingTenorError, NoPricingDataError
from ..models.curve import ForwardCurve
from ..models.schedule import DeliveryPeriod


@dataclass(frozen=True, slots=True)
class MtMPosition:
    """An open position to be marked to market (Req 10.1).

    ``prior_mark_price`` is the mark from the previous valuation date and
    ``trade_price`` the original contract price. Both may be negative — negative
    energy prices are real in European markets — but ``notional`` must be
    strictly positive (validated eagerly at construction).
    """

    commodity_id: str
    delivery_period: DeliveryPeriod
    notional: float
    trade_price: float
    prior_mark_price: float

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class MtMPositionResult:
    """Per-position mark, P&L pair, and how the mark was sourced (Req 10.1, 10.2)."""

    daily_pnl: float
    cumulative_pnl: float
    current_mark: float
    status: Literal["settled", "estimated"]


@dataclass(frozen=True, slots=True)
class MtMResult:
    """Per-position results in input order plus the count of estimated marks."""

    positions: tuple[MtMPositionResult, ...]
    estimated_count: int


def _resolve_mark(
    position: MtMPosition,
    settlement_prices: dict[tuple[str, DeliveryPeriod], float],
    forward_curve: ForwardCurve | None,
) -> tuple[float, Literal["settled", "estimated"]]:
    """Ordered price fallback (Chain-of-Responsibility intent, coding-style.md §2).

    1. Settlement price keyed by ``(commodity_id, delivery_period)`` → ``"settled"``.
    2. Otherwise a caller-supplied ``forward_curve`` *for the same commodity* whose
       node covers the period → ``"estimated"`` (Req 10.2). A curve for a different
       commodity never marks this position, and an absent node
       (:class:`MissingTenorError`) means the fallback is unavailable, not an answer.
    3. Otherwise raise :class:`NoPricingDataError` naming the commodity and delivery
       period — the position is never silently omitted (Req 10.3).
    """
    settlement = settlement_prices.get((position.commodity_id, position.delivery_period))
    if settlement is not None:
        return settlement, "settled"
    if forward_curve is not None and forward_curve.commodity.commodity_id == position.commodity_id:
        with contextlib.suppress(MissingTenorError):
            return forward_curve.price_at(position.delivery_period), "estimated"
    raise NoPricingDataError(
        f"no pricing data for commodity_id {position.commodity_id!r} and "
        f"delivery_period {position.delivery_period!r}: settlement_prices has no "
        "matching entry and no forward_curve for this commodity covers the period; "
        "supply a settlement price or a matching forward curve"
    )


def mark_to_market(
    positions: list[MtMPosition],
    market_date: date,
    settlement_prices: dict[tuple[str, DeliveryPeriod], float],
    forward_curve: ForwardCurve | None = None,
) -> MtMResult:
    """Mark each position to market and compute daily and cumulative P&L (Req 10).

    ``market_date`` documents the as-of date of the marks: ``settlement_prices``
    (and ``forward_curve``, if given) are the caller's pricing data for that date.
    All marks come solely from these inputs — the function reads no clock and keeps
    no state — so identical inputs always produce an identical result (Req 10.5).

    Each position's ``current_mark`` is resolved by ordered fallback: the
    settlement price for ``(commodity_id, delivery_period)``; else the node of a
    same-commodity ``forward_curve``, flagged ``"estimated"``; else
    :class:`NoPricingDataError`. P&L is then computed identically for settled and
    estimated marks (Req 10.1):

    - ``daily_pnl = (current_mark - prior_mark_price) * notional``
    - ``cumulative_pnl = (current_mark - trade_price) * notional``

    Results are returned in input order; ``estimated_count`` is the number of
    positions whose status is ``"estimated"``. An empty book yields an empty
    result. Inputs are never mutated.

    Raises:
        NoPricingDataError: If neither a settlement price nor a same-commodity
            forward-curve node is available for a position's ``(commodity_id,
            delivery_period)`` (Req 10.3).
    """
    results: list[MtMPositionResult] = []
    estimated_count = 0
    for position in positions:
        current_mark, status = _resolve_mark(position, settlement_prices, forward_curve)
        if status == "estimated":
            estimated_count += 1
        results.append(
            MtMPositionResult(
                daily_pnl=(current_mark - position.prior_mark_price) * position.notional,
                cumulative_pnl=(current_mark - position.trade_price) * position.notional,
                current_mark=current_mark,
                status=status,
            )
        )
    return MtMResult(positions=tuple(results), estimated_count=estimated_count)
