"""Curve-construction correctness properties (design Properties 1-5; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``).
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.curves.builder import CurveBuilder
from quantvolt.exceptions import InsufficientDataError
from quantvolt.models.commodity import CommodityConfig
from quantvolt.models.curve import ForwardCurve
from quantvolt.models.instruments import InstrumentPriceRecord
from quantvolt.models.schedule import DeliveryPeriod
from strategies import (
    MARKET_DATES,
    commodity_configs,
    delivery_periods,
    forward_curves,
    instrument_price_record_lists,
)

_INTERPOLATIONS: tuple[str, ...] = ("piecewise_flat", "piecewise_linear", "cubic_spline")
_MIN_INSTRUMENTS: dict[str, int] = {
    "piecewise_flat": 1,
    "piecewise_linear": 2,
    "cubic_spline": 4,
}
# >= 4 instruments satisfies the minimum of every interpolation method.
_BUILD_INSTRUMENTS = instrument_price_record_lists(min_len=4, max_len=10)
_TOLERANCES = st.floats(min_value=0.001, max_value=1.0)


def _month_grid(first: DeliveryPeriod, last: DeliveryPeriod) -> list[DeliveryPeriod]:
    """Every calendar month from ``first`` to ``last`` inclusive (test-local oracle)."""
    start = first.year * 12 + first.month - 1
    end = last.year * 12 + last.month - 1
    return [
        DeliveryPeriod(year=index // 12, month=index % 12 + 1) for index in range(start, end + 1)
    ]


def _next_month(period: DeliveryPeriod) -> DeliveryPeriod:
    if period.month == 12:
        return DeliveryPeriod(year=period.year + 1, month=1)
    return DeliveryPeriod(year=period.year, month=period.month + 1)


def _record(
    instrument_id: str, commodity: CommodityConfig, period: DeliveryPeriod, price: float
) -> InstrumentPriceRecord:
    return InstrumentPriceRecord(
        instrument_id=instrument_id, commodity=commodity, delivery_period=period, price=price
    )


# Feature: power-energy-quant-analysis, Property 1: Forward Curve Reprice Consistency
@given(
    instruments=_BUILD_INSTRUMENTS,
    market_date=MARKET_DATES,
    interpolation=st.sampled_from(_INTERPOLATIONS),
    tolerance=_TOLERANCES,
)
@settings(max_examples=100)
def test_built_curve_reprices_every_input_instrument_within_tolerance(
    instruments: list[InstrumentPriceRecord],
    market_date: date,
    interpolation: str,
    tolerance: float,
) -> None:
    result = CurveBuilder().build(
        instruments[0].commodity,
        market_date,
        instruments,
        interpolation=interpolation,  # type: ignore[arg-type]
        tolerance=tolerance,
    )
    for instrument in instruments:
        reprice = result.curve.price_at(instrument.delivery_period)
        assert abs(reprice - instrument.price) <= tolerance
    # Observed nodes carry the input price verbatim, so residuals are exactly zero.
    assert set(result.reprice_residuals) == {i.instrument_id for i in instruments}
    for residual in result.reprice_residuals.values():
        assert residual == 0.0


# Feature: power-energy-quant-analysis, Property 2: Gap Filling and Node Annotation
@given(
    instruments=_BUILD_INSTRUMENTS,
    market_date=MARKET_DATES,
    interpolation=st.sampled_from(_INTERPOLATIONS),
)
@settings(max_examples=100)
def test_every_month_in_span_has_a_node_and_gap_months_are_interpolated(
    instruments: list[InstrumentPriceRecord],
    market_date: date,
    interpolation: str,
) -> None:
    result = CurveBuilder().build(
        instruments[0].commodity,
        market_date,
        instruments,
        interpolation=interpolation,  # type: ignore[arg-type]
    )
    observed_periods = {instrument.delivery_period for instrument in instruments}
    expected_grid = _month_grid(min(observed_periods), max(observed_periods))
    assert [node.period for node in result.curve.nodes] == expected_grid
    for node in result.curve.nodes:
        expected_status = "observed" if node.period in observed_periods else "interpolated"
        assert node.status == expected_status


# Feature: power-energy-quant-analysis, Property 3: Arbitrage Violation Detection
@given(
    commodity=commodity_configs(),
    market_date=MARKET_DATES,
    period=delivery_periods(),
    near_price=st.floats(min_value=-1_000.0, max_value=1_000.0),
    storage_cost=st.floats(min_value=0.0, max_value=50.0),
    excess=st.floats(min_value=0.5, max_value=100.0),
)
@settings(max_examples=100)
def test_inversion_beyond_storage_cost_is_flagged_with_offending_periods(
    commodity: CommodityConfig,
    market_date: date,
    period: DeliveryPeriod,
    near_price: float,
    storage_cost: float,
    excess: float,
) -> None:
    late_period = _next_month(period)
    # Far price below the near price by strictly more than one month of carry.
    late_price = near_price - storage_cost - excess
    instruments = [
        _record("near", commodity, period, near_price),
        _record("far", commodity, late_period, late_price),
    ]
    result = CurveBuilder().build(
        commodity,
        market_date,
        instruments,
        interpolation="piecewise_linear",
        storage_cost=storage_cost,
    )
    assert result.arbitrage_warnings
    warning = result.arbitrage_warnings[0]
    assert warning.periods == (period, late_period)
    assert repr(period) in warning.message
    assert repr(late_period) in warning.message


# Feature: power-energy-quant-analysis, Property 3: Arbitrage Violation Detection
@given(
    commodity=commodity_configs(),
    market_date=MARKET_DATES,
    period=delivery_periods(),
    near_price=st.floats(min_value=-1_000.0, max_value=1_000.0),
    storage_cost=st.floats(min_value=0.0, max_value=50.0),
    uplift=st.floats(min_value=0.0, max_value=100.0),
)
@settings(max_examples=100)
def test_clean_contango_produces_no_arbitrage_warnings(
    commodity: CommodityConfig,
    market_date: date,
    period: DeliveryPeriod,
    near_price: float,
    storage_cost: float,
    uplift: float,
) -> None:
    late_period = _next_month(period)
    instruments = [
        _record("near", commodity, period, near_price),
        _record("far", commodity, late_period, near_price + uplift),
    ]
    result = CurveBuilder().build(
        commodity,
        market_date,
        instruments,
        interpolation="piecewise_linear",
        storage_cost=storage_cost,
    )
    assert result.arbitrage_warnings == []


# Feature: power-energy-quant-analysis, Property 4: Interpolation Minimum Instrument Validation
# NOTE: the design's prose says "ValidationError"; the implemented (and unit-tested)
# behaviour raises the more specific InsufficientDataError, also an EnergyQuantError.
@given(
    data=st.data(),
    interpolation=st.sampled_from(_INTERPOLATIONS),
    commodity=commodity_configs(),
    market_date=MARKET_DATES,
)
@settings(max_examples=100)
def test_fewer_instruments_than_method_minimum_is_rejected_before_construction(
    data: st.DataObject,
    interpolation: str,
    commodity: CommodityConfig,
    market_date: date,
) -> None:
    minimum = _MIN_INSTRUMENTS[interpolation]
    count = data.draw(st.integers(min_value=0, max_value=minimum - 1), label="count")
    instruments = (
        data.draw(instrument_price_record_lists(min_len=count, max_len=count), label="instruments")
        if count
        else []
    )
    with pytest.raises(InsufficientDataError) as excinfo:
        CurveBuilder().build(
            commodity if not instruments else instruments[0].commodity,
            market_date,
            instruments,
            interpolation=interpolation,  # type: ignore[arg-type]
        )
    message = str(excinfo.value)
    assert interpolation in message
    assert str(minimum) in message


# Feature: power-energy-quant-analysis, Property 5: Forward Curve Serialisation Round-Trip
@given(curve=forward_curves(min_nodes=1, max_nodes=12))
@settings(max_examples=100)
def test_to_dict_from_dict_round_trips_to_an_equal_curve(curve: ForwardCurve) -> None:
    assert ForwardCurve.from_dict(curve.to_dict()) == curve


# Feature: power-energy-quant-analysis, Property 5: Forward Curve Serialisation Round-Trip
@given(
    instruments=_BUILD_INSTRUMENTS,
    market_date=MARKET_DATES,
    interpolation=st.sampled_from(_INTERPOLATIONS),
    tolerance=_TOLERANCES,
)
@settings(max_examples=100)
def test_round_tripped_built_curve_still_reprices_source_instruments(
    instruments: list[InstrumentPriceRecord],
    market_date: date,
    interpolation: str,
    tolerance: float,
) -> None:
    result = CurveBuilder().build(
        instruments[0].commodity,
        market_date,
        instruments,
        interpolation=interpolation,  # type: ignore[arg-type]
        tolerance=tolerance,
    )
    restored = ForwardCurve.from_dict(result.curve.to_dict())
    assert restored == result.curve
    for instrument in instruments:
        assert abs(restored.price_at(instrument.delivery_period) - instrument.price) <= tolerance
