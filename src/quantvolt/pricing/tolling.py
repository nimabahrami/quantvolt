"""Tolling-agreement valuation (Task 31; Req 8.1-8.5; Properties 19, 20).

A tolling agreement is the Composite intent: a strip of clean spark
(``fuel_type == "gas"``) or clean dark (``fuel_type == "coal"``) spread
options, one per delivery period, each priced independently through
:func:`quantvolt.pricing.spread_option.price_spread_option`, returned with
per-period AND aggregate values/deltas. ``fuel_type`` only labels the strip:
gas and coal tolling share the same mathematics, with the fuel curve
supplying the prices either way.

Conventions fixed by this module
--------------------------------
- **Unit chain**: ``heat_rate`` is MWh_fuel/MWh_power and
  ``emissions_intensity`` is tCO2/MWh_fuel. Per MWh of power, the fuel cost
  is ``heat_rate x fuel_price`` and the carbon cost is
  ``emissions_intensity x heat_rate x eua_price``
  ([tCO2/MWh_fuel] x [MWh_fuel/MWh_power] x [EUR/tCO2] = EUR/MWh_power).
- **Leg composition**: each period is a call on ``power - (heat_rate x fuel
  + emissions_intensity x heat_rate x eua) - variable_om_cost``, i.e.
  ``forward1`` = the power forward, ``forward2`` = the combined fuel+carbon
  leg, ``strike = variable_om_cost`` (EUR/MWh_power). A zero O&M cost thus
  prices through Margrabe, a positive one through Kirk (Property 18).
- **Notional**: the request carries no capacity/notional concept, so every
  period prices with notional 1.0 — a unit-capacity (1 MWh per period)
  tolling agreement. Callers scale results for real capacities.
- **Volatility**: the design supplies ONE volatility surface, so
  ``sigma_at(period)`` serves both legs (``sigma1 == sigma2``) — a
  documented simplification; scaling a lognormal forward by constants
  leaves its lognormal volatility unchanged, so the composite fuel+carbon
  leg reuses the same annualised vol.
- **Correlation**: ``correlation_matrix`` rows/columns follow the Req 8.1
  ordering ``[power, fuel, eua]``; the pricing rho for every period is the
  power-fuel entry ``correlation_matrix[0, 1]``.
- **Discounting**: the discount factor at each period's settlement
  (``DeliveryPeriod.last_day``, the swap-module convention) is passed INTO
  the :class:`~quantvolt.pricing.spread_option.SpreadOptionRequest`, so the
  kernel premium is already discounted and is used as the per-period value
  unchanged — it is never discounted a second time.
- **Time to expiry**: actual/365 from ``discount_curve.reference_date`` to
  ``period.last_day`` — the option's decision horizon (the plant either runs
  or does not over the delivery period). ``settlement_lag_days`` shifts ONLY
  the discount-factor lookup date (a payment-timing convention); it never
  enters the time-to-expiry / volatility horizon.
- **Intrinsic value** (Req 8.2): ``sum(max(0, forward_spread_i) x 1.0)``
  with ``forward_spread_i = power_i - heat_rate x fuel_i -
  emissions_intensity x heat_rate x eua_i - variable_om_cost`` — computed
  from current forwards with zero time value and, per the Req 8.2 formula,
  undiscounted. ``time_value = npv - intrinsic_value``.
- **Deltas** (Req 8.3): the per-period power delta is the spread option's
  ``delta1`` (df-consistent — the kernel premium is discounted). Fuel and
  EUA deltas are chain-rule scalings of ``delta2``:
  ``d(forward2)/d(fuel) = heat_rate`` and
  ``d(forward2)/d(eua) = emissions_intensity x heat_rate``. Aggregate
  deltas are the plain sums of the per-period tuples, so the aggregate
  equals the sum of the per-period values exactly (Property 20).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import numpy as np

from .._validation import require_correlation, require_non_negative, require_positive
from ..exceptions import InsufficientDataError, MissingTenorError, ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.instruments import PlantConfig
from ..models.schedule import DeliveryPeriod, DeliverySchedule
from ..models.vol_surface import VolatilitySurface
from ..numerics.daycount import actual_365
from ._dates import gather_discount_factors
from .spread_option import SpreadOptionRequest, price_spread_option

# Schedule bounds (Req 8.1).
_MAX_SCHEDULE_PERIODS = 1200
# Absolute tolerance for the symmetry / unit-diagonal checks of the correlation matrix.
_MATRIX_TOLERANCE = 1e-9
# The matrix must at least cover [power, fuel, eua] (Req 8.1).
_MIN_MATRIX_SIZE = 3
# Unit-capacity tolling: 1 MWh per delivery period (see module docstring).
_UNIT_NOTIONAL = 1.0
# correlation_matrix row/column convention: [power, fuel, eua] (Req 8.1 ordering).
_POWER_INDEX, _FUEL_INDEX = 0, 1


@dataclass(frozen=True, slots=True)
class TollingResult:
    """Strip-level tolling valuation: NPV decomposition plus per-period detail.

    ``per_period_values`` are the discounted per-period spread-option values in
    schedule order; ``npv`` is their sum. ``per_period_deltas`` and
    ``aggregate_deltas`` are keyed ``"power"``/``"fuel"``/``"eua"``, and each
    aggregate equals the sum of its per-period tuple exactly (Property 20).
    """

    npv: float
    intrinsic_value: float
    time_value: float
    per_period_values: tuple[float, ...]
    per_period_deltas: dict[str, tuple[float, ...]]
    aggregate_deltas: dict[str, float]


def _validate_schedule_length(periods: tuple[DeliveryPeriod, ...]) -> None:
    """A tolling schedule carries 1-1200 delivery periods (Req 8.1)."""
    if not 1 <= len(periods) <= _MAX_SCHEDULE_PERIODS:
        raise ValidationError(
            f"schedule must contain between 1 and {_MAX_SCHEDULE_PERIODS} delivery "
            f"periods (Req 8.1), got {len(periods)}"
        )


def _validate_correlation_matrix(matrix: np.ndarray, matrix_tolerance: float) -> None:
    """Req 8.1: at least 3x3 ``[power, fuel, eua]``, symmetric, unit diagonal.

    Off-diagonal entries must lie strictly inside ``(-1, 1)`` (Property 19);
    symmetry and the unit diagonal are enforced within ``matrix_tolerance``.
    """
    if not isinstance(matrix, np.ndarray):
        raise ValidationError(
            f"correlation_matrix must be a numpy ndarray, got {type(matrix).__name__}"
        )
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValidationError(
            f"correlation_matrix must be a square 2-D matrix, got shape {matrix.shape}"
        )
    size = matrix.shape[0]
    if size < _MIN_MATRIX_SIZE:
        raise ValidationError(
            f"correlation_matrix must be at least {_MIN_MATRIX_SIZE}x{_MIN_MATRIX_SIZE} "
            f"covering [power, fuel, eua] (Req 8.1), got shape {matrix.shape}"
        )
    for i in range(size):
        diagonal = float(matrix[i, i])
        if abs(diagonal - 1.0) > matrix_tolerance:
            raise ValidationError(
                f"correlation_matrix must have a unit diagonal (within {matrix_tolerance}); "
                f"got correlation_matrix[{i}, {i}] = {diagonal!r}"
            )
        for j in range(i + 1, size):
            upper, lower = float(matrix[i, j]), float(matrix[j, i])
            if abs(upper - lower) > matrix_tolerance:
                raise ValidationError(
                    f"correlation_matrix must be symmetric (within {matrix_tolerance}); "
                    f"correlation_matrix[{i}, {j}] = {upper!r} != "
                    f"correlation_matrix[{j}, {i}] = {lower!r}"
                )
            require_correlation(f"correlation_matrix[{i}, {j}]", upper)


def _schedule_prices(
    curves: tuple[tuple[str, ForwardCurve], ...],
    periods: tuple[DeliveryPeriod, ...],
) -> tuple[tuple[float, ...], ...]:
    """Gather each curve's price per schedule period, in curve then schedule order.

    Coverage is validated for ALL curves before returning: every curve missing
    any schedule period is reported — commodity and missing periods — in one
    :class:`InsufficientDataError`, rather than pricing a covered portion
    silently (Req 8.4).
    """
    gathered: list[tuple[float, ...]] = []
    shortfalls: list[str] = []
    for role, curve in curves:
        node_prices = {node.period: node.price for node in curve.nodes}
        missing = [period for period in periods if period not in node_prices]
        if missing:
            shortfalls.append(
                f"{role} (commodity {curve.commodity.commodity_id!r}) is missing "
                + ", ".join(repr(period) for period in missing)
            )
            continue
        gathered.append(tuple(node_prices[period] for period in periods))
    if shortfalls:
        raise InsufficientDataError(
            "every forward curve must cover the full delivery schedule (Req 8.4); "
            + "; ".join(shortfalls)
        )
    return tuple(gathered)


def _schedule_sigmas(
    vol_surface: VolatilitySurface, periods: tuple[DeliveryPeriod, ...]
) -> tuple[float, ...]:
    """Gather the implied vol per schedule period, never extrapolating (Req 8.5).

    Raises :class:`InsufficientDataError` naming the surface's commodity and
    EVERY missing tenor when the surface does not cover the whole schedule.
    """
    sigmas: list[float] = []
    missing: list[DeliveryPeriod] = []
    for period in periods:
        try:
            sigmas.append(vol_surface.sigma_at(period))
        except MissingTenorError:
            missing.append(period)
    if missing:
        raise InsufficientDataError(
            f"vol_surface (commodity {vol_surface.commodity.commodity_id!r}) must cover "
            "every delivery period in schedule (Req 8.5); missing tenor(s): "
            + ", ".join(repr(period) for period in missing)
        )
    return tuple(sigmas)


def _schedule_discount_factors(
    discount_curve: DiscountCurve,
    periods: tuple[DeliveryPeriod, ...],
    settlement_lag_days: int,
) -> tuple[float, ...]:
    """Gather the discount factor at each period's settlement (``last_day`` + lag).

    Raises :class:`MissingTenorError` naming every period whose settlement date
    falls outside the discount curve's tenor range (the swap-module convention).
    """
    return tuple(
        gather_discount_factors(
            periods,
            discount_curve,
            settlement_lag_days,
            not_covered_message=(
                "discount_curve must cover every delivery-period settlement date in schedule"
            ),
        )
    )


def price_tolling_agreement(
    plant: PlantConfig,
    power_curve: ForwardCurve,
    fuel_curve: ForwardCurve,
    eua_curve: ForwardCurve,
    vol_surface: VolatilitySurface,
    correlation_matrix: np.ndarray,
    schedule: DeliverySchedule,
    discount_curve: DiscountCurve,
    *,
    capacity: float = _UNIT_NOTIONAL,
    fuel_sigma: VolatilitySurface | None = None,
    matrix_tolerance: float = _MATRIX_TOLERANCE,
    day_count: Callable[[date, date], float] = actual_365,
    settlement_lag_days: int = 0,
) -> TollingResult:
    """Value a tolling agreement as a strip of clean spread options (Req 8.1-8.5).

    One clean spark (gas) / clean dark (coal) spread option per delivery
    period — see the module docstring for the leg composition, unit chain,
    single-surface volatility, correlation-indexing and discounting
    conventions. Validation is eager and complete before any pricing:
    schedule length, correlation matrix, full forward-curve / vol-surface /
    discount-curve coverage of the schedule.

    Args:
        plant: Heat rate, variable O&M cost, emissions intensity, fuel type.
        power_curve: Power forwards; must cover every schedule period.
        fuel_curve: Gas or coal forwards; must cover every schedule period.
        eua_curve: EUA forwards; must cover every schedule period.
        vol_surface: Surface used for the power leg of every period (and the
            fuel+carbon leg too, when ``fuel_sigma`` is ``None``).
        correlation_matrix: At least 3x3, ordered ``[power, fuel, eua]``.
        schedule: 1-1200 delivery periods.
        discount_curve: Must cover every period's settlement date.
        capacity: Per-period notional in MWh, positive (default 1.0 —
            unit-capacity; the historical behaviour). Scales every per-period
            spread-option notional and the intrinsic-value payoff.
        fuel_sigma: Optional separate volatility surface for the fuel+carbon
            leg; must cover every schedule period. ``None`` (default) reuses
            ``vol_surface`` for both legs, exactly as before.
        matrix_tolerance: Absolute tolerance for the correlation matrix's
            symmetry / unit-diagonal checks (default ``1e-9``); must be > 0
            (a non-positive or NaN tolerance would silently disable or
            misreport those checks).
        day_count: Year-fraction convention for each period's time-to-expiry,
            taking ``(start, end)`` (default
            :func:`~quantvolt.numerics.daycount.actual_365`).
        settlement_lag_days: Calendar days added to each period's last day to
            get the settlement date used for the discount-factor lookup
            (default 0, non-negative). Does NOT affect the option's
            ``time_to_expiry``, which is always ``day_count`` from
            ``discount_curve.reference_date`` to ``period.last_day`` — the
            decision horizon, not the payment date.

    Returns:
        NPV, intrinsic/time value decomposition, per-period values, and
        per-period plus aggregate deltas for ``"power"``/``"fuel"``/``"eua"``
        (aggregate == sum of per-period exactly, Property 20).

    Raises:
        ValidationError: If the schedule has more than 1200 periods; if the
            correlation matrix is not a square ndarray of size >= 3x3,
            symmetric with unit diagonal (within ``matrix_tolerance``) and
            off-diagonals strictly inside (-1, 1) (Property 19); if
            ``capacity`` is not > 0, ``settlement_lag_days`` is negative, or
            ``matrix_tolerance`` is not > 0 (including ``NaN``); or
            if any per-period spread-option input violates
            :func:`price_spread_option`'s domain (e.g. a non-positive power or
            fuel+carbon leg forward).
        InsufficientDataError: If any forward curve misses any schedule period
            (naming the commodity and the missing periods, Req 8.4), or the
            vol surface (or ``fuel_sigma``) misses any tenor (naming them,
            Req 8.5).
        MissingTenorError: If the discount curve does not cover every
            period's settlement date.
    """
    require_positive("capacity", capacity)
    require_non_negative("settlement_lag_days", settlement_lag_days)
    require_positive("matrix_tolerance", matrix_tolerance)
    periods = schedule.periods
    _validate_schedule_length(periods)
    _validate_correlation_matrix(correlation_matrix, matrix_tolerance)
    power_prices, fuel_prices, eua_prices = _schedule_prices(
        (("power_curve", power_curve), ("fuel_curve", fuel_curve), ("eua_curve", eua_curve)),
        periods,
    )
    sigmas = _schedule_sigmas(vol_surface, periods)
    fuel_sigmas = sigmas if fuel_sigma is None else _schedule_sigmas(fuel_sigma, periods)
    factors = _schedule_discount_factors(discount_curve, periods, settlement_lag_days)

    rho = float(correlation_matrix[_POWER_INDEX, _FUEL_INDEX])
    strike = plant.variable_om_cost
    fuel_leg_weight = plant.heat_rate  # MWh_fuel / MWh_power
    eua_leg_weight = plant.emissions_intensity * plant.heat_rate  # tCO2 / MWh_power

    values: list[float] = []
    power_deltas: list[float] = []
    fuel_deltas: list[float] = []
    eua_deltas: list[float] = []
    intrinsic_value = 0.0
    for period, power, fuel, eua, sigma, fuel_carbon_sigma, factor in zip(
        periods, power_prices, fuel_prices, eua_prices, sigmas, fuel_sigmas, factors, strict=True
    ):
        fuel_carbon_leg = fuel_leg_weight * fuel + eua_leg_weight * eua
        option = price_spread_option(
            SpreadOptionRequest(
                forward1=power,
                forward2=fuel_carbon_leg,
                strike=strike,
                sigma1=sigma,
                sigma2=fuel_carbon_sigma,
                correlation=rho,
                # Decision horizon (Req 8.1): the option's time_to_expiry is to the
                # period's last delivery day, NOT the (possibly lagged) settlement
                # date used for discounting below (see module docstring).
                time_to_expiry=day_count(discount_curve.reference_date, period.last_day),
                discount_factor=factor,
                notional=capacity,
            )
        )
        values.append(option.premium)
        power_deltas.append(option.delta1)
        fuel_deltas.append(option.delta2 * fuel_leg_weight)
        eua_deltas.append(option.delta2 * eua_leg_weight)
        intrinsic_value += max(0.0, power - fuel_carbon_leg - strike) * capacity

    npv = sum(values)
    per_period_deltas = {
        "power": tuple(power_deltas),
        "fuel": tuple(fuel_deltas),
        "eua": tuple(eua_deltas),
    }
    return TollingResult(
        npv=npv,
        intrinsic_value=intrinsic_value,
        time_value=npv - intrinsic_value,
        per_period_values=tuple(values),
        per_period_deltas=per_period_deltas,
        aggregate_deltas={name: sum(deltas) for name, deltas in per_period_deltas.items()},
    )
