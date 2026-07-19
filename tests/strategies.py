"""Importable Hypothesis ``@st.composite`` strategies for the test suites (Task 48).

Shared by the property suite (and importable from unit tests). Draws are confined to
well-conditioned numeric regions so the closed-form kernels stay far from
under-/overflow while still exercising the full documented domains:

- forward-curve / instrument / contract prices: finite in ``[-10_000, 10_000]``
  (negative power prices are real and must be exercised);
- option forwards: ``[10, 1_000]``; strikes are ``forward * exp(m)`` with log-moneyness
  ``m`` bounded by ``min(0.69, 4.5 * sigma * sqrt(T))`` so ``|d1|`` stays below ~7 and
  the normal pdf (hence vega) never underflows;
- volatilities: ``sigma`` in ``[0.01, 2.0]`` on surfaces; option requests use a
  ``0.05`` floor (and a ``1.5`` cap for the exotic closed forms);
- times to expiry: ``[0.01, 5.0]`` years (option requests use a ``0.05`` floor);
- discount factors: ``[0.05, 1.0]``;
- notionals: ``[0.01, 10_000]`` (strictly positive per the instrument invariants);
- delivery periods: calendar months in ``[2024-01, 2032-12]``, always strictly
  increasing where a model requires ordering.

``discount_curves()`` always spans ``[2023-06-30, 2033-12-31]`` from a fixed
``reference_date`` of 2023-01-01, so every settlement date reachable from
``delivery_periods()`` is covered; factors are drawn in ``[0.05, 1.0]`` and assigned
in decreasing order along the tenors.
"""

from __future__ import annotations

import math
from datetime import date
from typing import TYPE_CHECKING, Final, Literal

import numpy as np
from hypothesis import strategies as st
from numpy.typing import NDArray

from quantvolt.models.commodity import BUILT_IN_COMMODITIES, CommodityConfig
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    CachedAssetValuation,
    CapFloorStripContract,
    CapFloorType,
    FuturesContract,
    InstrumentPriceRecord,
    OptionSide,
    OptionType,
    SettlementType,
    SpreadOptionContract,
    SwapContract,
    ValuationSource,
    VanillaOptionContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule, Granularity
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.pricing.exotic import AsianOptionRequest, BarrierOptionRequest
from quantvolt.pricing.mark_to_market import MtMPosition
from quantvolt.pricing.spread_option import SpreadOptionRequest
from quantvolt.pricing.vanilla import VanillaOptionRequest

if TYPE_CHECKING:
    import polars as pl

__all__ = [
    "aligned_forward_curves",
    "asian_option_requests",
    "barrier_option_requests",
    "cached_asset_valuations",
    "cap_floor_strip_contracts",
    "commodity_configs",
    "curve_nodes",
    "delivery_periods",
    "delivery_schedules",
    "discount_curves",
    "forward_curves",
    "futures_contracts",
    "futures_pricing_cases",
    "instrument_price_record_lists",
    "mtm_positions",
    "priced_positions",
    "spread_option_contracts",
    "spread_option_requests",
    "swap_contracts",
    "swap_pricing_cases",
    "temperature_frames",
    "vanilla_option_contracts",
    "vanilla_option_requests",
    "vol_surfaces",
]

# --- documented numeric ranges (module docstring) ----------------------------------

_MIN_YEAR: Final[int] = 2024
_MAX_YEAR: Final[int] = 2032
_MONTH_INDEX_MIN: Final[int] = _MIN_YEAR * 12
_MONTH_INDEX_MAX: Final[int] = _MAX_YEAR * 12 + 11

PRICES: Final[st.SearchStrategy[float]] = st.floats(
    min_value=-10_000.0, max_value=10_000.0, allow_nan=False, allow_infinity=False
)
NOTIONALS: Final[st.SearchStrategy[float]] = st.floats(min_value=0.01, max_value=10_000.0)
SIGMAS: Final[st.SearchStrategy[float]] = st.floats(min_value=0.01, max_value=2.0)
DISCOUNT_FACTORS: Final[st.SearchStrategy[float]] = st.floats(min_value=0.05, max_value=1.0)
MARKET_DATES: Final[st.SearchStrategy[date]] = st.dates(
    min_value=date(2023, 1, 1), max_value=date(2026, 12, 31)
)

