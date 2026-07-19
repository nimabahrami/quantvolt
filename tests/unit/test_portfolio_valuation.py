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

import numpy as np
import pytest

from quantvolt.exceptions import ExpiredContractError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    CachedAssetValuation,
    CapFloorStripContract,
    CapFloorType,
    ForwardContract,
    FuturesContract,
    OptionSide,
    OptionType,
    PlantConfig,
    SpreadOptionContract,
    SwapContract,
    TollingAgreement,
    ValuationSource,
    VanillaOptionContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.daycount import actual_365
from quantvolt.portfolio.model import Portfolio, Position, PricedPosition
from quantvolt.portfolio.valuation import (
    DEFAULT_PRICERS,
    MarketData,
    PortfolioValuation,
    value_portfolio,
)
from quantvolt.pricing.futures import price_futures
from quantvolt.pricing.spread_option import (
    SpreadOptionRequest,
    price_spark_spread_option,
    price_spread_option,
)
from quantvolt.pricing.swap import price_swap
from quantvolt.pricing.tolling import price_tolling_agreement
from quantvolt.pricing.vanilla import (
    CapFloorRequest,
    VanillaOptionRequest,
    price_cap_floor,
    price_vanilla_option,
)
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


# --- portfolio-native-pricers spec: MarketData vol_surfaces/correlations extension, and
# native vanilla/spread/tolling option pricers (Reqs 1-3, 7, 8, 14) ---

EUA = CommodityConfig("EUA", "EUR/tCO2", Hub("EUA", "EEX", "EUR/tCO2"))

TTF_SIGMA = 0.35
POWER_SIGMA = 0.40
EUA_SIGMA = 0.25


def make_ttf_vol_surface() -> VolatilitySurface:
    return VolatilitySurface(commodity=TTF, tenors=(VolatilityTenor(JAN, TTF_SIGMA),))


def make_power_vol_surface() -> VolatilitySurface:
    return VolatilitySurface(commodity=POWER, tenors=(VolatilityTenor(JAN, POWER_SIGMA),))


class TestMarketDataVolAndCorrelationExtension:
    """Requirement 1: additive vol_surfaces/correlations fields, defensively copied,
    with correlations validated strictly inside (-1, 1) at construction."""

    def test_defaults_are_empty(self) -> None:
        market_data = make_market_data()
        assert market_data.vol_surfaces == {}
        assert market_data.correlations == {}

    def test_vol_surfaces_defensively_copied(self) -> None:
        caller_surfaces = {"TTF": make_ttf_vol_surface()}
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces=caller_surfaces,
        )
        assert market_data.vol_surfaces is not caller_surfaces
        del caller_surfaces["TTF"]
        assert market_data.surface_for("TTF") == make_ttf_vol_surface()

    def test_correlations_defensively_copied(self) -> None:
        caller_correlations = {("TTF", "DE_POWER"): 0.5}
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            correlations=caller_correlations,
        )
        assert market_data.correlations is not caller_correlations
        del caller_correlations[("TTF", "DE_POWER")]
        assert market_data.correlation_for("TTF", "DE_POWER") == 0.5

    @pytest.mark.parametrize("rho", [1.0, -1.0, 1.5, -1.5, float("nan")])
    def test_out_of_range_correlation_rejected_naming_the_pair(self, rho: float) -> None:
        with pytest.raises(ValidationError, match=r"correlations\[\('TTF', 'DE_POWER'\)\]"):
            MarketData(
                forward_curves={"TTF": make_ttf_curve()},
                discount_curve=make_discount_curve(),
                valuation_date=VALUATION_DATE,
                correlations={("TTF", "DE_POWER"): rho},
            )

    def test_in_range_correlation_accepted(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            correlations={("TTF", "DE_POWER"): 0.999},
        )
        assert market_data.correlation_for("TTF", "DE_POWER") == 0.999

    def test_existing_call_sites_without_the_new_fields_still_work(self) -> None:
        # Requirement 1.4: additive with defaults.
        market_data = make_market_data()
        valuation = value_portfolio(make_mixed_portfolio(), market_data)
        assert valuation.total_npv == pytest.approx(FUTURES_NPV + FORWARD_NPV + SWAP_NPV)


