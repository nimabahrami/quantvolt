"""Normality tests.

Stateless normality testing on a Polars ``Series``. The test algorithm is chosen
by :class:`NormalityTestType` through a dispatch table (Strategy) — never a
``switch`` on the enum (see ``.kiro/steering/coding-style.md`` §4).

For the p-value tests (Jarque-Bera, Shapiro-Wilk, D'Agostino-Pearson) the null
hypothesis is normality, so ``is_normal`` is ``p_value > acceptance_level``.
Anderson-Darling produces *no* p-value; ``is_normal`` is derived by comparing the
statistic against the tabulated critical value at the significance level closest
to ``acceptance_level``, and ``p_value`` is reported as ``nan`` (the documented
:data:`_NO_P_VALUE` sentinel).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray
from scipy.stats import (  # type: ignore[import-untyped]
    anderson,
    jarque_bera,
    normaltest,
    shapiro,
)

from .._validation import require_non_empty, require_probability
from ..exceptions import InsufficientDataError

if TYPE_CHECKING:
    import polars as pl


class NormalityTestType(StrEnum):
    JARQUE_BERA = "jarque_bera"  # Good for large samples
    SHAPIRO_WILK = "shapiro_wilk"  # Good for n < 50
    DAGOSTINO_PEARSON = "dagostino"  # Good for n >= 20
    ANDERSON_DARLING = "anderson"  # Sensitive to tails


@dataclass(frozen=True, slots=True)
class NormalityTestResult:
    test_type: NormalityTestType
    statistic: float
    p_value: float  # nan for Anderson-Darling (see _NO_P_VALUE)
    is_normal: bool  # at the specified acceptance level
    acceptance_level: float


# Reported p-value for tests that produce none (Anderson-Darling).
_NO_P_VALUE = float("nan")

# Minimum sample size each test needs. We fail loudly *before* calling SciPy so
# the caller gets an ``InsufficientDataError`` rather than a NaN result or a raw
# SciPy ``ValueError``.
_MIN_SAMPLE_SIZE: dict[NormalityTestType, int] = {
    NormalityTestType.JARQUE_BERA: 2,
    NormalityTestType.SHAPIRO_WILK: 3,  # SciPy requires n >= 3
    NormalityTestType.DAGOSTINO_PEARSON: 8,  # skewtest requires n >= 8
    NormalityTestType.ANDERSON_DARLING: 8,
}

# A test: (values, acceptance_level) -> (statistic, p_value, is_normal).
_NormalityTest = Callable[[NDArray[np.float64], float], tuple[float, float, bool]]


def _normal_from_pvalue(
    statistic: float, p_value: float, acceptance_level: float
) -> tuple[float, float, bool]:
    """Decision rule shared by the p-value tests: normal iff p-value exceeds the level."""
    return statistic, p_value, p_value > acceptance_level


def _jarque_bera(values: NDArray[np.float64], acceptance_level: float) -> tuple[float, float, bool]:
    statistic, p_value = jarque_bera(values)
    return _normal_from_pvalue(float(statistic), float(p_value), acceptance_level)


def _shapiro_wilk(
    values: NDArray[np.float64], acceptance_level: float
) -> tuple[float, float, bool]:
    statistic, p_value = shapiro(values)
    return _normal_from_pvalue(float(statistic), float(p_value), acceptance_level)


def _dagostino_pearson(
    values: NDArray[np.float64], acceptance_level: float
) -> tuple[float, float, bool]:
    statistic, p_value = normaltest(values)
    return _normal_from_pvalue(float(statistic), float(p_value), acceptance_level)


def _anderson_darling(
    values: NDArray[np.float64], acceptance_level: float
) -> tuple[float, float, bool]:
    # Anderson-Darling yields a statistic plus tabulated critical values, not a
    # p-value. Reject normality when the statistic exceeds the critical value at
    # the tabulated significance level closest to ``acceptance_level``. SciPy
    # exposes those critical values only via the (soon-deprecated) default call,
    # so the deliberate choice is shielded from SciPy's FutureWarning.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        result = anderson(values, dist="norm")
    statistic = float(result.statistic)
    significance_pct = np.asarray(result.significance_level, dtype=np.float64)
    critical_values = np.asarray(result.critical_values, dtype=np.float64)
    closest = int(np.argmin(np.abs(significance_pct - acceptance_level * 100.0)))
    critical = float(critical_values[closest])
    return statistic, _NO_P_VALUE, statistic < critical


_TESTS: dict[NormalityTestType, _NormalityTest] = {
    NormalityTestType.JARQUE_BERA: _jarque_bera,
    NormalityTestType.SHAPIRO_WILK: _shapiro_wilk,
    NormalityTestType.DAGOSTINO_PEARSON: _dagostino_pearson,
    NormalityTestType.ANDERSON_DARLING: _anderson_darling,
}


def _require_sufficient(test_type: NormalityTestType, n: int) -> None:
    minimum = _MIN_SAMPLE_SIZE[test_type]
    if n < minimum:
        raise InsufficientDataError(
            f"{test_type.value} normality test requires at least {minimum} observations, got {n}"
        )


def test_normality(
    data: pl.Series,
    test_type: NormalityTestType = NormalityTestType.JARQUE_BERA,
    acceptance_level: float = 0.05,
) -> NormalityTestResult:
    """Test whether ``data`` follows a normal distribution at ``acceptance_level``.

    Nulls are dropped before testing and the input is never mutated. The test is
    selected from :data:`_TESTS` by ``test_type`` (Strategy dispatch).

    Args:
        data: Sample to test (a Polars ``Series``); nulls are ignored.
        test_type: Which normality test to run.
        acceptance_level: Significance level in ``[0, 1]`` (e.g. ``0.05``).

    Returns:
        A :class:`NormalityTestResult`. For the p-value tests ``is_normal`` is
        ``p_value > acceptance_level``; for Anderson-Darling ``p_value`` is
        ``nan`` and ``is_normal`` compares the statistic to the critical value at
        the significance level closest to ``acceptance_level``.

    Raises:
        ValidationError: If ``acceptance_level`` is outside ``[0, 1]`` or the
            (null-dropped) sample is empty.
        InsufficientDataError: If the sample is smaller than the chosen test's
            minimum size.
    """
    require_probability("acceptance_level", acceptance_level)
    values: NDArray[np.float64] = data.drop_nulls().to_numpy().astype(np.float64, copy=False)
    require_non_empty("data", values)
    _require_sufficient(test_type, int(values.size))

    statistic, p_value, is_normal = _TESTS[test_type](values, acceptance_level)
    return NormalityTestResult(
        test_type=test_type,
        statistic=statistic,
        p_value=p_value,
        is_normal=is_normal,
        acceptance_level=acceptance_level,
    )