_OPTION_FORWARDS: Final[st.SearchStrategy[float]] = st.floats(min_value=10.0, max_value=1_000.0)
_OPTION_SIGMAS: Final[st.SearchStrategy[float]] = st.floats(min_value=0.05, max_value=2.0)
_EXOTIC_SIGMAS: Final[st.SearchStrategy[float]] = st.floats(min_value=0.05, max_value=1.5)
_OPTION_EXPIRIES: Final[st.SearchStrategy[float]] = st.floats(min_value=0.05, max_value=5.0)
_EXOTIC_EXPIRIES: Final[st.SearchStrategy[float]] = st.floats(min_value=0.05, max_value=3.0)
_STATUSES: Final[st.SearchStrategy[Literal["observed", "interpolated"]]] = st.sampled_from(
    ("observed", "interpolated")
)
_FLOATING_INDICES: Final[st.SearchStrategy[str]] = st.sampled_from(
    ("TTF_DA", "EPEX_SPOT_DE", "NBP_DA")
)
_CALL_PUT: Final[tuple[Literal["call", "put"], ...]] = ("call", "put")
_AVERAGINGS: Final[tuple[Literal["arithmetic", "geometric"], ...]] = ("arithmetic", "geometric")
_BARRIER_TYPES: Final[tuple[Literal["up_in", "up_out", "down_in", "down_out"], ...]] = (
    "up_in",
    "up_out",
    "down_in",
    "down_out",
)


