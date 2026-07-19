"""CurveBuilder — holds the commodity registry; builds forward curves.

The builder is a thin orchestrator: validate eagerly at the
boundary, gap-fill via the selected ``numerics.interpolation`` kernel, check
arbitrage, then package. The interpolation math lives in ``numerics/`` and the
method is selected through the ``INTERPOLATION_METHODS`` dispatch dict, no
``if/elif`` chain. ``CurveBuildResult`` is co-located here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from .._validation import require_in_range
from ..exceptions import InsufficientDataError, ValidationError
from ..models.commodity import CommodityConfig, merge_commodities
from ..models.curve import CurveNode, ForwardCurve
from ..models.instruments import InstrumentPriceRecord
from ..models.schedule import DeliveryPeriod
from ..numerics.interpolation import INTERPOLATION_METHODS
from .arbitrage import ArbitrageWarning, check_arbitrage

# Minimum observed instruments each interpolation method needs (Req 1.8, Property 4).
_MIN_INSTRUMENTS: dict[str, int] = {
    "piecewise_flat": 1,
    "piecewise_linear": 2,
    "cubic_spline": 4,
}


@dataclass(frozen=True, slots=True)
class CurveBuildResult:
    """Outcome of a curve build: the curve, any arbitrage warnings, reprice residuals."""

    curve: ForwardCurve
    arbitrage_warnings: list[ArbitrageWarning]  # empty list if none
    reprice_residuals: dict[str, float]  # instrument_id -> abs(curve - input) price


def _monthly_grid(start: DeliveryPeriod, end: DeliveryPeriod) -> list[DeliveryPeriod]:
    """Every calendar month from ``start`` to ``end`` inclusive, in order."""
    start_index = start.year * 12 + (start.month - 1)
    end_index = end.year * 12 + (end.month - 1)
    return [
        DeliveryPeriod(year=index // 12, month=index % 12 + 1)
        for index in range(start_index, end_index + 1)
    ]


class CurveBuilder:
    """Config-holding class: merges BUILT_IN_COMMODITIES with caller extensions."""

    def __init__(self, extra_commodities: dict[str, CommodityConfig] | None = None) -> None:
        # Adapter seam (Req 1.6): caller entries merged over the built-ins.
        self._registry = merge_commodities(extra_commodities)

    def build(
        self,
        commodity: CommodityConfig,
        market_date: date,
        instruments: list[InstrumentPriceRecord],
        interpolation: Literal[
            "piecewise_flat", "piecewise_linear", "cubic_spline"
        ] = "piecewise_linear",
        tolerance: float = 0.01,
        storage_cost: float = 0.0,
    ) -> CurveBuildResult:
        """Build a gap-filled forward curve from observed instrument prices.

        Validation is eager and strictly ordered *before* any construction (fail
        loudly): interpolation method known -> minimum instrument count
        -> commodity supported -> tolerance in [0.001, 1.0] ->
        every instrument's commodity matches -> no two instruments repeat a
        delivery period (conflicting/duplicate quotes are a caller error, not a
        silent last-price-wins resolution). The minimum-count gate (>= 1 for all
        methods) also guarantees ``instruments`` is non-empty, and rejecting
        duplicates first guarantees the number of *unique* delivery periods can
        never silently fall below the interpolation method's minimum either.
        AFTER construction, every input instrument must reprice within
        ``tolerance``; a :class:`ValidationError` naming every offending
        instrument and its residual is raised rather than returning a curve that
        silently fails this guarantee.
        """
        if interpolation not in INTERPOLATION_METHODS:
            raise ValidationError(
                f"interpolation must be one of {sorted(INTERPOLATION_METHODS)}, "
                f"got {interpolation!r}"
            )
        # 1) minimum instrument count for the selected method (Req 1.8).
        minimum = _MIN_INSTRUMENTS[interpolation]
        if len(instruments) < minimum:
            raise InsufficientDataError(
                f"interpolation {interpolation!r} requires at least {minimum} "
                f"instrument(s), got {len(instruments)}"
            )
        # 2) commodity supported in the built-in or caller-extension registry (Req 1.6).
        if commodity.commodity_id not in self._registry:
            available = ", ".join(sorted(self._registry))
            raise ValidationError(
                f"commodity_id {commodity.commodity_id!r} is not supported; "
                f"available ids: {available}"
            )
        # 3) tolerance within its documented range (Req 1.1).
        require_in_range("tolerance", tolerance, 0.001, 1.0)
        # Every instrument must belong to the commodity being built.
        for instrument in instruments:
            if instrument.commodity.commodity_id != commodity.commodity_id:
                raise ValidationError(
                    f"instrument {instrument.instrument_id!r} has commodity "
                    f"{instrument.commodity.commodity_id!r} but the curve is built "
                    f"for {commodity.commodity_id!r}"
                )
        # 4) no two instruments repeat a delivery period (fail loudly rather than
        # silently discarding one quote by dict-collapse last-price-wins).
        instrument_ids_by_period: dict[DeliveryPeriod, list[str]] = {}
        for instrument in instruments:
            instrument_ids_by_period.setdefault(instrument.delivery_period, []).append(
                instrument.instrument_id
            )
        duplicated_periods = {
            period: ids for period, ids in instrument_ids_by_period.items() if len(ids) > 1
        }
        if duplicated_periods:
            details = "; ".join(
                f"{period!r}: {ids!r}" for period, ids in sorted(duplicated_periods.items())
            )
            raise ValidationError(
                "instruments must not repeat a delivery period; conflicting or "
                f"duplicate quotes are a caller error, got duplicates for {details}"
            )

        curve = self._assemble_curve(commodity, market_date, instruments, interpolation)
        warnings = check_arbitrage(curve, storage_cost)
        residuals = {
            instrument.instrument_id: abs(
                curve.price_at(instrument.delivery_period) - instrument.price
            )
            for instrument in instruments
        }
        # Req 1.1: the curve must reprice every input instrument within tolerance;
        # fail loudly (naming every offending instrument) rather than silently
        # accepting a curve that violates the documented repricing guarantee.
        offending = {
            instrument_id: residual
            for instrument_id, residual in residuals.items()
            if residual > tolerance
        }
        if offending:
            details = ", ".join(
                f"{instrument_id!r} (residual {residual!r})"
                for instrument_id, residual in sorted(offending.items(), key=lambda item: -item[1])
            )
            raise ValidationError(
                f"tolerance {tolerance!r} exceeded for {len(offending)} instrument(s): {details}"
            )
        return CurveBuildResult(
            curve=curve, arbitrage_warnings=warnings, reprice_residuals=residuals
        )

    @staticmethod
    def _assemble_curve(
        commodity: CommodityConfig,
        market_date: date,
        instruments: list[InstrumentPriceRecord],
        interpolation: str,
    ) -> ForwardCurve:
        """Gap-fill the monthly grid and annotate observed vs interpolated."""
        observed: dict[DeliveryPeriod, float] = {
            instrument.delivery_period: instrument.price for instrument in instruments
        }
        knot_periods = sorted(observed)
        grid = _monthly_grid(knot_periods[0], knot_periods[-1])

        def months_from_market(period: DeliveryPeriod) -> float:
            # Whole months from the market date; monotone in period so the axis is sorted.
            return float((period.year - market_date.year) * 12 + (period.month - market_date.month))

        knot_times: NDArray[np.float64] = np.array(
            [months_from_market(period) for period in knot_periods], dtype=np.float64
        )
        knot_prices: NDArray[np.float64] = np.array(
            [observed[period] for period in knot_periods], dtype=np.float64
        )
        query_times: NDArray[np.float64] = np.array(
            [months_from_market(period) for period in grid], dtype=np.float64
        )

        # Strategy selection via dispatch dict (no if/elif); vectorised single call.
        interpolate = INTERPOLATION_METHODS[interpolation]
        filled = interpolate(knot_times, knot_prices, query_times)

        nodes = tuple(
            CurveNode(period, observed[period], "observed")
            if period in observed
            else CurveNode(period, float(filled[position]), "interpolated")
            for position, period in enumerate(grid)
        )
        return ForwardCurve(commodity=commodity, market_date=market_date, nodes=nodes)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ForwardCurve:
        return ForwardCurve.from_dict(data)
