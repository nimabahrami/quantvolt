"""Unit tests for cash_flow_at_risk (Task 67, Req 16.1-16.4, Property 52).

Covers the exact tail measure over a hand-built linear cash-flow model, the
shortfall floor at zero for a degenerate distribution, the horizon/vector-length
mismatch error, consistency-metadata round-tripping, determinism under a fixed
seed, and input immutability.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.risk.cfar import CFaRResult, Scenario, cash_flow_at_risk
from quantvolt.testing import assert_input_unchanged

_HORIZON = 4


def _linear_model(scenario: Scenario) -> npt.NDArray[np.float64]:
    """Per-period cash flow = generation (operational) x spark_spread (market).

    Constant across the horizon, so the aggregate over ``_HORIZON`` periods is
    ``_HORIZON * generation * spark_spread``.
    """
    per_period = scenario["generation"] * scenario["spark_spread"]
    return np.full(_HORIZON, per_period, dtype=np.float64)


def _three_scenarios() -> list[Scenario]:
    """Aggregates: 4*(2*5)=40, 4*(4*5)=80, 4*(6*5)=120."""
    return [
        {"generation": 2.0, "spark_spread": 5.0},
        {"generation": 4.0, "spark_spread": 5.0},
        {"generation": 6.0, "spark_spread": 5.0},
    ]


# --- exact tail measure (Req 16.1, Property 52) -------------------------------


def test_linear_model_exact_statistics() -> None:
    result = cash_flow_at_risk(_linear_model, _three_scenarios(), _HORIZON, seed=0)

    # aggregate distribution: sorted [40, 80, 120]
    assert result.aggregate_cashflows == (40.0, 80.0, 120.0)
    assert result.expected == pytest.approx(80.0)
    # numpy linear-interpolation percentiles over [40, 80, 120]:
    #   p5  = 40 + 0.10*(80-40)  = 44
    #   p50 = 80
    #   p95 = 80 + 0.90*(120-80) = 116
    assert result.p5 == pytest.approx(44.0)
    assert result.p50 == pytest.approx(80.0)
    assert result.p95 == pytest.approx(116.0)
    # cfar_95 = max(0, expected - p5) = 80 - 44 = 36
    assert result.cfar_95 == pytest.approx(36.0)


def test_horizon_and_seed_echoed() -> None:
    result = cash_flow_at_risk(_linear_model, _three_scenarios(), _HORIZON, seed=1234)
    assert result.horizon == _HORIZON
    assert result.seed == 1234


# --- shortfall floor at zero on a degenerate distribution ---------------------


def test_cfar_floors_at_zero_when_distribution_is_degenerate() -> None:
    scenarios: list[Scenario] = [{"generation": 3.0, "spark_spread": 5.0}] * 3
    result = cash_flow_at_risk(_linear_model, scenarios, _HORIZON, seed=0)

    # every scenario aggregates to the same value -> expected == p5 == p95
    assert result.expected == pytest.approx(60.0)
    assert result.p5 == pytest.approx(60.0)
    assert result.p95 == pytest.approx(60.0)
    assert result.cfar_95 == 0.0


# --- horizon / vector-length mismatch raises (Req 16.4, Property 52) ----------


def test_vector_length_mismatch_raises_naming_both() -> None:
    def wrong_length_model(scenario: Scenario) -> npt.NDArray[np.float64]:
        return np.zeros(_HORIZON + 1, dtype=np.float64)  # length 5 != horizon 4

    with pytest.raises(ValidationError) as excinfo:
        cash_flow_at_risk(wrong_length_model, _three_scenarios(), _HORIZON, seed=0)

    message = str(excinfo.value)
    assert "horizon=4" in message  # names the horizon
    assert "(5,)" in message  # names the returned length
    assert "scenario index 0" in message  # names which scenario


def test_horizon_below_one_raises() -> None:
    with pytest.raises(ValidationError, match="horizon must be > 0"):
        cash_flow_at_risk(_linear_model, _three_scenarios(), 0, seed=0)


def test_empty_scenario_set_raises() -> None:
    with pytest.raises(ValidationError, match="scenarios must be non-empty"):
        cash_flow_at_risk(_linear_model, [], _HORIZON, seed=0)


# --- consistency metadata round-trips (Req 16.2) ------------------------------


def test_consistency_metadata_round_trips_verbatim() -> None:
    consistency = {"generation": "power_price", "demand": "gas_price"}
    result = cash_flow_at_risk(
        _linear_model, _three_scenarios(), _HORIZON, seed=0, consistency=consistency
    )
    assert result.consistency == consistency


def test_consistency_metadata_defaults_to_none() -> None:
    result = cash_flow_at_risk(_linear_model, _three_scenarios(), _HORIZON, seed=0)
    assert result.consistency is None


# --- determinism (Req 16.3, Property 52) --------------------------------------


def test_two_identical_calls_are_equal() -> None:
    scenarios = _three_scenarios()
    consistency = {"generation": "power_price"}
    first = cash_flow_at_risk(_linear_model, scenarios, _HORIZON, seed=7, consistency=consistency)
    second = cash_flow_at_risk(_linear_model, scenarios, _HORIZON, seed=7, consistency=consistency)
    assert first == second
    assert isinstance(first, CFaRResult)


# --- input immutability (Req 11.4, coding-style section 7) --------------------


def test_inputs_are_not_mutated() -> None:
    scenarios = _three_scenarios()
    consistency = {"generation": "power_price", "demand": "gas_price"}
    result = assert_input_unchanged(
        cash_flow_at_risk,
        _linear_model,
        scenarios,
        _HORIZON,
        seed=0,
        consistency=consistency,
    )
    assert result.cfar_95 == pytest.approx(36.0)


# --- caller-configurable confidence level (task: expose hardcoded percentile) -


def test_default_confidence_level_matches_previous_hardcoded_behaviour() -> None:
    baseline = cash_flow_at_risk(_linear_model, _three_scenarios(), _HORIZON, seed=0)
    defaulted = cash_flow_at_risk(
        _linear_model, _three_scenarios(), _HORIZON, seed=0, confidence_level=0.95
    )
    assert defaulted == baseline
    assert defaulted.p5 == pytest.approx(44.0)
    assert defaulted.cfar_95 == pytest.approx(36.0)


def test_overriding_confidence_level_changes_p5_and_cfar_95() -> None:
    # aggregate distribution sorted: [40, 80, 120]; expected = 80.
    # confidence_level=0.50 -> percentile level 100 - 50 = 50.0 -> p_low = p50 = 80.0
    # -> cfar_95 = max(0, 80 - 80) = 0.0 (distinct from the default 36.0).
    result = cash_flow_at_risk(
        _linear_model, _three_scenarios(), _HORIZON, seed=0, confidence_level=0.50
    )
    assert result.p5 == pytest.approx(80.0)
    assert result.cfar_95 == 0.0
    # p50 / p95 are unaffected by confidence_level (only p5/cfar_95 are parametrized).
    assert result.p50 == pytest.approx(80.0)
    assert result.p95 == pytest.approx(116.0)


def test_confidence_level_out_of_range_raises() -> None:
    with pytest.raises(ValidationError, match="confidence_level"):
        cash_flow_at_risk(_linear_model, _three_scenarios(), _HORIZON, seed=0, confidence_level=1.5)


# --- documented known behaviour: the zero-collapse mode (Req 16.1, Property 52) ---
# cfar_95 = max(0, expected - p5) is spec-pinned and unchanged; this test documents,
# rather than "fixes", the collapse so callers know to inspect `expected` / `p5`.


def test_cfar_collapses_to_zero_when_extreme_tail_drags_mean_below_p5() -> None:
    horizon = 1

    def model(scenario: Scenario) -> npt.NDArray[np.float64]:
        return np.array([scenario["cashflow"]], dtype=np.float64)

    # 30 mild scenarios spread 1..30, plus one worse-case scenario. With 31 points the
    # 5th percentile's rank (0.05 * 30 = 1.5) never touches the worst-case point (index
    # 0 once sorted), so `p5` is set entirely by the mild scenarios and does not move
    # with the worst case's magnitude, while `expected` (the full-sample mean) is fully
    # exposed to it.
    good = [{"cashflow": float(v)} for v in range(1, 31)]

    mild = cash_flow_at_risk(model, [{"cashflow": -100.0}, *good], horizon, seed=0)
    assert mild.cfar_95 > 0.0  # ordinary case: a positive downside-risk measure

    catastrophic = cash_flow_at_risk(model, [{"cashflow": -1.0e9}, *good], horizon, seed=0)
    # `expected` collapses far below `p5` (which barely moved), so `expected - p5` is
    # deeply negative and the max(0.0, ...) floor reports cfar_95 == 0.0 even though
    # this book is unambiguously riskier (its `expected` is far more negative).
    assert catastrophic.expected < catastrophic.p5
    assert catastrophic.cfar_95 == 0.0
    assert catastrophic.expected < mild.expected  # the more extreme book, by `expected`
    assert catastrophic.cfar_95 < mild.cfar_95  # but NOT by cfar_95 in isolation
