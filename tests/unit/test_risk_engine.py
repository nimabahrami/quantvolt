"""Unit tests for RiskEngine (Task 41, Req 9.1 / 9.2 / 9.4 / 9.5 / 9.6 / 9.7).

Covers VaR/CVaR percentile math (Property 21), scenario P&L and per-position
contributions (Property 23), exclusion reporting and partial results
(Property 24), determinism, input immutability, and the 500-position SLA.
"""

from __future__ import annotations

import math
import time
from datetime import date

import numpy as np
import numpy.typing as npt
import pytest

from quantvolt.exceptions import ScenarioNotFoundError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.portfolio.model import Portfolio, Position, PricedPosition
from quantvolt.portfolio.valuation import MarketData, value_portfolio
from quantvolt.risk.engine import ExcludedPosition, RiskEngine, RiskResult, ScenarioResult
from quantvolt.risk.scenarios import BUILT_IN_SCENARIOS, ScenarioShock, gas_crisis
from quantvolt.testing import assert_input_unchanged

_TTF = CommodityConfig("TTF", "EUR/MBtu", Hub("TTF", "ICE_ENDEX", "EUR/MBtu"))
_JAN = DeliveryPeriod(2026, 1)
_FEB = DeliveryPeriod(2026, 2)
_FUTURES = FuturesContract(_TTF, _JAN, contract_price=30.0, notional=100.0)


def _priced(npv: float, delta: dict[tuple[str, DeliveryPeriod], float]) -> PricedPosition:
    return PricedPosition(position=Position(_FUTURES), npv=npv, delta=delta)


def _two_position_book() -> list[PricedPosition]:
    """Net grid: 1 commodity ("TTF") x 2 periods (Jan, Feb); delta vector [1.0, 0.0]."""
    return [
        _priced(10.0, {("TTF", _JAN): 2.0}),
        _priced(-5.0, {("TTF", _JAN): -1.0, ("TTF", _FEB): 0.0}),
    ]


def _loss_ladder_matrix() -> npt.NDArray[np.float64]:
    """20 scenarios x 2 factors; with delta [1, 0] the losses are exactly 1..20."""
    shocks_jan = -np.arange(1.0, 21.0)
    return np.column_stack([shocks_jan, np.zeros(20)])


# --- exclusion report (Req 9.5, Property 24) ----------------------------------


def test_exclusion_report_present_and_empty_on_clean_book() -> None:
    result = RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix())
    assert result.exclusion_report == []
    assert result.partial is False
    assert result.unprocessed_indices == []


def test_missing_delta_position_is_excluded_with_reason_and_index() -> None:
    positions = [
        _priced(1.0, {("TTF", _JAN): 5.0}),
        _priced(2.0, {}),  # empty delta -> excluded
    ]
    matrix = np.ones((4, 1))
    result = RiskEngine().compute_risk(positions, matrix)
    assert result.exclusion_report == [ExcludedPosition(index=1, reason="missing_delta")]
    # Only the included position's exposure reaches the delta grid.
    assert result.delta_matrix.delta_at("TTF", _JAN) == 5.0


def test_non_finite_npv_is_excluded_as_missing_npv() -> None:
    # PricedPosition validates npv at construction; simulate an upstream invariant
    # breach (the defensive path) by injecting NaN into the frozen instance.
    broken = _priced(0.0, {("TTF", _JAN): 5.0})
    object.__setattr__(broken, "npv", float("nan"))
    positions = [broken, _priced(1.0, {("TTF", _JAN): 3.0})]
    result = RiskEngine().compute_risk(positions, np.ones((4, 1)))
    assert result.exclusion_report == [ExcludedPosition(index=0, reason="missing_npv")]
    assert result.delta_matrix.delta_at("TTF", _JAN) == 3.0


def test_exclusions_preserve_input_order() -> None:
    positions = [
        _priced(1.0, {}),
        _priced(2.0, {("TTF", _JAN): 1.0}),
        _priced(3.0, {}),
    ]
    result = RiskEngine().compute_risk(positions, np.ones((4, 1)))
    assert [excluded.index for excluded in result.exclusion_report] == [0, 2]
    assert all(excluded.reason == "missing_delta" for excluded in result.exclusion_report)


