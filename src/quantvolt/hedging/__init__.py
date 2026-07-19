"""quantvolt.hedging — incomplete-market hedging.

Variance-minimizing and cross-commodity hedges for positions whose risk is not
fully spanned by traded instruments (Chapter 10, "Hedging in Incomplete
Markets"). The correct hedge in an incomplete market depends on the hedging
entity's risk appetite, so these kernels require an explicit corporate risk
adjustment rather than silently assuming risk-neutrality.
"""

from __future__ import annotations

from .hybrid import hybrid_deltas, residual_variance
from .mean_variance import global_mean_variance, local_mean_variance
from .ppa_nomination import (
    PpaNominationCandidate,
    PpaNominationColumns,
    PpaNominationFit,
    PpaNominationObjective,
    apply_ppa_nomination,
    calibrate_ppa_nomination,
)
from .ppa_walk_forward import PpaWalkForwardResult, walk_forward_ppa_nomination
from .variance_min import decomposed_delta, linear_cross_hedge, variance_min_hedge

__all__ = [
    "PpaNominationCandidate",
    "PpaNominationColumns",
    "PpaNominationFit",
    "PpaNominationObjective",
    "PpaWalkForwardResult",
    "apply_ppa_nomination",
    "calibrate_ppa_nomination",
    "decomposed_delta",
    "global_mean_variance",
    "hybrid_deltas",
    "linear_cross_hedge",
    "local_mean_variance",
    "residual_variance",
    "variance_min_hedge",
    "walk_forward_ppa_nomination",
]
