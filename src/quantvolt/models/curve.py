"""Forward curve value objects with round-trip serialisation.

A :class:`ForwardCurve` is a discrete term structure: exactly one
:class:`CurveNode` per delivery period, ordered strictly by period. Following
Tell-Don't-Ask, the curve carries only *intrinsic* behaviour — it answers
:meth:`~ForwardCurve.price_at` for its own periods and knows how to (de)serialise
its whole object graph. Cross-curve mathematics lives in the functional core, not
here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from .._validation import require_non_empty
from ..exceptions import MissingTenorError, ValidationError
from .commodity import CommodityConfig, Hub
from .schedule import DeliveryPeriod

# Prices are compared with this absolute tolerance in ``__eq__`` (Property 1);
# they are otherwise carried exactly and never rounded.
_PRICE_EQ_TOL = 1e-10
_VALID_STATUSES: frozenset[str] = frozenset({"observed", "interpolated"})


@dataclass(frozen=True, slots=True)
class CurveNode:
    """A single ``(period, price)`` point on a forward curve.

    ``status`` records whether the price was ``"observed"`` in the market or
    ``"interpolated"`` between observations. Prices may be negative — negative
    power prices are real in European power markets — so they are never rejected.
    """

    period: DeliveryPeriod
    price: float
    status: Literal["observed", "interpolated"]


@dataclass(frozen=True, slots=True, eq=False)
class ForwardCurve:
    """A discrete forward curve: one node per delivery period, ordered by period.

    Consistency invariants, validated eagerly in :meth:`__post_init__`:

    - ``nodes`` is non-empty.
    - Nodes are strictly increasing by :class:`DeliveryPeriod` (reusing the period's
      own ordering), so there are no duplicate periods.
    - Every node's ``status`` is one of ``{"observed", "interpolated"}``.

    Prices are *not* constrained: negative forward prices occur in European power
    markets and are accepted verbatim.

    Equality is tolerance-based (see :meth:`__eq__`), so ``eq=False`` disables the
    dataclass-generated comparison and this class supplies its own ``__eq__`` /
    ``__hash__`` pair.
    """

    commodity: CommodityConfig
    market_date: date
    nodes: tuple[CurveNode, ...]  # ordered strictly by period

    def __post_init__(self) -> None:
        require_non_empty("nodes", self.nodes)
        for node in self.nodes:
            if node.status not in _VALID_STATUSES:
                raise ValidationError(
                    f"node status must be one of {sorted(_VALID_STATUSES)}, "
                    f"got {node.status!r} for period {node.period!r}"
                )
        for index, (prev, curr) in enumerate(zip(self.nodes, self.nodes[1:], strict=False)):
            if prev.period >= curr.period:
                raise ValidationError(
                    "nodes must be strictly increasing by period with no duplicate "
                    f"periods; offending pair at index {index}: {prev.period!r} is "
                    f"not before {curr.period!r}"
                )

    def price_at(self, period: DeliveryPeriod) -> float:
        """Return the price of the node whose period equals ``period``.

        This is a *discrete* lookup: the curve holds exactly one node per delivery
        period, so a ``period`` with no matching node raises
        :class:`MissingTenorError` naming the period and the curve's covered range.
        No interpolation is performed.
        """
        for node in self.nodes:
            if node.period == period:
                return node.price
        raise MissingTenorError(
            f"no forward-curve node for period {period!r}; covered range "
            f"[{self.nodes[0].period!r}, {self.nodes[-1].period!r}]"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialise the whole object graph to JSON-friendly built-ins.

        The commodity (with its hub), ``market_date`` (as an ISO-8601 string) and
        every node (period as ``{year, month}``, price and status) are written
        inline, so the result round-trips through :meth:`from_dict` to an equal
        curve.
        """
        hub = self.commodity.hub
        return {
            "commodity": {
                "commodity_id": self.commodity.commodity_id,
                "price_unit": self.commodity.price_unit,
                "hub": {
                    "hub_id": hub.hub_id,
                    "exchange": hub.exchange,
                    "price_unit": hub.price_unit,
                },
            },
            "market_date": self.market_date.isoformat(),
            "nodes": [
                {
                    "period": {"year": node.period.year, "month": node.period.month},
                    "price": node.price,
                    "status": node.status,
                }
                for node in self.nodes
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ForwardCurve:
        """Reconstruct a :class:`ForwardCurve` from :meth:`to_dict` output.

        Rebuilds the exact commodity, hub and node objects; ``from_dict(c.to_dict())``
        equals ``c``. ``data`` is only read, never mutated.
        """
        commodity_data = data["commodity"]
        hub_data = commodity_data["hub"]
        commodity = CommodityConfig(
            commodity_id=commodity_data["commodity_id"],
            price_unit=commodity_data["price_unit"],
            hub=Hub(
                hub_id=hub_data["hub_id"],
                exchange=hub_data["exchange"],
                price_unit=hub_data["price_unit"],
            ),
        )
        nodes = tuple(
            CurveNode(
                period=DeliveryPeriod(
                    year=node_data["period"]["year"],
                    month=node_data["period"]["month"],
                ),
                price=node_data["price"],
                status=node_data["status"],
            )
            for node_data in data["nodes"]
        )
        return cls(
            commodity=commodity,
            market_date=date.fromisoformat(data["market_date"]),
            nodes=nodes,
        )

    def __eq__(self, other: object) -> bool:
        """Tolerance-aware equality.

        Two curves are equal iff they share the same commodity and market date and
        have node-for-node identical periods and statuses with prices equal to
        within ``1e-10``. Any structural mismatch (different length, period or
        status) is unequal regardless of prices.
        """
        if not isinstance(other, ForwardCurve):
            return NotImplemented
        if self.commodity != other.commodity or self.market_date != other.market_date:
            return False
        if len(self.nodes) != len(other.nodes):
            return False
        for own, their in zip(self.nodes, other.nodes, strict=False):
            if own.period != their.period or own.status != their.status:
                return False
            if abs(own.price - their.price) > _PRICE_EQ_TOL:
                return False
        return True

    def __hash__(self) -> int:
        """Hash only the exactness-preserving fields, consistent with :meth:`__eq__`.

        Prices are excluded because equality is tolerance-based; the remaining
        fields (commodity, market date, node periods) are identical for any two
        equal curves, so ``a == b`` implies ``hash(a) == hash(b)``.
        """
        return hash((self.commodity, self.market_date, tuple(node.period for node in self.nodes)))
