"""Unit tests for pricing/spreads.py (Tasks 32-34): formula correctness, spark/dark
independence, clean-spread deduction, gas-price validation, anomaly flagging, basis
statistics, crack ratios, error paths and input immutability (Properties 6-9, 42, 43)."""

from __future__ import annotations

import copy
import dataclasses
from datetime import date

import numpy as np
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.spreads import (
    basis,
    calendar_spread,
    clean_spread,
    crack_spread,
    dark_spread,
    forward_spread,
    implied_heat_rate,
    spark_spread,
)
from quantvolt.testing import assert_input_unchanged

MARKET_DATE = date(2025, 1, 1)

JAN = DeliveryPeriod(2025, 1)
FEB = DeliveryPeriod(2025, 2)
MAR = DeliveryPeriod(2025, 3)
APR = DeliveryPeriod(2025, 4)


def make_curve(
    commodity_id: str, prices: dict[DeliveryPeriod, float], unit: str = "EUR/MWh"
) -> ForwardCurve:
    return ForwardCurve(
        commodity=CommodityConfig(commodity_id, unit, Hub(commodity_id, "EEX", unit)),
        market_date=MARKET_DATE,
        nodes=tuple(CurveNode(period, prices[period], "observed") for period in sorted(prices)),
    )


# Power covers JAN-MAR, gas covers FEB-APR -> shared periods are exactly {FEB, MAR}.
POWER = make_curve("EEX_PHELIX_DE", {JAN: 100.0, FEB: 90.0, MAR: 84.0})
GAS = make_curve("TTF", {FEB: 25.0, MAR: 20.0, APR: 30.0})
COAL = make_curve("API2", {FEB: 12.0, MAR: 10.0})
EUA = make_curve("EUA", {FEB: 80.0, MAR: 75.0, APR: 70.0}, unit="EUR/tCO2")


# --- spark_spread / dark_spread (Task 32; Req 2.1; Property 6) ----------------


def test_spark_spread_matches_hand_computed_values() -> None:
    result = spark_spread(POWER, GAS, heat_rate=2.0, variable_cost=3.0, emissions_cost=1.0)
    # FEB: 90 - 2*25 - 3 - 1 = 36 ; MAR: 84 - 2*20 - 3 - 1 = 40
    assert result.per_period == {FEB: 36.0, MAR: 40.0}
    assert result.spread_type == "spark"


def test_dark_spread_matches_hand_computed_values() -> None:
    result = dark_spread(POWER, COAL, heat_rate=2.5, variable_cost=2.0, emissions_cost=0.5)
    # FEB: 90 - 2.5*12 - 2 - 0.5 = 57.5 ; MAR: 84 - 2.5*10 - 2 - 0.5 = 56.5
    assert result.per_period == {FEB: 57.5, MAR: 56.5}
    assert result.spread_type == "dark"


def test_spread_covers_only_the_curve_intersection_in_order() -> None:
    result = spark_spread(POWER, GAS, 2.0, 0.0, 0.0)
    # JAN (power only) and APR (gas only) are excluded; keys stay chronological.
    assert list(result.per_period) == [FEB, MAR]


def test_spark_computation_leaves_prior_dark_result_untouched() -> None:
    # Property 6: results are separate immutable objects; computing one spread
    # never reads or writes the other's values.
    dark = dark_spread(POWER, COAL, 2.5, 2.0, 0.5)
    dark_snapshot = copy.deepcopy(dark)
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)
    assert dark == dark_snapshot
    assert spark is not dark
    assert spark.spread_type == "spark"
    assert dark.spread_type == "dark"


def test_spread_result_is_frozen() -> None:
    result = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.spread_type = "dark"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("heat_rate", "variable_cost", "emissions_cost", "param"),
    [
        (0.0, 3.0, 1.0, "heat_rate"),
        (-2.0, 3.0, 1.0, "heat_rate"),
        (2.0, -0.1, 1.0, "variable_cost"),
        (2.0, 3.0, -1.0, "emissions_cost"),
    ],
)
def test_spread_parameter_validation_names_offending_parameter(
    heat_rate: float, variable_cost: float, emissions_cost: float, param: str
) -> None:
    for func in (spark_spread, dark_spread, forward_spread):
        with pytest.raises(ValidationError, match=param):
            func(POWER, GAS, heat_rate, variable_cost, emissions_cost)


