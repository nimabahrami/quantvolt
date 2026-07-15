"""Spread analysis — spark/dark/clean/basis/crack/forward/implied-heat-rate (Tasks 32-34).

Intercommodity spread analytics over discrete forward curves (design §2.4, Req 2).
Every function computes over the **intersection** of the delivery periods of its
input curves; an empty intersection raises
:class:`~quantvolt.exceptions.InsufficientDataError` naming both commodities (and
the requested range where one applies) rather than computing partial results
silently (Req 2.4, 2.5).

Conventions fixed by this module (result objects are co-located per ``structure.md``):

- :class:`SpreadResult` carries its ``spread_type`` (``"spark"`` or ``"dark"``)
  alongside the per-period values, so spark and dark margins are always *separate*
  immutable objects — computing one can never touch the other (Req 2.1, Property 6).
- :func:`clean_spread` reads Req 2.2 as follows: the function cleans the ONE spread
  it is given and labels the result with that spread's type. "Compute both the
  Clean_Spark_Spread and the Clean_Dark_Spread" is satisfied by calling it twice —
  once with a spark :class:`SpreadResult` and once with a dark one — each deducting
  ``emissions_intensity * EUA_price`` from its corresponding uncleaned spread.
- :func:`crack_spread` uses the market ``input:outputs`` ratio convention: with
  ``ratio=(3, 2, 1)`` (3:2:1), 3 units of crude yield 2 units of the first product
  and 1 unit of the second, and the spread is normalised per unit of crude.
- :func:`basis` reports the population standard deviation by default (``ddof=0``);
  percentiles default to the 5th/95th and use :func:`numpy.percentile` with its
  default (linear) interpolation.
- :func:`forward_spread` is the forward spark spread: the formula is identical to
  :func:`spark_spread`, differing only in time-horizon interpretation (Property 43).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np

from .._validation import (
    require_in_range,
    require_non_empty,
    require_non_negative,
    require_positive,
)
from ..exceptions import InsufficientDataError, ValidationError
from ..models.curve import ForwardCurve
from ..models.schedule import DeliveryPeriod

SpreadType = Literal["spark", "dark"]


@dataclass(frozen=True, slots=True)
class SpreadResult:
    """A generation-margin spread per delivery period, labelled by its type.

    ``spread_type`` records whether the values are spark (gas-fired) or dark
    (coal-fired) margins; the label is what lets :func:`clean_spread` name its
    output and what keeps spark and dark results distinct objects (Property 6).
    ``per_period`` preserves chronological key order.
    """

    spread_type: SpreadType
    per_period: dict[DeliveryPeriod, float]


@dataclass(frozen=True, slots=True)
class CleanSpreadResult:
    """A carbon-cleaned spread: base ``spread_type``, cleaned values, carbon cost.

    ``per_period`` holds the cleaned spread (uncleaned - carbon cost) and
    ``carbon_cost`` the deducted ``emissions_intensity * EUA_price`` per period,
    so callers can reconstruct the uncleaned spread (Property 7).
    """

    spread_type: SpreadType
    per_period: dict[DeliveryPeriod, float]
    carbon_cost: dict[DeliveryPeriod, float]


@dataclass(frozen=True, slots=True)
class ImpliedHeatRateResult:
    """Implied heat rate (power/gas) per shared period plus anomaly flags.

    ``anomalous`` lists, in chronological order, the periods whose implied heat
    rate falls strictly outside the caller-supplied ``anomaly_range``; it is empty
    when no range was supplied (Req 2.3).
    """

    per_period: dict[DeliveryPeriod, float]
    anomalous: tuple[DeliveryPeriod, ...]


@dataclass(frozen=True, slots=True)
class BasisResult:
    """Per-period locational basis (A - B) with summary statistics (Req 2.4).

    ``std`` is the standard deviation (population by default, ``ddof=0``);
    ``p5``/``p95`` are the ``lower_percentile``/``upper_percentile`` (5th/95th by
    default) via :func:`numpy.percentile` (linear interpolation). See :func:`basis`.
    """

    per_period: dict[DeliveryPeriod, float]
    mean: float
    std: float
    p5: float
    p95: float


@dataclass(frozen=True, slots=True)
class CrackSpreadResult:
    """Refining margin per delivery period, normalised per unit of crude.

    ``ratio`` echoes the crack convention used, e.g. ``(3, 2, 1)`` — crude units
    first, then one output entry per product curve in insertion order.
    """

    per_period: dict[DeliveryPeriod, float]
    ratio: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CalendarSpreadResult:
    """Storage-related calendar spread between two delivery periods (Property 44).

    ``price_difference`` is the raw later-minus-earlier price difference;
    ``storage_cost_total`` is ``storage_cost`` (per month) times the number of
    months between the two periods; ``spread`` is the storage-adjusted value
    (``price_difference - storage_cost_total``). A positive ``spread`` indicates
    contango net of carry (profitable storage injection); negative indicates
    backwardation.
    """

    period_early: DeliveryPeriod
    period_late: DeliveryPeriod
    price_difference: float
    storage_cost_total: float
    spread: float


def _prices_by_period(curve: ForwardCurve) -> dict[DeliveryPeriod, float]:
    """One-shot lookup table for a curve's node prices (avoids per-period scans)."""
    return {node.period: node.price for node in curve.nodes}


