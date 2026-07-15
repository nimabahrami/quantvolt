"""Unit tests for models/schedule.py (Task 3): DeliveryPeriod, DeliverySchedule, Granularity."""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule, Granularity


class TestGranularity:
    def test_string_values(self) -> None:
        assert Granularity.HOURLY == "hourly"
        assert Granularity.DAILY == "daily"
        assert Granularity.MONTHLY == "monthly"
        assert Granularity.QUARTERLY == "quarterly"
        assert Granularity.YEARLY == "yearly"

    def test_members(self) -> None:
        assert {g.value for g in Granularity} == {
            "hourly",
            "daily",
            "monthly",
            "quarterly",
            "yearly",
        }


class TestDeliveryPeriodLastDay:
    @pytest.mark.parametrize(
        ("year", "month", "expected"),
        [
            (2023, 1, date(2023, 1, 31)),  # January -> 31 days
            (2023, 2, date(2023, 2, 28)),  # February, non-leap -> 28 days
            (2024, 2, date(2024, 2, 29)),  # February, leap year 2024 -> 29 days
            (2023, 4, date(2023, 4, 30)),  # April -> 30 days
            (2023, 12, date(2023, 12, 31)),  # December -> 31 days
            (2000, 2, date(2000, 2, 29)),  # 2000 is a leap year (divisible by 400)
            (1900, 2, date(1900, 2, 28)),  # 1900 is NOT a leap year (divisible by 100)
        ],
    )
    def test_last_day(self, year: int, month: int, expected: date) -> None:
        assert DeliveryPeriod(year=year, month=month).last_day == expected


class TestDeliveryPeriodValidation:
    @pytest.mark.parametrize("month", [0, -1, 13, 100])
    def test_invalid_month_rejected(self, month: int) -> None:
        with pytest.raises(ValidationError, match="month"):
            DeliveryPeriod(year=2024, month=month)

    @pytest.mark.parametrize("year", [0, -5, 10000])
    def test_invalid_year_rejected(self, year: int) -> None:
        with pytest.raises(ValidationError, match="year"):
            DeliveryPeriod(year=year, month=6)

    @pytest.mark.parametrize("month", [1, 6, 12])
    def test_valid_months_accepted(self, month: int) -> None:
        period = DeliveryPeriod(year=2024, month=month)
        assert period.month == month


class TestDeliveryPeriodOrdering:
    def test_ordering_by_year_then_month(self) -> None:
        assert DeliveryPeriod(2024, 1) < DeliveryPeriod(2024, 2)
        assert DeliveryPeriod(2023, 12) < DeliveryPeriod(2024, 1)
        assert DeliveryPeriod(2024, 5) > DeliveryPeriod(2024, 4)

    def test_equality(self) -> None:
        assert DeliveryPeriod(2024, 3) == DeliveryPeriod(2024, 3)

    def test_sortable(self) -> None:
        unsorted = [
            DeliveryPeriod(2024, 3),
            DeliveryPeriod(2023, 12),
            DeliveryPeriod(2024, 1),
        ]
        assert sorted(unsorted) == [
            DeliveryPeriod(2023, 12),
            DeliveryPeriod(2024, 1),
            DeliveryPeriod(2024, 3),
        ]


class TestDeliverySchedule:
    def test_valid_schedule(self) -> None:
        periods = (
            DeliveryPeriod(2024, 1),
            DeliveryPeriod(2024, 2),
            DeliveryPeriod(2024, 3),
        )
        schedule = DeliverySchedule(periods=periods)
        assert schedule.periods == periods

    def test_valid_schedule_spanning_year_boundary(self) -> None:
        periods = (DeliveryPeriod(2023, 11), DeliveryPeriod(2023, 12), DeliveryPeriod(2024, 1))
        assert DeliverySchedule(periods=periods).periods == periods

    def test_single_period_is_valid(self) -> None:
        assert DeliverySchedule(periods=(DeliveryPeriod(2024, 6),)).periods == (
            DeliveryPeriod(2024, 6),
        )

    def test_empty_schedule_rejected(self) -> None:
        with pytest.raises(ValidationError, match="periods"):
            DeliverySchedule(periods=())

    def test_duplicate_period_rejected(self) -> None:
        periods = (DeliveryPeriod(2024, 1), DeliveryPeriod(2024, 1))
        with pytest.raises(ValidationError, match="strictly increasing"):
            DeliverySchedule(periods=periods)

    def test_out_of_order_period_rejected(self) -> None:
        periods = (DeliveryPeriod(2024, 3), DeliveryPeriod(2024, 1))
        with pytest.raises(ValidationError, match="strictly increasing"):
            DeliverySchedule(periods=periods)

    def test_out_of_order_across_years_rejected(self) -> None:
        periods = (DeliveryPeriod(2024, 1), DeliveryPeriod(2023, 12))
        with pytest.raises(ValidationError, match="strictly increasing"):
            DeliverySchedule(periods=periods)

    def test_offending_pair_index_reported(self) -> None:
        periods = (
            DeliveryPeriod(2024, 1),
            DeliveryPeriod(2024, 2),
            DeliveryPeriod(2024, 2),  # duplicate of previous -> offending pair at index 1
        )
        with pytest.raises(ValidationError, match="index 1"):
            DeliverySchedule(periods=periods)


class TestImmutability:
    def test_delivery_period_is_frozen(self) -> None:
        period = DeliveryPeriod(2024, 1)
        with pytest.raises(dataclasses.FrozenInstanceError):
            period.month = 2  # type: ignore[misc]

    def test_delivery_schedule_is_frozen(self) -> None:
        schedule = DeliverySchedule(periods=(DeliveryPeriod(2024, 1),))
        with pytest.raises(dataclasses.FrozenInstanceError):
            schedule.periods = ()  # type: ignore[misc]