# --- VaR / CVaR quantile math (Req 9.1 / 9.2, Property 21) ---------------------


def test_var_and_cvar_exact_percentile_math() -> None:
    # Losses are exactly 1..20; np.percentile linear interpolation on n=20:
    # q95  -> rank 0.95*19 = 18.05 -> 19 + 0.05 = 19.05
    # q99  -> rank 0.99*19 = 18.81 -> 19 + 0.81 = 19.81
    # q97.5-> rank 18.525 -> 19.525; inclusive tail = {20} -> cvar = 20.0
    result = RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix())
    assert result.var_95 == pytest.approx(19.05, rel=1e-12)
    assert result.var_99 == pytest.approx(19.81, rel=1e-12)
    assert result.cvar_975 == pytest.approx(20.0, rel=1e-12)


def test_vectorised_pnl_matches_manual_loop() -> None:
    # Property 21: pnl = scenario_matrix @ delta_vector must equal a hand loop
    # over positions and scenarios, and the VaR/CVaR must follow from it.
    rng = np.random.default_rng(42)
    positions = [
        _priced(1.0, {("TTF", _JAN): 120.0, ("TTF", _FEB): -30.0}),
        _priced(2.0, {("TTF", _JAN): -45.5}),
        _priced(3.0, {("TTF", _FEB): 80.25}),
    ]
    matrix = rng.normal(size=(252, 2))  # columns: (TTF, Jan), (TTF, Feb) — sorted order

    result = RiskEngine().compute_risk(positions, matrix)

    factor_index = {("TTF", _JAN): 0, ("TTF", _FEB): 1}
    manual_pnl = np.zeros(252)
    for scenario in range(252):
        for position in positions:
            for key, delta in position.delta.items():
                manual_pnl[scenario] += delta * matrix[scenario, factor_index[key]]
    losses = -manual_pnl
    assert result.var_95 == pytest.approx(float(np.percentile(losses, 95)), rel=1e-9)
    assert result.var_99 == pytest.approx(float(np.percentile(losses, 99)), rel=1e-9)
    tail = losses[losses >= np.percentile(losses, 97.5)]
    assert result.cvar_975 == pytest.approx(float(tail.mean()), rel=1e-9)


# --- validation ----------------------------------------------------------------


def test_factor_dimension_mismatch_raises_naming_both_dims() -> None:
    # Grid is 1 commodity x 2 periods = 2 cells; matrix has 3 columns.
    with pytest.raises(ValidationError) as excinfo:
        RiskEngine().compute_risk(_two_position_book(), np.ones((5, 3)))
    message = str(excinfo.value)
    assert "3" in message and "2" in message
    assert "scenario_matrix" in message


def test_non_array_scenario_matrix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="scenario_matrix"):
        RiskEngine().compute_risk(
            _two_position_book(),
            [[1.0, 2.0]],  # type: ignore[arg-type]
        )


def test_one_dimensional_scenario_matrix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="scenario_matrix must be 2-D"):
        RiskEngine().compute_risk(_two_position_book(), np.ones(4))


def test_integer_dtype_scenario_matrix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="floating-point dtype"):
        RiskEngine().compute_risk(_two_position_book(), np.ones((4, 2), dtype=np.int64))


def test_empty_scenario_matrix_is_rejected() -> None:
    with pytest.raises(ValidationError, match="at least one scenario row"):
        RiskEngine().compute_risk(_two_position_book(), np.empty((0, 2)))


def test_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timeout_seconds"):
        RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix(), timeout_seconds=0.0)


# --- partial results on timeout (Req 9.6, Property 24) --------------------------


def test_tiny_timeout_returns_partial_result_without_raising() -> None:
    positions = _two_position_book()
    result = RiskEngine().compute_risk(positions, _loss_ladder_matrix(), timeout_seconds=1e-12)
    assert result.partial is True
    assert result.unprocessed_indices == list(range(len(positions)))
    assert result.unprocessed_indices  # populated
    # Nothing was processed: empty grid short-circuits to zero P&L everywhere.
    assert result.exclusion_report == []
    assert result.var_95 == 0.0
    assert result.var_99 == 0.0
    assert result.cvar_975 == 0.0


