"""Unit tests for `quantvolt.models.units` (gas-unit-conventions spec, Req 1-5).

Covers `PriceUnit` construction/validation, parse/render round-trip, the pure energy
conversion functions, and `convert_price`, including the worked examples from the
spec's design.md.
"""

from __future__ import annotations

import math

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.units import (
    KWH_PER_THERM,
    MWH_PER_MMBTU,
    MWH_PER_THERM,
    PENCE_PER_POUND,
    THERMS_PER_MMBTU,
    PriceUnit,
    convert_price,
    mmbtu_to_mwh,
    mwh_to_mmbtu,
    mwh_to_therms,
    therms_to_mwh,
)

# --- Constants (Requirement 3) -----------------------------------------------


def test_constants_match_provenance_values() -> None:
    assert KWH_PER_THERM == 29.3071
    assert pytest.approx(0.0293071) == MWH_PER_THERM
    assert THERMS_PER_MMBTU == 10.0
    assert PENCE_PER_POUND == 100.0


def test_mwh_per_mmbtu_is_derived_and_matches_source_document() -> None:
    assert MWH_PER_MMBTU == THERMS_PER_MMBTU * MWH_PER_THERM
    assert pytest.approx(0.293071, rel=1e-12) == MWH_PER_MMBTU


# --- PriceUnit construction validation (Requirement 1) -----------------------


@pytest.mark.parametrize("currency", ["EUR", "GBP", "USD", "GBp"])
def test_valid_currencies_are_accepted(currency: str) -> None:
    denominator = "MWh" if currency != "GBp" else "therm"
    unit = PriceUnit(currency, denominator)
    assert unit.currency == currency