class TestSurfaceForAccessor:
    """Requirement 2: fail-loud vol-surface accessor, mirroring curve_for's shape."""

    def test_hit_returns_the_registered_surface(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces={"TTF": make_ttf_vol_surface()},
        )
        assert market_data.surface_for("TTF") == make_ttf_vol_surface()

    def test_miss_names_the_commodity_and_lists_available(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces={"TTF": make_ttf_vol_surface()},
        )
        with pytest.raises(ValidationError) as excinfo:
            market_data.surface_for("DE_POWER")
        message = str(excinfo.value)
        assert "'DE_POWER'" in message
        assert "'TTF'" in message

    def test_miss_with_no_surfaces_at_all(self) -> None:
        market_data = make_market_data()
        with pytest.raises(ValidationError, match="none"):
            market_data.surface_for("TTF")


class TestCorrelationForAccessor:
    """Requirement 3: symmetric correlation lookup, a pure query (no re-validation)."""

    def test_forward_order_hit(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            correlations={("TTF", "DE_POWER"): 0.6},
        )
        assert market_data.correlation_for("TTF", "DE_POWER") == 0.6

    def test_reverse_order_hit_is_symmetric(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            correlations={("TTF", "DE_POWER"): 0.6},
        )
        assert market_data.correlation_for("DE_POWER", "TTF") == 0.6

    def test_missing_pair_names_it_and_lists_available(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            correlations={("TTF", "DE_POWER"): 0.6},
        )
        with pytest.raises(ValidationError) as excinfo:
            market_data.correlation_for("TTF", "EUA")
        message = str(excinfo.value)
        assert "'EUA'" in message
        assert "('TTF', 'DE_POWER')" in message


# --- Requirement 7 / Property 80: native vanilla-option pricer -------------------------

VANILLA_STRIKE = 34.0
VANILLA_NOTIONAL = 1_000.0
VANILLA_TTE = actual_365(VALUATION_DATE, JAN.last_day)


def make_vanilla_market_data() -> MarketData:
    return MarketData(
        forward_curves={"TTF": make_ttf_curve()},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
        vol_surfaces={"TTF": make_ttf_vol_surface()},
    )


def make_vanilla_option(side: OptionSide = OptionSide.LONG) -> VanillaOptionContract:
    return VanillaOptionContract(
        commodity=TTF,
        delivery_period=JAN,
        option_type=OptionType.CALL,
        strike=VANILLA_STRIKE,
        notional=VANILLA_NOTIONAL,
        side=side,
    )


def _expected_vanilla_result() -> object:
    return price_vanilla_option(
        VanillaOptionRequest(
            option_type="call",
            strike=VANILLA_STRIKE,
            notional=VANILLA_NOTIONAL,
            forward=TTF_JAN,
            sigma=TTF_SIGMA,
            time_to_expiry=VANILLA_TTE,
            discount_factor=JAN_DF,
        )
    )


