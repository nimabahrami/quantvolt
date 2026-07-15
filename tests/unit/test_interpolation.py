"""Unit tests for numerics/interpolation.py (Task 13): interpolation kernels.

Each method is exercised against a known curve shape, plus a shared check that
querying exactly at the knots returns the knot prices for all three methods.
"""

from __future__ import annotations

import numpy as np
import pytest

from quantvolt.exceptions import NumericalError
from quantvolt.numerics.interpolation import (
    INTERPOLATION_METHODS,
    cubic_spline,
    piecewise_flat,
    piecewise_linear,
)


class TestPiecewiseFlat:
    def test_holds_previous_knot_between_steps(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0, 3.0])
        knot_prices = np.array([10.0, 20.0, 30.0, 40.0])
        query_times = np.array([0.5, 1.0, 1.5, 1.999, 2.0, 2.5])
        result = piecewise_flat(knot_times, knot_prices, query_times)
        # 0.5 holds knot@0 (10); [1.0,1.5,1.999] hold knot@1 (20); 2.0 -> 30; 2.5 holds knot@2 (30).
        np.testing.assert_array_equal(result, [10.0, 20.0, 20.0, 20.0, 30.0, 30.0])

    def test_before_first_knot_takes_first_price(self) -> None:
        knot_times = np.array([1.0, 2.0, 3.0])
        knot_prices = np.array([5.0, 6.0, 7.0])
        result = piecewise_flat(knot_times, knot_prices, np.array([-2.0, 0.0, 0.999]))
        np.testing.assert_array_equal(result, [5.0, 5.0, 5.0])

    def test_past_last_knot_holds_last_price(self) -> None:
        knot_times = np.array([1.0, 2.0, 3.0])
        knot_prices = np.array([5.0, 6.0, 7.0])
        result = piecewise_flat(knot_times, knot_prices, np.array([3.0, 4.0, 100.0]))
        np.testing.assert_array_equal(result, [7.0, 7.0, 7.0])


class TestPiecewiseLinear:
    def test_recovers_linear_data_exactly_at_midpoints(self) -> None:
        # Prices lie on the line price = 3*t + 2; linear interp is exact everywhere.
        knot_times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        knot_prices = 3.0 * knot_times + 2.0
        query_times = np.array([0.5, 1.25, 2.5, 3.75])
        expected = 3.0 * query_times + 2.0
        result = piecewise_linear(knot_times, knot_prices, query_times)
        np.testing.assert_allclose(result, expected)

    def test_midpoint_is_average_of_neighbours(self) -> None:
        knot_times = np.array([0.0, 2.0])
        knot_prices = np.array([10.0, 30.0])
        result = piecewise_linear(knot_times, knot_prices, np.array([1.0]))
        np.testing.assert_allclose(result, [20.0])


