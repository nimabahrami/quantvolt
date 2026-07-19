"""Unit tests for CurveNode / ForwardCurve (Task 5): lookup, serialisation round-trip,
tolerance equality, construction validation, negative prices and input immutability."""

from __future__ import annotations

import copy
from datetime import date

import pytest

from quantvolt.exceptions import MissingTenorError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.testing import assert_input_unchanged

MARKET_DATE = date(2025, 1, 1)
COMMODITY = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))

JAN = DeliveryPeriod(2025, 1)
FEB = DeliveryPeriod(2025, 2)
MAR = DeliveryPeriod(2025, 3)


def make_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=COMMODITY,
        market_date=MARKET_DATE,
        nodes=(
            CurveNode(JAN, 30.0, "observed"),
            CurveNode(FEB, 28.5, "interpolated"),
            CurveNode(MAR, 27.0, "observed"),
        ),
    )


# --- price_at ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("period", "expected"),
    [(JAN, 30.0), (FEB, 28.5), (MAR, 27.0)],
)
def test_price_at_returns_node_price(period: DeliveryPeriod, expected: float) -> None:
    assert make_curve().price_at(period) == expected


def test_price_at_missing_period_raises_naming_period_and_range() -> None:
    with pytest.raises(MissingTenorError) as excinfo:
        make_curve().price_at(DeliveryPeriod(2025, 6))
    message = str(excinfo.value)
    assert "month=6" in message  # names the requested period
    assert "month=1" in message and "month=3" in message  # covered range endpoints


def test_price_at_does_not_interpolate_between_nodes() -> None:
    # A period strictly inside the covered range but with no node still misses.
    curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=MARKET_DATE,
        nodes=(CurveNode(JAN, 30.0, "observed"), CurveNode(MAR, 27.0, "observed")),
    )
    with pytest.raises(MissingTenorError):
        curve.price_at(FEB)


# --- serialisation round-trip (Property 5) ----------------------------------


def test_to_dict_from_dict_round_trip_is_equal() -> None:
    curve = make_curve()
    assert ForwardCurve.from_dict(curve.to_dict()) == curve


def test_to_dict_shape_is_json_friendly() -> None:
    data = make_curve().to_dict()
    assert data["market_date"] == "2025-01-01"
    assert data["commodity"] == {
        "commodity_id": "TTF",
        "price_unit": "EUR/MWh",
        "hub": {"hub_id": "TTF", "exchange": "ICE_ENDEX", "price_unit": "EUR/MWh"},
    }
    assert data["nodes"][0] == {
        "period": {"year": 2025, "month": 1},
        "price": 30.0,
        "status": "observed",
    }


def test_from_dict_rejects_stale_mbtu_price_unit() -> None:
    # Persisted curves from before the gas-unit-conventions fix carried "EUR/MBtu";
    # from_dict must reject them at the boundary, not deserialise them silently.
    data = make_curve().to_dict()
    data["commodity"]["price_unit"] = "EUR/MBtu"
    data["commodity"]["hub"]["price_unit"] = "EUR/MBtu"
    with pytest.raises(ValidationError):
        ForwardCurve.from_dict(data)


def test_from_dict_reconstructs_exact_objects() -> None:
    curve = ForwardCurve.from_dict(make_curve().to_dict())
    assert curve.commodity == COMMODITY
    assert curve.commodity.hub == COMMODITY.hub
    assert curve.market_date == MARKET_DATE
    assert curve.nodes[1] == CurveNode(FEB, 28.5, "interpolated")


# --- tolerance equality (Property 1) ----------------------------------------


def _curve_with_first_price(price: float) -> ForwardCurve:
    return ForwardCurve(
        commodity=COMMODITY,
        market_date=MARKET_DATE,
        nodes=(CurveNode(JAN, price, "observed"), CurveNode(FEB, 28.5, "interpolated")),
    )


def test_prices_within_tolerance_are_equal() -> None:
    a = _curve_with_first_price(30.0)
    b = _curve_with_first_price(30.0 + 1e-11)
    assert a == b
    assert hash(a) == hash(b)  # equal curves must share a hash


def test_prices_beyond_tolerance_are_not_equal() -> None:
    a = _curve_with_first_price(30.0)
    b = _curve_with_first_price(30.0 + 1e-9)
    assert a != b


def test_different_commodity_is_not_equal() -> None:
    other = CommodityConfig("NBP", "GBp/therm", Hub("NBP", "ICE_ENDEX", "GBp/therm"))
    a = make_curve()
    b = ForwardCurve(commodity=other, market_date=MARKET_DATE, nodes=a.nodes)
    assert a != b


def test_different_market_date_is_not_equal() -> None:
    a = make_curve()
    b = ForwardCurve(commodity=COMMODITY, market_date=date(2025, 1, 2), nodes=a.nodes)
    assert a != b


def test_different_status_is_not_equal() -> None:
    a = _curve_with_first_price(30.0)
    b = ForwardCurve(
        commodity=COMMODITY,
        market_date=MARKET_DATE,
        nodes=(CurveNode(JAN, 30.0, "interpolated"), CurveNode(FEB, 28.5, "interpolated")),
    )
    assert a != b


def test_different_node_count_is_not_equal() -> None:
    a = make_curve()
    b = _curve_with_first_price(30.0)  # only two nodes
    assert a != b


def test_equality_with_non_curve_is_false() -> None:
    assert make_curve() != object()
    assert (make_curve() == 42) is False


# --- construction validation ------------------------------------------------


def test_empty_nodes_rejected() -> None:
    with pytest.raises(ValidationError, match="nodes"):
        ForwardCurve(commodity=COMMODITY, market_date=MARKET_DATE, nodes=())


def test_non_increasing_periods_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        ForwardCurve(
            commodity=COMMODITY,
            market_date=MARKET_DATE,
            nodes=(CurveNode(FEB, 28.5, "observed"), CurveNode(JAN, 30.0, "observed")),
        )


def test_duplicate_periods_rejected() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        ForwardCurve(
            commodity=COMMODITY,
            market_date=MARKET_DATE,
            nodes=(CurveNode(JAN, 30.0, "observed"), CurveNode(JAN, 29.0, "observed")),
        )


def test_invalid_status_rejected() -> None:
    with pytest.raises(ValidationError, match="status"):
        ForwardCurve(
            commodity=COMMODITY,
            market_date=MARKET_DATE,
            nodes=(CurveNode(JAN, 30.0, "guessed"),),  # type: ignore[arg-type]
        )


# --- negative prices are real in power markets ------------------------------


def test_negative_price_is_accepted() -> None:
    curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=MARKET_DATE,
        nodes=(CurveNode(JAN, -15.0, "observed"),),
    )
    assert curve.price_at(JAN) == -15.0


# --- immutability -----------------------------------------------------------


def test_from_dict_does_not_mutate_input() -> None:
    data = make_curve().to_dict()
    snapshot = copy.deepcopy(data)
    curve = assert_input_unchanged(ForwardCurve.from_dict, data)
    assert isinstance(curve, ForwardCurve)
    assert data == snapshot


def test_price_at_does_not_mutate_inputs() -> None:
    curve = make_curve()
    price = assert_input_unchanged(curve.price_at, JAN)
    assert price == 30.0


def test_instance_is_frozen() -> None:
    curve = make_curve()
    with pytest.raises(AttributeError):
        curve.nodes = ()  # type: ignore[misc]
