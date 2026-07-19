"""Portfolio-native-pricers correctness properties (design Properties 80-84, 102-103;
`.kiro/specs/portfolio-native-pricers/` Tasks 9-11, 18, 22, Phase 8 / Tasks 23-24).

Each test is tagged with its design Property number and runs the default Hypothesis
profile (``quantvolt`` in ``tests/conftest.py``, 100 examples, no deadline).

Properties 102-103 cover the DEFERRED-roadmap Phase-8 instruments (Requirements 19-20):
``CachedAssetValuation`` (a staleness-checked LSMC/dispatch-cache passthrough) and
``CapFloorStripContract`` (a schedule-shaped strip delegating to ``price_cap_floor``).
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, date, datetime

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    CachedAssetValuation,
    CapFloorStripContract,
    CapFloorType,
    OptionSide,
    OptionType,
    PlantConfig,
    SpreadOptionContract,
    TollingAgreement,
    ValuationSource,
    VanillaOptionContract,
)
from quantvolt.models.ppa import PpaContract, PpaVolumeBasis
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.daycount import actual_365
from quantvolt.portfolio.model import Portfolio, Position
from quantvolt.portfolio.valuation import MarketData, value_portfolio
from quantvolt.pricing.ppa_valuation import PpaPeriodVolume, PpaVolumeProfile, price_ppa
from quantvolt.pricing.spread_option import (
    SpreadOptionRequest,
    price_spark_spread_option,
    price_spread_option,
)
from quantvolt.pricing.tolling import price_tolling_agreement
from quantvolt.pricing.vanilla import (
    CapFloorRequest,
    VanillaOptionRequest,
    price_cap_floor,
    price_vanilla_option,
)

TTF = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
POWER = CommodityConfig("DE_POWER", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh"))
EUA = CommodityConfig("EUA", "EUR/tCO2", Hub("EUA", "EEX", "EUR/tCO2"))

PERIOD = DeliveryPeriod(2027, 6)  # settles 2027-06-30
VALUATION_DATE = date(2026, 1, 1)
SETTLE = PERIOD.last_day
TTE = actual_365(VALUATION_DATE, SETTLE)

_FORWARDS = st.floats(min_value=10.0, max_value=1_000.0)
_SIGMAS = st.floats(min_value=0.05, max_value=2.0)
_DISCOUNT_FACTORS = st.floats(min_value=0.05, max_value=1.0)
_NOTIONALS = st.floats(min_value=0.01, max_value=10_000.0)
_CORRELATIONS = st.floats(min_value=-0.95, max_value=0.95)
_SIDES = st.sampled_from(list(OptionSide))


def _bounded_strike(draw: st.DrawFn, forward: float, sigma: float) -> float:
    bound = min(0.69, 4.5 * sigma * math.sqrt(TTE))
    log_moneyness = draw(st.floats(min_value=-bound, max_value=bound))
    return forward * math.exp(log_moneyness)


def _single_node_curve(commodity: CommodityConfig, price: float) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(PERIOD, price, "observed"),),
    )


def _single_tenor_surface(commodity: CommodityConfig, sigma: float) -> VolatilitySurface:
    return VolatilitySurface(commodity=commodity, tenors=(VolatilityTenor(PERIOD, sigma),))


def _single_tenor_discount_curve(discount_factor: float) -> DiscountCurve:
    return DiscountCurve(
        reference_date=VALUATION_DATE, tenors=(SETTLE,), factors=(discount_factor,)
    )


# --- Property 80: portfolio-native vanilla-option parity -------------------------------

_VanillaCase = tuple[VanillaOptionContract, MarketData, VanillaOptionRequest]


@st.composite
def _vanilla_cases(draw: st.DrawFn) -> _VanillaCase:
    forward = draw(_FORWARDS)
    sigma = draw(_SIGMAS)
    strike = _bounded_strike(draw, forward, sigma)
    notional = draw(_NOTIONALS)
    discount_factor = draw(_DISCOUNT_FACTORS)
    option_type = draw(st.sampled_from(list(OptionType)))
    side = draw(_SIDES)

    contract = VanillaOptionContract(
        commodity=TTF,
        delivery_period=PERIOD,
        option_type=option_type,
        strike=strike,
        notional=notional,
        side=side,
    )
    market_data = MarketData(
        forward_curves={"TTF": _single_node_curve(TTF, forward)},
        discount_curve=_single_tenor_discount_curve(discount_factor),
        valuation_date=VALUATION_DATE,
        vol_surfaces={"TTF": _single_tenor_surface(TTF, sigma)},
    )
    request = VanillaOptionRequest(
        option_type=option_type.value,
        strike=strike,
        notional=notional,
        forward=forward,
        sigma=sigma,
        time_to_expiry=TTE,
        discount_factor=discount_factor,
    )
    return contract, market_data, request


# Feature: portfolio-native-pricers, Property 80: vanilla portfolio-pricer parity
@given(case=_vanilla_cases())
def test_vanilla_portfolio_pricer_matches_the_kernel(
    case: tuple[VanillaOptionContract, MarketData, VanillaOptionRequest],
) -> None:
    contract, market_data, request = case
    expected = price_vanilla_option(request)
    sign = 1.0 if contract.side is OptionSide.LONG else -1.0

    valuation = value_portfolio(Portfolio(positions=(Position(contract),)), market_data)
    result = valuation.priced[0]

    assert result.npv == sign * expected.premium
    key = ("TTF", PERIOD)
    assert result.delta == {key: sign * expected.greeks.delta}
    assert result.greeks == expected.greeks.scale(sign)
    assert result.reference_prices == {key: request.forward}


# --- Property 81: portfolio-native spread-option parity (incl. chain-ruled delta2) -----


@st.composite
def _spread_cases(
    draw: st.DrawFn,
) -> tuple[SpreadOptionContract, MarketData, SpreadOptionRequest, float]:
    forward1 = draw(_FORWARDS)
    forward2 = draw(_FORWARDS)
    sigma1 = draw(_SIGMAS)
    sigma2 = draw(_SIGMAS)
    correlation = draw(_CORRELATIONS)
    strike = draw(st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=200.0)))
    notional = draw(_NOTIONALS)
    discount_factor = draw(_DISCOUNT_FACTORS)
    leg2_weight = draw(st.one_of(st.just(1.0), st.floats(min_value=0.1, max_value=5.0)))
    side = draw(_SIDES)

    contract = SpreadOptionContract(
        commodity_1="DE_POWER",
        commodity_2="TTF",
        delivery_period=PERIOD,
        strike=strike,
        notional=notional,
        leg2_weight=leg2_weight,
        side=side,
    )
    market_data = MarketData(
        forward_curves={
            "DE_POWER": _single_node_curve(POWER, forward1),
            "TTF": _single_node_curve(TTF, forward2),
        },
        discount_curve=_single_tenor_discount_curve(discount_factor),
        valuation_date=VALUATION_DATE,
        vol_surfaces={
            "DE_POWER": _single_tenor_surface(POWER, sigma1),
            "TTF": _single_tenor_surface(TTF, sigma2),
        },
        correlations={("DE_POWER", "TTF"): correlation},
    )
    request = SpreadOptionRequest(
        forward1=forward1,
        forward2=forward2,
        strike=strike,
        sigma1=sigma1,
        sigma2=sigma2,
        correlation=correlation,
        time_to_expiry=TTE,
        discount_factor=discount_factor,
        notional=notional,
    )
    return contract, market_data, request, leg2_weight


# Feature: portfolio-native-pricers, Property 81: spread portfolio-pricer parity
@given(case=_spread_cases())
def test_spread_portfolio_pricer_matches_the_kernel(
    case: tuple[SpreadOptionContract, MarketData, SpreadOptionRequest, float],
) -> None:
    contract, market_data, request, leg2_weight = case
    expected = (
        price_spread_option(request)
        if leg2_weight == 1.0
        else price_spark_spread_option(request, leg2_weight)
    )
    sign = 1.0 if contract.side is OptionSide.LONG else -1.0

    valuation = value_portfolio(Portfolio(positions=(Position(contract),)), market_data)
    result = valuation.priced[0]

    assert result.npv == sign * expected.premium
    assert result.delta == {
        ("DE_POWER", PERIOD): sign * expected.delta1,
        ("TTF", PERIOD): sign * expected.delta2,
    }
    assert result.greeks is None
    assert result.reference_prices == {
        ("DE_POWER", PERIOD): request.forward1,
        ("TTF", PERIOD): request.forward2,
    }


# --- Property 82: MarketData accessor completeness + correlation symmetry -------------


_MarketDataAccessorCase = tuple[MarketData, tuple[str, ...], dict[tuple[str, str], float]]


@st.composite
def _market_data_accessor_cases(draw: st.DrawFn) -> _MarketDataAccessorCase:
    commodity_ids = draw(
        st.lists(
            st.sampled_from(("TTF", "DE_POWER", "EUA", "NBP")),
            min_size=1,
            max_size=4,
            unique=True,
        )
    )
    surfaces = {
        commodity_id: _single_tenor_surface(TTF, draw(_SIGMAS)) for commodity_id in commodity_ids
    }
    pairs = draw(
        st.lists(
            st.tuples(st.sampled_from(commodity_ids), st.sampled_from(commodity_ids)).filter(
                lambda pair: pair[0] != pair[1]
            ),
            max_size=4,
            unique_by=lambda pair: frozenset(pair),
        )
    )
    correlations = {pair: draw(_CORRELATIONS) for pair in pairs}
    market_data = MarketData(
        forward_curves={cid: _single_node_curve(TTF, 50.0) for cid in commodity_ids},
        discount_curve=_single_tenor_discount_curve(0.9),
        valuation_date=VALUATION_DATE,
        vol_surfaces=surfaces,
        correlations=correlations,
    )
    return market_data, tuple(commodity_ids), correlations


# Feature: portfolio-native-pricers, Property 82: accessor completeness + correlation
# symmetry
@given(case=_market_data_accessor_cases())
def test_surface_for_and_correlation_for_completeness_and_symmetry(
    case: _MarketDataAccessorCase,
) -> None:
    market_data, commodity_ids, correlations = case
    for commodity_id in commodity_ids:
        assert market_data.surface_for(commodity_id) is market_data.vol_surfaces[commodity_id]
    try:
        market_data.surface_for("NOT_REGISTERED")
    except ValidationError:
        pass
    else:
        raise AssertionError("expected ValidationError for an unregistered commodity id")

    for (a, b), rho in correlations.items():
        assert market_data.correlation_for(a, b) == rho
        assert market_data.correlation_for(b, a) == rho
    if not any({"A", "B"} <= {a, b} for a, b in correlations):
        try:
            market_data.correlation_for("A", "B")
        except ValidationError:
            pass
        else:
            raise AssertionError("expected ValidationError for an unregistered pair")


# --- Property 83: tolling parity + delta-key mapping -----------------------------------

PLANT = PlantConfig(heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas")
TOLL_PERIODS = (DeliveryPeriod(2027, 1), DeliveryPeriod(2027, 2), DeliveryPeriod(2027, 3))
TOLL_SCHEDULE = DeliverySchedule(TOLL_PERIODS)


def _curve_from_prices(commodity: CommodityConfig, prices: list[float]) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=VALUATION_DATE,
        nodes=tuple(
            CurveNode(period, price, "observed")
            for period, price in zip(TOLL_PERIODS, prices, strict=True)
        ),
    )


@st.composite
def _tolling_cases(draw: st.DrawFn) -> tuple[TollingAgreement, MarketData]:
    power_prices = [draw(_FORWARDS) for _ in TOLL_PERIODS]
    fuel_prices = [draw(_FORWARDS) for _ in TOLL_PERIODS]
    eua_prices = [draw(_FORWARDS) for _ in TOLL_PERIODS]
    sigma = draw(_SIGMAS)
    rho_power_fuel = draw(_CORRELATIONS)
    rho_power_eua = draw(_CORRELATIONS)
    rho_fuel_eua = draw(_CORRELATIONS)
    capacity = draw(st.floats(min_value=0.1, max_value=100.0))

    power_curve = _curve_from_prices(POWER, power_prices)
    fuel_curve = _curve_from_prices(TTF, fuel_prices)
    eua_curve = _curve_from_prices(EUA, eua_prices)
    vol_surface = VolatilitySurface(
        commodity=POWER, tenors=tuple(VolatilityTenor(period, sigma) for period in TOLL_PERIODS)
    )
    discount_curve = DiscountCurve(
        reference_date=VALUATION_DATE,
        tenors=tuple(period.last_day for period in TOLL_PERIODS),
        factors=(0.99, 0.98, 0.97),
    )
    market_data = MarketData(
        forward_curves={"DE_POWER": power_curve, "TTF": fuel_curve, "EUA": eua_curve},
        discount_curve=discount_curve,
        valuation_date=VALUATION_DATE,
        vol_surfaces={"DE_POWER": vol_surface},
        correlations={
            ("DE_POWER", "TTF"): rho_power_fuel,
            ("DE_POWER", "EUA"): rho_power_eua,
            ("TTF", "EUA"): rho_fuel_eua,
        },
    )
    agreement = TollingAgreement(
        plant=PLANT,
        power_commodity_id="DE_POWER",
        fuel_commodity_id="TTF",
        eua_commodity_id="EUA",
        schedule=TOLL_SCHEDULE,
        capacity=capacity,
    )
    return agreement, market_data


# Feature: portfolio-native-pricers, Property 83: tolling parity + delta-key mapping
@given(case=_tolling_cases())
def test_tolling_portfolio_pricer_matches_the_kernel_and_maps_delta_keys(
    case: tuple[TollingAgreement, MarketData],
) -> None:
    agreement, market_data = case
    rho_pf = market_data.correlation_for("DE_POWER", "TTF")
    rho_pe = market_data.correlation_for("DE_POWER", "EUA")
    rho_fe = market_data.correlation_for("TTF", "EUA")
    matrix = np.array([[1.0, rho_pf, rho_pe], [rho_pf, 1.0, rho_fe], [rho_pe, rho_fe, 1.0]])
    expected = price_tolling_agreement(
        plant=PLANT,
        power_curve=market_data.curve_for("DE_POWER"),
        fuel_curve=market_data.curve_for("TTF"),
        eua_curve=market_data.curve_for("EUA"),
        vol_surface=market_data.surface_for("DE_POWER"),
        correlation_matrix=matrix,
        schedule=TOLL_SCHEDULE,
        discount_curve=market_data.discount_curve,
        capacity=agreement.capacity,
    )

    valuation = value_portfolio(Portfolio(positions=(Position(agreement),)), market_data)
    result = valuation.priced[0]

    assert result.npv == expected.npv
    for index, period in enumerate(TOLL_PERIODS):
        assert result.delta[("DE_POWER", period)] == expected.per_period_deltas["power"][index]
        assert result.delta[("TTF", period)] == expected.per_period_deltas["fuel"][index]
        assert result.delta[("EUA", period)] == expected.per_period_deltas["eua"][index]


# --- Property 84: PPA MtM linearity + delta bump ---------------------------------------


_PpaCase = tuple[PpaContract, PpaVolumeProfile, ForwardCurve, DiscountCurve]


@st.composite
def _ppa_cases(draw: st.DrawFn) -> _PpaCase:
    periods = TOLL_PERIODS
    forwards = [draw(st.floats(min_value=10.0, max_value=200.0)) for _ in periods]
    volumes = [draw(st.floats(min_value=1.0, max_value=1_000.0)) for _ in periods]
    captures = [draw(st.floats(min_value=0.5, max_value=1.5)) for _ in periods]
    factors = [draw(_DISCOUNT_FACTORS) for _ in periods]
    fixed_price = draw(st.floats(min_value=10.0, max_value=200.0))

    forward_curve = _curve_from_prices(POWER, forwards)
    discount_curve = DiscountCurve(
        reference_date=VALUATION_DATE,
        tenors=tuple(p.last_day for p in periods),
        factors=tuple(factors),
    )
    profile = PpaVolumeProfile(
        tuple(
            PpaPeriodVolume(period=p, expected_mwh=v, capture_factor=c)
            for p, v, c in zip(periods, volumes, captures, strict=True)
        )
    )
    contract = PpaContract(
        contract_id="ppa-prop",
        bidding_zone="DE_POWER",
        fixed_price_per_mwh=fixed_price,
        start_utc=datetime(2026, 1, 1, tzinfo=UTC),
        end_utc=datetime(2028, 1, 1, tzinfo=UTC),
        volume_basis=PpaVolumeBasis.BASELOAD,
    )
    return contract, profile, forward_curve, discount_curve


# Feature: portfolio-native-pricers, Property 84: PPA MtM linearity + delta bump
@given(case=_ppa_cases(), scale=st.floats(min_value=0.1, max_value=5.0))
def test_ppa_mtm_is_linear_in_volume_and_forward_with_matching_finite_difference_delta(
    case: _PpaCase, scale: float
) -> None:
    contract, profile, forward_curve, discount_curve = case
    base = price_ppa(contract, profile, forward_curve, discount_curve, VALUATION_DATE)

    # Linearity in expected_mwh: scaling every period's volume by `scale` scales npv by
    # `scale` exactly (K_t, capture_t, F_t all held fixed).
    scaled_profile = PpaVolumeProfile(
        tuple(
            PpaPeriodVolume(
                period=v.period,
                expected_mwh=v.expected_mwh * scale,
                capture_factor=v.capture_factor,
            )
            for v in profile.volumes
        )
    )
    scaled = price_ppa(contract, scaled_profile, forward_curve, discount_curve, VALUATION_DATE)
    assert scaled.npv == pytest.approx(base.npv * scale, rel=1e-9, abs=1e-9)

    # Linearity in the forward + finite-difference delta: bump one period's forward node
    # and confirm the npv change matches the reported closed-form delta exactly.
    bump = 1.0
    first_period = profile.volumes[0].period

    def _bump_price(node: CurveNode) -> float:
        return node.price + bump if node.period == first_period else node.price

    bumped_nodes = tuple(
        CurveNode(node.period, _bump_price(node), node.status) for node in forward_curve.nodes
    )
    bumped_curve = ForwardCurve(
        commodity=forward_curve.commodity,
        market_date=forward_curve.market_date,
        nodes=bumped_nodes,
    )
    bumped = price_ppa(contract, profile, bumped_curve, discount_curve, VALUATION_DATE)
    finite_difference = (bumped.npv - base.npv) / bump
    reported_delta = base.delta[(contract.bidding_zone, first_period)]
    assert finite_difference == pytest.approx(reported_delta, rel=1e-9, abs=1e-9)


# --- Property 102: CachedAssetValuation frozen passthrough + staleness guard -----------
# (DEFERRED roadmap, portfolio-native-pricers Requirement 19)

_CachedCase = tuple[CachedAssetValuation, MarketData]
_EXTRA_TAGS = st.lists(st.sampled_from(("desk-A", "desk-B", "hedge")), max_size=2, unique=True)


@st.composite
def _cached_asset_valuation_cases(draw: st.DrawFn) -> _CachedCase:
    delta = {
        ("DE_POWER", TOLL_PERIODS[0]): draw(st.floats(min_value=-1_000.0, max_value=1_000.0)),
        ("TTF", TOLL_PERIODS[1]): draw(st.floats(min_value=-1_000.0, max_value=1_000.0)),
    }
    wrapper = CachedAssetValuation(
        asset_id="plant-prop",
        npv=draw(st.floats(min_value=-1_000_000.0, max_value=1_000_000.0)),
        delta=delta,
        valuation_date=VALUATION_DATE,
        source=draw(st.sampled_from(ValuationSource)),
        standard_error=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=10_000.0))),
    )
    market_data = MarketData(
        forward_curves={},
        discount_curve=_single_tenor_discount_curve(0.95),
        valuation_date=VALUATION_DATE,
    )
    return wrapper, market_data


# Feature: portfolio-native-pricers, Property 102: CachedAssetValuation passthrough +
# staleness guard
@given(case=_cached_asset_valuation_cases(), extra_tags=_EXTRA_TAGS)
def test_cached_asset_valuation_passes_through_exactly_and_rejects_a_stale_cache(
    case: _CachedCase, extra_tags: list[str]
) -> None:
    wrapper, market_data = case
    position = Position(wrapper, tags=tuple(extra_tags))

    valuation = value_portfolio(Portfolio(positions=(position,)), market_data)
    result = valuation.priced[0]

    # Frozen passthrough: the cache's own npv/delta reach the PricedPosition unchanged.
    assert result.npv == wrapper.npv
    assert result.delta == dict(wrapper.delta)
    assert result.greeks is None
    # ValuationSource tag propagated onto Position.tags (Property-66 pattern), never
    # duplicated, and every pre-existing tag preserved.
    assert result.position.tags.count(wrapper.source.value) == 1
    assert set(extra_tags) <= set(result.position.tags)

    # Staleness guard: a valuation_date mismatch raises rather than repricing/reusing it.
    stale_wrapper = dataclasses.replace(wrapper, valuation_date=date(2000, 1, 1))
    with pytest.raises(ValidationError):
        value_portfolio(Portfolio(positions=(Position(stale_wrapper),)), market_data)


# --- Property 103: cap/floor-strip portfolio-native parity + strip additivity ----------
# (DEFERRED roadmap, portfolio-native-pricers Requirement 20; strip additivity cross-checks
# the external-validation spec's Property 94 precedent at the portfolio-adapter level --
# that property number is not claimed or renumbered here.)

_StripCase = tuple[CapFloorStripContract, MarketData]


@st.composite
def _cap_floor_strip_cases(draw: st.DrawFn) -> _StripCase:
    forwards = [draw(_FORWARDS) for _ in TOLL_PERIODS]
    sigma = draw(_SIGMAS)
    discount_factor = draw(_DISCOUNT_FACTORS)
    strike = draw(st.floats(min_value=1.0, max_value=500.0))
    notional = draw(_NOTIONALS)
    cap_floor_type = draw(st.sampled_from(CapFloorType))
    side = draw(_SIDES)

    curve = _curve_from_prices(TTF, forwards)
    vol_surface = VolatilitySurface(
        commodity=TTF, tenors=tuple(VolatilityTenor(period, sigma) for period in TOLL_PERIODS)
    )
    discount_curve = DiscountCurve(
        reference_date=VALUATION_DATE,
        tenors=tuple(period.last_day for period in TOLL_PERIODS),
        factors=tuple(discount_factor for _ in TOLL_PERIODS),
    )
    strip = CapFloorStripContract(
        commodity=TTF,
        schedule=TOLL_SCHEDULE,
        cap_floor_type=cap_floor_type,
        strike=strike,
        notional=notional,
        side=side,
    )
    market_data = MarketData(
        forward_curves={"TTF": curve},
        discount_curve=discount_curve,
        valuation_date=VALUATION_DATE,
        vol_surfaces={"TTF": vol_surface},
    )
    return strip, market_data


# Feature: portfolio-native-pricers, Property 103: cap/floor-strip portfolio-pricer parity
# + strip additivity vs independently-priced single caplets
@given(case=_cap_floor_strip_cases())
def test_cap_floor_strip_portfolio_pricer_matches_the_kernel_and_single_caplets(
    case: _StripCase,
) -> None:
    strip, market_data = case
    sign = 1.0 if strip.side is OptionSide.LONG else -1.0

    caplets = tuple(
        VanillaOptionRequest(
            option_type=strip.cap_floor_type.value,
            strike=strip.strike,
            notional=strip.notional,
            forward=market_data.curve_for("TTF").price_at(period),
            sigma=market_data.surface_for("TTF").sigma_at(period),
            time_to_expiry=actual_365(VALUATION_DATE, period.last_day),
            discount_factor=market_data.discount_curve.discount_factor(period.last_day),
        )
        for period in TOLL_PERIODS
    )
    expected = price_cap_floor(
        CapFloorRequest(
            option_type=strip.cap_floor_type.value,
            strike=strip.strike,
            notional=strip.notional,
            caplets=caplets,
        )
    )

    valuation = value_portfolio(Portfolio(positions=(Position(strip),)), market_data)
    result = valuation.priced[0]

    # Parity vs the kernel's own aggregate.
    assert result.npv == sign * expected.premium
    assert result.greeks == expected.greeks.scale(sign)

    # Strip additivity vs independently-priced single-period caplets (each period's own
    # `price_vanilla_option` call, not merely the kernel's internal sum): per-period delta
    # must equal the SAME period priced alone.
    for period, caplet_request in zip(TOLL_PERIODS, caplets, strict=True):
        independent = price_vanilla_option(caplet_request)
        assert result.delta[("TTF", period)] == sign * independent.greeks.delta
    assert sum(result.delta.values()) == pytest.approx(sign * expected.greeks.delta)
