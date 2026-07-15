"""quantvolt.risk — portfolio risk metrics — VaR, CVaR, aggregation, scenarios."""

from __future__ import annotations

from .aggregation import DeltaMatrix, aggregate_delta
from .cashflow_metrics import (
    CashflowStrategyComparison,
    CashflowStrategyMetrics,
    compare_cashflow_strategies,
)
from .cfar import CFaRResult, cash_flow_at_risk
from .covariance import ewma_covariance, garch11_covariance, nearest_psd
from .credit_var import CounterpartyCreditDetail, CreditVaRResult, credit_var
from .engine import ExcludedPosition, RiskEngine, RiskResult, ScenarioResult
from .mc_var import FactorModel, McVaRResult, TaggedDrift, monte_carlo_var
from .parametric_var import ParametricVaRResult, delta_gamma_var, parametric_var
from .scenarios import BUILT_IN_SCENARIOS, ScenarioCatalogue, ScenarioShock

__all__ = [
    "BUILT_IN_SCENARIOS",
    "CFaRResult",
    "CashflowStrategyComparison",
    "CashflowStrategyMetrics",
    "CounterpartyCreditDetail",
    "CreditVaRResult",
    "DeltaMatrix",
    "ExcludedPosition",
    "FactorModel",
    "McVaRResult",
    "ParametricVaRResult",
    "RiskEngine",
    "RiskResult",
    "ScenarioCatalogue",
    "ScenarioResult",
    "ScenarioShock",
    "TaggedDrift",
    "aggregate_delta",
    "cash_flow_at_risk",
    "compare_cashflow_strategies",
    "credit_var",
    "delta_gamma_var",
    "ewma_covariance",
    "garch11_covariance",
    "monte_carlo_var",
    "nearest_psd",
    "parametric_var",
]