def _shared_periods(
    name_a: str,
    curve_a: ForwardCurve,
    name_b: str,
    curve_b: ForwardCurve,
    within: tuple[date, date] | None = None,
) -> tuple[DeliveryPeriod, ...]:
    """Chronologically ordered intersection of two curves' delivery periods.

    When ``within=(start, end)`` is given, only shared periods whose
    :attr:`~quantvolt.models.schedule.DeliveryPeriod.last_day` falls inside the
    inclusive ``[start, end]`` range survive. An empty result raises
    :class:`InsufficientDataError` naming both parameters, both commodities, each
    curve's covered span, and the requested range (Req 2.4, 2.5).
    """
    periods_b = {node.period for node in curve_b.nodes}
    shared = [node.period for node in curve_a.nodes if node.period in periods_b]
    if within is not None:
        start, end = within
        shared = [period for period in shared if start <= period.last_day <= end]
    if shared:
        return tuple(shared)
    range_clause = (
        ""
        if within is None
        else f" with last day in [{within[0].isoformat()}, {within[1].isoformat()}]"
    )
    raise InsufficientDataError(
        f"{name_a} (commodity {curve_a.commodity.commodity_id!r}) and {name_b} "
        f"(commodity {curve_b.commodity.commodity_id!r}) share no delivery periods"
        f"{range_clause}; {name_a} covers [{curve_a.nodes[0].period!r}, "
        f"{curve_a.nodes[-1].period!r}] and {name_b} covers "
        f"[{curve_b.nodes[0].period!r}, {curve_b.nodes[-1].period!r}]"
    )


def _generation_spread(
    power_curve: ForwardCurve,
    fuel_curve: ForwardCurve,
    heat_rate: float,
    variable_cost: float,
    emissions_cost: float,
    spread_type: SpreadType,
) -> SpreadResult:
    """Shared spark/dark kernel: validate eagerly, then apply Req 2.1 per period."""
    require_positive("heat_rate", heat_rate)
    require_non_negative("variable_cost", variable_cost)
    require_non_negative("emissions_cost", emissions_cost)
    shared = _shared_periods("power_curve", power_curve, "fuel_curve", fuel_curve)
    power_prices = _prices_by_period(power_curve)
    fuel_prices = _prices_by_period(fuel_curve)
    per_period = {
        period: power_prices[period]
        - heat_rate * fuel_prices[period]
        - variable_cost
        - emissions_cost
        for period in shared
    }
    return SpreadResult(spread_type=spread_type, per_period=per_period)


