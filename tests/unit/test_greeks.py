"""Unit tests for the shared ``Greeks`` value object (Task 9)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from quantvolt.models.greeks import Greeks


def _sample() -> Greeks:
    return Greeks(delta=0.5, gamma=0.1, vega=1.2, theta=-0.3, rho=0.4)


def test_construction_and_field_access() -> None:
    g = _sample()
    assert g.delta == 0.5
    assert g.gamma == 0.1
    assert g.vega == 1.2
    assert g.theta == -0.3
    assert g.rho == 0.4


def test_equality_is_value_based() -> None:
    assert _sample() == _sample()
    assert _sample() != Greeks(delta=0.5, gamma=0.1, vega=1.2, theta=-0.3, rho=0.0)


def test_add_is_elementwise() -> None:
    a = Greeks(delta=1.0, gamma=2.0, vega=3.0, theta=4.0, rho=5.0)
    b = Greeks(delta=0.5, gamma=0.5, vega=0.5, theta=0.5, rho=0.5)
    assert a + b == Greeks(delta=1.5, gamma=2.5, vega=3.5, theta=4.5, rho=5.5)


def test_add_is_commutative() -> None:
    a = _sample()
    b = Greeks(delta=-1.0, gamma=2.0, vega=-3.0, theta=0.25, rho=7.0)
    assert a + b == b + a


def test_scale_is_elementwise() -> None:
    g = Greeks(delta=1.0, gamma=2.0, vega=3.0, theta=4.0, rho=5.0)
    assert g.scale(2.0) == Greeks(delta=2.0, gamma=4.0, vega=6.0, theta=8.0, rho=10.0)


def test_scale_by_zero_yields_zero() -> None:
    assert _sample().scale(0.0) == Greeks.zero()


def test_zero_is_all_zeros() -> None:
    assert Greeks.zero() == Greeks(delta=0.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)


def test_zero_is_additive_identity() -> None:
    g = _sample()
    assert g + Greeks.zero() == g
    assert Greeks.zero() + g == g


def test_zero_is_sum_start_value() -> None:
    parts = [
        Greeks(delta=1.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0),
        Greeks(delta=2.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0),
        Greeks(delta=3.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0),
    ]
    aggregate = sum(parts, Greeks.zero())
    assert aggregate == Greeks(delta=6.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)


def test_frozen_assignment_raises() -> None:
    g = _sample()
    with pytest.raises(FrozenInstanceError):
        g.delta = 9.9  # type: ignore[misc]
