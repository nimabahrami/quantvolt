"""quantvolt.stats — descriptive stats, normality, stationarity, correlation, mean reversion."""

from __future__ import annotations

from .correlation import correlation_matrix, rolling_correlation
from .descriptive import DescriptiveStats, descriptive_stats, moments
from .mean_reversion import MeanReversionParams, fit_ou
from .normality import NormalityTestResult, NormalityTestType, test_normality
from .stationarity import StationarityResult, test_stationarity

__all__ = [
    "DescriptiveStats",
    "MeanReversionParams",
    "NormalityTestResult",
    "NormalityTestType",
    "StationarityResult",
    "correlation_matrix",
    "descriptive_stats",
    "fit_ou",
    "moments",
    "rolling_correlation",
    "test_normality",
    "test_stationarity",
]