@pytest.mark.parametrize("currency", ["eur", "Eur", "EU", "EURO", "gbp", "GBP ", " GBP", "gBp", ""])
def test_invalid_currencies_are_rejected(currency: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PriceUnit(currency, "MWh")
    message = str(excinfo.value)
    assert "currency" in message


@pytest.mark.parametrize("denominator", ["MWh", "therm", "MMBtu", "tCO2", "bbl", "t"])
def test_valid_denominators_are_accepted(denominator: str) -> None:
    unit = PriceUnit("EUR", denominator)
    assert unit.denominator == denominator


def test_mbtu_denominator_raises_did_you_mean_mmbtu_hint() -> None:
    with pytest.raises(ValidationError) as excinfo:
        PriceUnit("EUR", "MBtu")
    message = str(excinfo.value)
    assert "did you mean MMBtu?" in message
    assert "denominator" in message


@pytest.mark.parametrize("denominator", ["mwh", "kWh", "GJ", "MMBTU", "", "Btu"])
def test_other_invalid_denominators_list_recognised_units(denominator: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PriceUnit("EUR", denominator)
    message = str(excinfo.value)
    assert "denominator" in message
    assert "MWh" in message and "therm" in message and "MMBtu" in message and "tCO2" in message
    assert "bbl" in message and "'t'" in message


def test_price_unit_is_frozen() -> None:
    unit = PriceUnit("EUR", "MWh")
    with pytest.raises(AttributeError):
        unit.currency = "USD"  # type: ignore[misc]


# --- Parse / render round-trip (Requirement 2) -------------------------------


def test_parse_valid_text() -> None:
    assert PriceUnit.parse("EUR/MWh") == PriceUnit("EUR", "MWh")
    assert PriceUnit.parse("GBp/therm") == PriceUnit("GBp", "therm")


def test_str_renders_currency_slash_denominator() -> None:
    assert str(PriceUnit("EUR", "MWh")) == "EUR/MWh"
    assert str(PriceUnit("GBp", "therm")) == "GBp/therm"


@pytest.mark.parametrize("text", ["EURMWh", "EUR/MWh/extra", "EUR", "/MWh", "EUR/", "/"])
def test_parse_rejects_malformed_text(text: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PriceUnit.parse(text)
    assert text in str(excinfo.value) or "text" in str(excinfo.value)


@pytest.mark.parametrize(
    "unit",
    [
        PriceUnit("EUR", "MWh"),
        PriceUnit("GBp", "therm"),
        PriceUnit("USD", "MMBtu"),
        PriceUnit("USD", "bbl"),
        PriceUnit("EUR", "t"),
    ],
)
def test_round_trip_parse_of_str_recovers_original_unit(unit: PriceUnit) -> None:
    assert PriceUnit.parse(str(unit)) == unit


@pytest.mark.parametrize(
    "text", ["EUR/MWh", "GBp/therm", "USD/MMBtu", "EUR/tCO2", "USD/bbl", "EUR/t"]
)
def test_round_trip_str_of_parse_recovers_original_text(text: str) -> None:
    assert str(PriceUnit.parse(text)) == text


def test_parse_does_not_normalise_whitespace_and_rejects_it() -> None:
    with pytest.raises(ValidationError):
        PriceUnit.parse(" EUR/MWh")
    with pytest.raises(ValidationError):
        PriceUnit.parse("EUR/ MWh")
    with pytest.raises(ValidationError):
        PriceUnit.parse("EUR/MWh ")


# --- Energy-quantity conversion functions (Requirement 4) --------------------


def test_therms_to_mwh_matches_hand_computed_value() -> None:
    assert therms_to_mwh(1.0) == pytest.approx(0.0293071, rel=1e-12)
    assert therms_to_mwh(10.0) == pytest.approx(0.293071, rel=1e-12)


def test_mwh_to_therms_matches_hand_computed_value() -> None:
    assert mwh_to_therms(1.0) == pytest.approx(34.12142, rel=1e-6)


def test_mmbtu_to_mwh_matches_hand_computed_value() -> None:
    assert mmbtu_to_mwh(1.0) == pytest.approx(0.293071, rel=1e-12)


def test_mwh_to_mmbtu_matches_hand_computed_value() -> None:
    assert mwh_to_mmbtu(1.0) == pytest.approx(3.412142, rel=1e-6)


@pytest.mark.parametrize("fn", [therms_to_mwh, mwh_to_therms, mmbtu_to_mwh, mwh_to_mmbtu])
def test_conversion_functions_reject_non_finite_input(fn) -> None:  # type: ignore[no-untyped-def]
    for bad in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValidationError):
            fn(bad)


def test_energy_round_trip_recovers_original_value() -> None:
    x = 123.456
    assert mwh_to_therms(therms_to_mwh(x)) == pytest.approx(x, rel=1e-12)
    assert mwh_to_mmbtu(mmbtu_to_mwh(x)) == pytest.approx(x, rel=1e-12)


# --- convert_price (Requirement 5) -------------------------------------------


def test_convert_price_worked_example_gbp_therm_to_mwh() -> None:
    # 85 GBp/therm -> GBp/MWh
    gbp_therm = PriceUnit("GBp", "therm")
    gbp_mwh = PriceUnit("GBp", "MWh")
    result = convert_price(85.0, gbp_therm, gbp_mwh)
    assert result == pytest.approx(85.0 / MWH_PER_THERM, rel=1e-12)
    assert result == pytest.approx(2900.32, rel=1e-4)

    # ...then GBp/MWh -> GBP/MWh
    gbp_pound_mwh = PriceUnit("GBP", "MWh")
    final = convert_price(result, gbp_mwh, gbp_pound_mwh)
    assert final == pytest.approx(29.0032, rel=1e-4)


def test_convert_price_worked_example_usd_mmbtu_to_mwh() -> None:
    result = convert_price(10.0, PriceUnit("USD", "MMBtu"), PriceUnit("USD", "MWh"))
    assert result == pytest.approx(34.1214, rel=1e-4)


def test_convert_price_identity_conversion_is_a_no_op() -> None:
    unit = PriceUnit("EUR", "MWh")
    assert convert_price(42.0, unit, unit) == pytest.approx(42.0, rel=1e-12)


def test_convert_price_gbp_pence_pair_multiplies_or_divides_by_100() -> None:
    gbp_mwh = PriceUnit("GBP", "MWh")
    pence_mwh = PriceUnit("GBp", "MWh")
    assert convert_price(1.0, gbp_mwh, pence_mwh) == pytest.approx(100.0)
    assert convert_price(100.0, pence_mwh, gbp_mwh) == pytest.approx(1.0)


def test_convert_price_round_trip_recovers_original() -> None:
    a = PriceUnit("EUR", "therm")
    b = PriceUnit("EUR", "MMBtu")
    value = 17.5
    forward = convert_price(value, a, b)
    back = convert_price(forward, b, a)
    assert back == pytest.approx(value, rel=1e-12)


def test_convert_price_is_linear_in_value() -> None:
    a = PriceUnit("GBp", "therm")
    b = PriceUnit("GBP", "MWh")
    k = 3.0
    v = 12.0
    assert convert_price(k * v, a, b) == pytest.approx(k * convert_price(v, a, b), rel=1e-12)


def test_convert_price_rejects_cross_currency_outside_gbp_pence_pair() -> None:
    with pytest.raises(ValidationError) as excinfo:
        convert_price(10.0, PriceUnit("EUR", "MWh"), PriceUnit("USD", "MWh"))
    message = str(excinfo.value)
    assert "FX rate" in message


def test_convert_price_tco2_only_converts_to_tco2() -> None:
    with pytest.raises(ValidationError):
        convert_price(10.0, PriceUnit("EUR", "tCO2"), PriceUnit("EUR", "MWh"))
    with pytest.raises(ValidationError):
        convert_price(10.0, PriceUnit("EUR", "MWh"), PriceUnit("EUR", "tCO2"))


def test_convert_price_tco2_same_currency_is_identity() -> None:
    unit = PriceUnit("EUR", "tCO2")
    assert convert_price(9.0, unit, unit) == pytest.approx(9.0, rel=1e-12)


def test_convert_price_tco2_allows_gbp_pence_currency_pair() -> None:
    gbp = PriceUnit("GBP", "tCO2")
    pence = PriceUnit("GBp", "tCO2")
    assert convert_price(1.0, gbp, pence) == pytest.approx(100.0)


# --- bbl / t: energy-inconvertible denominators (Task 14, deferred) ----------


@pytest.mark.parametrize("denominator", ["bbl", "t"])
def test_convert_price_inert_denominator_only_converts_to_same_denominator(
    denominator: str,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        convert_price(10.0, PriceUnit("USD", denominator), PriceUnit("USD", "MWh"))
    message = str(excinfo.value)
    assert "energy-content" in message
    with pytest.raises(ValidationError):
        convert_price(10.0, PriceUnit("USD", "MWh"), PriceUnit("USD", denominator))


@pytest.mark.parametrize("denominator", ["bbl", "t"])
def test_convert_price_inert_denominator_same_currency_is_identity(denominator: str) -> None:
    unit = PriceUnit("USD", denominator)
    assert convert_price(9.0, unit, unit) == pytest.approx(9.0, rel=1e-12)


@pytest.mark.parametrize("denominator", ["bbl", "t"])
def test_convert_price_inert_denominator_allows_gbp_pence_currency_pair(
    denominator: str,
) -> None:
    gbp = PriceUnit("GBP", denominator)
    pence = PriceUnit("GBp", denominator)
    assert convert_price(1.0, gbp, pence) == pytest.approx(100.0)


def test_convert_price_rejects_bbl_to_t_cross_denominator() -> None:
    with pytest.raises(ValidationError):
        convert_price(10.0, PriceUnit("USD", "bbl"), PriceUnit("USD", "t"))


def test_convert_price_rejects_non_finite_value() -> None:
    unit = PriceUnit("EUR", "MWh")
    for bad in (math.inf, -math.inf, math.nan):
        with pytest.raises(ValidationError):
            convert_price(bad, unit, unit)


# --- string-form units (parsed via PriceUnit.parse at the boundary) ----------


def test_convert_price_accepts_string_units_worked_example() -> None:
    # The string form must agree exactly with the PriceUnit form (Req 5, amended
    # 2026-07-19): 85 GBp/therm -> 29.0032 GBP/MWh.
    assert convert_price(85.0, "GBp/therm", "GBP/MWh") == pytest.approx(
        convert_price(85.0, PriceUnit("GBp", "therm"), PriceUnit("GBP", "MWh")), rel=1e-15
    )
    assert convert_price(85.0, "GBp/therm", "GBP/MWh") == pytest.approx(29.0032, rel=1e-4)
    assert convert_price(10.0, "USD/MMBtu", "USD/MWh") == pytest.approx(34.1214, rel=1e-4)


def test_convert_price_string_and_priceunit_forms_mix() -> None:
    assert convert_price(50.0, "EUR/MWh", PriceUnit("EUR", "therm")) == pytest.approx(
        convert_price(50.0, PriceUnit("EUR", "MWh"), PriceUnit("EUR", "therm")), rel=1e-15
    )


def test_convert_price_malformed_string_raises_validation_error() -> None:
    # A malformed string must fail loudly through PriceUnit.parse, never leak an
    # AttributeError from the arithmetic below.
    with pytest.raises(ValidationError):
        convert_price(1.0, "EUR/MBtu", "EUR/MWh")
    with pytest.raises(ValidationError):
        convert_price(1.0, "not-a-unit", "EUR/MWh")