def test_spread_no_overlap_raises_naming_both_commodities() -> None:
    power_only_jan = make_curve("EEX_PHELIX_DE", {JAN: 100.0})
    gas_only_apr = make_curve("TTF", {APR: 30.0})
    with pytest.raises(InsufficientDataError) as excinfo:
        spark_spread(power_only_jan, gas_only_apr, 2.0, 0.0, 0.0)
    message = str(excinfo.value)
    assert "EEX_PHELIX_DE" in message
    assert "TTF" in message


# --- clean_spread (Task 33; Req 2.2; Property 7) -------------------------------


def test_clean_spark_deducts_emissions_intensity_times_eua_price() -> None:
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)  # {FEB: 36, MAR: 40}
    clean = clean_spread(spark, EUA, emissions_intensity=0.5)
    # carbon: FEB 0.5*80 = 40 ; MAR 0.5*75 = 37.5
    assert clean.carbon_cost == {FEB: 40.0, MAR: 37.5}
    assert clean.per_period == {FEB: -4.0, MAR: 2.5}
    assert clean.spread_type == "spark"


def test_clean_dark_uses_the_dark_spread_as_its_base() -> None:
    # Req 2.2 reading: clean_spread cleans the ONE spread it is given; calling it
    # once per uncleaned spread yields both clean spark and clean dark.
    dark = dark_spread(POWER, COAL, 2.5, 2.0, 0.5)  # {FEB: 57.5, MAR: 56.5}
    clean = clean_spread(dark, EUA, emissions_intensity=0.25)
    # carbon: FEB 0.25*80 = 20 ; MAR 0.25*75 = 18.75
    assert clean.per_period == {FEB: 37.5, MAR: 37.75}
    assert clean.spread_type == "dark"


def test_clean_spread_with_zero_intensity_reproduces_the_uncleaned_spread() -> None:
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)
    clean = clean_spread(spark, EUA, emissions_intensity=0.0)
    assert clean.per_period == spark.per_period
    assert clean.carbon_cost == {FEB: 0.0, MAR: 0.0}


def test_clean_spread_negative_intensity_raises() -> None:
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)
    with pytest.raises(ValidationError, match="emissions_intensity"):
        clean_spread(spark, EUA, emissions_intensity=-0.1)


def test_clean_spread_missing_eua_period_raises_naming_period() -> None:
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)  # periods FEB, MAR
    eua_missing_mar = make_curve("EUA", {FEB: 80.0}, unit="EUR/tCO2")
    with pytest.raises(InsufficientDataError) as excinfo:
        clean_spread(spark, eua_missing_mar, 0.5)
    message = str(excinfo.value)
    assert "EUA" in message
    assert "month=3" in message  # the missing MAR period is identified


# --- implied_heat_rate (Task 32; Req 2.3; Property 8) ---------------------------


def test_implied_heat_rate_is_power_over_gas_per_shared_period() -> None:
    result = implied_heat_rate(POWER, GAS)
    assert result.per_period == {FEB: 90.0 / 25.0, MAR: 84.0 / 20.0}
    assert result.anomalous == ()


def test_implied_heat_rate_flags_values_outside_the_anomaly_range() -> None:
    # FEB: 3.6 inside [3, 4]; MAR: 4.2 outside -> anomalous.
    result = implied_heat_rate(POWER, GAS, anomaly_range=(3.0, 4.0))
    assert result.anomalous == (MAR,)


def test_implied_heat_rate_range_bounds_are_inclusive() -> None:
    result = implied_heat_rate(POWER, GAS, anomaly_range=(3.6, 4.2))
    assert result.anomalous == ()


def test_implied_heat_rate_flags_all_periods_when_all_are_outside() -> None:
    result = implied_heat_rate(POWER, GAS, anomaly_range=(10.0, 12.0))
    assert result.anomalous == (FEB, MAR)