class TestNativeVanillaOptionPricer:
    def test_long_npv_delta_greeks_and_reference_price_match_the_kernel(self) -> None:
        expected = _expected_vanilla_result()
        portfolio = Portfolio(positions=(Position(make_vanilla_option()),))
        valuation = value_portfolio(portfolio, make_vanilla_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(expected.premium)
        assert result.delta == pytest.approx({("TTF", JAN): expected.greeks.delta})
        assert result.greeks == expected.greeks
        assert result.reference_prices == pytest.approx({("TTF", JAN): TTF_JAN})

    def test_short_side_sign_flips_npv_delta_and_greeks(self) -> None:
        expected = _expected_vanilla_result()
        portfolio = Portfolio(positions=(Position(make_vanilla_option(OptionSide.SHORT)),))
        valuation = value_portfolio(portfolio, make_vanilla_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(-expected.premium)
        assert result.delta == pytest.approx({("TTF", JAN): -expected.greeks.delta})
        assert result.greeks == expected.greeks.scale(-1.0)

    def test_expiry_none_defaults_to_delivery_period_last_day(self) -> None:
        option = make_vanilla_option()
        assert option.expiry is None
        # time_to_expiry used above is computed from JAN.last_day; an explicit equal
        # expiry must reproduce the identical premium.
        explicit = VanillaOptionContract(
            commodity=TTF,
            delivery_period=JAN,
            option_type=OptionType.CALL,
            strike=VANILLA_STRIKE,
            notional=VANILLA_NOTIONAL,
            expiry=JAN.last_day,
        )
        market_data = make_vanilla_market_data()
        v1 = value_portfolio(Portfolio(positions=(Position(option),)), market_data)
        v2 = value_portfolio(Portfolio(positions=(Position(explicit),)), market_data)
        assert v1.priced[0].npv == v2.priced[0].npv

    def test_missing_vol_surface_raises_naming_the_commodity(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
        )
        portfolio = Portfolio(positions=(Position(make_vanilla_option()),))
        with pytest.raises(ValidationError, match="'TTF'"):
            value_portfolio(portfolio, market_data)

    def test_non_positive_forward_propagates_black76_domain_error(self) -> None:
        """Requirement 12: a non-positive forward is never clamped; the kernel's own
        ValidationError propagates unmodified."""
        negative_curve = ForwardCurve(
            commodity=TTF, market_date=VALUATION_DATE, nodes=(CurveNode(JAN, -5.0, "observed"),)
        )
        market_data = MarketData(
            forward_curves={"TTF": negative_curve},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces={"TTF": make_ttf_vol_surface()},
        )
        portfolio = Portfolio(positions=(Position(make_vanilla_option()),))
        with pytest.raises(ValidationError, match="forward"):
            value_portfolio(portfolio, market_data)

    def test_wrong_instrument_type_is_rejected_by_the_adapter_directly(self) -> None:
        from quantvolt.portfolio.valuation import _price_vanilla_option

        with pytest.raises(ValidationError, match="VanillaOptionContract"):
            _price_vanilla_option(Position(FUTURES), make_vanilla_market_data())


# --- Requirement 8 / Property 81: native spread-option pricer --------------------------

SPREAD_STRIKE = 50.0
SPREAD_NOTIONAL = 500.0
SPREAD_RHO = 0.5


def make_spread_market_data() -> MarketData:
    return MarketData(
        forward_curves={"TTF": make_ttf_curve(), "DE_POWER": make_power_curve()},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
        vol_surfaces={"TTF": make_ttf_vol_surface(), "DE_POWER": make_power_vol_surface()},
        correlations={("DE_POWER", "TTF"): SPREAD_RHO},
    )


def make_spread_option(
    leg2_weight: float = 1.0, side: OptionSide = OptionSide.LONG
) -> SpreadOptionContract:
    return SpreadOptionContract(
        commodity_1="DE_POWER",
        commodity_2="TTF",
        delivery_period=JAN,
        strike=SPREAD_STRIKE,
        notional=SPREAD_NOTIONAL,
        leg2_weight=leg2_weight,
        side=side,
    )


def _expected_spread_request() -> SpreadOptionRequest:
    return SpreadOptionRequest(
        forward1=POWER_JAN,
        forward2=TTF_JAN,
        strike=SPREAD_STRIKE,
        sigma1=POWER_SIGMA,
        sigma2=TTF_SIGMA,
        correlation=SPREAD_RHO,
        time_to_expiry=actual_365(VALUATION_DATE, JAN.last_day),
        discount_factor=JAN_DF,
        notional=SPREAD_NOTIONAL,
    )


class TestNativeSpreadOptionPricer:
    def test_plain_spread_npv_delta_and_reference_prices_match_the_kernel(self) -> None:
        expected = price_spread_option(_expected_spread_request())
        portfolio = Portfolio(positions=(Position(make_spread_option()),))
        valuation = value_portfolio(portfolio, make_spread_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(expected.premium)
        assert result.delta == pytest.approx(
            {("DE_POWER", JAN): expected.delta1, ("TTF", JAN): expected.delta2}
        )
        assert result.greeks is None
        assert result.reference_prices == pytest.approx(
            {("DE_POWER", JAN): POWER_JAN, ("TTF", JAN): TTF_JAN}
        )

    def test_short_side_sign_flips_npv_and_both_leg_deltas(self) -> None:
        expected = price_spread_option(_expected_spread_request())
        portfolio = Portfolio(positions=(Position(make_spread_option(side=OptionSide.SHORT)),))
        valuation = value_portfolio(portfolio, make_spread_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(-expected.premium)
        assert result.delta == pytest.approx(
            {("DE_POWER", JAN): -expected.delta1, ("TTF", JAN): -expected.delta2}
        )

    def test_spark_spread_leg2_weight_delegates_to_price_spark_spread_option(self) -> None:
        heat_rate = 2.0
        expected = price_spark_spread_option(_expected_spread_request(), heat_rate)
        portfolio = Portfolio(positions=(Position(make_spread_option(leg2_weight=heat_rate)),))
        valuation = value_portfolio(portfolio, make_spread_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(expected.premium)
        assert result.delta == pytest.approx(
            {("DE_POWER", JAN): expected.delta1, ("TTF", JAN): expected.delta2}
        )

    def test_missing_correlation_raises_naming_the_pair(self) -> None:
        market_data = MarketData(
            forward_curves={"TTF": make_ttf_curve(), "DE_POWER": make_power_curve()},
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces={"TTF": make_ttf_vol_surface(), "DE_POWER": make_power_vol_surface()},
        )
        portfolio = Portfolio(positions=(Position(make_spread_option()),))
        with pytest.raises(ValidationError, match="DE_POWER"):
            value_portfolio(portfolio, market_data)

    def test_wrong_instrument_type_is_rejected_by_the_adapter_directly(self) -> None:
        from quantvolt.portfolio.valuation import _price_spread_option

        with pytest.raises(ValidationError, match="SpreadOptionContract"):
            _price_spread_option(Position(FUTURES), make_spread_market_data())


# --- Requirement 14 / Property 83: native tolling-agreement pricer ---------------------

PLANT = PlantConfig(heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas")
TOLL_SCHEDULE = DeliverySchedule((JAN, FEB))
RHO_POWER_FUEL, RHO_POWER_EUA, RHO_FUEL_EUA = 0.6, 0.3, 0.4


def make_toll_power_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=POWER,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JAN, 95.0, "observed"), CurveNode(FEB, 96.0, "observed")),
    )


def make_toll_fuel_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=TTF,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JAN, 30.0, "observed"), CurveNode(FEB, 32.0, "observed")),
    )