def _period_from_index(index: int) -> DeliveryPeriod:
    """Map a whole-month index (``year * 12 + month - 1``) back to a period."""
    return DeliveryPeriod(year=index // 12, month=index % 12 + 1)


def _month_index_sets(min_size: int, max_size: int) -> st.SearchStrategy[set[int]]:
    """Distinct month indices within the documented delivery-period window."""
    return st.sets(
        st.integers(min_value=_MONTH_INDEX_MIN, max_value=_MONTH_INDEX_MAX),
        min_size=min_size,
        max_size=max_size,
    )


# --- domain value objects -----------------------------------------------------------


@st.composite
def delivery_periods(
    draw: st.DrawFn, min_year: int = _MIN_YEAR, max_year: int = _MAX_YEAR
) -> DeliveryPeriod:
    """A calendar-month delivery period within ``[min_year-01, max_year-12]``."""
    index = draw(st.integers(min_value=min_year * 12, max_value=max_year * 12 + 11))
    return _period_from_index(index)


@st.composite
def delivery_schedules(draw: st.DrawFn, min_len: int = 1, max_len: int = 12) -> DeliverySchedule:
    """A valid schedule: strictly increasing, distinct calendar months."""
    indices = draw(_month_index_sets(min_len, max_len))
    return DeliverySchedule(periods=tuple(_period_from_index(i) for i in sorted(indices)))


def commodity_configs() -> st.SearchStrategy[CommodityConfig]:
    """One of the built-in commodities (the registry the library ships with)."""
    return st.sampled_from(tuple(BUILT_IN_COMMODITIES.values()))


@st.composite
def curve_nodes(draw: st.DrawFn) -> CurveNode:
    """A single curve node: any finite price (negatives included), either status."""
    return CurveNode(period=draw(delivery_periods()), price=draw(PRICES), status=draw(_STATUSES))


@st.composite
def forward_curves(draw: st.DrawFn, min_nodes: int = 1, max_nodes: int = 12) -> ForwardCurve:
    """A valid forward curve: strictly ordered periods, finite (possibly negative)
    prices, and a mix of observed/interpolated statuses."""
    commodity = draw(commodity_configs())
    market_date = draw(MARKET_DATES)
    indices = sorted(draw(_month_index_sets(min_nodes, max_nodes)))
    nodes = tuple(
        CurveNode(period=_period_from_index(i), price=draw(PRICES), status=draw(_STATUSES))
        for i in indices
    )
    return ForwardCurve(commodity=commodity, market_date=market_date, nodes=nodes)


@st.composite
def discount_curves(draw: st.DrawFn) -> DiscountCurve:
    """A discount curve spanning ``[2023-06-30, 2033-12-31]`` (covers every settlement
    date reachable from ``delivery_periods()``) with factors in ``[0.05, 1.0]``
    assigned in decreasing order along the tenors."""
    first, last = date(2023, 6, 30), date(2033, 12, 31)
    interior = draw(
        st.sets(st.dates(min_value=date(2023, 7, 31), max_value=date(2033, 11, 30)), max_size=6)
    )
    tenors = tuple(sorted({first, last, *interior}))
    factors = draw(st.lists(DISCOUNT_FACTORS, min_size=len(tenors), max_size=len(tenors)))
    return DiscountCurve(
        reference_date=date(2023, 1, 1),
        tenors=tenors,
        factors=tuple(sorted(factors, reverse=True)),
    )


@st.composite
def vol_surfaces(draw: st.DrawFn, min_tenors: int = 1, max_tenors: int = 8) -> VolatilitySurface:
    """A vol surface with strictly increasing periods and sigma in ``[0.01, 2.0]``."""
    commodity = draw(commodity_configs())
    indices = sorted(draw(_month_index_sets(min_tenors, max_tenors)))
    tenors = tuple(
        VolatilityTenor(period=_period_from_index(i), sigma=draw(SIGMAS)) for i in indices
    )
    return VolatilitySurface(commodity=commodity, tenors=tenors)


# --- instruments ---------------------------------------------------------------------


@st.composite
def futures_contracts(draw: st.DrawFn) -> FuturesContract:
    """A futures contract: any finite contract price, positive notional, and a
    granularity/settlement type drawn across all enum members."""
    return FuturesContract(
        commodity=draw(commodity_configs()),
        delivery_period=draw(delivery_periods()),
        contract_price=draw(PRICES),
        notional=draw(NOTIONALS),
        granularity=draw(st.sampled_from(Granularity)),
        settlement_type=draw(st.sampled_from(SettlementType)),
    )


@st.composite
def swap_contracts(draw: st.DrawFn, max_periods: int = 12) -> SwapContract:
    """A fixed-for-floating swap over a valid (strictly increasing) schedule."""
    return SwapContract(
        commodity=draw(commodity_configs()),
        fixed_rate=draw(PRICES),
        floating_index=draw(_FLOATING_INDICES),
        notional=draw(NOTIONALS),
        schedule=draw(delivery_schedules(max_len=max_periods)),
        granularity=draw(st.sampled_from(Granularity)),
    )


@st.composite
def instrument_price_record_lists(
    draw: st.DrawFn, min_len: int = 1, max_len: int = 10, span_months: int = 36
) -> list[InstrumentPriceRecord]:
    """Observed instrument prices for ONE commodity over distinct, ordered delivery
    periods (all within a ``span_months`` window so gap-filled grids stay small).
    Instrument ids are unique within the list."""
    commodity = draw(commodity_configs())
    base = draw(st.integers(_MONTH_INDEX_MIN, _MONTH_INDEX_MAX - span_months))
    offsets = draw(st.sets(st.integers(0, span_months - 1), min_size=min_len, max_size=max_len))
    return [
        InstrumentPriceRecord(
            instrument_id=f"inst-{position}",
            commodity=commodity,
            delivery_period=_period_from_index(base + offset),
            price=draw(PRICES),
        )
        for position, offset in enumerate(sorted(offsets))
    ]


@st.composite
def mtm_positions(draw: st.DrawFn) -> MtMPosition:
    """An open mark-to-market position; trade/prior marks may be negative."""
    return MtMPosition(
        commodity_id=draw(st.sampled_from(tuple(BUILT_IN_COMMODITIES))),
        delivery_period=draw(delivery_periods()),
        notional=draw(NOTIONALS),
        trade_price=draw(PRICES),
        prior_mark_price=draw(PRICES),
    )


# --- option requests -----------------------------------------------------------------


def _bounded_strike(draw: st.DrawFn, forward: float, sigma: float, time_to_expiry: float) -> float:
    """A strike near the forward: log-moneyness bounded by ``min(0.69, 4.5*sigma*sqrt(T))``
    keeps ``|d1|`` below ~7 so the normal pdf (hence vega) never underflows."""
    bound = min(0.69, 4.5 * sigma * math.sqrt(time_to_expiry))
    log_moneyness = draw(st.floats(min_value=-bound, max_value=bound))
    return forward * math.exp(log_moneyness)


@st.composite
def vanilla_option_requests(
    draw: st.DrawFn,
    option_types: tuple[Literal["call", "put", "cap", "floor"], ...] = (
        "call",
        "put",
        "cap",
        "floor",
    ),
) -> VanillaOptionRequest:
    """A valid-domain Black-76 vanilla request in the well-conditioned region."""
    forward = draw(_OPTION_FORWARDS)
    sigma = draw(_OPTION_SIGMAS)
    time_to_expiry = draw(_OPTION_EXPIRIES)
    return VanillaOptionRequest(
        option_type=draw(st.sampled_from(option_types)),
        strike=_bounded_strike(draw, forward, sigma, time_to_expiry),
        notional=draw(st.floats(min_value=0.01, max_value=1_000.0)),
        forward=forward,
        sigma=sigma,
        time_to_expiry=time_to_expiry,
        discount_factor=draw(DISCOUNT_FACTORS),
    )


@st.composite
def spread_option_requests(draw: st.DrawFn) -> SpreadOptionRequest:
    """A valid spread-option request; strike mixes exactly-zero (Margrabe) and
    positive (Kirk) draws, correlation stays strictly inside ``(-1, 1)``."""
    return SpreadOptionRequest(
        forward1=draw(_OPTION_FORWARDS),
        forward2=draw(_OPTION_FORWARDS),
        strike=draw(st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=200.0))),
        sigma1=draw(st.floats(min_value=0.05, max_value=1.0)),
        sigma2=draw(st.floats(min_value=0.05, max_value=1.0)),
        correlation=draw(st.floats(min_value=-0.95, max_value=0.95)),
        time_to_expiry=draw(_EXOTIC_EXPIRIES),
        discount_factor=draw(DISCOUNT_FACTORS),
        notional=draw(st.floats(min_value=0.01, max_value=1_000.0)),
    )