@pytest.mark.parametrize("bad_gas_price", [0.0, -5.0])
def test_implied_heat_rate_nonpositive_gas_raises_naming_the_period(
    bad_gas_price: float,
) -> None:
    gas = make_curve("TTF", {FEB: 25.0, MAR: bad_gas_price})
    with pytest.raises(ValidationError) as excinfo:
        implied_heat_rate(POWER, gas)
    message = str(excinfo.value)
    assert "gas_curve" in message
    assert "month=3" in message  # identifies the offending delivery period (Property 8)


@pytest.mark.parametrize("bad_range", [(4.0, 3.0), (3.0, 3.0)])
def test_implied_heat_rate_invalid_anomaly_range_raises(
    bad_range: tuple[float, float],
) -> None:
    with pytest.raises(ValidationError, match="anomaly_range"):
        implied_heat_rate(POWER, GAS, anomaly_range=bad_range)


def test_implied_heat_rate_no_overlap_raises() -> None:
    gas_only_apr = make_curve("TTF", {APR: 30.0})
    with pytest.raises(InsufficientDataError):
        implied_heat_rate(POWER, gas_only_apr)


# --- basis (Task 34; Req 2.4; Property 9) ---------------------------------------


HUB_A = make_curve("EPEX_NL", {JAN: 50.0, FEB: 60.0, MAR: 70.0, APR: 80.0})
HUB_B = make_curve("EPEX_DE", {JAN: 45.0, FEB: 63.0, MAR: 66.0, APR: 100.0})


def test_basis_per_period_is_a_minus_b_within_the_range() -> None:
    result = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31))
    # APR (last day 2025-04-30) lies outside the range and is excluded.
    assert result.per_period == {JAN: 5.0, FEB: -3.0, MAR: 4.0}


def test_basis_statistics_match_numpy_on_the_per_period_vector() -> None:
    result = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31))
    vector = np.array([5.0, -3.0, 4.0])
    assert result.mean == float(np.mean(vector))
    assert result.std == float(np.std(vector))  # population std, ddof=0
    assert result.p5 == float(np.percentile(vector, 5.0))
    assert result.p95 == float(np.percentile(vector, 95.0))


def test_basis_range_is_inclusive_of_period_last_day() -> None:
    included = basis(HUB_A, HUB_B, start=date(2025, 3, 31), end=date(2025, 3, 31))
    assert list(included.per_period) == [MAR]
    # End one day before MAR's last day: FEB still matches, MAR falls out.
    excluded = basis(HUB_A, HUB_B, start=date(2025, 2, 1), end=date(2025, 3, 30))
    assert list(excluded.per_period) == [FEB]


def test_basis_no_overlap_in_range_raises_naming_commodities_and_range() -> None:
    with pytest.raises(InsufficientDataError) as excinfo:
        basis(HUB_A, HUB_B, start=date(2026, 1, 1), end=date(2026, 12, 31))
    message = str(excinfo.value)
    assert "EPEX_NL" in message
    assert "EPEX_DE" in message
    assert "2026-01-01" in message
    assert "2026-12-31" in message


def test_basis_disjoint_curves_raise() -> None:
    a = make_curve("EPEX_NL", {JAN: 50.0})
    b = make_curve("EPEX_DE", {FEB: 45.0})
    with pytest.raises(InsufficientDataError):
        basis(a, b, start=date(2025, 1, 1), end=date(2025, 12, 31))


def test_basis_start_after_end_raises() -> None:
    with pytest.raises(ValidationError, match="start"):
        basis(HUB_A, HUB_B, start=date(2025, 6, 1), end=date(2025, 1, 1))


# --- basis: new keyword-only lower_percentile / upper_percentile / ddof ---------


def test_basis_percentile_and_ddof_defaults_match_hardcoded_behaviour() -> None:
    baseline = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31))
    explicit = basis(
        HUB_A,
        HUB_B,
        start=date(2025, 1, 1),
        end=date(2025, 3, 31),
        lower_percentile=5.0,
        upper_percentile=95.0,
        ddof=0,
    )
    assert explicit == baseline