# --- apply_scenario (Req 9.4 / 9.7, Property 23) --------------------------------


def test_apply_named_builtin_scenario() -> None:
    positions = [_priced(1.0, {("TTF", _JAN): 100.0})]
    result = RiskEngine().apply_scenario(positions, "Cold Snap Winter")
    assert isinstance(result, ScenarioResult)
    assert result.scenario_name == "Cold Snap Winter"
    # Built-in Cold Snap Winter shocks TTF commodity-wide by +1.0.
    assert result.per_position_pnl == (100.0,)
    assert result.total_pnl == 100.0


def test_apply_custom_shock_period_specific_wins_over_commodity_wide() -> None:
    custom = ScenarioShock(
        name="Jan squeeze",
        shocks={("TTF", _JAN): 0.5, ("TTF", None): 0.1},
    )
    positions = [_priced(1.0, {("TTF", _JAN): 100.0, ("TTF", _FEB): 40.0})]
    result = RiskEngine().apply_scenario(positions, custom)
    # Jan uses the period-specific 0.5; Feb falls back to the commodity-wide 0.1.
    assert result.per_position_pnl == (100.0 * 0.5 + 40.0 * 0.1,)
    assert result.scenario_name == "Jan squeeze"


def test_unshocked_factor_contributes_zero() -> None:
    custom = ScenarioShock(name="EUA only", shocks={("EUA", None): 1.0})
    positions = [_priced(1.0, {("TTF", _JAN): 100.0})]
    result = RiskEngine().apply_scenario(positions, custom)
    assert result.per_position_pnl == (0.0,)
    assert result.total_pnl == 0.0


def test_unknown_scenario_name_raises_listing_available_names() -> None:
    with pytest.raises(ScenarioNotFoundError) as excinfo:
        RiskEngine().apply_scenario(_two_position_book(), "Beast from the East")
    message = str(excinfo.value)
    assert "Beast from the East" in message
    for name in BUILT_IN_SCENARIOS:
        assert name in message


def test_per_position_contributions_sum_to_total_and_preserve_order() -> None:
    positions = [
        _priced(1.0, {("TTF", _JAN): 100.0}),
        _priced(2.0, {("TTF", _FEB): -40.0}),
        _priced(3.0, {}),  # empty delta -> 0.0 contribution, still present in order
    ]
    custom = ScenarioShock(name="flat", shocks={("TTF", None): 0.25})
    result = RiskEngine().apply_scenario(positions, custom)
    assert result.per_position_pnl == (25.0, -10.0, 0.0)
    assert result.total_pnl == sum(result.per_position_pnl)  # Property 23, exact


# --- aggregate_delta delegation (Req 9.3) ---------------------------------------


def test_aggregate_delta_delegates_to_aggregation_module() -> None:
    positions = _two_position_book()
    matrix = RiskEngine().aggregate_delta(positions)
    assert matrix.commodities == ("TTF",)
    assert matrix.periods == (_JAN, _FEB)
    assert matrix.values == ((1.0, 0.0),)


# --- determinism & immutability (coding-style.md section 7) ----------------------


def test_same_inputs_twice_give_identical_results() -> None:
    engine = RiskEngine()
    positions = _two_position_book()
    matrix = _loss_ladder_matrix()
    first = engine.compute_risk(positions, matrix)
    second = engine.compute_risk(positions, matrix)
    assert isinstance(first, RiskResult)
    assert first == second


def test_compute_risk_does_not_mutate_inputs() -> None:
    engine = RiskEngine()
    result = assert_input_unchanged(
        engine.compute_risk, _two_position_book(), _loss_ladder_matrix()
    )
    assert isinstance(result, RiskResult)


def test_apply_scenario_does_not_mutate_inputs() -> None:
    engine = RiskEngine()
    custom = ScenarioShock(name="flat", shocks={("TTF", None): 0.25})
    result = assert_input_unchanged(engine.apply_scenario, _two_position_book(), custom)
    assert isinstance(result, ScenarioResult)


# --- performance sanity (Req 9.6) ------------------------------------------------


