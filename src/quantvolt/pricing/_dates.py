"""Pricing-internal settlement-date helpers (shared by futures/swap/tolling/transport).

Four pricers (:mod:`~quantvolt.pricing.futures`, :mod:`~quantvolt.pricing.swap`,
:mod:`~quantvolt.pricing.tolling`, :mod:`~quantvolt.pricing.transmission_right`) each
gather a discount-factor lookup date via the identical convention: a delivery
period's ``last_day`` plus ``settlement_lag_days`` calendar days. This module is the
one place that convention is written (coding-style.md §4, Duplicate Code); it is
**not** part of the public API (no re-export from ``pricing/__init__.py``).

``settlement_lag_days`` shifts ONLY the discount-factor lookup date computed here —
never an option's ``time_to_expiry`` / volatility horizon, a convention each caller
module's own docstring restates.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..exceptions import MissingTenorError
from ..models.discount_curve import DiscountCurve
from ..models.schedule import DeliveryPeriod


def settlement_date(period: DeliveryPeriod, settlement_lag_days: int) -> date:
    """The period's last day plus ``settlement_lag_days`` calendar days (default 0)."""
    return period.last_day + timedelta(days=settlement_lag_days)


def gather_discount_factors(
    periods: tuple[DeliveryPeriod, ...],
    discount_curve: DiscountCurve,
    settlement_lag_days: int,
    *,
    not_covered_message: str,
) -> list[float]:
    """Discount factor at each period's settlement date, in ``periods`` order.

    Raises :class:`~quantvolt.exceptions.MissingTenorError` — prefixed with
    ``not_covered_message`` — naming EVERY period whose settlement date falls outside
    ``discount_curve``'s tenor range, rather than extrapolating or stopping at the
    first gap.
    """
    factors: list[float] = []
    missing: list[str] = []
    for period in periods:
        settlement = settlement_date(period, settlement_lag_days)
        try:
            factors.append(discount_curve.discount_factor(settlement))
        except MissingTenorError:
            missing.append(f"{period!r} (settlement {settlement.isoformat()})")
    if missing:
        raise MissingTenorError(f"{not_covered_message}; missing: {', '.join(missing)}")
    return factors
