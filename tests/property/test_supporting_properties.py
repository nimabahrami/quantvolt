"""Supporting-module correctness properties (design Properties 38-41; Task 49).

Each test is tagged with its design Property number and runs >= 100 Hypothesis
examples (profile ``quantvolt`` in ``tests/conftest.py``).
"""

from __future__ import annotations

import re

import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.market.transmission import Pipeline, transmission_cost
from quantvolt.market.weather import degree_days
from quantvolt.workflow.criteria import ModelSelectionCriteria
from quantvolt.workflow.modeling import (
    DEFAULT_HEDGE_INSTRUMENTS,
    ConsistencyReport,
    DataSufficiencyReport,
    ModelingWorkflow,
    ResidualModel,
    StaticHedge,
    StructuredProduct,
    WorkflowSteps,
    is_model_independent,
)
from strategies import temperature_frames

_TARIFFS = st.floats(min_value=0.0, max_value=1_000.0)
_VOLUMES = st.floats(min_value=0.0, max_value=1_000_000.0)
_DISTANCES = st.floats(min_value=0.0, max_value=10_000.0)
_BASE_TEMPS = st.floats(min_value=-10.0, max_value=30.0)

# Model-independent factors with a listed liquid hedge, and model-dependent extras.
_HEDGEABLE_FACTORS = tuple(sorted(DEFAULT_HEDGE_INSTRUMENTS))
_MODEL_DEPENDENT_FACTORS = (
    "volatility:spark_spread",
    "volatility:power",
    "correlation:power_gas",
    "demand:heating",
)
# The design's Property 40 step sequence: 1, 2, one or more (3,4,5,6) passes, then 7.
_STEP_PATTERN = re.compile(r"1,2,(?:3,4,5,6,)+7")


class _FlakyStep6:
    """Injected step 6 reporting inconsistency for the first ``failures`` calls."""

    def __init__(self, failures: int) -> None:
        self._remaining = failures

    def __call__(
        self,
        model: ResidualModel,
        hedges: tuple[StaticHedge, ...],
        tolerance: float,
    ) -> ConsistencyReport:
        if self._remaining > 0:
            self._remaining -= 1
            return ConsistencyReport(consistent=False, discrepancy_pct=0.5)
        return ConsistencyReport(consistent=True, discrepancy_pct=0.0)


def _insufficient_step5(
    model: ResidualModel, criteria: ModelSelectionCriteria
) -> DataSufficiencyReport:
    return DataSufficiencyReport(
        sufficient=False,
        approximations=("proxy history from correlated hub",),
        trader_inputs_required=("residual volatility level",),
    )


# Feature: power-energy-quant-analysis, Property 38: Transmission Cost Determinism
@given(
    distance=_DISTANCES,
    tariff=_TARIFFS,
    volume=_VOLUMES,
    other_tariff=_TARIFFS,
    other_volume=_VOLUMES,
)
@settings(max_examples=100)
def test_transmission_cost_is_tariff_times_volume_nonnegative_and_call_order_free(
    distance: float, tariff: float, volume: float, other_tariff: float, other_volume: float
) -> None:
    pipeline = Pipeline(distance=distance, tariff=tariff)
    first = transmission_cost(pipeline, volume)
    assert first == tariff * volume
    assert first >= 0.0
    # Interleave an unrelated query: the original result must be unaffected.
    other = transmission_cost(Pipeline(distance=distance, tariff=other_tariff), other_volume)
    assert other == other_tariff * other_volume
    assert transmission_cost(pipeline, volume) == first


# Feature: power-energy-quant-analysis, Property 39: Weather Data Immutability
# The implemented weather module is pure computation over a caller-supplied frame
# (no fetching, no cache), so the design's cache-independence reads as: repeated
# calls with the same inputs return identical frames and never mutate the input.
# The hdd/cdd values are checked row-wise against a plain Python loop.
@given(frame=temperature_frames(), base_celsius=_BASE_TEMPS)
@settings(max_examples=100)
def test_degree_days_match_a_python_loop_and_leave_the_input_frame_unchanged(
    frame: pl.DataFrame, base_celsius: float
) -> None:
    snapshot = frame.clone()
    result = degree_days(frame, base_celsius)
    assert result.columns == [*frame.columns, "hdd", "cdd"]
    temps = frame["temp_celsius"].to_list()
    hdd = result["hdd"].to_list()
    cdd = result["cdd"].to_list()
    for temp, heating, cooling in zip(temps, hdd, cdd, strict=True):
        assert heating == max(0.0, base_celsius - temp)
        assert cooling == max(0.0, temp - base_celsius)
    # Determinism and input immutability.
    assert degree_days(frame, base_celsius).equals(result)
    assert frame.equals(snapshot)


