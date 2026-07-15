"""Unit tests for stats/descriptive.py (Task 20)."""

from __future__ import annotations

import math

import polars as pl
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.stats.descriptive import DescriptiveStats, descriptive_stats, moments

# [1, 2, 3, 4, 5]: hand-computed reference values.
#   mean      = 3.0
#   var(ddof=1) = (4+1+0+1+4)/4 = 2.5  -> std = sqrt(2.5)
#   m2 (pop)  = 10/5 = 2.0
#   m3 (pop)  = 0    -> skew = 0 (symmetric)
#   m4 (pop)  = 34/5 = 6.8 -> excess kurtosis = 6.8/2.0**2 - 3 = -1.3
_SIMPLE = [1.0, 2.0, 3.0, 4.0, 5.0]


class TestDescriptiveStats:
    def test_known_series_matches_hand_computed(self) -> None:
        result = descriptive_stats(pl.Series("prices", _SIMPLE))
        assert result.n == 5
        assert result.mean == pytest.approx(3.0)
        assert result.std == pytest.approx(math.sqrt(2.5))
        assert result.skewness == pytest.approx(0.0, abs=1e-12)
        assert result.kurtosis == pytest.approx(-1.3)

    def test_t_statistic_positive_for_positive_mean(self) -> None:
        result = descriptive_stats(pl.Series("p", _SIMPLE))
        expected = 3.0 / (math.sqrt(2.5) / math.sqrt(5))
        assert result.t_statistic == pytest.approx(expected)
        assert result.t_statistic > 0

    def test_t_statistic_flips_sign_and_keeps_magnitude_under_shift(self) -> None:
        base = descriptive_stats(pl.Series("p", _SIMPLE))
        # Shift every value by -6: same dispersion, mean sign flips (3.0 -> -3.0).
        shifted = descriptive_stats(pl.Series("p", [x - 6.0 for x in _SIMPLE]))
        assert base.t_statistic > 0
        assert shifted.t_statistic < 0
        assert shifted.t_statistic == pytest.approx(-base.t_statistic)

    def test_positive_skew_detected(self) -> None:
        # A long right tail -> positive skew.
        result = descriptive_stats(pl.Series("p", [1.0, 1.0, 1.0, 1.0, 10.0]))
        assert result.skewness > 0

    def test_nulls_are_dropped(self) -> None:
        with_nulls = pl.Series("p", [1.0, 2.0, None, 3.0, 4.0, 5.0])
        assert descriptive_stats(with_nulls) == descriptive_stats(pl.Series("p", _SIMPLE))

    @pytest.mark.filterwarnings("ignore:Precision loss occurred:RuntimeWarning")
    def test_zero_dispersion_yields_nan_t_statistic(self) -> None:
        # Constant series: std == 0, so the t-statistic is undefined (nan), not a crash.
        # SciPy warns about catastrophic cancellation on identical data; that is expected.
        result = descriptive_stats(pl.Series("p", [7.0, 7.0, 7.0]))
        assert result.std == 0.0
        assert math.isnan(result.t_statistic)

    def test_empty_series_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError, match="prices"):
            descriptive_stats(pl.Series("prices", [], dtype=pl.Float64))

    def test_single_element_raises_insufficient_data(self) -> None:
        with pytest.raises(InsufficientDataError, match="n >= 2"):
            descriptive_stats(pl.Series("p", [42.0]))

    def test_all_null_raises_insufficient_data(self) -> None:
        with pytest.raises(InsufficientDataError, match="n >= 2"):
            descriptive_stats(pl.Series("p", [None, None], dtype=pl.Float64))

    def test_input_series_not_mutated(self) -> None:
        s = pl.Series("p", [1.0, 2.0, None, 3.0, 4.0, 5.0])
        snapshot = s.clone()
        descriptive_stats(s)
        assert s.equals(snapshot, null_equal=True)

    def test_result_is_frozen(self) -> None:
        result = descriptive_stats(pl.Series("p", _SIMPLE))
        assert isinstance(result, DescriptiveStats)
        with pytest.raises(AttributeError):
            result.mean = 0.0  # type: ignore[misc]


class TestMoments:
    def test_central_moments_match_hand_computed(self) -> None:
        m = moments(pl.Series("p", _SIMPLE), order=4)
        assert set(m.keys()) == {1, 2, 3, 4}
        assert m[1] == pytest.approx(0.0, abs=1e-12)  # first central moment is 0
        assert m[2] == pytest.approx(2.0)  # population variance
        assert m[3] == pytest.approx(0.0, abs=1e-12)
        assert m[4] == pytest.approx(6.8)

    def test_dict_length_equals_order_and_keys_are_ascending(self) -> None:
        s = pl.Series("p", _SIMPLE)
        for order in (1, 2, 3, 4, 6):
            m = moments(s, order=order)
            assert len(m) == order
            assert list(m.keys()) == list(range(1, order + 1))

    def test_default_order_is_four(self) -> None:
        assert len(moments(pl.Series("p", _SIMPLE))) == 4

    def test_second_central_moment_is_population_variance(self) -> None:
        # ddof=0 variance of _SIMPLE is 2.0, distinct from the ddof=1 std reported elsewhere.
        m = moments(pl.Series("p", _SIMPLE), order=2)
        assert m[2] == pytest.approx(2.0)

    def test_nulls_are_dropped(self) -> None:
        with_nulls = moments(pl.Series("p", [1.0, 2.0, None, 3.0, 4.0, 5.0]))
        assert with_nulls == moments(pl.Series("p", _SIMPLE))

    def test_order_below_one_raises(self) -> None:
        with pytest.raises(ValidationError, match="order"):
            moments(pl.Series("p", _SIMPLE), order=0)

    def test_empty_series_raises(self) -> None:
        with pytest.raises(ValidationError, match="data"):
            moments(pl.Series("data", [], dtype=pl.Float64))

    def test_all_null_raises_insufficient_data(self) -> None:
        """FIX: moments() checked emptiness before drop_nulls with no post-drop
        guard, so an all-null series silently returned NaN moments instead of
        raising (sibling descriptive_stats already guards this via n >= 2)."""
        with pytest.raises(InsufficientDataError, match="n >= 2"):
            moments(pl.Series("p", [None, None], dtype=pl.Float64))

    def test_single_non_null_value_raises_insufficient_data(self) -> None:
        with pytest.raises(InsufficientDataError, match="n >= 2"):
            moments(pl.Series("p", [None, 42.0], dtype=pl.Float64))

    def test_input_series_not_mutated(self) -> None:
        s = pl.Series("p", [1.0, 2.0, None, 3.0, 4.0, 5.0])
        snapshot = s.clone()
        moments(s, order=4)
        assert s.equals(snapshot, null_equal=True)
