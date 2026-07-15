"""Timestamped power-delivery intervals.

Monthly :class:`~quantvolt.models.schedule.DeliveryPeriod` remains the contract
tenor used by forward curves.  Power spot, metering, dispatch, and imbalance
data need an exact half-open UTC interval instead: local clock labels are not
unique on the autumn daylight-saving transition and do not exist for one hour
on the spring transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..exceptions import ValidationError


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware UTC, got naive datetime {value!r}")
    if value.utcoffset() != timedelta(0):
        raise ValidationError(f"{name} must be expressed in UTC, got offset {value.utcoffset()}")


@dataclass(frozen=True, slots=True, order=True)
class PowerDeliveryInterval:
    """One unambiguous half-open power-delivery interval ``[start_utc, end_utc)``."""

    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        _require_utc("start_utc", self.start_utc)
        _require_utc("end_utc", self.end_utc)
        if self.end_utc <= self.start_utc:
            raise ValidationError(
                "end_utc must be strictly after start_utc; "
                f"got {self.start_utc!r}..{self.end_utc!r}"
            )

    @property
    def duration_minutes(self) -> int:
        """Exact delivery duration in whole minutes."""
        seconds = (self.end_utc - self.start_utc).total_seconds()
        minutes, remainder = divmod(seconds, 60.0)
        if remainder != 0.0:
            raise ValidationError(
                f"power delivery intervals must have whole-minute duration, got {seconds} seconds"
            )
        return int(minutes)

    @property
    def duration_hours(self) -> float:
        """Exact delivery duration in hours, used for MW-to-MWh cash-flow conversion."""
        return self.duration_minutes / 60.0
