"""Unit-conversion correctness properties (design Properties 75-78; gas-unit-conventions
spec Task 5).

Each test is tagged with its design Property number and runs >= 100 Hypothesis examples
(profile ``quantvolt`` in ``tests/conftest.py``). Property 79 (curve serialisation
regression) is exercised by the existing ``tests/property/test_curve_properties.py``
Property 5 tests, which sample ``BUILT_IN_COMMODITIES`` via ``strategies.commodity_configs``
and therefore automatically cover the corrected native units.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.units import (
    PriceUnit,
    convert_price,
    mmbtu_to_mwh,
    mwh_to_mmbtu,
    mwh_to_therms,
    therms_to_mwh,
)

_FINITE_ENERGY = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
_FINITE_PRICE = st.floats(min_value=-1e9, max_value=1e9, allow_nan=False, allow_infinity=False)
_SMALL_MULTIPLIER = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)

_CURRENCIES = ("EUR", "GBP", "USD", "GBp")
_ENERGY_DENOMINATORS = ("MWh", "therm", "MMBtu")
# Energy-inconvertible denominators (Task 14, deferred): validate/round-trip like any other
# denominator, but convert_price refuses to convert them to/from an energy denominator or to
# a *different* inert denominator (mirrors the tCO2 pattern; see models/units.py).
_INERT_DENOMINATORS = ("tCO2", "bbl", "t")


def _currencies() -> st.SearchStrategy[str]:
    return st.sampled_from(_CURRENCIES)


def _energy_denominators() -> st.SearchStrategy[str]:
    return st.sampled_from(_ENERGY_DENOMINATORS)


def _price_units() -> st.SearchStrategy[PriceUnit]:
    """Any valid PriceUnit over the recognised currency/denominator product."""
    denominators = (*_ENERGY_DENOMINATORS, *_INERT_DENOMINATORS)
    return st.builds(PriceUnit, currency=_currencies(), denominator=st.sampled_from(denominators))


def _same_or_gbp_pence_pair(unit_a: PriceUnit, unit_b: PriceUnit) -> bool:
    if unit_a.currency == unit_b.currency:
        return True
    return {unit_a.currency, unit_b.currency} == {"GBp", "GBP"}


def _convertible_pairs() -> st.SearchStrategy[tuple[PriceUnit, PriceUnit]]:
    """Pairs of PriceUnits that convert_price actually supports (same/GBp-GBP currency
    pair, and denominators compatible — both energy, or both tCO2)."""

    @st.composite
    def _draw(draw: st.DrawFn) -> tuple[PriceUnit, PriceUnit]:
        currency_a = draw(_currencies())
        same_currency_pair = draw(st.booleans())
        if same_currency_pair:
            currency_b = currency_a
        elif currency_a == "GBp":
            currency_b = "GBP"
        elif currency_a == "GBP":
            currency_b = "GBp"
        else:
            currency_b = currency_a  # non-GBp/GBP currencies must stay same to be convertible

        use_inert = draw(st.booleans())
        if use_inert:
            denom_a = denom_b = draw(st.sampled_from(_INERT_DENOMINATORS))
        else:
            denom_a = draw(_energy_denominators())
            denom_b = draw(_energy_denominators())
        return PriceUnit(currency_a, denom_a), PriceUnit(currency_b, denom_b)

    return _draw()


# Feature: gas-unit-conventions, Property 75: energy round-trip
@given(value=_FINITE_ENERGY)
def test_property_75_therm_round_trip(value: float) -> None:
    assert math.isclose(mwh_to_therms(therms_to_mwh(value)), value, rel_tol=1e-12, abs_tol=1e-9)


@given(value=_FINITE_ENERGY)
def test_property_75_mmbtu_round_trip(value: float) -> None:
    assert math.isclose(mwh_to_mmbtu(mmbtu_to_mwh(value)), value, rel_tol=1e-12, abs_tol=1e-9)


# Feature: gas-unit-conventions, Property 76: PriceUnit parse/render identity
@given(unit=_price_units())
def test_property_76_parse_of_str_recovers_unit(unit: PriceUnit) -> None:
    assert PriceUnit.parse(str(unit)) == unit


@given(
    currency=_currencies(),
    denominator=st.sampled_from((*_ENERGY_DENOMINATORS, *_INERT_DENOMINATORS)),
)
def test_property_76_str_of_parse_recovers_text(currency: str, denominator: str) -> None:
    text = f"{currency}/{denominator}"
    assert str(PriceUnit.parse(text)) == text


# Feature: gas-unit-conventions, Property 77: convert_price round-trip + linearity
@given(pair=_convertible_pairs(), value=_FINITE_PRICE)
def test_property_77_convert_price_round_trip(
    pair: tuple[PriceUnit, PriceUnit], value: float
) -> None:
    unit_a, unit_b = pair
    forward = convert_price(value, unit_a, unit_b)
    back = convert_price(forward, unit_b, unit_a)
    assert math.isclose(back, value, rel_tol=1e-12, abs_tol=1e-9)


@given(pair=_convertible_pairs(), value=_FINITE_PRICE, multiplier=_SMALL_MULTIPLIER)
def test_property_77_convert_price_is_linear(
    pair: tuple[PriceUnit, PriceUnit], value: float, multiplier: float
) -> None:
    unit_a, unit_b = pair
    scaled = convert_price(multiplier * value, unit_a, unit_b)
    expected = multiplier * convert_price(value, unit_a, unit_b)
    assert math.isclose(scaled, expected, rel_tol=1e-9, abs_tol=1e-6)


# Feature: gas-unit-conventions, Property 78: registry invariant
def test_property_78_every_builtin_parses_and_config_matches_hub() -> None:
    assert len(BUILT_IN_COMMODITIES) >= 1
    for config in BUILT_IN_COMMODITIES.values():
        PriceUnit.parse(config.price_unit)
        PriceUnit.parse(config.hub.price_unit)
        assert config.price_unit == config.hub.price_unit


# Feature: gas-unit-conventions Task 14 (deferred): energy-inconvertible denominators
# (tCO2/bbl/t) refuse cross-denominator conversion.
@given(
    inert=st.sampled_from(_INERT_DENOMINATORS),
    other=st.sampled_from((*_ENERGY_DENOMINATORS, *_INERT_DENOMINATORS)),
    currency=_currencies(),
    value=_FINITE_PRICE,
)
def test_inert_denominators_refuse_cross_denominator_conversion(
    inert: str, other: str, currency: str, value: float
) -> None:
    if other == inert:
        return  # same-denominator conversion is the identity case, covered elsewhere
    from_unit = PriceUnit(currency, inert)
    to_unit = PriceUnit(currency, other)
    with pytest.raises(ValidationError):
        convert_price(value, from_unit, to_unit)
    with pytest.raises(ValidationError):
        convert_price(value, to_unit, from_unit)
