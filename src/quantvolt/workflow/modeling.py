"""ModelingWorkflow — the fixed 7-step model-selection skeleton.

``ModelingWorkflow.run`` is a fixed skeleton that
enforces the strict step ordering 1 -> 2 -> 3 -> 4 -> 5 -> (6 -> 3 loop) -> 7,
while the seven steps themselves are injected callables
(``WorkflowSteps``), not abstract methods, not inheritance. Callers customise a
step by passing e.g. ``WorkflowSteps(step4=my_fitting_step)``; the skeleton and its
ordering guarantee never change.

Risk-factor vocabulary
----------------------
Risk factors are ``"category:detail"`` strings (e.g. ``"price:power"``,
``"volatility:spark_spread"``). Categories in :data:`MODEL_INDEPENDENT_CATEGORIES` carry
*model-independent* (linear) risk — hedgeable in principle with forwards/swaps.
:data:`DEFAULT_HEDGE_INSTRUMENTS` lists the markets where such a static-hedge instrument
actually exists; a model-independent factor outside it (an illiquid hub, say) cannot be
statically hedged, and risk-factor separation fails for it. To hedge in
other markets, inject a ``step2`` closed over your own instrument registry.

The default steps are deterministic, pure module-level functions that make the workflow
run out of the box. They are a process skeleton, not a pricing engine: they carry no
market data, and real analysis/fitting/pricing is injected via :class:`WorkflowSteps`.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, TypeAlias

from .._validation import require_non_empty, require_non_negative, require_probability
from ..exceptions import ValidationError
from .criteria import ModelSelectionCriteria

MODEL_INDEPENDENT_CATEGORIES: Final[frozenset[str]] = frozenset({"price", "fx", "rate"})
"""Risk-factor categories whose exposure is linear in a tradable underlying."""

DEFAULT_HEDGE_INSTRUMENTS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "price:power": "power_forward",
        "price:gas": "gas_forward",
        "price:coal": "coal_forward",
        "price:oil": "oil_swap",
        "price:carbon": "eua_forward",
        "fx:eur_usd": "fx_forward",
        "rate:eur": "interest_rate_swap",
    }
)
"""Markets with a liquid static-hedge instrument, used by the default step 2."""


def is_model_independent(risk_factor: str) -> bool:
    """True when the factor's category (text before ``:``) is a linear, tradable risk."""
    return risk_factor.split(":", 1)[0] in MODEL_INDEPENDENT_CATEGORIES


# --- Workflow vocabulary (frozen value objects) -----------------------------------------


@dataclass(frozen=True, slots=True)
class StructuredProduct:
    """The minimal product description the workflow needs."""

    name: str
    payoff_description: str
    risk_factors: tuple[str, ...]

    def __post_init__(self) -> None:
        require_non_empty("name", self.name)
        require_non_empty("payoff_description", self.payoff_description)
        require_non_empty("risk_factors", self.risk_factors)


@dataclass(frozen=True, slots=True)
class QualitativeAnalysis:
    """Step 1 output: structural features and the product's risk factors."""

    structural_features: tuple[str, ...]
    risk_factors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StaticHedge:
    """Step 2 output: one model-independent hedge (forward/swap) per risk factor."""

    instrument_kind: str
    risk_factor: str
    hedge_ratio: float

    def __post_init__(self) -> None:
        require_non_empty("instrument_kind", self.instrument_kind)
        require_non_empty("risk_factor", self.risk_factor)
        if not math.isfinite(self.hedge_ratio):
            raise ValidationError(f"hedge_ratio must be finite, got {self.hedge_ratio!r}")


@dataclass(frozen=True, slots=True)
class ResidualAnalysis:
    """Step 3 output: what remains after the static hedges."""

    unhedged_risk_factors: tuple[str, ...]
    residual_variance_pct: float

    def __post_init__(self) -> None:
        require_probability("residual_variance_pct", self.residual_variance_pct)


@dataclass(frozen=True, slots=True)
class ResidualModel:
    """Step 4 output: the fitted model of the residual."""

    modelled_factors: tuple[str, ...]
    r_squared: float
    observation_count: int

    def __post_init__(self) -> None:
        require_probability("r_squared", self.r_squared)
        require_non_negative("observation_count", self.observation_count)


@dataclass(frozen=True, slots=True)
class DataSufficiencyReport:
    """Step 5 output: is the data good enough, and if not, what fills the gap."""

    sufficient: bool
    approximations: tuple[str, ...]
    trader_inputs_required: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConsistencyReport:
    """Step 6 output: are the residual model and the static hedges consistent."""

    consistent: bool
    discrepancy_pct: float

    def __post_init__(self) -> None:
        require_non_negative("discrepancy_pct", self.discrepancy_pct)


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    """Final output of :meth:`ModelingWorkflow.run`.

    ``price`` and ``residual_model`` are None when step 5 reported insufficient data:
    the workflow still completes with the static hedges in place, and the unmodelled
    residual is left for trader judgment.
    """

    price: float | None
    hedges: tuple[StaticHedge, ...]
    residual_model: ResidualModel | None
    data_report: DataSufficiencyReport
    steps_executed: tuple[int, ...]
    risk_factor_separation_achieved: bool


