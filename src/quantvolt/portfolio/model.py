"""Portfolio value objects — a Composite over heterogeneous instrument positions (Task 60).

``Portfolio`` realises the Composite intent with the lightest Python construct
(``coding-style.md`` §0/§2): a frozen tuple of positions plus native iteration, so
downstream valuation and risk code handles one position and many uniformly (Req 13.1).
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass, field

from ..exceptions import ValidationError
from ..models.greeks import Greeks
from ..models.instruments import ForwardContract, FuturesContract, SwapContract
from ..models.power_hedge import PowerHedgeContract
from ..models.ppa import PpaContract
from ..models.schedule import DeliveryPeriod

# Extensible union of what a portfolio can hold. Add options / tolling here as pricers are wired.
Instrument = (
    FuturesContract | ForwardContract | SwapContract | PpaContract | PowerHedgeContract
)


@dataclass(frozen=True, slots=True)
class Position:
    """A single held instrument, plus optional identity/tags. Notional lives on the instrument."""

    instrument: Instrument
    position_id: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PricedPosition:
    """A position after valuation — exactly what RiskEngine and mark_to_market consume.

    Invariants enforced at construction (eager boundary validation, ``coding-style.md`` §7):

    - ``npv`` must be finite. A NaN or ±inf NPV would silently poison every downstream
      aggregate (portfolio NPV, VaR loss quantiles), so it is rejected here with a
      :class:`~quantvolt.exceptions.ValidationError` naming ``npv``.
    - ``delta`` is defensively copied: the mapping is snapshot into a fresh ``dict`` at
      construction, so later mutation of the caller's dict cannot reach into this frozen
      value object. The stored copy is treated as immutable by convention from then on —
      nothing in the library writes to it. (``object.__setattr__`` is the sanctioned way
      to assign inside ``__post_init__`` of a frozen dataclass and works with ``slots``.)
    - ``reference_prices`` is defensively copied the same way. It optionally records the
      forward price level ``value_portfolio`` observed for each ``delta`` entry's
      ``(commodity_id, delivery period)`` key, in the same units as that commodity's
      forward curve. ``RiskEngine.apply_scenario`` needs this to correctly scale a
      *relative* (fractional) scenario shock into currency P&L
      (``delta x reference_price x shock`` — see :mod:`quantvolt.risk.scenarios`); a key
      absent from ``reference_prices`` (including an entirely empty mapping, the default)
      falls back to a reference price of ``1.0``, preserving the legacy
      ``delta x shock`` behaviour for hand-built positions that never populate it.
    """

    position: Position
    npv: float
    # Delta exposure keyed by (commodity_id, delivery period), for risk aggregation / VaR.
    delta: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict)
    greeks: Greeks | None = None
    # Forward price observed for each `delta` key, for scenario P&L scaling (see above).
    reference_prices: dict[tuple[str, DeliveryPeriod], float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.npv):
            raise ValidationError(f"npv must be finite, got {self.npv!r}")
        object.__setattr__(self, "delta", dict(self.delta))
        object.__setattr__(self, "reference_prices", dict(self.reference_prices))


@dataclass(frozen=True, slots=True)
class Portfolio:
    """An immutable, iterable Composite of positions — one and many handled uniformly.

    Satisfies Req 13.1: an ordered, immutable collection whose positions can be iterated
    and counted without mutation — ``__iter__`` delegates to the underlying tuple in
    construction order and ``__len__`` counts without side effects.
    """

    positions: tuple[Position, ...]
    name: str | None = None

    def __iter__(self) -> Iterator[Position]:
        return iter(self.positions)

    def __len__(self) -> int:
        return len(self.positions)