def spark_spread(
    power_curve: ForwardCurve,
    fuel_curve: ForwardCurve,
    heat_rate: float,
    variable_cost: float,
    emissions_cost: float,
) -> SpreadResult:
    """Spark spread (gas-fired generation margin) per shared delivery period.

    For each period in the intersection of ``power_curve`` and ``fuel_curve``:
    ``power_price - heat_rate * fuel_price - variable_cost - emissions_cost``
    (Req 2.1, Property 6). Computing a spark spread never reads or writes any dark
    values: each call returns a new immutable :class:`SpreadResult` labelled
    ``"spark"``, so any existing dark result remains untouched.

    Raises :class:`~quantvolt.exceptions.ValidationError` unless ``heat_rate > 0``,
    ``variable_cost >= 0`` and ``emissions_cost >= 0``, and
    :class:`InsufficientDataError` when the curves share no delivery periods.
    """
    return _generation_spread(
        power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost, "spark"
    )


def dark_spread(
    power_curve: ForwardCurve,
    fuel_curve: ForwardCurve,
    heat_rate: float,
    variable_cost: float,
    emissions_cost: float,
) -> SpreadResult:
    """Dark spread (coal-fired generation margin) per shared delivery period.

    Same formula and validation as :func:`spark_spread` with a coal ``fuel_curve``;
    the result is labelled ``"dark"``. It is a separate immutable object, so
    computing it never modifies any spark values (Req 2.1, Property 6).
    """
    return _generation_spread(
        power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost, "dark"
    )


def clean_spread(
    spread: SpreadResult, eua_curve: ForwardCurve, emissions_intensity: float
) -> CleanSpreadResult:
    """Deduct the carbon cost from an uncleaned spark or dark spread (Req 2.2).

    Decorator intent as a plain function: wraps one :class:`SpreadResult` and adds
    the carbon cost, per period: ``cleaned = spread - emissions_intensity *
    EUA_price``. The result keeps the input's ``spread_type``, so cleaning a spark
    spread yields the clean spark spread and cleaning a dark spread the clean dark
    spread — call once per uncleaned spread to obtain both (Property 7).

    Raises :class:`~quantvolt.exceptions.ValidationError` unless
    ``emissions_intensity >= 0``, and :class:`InsufficientDataError` when
    ``eua_curve`` lacks any of the spread's delivery periods (Req 2.5) — no
    partial result is returned.
    """
    require_non_negative("emissions_intensity", emissions_intensity)
    eua_prices = _prices_by_period(eua_curve)
    missing = tuple(period for period in spread.per_period if period not in eua_prices)
    if missing:
        raise InsufficientDataError(
            f"eua_curve (commodity {eua_curve.commodity.commodity_id!r}) is missing "
            f"delivery periods required by the {spread.spread_type} spread: "
            + ", ".join(repr(period) for period in missing)
        )
    carbon_cost = {period: emissions_intensity * eua_prices[period] for period in spread.per_period}
    per_period = {
        period: value - carbon_cost[period] for period, value in spread.per_period.items()
    }
    return CleanSpreadResult(
        spread_type=spread.spread_type, per_period=per_period, carbon_cost=carbon_cost
    )


def implied_heat_rate(
    power_curve: ForwardCurve,
    gas_curve: ForwardCurve,
    anomaly_range: tuple[float, float] | None = None,
) -> ImpliedHeatRateResult:
    """Implied heat rate ``power_price / gas_price`` per shared period (Req 2.3).

    Validation is eager and complete before any computation: every shared period's
    gas price must be strictly positive; the first violation raises
    :class:`~quantvolt.exceptions.ValidationError` identifying that delivery period
    and no heat rate is computed (Property 8). When ``anomaly_range=(lo, hi)`` is
    supplied (requiring ``lo < hi``), periods whose implied heat rate falls
    *strictly outside* the inclusive ``[lo, hi]`` band are flagged in
    ``anomalous``; without a range no period is flagged.
    """
    if anomaly_range is not None:
        lo, hi = anomaly_range
        if not lo < hi:
            raise ValidationError(f"anomaly_range must satisfy lower < upper, got ({lo!r}, {hi!r})")
    shared = _shared_periods("power_curve", power_curve, "gas_curve", gas_curve)
    power_prices = _prices_by_period(power_curve)
    gas_prices = _prices_by_period(gas_curve)
    for period in shared:
        if gas_prices[period] <= 0:
            raise ValidationError(
                "gas_curve price must be > 0 for every shared delivery period; "
                f"got {gas_prices[period]!r} for period {period!r}"
            )
    per_period = {period: power_prices[period] / gas_prices[period] for period in shared}
    if anomaly_range is None:
        anomalous: tuple[DeliveryPeriod, ...] = ()
    else:
        lo, hi = anomaly_range
        anomalous = tuple(period for period in shared if not lo <= per_period[period] <= hi)
    return ImpliedHeatRateResult(per_period=per_period, anomalous=anomalous)