@st.composite
def asian_option_requests(draw: st.DrawFn) -> AsianOptionRequest:
    """A valid Asian request priced by the default closed form for its averaging."""
    forward = draw(_OPTION_FORWARDS)
    sigma = draw(_EXOTIC_SIGMAS)
    time_to_expiry = draw(_EXOTIC_EXPIRIES)
    return AsianOptionRequest(
        option_type=draw(st.sampled_from(_CALL_PUT)),
        averaging=draw(st.sampled_from(_AVERAGINGS)),
        strike=_bounded_strike(draw, forward, sigma, time_to_expiry),
        forward=forward,
        sigma=sigma,
        time_to_expiry=time_to_expiry,
        discount_factor=draw(DISCOUNT_FACTORS),
    )


@st.composite
def barrier_option_requests(draw: st.DrawFn) -> BarrierOptionRequest:
    """A VALID barrier request: an up barrier strictly above the forward, a down
    barrier strictly below it (Property 17's validity rule)."""
    barrier_type = draw(st.sampled_from(_BARRIER_TYPES))
    forward = draw(_OPTION_FORWARDS)
    if barrier_type.startswith("up"):
        barrier = forward * draw(st.floats(min_value=1.05, max_value=2.5))
    else:
        barrier = forward * draw(st.floats(min_value=0.4, max_value=0.95))
    return BarrierOptionRequest(
        option_type=draw(st.sampled_from(_CALL_PUT)),
        barrier_type=barrier_type,
        strike=forward * draw(st.floats(min_value=0.6, max_value=1.7)),
        barrier=barrier,
        forward=forward,
        sigma=draw(_EXOTIC_SIGMAS),
        time_to_expiry=draw(_EXOTIC_EXPIRIES),
        discount_factor=draw(DISCOUNT_FACTORS),
    )


# --- composed pricing cases (shared across property files) ----------------------------


@st.composite
def futures_pricing_cases(
    draw: st.DrawFn,
) -> tuple[FuturesContract, ForwardCurve, date, DiscountCurve]:
    """``(contract, forward_curve, valuation_date, discount_curve)`` ready to price:
    the contract period is a node of the curve, the discount curve covers its
    settlement date, and the valuation date is on or before settlement."""
    curve = draw(forward_curves(min_nodes=1, max_nodes=8))
    node = draw(st.sampled_from(curve.nodes))
    contract = FuturesContract(
        commodity=curve.commodity,
        delivery_period=node.period,
        contract_price=draw(PRICES),
        notional=draw(NOTIONALS),
        settlement_type=draw(st.sampled_from(SettlementType)),
    )
    valuation_date = draw(st.dates(min_value=date(2023, 7, 1), max_value=node.period.last_day))
    return contract, curve, valuation_date, draw(discount_curves())


