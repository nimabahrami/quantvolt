"""Unit tests for weather / degree days (Task 43, Property 39)."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.market.weather import TemperatureData, degree_days
from quantvolt.testing import assert_input_unchanged


def _sample(temp_celsius: float) -> TemperatureData:
    return TemperatureData(
        location="TTF",
        day=date(2026, 1, 15),
        temp_celsius=temp_celsius,
        temp_normal=10.0,
    )


class TestTemperatureDataDegreeDays:
    def test_cold_day_has_hdd_and_no_cdd(self) -> None:
        cold = _sample(5.0)
        assert cold.heating_degree_days == pytest.approx(13.0)
        assert cold.cooling_degree_days == 0.0

    def test_hot_day_has_cdd_and_no_hdd(self) -> None:
        hot = _sample(30.0)
        assert hot.heating_degree_days == 0.0
        assert hot.cooling_degree_days == pytest.approx(12.0)

    def test_exactly_18_gives_zero_both(self) -> None:
        mild = _sample(18.0)
        assert mild.heating_degree_days == 0.0
        assert mild.cooling_degree_days == 0.0

    def test_default_base_celsius_is_18(self) -> None:
        default = _sample(5.0)
        overridden = TemperatureData(
            location="TTF",
            day=date(2026, 1, 15),
            temp_celsius=5.0,
            temp_normal=10.0,
            base_celsius=18.0,
        )
        assert default.heating_degree_days == overridden.heating_degree_days == pytest.approx(13.0)
        assert default.cooling_degree_days == overridden.cooling_degree_days == 0.0

    def test_custom_base_celsius_changes_degree_days(self) -> None:
        custom = TemperatureData(
            location="TTF",
            day=date(2026, 1, 15),
            temp_celsius=5.0,
            temp_normal=10.0,
            base_celsius=15.5,
        )
        assert custom.heating_degree_days == pytest.approx(10.5)
        assert custom.cooling_degree_days == 0.0


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "location": ["TTF", "NBP", "PEG"],
            "date": [date(2026, 1, 15), date(2026, 7, 15), date(2026, 4, 15)],
            "temp_celsius": [5.0, 30.0, 18.0],
        }
    )


class TestDegreeDays:
    def test_default_base_matches_hand_computed(self) -> None:
        result = degree_days(_frame())

        assert result.columns == ["location", "date", "temp_celsius", "hdd", "cdd"]
        assert result["hdd"].to_list() == pytest.approx([13.0, 0.0, 0.0])
        assert result["cdd"].to_list() == pytest.approx([0.0, 12.0, 0.0])

    def test_custom_base_matches_hand_computed(self) -> None:
        frame = pl.DataFrame(
            {
                "location": ["TTF", "TTF"],
                "date": [date(2026, 2, 1), date(2026, 8, 1)],
                "temp_celsius": [10.0, 20.0],
            }
        )

        result = degree_days(frame, base_celsius=15.5)

        assert result["hdd"].to_list() == pytest.approx([5.5, 0.0])
        assert result["cdd"].to_list() == pytest.approx([0.0, 4.5])

    def test_input_columns_are_preserved(self) -> None:
        frame = _frame()
        result = degree_days(frame)
        assert result.select("location", "date", "temp_celsius").equals(frame)

    def test_missing_column_raises_naming_it(self) -> None:
        frame = _frame().drop("temp_celsius")
        with pytest.raises(ValidationError, match="temp_celsius"):
            degree_days(frame)

    def test_empty_frame_raises(self) -> None:
        empty = _frame().clear()
        with pytest.raises(ValidationError, match="temperatures"):
            degree_days(empty)

    def test_input_frame_is_not_mutated(self) -> None:
        assert_input_unchanged(degree_days, _frame())
