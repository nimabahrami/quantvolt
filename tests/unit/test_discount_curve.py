"""Unit tests for DiscountCurve (Task 6): interpolation, range errors, validation."""

from __future__ import annotations

from datetime import date

import pytest

from quantvolt.exceptions import MissingTenorError, ValidationError
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.testing import assert_input_unchanged

REFERENCE = date(2025, 1, 1)
# Tenors at 10, 20, 30 days past the reference date, with decreasing factors.
TENORS = (date(2025, 1, 11), date(2025, 1, 21), date(2025, 1, 31))
FACTORS = (0.99, 0.98, 0.97)


def make_curve() -> DiscountCurve:
    return DiscountCurve(reference_date=REFERENCE, tenors=TENORS, factors=FACTORS)


# --- interpolation / lookup -------------------------------------------------


@pytest.mark.parametrize(
    ("tenor", "expected"),
    [
        (date(2025, 1, 11), 0.99),
        (date(2025, 1, 21), 0.98),
        (date(2025, 1, 31), 0.97),
    ],
)
def test_exact_tenor_lookup_returns_stored_factor(tenor: date, expected: float) -> None:
    assert make_curve().discount_factor(tenor) == expected


def test_linear_midpoint_interpolation() -> None:
    # Day 15 sits exactly halfway between day 10 (0.99) and day 20 (0.98).
    assert make_curve().discount_factor(date(2025, 1, 16)) == pytest.approx(0.985)


def test_linear_interpolation_off_midpoint() -> None:
    # Day 13: weight = (13 - 10) / (20 - 10) = 0.3 -> 0.99 + 0.3 * (0.98 - 0.99).
    assert make_curve().discount_factor(date(2025, 1, 14)) == pytest.approx(0.987)


# --- out-of-range errors ----------------------------------------------------


def test_before_first_tenor_raises() -> None:
    with pytest.raises(MissingTenorError, match="outside the covered range"):
        make_curve().discount_factor(date(2025, 1, 5))


def test_reference_date_itself_is_out_of_range() -> None:
    with pytest.raises(MissingTenorError, match="2025-01-01"):
        make_curve().discount_factor(REFERENCE)


def test_after_last_tenor_raises() -> None:
    with pytest.raises(MissingTenorError, match="2025-02-01"):
        make_curve().discount_factor(date(2025, 2, 1))


# --- construction validation ------------------------------------------------


def test_empty_tenors_rejected() -> None:
    with pytest.raises(ValidationError, match="tenors"):
        DiscountCurve(reference_date=REFERENCE, tenors=(), factors=())


def test_length_mismatch_rejected() -> None:
    with pytest.raises(ValidationError, match="equal length"):
        DiscountCurve(reference_date=REFERENCE, tenors=TENORS, factors=(0.99, 0.98))


def test_non_increasing_tenors_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        DiscountCurve(
            reference_date=REFERENCE,
            tenors=(date(2025, 1, 21), date(2025, 1, 11)),
            factors=(0.98, 0.99),
        )


def test_duplicate_tenors_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        DiscountCurve(
            reference_date=REFERENCE,
            tenors=(date(2025, 1, 11), date(2025, 1, 11)),
            factors=(0.99, 0.98),
        )


def test_tenor_not_after_reference_date_rejected() -> None:
    with pytest.raises(ValidationError, match="reference_date"):
        DiscountCurve(
            reference_date=REFERENCE,
            tenors=(REFERENCE, date(2025, 1, 11)),
            factors=(1.0, 0.99),
        )


@pytest.mark.parametrize("bad_factor", [1.5, 0.0, -0.1])
def test_factor_outside_unit_interval_rejected(bad_factor: float) -> None:
    with pytest.raises(ValidationError, match=r"factors\["):
        DiscountCurve(
            reference_date=REFERENCE,
            tenors=(date(2025, 1, 11),),
            factors=(bad_factor,),
        )


def test_factor_of_one_is_allowed() -> None:
    curve = DiscountCurve(reference_date=REFERENCE, tenors=(date(2025, 1, 11),), factors=(1.0,))
    assert curve.discount_factor(date(2025, 1, 11)) == 1.0


# --- immutability -----------------------------------------------------------


def test_construction_does_not_mutate_inputs() -> None:
    tenors = TENORS
    factors = FACTORS
    curve = assert_input_unchanged(
        DiscountCurve, reference_date=REFERENCE, tenors=tenors, factors=factors
    )
    assert isinstance(curve, DiscountCurve)
    assert tenors == TENORS
    assert factors == FACTORS


def test_instance_is_frozen() -> None:
    curve = make_curve()
    with pytest.raises(AttributeError):
        curve.factors = (0.5,)  # type: ignore[misc]
