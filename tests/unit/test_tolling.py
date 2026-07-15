"""Unit tests for tolling-agreement valuation (Task 31; Req 8.1-8.5; Properties 19, 20)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pytest

from quantvolt.exceptions import InsufficientDataError, MissingTenorError, ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES, CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import PlantConfig
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.daycount import actual_360, actual_365
from quantvolt.pricing.spread_option import (
    SpreadOptionRequest,
    SpreadOptionResult,
    price_spread_option,
)
from quantvolt.pricing.tolling import TollingResult, price_tolling_agreement
from quantvolt.testing import assert_input_unchanged

MARKET_DATE = date(2026, 7, 1)
PERIODS = (DeliveryPeriod(2027, 1), DeliveryPeriod(2027, 2), DeliveryPeriod(2027, 3))
POWER_PRICES = (95.0, 96.0, 84.0)
GAS_PRICES = (30.0, 32.0, 28.0)
EUA_PRICES = (70.0, 72.0, 68.0)
SIGMAS = (0.40, 0.35, 0.30)

POWER = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
GAS = BUILT_IN_COMMODITIES["TTF"]
EUA = BUILT_IN_COMMODITIES["EUA"]
COAL = CommodityConfig("API2_COAL", "EUR/t", Hub("API2", "ICE_ENDEX", "EUR/t"))

# heat_rate 2.0 and emissions_intensity 0.2 give a fuel+carbon leg of
# 2*fuel + 0.4*eua per MWh_power; with variable O&M 3.0 the forward spreads are
# 95-88-3 = 4.0 (ITM), 96-92.8-3 = 0.2 (ATM-ish), 84-83.2-3 = -2.2 (OTM).
PLANT = PlantConfig(heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas")


def make_curve(
    commodity: CommodityConfig,
    prices: tuple[float, ...],
    periods: tuple[DeliveryPeriod, ...] = PERIODS,
) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=MARKET_DATE,
        nodes=tuple(
            CurveNode(period=period, price=price, status="observed")
            for period, price in zip(periods, prices, strict=True)
        ),
    )


def make_vol_surface(
    periods: tuple[DeliveryPeriod, ...] = PERIODS,
    sigmas: tuple[float, ...] = SIGMAS,
) -> VolatilitySurface:
    return VolatilitySurface(
        commodity=POWER,
        tenors=tuple(
            VolatilityTenor(period=period, sigma=sigma)
            for period, sigma in zip(periods, sigmas, strict=True)
        ),
    )


def make_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=MARKET_DATE,
        tenors=(date(2026, 12, 31), date(2027, 12, 31)),
        factors=(0.99, 0.95),
    )


def make_matrix() -> np.ndarray:
    return np.array(
        [
            [1.0, 0.6, 0.3],
            [0.6, 1.0, 0.4],
            [0.3, 0.4, 1.0],
        ]
    )


def default_inputs() -> dict[str, Any]:
    return {
        "plant": PLANT,
        "power_curve": make_curve(POWER, POWER_PRICES),
        "fuel_curve": make_curve(GAS, GAS_PRICES),
        "eua_curve": make_curve(EUA, EUA_PRICES),
        "vol_surface": make_vol_surface(),
        "correlation_matrix": make_matrix(),
        "schedule": DeliverySchedule(periods=PERIODS),
        "discount_curve": make_discount_curve(),
    }


def price_default(**overrides: Any) -> TollingResult:
    inputs = default_inputs()
    inputs.update(overrides)
    return price_tolling_agreement(**inputs)


def manual_spread_options() -> tuple[SpreadOptionResult, ...]:
    """Hand-compose each period's spread option exactly as the tolling conventions say.

    forward1 = power; forward2 = heat_rate*fuel + (emissions_intensity*heat_rate)*eua;
    strike = variable O&M; sigma1 = sigma2 = surface vol; rho = matrix[0, 1] (power-fuel);
    the settlement discount factor rides INSIDE the request, so the premium is discounted.
    """
    discount_curve = make_discount_curve()
    rho = float(make_matrix()[0, 1])
    eua_leg_weight = PLANT.emissions_intensity * PLANT.heat_rate
    options = []
    for period, power, gas, eua, sigma in zip(
        PERIODS, POWER_PRICES, GAS_PRICES, EUA_PRICES, SIGMAS, strict=True
    ):
        options.append(
            price_spread_option(
                SpreadOptionRequest(
                    forward1=power,
                    forward2=PLANT.heat_rate * gas + eua_leg_weight * eua,
                    strike=PLANT.variable_om_cost,
                    sigma1=sigma,
                    sigma2=sigma,
                    correlation=rho,
                    time_to_expiry=actual_365(discount_curve.reference_date, period.last_day),
                    discount_factor=discount_curve.discount_factor(period.last_day),
                    notional=1.0,
                )
            )
        )
    return tuple(options)


# --- NPV composition (Req 8.1) ---


def test_per_period_values_and_npv_compose_from_spread_options() -> None:
    result = price_default()
    expected = manual_spread_options()
    assert result.per_period_values == tuple(option.premium for option in expected)
    assert result.npv == sum(result.per_period_values)


# --- Intrinsic / time value decomposition (Req 8.2, Property 20) ---


def test_intrinsic_value_matches_hand_computation() -> None:
    result = price_default()
    # Spreads by hand: 4.0, 0.2, -2.2 -> intrinsic = (4.0 + 0.2) * notional 1.0.
    spreads = [
        power
        - PLANT.heat_rate * gas
        - PLANT.emissions_intensity * PLANT.heat_rate * eua
        - PLANT.variable_om_cost
        for power, gas, eua in zip(POWER_PRICES, GAS_PRICES, EUA_PRICES, strict=True)
    ]
    assert result.intrinsic_value == pytest.approx(sum(max(0.0, s) for s in spreads))
    assert result.intrinsic_value == pytest.approx(4.2)


def test_time_value_is_npv_minus_intrinsic_and_positive_for_atmish_strip() -> None:
    result = price_default()
    assert result.time_value == result.npv - result.intrinsic_value
    assert result.time_value > 0.0


# --- Deltas (Req 8.3, Property 20) ---


def test_aggregate_deltas_equal_sum_of_per_period_exactly() -> None:
    result = price_default()
    assert set(result.per_period_deltas) == {"power", "fuel", "eua"}
    assert set(result.aggregate_deltas) == {"power", "fuel", "eua"}
    for name, per_period in result.per_period_deltas.items():
        assert len(per_period) == len(PERIODS)
        assert result.aggregate_deltas[name] == sum(per_period)


def test_deltas_compose_from_spread_option_by_chain_rule() -> None:
    result = price_default()
    expected = manual_spread_options()
    assert result.per_period_deltas["power"] == tuple(option.delta1 for option in expected)
    for i, option in enumerate(expected):
        assert result.per_period_deltas["fuel"][i] == pytest.approx(
            option.delta2 * PLANT.heat_rate, rel=1e-12
        )
        assert result.per_period_deltas["eua"][i] == pytest.approx(
            option.delta2 * PLANT.emissions_intensity * PLANT.heat_rate, rel=1e-12
        )


def test_delta_signs_long_power_short_fuel_and_eua() -> None:
    result = price_default()
    assert all(delta > 0.0 for delta in result.per_period_deltas["power"])
    assert all(delta < 0.0 for delta in result.per_period_deltas["fuel"])
    assert all(delta < 0.0 for delta in result.per_period_deltas["eua"])


# --- Curve coverage (Req 8.4) ---


def test_missing_power_period_raises_naming_commodity_and_period() -> None:
    short_power = make_curve(POWER, POWER_PRICES[:2], PERIODS[:2])
    with pytest.raises(InsufficientDataError) as excinfo:
        price_default(power_curve=short_power)
    message = str(excinfo.value)
    assert "power_curve" in message
    assert "EEX_PHELIX_DE" in message
    assert repr(DeliveryPeriod(2027, 3)) in message
    assert repr(DeliveryPeriod(2027, 1)) not in message


def test_single_error_reports_every_undercovering_curve() -> None:
    with pytest.raises(InsufficientDataError) as excinfo:
        price_default(
            power_curve=make_curve(POWER, POWER_PRICES[:2], PERIODS[:2]),
            eua_curve=make_curve(EUA, EUA_PRICES[1:], PERIODS[1:]),
        )
    message = str(excinfo.value)
    assert "power_curve" in message and "EEX_PHELIX_DE" in message
    assert "eua_curve" in message and "'EUA'" in message
    assert repr(DeliveryPeriod(2027, 3)) in message  # missing from the power curve
    assert repr(DeliveryPeriod(2027, 1)) in message  # missing from the EUA curve


# --- Vol-surface coverage (Req 8.5) ---


def test_missing_vol_tenor_raises_naming_the_tenor() -> None:
    with pytest.raises(InsufficientDataError) as excinfo:
        price_default(vol_surface=make_vol_surface(PERIODS[:2], SIGMAS[:2]))
    message = str(excinfo.value)
    assert "vol_surface" in message
    assert repr(DeliveryPeriod(2027, 3)) in message
    assert repr(DeliveryPeriod(2027, 1)) not in message


# --- Discount coverage ---


def test_discount_curve_not_covering_settlement_raises_missing_tenor() -> None:
    short_curve = DiscountCurve(
        reference_date=MARKET_DATE,
        tenors=(date(2026, 12, 31), date(2027, 2, 28)),
        factors=(0.99, 0.98),
    )
    with pytest.raises(MissingTenorError, match="2027-03-31"):
        price_default(discount_curve=short_curve)


# --- Schedule bounds (Req 8.1) ---


def test_schedule_longer_than_1200_periods_rejected() -> None:
    periods = tuple(DeliveryPeriod(2027 + i // 12, 1 + i % 12) for i in range(1201))
    with pytest.raises(ValidationError, match="1200"):
        price_default(schedule=DeliverySchedule(periods=periods))


# --- Correlation-matrix validation (Req 8.1, Property 19) ---


def _asymmetric() -> np.ndarray:
    matrix = make_matrix()
    matrix[0, 1] = 0.2  # [1, 0] stays 0.6
    return matrix


def _non_unit_diagonal() -> np.ndarray:
    matrix = make_matrix()
    matrix[1, 1] = 0.9
    return matrix


def _boundary_correlation(value: float, i: int = 0, j: int = 1) -> np.ndarray:
    matrix = make_matrix()
    matrix[i, j] = matrix[j, i] = value
    return matrix


@pytest.mark.parametrize(
    "matrix",
    [
        _asymmetric(),
        _non_unit_diagonal(),
        _boundary_correlation(1.0),
        _boundary_correlation(-1.0),
        _boundary_correlation(1.5),
        _boundary_correlation(-1.0, i=1, j=2),  # bad entry outside the pricing rho
        np.eye(2),  # below the 3x3 minimum
        np.ones((3, 4)),  # not square
        np.array([1.0, 0.5, 0.5]),  # not 2-D
    ],
)
def test_invalid_correlation_matrix_rejected(matrix: np.ndarray) -> None:
    with pytest.raises(ValidationError, match="correlation_matrix"):
        price_default(correlation_matrix=matrix)


def test_matrix_larger_than_minimum_prices_identically() -> None:
    larger = np.eye(4)
    larger[:3, :3] = make_matrix()
    larger[0, 3] = larger[3, 0] = 0.1
    larger[1, 3] = larger[3, 1] = 0.2
    larger[2, 3] = larger[3, 2] = 0.15
    assert price_default(correlation_matrix=larger) == price_default()


# --- fuel_type only labels the strip (Req 8.1) ---


def test_coal_plant_with_identical_numbers_prices_identically() -> None:
    coal_plant = PlantConfig(
        heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="coal"
    )
    coal_result = price_default(plant=coal_plant, fuel_curve=make_curve(COAL, GAS_PRICES))
    assert coal_result == price_default()


# --- Immutability (coding-style section 7) ---


def test_inputs_are_not_mutated() -> None:
    assert_input_unchanged(price_tolling_agreement, **default_inputs())


# --- new keyword-only parameters -------------------------------------------------


def test_new_keyword_defaults_match_hardcoded_behaviour() -> None:
    baseline = price_default()
    explicit = price_default(
        capacity=1.0,
        fuel_sigma=None,
        matrix_tolerance=1e-9,
        day_count=actual_365,
        settlement_lag_days=0,
    )
    assert explicit == baseline


def test_capacity_scales_values_and_intrinsic_linearly() -> None:
    baseline = price_default()
    scaled = price_default(capacity=10.0)
    assert scaled.npv == pytest.approx(10.0 * baseline.npv)
    assert scaled.intrinsic_value == pytest.approx(10.0 * baseline.intrinsic_value)
    assert scaled.per_period_values == pytest.approx(
        tuple(10.0 * v for v in baseline.per_period_values)
    )


def test_capacity_non_positive_rejected() -> None:
    with pytest.raises(ValidationError, match="capacity"):
        price_default(capacity=0.0)


def test_fuel_sigma_none_reuses_vol_surface() -> None:
    explicit = price_default(fuel_sigma=make_vol_surface())
    baseline = price_default()
    assert explicit == baseline


def test_fuel_sigma_override_changes_result() -> None:
    baseline = price_default()
    different_fuel_vols = make_vol_surface(sigmas=(0.10, 0.10, 0.10))
    result = price_default(fuel_sigma=different_fuel_vols)
    assert result.npv != baseline.npv


def test_fuel_sigma_missing_tenor_raises() -> None:
    short_fuel_sigma = make_vol_surface(PERIODS[:2], SIGMAS[:2])
    with pytest.raises(InsufficientDataError):
        price_default(fuel_sigma=short_fuel_sigma)


def test_matrix_tolerance_widened_accepts_previously_rejected_matrix() -> None:
    # A unit-diagonal deviation of 1e-5 is rejected at the default 1e-9 tolerance...
    matrix = make_matrix()
    matrix[1, 1] = 1.0 + 1e-5
    with pytest.raises(ValidationError, match="correlation_matrix"):
        price_default(correlation_matrix=matrix)
    # ...but accepted once matrix_tolerance is widened past the deviation.
    result = price_default(correlation_matrix=matrix, matrix_tolerance=1e-4)
    assert isinstance(result, TollingResult)


@pytest.mark.parametrize("bad_tolerance", [0.0, -1e-9, float("nan")])
def test_matrix_tolerance_non_positive_or_nan_rejected(bad_tolerance: float) -> None:
    """matrix_tolerance must itself be validated (> 0): a non-positive value gave a
    misleading "matrix must have unit diagonal" message for a valid matrix, and NaN
    silently disabled the symmetry / unit-diagonal checks entirely (``abs(x) >
    nan`` is always False).
    """
    with pytest.raises(ValidationError, match="matrix_tolerance"):
        price_default(matrix_tolerance=bad_tolerance)


def test_day_count_override_changes_time_to_expiry_dependent_value() -> None:
    baseline = price_default()
    with_360 = price_default(day_count=actual_360)
    assert with_360.npv != baseline.npv
    # Intrinsic value has no time-value component, so it is unaffected.
    assert with_360.intrinsic_value == pytest.approx(baseline.intrinsic_value)


def test_settlement_lag_days_shifts_discount_lookup_only() -> None:
    """``settlement_lag_days`` only moves the discount-factor lookup date.

    On a non-flat curve, lagging the settlement date changes the discount factor
    (and hence the NPV) by exactly the ratio of the two factors -- confirming the
    lag enters ONLY through discounting, never through the option's
    ``time_to_expiry`` (regression for the T-inflation bug: previously the lagged
    date leaked into ``time_to_expiry`` too, inflating time value beyond this
    discounting-only ratio).
    """
    discount_curve = make_discount_curve()
    lag_days = 30
    baseline = price_default(discount_curve=discount_curve)
    lagged = price_default(discount_curve=discount_curve, settlement_lag_days=lag_days)
    assert lagged.npv != pytest.approx(baseline.npv)
    for period, base_value, lag_value in zip(
        PERIODS, baseline.per_period_values, lagged.per_period_values, strict=True
    ):
        base_factor = discount_curve.discount_factor(period.last_day)
        lag_factor = discount_curve.discount_factor(period.last_day + timedelta(days=lag_days))
        assert lag_value == pytest.approx(base_value * lag_factor / base_factor, rel=1e-9)


def test_settlement_lag_days_with_flat_curve_does_not_change_time_value() -> None:
    """Regression: on a FLAT discount curve, ``settlement_lag_days`` must leave
    every result bit-for-bit unchanged. The only economic channel for the lag is
    the discount factor, which is constant on a flat curve; if the lagged
    settlement date instead leaked into the option's ``time_to_expiry`` (the
    original bug), time value -- and hence NPV -- would change even here.
    """
    flat_curve = DiscountCurve(
        reference_date=MARKET_DATE,
        tenors=(date(2026, 12, 31), date(2027, 12, 31)),
        factors=(0.9, 0.9),
    )
    baseline = price_default(discount_curve=flat_curve)
    lagged = price_default(discount_curve=flat_curve, settlement_lag_days=30)
    assert lagged.npv == pytest.approx(baseline.npv)
    assert lagged.time_value == pytest.approx(baseline.time_value)
    assert lagged.per_period_values == pytest.approx(baseline.per_period_values)


def test_settlement_lag_days_negative_rejected() -> None:
    with pytest.raises(ValidationError, match="settlement_lag_days"):
        price_default(settlement_lag_days=-1)