def basis(
    curve_a: ForwardCurve,
    curve_b: ForwardCurve,
    start: date,
    end: date,
    *,
    lower_percentile: float = 5.0,
    upper_percentile: float = 95.0,
    ddof: int = 0,
) -> BasisResult:
    """Locational basis ``price(A) - price(B)`` per period in ``[start, end]`` (Req 2.4).

    The computation covers the shared delivery periods whose last calendar day
    falls within the inclusive ``[start, end]`` range; no such period raises
    :class:`InsufficientDataError` naming both commodities and the range rather
    than returning empty statistics (Property 9). Summary statistics: mean,
    standard deviation (``ddof=0`` by default — the periods are the whole
    population of interest, not a sample), and the ``lower_percentile``/
    ``upper_percentile`` (default 5th/95th) via :func:`numpy.percentile`
    (linear interpolation).

    Args:
        curve_a: First curve of the basis (``A`` in ``A - B``).
        curve_b: Second curve of the basis.
        start: Inclusive lower bound on each period's last calendar day.
        end: Inclusive upper bound; must be ``>= start``.
        lower_percentile: Percentile reported as ``p5``, in ``[0, 100]``
            (default 5.0) and strictly below ``upper_percentile``.
        upper_percentile: Percentile reported as ``p95``, in ``[0, 100]``
            (default 95.0).
        ddof: Delta degrees of freedom for :func:`numpy.std`, non-negative
            (default 0, population standard deviation).
    """
    if start > end:
        raise ValidationError(
            f"start must be <= end, got start={start.isoformat()}, end={end.isoformat()}"
        )
    require_in_range("lower_percentile", lower_percentile, 0.0, 100.0)
    require_in_range("upper_percentile", upper_percentile, 0.0, 100.0)
    if not lower_percentile < upper_percentile:
        raise ValidationError(
            "lower_percentile must be < upper_percentile, got "
            f"lower_percentile={lower_percentile!r}, upper_percentile={upper_percentile!r}"
        )
    if ddof < 0:
        raise ValidationError(f"ddof must be >= 0, got {ddof!r}")
    shared = _shared_periods("curve_a", curve_a, "curve_b", curve_b, within=(start, end))
    prices_a = _prices_by_period(curve_a)
    prices_b = _prices_by_period(curve_b)
    per_period = {period: prices_a[period] - prices_b[period] for period in shared}
    values = np.asarray(list(per_period.values()), dtype=np.float64)
    return BasisResult(
        per_period=per_period,
        mean=float(np.mean(values)),
        std=float(np.std(values, ddof=ddof)),
        p5=float(np.percentile(values, lower_percentile)),
        p95=float(np.percentile(values, upper_percentile)),
    )