class TestCubicSpline:
    def test_reproduces_known_cubic_polynomial_samples(self) -> None:
        # Sample a known cubic at the knots; the spline must pass through them exactly.
        cubic = np.poly1d([2.0, -3.0, 1.0, 5.0])
        knot_times = np.arange(0.0, 11.0, 1.0)
        knot_prices = cubic(knot_times)
        result = cubic_spline(knot_times, knot_prices, knot_times)
        np.testing.assert_allclose(result, knot_prices, atol=1e-9)

    def test_approximates_cubic_in_the_interior(self) -> None:
        # Away from the natural-BC boundaries the spline tracks the true cubic closely.
        cubic = np.poly1d([2.0, -3.0, 1.0, 5.0])
        knot_times = np.arange(0.0, 11.0, 1.0)
        knot_prices = cubic(knot_times)
        query_times = np.array([5.5])
        result = cubic_spline(knot_times, knot_prices, query_times)
        np.testing.assert_allclose(result, cubic(query_times), atol=0.1)

    def test_default_bc_type_is_natural_and_unchanged(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0, 3.0])
        knot_prices = np.array([10.0, 12.0, 9.0, 15.0])
        query_times = np.array([0.5, 1.5, 2.5])
        implicit = cubic_spline(knot_times, knot_prices, query_times)
        explicit = cubic_spline(knot_times, knot_prices, query_times, bc_type="natural")
        np.testing.assert_array_equal(implicit, explicit)

    def test_bc_type_override_changes_result(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0, 3.0])
        knot_prices = np.array([10.0, 12.0, 9.0, 15.0])
        query_times = np.array([0.5, 1.5, 2.5])
        natural = cubic_spline(knot_times, knot_prices, query_times, bc_type="natural")
        not_a_knot = cubic_spline(knot_times, knot_prices, query_times, bc_type="not-a-knot")
        assert not np.allclose(natural, not_a_knot)

    def test_invalid_bc_type_raises_value_error(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0, 3.0])
        knot_prices = np.array([10.0, 12.0, 9.0, 15.0])
        with pytest.raises(ValueError, match="bc_type"):
            cubic_spline(knot_times, knot_prices, knot_times, bc_type="bogus")

    # --- Fix 7 regression: scipy's raw ValueError must be wrapped as NumericalError --

    def test_non_increasing_knot_times_raises_numerical_error(self) -> None:
        # Previously a raw scipy ValueError escaped, violating the exceptions hierarchy.
        knot_times = np.array([1.0, 0.0, 2.0])
        knot_prices = np.array([1.0, 2.0, 3.0])
        with pytest.raises(NumericalError, match="strictly increasing"):
            cubic_spline(knot_times, knot_prices, np.array([0.5]))

    def test_mismatched_knot_lengths_raises_numerical_error(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0])
        knot_prices = np.array([1.0, 2.0])
        with pytest.raises(NumericalError):
            cubic_spline(knot_times, knot_prices, np.array([0.5]))

    def test_periodic_with_mismatched_endpoints_raises_numerical_error(self) -> None:
        knot_times = np.array([0.0, 1.0, 2.0])
        knot_prices = np.array([1.0, 2.0, 3.0])  # first != last: invalid for "periodic"
        with pytest.raises(NumericalError, match="periodic"):
            cubic_spline(knot_times, knot_prices, np.array([0.5]), bc_type="periodic")

    def test_too_few_knots_raises_numerical_error(self) -> None:
        # scipy's CubicSpline requires at least 2 knots.
        knot_times = np.array([0.0])
        knot_prices = np.array([1.0])
        with pytest.raises(NumericalError, match="at least 2"):
            cubic_spline(knot_times, knot_prices, np.array([0.5]), bc_type="not-a-knot")

    def test_numerical_error_is_also_a_value_error(self) -> None:
        # ValueError compatibility is preserved for callers using the low-level API.
        knot_times = np.array([1.0, 0.0, 2.0])
        knot_prices = np.array([1.0, 2.0, 3.0])
        with pytest.raises(ValueError):
            cubic_spline(knot_times, knot_prices, np.array([0.5]))


class TestQueryExactlyAtKnots:
    @pytest.mark.parametrize("method_name", list(INTERPOLATION_METHODS))
    def test_querying_at_knots_returns_knot_prices(self, method_name: str) -> None:
        method = INTERPOLATION_METHODS[method_name]
        knot_times = np.array([0.0, 1.5, 3.0, 6.0, 9.0])
        knot_prices = np.array([42.0, 45.5, 41.0, 50.0, 48.25])
        result = method(knot_times, knot_prices, knot_times)
        np.testing.assert_allclose(result, knot_prices, atol=1e-9)


class TestDispatchRegistry:
    def test_registry_keys_map_to_expected_functions(self) -> None:
        assert set(INTERPOLATION_METHODS) == {
            "piecewise_flat",
            "piecewise_linear",
            "cubic_spline",
        }
        assert INTERPOLATION_METHODS["piecewise_flat"] is piecewise_flat
        assert INTERPOLATION_METHODS["piecewise_linear"] is piecewise_linear
        assert INTERPOLATION_METHODS["cubic_spline"] is cubic_spline
