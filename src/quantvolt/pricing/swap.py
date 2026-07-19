"""Fixed-for-floating swap pricing.

Conventions
-----------
- **Cash flows** are from the **payer-of-fixed / receiver-of-floating** perspective:
  per delivery period ``i`` the undiscounted cash flow is
  ``(F_i - fixed_rate) * notional``, where ``F_i`` is the forward price for the
  period. NPV is positive when floating forwards exceed the fixed rate.
- **Settlement** for a period is its last calendar day (``DeliveryPeriod.last_day``);
  ``pv_i = df_i * cashflow_i`` with ``df_i`` the discount factor at settlement.
- **delta** is exact (NPV is linear in each forward price):
  ``delta[i] = dNPV/dF_i = df_i * notional``, in schedule order.
- **rho** is the NPV change per **+1 basis point parallel shift of the
  continuously compounded zero rate** underlying the discount curve. With
  ``df_i = exp(-r_i * t_i)`` a parallel shift ``dr`` gives ``d(df_i) = -t_i * df_i * dr``,
  so ``rho = sum_i (-t_i) * pv_i * 0.0001`` where ``t_i`` is the actual/365 year
  fraction from ``discount_curve.reference_date`` to settlement.

The pricer stays thin (validate -> vectorised kernel -> package): float prices and
discount factors are gathered once at the boundary, and the cash-flow arithmetic is
pure NumPy so a 120-period swap prices well inside the 500 ms budget.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from .._validation import require_non_empty, require_non_negative, require_positive
from ..exceptions import MissingTenorError, ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.instruments import SwapContract
from ..models.schedule import DeliveryPeriod
from ..numerics.daycount import actual_365
from ._dates import gather_discount_factors
from ._dates import settlement_date as _settlement_date

_BASIS_POINT = 1e-4


@dataclass(frozen=True, slots=True)
class SwapPricingResult:
    npv: float
    delta: tuple[float, ...]  # per delivery period
    rho: float


def _require_no_overlapping_periods(periods: tuple[DeliveryPeriod, ...]) -> None:
    """Sort-and-scan overlap guard, reporting *each* offending pair.

    A valid :class:`~quantvolt.models.schedule.DeliverySchedule` already enforces
    strictly-increasing periods at construction, so overlapping periods cannot reach
    ``price_swap`` through a valid schedule; this check is retained as a defensive
    boundary guard. Delivery periods are whole calendar months, so two periods
    overlap exactly when they share the same ``(year, month)`` — the scan over the
    sorted copy therefore also covers duplicate months.
    """
    ordered = sorted(periods)  # sorted() returns a new list; the input is never mutated
    offending = [(prev, curr) for prev, curr in pairwise(ordered) if prev >= curr]
    if offending:
        described = "; ".join(f"{a!r} overlaps {b!r}" for a, b in offending)
        raise ValidationError(
            "swap.schedule.periods must contain no overlapping or duplicate "
            f"delivery periods; offending pair(s): {described}"
        )


def _forward_prices(
    periods: tuple[DeliveryPeriod, ...], forward_curve: ForwardCurve
) -> npt.NDArray[np.float64]:
    """Gather the floating forward price per period, in schedule order.

    Raises :class:`MissingTenorError` naming *every* delivery period the forward
    curve does not cover, rather than extrapolating silently.
    """
    prices: list[float] = []
    missing: list[DeliveryPeriod] = []
    for period in periods:
        try:
            prices.append(forward_curve.price_at(period))
        except MissingTenorError:
            missing.append(period)
    if missing:
        raise MissingTenorError(
            "forward_curve must cover every delivery period in swap.schedule; "
            f"missing period(s): {', '.join(repr(p) for p in missing)}"
        )
    return np.asarray(prices, dtype=np.float64)


def _discount_factors(
    periods: tuple[DeliveryPeriod, ...],
    discount_curve: DiscountCurve,
    settlement_lag_days: int,
) -> npt.NDArray[np.float64]:
    """Gather the discount factor at each period's settlement date.

    Settlement is the period's last calendar day plus ``settlement_lag_days``. Raises
    :class:`MissingTenorError` naming *every* period whose settlement date falls
    outside the discount curve's tenor range, rather than extrapolating silently.
    """
    factors = gather_discount_factors(
        periods,
        discount_curve,
        settlement_lag_days,
        not_covered_message="discount_curve must cover every settlement date in swap.schedule",
    )
    return np.asarray(factors, dtype=np.float64)


def price_swap(
    swap: SwapContract,
    forward_curve: ForwardCurve,
    discount_curve: DiscountCurve,
    *,
    day_count: Callable[[date, date], float] = actual_365,
    settlement_lag_days: int = 0,
    rate_bump: float = _BASIS_POINT,
) -> SwapPricingResult:
    """Price a fixed-for-floating swap: NPV, per-period delta, and rho.

    See the module docstring for the cash-flow (payer-of-fixed / receiver-of-floating)
    and rho (per-bp parallel shift of the continuously compounded zero rate) conventions.

    Args:
        swap: The swap contract to price.
        forward_curve: Must cover every delivery period in ``swap.schedule``.
        discount_curve: Must cover every period's settlement date.
        day_count: Year-fraction convention used for the rho computation, taking
            ``(start, end)`` and returning the fraction of a year (default
            :func:`~quantvolt.numerics.daycount.actual_365`).
        settlement_lag_days: Calendar days added to each period's last day to get
            the settlement date used for both the discount-factor lookup and the
            rho year fraction (default 0, non-negative).
        rate_bump: The per-basis-point size used to scale rho — the NPV change
            per this parallel shift of the continuously compounded zero rate
            (default ``1e-4``, i.e. one basis point).

    Validation is eager and ordered, before any computation:

    1. ``swap.schedule.periods`` is non-empty;
    2. sort-and-scan overlap/duplicate detection, raising :class:`ValidationError`
       identifying each offending pair (defensive — see
       :func:`_require_no_overlapping_periods`);
    3. coverage: every delivery period on the forward curve, then every settlement
       date within the discount curve's tenor range, raising
       :class:`MissingTenorError` identifying the missing period(s).

    Inputs are never mutated; identical inputs produce identical results.

    Raises:
        ValidationError: If ``settlement_lag_days`` is negative or ``rate_bump``
            is not > 0, in addition to the schedule/coverage errors above.
    """
    require_non_negative("settlement_lag_days", settlement_lag_days)
    require_positive("rate_bump", rate_bump)
    periods = swap.schedule.periods
    require_non_empty("swap.schedule.periods", periods)
    _require_no_overlapping_periods(periods)
    floats = _forward_prices(periods, forward_curve)
    factors = _discount_factors(periods, discount_curve, settlement_lag_days)

    present_values = factors * (floats - swap.fixed_rate) * swap.notional
    npv = float(np.sum(present_values))

    delta = tuple(float(d) for d in factors * swap.notional)

    year_fractions = np.asarray(
        [
            day_count(discount_curve.reference_date, _settlement_date(period, settlement_lag_days))
            for period in periods
        ],
        dtype=np.float64,
    )
    rho = float(np.sum(-year_fractions * present_values) * rate_bump)

    return SwapPricingResult(npv=npv, delta=delta, rho=rho)
