"""Unit tests for numerics/daycount.py (Task 11): actual/365 day-count."""

from __future__ import annotations

from datetime import date

import pytest

from quantvolt.numerics.daycount import actual_360, actual_365


class TestActual360:
    def test_exactly_360_days_is_one_year(self) -> None:
        assert actual_360(date(2023, 1, 1), date(2023, 12, 27)) == 1.0

    def test_zero_span_is_zero(self) -> None:
        d = date(2024, 6, 15)
        assert actual_360(d, d) == 0.0

    def test_known_partial_span(self) -> None:
        assert actual_360(date(2023, 1, 1), date(2023, 1, 31)) == pytest.approx(30.0 / 360.0)

    def test_reversed_dates_are_signed_negative(self) -> None:
        assert actual_360(date(2023, 12, 27), date(2023, 1, 1)) == -1.0

    def test_antisymmetry(self) -> None:
        a, b = date(2023, 3, 10), date(2023, 9, 22)
        assert actual_360(a, b) == pytest.approx(-actual_360(b, a))

    def test_differs_from_actual_365_for_the_same_span(self) -> None:
        a, b = date(2023, 1, 1), date(2023, 7, 1)
        assert actual_360(a, b) != actual_365(a, b)
        assert actual_360(a, b) == pytest.approx((b - a).days / 360.0)


class TestActual365:
    def test_exactly_365_days_is_one_year(self) -> None:
        # 2023 is a non-leap year, so 1 Jan 2023 -> 1 Jan 2024 is exactly 365 days.
        assert actual_365(date(2023, 1, 1), date(2024, 1, 1)) == 1.0

    def test_zero_span_is_zero(self) -> None:
        d = date(2024, 6, 15)
        assert actual_365(d, d) == 0.0

    def test_known_partial_span(self) -> None:
        # 1 Jan -> 31 Jan 2023 is 30 elapsed days.
        assert actual_365(date(2023, 1, 1), date(2023, 1, 31)) == pytest.approx(30.0 / 365.0)

    def test_leap_span_counts_actual_days(self) -> None:
        # 28 Feb 2024 -> 1 Mar 2024 crosses the 29 Feb leap day: 2 actual days.
        assert actual_365(date(2024, 2, 28), date(2024, 3, 1)) == pytest.approx(2.0 / 365.0)

    def test_full_leap_year_span_exceeds_one(self) -> None:
        # 1 Jan 2024 -> 1 Jan 2025 spans the leap year 2024: 366 actual days.
        assert actual_365(date(2024, 1, 1), date(2025, 1, 1)) == pytest.approx(366.0 / 365.0)

    def test_reversed_dates_are_signed_negative(self) -> None:
        assert actual_365(date(2024, 1, 1), date(2023, 1, 1)) == -1.0

    def test_antisymmetry(self) -> None:
        a, b = date(2023, 3, 10), date(2023, 9, 22)
        assert actual_365(a, b) == pytest.approx(-actual_365(b, a))
