"""Unit tests for curves/arbitrage.py (Task 18, Req 1.4, Property 3).

The checker flags a *negative time spread* (far below near) between consecutive
delivery periods that the cost of carry cannot explain:

    price(p_late) < price(p_early) - storage_cost * months_between - EPS

Contango and inversions within the carry band are clean; a non-finite price makes
the spreads unattributable and raises ``ArbitrageError``.
"""

from __future__ import annotations

import math
from datetime import date

import pytest

from quantvolt.curves.arbitrage import ArbitrageChecker, ArbitrageWarning
from quantvolt.exceptions import ArbitrageError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod

MARKET_DATE = date(2025, 1, 1)
COMMODITY = CommodityConfig("TTF", "EUR/MBtu", Hub("TTF", "ICE_ENDEX", "EUR/MBtu"))

JAN = DeliveryPeriod(2025, 1)
FEB = DeliveryPeriod(2025, 2)
MAR = DeliveryPeriod(2025, 3)
APR = DeliveryPeriod(2025, 4)


def _curve(prices: dict[DeliveryPeriod, float]) -> ForwardCurve:
    nodes = tuple(CurveNode(period, price, "observed") for period, price in sorted(prices.items()))
    return ForwardCurve(commodity=COMMODITY, market_date=MARKET_DATE, nodes=nodes)


def test_clean_contango_curve_has_no_warnings() -> None:
    curve = _curve({JAN: 20.0, FEB: 21.0, MAR: 22.5, APR: 23.0})
    assert ArbitrageChecker().check(curve) == []


def test_flat_curve_has_no_warnings() -> None:
    curve = _curve({JAN: 25.0, FEB: 25.0, MAR: 25.0})
    assert ArbitrageChecker().check(curve) == []


def test_inverted_curve_warns_naming_offending_periods() -> None:
    # Feb->Mar drops 30 -> 22 with zero storage cost: an unexplained negative spread.
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 22.0, APR: 22.0})
    warnings = ArbitrageChecker().check(curve, storage_cost=0.0)
    assert len(warnings) == 1
    warning = warnings[0]
    assert isinstance(warning, ArbitrageWarning)
    assert warning.periods == (FEB, MAR)
    assert "22" in warning.message and "30" in warning.message


def test_storage_cost_explains_a_mild_inversion() -> None:
    # Feb->Mar declines by 1.5 over one month; a 2.0/month carry covers it -> clean.
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 28.5})
    assert ArbitrageChecker().check(curve, storage_cost=2.0) == []


def test_storage_cost_insufficient_to_explain_large_inversion() -> None:
    # Decline of 5.0 over one month exceeds a 2.0/month carry -> still flagged.
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 25.0})
    warnings = ArbitrageChecker().check(curve, storage_cost=2.0)
    assert len(warnings) == 1
    assert warnings[0].periods == (FEB, MAR)


def test_multiple_offending_pairs_each_warn() -> None:
    curve = _curve({JAN: 30.0, FEB: 25.0, MAR: 26.0, APR: 20.0})
    warnings = ArbitrageChecker().check(curve, storage_cost=0.0)
    offending = {w.periods for w in warnings}
    assert offending == {(JAN, FEB), (MAR, APR)}


def test_single_node_curve_is_clean() -> None:
    curve = _curve({JAN: 42.0})
    assert ArbitrageChecker().check(curve) == []


def test_non_finite_price_is_unattributable_and_raises() -> None:
    curve = _curve({JAN: 30.0, FEB: math.nan, MAR: 22.0})
    with pytest.raises(ArbitrageError) as excinfo:
        ArbitrageChecker().check(curve)
    assert "cannot be attributed" in str(excinfo.value)
    assert repr(FEB) in str(excinfo.value)


# --- new keyword-only eps parameter ------------------------------------------


def test_eps_default_matches_hardcoded_1e_minus_9() -> None:
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 22.0})
    baseline = ArbitrageChecker().check(curve)
    explicit = ArbitrageChecker().check(curve, eps=1e-9)
    assert explicit == baseline


def test_eps_widened_absorbs_a_tiny_spread_below_the_carry_bound() -> None:
    # Spread sits exactly 5e-7 below the carry bound: flagged at the default 1e-9
    # tolerance, clean once eps is widened past it.
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 30.0 - 5e-7})
    assert len(ArbitrageChecker().check(curve)) == 1
    assert ArbitrageChecker().check(curve, eps=1e-6) == []


def test_eps_must_be_positive() -> None:
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 22.0})
    with pytest.raises(ValidationError, match="eps"):
        ArbitrageChecker().check(curve, eps=0.0)


# --- storage_cost must be non-negative (mirrors pricing/spreads.py:476) ------


def test_negative_storage_cost_raises() -> None:
    """Regression: storage_cost is documented non-negative but was never
    validated, so a negative value (e.g. -5) could produce false arbitrage
    warnings on an otherwise-clean flat curve (``slack = 0 + storage_cost *
    months < 0`` for any negative storage_cost and positive month gap) --
    reachable via ``CurveBuilder.build`` too, which forwards ``storage_cost``
    unchanged to this checker."""
    curve = _curve({JAN: 30.0, FEB: 30.0, MAR: 30.0})
    with pytest.raises(ValidationError, match="storage_cost"):
        ArbitrageChecker().check(curve, storage_cost=-5.0)
