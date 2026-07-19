"""Day-count conventions."""

from __future__ import annotations

from datetime import date


def actual_365(start: date, end: date) -> float:
    """Fractional years between ``start`` and ``end`` under the actual/365 convention.

    Computed as the *actual* number of calendar days elapsed (so leap days such
    as 29 Feb are counted) divided by a fixed 365.0.

    The result is **signed**: when ``end`` precedes ``start`` the day difference is
    negative and the returned fraction is negative. Coincident dates yield ``0.0``.
    """
    return (end - start).days / 365.0


def actual_360(start: date, end: date) -> float:
    """Fractional years between ``start`` and ``end`` under the actual/360 convention.

    Computed as the *actual* number of calendar days elapsed (so leap days such
    as 29 Feb are counted) divided by a fixed 360.0 — the money-market convention
    used for some gas/power short-tenor instruments.

    The result is **signed**: when ``end`` precedes ``start`` the day difference is
    negative and the returned fraction is negative. Coincident dates yield ``0.0``.
    """
    return (end - start).days / 360.0