def make_toll_eua_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=EUA,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JAN, 70.0, "observed"), CurveNode(FEB, 72.0, "observed")),
    )


def make_toll_vol_surface() -> VolatilitySurface:
    return VolatilitySurface(
        commodity=POWER, tenors=(VolatilityTenor(JAN, 0.4), VolatilityTenor(FEB, 0.38))
    )


def make_tolling_market_data() -> MarketData:
    return MarketData(
        forward_curves={
            "DE_POWER": make_toll_power_curve(),
            "TTF": make_toll_fuel_curve(),
            "EUA": make_toll_eua_curve(),
        },
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
        vol_surfaces={"DE_POWER": make_toll_vol_surface()},
        correlations={
            ("DE_POWER", "TTF"): RHO_POWER_FUEL,
            ("DE_POWER", "EUA"): RHO_POWER_EUA,
            ("TTF", "EUA"): RHO_FUEL_EUA,
        },
    )


def make_tolling_agreement() -> TollingAgreement:
    return TollingAgreement(
        plant=PLANT,
        power_commodity_id="DE_POWER",
        fuel_commodity_id="TTF",
        eua_commodity_id="EUA",
        schedule=TOLL_SCHEDULE,
    )


def _expected_tolling_result() -> object:
    matrix = np.array(
        [
            [1.0, RHO_POWER_FUEL, RHO_POWER_EUA],
            [RHO_POWER_FUEL, 1.0, RHO_FUEL_EUA],
            [RHO_POWER_EUA, RHO_FUEL_EUA, 1.0],
        ]
    )
    return price_tolling_agreement(
        plant=PLANT,
        power_curve=make_toll_power_curve(),
        fuel_curve=make_toll_fuel_curve(),
        eua_curve=make_toll_eua_curve(),
        vol_surface=make_toll_vol_surface(),
        correlation_matrix=matrix,
        schedule=TOLL_SCHEDULE,
        discount_curve=make_discount_curve(),
    )