def test_basis_percentile_override_changes_p5_p95() -> None:
    baseline = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31))
    vector = np.array([5.0, -3.0, 4.0])
    widened = basis(
        HUB_A,
        HUB_B,
        start=date(2025, 1, 1),
        end=date(2025, 3, 31),
        lower_percentile=10.0,
        upper_percentile=90.0,
    )
    assert widened.p5 != baseline.p5
    assert widened.p5 == pytest.approx(float(np.percentile(vector, 10.0)))
    assert widened.p95 == pytest.approx(float(np.percentile(vector, 90.0)))


def test_basis_ddof_override_changes_std() -> None:
    baseline = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31))
    vector = np.array([5.0, -3.0, 4.0])
    sample_std = basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31), ddof=1)
    assert sample_std.std != baseline.std
    assert sample_std.std == pytest.approx(float(np.std(vector, ddof=1)))


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"lower_percentile": -1.0}, "lower_percentile"),
        ({"lower_percentile": 101.0}, "lower_percentile"),
        ({"upper_percentile": -1.0}, "upper_percentile"),
        ({"upper_percentile": 101.0}, "upper_percentile"),
        ({"lower_percentile": 95.0, "upper_percentile": 5.0}, "lower_percentile"),
        ({"ddof": -1}, "ddof"),
    ],
)
def test_basis_percentile_and_ddof_validation(kwargs: dict[str, float], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        basis(HUB_A, HUB_B, start=date(2025, 1, 1), end=date(2025, 3, 31), **kwargs)


# --- crack_spread (Task 34; Property 42) ----------------------------------------


CRUDE = make_curve("BRENT", {JAN: 70.0, FEB: 80.0, MAR: 90.0}, unit="USD/bbl")
GASOLINE = make_curve("RBOB", {FEB: 100.0, MAR: 105.0, APR: 110.0}, unit="USD/bbl")
DIESEL = make_curve("ULSD", {FEB: 95.0, MAR: 100.0}, unit="USD/bbl")


def test_crack_spread_3_2_1_matches_hand_computed_values() -> None:
    result = crack_spread({"gasoline": GASOLINE, "diesel": DIESEL}, CRUDE, ratio=(3, 2, 1))
    # Shared periods of ALL curves: FEB, MAR (JAN lacks products, APR lacks diesel).
    # FEB: (2*100 + 1*95 - 3*80) / 3 = 55/3 ; MAR: (2*105 + 1*100 - 3*90) / 3 = 40/3
    assert result.per_period == {FEB: 55.0 / 3.0, MAR: 40.0 / 3.0}
    assert result.ratio == (3, 2, 1)


def test_crack_spread_equals_unit_weighted_products_minus_crude() -> None:
    # Property 42 phrasing: product weights (2/3, 1/3) sum to 1, minus the crude price.
    result = crack_spread({"gasoline": GASOLINE, "diesel": DIESEL}, CRUDE, ratio=(3, 2, 1))
    expected_feb = (2.0 / 3.0) * 100.0 + (1.0 / 3.0) * 95.0 - 80.0
    assert result.per_period[FEB] == pytest.approx(expected_feb)


def test_crack_spread_single_product_ratio() -> None:
    result = crack_spread({"gasoline": GASOLINE}, CRUDE, ratio=(2, 2))
    # FEB: (2*100 - 2*80) / 2 = 20 ; MAR: (2*105 - 2*90) / 2 = 15
    assert result.per_period == {FEB: 20.0, MAR: 15.0}


def test_crack_spread_ratio_length_mismatch_raises() -> None:
    with pytest.raises(ValidationError, match="ratio"):
        crack_spread({"gasoline": GASOLINE, "diesel": DIESEL}, CRUDE, ratio=(3, 2))


@pytest.mark.parametrize("bad_ratio", [(0, 2, 1), (3, -2, 1), (3, 2, 0)])
def test_crack_spread_nonpositive_ratio_entry_raises(bad_ratio: tuple[int, ...]) -> None:
    with pytest.raises(ValidationError, match="ratio"):
        crack_spread({"gasoline": GASOLINE, "diesel": DIESEL}, CRUDE, ratio=bad_ratio)


def test_crack_spread_empty_products_raises() -> None:
    with pytest.raises(ValidationError, match="product_curves"):
        crack_spread({}, CRUDE, ratio=(3,))


def test_crack_spread_no_common_period_across_all_curves_raises() -> None:
    crude_jan_only = make_curve("BRENT", {JAN: 70.0}, unit="USD/bbl")
    with pytest.raises(InsufficientDataError) as excinfo:
        crack_spread({"gasoline": GASOLINE, "diesel": DIESEL}, crude_jan_only)
    message = str(excinfo.value)
    assert "BRENT" in message
    assert "gasoline" in message


# --- forward_spread (Task 34; Property 43) --------------------------------------


def test_forward_spread_equals_spark_spread_on_identical_inputs() -> None:
    forward = forward_spread(POWER, GAS, 2.0, 3.0, 1.0)
    spark = spark_spread(POWER, GAS, 2.0, 3.0, 1.0)
    assert forward == spark
    assert forward.spread_type == "spark"


# --- calendar_spread (Task 34; Property 44) ---------------------------------------


def test_calendar_spread_is_later_minus_earlier_adjusted_for_storage() -> None:
    # JAN=100, MAR=84 on POWER: raw difference = -16, 2 months at 1.5/month = 3.0.
    result = calendar_spread(POWER, JAN, MAR, storage_cost=1.5)
    assert result.price_difference == pytest.approx(84.0 - 100.0)
    assert result.storage_cost_total == pytest.approx(3.0)
    assert result.spread == pytest.approx(-16.0 - 3.0)
    assert result.period_early == JAN
    assert result.period_late == MAR


def test_calendar_spread_sign_indicates_contango_vs_backwardation() -> None:
    contango = make_curve("TTF", {FEB: 20.0, MAR: 25.0})
    assert calendar_spread(contango, FEB, MAR).spread > 0  # contango
    assert calendar_spread(POWER, JAN, FEB).spread < 0  # backwardated curve


def test_calendar_spread_zero_storage_cost_is_the_raw_difference() -> None:
    result = calendar_spread(POWER, JAN, FEB)
    assert result.spread == result.price_difference
    assert result.storage_cost_total == 0.0


def test_calendar_spread_periods_must_be_ordered() -> None:
    with pytest.raises(ValidationError, match="period_early"):
        calendar_spread(POWER, MAR, JAN)
    with pytest.raises(ValidationError, match="period_early"):
        calendar_spread(POWER, JAN, JAN)


def test_calendar_spread_negative_storage_cost_raises() -> None:
    with pytest.raises(ValidationError, match="storage_cost"):
        calendar_spread(POWER, JAN, FEB, storage_cost=-0.1)


def test_calendar_spread_missing_period_raises_missing_tenor() -> None:
    from quantvolt.exceptions import MissingTenorError

    with pytest.raises(MissingTenorError):
        calendar_spread(POWER, JAN, APR)  # APR not on POWER


# --- input immutability (coding-style.md section 7) ------------------------------


def test_spread_functions_do_not_mutate_their_inputs() -> None:
    spark = assert_input_unchanged(spark_spread, POWER, GAS, 2.0, 3.0, 1.0)
    assert_input_unchanged(dark_spread, POWER, COAL, 2.5, 2.0, 0.5)
    assert_input_unchanged(clean_spread, spark, EUA, 0.5)
    assert_input_unchanged(implied_heat_rate, POWER, GAS, (3.0, 4.0))
    assert_input_unchanged(basis, HUB_A, HUB_B, date(2025, 1, 1), date(2025, 3, 31))
    assert_input_unchanged(crack_spread, {"gasoline": GASOLINE, "diesel": DIESEL}, CRUDE, (3, 2, 1))
    assert_input_unchanged(forward_spread, POWER, GAS, 2.0, 3.0, 1.0)
    assert_input_unchanged(calendar_spread, POWER, JAN, MAR, 1.5)
