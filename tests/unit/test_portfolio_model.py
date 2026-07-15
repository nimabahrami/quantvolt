"""Unit tests for portfolio/model.py (Task 60, Req 13.1): the portfolio value objects.

Covers Position construction over every Instrument variant, Portfolio iteration order /
counting / immutability, PricedPosition with and without Greeks, rejection of
non-finite npv, and the defensive copy of the caller's delta mapping.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.greeks import Greeks
from quantvolt.models.instruments import ForwardContract, FuturesContract, SwapContract
from quantvolt.models.power_hedge import (
    PowerHedgeContract,
    PowerHedgePosition,
    PowerHedgeType,
)
from quantvolt.models.ppa import PpaContract, PpaVolumeBasis
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.portfolio.model import Portfolio, Position, PricedPosition

_COMMODITY = CommodityConfig("TTF", "EUR/MBtu", Hub("TTF", "ICE_ENDEX", "EUR/MBtu"))
_PERIOD = DeliveryPeriod(2026, 1)
_SCHEDULE = DeliverySchedule((DeliveryPeriod(2026, 1), DeliveryPeriod(2026, 2)))

_FUTURES = FuturesContract(_COMMODITY, _PERIOD, contract_price=30.0, notional=100.0)
_FORWARD = ForwardContract(_COMMODITY, _PERIOD, contract_price=28.0, notional=50.0)
_SWAP = SwapContract(_COMMODITY, 25.0, "TTF_DA", notional=200.0, schedule=_SCHEDULE)
_UTC_START = datetime(2026, 1, 1, tzinfo=UTC)
_PPA = PpaContract(
    "ppa",
    "DE-LU",
    70.0,
    _UTC_START,
    _UTC_START + timedelta(days=1),
    PpaVolumeBasis.BASELOAD,
)
_HEDGE = PowerHedgeContract(
    "floor",
    PowerHedgeType.FLOOR,
    PowerHedgePosition.LONG,
    _UTC_START,
    _UTC_START + timedelta(days=1),
    1.0,
    60.0,
)


class TestPosition:
    @pytest.mark.parametrize("instrument", [_FUTURES, _FORWARD, _SWAP, _PPA, _HEDGE])
    def test_construction_with_each_instrument_type(
        self,
        instrument: (
            FuturesContract
            | ForwardContract
            | SwapContract
            | PpaContract
            | PowerHedgeContract
        ),
    ) -> None:
        position = Position(instrument=instrument)
        assert position.instrument is instrument
        assert position.position_id is None
        assert position.tags == ()

    def test_identity_and_tags(self) -> None:
        position = Position(_FUTURES, position_id="POS-1", tags=("hedge", "desk-A"))
        assert position.position_id == "POS-1"
        assert position.tags == ("hedge", "desk-A")

    def test_is_frozen(self) -> None:
        position = Position(_FUTURES)
        with pytest.raises(dataclasses.FrozenInstanceError):
            position.position_id = "X"  # type: ignore[misc]


class TestPortfolio:
    def test_iteration_preserves_construction_order(self) -> None:
        first, second, third = Position(_FUTURES), Position(_FORWARD), Position(_SWAP)
        portfolio = Portfolio(positions=(first, second, third))
        assert list(portfolio) == [first, second, third]

    def test_len_counts_positions(self) -> None:
        portfolio = Portfolio(positions=(Position(_FUTURES), Position(_SWAP)))
        assert len(portfolio) == 2

    def test_empty_portfolio(self) -> None:
        portfolio = Portfolio(positions=())
        assert len(portfolio) == 0
        assert list(portfolio) == []

    def test_iteration_does_not_mutate(self) -> None:
        positions = (Position(_FUTURES), Position(_FORWARD))
        portfolio = Portfolio(positions=positions)
        assert list(portfolio) == list(portfolio)  # re-iterable, not consumed
        assert portfolio.positions == positions
        assert len(portfolio) == 2

    def test_is_frozen(self) -> None:
        portfolio = Portfolio(positions=(Position(_FUTURES),), name="book")
        with pytest.raises(dataclasses.FrozenInstanceError):
            portfolio.positions = ()  # type: ignore[misc]
        with pytest.raises(dataclasses.FrozenInstanceError):
            portfolio.name = "other"  # type: ignore[misc]

    def test_name_defaults_to_none(self) -> None:
        assert Portfolio(positions=()).name is None


class TestPricedPosition:
    def test_without_greeks(self) -> None:
        priced = PricedPosition(position=Position(_FUTURES), npv=1234.5)
        assert priced.npv == 1234.5
        assert priced.greeks is None
        assert priced.delta == {}

    def test_with_greeks_and_delta(self) -> None:
        greeks = Greeks(delta=0.6, gamma=0.01, vega=0.2, theta=-0.05, rho=0.001)
        delta = {("TTF", _PERIOD): 100.0}
        priced = PricedPosition(Position(_FORWARD), npv=-42.0, delta=delta, greeks=greeks)
        assert priced.greeks == greeks
        assert priced.delta == {("TTF", _PERIOD): 100.0}
        assert priced.npv == -42.0  # negative NPV is a valid valuation outcome

    @pytest.mark.parametrize("npv", [math.nan, math.inf, -math.inf])
    def test_non_finite_npv_rejected(self, npv: float) -> None:
        with pytest.raises(ValidationError, match="npv"):
            PricedPosition(position=Position(_FUTURES), npv=npv)

    def test_delta_is_defensively_copied(self) -> None:
        caller_delta = {("TTF", _PERIOD): 100.0}
        priced = PricedPosition(Position(_FUTURES), npv=10.0, delta=caller_delta)
        assert priced.delta is not caller_delta

        caller_delta[("TTF", _PERIOD)] = -999.0
        caller_delta[("TTF", DeliveryPeriod(2026, 2))] = 55.0
        assert priced.delta == {("TTF", _PERIOD): 100.0}

    def test_default_delta_not_shared_between_instances(self) -> None:
        first = PricedPosition(Position(_FUTURES), npv=1.0)
        second = PricedPosition(Position(_SWAP), npv=2.0)
        assert first.delta is not second.delta

    def test_reference_prices_defaults_to_empty_dict(self) -> None:
        priced = PricedPosition(Position(_FUTURES), npv=1.0)
        assert priced.reference_prices == {}

    def test_reference_prices_is_defensively_copied(self) -> None:
        caller_reference_prices = {("TTF", _PERIOD): 40.0}
        priced = PricedPosition(
            Position(_FUTURES), npv=10.0, reference_prices=caller_reference_prices
        )
        assert priced.reference_prices is not caller_reference_prices

        caller_reference_prices[("TTF", _PERIOD)] = -999.0
        caller_reference_prices[("TTF", DeliveryPeriod(2026, 2))] = 55.0
        assert priced.reference_prices == {("TTF", _PERIOD): 40.0}

    def test_default_reference_prices_not_shared_between_instances(self) -> None:
        first = PricedPosition(Position(_FUTURES), npv=1.0)
        second = PricedPosition(Position(_SWAP), npv=2.0)
        assert first.reference_prices is not second.reference_prices

    def test_is_frozen(self) -> None:
        priced = PricedPosition(Position(_FUTURES), npv=1.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            priced.npv = 2.0  # type: ignore[misc]
