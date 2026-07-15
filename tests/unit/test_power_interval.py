"""Timestamped power delivery intervals stay unambiguous across local DST changes."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from quantvolt import PowerDeliveryInterval
from quantvolt.exceptions import ValidationError


def test_hourly_and_quarter_hour_duration() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)

    hourly = PowerDeliveryInterval(start, start + timedelta(hours=1))
    quarter = PowerDeliveryInterval(start, start + timedelta(minutes=15))

    assert hourly.duration_minutes == 60
    assert hourly.duration_hours == 1.0
    assert quarter.duration_minutes == 15
    assert quarter.duration_hours == 0.25


def test_naive_datetime_is_rejected() -> None:
    start = datetime(2026, 1, 1)
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        PowerDeliveryInterval(start, start + timedelta(hours=1))


def test_non_utc_datetime_is_rejected() -> None:
    cet = timezone(timedelta(hours=1))
    start = datetime(2026, 1, 1, tzinfo=cet)
    with pytest.raises(ValidationError, match="expressed in UTC"):
        PowerDeliveryInterval(start, start + timedelta(hours=1))


def test_non_positive_interval_is_rejected() -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError, match="strictly after"):
        PowerDeliveryInterval(instant, instant)


def test_subminute_duration_fails_when_queried() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    interval = PowerDeliveryInterval(start, start + timedelta(seconds=90))
    with pytest.raises(ValidationError, match="whole-minute"):
        _ = interval.duration_minutes
