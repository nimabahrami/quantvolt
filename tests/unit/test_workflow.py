"""Unit tests for the model-selection workflow (Task 44, Properties 40 and 41)."""

from __future__ import annotations

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.testing import assert_input_unchanged
from quantvolt.workflow.criteria import ModelSelectionCriteria
from quantvolt.workflow.modeling import (
    ConsistencyReport,
    DataSufficiencyReport,
    ModelingWorkflow,
    ResidualModel,
    StaticHedge,
    StructuredProduct,
    WorkflowResult,
    WorkflowSteps,
)

# All risk factors carry a liquid static hedge -> fully model-independent product.
HEDGEABLE_PRODUCT = StructuredProduct(
    name="power_gas_swap",
    payoff_description="fixed-for-floating power vs gas",
    risk_factors=("price:power", "price:gas"),
)

# One model-dependent (volatility) factor left as residual for the model.
RESIDUAL_PRODUCT = StructuredProduct(
    name="virtual_power_plant",
    payoff_description="strip of spark-spread options",
    risk_factors=("price:power", "price:gas", "volatility:spark_spread"),
)

# "price:illiquid_hub" is model-independent (a price risk) but has no listed
# static-hedge instrument -> risk-factor separation cannot be achieved.
ILLIQUID_PRODUCT = StructuredProduct(
    name="illiquid_hub_forward",
    payoff_description="forward on an illiquid hub",
    risk_factors=("price:power", "price:illiquid_hub"),
)


def assert_property_40_ordering(steps_executed: tuple[int, ...]) -> None:
    """Only 1,2 then one-or-more (3,4,5,6) passes then an optional final 7 may occur."""
    assert steps_executed[:2] == (1, 2)
    body = steps_executed[2:]
    if body and body[-1] == 7:
        body = body[:-1]
    assert len(body) >= 4 and len(body) % 4 == 0
    for i in range(0, len(body), 4):
        assert body[i : i + 4] == (3, 4, 5, 6)


class _FlakyStep6:
    """Injected step 6 that reports inconsistency for the first ``failures`` calls."""

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


class TestStepOrdering:
    """Property 40: strict order 1 -> 2 -> 3 -> 4 -> 5 -> (6 -> 3 loop) -> 7."""

    def test_default_consistent_run_records_1_through_7(self) -> None:
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT)
        assert result.steps_executed == (1, 2, 3, 4, 5, 6, 7)
        assert_property_40_ordering(result.steps_executed)

    def test_step6_failing_once_reenters_at_step_3(self) -> None:
        steps = WorkflowSteps(step6=_FlakyStep6(failures=1))
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT, steps=steps)
        assert result.steps_executed == (1, 2, 3, 4, 5, 6, 3, 4, 5, 6, 7)
        assert_property_40_ordering(result.steps_executed)

    @pytest.mark.parametrize("failures", [0, 1, 2, 3])
    def test_no_other_orderings_occur(self, failures: int) -> None:
        steps = WorkflowSteps(step6=_FlakyStep6(failures=failures))
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT, steps=steps)
        expected = (1, 2) + (3, 4, 5, 6) * (failures + 1) + (7,)
        assert result.steps_executed == expected
        assert_property_40_ordering(result.steps_executed)

    def test_never_consistent_raises_naming_the_limit(self) -> None:
        steps = WorkflowSteps(step6=_FlakyStep6(failures=99))
        with pytest.raises(ValidationError, match="max_consistency_loops=2"):
            ModelingWorkflow().run(HEDGEABLE_PRODUCT, steps=steps, max_consistency_loops=2)

    def test_insufficient_data_run_stops_after_step_6(self) -> None:
        steps = WorkflowSteps(step5=_insufficient_step5)
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT, steps=steps)
        assert result.steps_executed == (1, 2, 3, 4, 5, 6)
        assert_property_40_ordering(result.steps_executed)