def test_500_positions_252_scenarios_completes_well_within_sla() -> None:
    periods = [DeliveryPeriod(2026, month) for month in range(1, 7)]
    commodities = ["EEX_PHELIX_DE", "TTF"]
    delta = {(commodity, period): 10.0 for commodity in commodities for period in periods}
    positions = [_priced(float(i), dict(delta)) for i in range(500)]
    matrix = np.random.default_rng(7).normal(size=(252, len(commodities) * len(periods)))

    start = time.monotonic()
    result = RiskEngine().compute_risk(positions, matrix, timeout_seconds=60.0)
    elapsed = time.monotonic() - start

    assert result.partial is False
    assert result.unprocessed_indices == []
    assert not math.isnan(result.var_95)
    assert elapsed < 30.0  # loose sanity bound; the SLA is 60 s (Req 9.6)


# --- caller-configurable confidence levels (task: expose hardcoded VaR/CVaR levels) --


def test_default_confidences_match_previous_hardcoded_behaviour() -> None:
    # Same fixture/expectations as test_var_and_cvar_exact_percentile_math: calling
    # compute_risk with the new keyword-only defaults must reproduce the previously
    # hardcoded 95/99/97.5 percentile levels bit-for-bit.
    baseline = RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix())
    defaulted = RiskEngine().compute_risk(
        _two_position_book(),
        _loss_ladder_matrix(),
        confidences=(0.95, 0.99),
        cvar_confidence=0.975,
    )
    assert defaulted.var_95 == baseline.var_95
    assert defaulted.var_99 == baseline.var_99
    assert defaulted.cvar_975 == baseline.cvar_975
    assert defaulted.var_95 == pytest.approx(19.05, rel=1e-12)
    assert defaulted.var_99 == pytest.approx(19.81, rel=1e-12)
    assert defaulted.cvar_975 == pytest.approx(20.0, rel=1e-12)


def test_overriding_confidences_changes_var_and_cvar() -> None:
    # Losses are exactly 1..20 (see test_var_and_cvar_exact_percentile_math). Overriding
    # to (0.50, 0.90) / cvar_confidence=0.80 must change the reported figures.
    result = RiskEngine().compute_risk(
        _two_position_book(),
        _loss_ladder_matrix(),
        confidences=(0.50, 0.90),
        cvar_confidence=0.80,
    )
    losses = np.arange(1.0, 21.0)
    assert result.var_95 == pytest.approx(float(np.percentile(losses, 50.0)), rel=1e-12)
    assert result.var_99 == pytest.approx(float(np.percentile(losses, 90.0)), rel=1e-12)
    tail_threshold = np.percentile(losses, 80.0)
    expected_cvar = losses[losses >= tail_threshold].mean()
    assert result.cvar_975 == pytest.approx(float(expected_cvar), rel=1e-12)
    # Sanity: genuinely different from the default-confidence result.
    default_result = RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix())
    assert result.var_95 != default_result.var_95
    assert result.cvar_975 != default_result.cvar_975


def test_confidences_must_have_exactly_two_levels() -> None:
    with pytest.raises(ValidationError, match="exactly 2 levels"):
        RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix(), confidences=(0.95,))


def test_confidences_out_of_range_raises() -> None:
    with pytest.raises(ValidationError, match="open interval"):
        RiskEngine().compute_risk(
            _two_position_book(), _loss_ladder_matrix(), confidences=(0.0, 0.99)
        )


def test_cvar_confidence_out_of_range_raises() -> None:
    with pytest.raises(ValidationError, match="cvar_confidence"):
        RiskEngine().compute_risk(_two_position_book(), _loss_ladder_matrix(), cvar_confidence=1.0)


# --- FIX: confidences must be strictly ascending (var_95 < var_99) -------------
# A previously accepted (0.99, 0.95) pair silently swapped var_95/var_99.


def test_swapped_confidences_are_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly ascending"):
        RiskEngine().compute_risk(
            _two_position_book(), _loss_ladder_matrix(), confidences=(0.99, 0.95)
        )


def test_equal_confidences_are_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly ascending"):
        RiskEngine().compute_risk(
            _two_position_book(), _loss_ladder_matrix(), confidences=(0.95, 0.95)
        )


# --- FIX: scenario_matrix finiteness is validated (a NaN cell used to silently ---
# --- propagate into every downstream loss quantile) -----------------------------