@st.composite
def swap_pricing_cases(
    draw: st.DrawFn,
) -> tuple[SwapContract, ForwardCurve, DiscountCurve]:
    """``(swap, forward_curve, discount_curve)`` ready to price: the schedule is a
    non-empty subset of the curve's periods and every settlement date is covered."""
    curve = draw(forward_curves(min_nodes=1, max_nodes=12))
    picks = draw(
        st.sets(st.integers(0, len(curve.nodes) - 1), min_size=1, max_size=len(curve.nodes))
    )
    schedule = DeliverySchedule(periods=tuple(curve.nodes[i].period for i in sorted(picks)))
    swap = SwapContract(
        commodity=curve.commodity,
        fixed_rate=draw(PRICES),
        floating_index=draw(_FLOATING_INDICES),
        notional=draw(NOTIONALS),
        schedule=schedule,
    )
    return swap, curve, draw(discount_curves())


# --- part-2 additions (Task 49, second half) ------------------------------------------
#
# Additive only: nothing above this marker may change (part 1's tests depend on it).


@st.composite
def aligned_forward_curves(
    draw: st.DrawFn,
    count: int = 2,
    min_nodes: int = 1,
    max_nodes: int = 12,
    prices: st.SearchStrategy[float] = PRICES,
) -> tuple[ForwardCurve, ...]:
    """``count`` forward curves sharing one drawn delivery-period grid (and market
    date), each with independently drawn commodity and prices — the intersection of
    their periods is the full grid, ready for the spread analytics (spark/dark/
    clean/basis/crack; design Properties 6-9, 42-43)."""
    market_date = draw(MARKET_DATES)
    indices = sorted(draw(_month_index_sets(min_nodes, max_nodes)))
    curves = []
    for _ in range(count):
        nodes = tuple(
            CurveNode(period=_period_from_index(i), price=draw(prices), status=draw(_STATUSES))
            for i in indices
        )
        curves.append(
            ForwardCurve(commodity=draw(commodity_configs()), market_date=market_date, nodes=nodes)
        )
    return tuple(curves)


# Deliberately small risk-factor pool (3 commodities x 6 months) so books of a few
# positions overlap on (commodity, period) cells and aggregation really nets.
RISK_COMMODITY_IDS: Final[tuple[str, ...]] = ("EEX_PHELIX_DE", "EUA", "TTF")
RISK_PERIODS: Final[tuple[DeliveryPeriod, ...]] = tuple(
    DeliveryPeriod(year=2026, month=month) for month in range(1, 7)
)
_DELTA_EXPOSURES: Final[st.SearchStrategy[float]] = st.floats(min_value=-1_000.0, max_value=1_000.0)


@st.composite
def _risk_futures_contracts(draw: st.DrawFn) -> FuturesContract:
    """A FuturesContract drawn from the small RISK_COMMODITY_IDS x RISK_PERIODS pool.

    Draws ``side`` from ``OptionSide`` (short-side-instruments spec, Req 5.2) — as
    ``vanilla_option_contracts``/``spread_option_contracts`` already do — so the base-spec
    Property 22/23 risk suites see both LONG and SHORT forward-like positions."""
    return FuturesContract(
        commodity=BUILT_IN_COMMODITIES[draw(st.sampled_from(RISK_COMMODITY_IDS))],
        delivery_period=draw(st.sampled_from(RISK_PERIODS)),
        contract_price=draw(PRICES),
        notional=draw(NOTIONALS),
        side=draw(st.sampled_from(OptionSide)),
    )


