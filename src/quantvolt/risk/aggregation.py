"""Delta aggregation grouped by commodity x delivery period.

``aggregate_delta`` nets position-level delta exposure into a dense matrix with one row
per commodity and one column per calendar-month delivery period. The
runtime import of :class:`~quantvolt.portfolio.model.PricedPosition` is the normal
inward dependency ``risk/`` → ``portfolio/``: risk consumes the priced book.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from ..models.schedule import DeliveryPeriod
from ..portfolio.model import PricedPosition


@dataclass(frozen=True, slots=True)
class DeltaMatrix:
    """Net delta exposure over the union grid of commodities x delivery periods.

    Rows (``commodities``) are sorted lexicographically; columns (``periods``) are
    sorted chronologically. The matrix is *dense* over that grid: every
    ``(commodity, period)`` combination inside the grid has a cell (0.0 where no
    position carries that exposure). Combinations outside the grid were never seen in
    any position, so :meth:`delta_at` answers 0.0 for them too — "not held" and "held
    with zero net delta" are the same exposure. The shape invariant (one row per
    commodity, one column per period) is validated at construction, mirroring how
    ``DeliverySchedule`` validates its own consistency.
    """

    commodities: tuple[str, ...]
    periods: tuple[DeliveryPeriod, ...]
    values: tuple[tuple[float, ...], ...]  # rows = commodities, cols = periods

    def __post_init__(self) -> None:
        if len(self.values) != len(self.commodities):
            raise ValidationError(
                "values must have exactly one row per commodity: "
                f"expected {len(self.commodities)} rows, got {len(self.values)}"
            )
        for index, row in enumerate(self.values):
            if len(row) != len(self.periods):
                raise ValidationError(
                    "values must have exactly one column per period: "
                    f"row {index} has {len(row)} columns, expected {len(self.periods)}"
                )

    def delta_at(self, commodity_id: str, period: DeliveryPeriod) -> float:
        """Net delta for one cell; 0.0 for a combination absent from the grid."""
        try:
            row = self.commodities.index(commodity_id)
            col = self.periods.index(period)
        except ValueError:
            return 0.0
        return self.values[row][col]


def aggregate_delta(positions: list[PricedPosition]) -> DeltaMatrix:
    """Net position-level delta by commodity (rows) x delivery period (cols).

    Each cell is the sum of that ``(commodity, period)`` delta across all positions.
    The grid is the sorted union of the key sets of every position's ``delta`` mapping:
    positions with an empty ``delta`` contribute nothing, and an empty ``positions``
    list yields the empty matrix (no rows, no columns). Inputs are never mutated —
    totals accumulate in a fresh dict and the result is built from new tuples.
    """
    totals: dict[tuple[str, DeliveryPeriod], float] = {}
    for position in positions:
        for key, exposure in position.delta.items():
            totals[key] = totals.get(key, 0.0) + exposure

    commodities = tuple(sorted({commodity for commodity, _ in totals}))
    periods = tuple(sorted({period for _, period in totals}))
    values = tuple(
        tuple(totals.get((commodity, period), 0.0) for period in periods)
        for commodity in commodities
    )
    return DeltaMatrix(commodities=commodities, periods=periods, values=values)
