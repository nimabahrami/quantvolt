"""Unit tests for portfolio/valuation.py (Task 61, Req 13.2-13.6).

Covers MarketData.curve_for (hit, miss naming the commodity, defensive copy), the
mixed-book happy path (futures + forward + swap) against hand-composed values and the
individual pricers, the unpriced path for an unregistered instrument type (Req 13.3),
the caller-supplied pricer registry (Req 13.4), propagation of pricing data errors,
determinism and input immutability (Req 13.6), and direct consumption of the produced
PricedPositions by risk.aggregation.aggregate_delta (Req 13.5).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import date

import pytest

from quantvolt.exceptions import ExpiredContractError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import ForwardContract, FuturesContract, SwapContract
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.portfolio.model import Portfolio, Position, PricedPosition
from quantvolt.portfolio.valuation import (
    DEFAULT_PRICERS,
    MarketData,
    PortfolioValuation,
    value_portfolio,
)
from quantvolt.pricing.futures import price_futures
from quantvolt.pricing.swap import price_swap
from quantvolt.risk.aggregation import aggregate_delta
from quantvolt.testing import assert_input_unchanged

TTF = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
POWER = CommodityConfig("DE_POWER", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh"))

JAN = DeliveryPeriod(2026, 1)  # settles 2026-01-31
FEB = DeliveryPeriod(2026, 2)  # settles 2026-02-28

VALUATION_DATE = date(2025, 12, 15)
JAN_DF = 0.99  # stored exactly at the 2026-01-31 tenor
FEB_DF = 0.98  # stored exactly at the 2026-02-28 tenor
TTF_JAN, TTF_FEB = 35.0, 36.0
POWER_JAN = 90.0

FUTURES = FuturesContract(TTF, JAN, contract_price=30.0, notional=100.0)
FORWARD = ForwardContract(POWER, JAN, contract_price=80.0, notional=50.0, counterparty="ACME")
SWAP = SwapContract(
    TTF,
    fixed_rate=32.0,
    floating_index="TTF_DA",
    notional=200.0,
    schedule=DeliverySchedule((JAN, FEB)),
)

# Hand-computed per-position values (discount factors hit stored tenors exactly):
FUTURES_NPV = JAN_DF * (TTF_JAN - 30.0) * 100.0  # 495.0
FUTURES_DELTA = JAN_DF * 100.0  # 99.0
FORWARD_NPV = JAN_DF * (POWER_JAN - 80.0) * 50.0  # 495.0
FORWARD_DELTA = JAN_DF * 50.0  # 49.5
SWAP_NPV = JAN_DF * (TTF_JAN - 32.0) * 200.0 + FEB_DF * (TTF_FEB - 32.0) * 200.0  # 1378.0
SWAP_DELTA_JAN = JAN_DF * 200.0  # 198.0
SWAP_DELTA_FEB = FEB_DF * 200.0  # 196.0


@dataclass(frozen=True, slots=True)
class _UnregisteredOption:
    """An instrument type no built-in pricer knows about (Req 13.3 / 13.4)."""

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    strike: float


DUMMY = _UnregisteredOption(TTF, JAN, strike=40.0)


def make_ttf_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=TTF,
        market_date=VALUATION_DATE,
        nodes=(
            CurveNode(JAN, TTF_JAN, "observed"),
            CurveNode(FEB, TTF_FEB, "observed"),
        ),
    )


def make_power_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=POWER,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JAN, POWER_JAN, "observed"),),
    )


def make_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=date(2025, 12, 1),
        tenors=(date(2026, 1, 31), date(2026, 2, 28)),
        factors=(JAN_DF, FEB_DF),
    )


def make_market_data() -> MarketData:
    return MarketData(
        forward_curves={"TTF": make_ttf_curve(), "DE_POWER": make_power_curve()},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
    )


def make_mixed_portfolio() -> Portfolio:
    return Portfolio(
        positions=(
            Position(FUTURES, position_id="POS-FUT"),
            Position(FORWARD, position_id="POS-FWD"),
            Position(SWAP, position_id="POS-SWP"),
        ),
        name="mixed-book",
    )


class TestMarketData:
    def test_curve_for_returns_matching_curve(self) -> None:
        market_data = make_market_data()
        assert market_data.curve_for("TTF") == make_ttf_curve()
        assert market_data.curve_for("DE_POWER") == make_power_curve()

    def test_curve_for_missing_commodity_names_it_and_lists_available(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            make_market_data().curve_for("NBP")
        message = str(excinfo.value)
        assert "'NBP'" in message
        assert "'TTF'" in message
        assert "'DE_POWER'" in message

    def test_curve_for_with_no_curves_at_all(self) -> None:
        market_data = MarketData(
            forward_curves={},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
        )
        with pytest.raises(ValidationError, match="none"):
            market_data.curve_for("TTF")

    def test_forward_curves_defensively_copied(self) -> None:
        caller_curves = {"TTF": make_ttf_curve()}
        market_data = MarketData(
            forward_curves=caller_curves,
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
        )
        assert market_data.forward_curves is not caller_curves

        del caller_curves["TTF"]
        assert market_data.curve_for("TTF") == make_ttf_curve()

    def test_is_frozen(self) -> None:
        market_data = make_market_data()
        with pytest.raises(dataclasses.FrozenInstanceError):
            market_data.valuation_date = date(2026, 1, 1)  # type: ignore[misc]


class TestMixedBookValuation:
    def test_total_npv_matches_hand_composed_sum(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        assert valuation.total_npv == pytest.approx(FUTURES_NPV + FORWARD_NPV + SWAP_NPV)
        assert valuation.total_npv == pytest.approx(2368.0)

    def test_total_npv_equals_sum_of_individually_priced_npvs(self) -> None:
        market_data = make_market_data()
        futures_npv = price_futures(
            FUTURES, make_ttf_curve(), VALUATION_DATE, make_discount_curve()
        ).npv
        forward_npv = price_futures(
            FORWARD, make_power_curve(), VALUATION_DATE, make_discount_curve()
        ).npv
        swap_npv = price_swap(SWAP, make_ttf_curve(), make_discount_curve()).npv

        valuation = value_portfolio(make_mixed_portfolio(), market_data)
        assert valuation.total_npv == pytest.approx(futures_npv + forward_npv + swap_npv)

    def test_priced_results_in_input_order_preserving_positions(self) -> None:
        portfolio = make_mixed_portfolio()
        valuation = value_portfolio(portfolio, make_market_data())
        assert valuation.unpriced == ()
        assert len(valuation.priced) == 3
        for priced, original in zip(valuation.priced, portfolio.positions, strict=True):
            assert priced.position is original

    def test_futures_position_npv_and_delta(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        futures_result = valuation.priced[0]
        assert futures_result.npv == pytest.approx(FUTURES_NPV)
        assert futures_result.delta == pytest.approx({("TTF", JAN): FUTURES_DELTA})

    def test_forward_position_npv_and_delta(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        forward_result = valuation.priced[1]
        assert forward_result.npv == pytest.approx(FORWARD_NPV)
        assert forward_result.delta == pytest.approx({("DE_POWER", JAN): FORWARD_DELTA})

    def test_swap_position_npv_and_per_period_delta(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        swap_result = valuation.priced[2]
        assert swap_result.npv == pytest.approx(SWAP_NPV)
        assert swap_result.delta == pytest.approx(
            {("TTF", JAN): SWAP_DELTA_JAN, ("TTF", FEB): SWAP_DELTA_FEB}
        )

    def test_futures_and_forward_reference_prices_are_the_curve_forward(self) -> None:
        """Regression: PricedPosition.reference_prices feeds RiskEngine.apply_scenario's
        `delta * reference_price * shock` scaling (fix for the gas-crisis stress bug)."""
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        futures_result, forward_result, swap_result = valuation.priced
        assert futures_result.reference_prices == pytest.approx({("TTF", JAN): TTF_JAN})
        assert forward_result.reference_prices == pytest.approx({("DE_POWER", JAN): POWER_JAN})
        assert swap_result.reference_prices == pytest.approx(
            {("TTF", JAN): TTF_JAN, ("TTF", FEB): TTF_FEB}
        )
        # Every delta key has a matching reference_prices key.
        for priced in valuation.priced:
            assert set(priced.delta) == set(priced.reference_prices)

    def test_empty_portfolio_yields_zero_and_empty_result(self) -> None:
        valuation = value_portfolio(Portfolio(positions=()), make_market_data())
        assert valuation == PortfolioValuation(total_npv=0.0, priced=(), unpriced=())


class TestUnpricedPath:
    """Req 13.3: unregistered instrument types are collected, never raised on."""

    def test_unregistered_type_lands_in_unpriced_and_rest_still_valued(self) -> None:
        dummy_position = Position(DUMMY, position_id="POS-OPT")  # type: ignore[arg-type]
        portfolio = Portfolio(
            positions=(
                Position(FUTURES),
                dummy_position,  # in the middle: the remaining positions still price
                Position(SWAP),
            )
        )
        valuation = value_portfolio(portfolio, make_market_data())
        assert valuation.unpriced == (dummy_position,)
        assert valuation.unpriced[0] is dummy_position
        assert len(valuation.priced) == 2
        assert valuation.total_npv == pytest.approx(FUTURES_NPV + SWAP_NPV)

    def test_all_unpriced_book_totals_zero(self) -> None:
        portfolio = Portfolio(positions=(Position(DUMMY),))  # type: ignore[arg-type]
        valuation = value_portfolio(portfolio, make_market_data())
        assert valuation.total_npv == 0.0
        assert valuation.priced == ()
        assert len(valuation.unpriced) == 1


class TestCallerRegistry:
    """Req 13.4: extend the pricer registry per call, without editing the module."""

    def test_caller_registered_pricer_prices_the_new_type(self) -> None:
        def price_option(position: Position, market_data: MarketData) -> PricedPosition:
            instrument = position.instrument
            assert isinstance(instrument, _UnregisteredOption)
            forward = market_data.curve_for(instrument.commodity.commodity_id)
            intrinsic = max(forward.price_at(instrument.delivery_period) - instrument.strike, 0.0)
            return PricedPosition(
                position=position,
                npv=intrinsic,
                delta={(instrument.commodity.commodity_id, instrument.delivery_period): 0.5},
            )

        dummy_position = Position(DUMMY)  # type: ignore[arg-type]
        portfolio = Portfolio(positions=(Position(FUTURES), dummy_position))
        valuation = value_portfolio(
            portfolio, make_market_data(), pricers={_UnregisteredOption: price_option}
        )
        assert valuation.unpriced == ()
        assert len(valuation.priced) == 2
        assert valuation.priced[1].position is dummy_position
        assert valuation.priced[1].npv == pytest.approx(0.0)  # max(35 - 40, 0)
        assert valuation.priced[1].delta == {("TTF", JAN): 0.5}
        assert valuation.total_npv == pytest.approx(FUTURES_NPV + 0.0)

    def test_caller_entry_overrides_default_pricer(self) -> None:
        def zero_pricer(position: Position, market_data: MarketData) -> PricedPosition:
            return PricedPosition(position=position, npv=0.0)

        valuation = value_portfolio(
            make_mixed_portfolio(), make_market_data(), pricers={FuturesContract: zero_pricer}
        )
        assert valuation.priced[0].npv == 0.0  # caller wins over price_futures
        assert valuation.priced[1].npv == pytest.approx(FORWARD_NPV)  # defaults untouched
        assert valuation.total_npv == pytest.approx(FORWARD_NPV + SWAP_NPV)

    def test_default_pricers_are_not_mutated_by_caller_registration(self) -> None:
        snapshot = dict(DEFAULT_PRICERS)
        portfolio = Portfolio(positions=(Position(DUMMY),))  # type: ignore[arg-type]

        def price_option(position: Position, market_data: MarketData) -> PricedPosition:
            return PricedPosition(position=position, npv=7.5)

        value_portfolio(portfolio, make_market_data(), pricers={_UnregisteredOption: price_option})
        assert snapshot == DEFAULT_PRICERS
        assert _UnregisteredOption not in DEFAULT_PRICERS


class TestPricingErrorPropagation:
    """Data errors on a priceable type propagate; only registry misses go to unpriced."""

    def test_missing_forward_curve_raises_naming_the_commodity(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},  # no DE_POWER curve
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
        )
        with pytest.raises(ValidationError, match="'DE_POWER'"):
            value_portfolio(make_mixed_portfolio(), market_data)

    def test_expired_contract_error_propagates(self) -> None:
        expired = FuturesContract(TTF, DeliveryPeriod(2025, 6), contract_price=30.0, notional=100.0)
        portfolio = Portfolio(positions=(Position(expired),))
        with pytest.raises(ExpiredContractError):
            value_portfolio(portfolio, make_market_data())


class TestDeterminismAndImmutability:
    """Req 13.6."""

    def test_identical_inputs_produce_identical_results(self) -> None:
        portfolio, market_data = make_mixed_portfolio(), make_market_data()
        first = value_portfolio(portfolio, market_data)
        second = value_portfolio(portfolio, market_data)
        assert first == second

    def test_inputs_are_not_mutated(self) -> None:
        valuation = assert_input_unchanged(
            value_portfolio, make_mixed_portfolio(), make_market_data()
        )
        assert valuation.total_npv == pytest.approx(FUTURES_NPV + FORWARD_NPV + SWAP_NPV)


class TestRiskWiring:
    """Req 13.5: PricedPositions feed risk.aggregation.aggregate_delta unchanged."""

    def test_aggregate_delta_consumes_priced_positions_directly(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        matrix = aggregate_delta(list(valuation.priced))

        assert matrix.commodities == ("DE_POWER", "TTF")
        assert matrix.periods == (JAN, FEB)
        assert matrix.delta_at("TTF", JAN) == pytest.approx(FUTURES_DELTA + SWAP_DELTA_JAN)
        assert matrix.delta_at("TTF", FEB) == pytest.approx(SWAP_DELTA_FEB)
        assert matrix.delta_at("DE_POWER", JAN) == pytest.approx(FORWARD_DELTA)
        assert matrix.delta_at("DE_POWER", FEB) == 0.0  # never held -> zero exposure

    def test_matrix_matches_sum_of_per_position_deltas(self) -> None:
        valuation = value_portfolio(make_mixed_portfolio(), make_market_data())
        matrix = aggregate_delta(list(valuation.priced))

        expected: dict[tuple[str, DeliveryPeriod], float] = {}
        for priced in valuation.priced:
            for key, exposure in priced.delta.items():
                expected[key] = expected.get(key, 0.0) + exposure
        for (commodity_id, period), net in expected.items():
            assert matrix.delta_at(commodity_id, period) == pytest.approx(net)