@st.composite
def vanilla_option_contracts(draw: st.DrawFn) -> VanillaOptionContract:
    """A valid ``VanillaOptionContract`` drawn from the shared ``RISK_COMMODITY_IDS`` x
    ``RISK_PERIODS`` pool (portfolio-native-pricers spec, Req 18.2), so books built from
    it overlap the same (commodity, period) cells as ``_risk_futures_contracts`` and
    exercise base-spec Properties 22/23/27/29 through a native option position."""
    commodity_id = draw(st.sampled_from(RISK_COMMODITY_IDS))
    period = draw(st.sampled_from(RISK_PERIODS))
    forward = draw(_OPTION_FORWARDS)
    sigma = draw(_OPTION_SIGMAS)
    time_to_expiry = draw(_OPTION_EXPIRIES)
    strike = _bounded_strike(draw, forward, sigma, time_to_expiry)
    return VanillaOptionContract(
        commodity=BUILT_IN_COMMODITIES[commodity_id],
        delivery_period=period,
        option_type=draw(st.sampled_from(OptionType)),
        strike=strike,
        notional=draw(NOTIONALS),
        side=draw(st.sampled_from(OptionSide)),
    )


@st.composite
def spread_option_contracts(draw: st.DrawFn) -> SpreadOptionContract:
    """A valid ``SpreadOptionContract`` over two distinct commodities drawn from the
    shared ``RISK_COMMODITY_IDS`` x ``RISK_PERIODS`` pool (Req 18.2); strike mixes
    exactly-zero (Margrabe) and positive (Kirk) draws, and ``leg2_weight`` sometimes
    departs from ``1.0`` to exercise the spark-spread chain-rule branch."""
    commodity_1, commodity_2 = draw(
        st.tuples(st.sampled_from(RISK_COMMODITY_IDS), st.sampled_from(RISK_COMMODITY_IDS)).filter(
            lambda pair: pair[0] != pair[1]
        )
    )
    period = draw(st.sampled_from(RISK_PERIODS))
    return SpreadOptionContract(
        commodity_1=commodity_1,
        commodity_2=commodity_2,
        delivery_period=period,
        strike=draw(st.one_of(st.just(0.0), st.floats(min_value=0.01, max_value=200.0))),
        notional=draw(NOTIONALS),
        leg2_weight=draw(st.floats(min_value=0.1, max_value=5.0)),
        side=draw(st.sampled_from(OptionSide)),
    )


@st.composite
def cached_asset_valuations(draw: st.DrawFn) -> CachedAssetValuation:
    """A valid ``CachedAssetValuation`` drawn from the shared ``RISK_COMMODITY_IDS`` x
    ``RISK_PERIODS`` pool (portfolio-native-pricers spec, Req 18.2/19), so books built
    from it overlap the same (commodity, period) cells as every other risk-factor
    generator and exercise base-spec Properties 22/23/27/29 through this DEFERRED-roadmap
    passthrough instrument too."""
    delta_keys = draw(
        st.sets(
            st.tuples(st.sampled_from(RISK_COMMODITY_IDS), st.sampled_from(RISK_PERIODS)),
            max_size=3,
        )
    )
    delta = {key: draw(_DELTA_EXPOSURES) for key in sorted(delta_keys)}
    return CachedAssetValuation(
        asset_id=draw(st.sampled_from(("asset-1", "asset-2", "asset-3"))),
        npv=draw(st.floats(min_value=-1_000_000.0, max_value=1_000_000.0)),
        delta=delta,
        valuation_date=draw(st.sampled_from(RISK_PERIODS)).last_day,
        source=draw(st.sampled_from(ValuationSource)),
        standard_error=draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=10_000.0))),
    )


@st.composite
def cap_floor_strip_contracts(draw: st.DrawFn) -> CapFloorStripContract:
    """A valid ``CapFloorStripContract`` drawn from the shared ``RISK_COMMODITY_IDS`` x
    ``RISK_PERIODS`` pool (portfolio-native-pricers spec, Req 18.2/20)."""
    commodity_id = draw(st.sampled_from(RISK_COMMODITY_IDS))
    periods = tuple(sorted(draw(st.sets(st.sampled_from(RISK_PERIODS), min_size=1, max_size=6))))
    return CapFloorStripContract(
        commodity=BUILT_IN_COMMODITIES[commodity_id],
        schedule=DeliverySchedule(periods),
        cap_floor_type=draw(st.sampled_from(CapFloorType)),
        strike=draw(st.floats(min_value=0.01, max_value=200.0)),
        notional=draw(NOTIONALS),
        side=draw(st.sampled_from(OptionSide)),
    )


