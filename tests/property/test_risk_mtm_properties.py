"""Risk-engine and mark-to-market correctness properties (design Properties 21-26; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``) unless noted otherwise.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import NoPricingDataError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.portfolio.model import PricedPosition
from quantvolt.pricing.mark_to_market import MtMPosition, mark_to_market
from quantvolt.risk.aggregation import aggregate_delta
from quantvolt.risk.engine import ExcludedPosition, RiskEngine
from quantvolt.risk.scenarios import BUILT_IN_SCENARIOS, ScenarioShock, ShockKey
from strategies import (
    MARKET_DATES,
    PRICES,
    RISK_COMMODITY_IDS,
    RISK_PERIODS,
    mtm_positions,
    priced_positions,
)

_MtMFallbackCase = tuple[list[MtMPosition], ForwardCurve, dict[tuple[str, DeliveryPeriod], float]]

# The design quantifies Property 21 over "at least 252 trading days" of scenarios.
_N_SCENARIOS = 252
_SHOCKS = st.floats(min_value=-3.0, max_value=3.0)


def _books(
    min_deltas: int, min_size: int = 1, max_size: int = 6
) -> st.SearchStrategy[list[PricedPosition]]:
    return st.lists(priced_positions(min_deltas=min_deltas), min_size=min_size, max_size=max_size)


def _manual_pnl(positions: list[PricedPosition], scenario_matrix: np.ndarray) -> list[float]:
    """Oracle: per-scenario P&L via plain Python loops over the row-major factor grid."""
    grid = aggregate_delta(positions)
    n_periods = len(grid.periods)
    pnl = []
    for row in range(scenario_matrix.shape[0]):
        total = 0.0
        for i, commodity in enumerate(grid.commodities):
            for j, period in enumerate(grid.periods):
                total += grid.delta_at(commodity, period) * float(
                    scenario_matrix[row, i * n_periods + j]
                )
        pnl.append(total)
    return pnl


# Feature: power-energy-quant-analysis, Property 21: Portfolio VaR and CVaR Quantile
# Correctness
# The engine's vectorised pnl = scenario_matrix @ delta_vector is checked against a
# manual Python loop over the same row-major (commodity, period) factor grid; VaR
# and CVaR are then the loss percentiles of that oracle P&L. Note the implementation
# takes the inclusive tail (losses >= the 97.5th percentile) so the tail is never
# empty; with 252 continuous scenario draws it coincides with the design's "strictly
# exceeding" reading almost surely.
@given(book=_books(min_deltas=1), seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=100)
def test_var_and_cvar_match_the_loss_percentiles_of_a_manual_scenario_loop(
    book: list[PricedPosition], seed: int
) -> None:
    grid = aggregate_delta(book)
    n_cells = len(grid.commodities) * len(grid.periods)
    scenario_matrix = np.random.default_rng(seed).normal(size=(_N_SCENARIOS, n_cells))
    result = RiskEngine().compute_risk(book, scenario_matrix)
    losses = -np.asarray(_manual_pnl(book, scenario_matrix), dtype=np.float64)
    assert result.var_95 == pytest.approx(float(np.percentile(losses, 95.0)), rel=1e-9, abs=1e-9)
    assert result.var_99 == pytest.approx(float(np.percentile(losses, 99.0)), rel=1e-9, abs=1e-9)
    tail_threshold = np.percentile(losses, 97.5)
    expected_cvar = float(losses[losses >= tail_threshold].mean())
    assert result.cvar_975 == pytest.approx(expected_cvar, rel=1e-9, abs=1e-9)
    assert result.partial is False
    assert result.unprocessed_indices == []


# Feature: power-energy-quant-analysis, Property 22: Delta Aggregation Correctness
@given(book=_books(min_deltas=0, max_size=8))
@settings(max_examples=100)
def test_each_aggregated_cell_is_the_sum_of_the_individual_position_deltas(
    book: list[PricedPosition],
) -> None:
    matrix = aggregate_delta(book)
    seen_keys = {key for position in book for key in position.delta}
    assert set(matrix.commodities) == {commodity for commodity, _ in seen_keys}
    assert set(matrix.periods) == {period for _, period in seen_keys}
    assert matrix.commodities == tuple(sorted(matrix.commodities))
    assert matrix.periods == tuple(sorted(matrix.periods))
    for commodity in RISK_COMMODITY_IDS:  # the full key pool, incl. off-grid cells
        for period in RISK_PERIODS:
            # Left-fold accumulation, matching the implementation's `+=` netting
            # (Python 3.12's built-in sum() compensates rounding, so it can differ
            # in the last ulp from plain accumulation).
            expected = 0.0
            for position in book:
                expected += position.delta.get((commodity, period), 0.0)
            assert matrix.delta_at(commodity, period) == expected


@st.composite
def _scenarios(draw: st.DrawFn) -> str | ScenarioShock:
    """A named built-in scenario or a user-defined shock over the small key pool,
    mixing period-specific and commodity-wide entries."""
    if draw(st.booleans()):
        return draw(st.sampled_from(sorted(BUILT_IN_SCENARIOS)))
    keys = draw(
        st.sets(
            st.tuples(
                st.sampled_from(RISK_COMMODITY_IDS),
                st.one_of(st.none(), st.sampled_from(RISK_PERIODS)),
            ),
            min_size=1,
            max_size=6,
        )
    )
    shocks: dict[ShockKey, float] = {
        key: draw(_SHOCKS)
        for key in sorted(keys, key=lambda k: (k[0], k[1] is not None, k[1] or RISK_PERIODS[0]))
    }
    return ScenarioShock(name="drawn scenario", shocks=shocks)


# Feature: power-energy-quant-analysis, Property 23: Scenario P&L Computation Correctness
@given(book=_books(min_deltas=0, max_size=8), scenario=_scenarios())
@settings(max_examples=100)
def test_per_position_scenario_pnl_is_delta_dot_shock_and_sums_to_total(
    book: list[PricedPosition], scenario: str | ScenarioShock
) -> None:
    result = RiskEngine().apply_scenario(book, scenario)
    resolved = BUILT_IN_SCENARIOS[scenario] if isinstance(scenario, str) else scenario
    assert result.scenario_name == resolved.name
    assert len(result.per_position_pnl) == len(book)
    for position, pnl in zip(book, result.per_position_pnl, strict=True):
        expected = 0.0
        for (commodity, period), delta in position.delta.items():
            specific = resolved.shocks.get((commodity, period))
            commodity_wide = resolved.shocks.get((commodity, None), 0.0)
            expected += delta * (specific if specific is not None else commodity_wide)
        assert pnl == expected
    assert result.total_pnl == sum(result.per_position_pnl)


# Feature: power-energy-quant-analysis, Property 24: Incomplete Position Exclusion and
# Reporting
# priced_positions(min_deltas=0) naturally mixes complete positions with empty-delta
# ones, so the drawn books cover both a populated and an empty exclusion report.
@given(book=_books(min_deltas=0, max_size=8), seed=st.integers(min_value=0, max_value=2**31 - 1))
@settings(max_examples=100)
def test_empty_delta_positions_are_excluded_with_reason_and_the_report_is_always_present(
    book: list[PricedPosition], seed: int
) -> None:
    included = [position for position in book if position.delta]
    grid = aggregate_delta(included)
    n_cells = len(grid.commodities) * len(grid.periods)
    scenario_matrix = np.random.default_rng(seed).normal(size=(5, n_cells))
    result = RiskEngine().compute_risk(book, scenario_matrix)
    assert isinstance(result.exclusion_report, list)  # always present, even when empty
    assert result.exclusion_report == [
        ExcludedPosition(index=index, reason="missing_delta")
        for index, position in enumerate(book)
        if not position.delta
    ]
    # included + excluded partitions the input book exactly.
    assert len(included) + len(result.exclusion_report) == len(book)
    assert result.delta_matrix == grid  # metrics aggregate exactly the included subset


@st.composite
def _mtm_fallback_cases(draw: st.DrawFn) -> _MtMFallbackCase:
    """A one-commodity book where a forward curve covers EVERY position's period and a
    drawn subset of (commodity, period) keys also has a settlement price — so the
    settled/estimated split is fully known and settlement always wins over the curve."""
    commodity_id = draw(st.sampled_from(sorted(BUILT_IN_COMMODITIES)))
    positions = [
        replace(position, commodity_id=commodity_id)
        for position in draw(st.lists(mtm_positions(), min_size=1, max_size=6))
    ]
    periods = sorted({position.delivery_period for position in positions})
    curve = ForwardCurve(
        commodity=BUILT_IN_COMMODITIES[commodity_id],
        market_date=draw(MARKET_DATES),
        nodes=tuple(
            CurveNode(period=period, price=draw(PRICES), status="observed") for period in periods
        ),
    )
    settled_periods = draw(st.sets(st.sampled_from(periods), max_size=len(periods)))
    settlement_prices = {(commodity_id, period): draw(PRICES) for period in sorted(settled_periods)}
    return positions, curve, settlement_prices


# Feature: power-energy-quant-analysis, Property 25: Mark-to-Market P&L Formula
# Correctness
@given(case=_mtm_fallback_cases(), market_date=MARKET_DATES)
@settings(max_examples=100)
def test_daily_and_cumulative_pnl_formulas_and_settlement_wins_over_the_curve(
    case: _MtMFallbackCase, market_date: date
) -> None:
    positions, curve, settlement_prices = case
    result = mark_to_market(positions, market_date, settlement_prices, curve)
    for position, position_result in zip(positions, result.positions, strict=True):
        key = (position.commodity_id, position.delivery_period)
        if key in settlement_prices:
            # The curve also covers this period; the settlement price must win.
            assert position_result.status == "settled"
            assert position_result.current_mark == settlement_prices[key]
        mark = position_result.current_mark
        assert position_result.daily_pnl == (mark - position.prior_mark_price) * position.notional
        assert position_result.cumulative_pnl == (mark - position.trade_price) * position.notional


# Feature: power-energy-quant-analysis, Property 26: Settlement Price Fallback and
# Estimation Flagging
@given(case=_mtm_fallback_cases(), market_date=MARKET_DATES)
@settings(max_examples=100)
def test_curve_fallback_marks_exactly_the_unsettled_positions_as_estimated(
    case: _MtMFallbackCase, market_date: date
) -> None:
    positions, curve, settlement_prices = case
    result = mark_to_market(positions, market_date, settlement_prices, curve)
    estimated = 0
    for position, position_result in zip(positions, result.positions, strict=True):
        key = (position.commodity_id, position.delivery_period)
        if key in settlement_prices:
            assert position_result.status == "settled"
        else:
            assert position_result.status == "estimated"
            assert position_result.current_mark == curve.price_at(position.delivery_period)
            estimated += 1
    assert result.estimated_count == estimated


# Feature: power-energy-quant-analysis, Property 26: Settlement Price Fallback and
# Estimation Flagging
@given(position=mtm_positions(), market_date=MARKET_DATES, other_price=PRICES)
@settings(max_examples=100)
def test_no_settlement_and_no_matching_curve_raises_no_pricing_data_error(
    position: MtMPosition, market_date: date, other_price: float
) -> None:
    # No settlement price and no curve at all.
    with pytest.raises(NoPricingDataError) as excinfo:
        mark_to_market([position], market_date, {})
    message = str(excinfo.value)
    assert position.commodity_id in message
    assert repr(position.delivery_period) in message
    # A curve for a DIFFERENT commodity never marks the position either.
    other_id = next(
        commodity_id
        for commodity_id in sorted(BUILT_IN_COMMODITIES)
        if commodity_id != position.commodity_id
    )
    other_curve = ForwardCurve(
        commodity=BUILT_IN_COMMODITIES[other_id],
        market_date=market_date,
        nodes=(CurveNode(period=position.delivery_period, price=other_price, status="observed"),),
    )
    with pytest.raises(NoPricingDataError):
        mark_to_market([position], market_date, {}, other_curve)
