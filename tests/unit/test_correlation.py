"""Unit tests for stats/correlation.py (Task 23).

Covers the correlation-matrix estimators (Pearson/Spearman/Kendall) — perfect
positive/negative correlation, near-zero independence, and the symmetry + unit
diagonal invariants — plus the rolling Pearson correlation and the boundary
validations (bad method, dimension/length checks).
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.stats.correlation import correlation_matrix, rolling_correlation

METHODS = ["pearson", "spearman", "kendall"]


def _matrix(result: pl.DataFrame) -> np.ndarray:
    """Drop the leading label column and return the square matrix as numpy."""
    return result.drop("index").to_numpy()


class TestCorrelationMatrixValues:
    @pytest.mark.parametrize("method", METHODS)
    def test_perfectly_correlated_columns_are_one(self, method: str) -> None:
        base = np.arange(1.0, 21.0)
        # A strictly increasing affine map is perfectly correlated under all three
        # estimators (linear for Pearson, monotonic for Spearman/Kendall).
        df = pl.DataFrame({"a": base, "b": 2.0 * base + 3.0})
        m = _matrix(correlation_matrix(df, method=method))
        assert m[0, 1] == pytest.approx(1.0)

    @pytest.mark.parametrize("method", METHODS)
    def test_perfectly_anti_correlated_columns_are_minus_one(self, method: str) -> None:
        base = np.arange(1.0, 21.0)
        df = pl.DataFrame({"a": base, "b": -2.0 * base + 5.0})
        m = _matrix(correlation_matrix(df, method=method))
        assert m[0, 1] == pytest.approx(-1.0)

    def test_independent_columns_near_zero(self) -> None:
        rng = np.random.default_rng(20260714)
        df = pl.DataFrame({"a": rng.standard_normal(2000), "b": rng.standard_normal(2000)})
        m = _matrix(correlation_matrix(df, method="pearson"))
        assert abs(m[0, 1]) < 0.1  # loose tolerance for a finite sample

    @pytest.mark.parametrize("method", METHODS)
    def test_symmetry_and_unit_diagonal(self, method: str) -> None:
        rng = np.random.default_rng(7)
        df = pl.DataFrame(
            {
                "power": rng.standard_normal(300),
                "gas": rng.standard_normal(300),
                "carbon": rng.standard_normal(300),
            }
        )
        m = _matrix(correlation_matrix(df, method=method))
        np.testing.assert_array_equal(np.diag(m), np.ones(3))  # exact 1.0 diagonal
        np.testing.assert_allclose(m, m.T, atol=1e-12)  # symmetric

    def test_shape_and_labels(self) -> None:
        rng = np.random.default_rng(1)
        names = ["power", "gas", "carbon"]
        df = pl.DataFrame({name: rng.standard_normal(50) for name in names})
        result = correlation_matrix(df, method="pearson")
        assert result.shape == (3, 4)  # n_vars rows, n_vars + 1 columns
        assert result.columns == ["index", *names]
        assert result["index"].to_list() == names

    def test_input_not_mutated(self) -> None:
        rng = np.random.default_rng(3)
        df = pl.DataFrame({"a": rng.standard_normal(40), "b": rng.standard_normal(40)})
        before = df.clone()
        correlation_matrix(df, method="spearman")
        assert df.equals(before)


class TestCorrelationMatrixValidation:
    def test_bad_method_raises(self) -> None:
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [3.0, 2.0, 1.0]})
        with pytest.raises(ValidationError, match="method must be one of"):
            correlation_matrix(df, method="cosine")  # type: ignore[arg-type]

    def test_too_few_columns_raises(self) -> None:
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0]})
        with pytest.raises(ValidationError, match="columns"):
            correlation_matrix(df)

    def test_too_few_rows_raises(self) -> None:
        df = pl.DataFrame({"a": [1.0], "b": [2.0]})
        with pytest.raises(ValidationError, match="rows"):
            correlation_matrix(df)

    def test_null_value_is_rejected_naming_the_column(self) -> None:
        """FIX: a single null used to silently propagate as NaN off-diagonals (the
        diagonal is force-set to 1.0, masking the corruption)."""
        df = pl.DataFrame({"a": [1.0, None, 3.0, 4.0], "b": [4.0, 3.0, 2.0, 1.0]})
        with pytest.raises(ValidationError, match="'a'") as excinfo:
            correlation_matrix(df)
        assert "null" in str(excinfo.value) or "non-finite" in str(excinfo.value)

    def test_non_finite_value_is_rejected_naming_the_column(self) -> None:
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [4.0, float("inf"), 2.0, 1.0]})
        with pytest.raises(ValidationError, match="'b'"):
            correlation_matrix(df)


class TestRollingCorrelation:
    def test_length_equals_input_with_leading_nulls(self) -> None:
        a = pl.Series("a", [float(x) for x in range(1, 11)])
        b = pl.Series("b", [float(2 * x) for x in range(1, 11)])
        result = rolling_correlation(a, b, window=3)
        assert len(result) == len(a)
        # First window-1 entries are null; the rest are populated.
        assert result[:2].null_count() == 2
        assert result[2:].null_count() == 0

    def test_constant_positive_correlation_segment(self) -> None:
        base = [float(x) for x in range(1, 11)]
        a = pl.Series("a", base)
        b = pl.Series("b", [2.0 * x + 1.0 for x in base])  # perfectly correlated
        result = rolling_correlation(a, b, window=4)
        valid = result.drop_nulls().to_list()
        assert valid  # non-empty
        for value in valid:
            assert value == pytest.approx(1.0)

    def test_constant_negative_correlation_segment(self) -> None:
        base = [float(x) for x in range(1, 11)]
        a = pl.Series("a", base)
        b = pl.Series("b", [-3.0 * x for x in base])  # perfectly anti-correlated
        result = rolling_correlation(a, b, window=4)
        for value in result.drop_nulls().to_list():
            assert value == pytest.approx(-1.0)

    def test_length_mismatch_raises(self) -> None:
        a = pl.Series("a", [1.0, 2.0, 3.0])
        b = pl.Series("b", [1.0, 2.0])
        with pytest.raises(ValidationError, match="equal length"):
            rolling_correlation(a, b, window=2)

    def test_window_too_small_raises(self) -> None:
        a = pl.Series("a", [1.0, 2.0, 3.0])
        b = pl.Series("b", [3.0, 2.0, 1.0])
        with pytest.raises(ValidationError, match="window must be >= 2"):
            rolling_correlation(a, b, window=1)

    def test_window_exceeds_length_raises(self) -> None:
        a = pl.Series("a", [1.0, 2.0, 3.0])
        b = pl.Series("b", [3.0, 2.0, 1.0])
        with pytest.raises(ValidationError, match="window must be <="):
            rolling_correlation(a, b, window=4)
