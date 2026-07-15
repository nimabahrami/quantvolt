"""Spread-analysis correctness properties (design Properties 6-9, 42-44; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.spreads import (
    basis,
    calendar_spread,
    clean_spread,
    crack_spread,
    dark_spread,
    forward_spread,
    implied_heat_rate,
    spark_spread,
)
from strategies import MARKET_DATES, aligned_forward_curves, commodity_configs, forward_curves

_CurvePair = tuple[ForwardCurve, ForwardCurve]
_CurveTriple = tuple[ForwardCurve, ForwardCurve, ForwardCurve]

_HEAT_RATES = st.floats(min_value=0.1, max_value=5.0)
_COSTS = st.floats(min_value=0.0, max_value=50.0)
_INTENSITIES = st.floats(min_value=0.0, max_value=5.0)
_POSITIVE_PRICES = st.floats(min_value=0.01, max_value=10_000.0)
# The whole delivery-period window of strategies.delivery_periods() ([2024-01, 2032-12])
# has its last days inside this range, so basis() over it never filters a shared period.
_FULL_RANGE = (date(2023, 1, 1), date(2033, 12, 31))


def _prices(curve: ForwardCurve) -> dict[DeliveryPeriod, float]:
    return {node.period: node.price for node in curve.nodes}


# Feature: power-energy-quant-analysis, Property 6: Spark Spread Formula Correctness
@given(
    curves=aligned_forward_curves(count=2),
    heat_rate=_HEAT_RATES,
    variable_cost=_COSTS,
    emissions_cost=_COSTS,
)
@settings(max_examples=100)
def test_spark_spread_formula_per_shared_period(
    curves: _CurvePair, heat_rate: float, variable_cost: float, emissions_cost: float
) -> None:
    power_curve, fuel_curve = curves
    result = spark_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    power_prices, fuel_prices = _prices(power_curve), _prices(fuel_curve)
    assert result.spread_type == "spark"
    assert set(result.per_period) == set(power_prices) & set(fuel_prices)
    for period, value in result.per_period.items():
        expected = (
            power_prices[period] - heat_rate * fuel_prices[period] - variable_cost - emissions_cost
        )
        assert value == pytest.approx(expected, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 6: Spark Spread Formula Correctness
@given(
    curves=aligned_forward_curves(count=2),
    heat_rate=_HEAT_RATES,
    variable_cost=_COSTS,
    emissions_cost=_COSTS,
)
@settings(max_examples=100)
def test_computing_a_spark_spread_leaves_an_existing_dark_result_untouched(
    curves: _CurvePair, heat_rate: float, variable_cost: float, emissions_cost: float
) -> None:
    power_curve, fuel_curve = curves
    dark = dark_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    dark_snapshot = dict(dark.per_period)
    spark = spark_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    assert dark.spread_type == "dark"
    assert dark.per_period == dark_snapshot
    assert spark.spread_type == "spark"
    assert spark is not dark
    assert spark.per_period is not dark.per_period


# Feature: power-energy-quant-analysis, Property 7: Clean Spread Deduction Formula
@given(
    curves=aligned_forward_curves(count=3),
    heat_rate=_HEAT_RATES,
    variable_cost=_COSTS,
    emissions_cost=_COSTS,
    emissions_intensity=_INTENSITIES,
    base_is_spark=st.booleans(),
)
@settings(max_examples=100)
def test_clean_spread_deducts_intensity_times_eua_price_per_period(
    curves: _CurveTriple,
    heat_rate: float,
    variable_cost: float,
    emissions_cost: float,
    emissions_intensity: float,
    base_is_spark: bool,
) -> None:
    power_curve, fuel_curve, eua_curve = curves
    uncleaned_fn = spark_spread if base_is_spark else dark_spread
    uncleaned = uncleaned_fn(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    result = clean_spread(uncleaned, eua_curve, emissions_intensity)
    eua_prices = _prices(eua_curve)
    assert result.spread_type == uncleaned.spread_type
    assert set(result.per_period) == set(uncleaned.per_period)
    for period, value in result.per_period.items():
        carbon = emissions_intensity * eua_prices[period]
        assert result.carbon_cost[period] == pytest.approx(carbon, rel=1e-12, abs=1e-12)
        assert value == pytest.approx(uncleaned.per_period[period] - carbon, rel=1e-12, abs=1e-12)


@st.composite
def _heat_rate_curve_pairs(draw: st.DrawFn) -> _CurvePair:
    """A (power, gas) pair on one grid where every gas price is strictly positive."""
    power_curve, gas_template = draw(aligned_forward_curves(count=2))
    gas_nodes = tuple(replace(node, price=draw(_POSITIVE_PRICES)) for node in gas_template.nodes)
    return power_curve, replace(gas_template, nodes=gas_nodes)


# Feature: power-energy-quant-analysis, Property 8: Implied Heat Rate Formula and Validation
@given(curves=_heat_rate_curve_pairs())
@settings(max_examples=100)
def test_implied_heat_rate_is_power_over_gas_per_shared_period(curves: _CurvePair) -> None:
    power_curve, gas_curve = curves
    result = implied_heat_rate(power_curve, gas_curve)
    power_prices, gas_prices = _prices(power_curve), _prices(gas_curve)
    assert set(result.per_period) == set(power_prices) & set(gas_prices)
    for period, value in result.per_period.items():
        assert value == pytest.approx(
            power_prices[period] / gas_prices[period], rel=1e-12, abs=1e-12
        )
    assert result.anomalous == ()  # no anomaly_range supplied -> nothing flagged


# Feature: power-energy-quant-analysis, Property 8: Implied Heat Rate Formula and Validation
@given(
    curves=_heat_rate_curve_pairs(),
    bad_index=st.integers(min_value=0, max_value=11),
    bad_price=st.floats(min_value=-10_000.0, max_value=0.0),
)
@settings(max_examples=100)
def test_implied_heat_rate_rejects_a_non_positive_gas_price_naming_the_period(
    curves: _CurvePair, bad_index: int, bad_price: float
) -> None:
    power_curve, gas_curve = curves
    position = bad_index % len(gas_curve.nodes)
    bad_nodes = tuple(
        replace(node, price=bad_price) if index == position else node
        for index, node in enumerate(gas_curve.nodes)
    )
    bad_curve = replace(gas_curve, nodes=bad_nodes)
    with pytest.raises(ValidationError) as excinfo:
        implied_heat_rate(power_curve, bad_curve)
    message = str(excinfo.value)
    assert repr(bad_nodes[position].period) in message
    assert "gas_curve" in message


# Feature: power-energy-quant-analysis, Property 9: Basis Formula and Statistics
@given(curves=aligned_forward_curves(count=2))
@settings(max_examples=100)
def test_basis_is_a_minus_b_and_statistics_match_numpy(curves: _CurvePair) -> None:
    curve_a, curve_b = curves
    result = basis(curve_a, curve_b, *_FULL_RANGE)
    prices_a, prices_b = _prices(curve_a), _prices(curve_b)
    assert set(result.per_period) == set(prices_a) & set(prices_b)
    for period, value in result.per_period.items():
        assert value == pytest.approx(prices_a[period] - prices_b[period], rel=1e-12, abs=1e-12)
    values = np.asarray(list(result.per_period.values()), dtype=np.float64)
    assert result.mean == pytest.approx(float(np.mean(values)), rel=1e-12, abs=1e-12)
    assert result.std == pytest.approx(float(np.std(values)), rel=1e-12, abs=1e-12)
    assert result.p5 == pytest.approx(float(np.percentile(values, 5.0)), rel=1e-12, abs=1e-12)
    assert result.p95 == pytest.approx(float(np.percentile(values, 95.0)), rel=1e-12, abs=1e-12)


@st.composite
def _disjoint_curve_pairs(draw: st.DrawFn) -> _CurvePair:
    """Two curves whose delivery-period grids come from disjoint year ranges."""
    market_date = draw(MARKET_DATES)

    def curve(min_index: int, max_index: int) -> ForwardCurve:
        indices = sorted(draw(st.sets(st.integers(min_index, max_index), min_size=1, max_size=6)))
        nodes = tuple(
            CurveNode(
                period=DeliveryPeriod(year=i // 12, month=i % 12 + 1),
                price=draw(st.floats(min_value=-10_000.0, max_value=10_000.0)),
                status="observed",
            )
            for i in indices
        )
        return ForwardCurve(
            commodity=draw(commodity_configs()), market_date=market_date, nodes=nodes
        )

    return curve(2024 * 12, 2027 * 12 + 11), curve(2028 * 12, 2032 * 12 + 11)


# Feature: power-energy-quant-analysis, Property 9: Basis Formula and Statistics
@given(curves=_disjoint_curve_pairs())
@settings(max_examples=100)
def test_basis_on_curves_with_no_shared_period_raises_insufficient_data(
    curves: _CurvePair,
) -> None:
    curve_a, curve_b = curves
    with pytest.raises(InsufficientDataError) as excinfo:
        basis(curve_a, curve_b, *_FULL_RANGE)
    message = str(excinfo.value)
    assert curve_a.commodity.commodity_id in message
    assert curve_b.commodity.commodity_id in message


@st.composite
def _crack_cases(draw: st.DrawFn) -> tuple[dict[str, ForwardCurve], ForwardCurve, tuple[int, ...]]:
    """1-3 product curves plus a crude curve on one grid, with a drawn crack ratio."""
    product_count = draw(st.integers(min_value=1, max_value=3))
    curves = draw(aligned_forward_curves(count=product_count + 1))
    products = {f"product_{index}": curve for index, curve in enumerate(curves[:-1])}
    ratio = tuple(draw(st.integers(min_value=1, max_value=10)) for _ in range(product_count + 1))
    return products, curves[-1], ratio


# Feature: power-energy-quant-analysis, Property 42: Crack Spread Formula Correctness
@given(case=_crack_cases())
@settings(max_examples=100)
def test_crack_spread_matches_the_ratio_weighted_hand_computation(
    case: tuple[dict[str, ForwardCurve], ForwardCurve, tuple[int, ...]],
) -> None:
    product_curves, crude_curve, ratio = case
    result = crack_spread(product_curves, crude_curve, ratio)
    crude_prices = _prices(crude_curve)
    product_prices = {name: _prices(curve) for name, curve in product_curves.items()}
    assert result.ratio == ratio
    assert set(result.per_period) == set(crude_prices)
    for period, value in result.per_period.items():
        weighted_products = sum(
            units * product_prices[name][period]
            for name, units in zip(product_curves, ratio[1:], strict=True)
        )
        expected = (weighted_products - ratio[0] * crude_prices[period]) / ratio[0]
        assert value == pytest.approx(expected, rel=1e-12, abs=1e-12)


# Feature: power-energy-quant-analysis, Property 43: Forward Spread Consistency with
# Spot Spread
@given(
    curves=aligned_forward_curves(count=2),
    heat_rate=_HEAT_RATES,
    variable_cost=_COSTS,
    emissions_cost=_COSTS,
)
@settings(max_examples=100)
def test_forward_spread_equals_spark_spread_on_identical_inputs(
    curves: _CurvePair, heat_rate: float, variable_cost: float, emissions_cost: float
) -> None:
    power_curve, fuel_curve = curves
    forward = forward_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    spark = spark_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)
    assert forward == spark
    assert forward.spread_type == "spark"


# Feature: power-energy-quant-analysis, Property 44: Storage-Related Calendar Spread
@given(
    curve=forward_curves(min_nodes=2, max_nodes=12),
    picks=st.tuples(st.integers(min_value=0, max_value=100), st.integers(0, 100)),
    storage_cost=st.floats(min_value=0.0, max_value=20.0),
)
@settings(max_examples=100)
def test_calendar_spread_is_later_minus_earlier_net_of_storage_with_contango_sign(
    curve: ForwardCurve, picks: tuple[int, int], storage_cost: float
) -> None:
    first = picks[0] % len(curve.nodes)
    second = picks[1] % len(curve.nodes)
    if first == second:  # force two distinct node indices
        second = (first + 1) % len(curve.nodes)
    first, second = sorted((first, second))
    period_early = curve.nodes[first].period
    period_late = curve.nodes[second].period
    result = calendar_spread(curve, period_early, period_late, storage_cost)
    months = (period_late.year - period_early.year) * 12 + (period_late.month - period_early.month)
    price_difference = curve.nodes[second].price - curve.nodes[first].price
    assert result.period_early == period_early
    assert result.period_late == period_late
    assert result.price_difference == pytest.approx(price_difference, rel=1e-12, abs=1e-12)
    assert result.storage_cost_total == pytest.approx(storage_cost * months, rel=1e-12, abs=1e-12)
    assert result.spread == pytest.approx(
        price_difference - storage_cost * months, rel=1e-12, abs=1e-12
    )
    # Sign semantics: positive == contango net of carry (profitable injection),
    # negative == backwardation.
    assert (result.spread > 0) == (result.price_difference > result.storage_cost_total)
