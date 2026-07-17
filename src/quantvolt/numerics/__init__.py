"""quantvolt.numerics — pure math kernels — float/ndarray in and out."""

from __future__ import annotations

from .black76 import black76_greeks, black76_implied_vol, black76_price
from .daycount import actual_360, actual_365
from .exotic import (
    barrier_analytic,
    kemna_vorst,
    lookback_fixed,
    lookback_floating,
    turnbull_wakeman,
)
from .interpolation import (
    INTERPOLATION_METHODS,
    InterpolationMethod,
    cubic_spline,
    piecewise_flat,
    piecewise_linear,
)
from .monte_carlo import (
    CorrelatedSimulationRequest,
    asian_monte_carlo,
    build_covariance,
    simulate_correlated_forwards,
    simulate_correlated_term_structure,
    simulate_ou_paths,
)
from .risk_adjustment import (
    DriftKind,
    PriceOfRiskKind,
    price_of_risk,
    require_physical_drift,
    risk_adjusted_drift,
    tradable_price_of_risk,
)
from .rootfind import brent_root, finite_difference_bump
from .spread_models import kirk, margrabe

__all__ = [
    "INTERPOLATION_METHODS",
    "CorrelatedSimulationRequest",
    "DriftKind",
    "InterpolationMethod",
    "PriceOfRiskKind",
    "actual_360",
    "actual_365",
    "asian_monte_carlo",
    "barrier_analytic",
    "black76_greeks",
    "black76_implied_vol",
    "black76_price",
    "brent_root",
    "build_covariance",
    "cubic_spline",
    "finite_difference_bump",
    "kemna_vorst",
    "kirk",
    "lookback_fixed",
    "lookback_floating",
    "margrabe",
    "piecewise_flat",
    "piecewise_linear",
    "price_of_risk",
    "require_physical_drift",
    "risk_adjusted_drift",
    "simulate_correlated_forwards",
    "simulate_correlated_term_structure",
    "simulate_ou_paths",
    "tradable_price_of_risk",
    "turnbull_wakeman",
]
