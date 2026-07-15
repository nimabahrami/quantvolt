"""Unit tests for the shared boundary-validation guards in ``_validation.py``.

Fix 6 regression: ``require_non_negative`` previously used a plain ``value < 0``
check, under which ``NaN < 0`` is ``False`` in IEEE-754 float comparison, so a NaN
silently passed the guard (verified: ``price_spread_option(strike=NaN)`` returned an
all-NaN result instead of raising). ``require_positive`` and ``require_in_range``
already rejected NaN because ``not (value > 0)`` / ``not (lo <= value <= hi)`` are both
``True`` for NaN; ``require_non_negative`` now matches that pattern.
"""

from __future__ import annotations

import math

import pytest

from quantvolt._validation import (
    require_correlation,
    require_discount_factor,
    require_in_range,
    require_non_negative,
    require_positive,
    require_probability,
)
from quantvolt.exceptions import ValidationError


def test_require_non_negative_accepts_zero_and_positive() -> None:
    require_non_negative("x", 0.0)
    require_non_negative("x", 3.5)


def test_require_non_negative_rejects_negative() -> None:
    with pytest.raises(ValidationError, match="x"):
        require_non_negative("x", -0.1)


def test_require_non_negative_rejects_nan() -> None:
    # Previously silently passed: NaN < 0 is False (verified).
    with pytest.raises(ValidationError, match="x"):
        require_non_negative("x", float("nan"))


def test_require_non_negative_rejects_infinity() -> None:
    with pytest.raises(ValidationError, match="x"):
        require_non_negative("x", math.inf)


@pytest.mark.parametrize(
    "guard",
    [
        require_positive,
        require_non_negative,
        lambda name, value: require_in_range(name, value, 0.0, 10.0),
        require_probability,
        require_discount_factor,
        require_correlation,
    ],
)
def test_all_scalar_guards_reject_nan(guard) -> None:  # type: ignore[no-untyped-def]
    # Sibling guards already rejected NaN; this pins that require_non_negative now
    # belongs to the same family rather than being the one silent exception.
    with pytest.raises(ValidationError):
        guard("value", float("nan"))
