"""quantvolt.assets — physical-asset optimization (Reqs 21-23).

Thermal-generation dispatch, gas storage, and long-dated valuation governance.
This package holds the *operational* asset models: equipment and operating
constraints translated into optimization states, feasible actions, cash flows,
and asset optionality — the guard against unconstrained financial analogies
overstating physical value.
"""

from __future__ import annotations

from .dispatch_approx import BangBangHedgeWarning, bang_bang, horizon_divide, time_aggregate
from .dispatch_deterministic import DispatchSchedule, dispatch_deterministic
from .dispatch_sdp import (
    DispatchDiagnostics,
    DispatchFactorModel,
    DispatchResult,
    FactorTransform,
    MonteCarloEvaluation,
    PeakKind,
    PhysicalFactorMapping,
    dispatch_value,
)
from .long_dated import (
    BenchmarkResult,
    CorporatePremium,
    LowerBoundResult,
    ValuationSource,
    VarApplicabilityVerdict,
    furthest_forward_lower_bound,
    valuation_benchmark,
    var_applicability_guard,
)
from .plant import PlantModel, StartCost, StartState
from .storage import (
    IntrinsicResult,
    StorageFactorModel,
    StorageModel,
    StorageValueResult,
    storage_intrinsic,
    storage_value,
)

__all__ = [
    "BangBangHedgeWarning",
    "BenchmarkResult",
    "CorporatePremium",
    "DispatchDiagnostics",
    "DispatchFactorModel",
    "DispatchResult",
    "DispatchSchedule",
    "FactorTransform",
    "IntrinsicResult",
    "LowerBoundResult",
    "MonteCarloEvaluation",
    "PeakKind",
    "PhysicalFactorMapping",
    "PlantModel",
    "StartCost",
    "StartState",
    "StorageFactorModel",
    "StorageModel",
    "StorageValueResult",
    "ValuationSource",
    "VarApplicabilityVerdict",
    "bang_bang",
    "dispatch_deterministic",
    "dispatch_value",
    "furthest_forward_lower_bound",
    "horizon_divide",
    "storage_intrinsic",
    "storage_value",
    "time_aggregate",
    "valuation_benchmark",
    "var_applicability_guard",
]
