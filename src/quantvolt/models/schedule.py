"""Delivery periods, schedules, and granularity.

These are pure, immutable value objects (Tell-Don't-Ask): each type answers
queries about *its own* data. A :class:`DeliveryPeriod` knows its own calendar
extent (:attr:`~DeliveryPeriod.last_day`) and how to order itself against another
period; callers never reach into ``.year``/``.month`` to recompute those.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import MAXYEAR, MINYEAR, date
from enum import StrEnum

from .._validation import require_in_range, require_non_empty
from ..exceptions import ValidationError


class Granularity(StrEnum):
    """Single source of delivery granularity, reused by instruments (Task 3)."""

    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


@dataclass(frozen=True, slots=True, order=True)
class DeliveryPeriod:
    """A single calendar month of delivery, identified by ``(year, month)``.

    ``order=True`` gives periods a natural chronological ordering: comparisons and
    ``sorted(...)`` fall back to the ``(year, month)`` tuple in field order, so a
    period knows how to rank itself (Tell-Don't-Ask) and callers never compare raw
    ints. Years are constrained to the range :class:`datetime.date` can represent,
    which also guarantees :attr:`last_day` never fails.
    """

    year: int
    month: int  # 1-12; a calendar month

    def __post_init__(self) -> None:
        require_in_range("year", self.year, MINYEAR, MAXYEAR)
        require_in_range("month", self.month, 1, 12)

    @property
    def last_day(self) -> date:
        """The calendar last day of this month (e.g. 2024-02 -> 2024-02-29)."""
        _, last = calendar.monthrange(self.year, self.month)
        return date(self.year, self.month, last)


@dataclass(frozen=True, slots=True)
class DeliverySchedule:
    """An ordered, non-empty run of delivery periods.

    Consistency invariant: periods are strictly increasing by ``(year, month)``,
    so there are no duplicate or overlapping months. The schedule validates this
    for itself at construction rather than trusting callers (Tell-Don't-Ask).
    """

    periods: tuple[DeliveryPeriod, ...]  # immutable, ordered

    def __post_init__(self) -> None:
        require_non_empty("periods", self.periods)
        for index, (prev, curr) in enumerate(zip(self.periods, self.periods[1:], strict=False)):
            if prev >= curr:
                raise ValidationError(
                    "periods must be strictly increasing by (year, month) with no "
                    f"duplicates or overlaps; offending pair at index {index}: "
                    f"{prev!r} is not before {curr!r}"
                )