class TestNativeTollingAgreementPricer:
    def test_npv_matches_the_kernel(self) -> None:
        expected = _expected_tolling_result()
        portfolio = Portfolio(positions=(Position(make_tolling_agreement()),))
        valuation = value_portfolio(portfolio, make_tolling_market_data())
        assert valuation.priced[0].npv == pytest.approx(expected.npv)

    def test_delta_keys_map_power_fuel_eua_to_commodity_period_pairs(self) -> None:
        expected = _expected_tolling_result()
        portfolio = Portfolio(positions=(Position(make_tolling_agreement()),))
        valuation = value_portfolio(portfolio, make_tolling_market_data())
        delta = valuation.priced[0].delta
        for index, period in enumerate((JAN, FEB)):
            assert delta[("DE_POWER", period)] == pytest.approx(
                expected.per_period_deltas["power"][index]
            )
            assert delta[("TTF", period)] == pytest.approx(
                expected.per_period_deltas["fuel"][index]
            )
            assert delta[("EUA", period)] == pytest.approx(expected.per_period_deltas["eua"][index])

    def test_missing_one_of_the_three_correlations_raises(self) -> None:
        market_data = MarketData(
            forward_curves={
                "DE_POWER": make_toll_power_curve(),
                "TTF": make_toll_fuel_curve(),
                "EUA": make_toll_eua_curve(),
            },
            discount_curve=make_discount_curve(),
            valuation_date=VALUATION_DATE,
            vol_surfaces={"DE_POWER": make_toll_vol_surface()},
            correlations={
                ("DE_POWER", "TTF"): RHO_POWER_FUEL,
                ("DE_POWER", "EUA"): RHO_POWER_EUA,
                # ("TTF", "EUA") deliberately missing
            },
        )
        portfolio = Portfolio(positions=(Position(make_tolling_agreement()),))
        with pytest.raises(ValidationError, match="EUA"):
            value_portfolio(portfolio, market_data)

    def test_wrong_instrument_type_is_rejected_by_the_adapter_directly(self) -> None:
        from quantvolt.portfolio.valuation import _price_tolling_agreement

        with pytest.raises(ValidationError, match="TollingAgreement"):
            _price_tolling_agreement(Position(FUTURES), make_tolling_market_data())


# --- Requirement 19 (DEFERRED roadmap): CachedAssetValuation passthrough ---------------


def make_cached_asset_valuation(
    *, valuation_date: date = VALUATION_DATE, source: ValuationSource = ValuationSource.SIMULATED
) -> CachedAssetValuation:
    return CachedAssetValuation(
        asset_id="plant-42",
        npv=12_345.0,
        delta={("DE_POWER", JAN): 100.0, ("TTF", FEB): -50.0},
        valuation_date=valuation_date,
        source=source,
        standard_error=1.5,
    )


def make_cached_asset_market_data() -> MarketData:
    return MarketData(
        forward_curves={},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
    )


class TestNativeCachedAssetValuationPricer:
    def test_npv_and_delta_pass_through_exactly(self) -> None:
        wrapper = make_cached_asset_valuation()
        portfolio = Portfolio(positions=(Position(wrapper),))
        valuation = value_portfolio(portfolio, make_cached_asset_market_data())
        result = valuation.priced[0]
        assert result.npv == wrapper.npv
        assert result.delta == dict(wrapper.delta)
        assert result.greeks is None
        assert result.reference_prices == {}

    def test_valuation_source_tag_is_propagated_onto_position_tags(self) -> None:
        wrapper = make_cached_asset_valuation(source=ValuationSource.SIMULATED)
        portfolio = Portfolio(positions=(Position(wrapper, position_id="plant-42"),))
        valuation = value_portfolio(portfolio, make_cached_asset_market_data())
        result = valuation.priced[0]
        assert ValuationSource.SIMULATED.value in result.position.tags
        assert result.position.position_id == "plant-42"

    def test_existing_tag_is_not_duplicated(self) -> None:
        wrapper = make_cached_asset_valuation(source=ValuationSource.SIMULATED)
        portfolio = Portfolio(
            positions=(Position(wrapper, tags=(ValuationSource.SIMULATED.value, "desk-A")),)
        )
        valuation = value_portfolio(portfolio, make_cached_asset_market_data())
        result = valuation.priced[0]
        assert result.position.tags.count(ValuationSource.SIMULATED.value) == 1
        assert "desk-A" in result.position.tags

    def test_stale_valuation_date_raises_naming_both_dates(self) -> None:
        wrapper = make_cached_asset_valuation(valuation_date=date(2025, 12, 1))
        portfolio = Portfolio(positions=(Position(wrapper),))
        with pytest.raises(ValidationError, match="2025, 12, 1") as exc_info:
            value_portfolio(portfolio, make_cached_asset_market_data())
        assert "2025, 12, 15" in str(exc_info.value)

    def test_wrong_instrument_type_is_rejected_by_the_adapter_directly(self) -> None:
        from quantvolt.portfolio.valuation import _price_cached_asset_valuation

        with pytest.raises(ValidationError, match="CachedAssetValuation"):
            _price_cached_asset_valuation(Position(FUTURES), make_cached_asset_market_data())


# --- Requirement 20 (DEFERRED roadmap): native cap/floor-strip pricer ------------------

STRIP_SCHEDULE = DeliverySchedule((JAN, FEB))


