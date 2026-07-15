"""Model-selection criteria (Task 44)."""

from __future__ import annotations

from dataclasses import dataclass

from .._validation import require_positive, require_probability


@dataclass(frozen=True, slots=True)
class ModelSelectionCriteria:
    """Thresholds the 7-step modeling workflow applies when accepting a residual model.

    Attributes:
        min_observations: Minimum history length (observations) a residual model must be
            fitted on. Must be >= 1.
        max_missing_pct: Maximum tolerated fraction of missing data, in [0, 1].
        min_r_squared: Minimum acceptable model fit (R-squared), in [0, 1].
        max_rmse_pct: Maximum acceptable RMSE as a fraction of price level, in [0, 1].
        max_parameter_drift: Maximum tolerated parameter change over a rolling window,
            as a fraction, in [0, 1].
        require_risk_factor_separation: When True, ``ModelingWorkflow.run`` fails loudly
            if any model-independent risk factor is left without a static hedge
            (Property 41); when False the result merely records the failure.
    """

    min_observations: int = 252
    max_missing_pct: float = 0.05
    min_r_squared: float = 0.7
    max_rmse_pct: float = 0.10
    max_parameter_drift: float = 0.20
    require_risk_factor_separation: bool = True

    def __post_init__(self) -> None:
        require_positive("min_observations", self.min_observations)
        require_probability("max_missing_pct", self.max_missing_pct)
        require_probability("min_r_squared", self.min_r_squared)
        require_probability("max_rmse_pct", self.max_rmse_pct)
        require_probability("max_parameter_drift", self.max_parameter_drift)