@st.composite
def _hedgeable_products(draw: st.DrawFn) -> StructuredProduct:
    """A product whose every risk factor has a listed static hedge, so the default
    steps reach full risk-factor separation and a sufficient data report."""
    factors = draw(
        st.lists(st.sampled_from(_HEDGEABLE_FACTORS), min_size=1, max_size=5, unique=True)
    )
    return StructuredProduct(
        name="drawn_product",
        payoff_description="drawn structured payoff",
        risk_factors=tuple(factors),
    )


@st.composite
def _mixed_products(draw: st.DrawFn) -> StructuredProduct:
    """A product mixing hedgeable model-independent factors with model-dependent ones."""
    independent = draw(
        st.lists(st.sampled_from(_HEDGEABLE_FACTORS), min_size=1, max_size=4, unique=True)
    )
    dependent = draw(
        st.lists(st.sampled_from(_MODEL_DEPENDENT_FACTORS), min_size=1, max_size=3, unique=True)
    )
    return StructuredProduct(
        name="drawn_mixed_product",
        payoff_description="drawn structured payoff with residual",
        risk_factors=tuple(independent) + tuple(dependent),
    )


# Feature: power-energy-quant-analysis, Property 40: Modeling Workflow Step Ordering
@given(product=_hedgeable_products(), step6_failures=st.integers(min_value=0, max_value=2))
@settings(max_examples=100)
def test_steps_execute_as_1_2_then_3_4_5_6_loops_then_7(
    product: StructuredProduct, step6_failures: int
) -> None:
    steps = WorkflowSteps(step6=_FlakyStep6(failures=step6_failures))
    result = ModelingWorkflow().run(product, steps=steps, max_consistency_loops=3)
    # Exact ordering: 1, 2, then one (3,4,5,6) pass per step-6 verdict, then 7.
    expected = (1, 2) + (3, 4, 5, 6) * (step6_failures + 1) + (7,)
    assert result.steps_executed == expected
    # And the design's regex form of the same invariant.
    assert _STEP_PATTERN.fullmatch(",".join(map(str, result.steps_executed)))
    assert result.price is not None
    assert result.residual_model is not None


# Feature: power-energy-quant-analysis, Property 41: Risk Factor Separation
@given(product=_mixed_products())
@settings(max_examples=100)
def test_insufficient_data_still_completes_with_static_hedges_covering_linear_risk(
    product: StructuredProduct,
) -> None:
    steps = WorkflowSteps(step5=_insufficient_step5)
    result = ModelingWorkflow().run(product, steps=steps)
    # The run completes without step 7: no price, no accepted residual model.
    assert result.steps_executed == (1, 2, 3, 4, 5, 6)
    assert result.price is None
    assert result.residual_model is None
    assert result.data_report.sufficient is False
    assert result.data_report.trader_inputs_required  # residual left to trader judgment
    # Separation achieved: every model-independent factor carries a static hedge.
    assert result.risk_factor_separation_achieved is True
    hedged_factors = {hedge.risk_factor for hedge in result.hedges}
    independent_factors = {
        factor for factor in product.risk_factors if is_model_independent(factor)
    }
    assert independent_factors <= hedged_factors
    for hedge in result.hedges:
        assert hedge.instrument_kind == DEFAULT_HEDGE_INSTRUMENTS[hedge.risk_factor]


# Feature: power-energy-quant-analysis, Property 41: Risk Factor Separation
@given(product=_mixed_products(), suffix=st.integers(min_value=0, max_value=9))
@settings(max_examples=100)
def test_an_unhedgeable_linear_factor_is_reported_when_separation_is_not_required(
    product: StructuredProduct, suffix: int
) -> None:
    illiquid = StructuredProduct(
        name=product.name,
        payoff_description=product.payoff_description,
        risk_factors=(*product.risk_factors, f"price:illiquid_hub_{suffix}"),
    )
    criteria = ModelSelectionCriteria(require_risk_factor_separation=False)
    result = ModelingWorkflow().run(illiquid, criteria=criteria)
    # The separation flag is computed (False) and the run still completes.
    assert result.risk_factor_separation_achieved is False
    assert result.steps_executed[:2] == (1, 2)
    hedged_factors = {hedge.risk_factor for hedge in result.hedges}
    assert f"price:illiquid_hub_{suffix}" not in hedged_factors


# Feature: power-energy-quant-analysis, Property 41: Risk Factor Separation
@given(product=_mixed_products(), suffix=st.integers(min_value=0, max_value=9))
@settings(max_examples=100)
def test_an_unhedgeable_linear_factor_fails_loudly_when_separation_is_required(
    product: StructuredProduct, suffix: int
) -> None:
    illiquid = StructuredProduct(
        name=product.name,
        payoff_description=product.payoff_description,
        risk_factors=(*product.risk_factors, f"price:illiquid_hub_{suffix}"),
    )
    with pytest.raises(ValidationError) as excinfo:
        ModelingWorkflow().run(illiquid)  # default criteria require separation
    message = str(excinfo.value)
    assert "require_risk_factor_separation" in message
    assert f"price:illiquid_hub_{suffix}" in message
