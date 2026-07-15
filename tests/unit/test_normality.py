"""Unit tests for stats/normality.py (Task 21, Property 33).

Determinism: every sample is drawn from ``numpy.random.default_rng`` with a fixed
seed. The seed-0 standard-normal draw of 500 points is borderline for Jarque-Bera
at the 5% level (p ~ 0.037), so the "normal is normal" assertions use a stricter
1% acceptance level where both p-value tests classify it as normal.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.stats import normality
from quantvolt.stats.normality import _TESTS, NormalityTestResult, NormalityTestType

# The function under test is named ``test_normality``; import it under a non-``test``
# alias so pytest does not mistake it for a test case and inject a ``data`` fixture.
run_normality = normality.test_normality


def _normal_sample() -> pl.Series:
    return pl.Series("x", np.random.default_rng(0).standard_normal(500))


def _non_normal_sample() -> pl.Series:
    # Standard exponential is strongly right-skewed: unambiguously non-normal.
    return pl.Series("x", np.random.default_rng(1).standard_exponential(500))


class TestClassification:
    @pytest.mark.parametrize(
        "test_type",
        [NormalityTestType.JARQUE_BERA, NormalityTestType.DAGOSTINO_PEARSON],
    )
    def test_normal_sample_is_classified_normal(self, test_type: NormalityTestType) -> None:
        result = run_normality(_normal_sample(), test_type, acceptance_level=0.01)
        assert result.is_normal is True

    @pytest.mark.parametrize("test_type", list(NormalityTestType))
    def test_non_normal_sample_is_classified_non_normal(self, test_type: NormalityTestType) -> None:
        result = run_normality(_non_normal_sample(), test_type, acceptance_level=0.05)
        assert result.is_normal is False


class TestResultPopulated:
    @pytest.mark.parametrize("test_type", list(NormalityTestType))
    def test_each_test_type_returns_populated_result(self, test_type: NormalityTestType) -> None:
        result = run_normality(_normal_sample(), test_type, acceptance_level=0.05)

        assert isinstance(result, NormalityTestResult)
        assert result.test_type is test_type
        assert result.acceptance_level == 0.05
        assert isinstance(result.is_normal, bool)
        assert isinstance(result.statistic, float)
        assert math.isfinite(result.statistic)

        if test_type is NormalityTestType.ANDERSON_DARLING:
            # Anderson-Darling yields no p-value; the sentinel is nan.
            assert math.isnan(result.p_value)
        else:
            assert 0.0 <= result.p_value <= 1.0

    def test_default_test_type_is_jarque_bera(self) -> None:
        result = run_normality(_normal_sample())
        assert result.test_type is NormalityTestType.JARQUE_BERA
        assert result.acceptance_level == 0.05


class TestNullAndImmutability:
    def test_nulls_are_dropped_before_testing(self) -> None:
        clean = _normal_sample()
        with_nulls = pl.concat([clean, pl.Series("x", [None, None], dtype=pl.Float64)])

        from_clean = run_normality(clean, NormalityTestType.JARQUE_BERA)
        from_nulls = run_normality(with_nulls, NormalityTestType.JARQUE_BERA)

        assert from_nulls.statistic == pytest.approx(from_clean.statistic)
        assert from_nulls.p_value == pytest.approx(from_clean.p_value)
        assert from_nulls.is_normal == from_clean.is_normal

    def test_input_series_is_not_mutated(self) -> None:
        data = pl.concat([_normal_sample(), pl.Series("x", [None], dtype=pl.Float64)])
        before = data.to_list()
        run_normality(data, NormalityTestType.SHAPIRO_WILK)
        assert data.to_list() == before


class TestValidation:
    @pytest.mark.parametrize("level", [-0.1, 1.5, 2.0])
    def test_acceptance_level_out_of_range_raises(self, level: float) -> None:
        with pytest.raises(ValidationError, match="acceptance_level"):
            run_normality(_normal_sample(), acceptance_level=level)

    def test_all_null_sample_raises(self) -> None:
        empty = pl.Series("x", [None, None, None], dtype=pl.Float64)
        with pytest.raises(ValidationError, match="data"):
            run_normality(empty, NormalityTestType.JARQUE_BERA)

    def test_shapiro_below_minimum_raises(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 3"):
            run_normality(pl.Series("x", [1.0, 2.0]), NormalityTestType.SHAPIRO_WILK)

    def test_dagostino_below_minimum_raises(self) -> None:
        with pytest.raises(InsufficientDataError, match="at least 8"):
            run_normality(
                pl.Series("x", [1.0, 2.0, 3.0, 4.0, 5.0]),
                NormalityTestType.DAGOSTINO_PEARSON,
            )


class TestDispatchRegistry:
    def test_registry_covers_every_test_type(self) -> None:
        assert set(_TESTS) == set(NormalityTestType)
