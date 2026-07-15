"""Portfolio valuation — dispatch each instrument to its pricer and aggregate (Task 61).

Composite (value the whole book) + Replace-Conditional-with-Dispatch (instrument type -> pricer).
New instrument kinds are supported by registering an entry — in :data:`DEFAULT_PRICERS` inside
the library, or per call via the ``pricers`` argument of :func:`value_portfolio` — never by
editing ``value_portfolio`` itself (open/closed, Req 13.4).

The produced :class:`~quantvolt.portfolio.model.PricedPosition` objects are exactly what
``risk.aggregation.aggregate_delta`` / ``RiskEngine`` and mark-to-market consume (Req 13.5),
so the flow is: instruments -> ``Portfolio`` -> ``value_portfolio`` -> ``PricedPosition`` ->
risk / mark-to-market.

Every built-in pricer also populates ``PricedPosition.reference_prices`` with the forward
curve price observed for each ``delta`` entry's ``(commodity_id, delivery period)`` key.
``RiskEngine.apply_scenario`` uses this to scale a *relative* named/user scenario shock
(:mod:`quantvolt.risk.scenarios`) into currency P&L (``delta x reference_price x shock``);
see that module and :mod:`quantvolt.risk.engine` for the full convention.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from ..exceptions import ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.instruments import (
    ForwardContract,
    FuturesContract,
    PipelineRight,
    SwapContract,
    TransmissionRight,
)
from ..models.schedule import DeliveryPeriod
from ..pricing.futures import price_futures
from ..pricing.swap import price_swap
from ..pricing.transmission_right import value_transport_right
from .model import Portfolio, Position, PricedPosition


@dataclass(frozen=True, slots=True)
class MarketData:
    """The market inputs needed to value a portfolio (Req 13.2).

    ``forward_curves`` is defensively copied into a fresh ``dict`` at construction
    (the ``object.__setattr__`` pattern used by ``PricedPosition``), so later mutation
    of the caller's mapping cannot reach into this frozen value object. The stored copy
    is treated as immutable by convention from then on — nothing in the library writes
    to it.
    """

    forward_curves: dict[str, ForwardCurve]  # keyed by commodity_id
    discount_curve: DiscountCurve
    valuation_date: date

    def __post_init__(self) -> None:
        object.__setattr__(self, "forward_curves", dict(self.forward_curves))

    def curve_for(self, commodity_id: str) -> ForwardCurve:
        """Return the forward curve for ``commodity_id``; raise if absent (Task 61).

        An intrinsic query (Tell-Don't-Ask): callers ask the market data for the
        curve instead of indexing into ``forward_curves`` themselves.

        Raises:
            ValidationError: If no curve is registered for ``commodity_id``, naming
                the missing commodity and listing the available ones.
        """
        curve = self.forward_curves.get(commodity_id)
        if curve is None:
            available = ", ".join(repr(key) for key in sorted(self.forward_curves)) or "none"
            raise ValidationError(
                f"market_data.forward_curves has no curve for commodity_id "
                f"{commodity_id!r}; available commodities: {available}"
            )
        return curve


@dataclass(frozen=True, slots=True)
class PortfolioValuation:
    """Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3)."""

    total_npv: float  # sum over ``priced`` only; ``unpriced`` never contributes
    priced: tuple[PricedPosition, ...]
    unpriced: tuple[Position, ...]  # instrument type had no registered pricer


# --- Dispatch: instrument type -> how to value one position (Task 61) ---

# A pricer adapter values one position against the market data. Registered per
# instrument type; adding a type means adding an entry, not editing value_portfolio.
Pricer = Callable[[Position, MarketData], PricedPosition]


def _price_forward_like(position: Position, market_data: MarketData) -> PricedPosition:
    """FuturesContract / ForwardContract via pricing.futures (Req 13.2)."""
    instrument = position.instrument
    if not isinstance(instrument, FuturesContract | ForwardContract):
        raise ValidationError(
            "position.instrument must be a FuturesContract or ForwardContract for "
            f"this pricer, got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    curve = market_data.curve_for(commodity_id)
    result = price_futures(
        instrument,
        curve,
        market_data.valuation_date,
        market_data.discount_curve,
    )
    period = instrument.delivery_period
    return PricedPosition(
        position=position,
        npv=result.npv,
        delta={(commodity_id, period): result.delta},
        reference_prices={(commodity_id, period): curve.price_at(period)},
    )


def _price_swap(position: Position, market_data: MarketData) -> PricedPosition:
    """SwapContract via pricing.swap — one delta entry per schedule period (Req 13.2)."""
    instrument = position.instrument
    if not isinstance(instrument, SwapContract):
        raise ValidationError(
            "position.instrument must be a SwapContract for this pricer, "
            f"got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    curve = market_data.curve_for(commodity_id)
    result = price_swap(instrument, curve, market_data.discount_curve)
    delta = {
        (commodity_id, period): period_delta
        for period, period_delta in zip(instrument.schedule.periods, result.delta, strict=True)
    }
    reference_prices = {
        (commodity_id, period): curve.price_at(period) for period in instrument.schedule.periods
    }
    return PricedPosition(
        position=position, npv=result.npv, delta=delta, reference_prices=reference_prices
    )


def _price_transport_right(position: Position, market_data: MarketData) -> PricedPosition:
    """TransmissionRight / PipelineRight via pricing.transmission_right (Req 24, Task 80).

    Prices the intrinsic transport value (market data carries no location vols, so no
    extrinsic term) over the shared periods of the origin (hub A) and destination
    (hub B) curves. The per-position ``delta`` carries one entry per (hub, period):
    ``delta_origin`` on the origin commodity and the opposite-signed ``delta_destination``
    on the destination — the right holder is short the origin and long the destination
    (module-level sign convention of :mod:`quantvolt.pricing.transmission_right`).
    """
    instrument = position.instrument
    if not isinstance(instrument, TransmissionRight | PipelineRight):
        raise ValidationError(
            "position.instrument must be a TransmissionRight or PipelineRight for this "
            f"pricer, got {type(instrument).__name__}"
        )
    origin_curve = market_data.curve_for(instrument.origin)
    destination_curve = market_data.curve_for(instrument.destination)
    result = value_transport_right(
        instrument,
        origin_curve,
        destination_curve,
        market_data.discount_curve,
    )
    delta: dict[tuple[str, DeliveryPeriod], float] = {}
    reference_prices: dict[tuple[str, DeliveryPeriod], float] = {}
    for period_value in result.per_period:
        period = period_value.period
        delta[(instrument.origin, period)] = period_value.delta_origin
        delta[(instrument.destination, period)] = period_value.delta_destination
        reference_prices[(instrument.origin, period)] = origin_curve.price_at(period)
        reference_prices[(instrument.destination, period)] = destination_curve.price_at(period)
    return PricedPosition(
        position=position, npv=result.total, delta=delta, reference_prices=reference_prices
    )


#: Built-in dispatch table: instrument type -> pricer adapter. A module-level constant,
#: **not** a Singleton (coding-style.md §3) and never mutated: ``value_portfolio`` merges
#: it with any caller-supplied ``pricers`` into a fresh dict per call, so registering an
#: extra instrument type needs no edit to this module (Req 13.4).
DEFAULT_PRICERS: dict[type[Any], Pricer] = {
    FuturesContract: _price_forward_like,
    ForwardContract: _price_forward_like,
    SwapContract: _price_swap,
    TransmissionRight: _price_transport_right,
    PipelineRight: _price_transport_right,
}


def value_portfolio(
    portfolio: Portfolio,
    market_data: MarketData,
    pricers: Mapping[type[Any], Pricer] | None = None,
) -> PortfolioValuation:
    """Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).

    The dispatch registry is :data:`DEFAULT_PRICERS` merged with the caller-supplied
    ``pricers`` (caller entries win) — the open/closed extension seam: new instrument
    types are registered, never edited in (Req 13.4). Positions are processed in
    portfolio order; a position whose instrument type has no registered pricer is
    returned in ``unpriced`` rather than raising, so the rest of the book is still
    valued, and ``total_npv`` sums the priced positions only (Req 13.3).

    Pricing errors — :class:`~quantvolt.exceptions.ExpiredContractError`,
    :class:`~quantvolt.exceptions.MissingTenorError`, a missing forward curve from
    :meth:`MarketData.curve_for` — **propagate**: they are data errors on a position
    the registry *does* know how to price, not registry misses, and silently skipping
    them would hide a mispriced book.

    Inputs are never mutated, and identical inputs produce identical results (Req 13.6).
    """
    registry: dict[type[Any], Pricer] = {**DEFAULT_PRICERS, **(pricers or {})}
    priced: list[PricedPosition] = []
    unpriced: list[Position] = []
    for position in portfolio.positions:
        pricer = registry.get(type(position.instrument))
        if pricer is None:
            unpriced.append(position)
        else:
            priced.append(pricer(position, market_data))
    return PortfolioValuation(
        total_npv=float(sum(p.npv for p in priced)),
        priced=tuple(priced),
        unpriced=tuple(unpriced),
    )