# --- Step signatures ---------------------------------------------------------------------

Step1: TypeAlias = Callable[[StructuredProduct], QualitativeAnalysis]
Step2: TypeAlias = Callable[[StructuredProduct, QualitativeAnalysis], tuple[StaticHedge, ...]]
Step3: TypeAlias = Callable[[StructuredProduct, tuple[StaticHedge, ...]], ResidualAnalysis]
Step4: TypeAlias = Callable[[ResidualAnalysis, ModelSelectionCriteria], ResidualModel]
Step5: TypeAlias = Callable[[ResidualModel, ModelSelectionCriteria], DataSufficiencyReport]
Step6: TypeAlias = Callable[[ResidualModel, tuple[StaticHedge, ...], float], ConsistencyReport]
Step7: TypeAlias = Callable[[StructuredProduct, ResidualModel, tuple[StaticHedge, ...]], float]


# --- Default step implementations (deterministic, pure) ----------------------------------


def step1_qualitative_properties(product: StructuredProduct) -> QualitativeAnalysis:
    """Identify structural features: the skeleton records the payoff description."""
    return QualitativeAnalysis(
        structural_features=(f"payoff:{product.payoff_description}",),
        risk_factors=product.risk_factors,
    )


def step2_static_hedges(
    product: StructuredProduct, qualitative: QualitativeAnalysis
) -> tuple[StaticHedge, ...]:
    """Emit one unit-ratio static hedge per factor with a listed liquid instrument."""
    return tuple(
        StaticHedge(
            instrument_kind=DEFAULT_HEDGE_INSTRUMENTS[factor],
            risk_factor=factor,
            hedge_ratio=1.0,
        )
        for factor in qualitative.risk_factors
        if factor in DEFAULT_HEDGE_INSTRUMENTS
    )


def step3_residual_investigation(
    product: StructuredProduct, hedges: tuple[StaticHedge, ...]
) -> ResidualAnalysis:
    """Report the unhedged factors; residual variance is equal-weight attributed."""
    hedged = {hedge.risk_factor for hedge in hedges}
    unhedged = tuple(factor for factor in product.risk_factors if factor not in hedged)
    return ResidualAnalysis(
        unhedged_risk_factors=unhedged,
        residual_variance_pct=len(unhedged) / len(product.risk_factors),
    )


def step4_model_residual(
    residual: ResidualAnalysis, criteria: ModelSelectionCriteria
) -> ResidualModel:
    """Model the residual.

    The skeleton carries no market data: it assumes exactly the required history is
    available and credits the model with the statically hedged share of variance.
    Real fitting is injected via ``WorkflowSteps(step4=...)``.
    """
    return ResidualModel(
        modelled_factors=residual.unhedged_risk_factors,
        r_squared=1.0 - residual.residual_variance_pct,
        observation_count=criteria.min_observations,
    )


def step5_data_check(
    model: ResidualModel, criteria: ModelSelectionCriteria
) -> DataSufficiencyReport:
    """Check observation count and fit against the criteria; flag trader inputs if short."""
    sufficient = (
        model.observation_count >= criteria.min_observations
        and model.r_squared >= criteria.min_r_squared
    )
    if sufficient:
        return DataSufficiencyReport(sufficient=True, approximations=(), trader_inputs_required=())
    trader_inputs = model.modelled_factors or ("residual model parameters",)
    return DataSufficiencyReport(
        sufficient=False,
        approximations=tuple(
            f"proxy-history approximation for {factor}" for factor in model.modelled_factors
        ),
        trader_inputs_required=trader_inputs,
    )


def step6_consistency_check(
    model: ResidualModel, hedges: tuple[StaticHedge, ...], tolerance: float
) -> ConsistencyReport:
    """Model and hedges are consistent when no factor is both hedged and modelled."""
    hedged = {hedge.risk_factor for hedge in hedges}
    double_counted = [factor for factor in model.modelled_factors if factor in hedged]
    total = len(hedged | set(model.modelled_factors))
    discrepancy_pct = len(double_counted) / total if total else 0.0
    return ConsistencyReport(
        consistent=discrepancy_pct <= tolerance, discrepancy_pct=discrepancy_pct
    )


def step7_price_and_hedge(
    product: StructuredProduct,
    model: ResidualModel,
    hedges: tuple[StaticHedge, ...],
) -> float:
    """Price the residual after static hedging.

    The default skeleton holds no market data, so it marks the residual of the
    statically replicated product at zero. Real pricing is injected via
    ``WorkflowSteps(step7=...)``.
    """
    return 0.0