def crack_spread(
    product_curves: dict[str, ForwardCurve],
    crude_curve: ForwardCurve,
    ratio: tuple[int, ...] = (3, 2, 1),
) -> CrackSpreadResult:
    """Refining margin per delivery period for an ``input:outputs`` crack ratio.

    Convention: ``ratio[0]`` is the number of crude (input) units and ``ratio[1:]``
    the product (output) units, matched to ``product_curves`` in insertion order —
    the default 3:2:1 means 3 crude → 2 of the first product + 1 of the second.
    Per period, over the shared delivery periods of *all* curves::

        spread = (Σᵢ product_priceᵢ * ratio[1 + i] - crude_price * ratio[0]) / ratio[0]

    i.e. the margin normalised per unit of crude. For the standard 3:2:1 and 5:3:2
    cracks the output units sum to the input units, so the product weights sum to 1
    (Property 42).

    Raises :class:`~quantvolt.exceptions.ValidationError` unless ``product_curves``
    is non-empty, ``len(ratio) == len(product_curves) + 1`` and every ratio entry
    is > 0; raises :class:`InsufficientDataError` when no delivery period is common
    to the crude curve and every product curve.
    """
    require_non_empty("product_curves", product_curves)
    expected_entries = len(product_curves) + 1
    if len(ratio) != expected_entries:
        raise ValidationError(
            f"ratio must have exactly len(product_curves) + 1 = {expected_entries} entries "
            f"(crude units first, then one entry per product curve), got {len(ratio)}"
        )
    for index, entry in enumerate(ratio):
        require_positive(f"ratio[{index}]", entry)
    crude_units = ratio[0]
    product_units = dict(zip(product_curves, ratio[1:], strict=True))
    crude_prices = _prices_by_period(crude_curve)
    product_prices = {name: _prices_by_period(curve) for name, curve in product_curves.items()}
    shared = tuple(
        node.period
        for node in crude_curve.nodes
        if all(node.period in prices for prices in product_prices.values())
    )
    if not shared:
        product_ids = ", ".join(
            f"{name!r} (commodity {curve.commodity.commodity_id!r})"
            for name, curve in product_curves.items()
        )
        raise InsufficientDataError(
            f"crude_curve (commodity {crude_curve.commodity.commodity_id!r}) and "
            f"product_curves {product_ids} share no delivery period common to all curves"
        )
    per_period = {
        period: (
            sum(product_units[name] * product_prices[name][period] for name in product_curves)
            - crude_units * crude_prices[period]
        )
        / crude_units
        for period in shared
    }
    return CrackSpreadResult(per_period=per_period, ratio=ratio)


def forward_spread(
    power_curve: ForwardCurve,
    fuel_curve: ForwardCurve,
    heat_rate: float,
    variable_cost: float,
    emissions_cost: float,
) -> SpreadResult:
    """Forward spark spread over the curve intersection, for forward price risk.

    The formula is identical to :func:`spark_spread` — forward power minus
    heat-rate-weighted forward fuel minus costs — differing only in time-horizon
    interpretation, so this delegates to it and returns the same ``"spark"``
    -labelled :class:`SpreadResult` (design §2.4, Property 43).
    """
    return spark_spread(power_curve, fuel_curve, heat_rate, variable_cost, emissions_cost)


def calendar_spread(
    curve: ForwardCurve,
    period_early: DeliveryPeriod,
    period_late: DeliveryPeriod,
    storage_cost: float = 0.0,
) -> CalendarSpreadResult:
    """Storage-related calendar spread on one curve (Task 34, Property 44).

    ``spread = price(period_late) - price(period_early) - storage_cost * months``
    where ``months`` is the whole-month distance between the two delivery periods
    and ``storage_cost`` is the cost of carry per month. This is the spread a
    storage operator captures by injecting in ``period_early`` and withdrawing in
    ``period_late``; positive means contango net of carry, negative means
    backwardation.

    Raises :class:`~quantvolt.exceptions.ValidationError` unless
    ``period_early < period_late`` and ``storage_cost >= 0``; a period absent from
    the curve raises :class:`~quantvolt.exceptions.MissingTenorError` (via
    :meth:`ForwardCurve.price_at`).
    """
    require_non_negative("storage_cost", storage_cost)
    if not period_early < period_late:
        raise ValidationError(
            "period_early must be strictly before period_late, got "
            f"period_early={period_early!r}, period_late={period_late!r}"
        )
    price_early = curve.price_at(period_early)
    price_late = curve.price_at(period_late)
    months = (period_late.year - period_early.year) * 12 + (period_late.month - period_early.month)
    price_difference = price_late - price_early
    storage_cost_total = storage_cost * months
    return CalendarSpreadResult(
        period_early=period_early,
        period_late=period_late,
        price_difference=price_difference,
        storage_cost_total=storage_cost_total,
        spread=price_difference - storage_cost_total,
    )