@st.composite
def priced_positions(draw: st.DrawFn, min_deltas: int = 0, max_deltas: int = 4) -> PricedPosition:
    """A valuated position for the risk engine: finite npv and a delta mapping whose
    keys come from the small ``RISK_COMMODITY_IDS`` x ``RISK_PERIODS`` pool, so books
    drawn from this strategy overlap on cells (Properties 21-24). ``min_deltas=0``
    admits empty-delta positions (excluded by the engine as ``missing_delta``).

    ``instrument`` is drawn across futures, vanilla options, spread options, a cached
    asset valuation, and a cap/floor strip (Req 18.2, extended by the DEFERRED-roadmap
    Req 19/20 instruments): ``PricedPosition``/``aggregate_delta``/``RiskEngine`` never
    inspect the instrument type itself, so this only proves those base-spec properties
    (22, 23, 27, 29) hold regardless of which natively-priced instrument produced the
    position.
    """
    delta_keys = draw(
        st.sets(
            st.tuples(st.sampled_from(RISK_COMMODITY_IDS), st.sampled_from(RISK_PERIODS)),
            min_size=min_deltas,
            max_size=max_deltas,
        )
    )
    delta = {key: draw(_DELTA_EXPOSURES) for key in sorted(delta_keys)}
    instrument = draw(
        st.one_of(
            _risk_futures_contracts(),
            vanilla_option_contracts(),
            spread_option_contracts(),
            cached_asset_valuations(),
            cap_floor_strip_contracts(),
        )
    )
    return PricedPosition(
        position=Position(instrument=instrument),
        npv=draw(st.floats(min_value=-1_000_000.0, max_value=1_000_000.0)),
        delta=delta,
    )


_LOCATIONS: Final[tuple[str, ...]] = ("DE_FRA", "NL_AMS", "FR_PAR")
_TEMPS_CELSIUS: Final[st.SearchStrategy[float]] = st.floats(min_value=-30.0, max_value=45.0)


@st.composite
def temperature_frames(draw: st.DrawFn, min_rows: int = 1, max_rows: int = 30) -> pl.DataFrame:
    """A Polars frame with the ``degree_days`` input columns (``location``, ``date``,
    ``temp_celsius``) over drawn locations/dates/temperatures (Property 39)."""
    import polars as pl  # runtime import, mirroring the library's lazy-polars style

    rows = draw(st.integers(min_value=min_rows, max_value=max_rows))
    return pl.DataFrame(
        {
            "location": [draw(st.sampled_from(_LOCATIONS)) for _ in range(rows)],
            "date": [
                draw(st.dates(min_value=date(2024, 1, 1), max_value=date(2026, 12, 31)))
                for _ in range(rows)
            ],
            "temp_celsius": [draw(_TEMPS_CELSIUS) for _ in range(rows)],
        }
    )


# --- Task 77 / Task 84 additions (Properties 47-74) ----------------------------------
#
# Additive only (below the marker): matrix / vector strategies for the VaR, covariance,
# hedging and simulation property suites. (The ``numpy`` / ``NDArray`` imports these use
# live in the top import block, as ruff requires module-level imports at the top.)

_COV_ENTRIES: Final[st.SearchStrategy[float]] = st.floats(
    min_value=-3.0, max_value=3.0, allow_nan=False, allow_infinity=False
)
# Delta entries: exactly zero, or a magnitude in ``[1e-3, 1000]``. The lower magnitude
# floor keeps ``deltaᵀΣδ`` (hence the delta-gamma cumulant denominators) well clear of
# subnormal float underflow — matching this module's "well-conditioned regions" contract —
# while still exercising the zero-delta boundary and a broad realistic range.
_DELTA_ENTRIES: Final[st.SearchStrategy[float]] = st.one_of(
    st.just(0.0),
    st.floats(min_value=1e-3, max_value=1_000.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-1_000.0, max_value=-1e-3, allow_nan=False, allow_infinity=False),
)
_RETURN_ENTRIES: Final[st.SearchStrategy[float]] = st.floats(
    min_value=-0.5, max_value=0.5, allow_nan=False, allow_infinity=False
)
# Gamma (second-order) entries: zero or magnitude in ``[1e-3, 3]``. The floor keeps the
# quadratic-form cumulants (whose ``skewness = kappa3 / kappa2**1.5`` divides by a
# ``**1.5`` power) clear of subnormal underflow, in line with the well-conditioned contract.
_GAMMA_ENTRIES: Final[st.SearchStrategy[float]] = st.one_of(
    st.just(0.0),
    st.floats(min_value=1e-3, max_value=3.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-3.0, max_value=-1e-3, allow_nan=False, allow_infinity=False),
)