@dataclass(frozen=True, slots=True)
class WorkflowSteps:
    """The seven injected step callables (Template Method via injection, not inheritance).

    Every field defaults to the module-level default step, so ``WorkflowSteps()`` is the
    out-of-the-box process and ``WorkflowSteps(step5=my_check)`` overrides exactly one step.
    """

    step1: Step1 = step1_qualitative_properties
    step2: Step2 = step2_static_hedges
    step3: Step3 = step3_residual_investigation
    step4: Step4 = step4_model_residual
    step5: Step5 = step5_data_check
    step6: Step6 = step6_consistency_check
    step7: Step7 = step7_price_and_hedge


DEFAULT_STEPS: Final[WorkflowSteps] = WorkflowSteps()


class ModelingWorkflow:
    """Steps run 1 -> 2 -> 3 -> 4 -> 5 -> (6 -> 3 loop) -> 7."""

    def run(
        self,
        product: StructuredProduct,
        criteria: ModelSelectionCriteria | None = None,
        steps: WorkflowSteps | None = None,
        max_consistency_loops: int = 3,
        tolerance: float = 0.01,
    ) -> WorkflowResult:
        """Execute the fixed 7-step skeleton over the injected step callables.

        Ordering: steps run strictly 1, 2, 3, 4, 5, 6; if step 6 reports
        inconsistency the workflow re-enters at step 3 (re-running 3, 4, 5, 6) up to
        ``max_consistency_loops`` times, then fails loudly; step 7 runs last. Every
        executed step number is recorded in order in ``WorkflowResult.steps_executed``.

        Risk-factor separation: after step 2 every model-independent risk
        factor of the product must be covered by a static hedge. If it is not and
        ``criteria.require_risk_factor_separation`` is True, a ``ValidationError`` is
        raised; otherwise the result records the failure. When step 5 reports
        insufficient data the workflow still completes — ``price`` and
        ``residual_model`` are None, the static hedges stand, and the unmodelled
        residual is left for trader judgment via ``trader_inputs_required``.

        Args:
            product: The structured product to price and hedge.
            criteria: Acceptance thresholds; defaults to ``ModelSelectionCriteria()``.
            steps: The seven step callables; defaults to the module defaults.
            max_consistency_loops: Maximum step-6 -> step-3 re-entries. Must be >= 1.
            tolerance: Consistency tolerance passed to step 6, in [0, 1].

        Raises:
            ValidationError: On invalid arguments, on a risk-factor-separation failure
                when required, or when consistency is not reached within
                ``max_consistency_loops`` loop-backs.
        """
        if criteria is None:
            criteria = ModelSelectionCriteria()
        if steps is None:
            steps = DEFAULT_STEPS
        if max_consistency_loops < 1:
            raise ValidationError(
                f"max_consistency_loops must be >= 1, got {max_consistency_loops!r}"
            )
        require_probability("tolerance", tolerance)

        executed: list[int] = []

        qualitative = steps.step1(product)
        executed.append(1)
        hedges = steps.step2(product, qualitative)
        executed.append(2)

        hedged_factors = frozenset(hedge.risk_factor for hedge in hedges)
        uncovered = tuple(
            factor
            for factor in product.risk_factors
            if is_model_independent(factor) and factor not in hedged_factors
        )
        separation_achieved = not uncovered
        if criteria.require_risk_factor_separation and not separation_achieved:
            raise ValidationError(
                "require_risk_factor_separation is violated: model-independent risk "
                f"factor(s) {uncovered!r} of product {product.name!r} have no static hedge"
            )

        loop_backs = 0
        while True:
            residual = steps.step3(product, hedges)
            executed.append(3)
            model = steps.step4(residual, criteria)
            executed.append(4)
            data_report = steps.step5(model, criteria)
            executed.append(5)
            consistency = steps.step6(model, hedges, tolerance)
            executed.append(6)
            if consistency.consistent:
                break
            loop_backs += 1
            if loop_backs > max_consistency_loops:
                raise ValidationError(
                    "residual model and static hedges are still inconsistent after "
                    f"max_consistency_loops={max_consistency_loops} loop-backs to step 3 "
                    f"(last discrepancy_pct={consistency.discrepancy_pct!r})"
                )

        price: float | None = None
        residual_model: ResidualModel | None = None
        if data_report.sufficient:
            price = steps.step7(product, model, hedges)
            executed.append(7)
            residual_model = model

        return WorkflowResult(
            price=price,
            hedges=hedges,
            residual_model=residual_model,
            data_report=data_report,
            steps_executed=tuple(executed),
            risk_factor_separation_achieved=separation_achieved,
        )