class TestRiskFactorSeparation:
    """Property 41: static hedges cover model-independent risks even with poor data."""

    def test_insufficient_data_still_completes_with_separation(self) -> None:
        steps = WorkflowSteps(step5=_insufficient_step5)
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT, steps=steps)
        assert result.price is None
        assert result.residual_model is None
        hedged = {hedge.risk_factor for hedge in result.hedges}
        assert hedged == {"price:power", "price:gas"}
        assert not result.data_report.sufficient
        assert result.data_report.trader_inputs_required == ("residual volatility level",)
        assert result.risk_factor_separation_achieved is True

    def test_default_steps_leave_unmodellable_residual_to_trader(self) -> None:
        # Default step 4 credits the model with the hedged share of variance: 2/3 of
        # RESIDUAL_PRODUCT is hedged, so r_squared < min_r_squared -> insufficient data.
        result = ModelingWorkflow().run(RESIDUAL_PRODUCT)
        assert result.price is None
        assert result.residual_model is None
        hedged = {hedge.risk_factor for hedge in result.hedges}
        assert hedged == {"price:power", "price:gas"}
        assert result.data_report.trader_inputs_required == ("volatility:spark_spread",)
        assert result.risk_factor_separation_achieved is True

    def test_unhedgeable_model_independent_factor_raises_when_required(self) -> None:
        criteria = ModelSelectionCriteria(require_risk_factor_separation=True)
        with pytest.raises(ValidationError, match="price:illiquid_hub"):
            ModelingWorkflow().run(ILLIQUID_PRODUCT, criteria)

    def test_unhedgeable_factor_completes_when_separation_not_required(self) -> None:
        criteria = ModelSelectionCriteria(require_risk_factor_separation=False)
        result = ModelingWorkflow().run(ILLIQUID_PRODUCT, criteria)
        assert result.risk_factor_separation_achieved is False
        hedged = {hedge.risk_factor for hedge in result.hedges}
        assert hedged == {"price:power"}


class TestCriteriaValidation:
    def test_defaults_are_valid(self) -> None:
        criteria = ModelSelectionCriteria()
        assert criteria.min_observations == 252
        assert criteria.require_risk_factor_separation is True

    def test_boundary_values_construct(self) -> None:
        ModelSelectionCriteria(
            min_observations=1,
            max_missing_pct=0.0,
            min_r_squared=1.0,
            max_rmse_pct=1.0,
            max_parameter_drift=0.0,
        )

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("min_observations", 0),
            ("min_observations", -10),
            ("max_missing_pct", -0.01),
            ("max_missing_pct", 1.01),
            ("min_r_squared", -0.5),
            ("min_r_squared", 1.5),
            ("max_rmse_pct", -1.0),
            ("max_rmse_pct", 2.0),
            ("max_parameter_drift", -0.2),
            ("max_parameter_drift", 1.2),
        ],
    )
    def test_bad_ranges_raise_naming_the_field(self, field: str, value: float) -> None:
        with pytest.raises(ValidationError, match=field):
            ModelSelectionCriteria(**{field: value})


class TestRunArgumentValidation:
    def test_zero_max_consistency_loops_rejected(self) -> None:
        with pytest.raises(ValidationError, match="max_consistency_loops"):
            ModelingWorkflow().run(HEDGEABLE_PRODUCT, max_consistency_loops=0)

    def test_out_of_range_tolerance_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tolerance"):
            ModelingWorkflow().run(HEDGEABLE_PRODUCT, tolerance=1.5)


class TestValueObjectValidation:
    def test_product_requires_risk_factors(self) -> None:
        with pytest.raises(ValidationError, match="risk_factors"):
            StructuredProduct(name="x", payoff_description="y", risk_factors=())

    def test_hedge_ratio_must_be_finite(self) -> None:
        with pytest.raises(ValidationError, match="hedge_ratio"):
            StaticHedge(
                instrument_kind="forward", risk_factor="price:power", hedge_ratio=float("inf")
            )

    def test_residual_model_r_squared_range(self) -> None:
        with pytest.raises(ValidationError, match="r_squared"):
            ResidualModel(modelled_factors=(), r_squared=1.5, observation_count=10)


class TestDeterminism:
    @pytest.mark.parametrize("product", [HEDGEABLE_PRODUCT, RESIDUAL_PRODUCT])
    def test_same_inputs_give_equal_results(self, product: StructuredProduct) -> None:
        first = ModelingWorkflow().run(product)
        second = ModelingWorkflow().run(product)
        assert isinstance(first, WorkflowResult)
        assert first == second

    def test_default_sufficient_run_prices_residual_at_zero(self) -> None:
        result = ModelingWorkflow().run(HEDGEABLE_PRODUCT)
        assert result.price == 0.0
        assert result.residual_model is not None
        assert result.risk_factor_separation_achieved is True


class TestInputImmutability:
    def test_run_does_not_mutate_its_inputs(self) -> None:
        product = StructuredProduct(
            name="power_gas_swap",
            payoff_description="fixed-for-floating power vs gas",
            risk_factors=("price:power", "price:gas"),
        )
        criteria = ModelSelectionCriteria()
        result = assert_input_unchanged(ModelingWorkflow().run, product, criteria)
        assert result.steps_executed == (1, 2, 3, 4, 5, 6, 7)
