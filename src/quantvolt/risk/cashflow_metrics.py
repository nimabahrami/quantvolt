"""Comparable profit and downside-risk metrics for realized strategy cash flows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import polars as pl

from .._validation import require_non_empty
from ..exceptions import ValidationError


@dataclass(frozen=True, slots=True)
class CashflowStrategyMetrics:
    """One strategy's realized cash-flow distribution and benchmark differences."""

    strategy: str
    observations: int
    total_cashflow: float
    mean_cashflow: float
    sample_std_cashflow: float
    lower_percentile_cashflow: float
    minimum_cashflow: float
    maximum_cashflow: float
    cfar: float
    negative_observations: int
    total_difference_vs_benchmark: float
    cfar_reduction_vs_benchmark: float
    volatility_reduction_vs_benchmark: float


@dataclass(frozen=True, slots=True)
class CashflowStrategyComparison:
    """Metrics in caller strategy order with an explicit benchmark identity."""

    benchmark: str
    confidence_level: float
    metrics: tuple[CashflowStrategyMetrics, ...]

    def for_strategy(self, strategy: str) -> CashflowStrategyMetrics:
        """Return one named result or fail loudly with available names."""
        for item in self.metrics:
            if item.strategy == strategy:
                return item
        available = ", ".join(item.strategy for item in self.metrics)
        raise ValidationError(f"unknown strategy {strategy!r}; available: {available}")


def compare_cashflow_strategies(
    data: pl.DataFrame,
    cashflow_columns: Mapping[str, str],
    *,
    benchmark: str,
    confidence_level: float = 0.95,
) -> CashflowStrategyComparison:
    """Compare caller-supplied periodic cash flows using one consistent convention.

    CFaR is ``max(mean - lower percentile, 0)``. Positive reduction fields mean
    lower risk than the benchmark; positive total difference means more cash flow.
    No annualization is performed because the function does not guess observation
    frequency.
    """
    if not isinstance(data, pl.DataFrame):
        raise ValidationError("data must be a polars DataFrame")
    require_non_empty("data", data)
    require_non_empty("cashflow_columns", cashflow_columns)
    if benchmark not in cashflow_columns:
        raise ValidationError(f"benchmark {benchmark!r} is not in cashflow_columns")
    if len(cashflow_columns) != len(set(cashflow_columns)):
        raise ValidationError("strategy names must be unique")
    if len(set(cashflow_columns.values())) != len(cashflow_columns):
        raise ValidationError("cashflow column mappings must be distinct")
    if not 0.0 < confidence_level < 1.0:
        raise ValidationError("confidence_level must be in (0, 1)")
    missing = sorted(set(cashflow_columns.values()) - set(data.columns))
    if missing:
        raise ValidationError(f"data is missing cashflow columns: {', '.join(missing)}")

    raw: dict[str, tuple[float, float, float, float, float, float, int]] = {}
    percentile = (1.0 - confidence_level) * 100.0
    for strategy, column in cashflow_columns.items():
        if not data.schema[column].is_numeric():
            raise ValidationError(f"cashflow column must be numeric: {column}")
        values = data[column].to_numpy().astype(float)
        if not bool(np.all(np.isfinite(values))):
            raise ValidationError(f"cashflow column must be finite and non-null: {column}")
        total = float(values.sum())
        mean = float(values.mean())
        std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        lower = float(np.percentile(values, percentile))
        raw[strategy] = (
            total,
            mean,
            std,
            lower,
            float(values.min()),
            float(values.max()),
            int((values < 0.0).sum()),
        )
    benchmark_values = raw[benchmark]
    metrics = tuple(
        CashflowStrategyMetrics(
            strategy=strategy,
            observations=data.height,
            total_cashflow=values[0],
            mean_cashflow=values[1],
            sample_std_cashflow=values[2],
            lower_percentile_cashflow=values[3],
            minimum_cashflow=values[4],
            maximum_cashflow=values[5],
            cfar=max(values[1] - values[3], 0.0),
            negative_observations=values[6],
            total_difference_vs_benchmark=values[0] - benchmark_values[0],
            cfar_reduction_vs_benchmark=max(benchmark_values[1] - benchmark_values[3], 0.0)
            - max(values[1] - values[3], 0.0),
            volatility_reduction_vs_benchmark=benchmark_values[2] - values[2],
        )
        for strategy, values in raw.items()
    )
    return CashflowStrategyComparison(benchmark, confidence_level, metrics)
