"""Reusable boundary-validation guards. Public entry points validate through these before any
computation, raising ``ValidationError`` on the first violated constraint."""

from __future__ import annotations

import math
from collections.abc import Sized

from .exceptions import ValidationError


def require_positive(name: str, value: float) -> None:
    if not value > 0:
        raise ValidationError(f"{name} must be > 0, got {value!r}")


def require_non_negative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValidationError(f"{name} must be finite and >= 0, got {value!r}")


def require_in_range(name: str, value: float, lo: float, hi: float) -> None:
    if not (lo <= value <= hi):
        raise ValidationError(f"{name} must be in [{lo}, {hi}], got {value!r}")


def require_probability(name: str, value: float) -> None:
    if not (0.0 <= value <= 1.0):
        raise ValidationError(f"{name} must be in [0, 1], got {value!r}")


def require_discount_factor(name: str, value: float) -> None:
    if not (0.0 < value <= 1.0):
        raise ValidationError(f"{name} must be in (0, 1], got {value!r}")


def require_correlation(name: str, value: float) -> None:
    if not (-1.0 < value < 1.0):
        raise ValidationError(f"{name} must be in (-1, 1), got {value!r}")


def require_non_empty(name: str, value: Sized) -> None:
    if len(value) == 0:
        raise ValidationError(f"{name} must be non-empty")


def require_finite(name: str, value: float) -> None:
    """Require one finite real-valued scalar."""
    if not math.isfinite(value):
        raise ValidationError(f"{name} must be finite, got {value!r}")


def require_integer_at_least(name: str, value: int, minimum: int) -> None:
    """Require a genuine integer at or above ``minimum`` (booleans are rejected)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValidationError(f"{name} must be an integer >= {minimum}, got {value!r}")


def require_length(name: str, value: Sized, expected: int) -> None:
    """Require an exact collection length."""
    actual = len(value)
    if actual != expected:
        raise ValidationError(f"{name} must have length {expected}, got {actual}")