def test_nan_cell_in_scenario_matrix_is_rejected() -> None:
    matrix = _loss_ladder_matrix()
    matrix[3, 0] = float("nan")
    with pytest.raises(ValidationError, match="finite"):
        RiskEngine().compute_risk(_two_position_book(), matrix)


def test_inf_cell_in_scenario_matrix_is_rejected() -> None:
    matrix = _loss_ladder_matrix()
    matrix[3, 0] = float("inf")
    with pytest.raises(ValidationError, match="finite"):
        RiskEngine().compute_risk(_two_position_book(), matrix)


# --- FIX: apply_scenario scales relative shocks by the position's reference -----
# --- price (Property 23 dot-product convention is preserved for hand-built -----
# --- PricedPositions that never set reference_prices; positions produced by ----
# --- value_portfolio now scale correctly for the *relative* built-in catalogue --
# --- shocks, matching scenarios.py's documented `delta * price * shock`) -------


def test_apply_scenario_scales_by_reference_price_when_populated() -> None:
    """Directly on PricedPosition.reference_prices, bypassing value_portfolio."""
    priced = PricedPosition(
        position=Position(_FUTURES),
        npv=0.0,
        delta={("TTF", _JAN): 1000.0},
        reference_prices={("TTF", _JAN): 40.0},
    )
    custom = ScenarioShock(name="+300%", shocks={("TTF", None): 3.0})
    result = RiskEngine().apply_scenario([priced], custom)
    # delta * reference_price * shock = 1000 * 40 * 3.0, NOT the un-scaled 1000 * 3.0.
    assert result.total_pnl == pytest.approx(120_000.0)
    assert result.total_pnl != pytest.approx(3_000.0)


def test_apply_scenario_without_reference_prices_falls_back_to_legacy_delta_times_shock() -> None:
    """Backward compatibility: a position that never sets reference_prices (the
    default, empty mapping) keeps the pre-fix `delta * shock` convention."""
    priced = _priced(0.0, {("TTF", _JAN): 1000.0})
    assert priced.reference_prices == {}
    custom = ScenarioShock(name="+300%", shocks={("TTF", None): 3.0})
    result = RiskEngine().apply_scenario([priced], custom)
    assert result.total_pnl == pytest.approx(3_000.0)


def test_gas_crisis_stress_on_a_valued_ttf_book_uses_the_forward_price() -> None:
    """End-to-end regression for the verified bug: a real (value_portfolio-priced)
    TTF futures book stressed under the built-in "European Gas Crisis 2022" scenario
    (ttf_shock=+3.0, i.e. +300%) must move by delta * forward_price * shock, not the
    un-scaled delta * shock the bug previously computed.
    """
    ttf = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
    forward = 40.0
    valuation_date = date(2025, 12, 1)
    curve = ForwardCurve(
        commodity=ttf,
        market_date=valuation_date,
        nodes=(CurveNode(_JAN, forward, "observed"),),
    )
    discount_curve = DiscountCurve(
        reference_date=valuation_date,
        tenors=(_JAN.last_day,),
        factors=(1.0,),  # discount factor 1.0 -> delta = notional exactly
    )
    market_data = MarketData(
        forward_curves={"TTF": curve}, discount_curve=discount_curve, valuation_date=valuation_date
    )
    contract = FuturesContract(ttf, _JAN, contract_price=forward, notional=1000.0)
    valuation = value_portfolio(Portfolio(positions=(Position(contract),)), market_data)
    priced = valuation.priced[0]
    assert priced.delta == pytest.approx({("TTF", _JAN): 1000.0})
    assert priced.reference_prices == pytest.approx({("TTF", _JAN): forward})

    result = RiskEngine().apply_scenario([priced], "European Gas Crisis 2022")

    ttf_shock = gas_crisis().shocks[("TTF", None)]
    assert ttf_shock == pytest.approx(3.0)
    expected_pnl = 1000.0 * forward * ttf_shock  # 120,000.0
    assert result.total_pnl == pytest.approx(expected_pnl)
    assert result.total_pnl == pytest.approx(120_000.0)
    # The previously-buggy `delta * shock` (no price) value would have been 3,000.0.
    assert result.total_pnl != pytest.approx(1000.0 * ttf_shock)