def _square(draw: st.DrawFn, n: int, elements: st.SearchStrategy[float]) -> NDArray[np.float64]:
    """Draw an ``(n, n)`` ``float64`` matrix with entries from ``elements``."""
    rows = draw(st.lists(st.lists(elements, min_size=n, max_size=n), min_size=n, max_size=n))
    matrix: NDArray[np.float64] = np.array(rows, dtype=np.float64)
    return matrix


def _symmetrize(matrix: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return the symmetric part ``(M + Mᵀ)/2`` as ``float64``."""
    result: NDArray[np.float64] = np.asarray(0.5 * (matrix + matrix.T), dtype=np.float64)
    return result


@st.composite
def spd_covariances(draw: st.DrawFn, min_dim: int = 1, max_dim: int = 5) -> NDArray[np.float64]:
    """A symmetric positive-*definite* covariance ``A·Aᵀ + 1e-3·I`` (dimension in
    ``[min_dim, max_dim]``). Definiteness guarantees the parametric-VaR PSD gate accepts it
    and the variance-minimizing-hedge system is non-singular (Properties 47, 48, 54)."""
    n = draw(st.integers(min_value=min_dim, max_value=max_dim))
    a = _square(draw, n, _COV_ENTRIES)
    cov: NDArray[np.float64] = a @ a.T + 1e-3 * np.eye(n)
    return _symmetrize(cov)


@st.composite
def deltas_and_covariance(
    draw: st.DrawFn, min_dim: int = 1, max_dim: int = 5
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """``(deltas, cov)``: a finite delta vector and a conformable SPD covariance
    (Properties 47, 48)."""
    cov = draw(spd_covariances(min_dim=min_dim, max_dim=max_dim))
    n = int(cov.shape[0])
    deltas: NDArray[np.float64] = np.array(
        draw(st.lists(_DELTA_ENTRIES, min_size=n, max_size=n)), dtype=np.float64
    )
    return deltas, cov


def symmetric_matrices(dim: int) -> st.SearchStrategy[NDArray[np.float64]]:
    """Strategy for a symmetric ``(dim, dim)`` matrix (a valid gamma; need not be PSD)."""
    return st.lists(
        st.lists(_GAMMA_ENTRIES, min_size=dim, max_size=dim), min_size=dim, max_size=dim
    ).map(lambda rows: _symmetrize(np.array(rows, dtype=np.float64)))


@st.composite
def correlation_matrices(
    draw: st.DrawFn, min_dim: int = 2, max_dim: int = 4
) -> NDArray[np.float64]:
    """A symmetric, unit-diagonal, PSD correlation matrix with entries in ``[-1, 1]``,
    obtained by normalising an SPD Gram matrix (Properties 60, 72)."""
    n = draw(st.integers(min_value=min_dim, max_value=max_dim))
    a = _square(draw, n, _COV_ENTRIES)
    cov = a @ a.T + 1e-6 * np.eye(n)
    inv_std = 1.0 / np.sqrt(np.diag(cov))
    r = inv_std[:, None] * cov * inv_std[None, :]
    r = np.clip(r, -1.0, 1.0)
    np.fill_diagonal(r, 1.0)
    return _symmetrize(r)


@st.composite
def return_matrices(
    draw: st.DrawFn,
    min_obs: int = 2,
    max_obs: int = 30,
    min_assets: int = 1,
    max_assets: int = 4,
) -> NDArray[np.float64]:
    """A finite ``(n_obs, n_assets)`` return matrix (oldest row first) for the covariance
    estimators (Property 49)."""
    n_obs = draw(st.integers(min_value=min_obs, max_value=max_obs))
    n_assets = draw(st.integers(min_value=min_assets, max_value=max_assets))
    rows = draw(
        st.lists(
            st.lists(_RETURN_ENTRIES, min_size=n_assets, max_size=n_assets),
            min_size=n_obs,
            max_size=n_obs,
        )
    )
    matrix: NDArray[np.float64] = np.array(rows, dtype=np.float64)
    return matrix
