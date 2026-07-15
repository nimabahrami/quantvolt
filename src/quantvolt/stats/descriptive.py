"""Descriptive statistics (Task 20).

Stateless, module-level functions over a Polars :class:`~polars.Series` of prices (or
price changes). They validate at the boundary, drop nulls, and hand the remaining values
to NumPy / SciPy for the math. Inputs are never mutated.

Moment convention: :func:`moments` returns **central moments about the mean** with the
population (``1/n``) normalisation, i.e. ``m_k = (1/n) * sum_i (x_i - mean)**k`` for each
order ``k``. The first central moment is therefore ~0 and the second is the population
variance. The sample standard deviation reported by :func:`descriptive_stats` uses the
unbiased ``ddof=1`` normalisation instead; the two are intentionally different.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy import stats  # type: ignore[import-untyped]

from .._validation import require_non_empty, require_positive
from ..exceptions import InsufficientDataError


@dataclass(frozen=True, slots=True)
class DescriptiveStats:
    """Summary statistics of a price (or price-change) series.

    Attributes:
        mean: Arithmetic mean of the observations.
        std: Sample standard deviation (unbiased, ``ddof=1``).
        skewness: Fisher-Pearson coefficient of skewness (0 for a symmetric sample).
        kurtosis: Excess kurtosis (Fisher definition, so a normal sample is ~0).
        n: Number of non-null observations used.
        t_statistic: t-statistic for the hypothesis ``mean == 0``, i.e.
            ``mean / (std / sqrt(n))``. ``nan`` when the sample has zero dispersion.
    """

    mean: float
    std: float
    skewness: float
    kurtosis: float
    n: int
    t_statistic: float


def descriptive_stats(prices: pl.Series) -> DescriptiveStats:
    """Compute summary statistics of ``prices``.

    Nulls are dropped before any computation; the input series is left unchanged.

    Args:
        prices: A Polars Series of prices or daily price changes.

    Returns:
        A :class:`DescriptiveStats` with the mean, sample std (``ddof=1``), skewness,
        excess kurtosis, observation count, and the mean-vs-zero t-statistic.

    Raises:
        ValidationError: If ``prices`` is empty.
        InsufficientDataError: If fewer than two non-null observations remain (the
            ``n >= 2`` constraint required to estimate a sample standard deviation).
    """
    require_non_empty("prices", prices)
    values = prices.drop_nulls().to_numpy()
    n = int(values.size)
    if n < 2:
        raise InsufficientDataError(
            f"prices must have at least 2 non-null observations (n >= 2), got n={n}"
        )

    mean = float(np.mean(values))
    std = float(np.std(values, ddof=1))
    skewness = float(stats.skew(values))
    kurtosis = float(stats.kurtosis(values, fisher=True))

    standard_error = std / math.sqrt(n)
    t_statistic = mean / standard_error if standard_error != 0.0 else math.nan

    return DescriptiveStats(
        mean=mean,
        std=std,
        skewness=skewness,
        kurtosis=kurtosis,
        n=n,
        t_statistic=t_statistic,
    )


def moments(data: pl.Series, order: int = 4) -> dict[int, float]:
    """Compute central moments about the mean up to ``order``.

    Returns central moments with the population (``1/n``) normalisation:
    ``m_k = (1/n) * sum_i (x_i - mean)**k`` for ``k`` in ``1..order``. The first
    central moment is ~0 by construction and the second is the population variance.
    Nulls are dropped first; the input series is left unchanged.

    Args:
        data: A Polars Series of observations.
        order: Highest moment order to compute (default 4, i.e. up to kurtosis).

    Returns:
        A dict mapping each order ``k`` (``1..order``, in ascending order) to its central
        moment. The dict has exactly ``order`` entries.

    Raises:
        ValidationError: If ``order`` is not >= 1, or if ``data`` is empty.
        InsufficientDataError: If fewer than two non-null observations remain after
            dropping nulls (mirroring :func:`descriptive_stats`'s ``n >= 2`` guard) — a
            single observation gives a well-defined mean but every central moment
            about it is trivially zero, which would silently look like a real result
            rather than the near-absence of data it is.
    """
    require_positive("order", order)
    require_non_empty("data", data)
    values = data.drop_nulls().to_numpy()
    n = int(values.size)
    if n < 2:
        raise InsufficientDataError(
            f"data must have at least 2 non-null observations (n >= 2), got n={n}"
        )
    mean = np.mean(values)
    return {k: float(np.mean((values - mean) ** k)) for k in range(1, order + 1)}