def make_strip_vol_surface() -> VolatilitySurface:
    # Covers both STRIP_SCHEDULE periods (make_ttf_vol_surface only covers JAN).
    return VolatilitySurface(
        commodity=TTF, tenors=(VolatilityTenor(JAN, TTF_SIGMA), VolatilityTenor(FEB, TTF_SIGMA))
    )


def make_strip_market_data() -> MarketData:
    return MarketData(
        forward_curves={"TTF": make_ttf_curve()},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
        vol_surfaces={"TTF": make_strip_vol_surface()},
    )


def make_cap_floor_strip(
    *, cap_floor_type: CapFloorType = CapFloorType.CAP, side: OptionSide = OptionSide.LONG
) -> CapFloorStripContract:
    return CapFloorStripContract(
        commodity=TTF,
        schedule=STRIP_SCHEDULE,
        cap_floor_type=cap_floor_type,
        strike=34.0,
        notional=1_000.0,
        side=side,
    )


def _expected_strip_result(cap_floor_type: CapFloorType) -> object:
    market_data = make_strip_market_data()
    caplets = tuple(
        VanillaOptionRequest(
            option_type=cap_floor_type.value,
            strike=34.0,
            notional=1_000.0,
            forward=market_data.curve_for("TTF").price_at(period),
            sigma=market_data.surface_for("TTF").sigma_at(period),
            time_to_expiry=actual_365(VALUATION_DATE, period.last_day),
            discount_factor=market_data.discount_curve.discount_factor(period.last_day),
        )
        for period in STRIP_SCHEDULE.periods
    )
    return price_cap_floor(
        CapFloorRequest(
            option_type=cap_floor_type.value, strike=34.0, notional=1_000.0, caplets=caplets
        )
    )


class TestNativeCapFloorStripPricer:
    def test_npv_and_greeks_match_the_kernel(self) -> None:
        expected = _expected_strip_result(CapFloorType.CAP)
        portfolio = Portfolio(positions=(Position(make_cap_floor_strip()),))
        valuation = value_portfolio(portfolio, make_strip_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(expected.premium)
        assert result.greeks == expected.greeks

    def test_per_period_delta_matches_independently_priced_caplets(self) -> None:
        # Strip additivity vs single caplets (external-validation Property 94 precedent):
        # each per-period delta must equal the SAME period priced alone via
        # price_vanilla_option, not merely sum to the aggregate.
        expected = _expected_strip_result(CapFloorType.CAP)
        portfolio = Portfolio(positions=(Position(make_cap_floor_strip()),))
        valuation = value_portfolio(portfolio, make_strip_market_data())
        result = valuation.priced[0]
        for period, caplet in zip(STRIP_SCHEDULE.periods, expected.per_period, strict=True):
            assert result.delta[("TTF", period)] == pytest.approx(caplet.greeks.delta)
        assert sum(result.delta.values()) == pytest.approx(expected.greeks.delta)

    def test_short_side_sign_flips_npv_delta_and_greeks(self) -> None:
        expected = _expected_strip_result(CapFloorType.CAP)
        portfolio = Portfolio(positions=(Position(make_cap_floor_strip(side=OptionSide.SHORT)),))
        valuation = value_portfolio(portfolio, make_strip_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(-expected.premium)
        assert result.greeks == expected.greeks.scale(-1.0)

    def test_floor_type_matches_the_kernel(self) -> None:
        expected = _expected_strip_result(CapFloorType.FLOOR)
        strip = make_cap_floor_strip(cap_floor_type=CapFloorType.FLOOR)
        portfolio = Portfolio(positions=(Position(strip),))
        valuation = value_portfolio(portfolio, make_strip_market_data())
        result = valuation.priced[0]
        assert result.npv == pytest.approx(expected.premium)

    def test_wrong_instrument_type_is_rejected_by_the_adapter_directly(self) -> None:
        from quantvolt.portfolio.valuation import _price_cap_floor_strip

        with pytest.raises(ValidationError, match="CapFloorStripContract"):
            _price_cap_floor_strip(Position(FUTURES), make_strip_market_data())


class TestNewInstrumentsRegisteredInDefaultPricers:
    def test_default_pricers_cover_every_native_instrument_type(self) -> None:
        assert VanillaOptionContract in DEFAULT_PRICERS
        assert SpreadOptionContract in DEFAULT_PRICERS
        assert TollingAgreement in DEFAULT_PRICERS
        assert CachedAssetValuation in DEFAULT_PRICERS
        assert CapFloorStripContract in DEFAULT_PRICERS
