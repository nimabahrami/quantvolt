"""Unit tests for the root-finding / finite-difference kernels (Task 12)."""

from __future__ import annotations

import math

import pytest
from scipy.optimize import brentq  # type: ignore[import-untyped]

from quantvolt.numerics.rootfind import brent_root, finite_difference_bump


def test_brent_root_recovers_sqrt_two() -> None:
    root = brent_root(lambda x: x**2 - 2.0, 0.0, 2.0)
    assert root == pytest.approx(math.sqrt(2.0), abs=1e-4)


def test_brent_root_on_linear_function() -> None:
    # 2x - 4 has its root at x = 2.
    root = brent_root(lambda x: 2.0 * x - 4.0, 0.0, 10.0)
    assert root == pytest.approx(2.0, abs=1e-4)


def test_brent_root_solves_to_tolerance() -> None:
    root = brent_root(lambda x: math.cos(x), 1.0, 2.0)
    assert root == pytest.approx(math.pi / 2.0, abs=1e-4)


def test_brent_root_endpoint_is_root() -> None:
    # b is exactly a root; f(a)*f(b) == 0, so the bracketing check passes.
    root = brent_root(lambda x: x - 3.0, 0.0, 3.0)
    assert root == pytest.approx(3.0, abs=1e-4)


def test_brent_root_non_bracketing_raises() -> None:
    # x**2 + 1 is strictly positive: f(a) and f(b) share the same sign.
    with pytest.raises(ValueError, match="opposite signs"):
        brent_root(lambda x: x**2 + 1.0, -1.0, 1.0)


def test_brent_root_same_sign_positive_raises() -> None:
    with pytest.raises(ValueError):
        brent_root(lambda x: x + 5.0, 1.0, 2.0)


def test_finite_difference_bump_quadratic() -> None:
    # d/dx (x**2) = 2x; at x = 3 the derivative is 6.
    deriv = finite_difference_bump(lambda x: x**2, 3.0, 1e-5)
    assert deriv == pytest.approx(6.0, abs=1e-6)


def test_finite_difference_bump_sine_is_cosine() -> None:
    # d/dx sin(x) = cos(x); check at a couple of points.
    for x in (0.0, 0.5, 1.0, math.pi / 3.0):
        deriv = finite_difference_bump(math.sin, x, 1e-6)
        assert deriv == pytest.approx(math.cos(x), abs=1e-6)


def test_finite_difference_bump_is_exact_for_linear() -> None:
    # Central difference is exact for affine functions regardless of bump.
    deriv = finite_difference_bump(lambda x: 3.0 * x + 7.0, 42.0, 0.25)
    assert deriv == pytest.approx(3.0, abs=1e-12)


# --- Fix 8 regression: brent_root no longer double-counts the bracket endpoints ---


def test_brent_root_call_count_matches_raw_brentq_exactly() -> None:
    # Previously pre-evaluated f(a) and f(b) before calling brentq (which evaluates
    # them again internally), inflating any caller's objective-evaluation count by
    # exactly 2 (verified: 9 vs scipy's 7 for a representative implied-vol inversion).
    # brent_root's own call count must now match a bare brentq call one-for-one.
    def f(x: float) -> float:
        return x**2 - 2.0

    calls_via_wrapper = 0

    def counted_wrapper(x: float) -> float:
        nonlocal calls_via_wrapper
        calls_via_wrapper += 1
        return f(x)

    brent_root(counted_wrapper, 0.0, 2.0, tol=1e-4, max_iter=100)

    calls_via_raw = 0

    def counted_raw(x: float) -> float:
        nonlocal calls_via_raw
        calls_via_raw += 1
        return f(x)

    brentq(counted_raw, 0.0, 2.0, xtol=1e-4, maxiter=100)

    assert calls_via_wrapper == calls_via_raw


def test_brent_root_non_bracketing_still_names_both_endpoint_values() -> None:
    # The re-raised message must still report f(a) and f(b), even though they are no
    # longer pre-evaluated on the happy path (only re-evaluated once bracketing fails).
    with pytest.raises(ValueError, match=r"f\(-1\.0\) = 2\.0 and f\(1\.0\) = 2\.0"):
        brent_root(lambda x: x**2 + 1.0, -1.0, 1.0)
