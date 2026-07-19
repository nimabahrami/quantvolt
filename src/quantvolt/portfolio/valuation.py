"""Portfolio valuation — dispatch each instrument to its pricer and aggregate (Task 61).

Composite (value the whole book) + Replace-Conditional-with-Dispatch (instrument type -> pricer).
New instrument kinds are supported by registering an entry — in :data:`DEFAULT_PRICERS` inside
the library, or per call via the ``pricers`` argument of :func:`value_portfolio` — never by
editing ``value_portfolio`` itself (open/closed, Req 13.4).

The produced :class:`~quantvolt.portfolio.model.PricedPosition` objects are exactly what
``risk.aggregation.aggregate_delta`` / ``RiskEngine`` and mark-to-market consume (Req 13.5),
so the flow is: instruments -> ``Portfolio`` -> ``value_portfolio`` -> ``PricedPosition`` ->
risk / mark-to-market.

Every built-in pricer also populates ``PricedPosition.reference_prices`` with the forward
curve price observed for each ``delta`` entry's ``(commodity_id, delivery period)`` key.
``RiskEngine.apply_scenario`` uses this to scale a *relative* named/user scenario shock
(:mod:`quantvolt.risk.scenarios`) into currency P&L (``delta x reference_price x shock``);
see that module and :mod:`quantvolt.risk.engine` for the full convention.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np

from .._validation import require_correlation
from ..exceptions import ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.greeks import Greeks
from ..models.instruments import (
    CachedAssetValuation,
    CapFloorStripContract,
    ForwardContract,
    FuturesContract,
    OptionSide,
    PipelineRight,
    SpreadOptionContract,
    SwapContract,
    TollingAgreement,
    TransmissionRight,
    VanillaOptionContract,
)
from ..models.schedule import DeliveryPeriod
from ..models.vol_surface import VolatilitySurface
from ..numerics.daycount import actual_365
from ..pricing.futures import price_futures
from ..pricing.spread_option import (
    SpreadOptionRequest,
    price_spark_spread_option,
    price_spread_option,
)
from ..pricing.swap import price_swap
from ..pricing.tolling import price_tolling_agreement
from ..pricing.transmission_right import value_transport_right
from ..pricing.vanilla import (
    CapFloorRequest,
    VanillaOptionRequest,
    price_cap_floor,
    price_vanilla_option,
)
from .model import Portfolio, Position, PricedPosition


@dataclass(frozen=True, slots=True)
class MarketData:
    """The market inputs needed to value a portfolio (Req 13.2; portfolio-native-pricers
    Req 1: ``vol_surfaces`` / ``correlations`` extension).

    ``forward_curves``, ``vol_surfaces`` and ``correlations`` are all defensively copied
    into fresh ``dict``s at construction (the ``object.__setattr__`` pattern), so later
    mutation of a caller's mapping cannot reach into this frozen value object. The stored
    copies are treated as immutable by convention from then on — nothing in the library
    writes to them. ``vol_surfaces`` and ``correlations`` both default to empty, so every
    existing ``MarketData(...)`` call site (and the futures/forward/swap/transport
    pricers, which never touch either field) continues to work unchanged.

    Every ``correlations`` value is validated once, here, to lie strictly inside
    ``(-1, 1)`` via :func:`~quantvolt._validation.require_correlation`; :meth:`correlation_for`
    is therefore a pure lookup that never re-validates.
    """

    forward_curves: dict[str, ForwardCurve]  # keyed by commodity_id
    discount_curve: DiscountCurve
    valuation_date: date
    vol_surfaces: dict[str, VolatilitySurface] = field(default_factory=dict)
    correlations: dict[tuple[str, str], float] = field(default_factory=dict)  # ordered pair key

    def __post_init__(self) -> None:
        object.__setattr__(self, "forward_curves", dict(self.forward_curves))
        object.__setattr__(self, "vol_surfaces", dict(self.vol_surfaces))
        object.__setattr__(self, "correlations", dict(self.correlations))
        for key, value in self.correlations.items():
            require_correlation(f"correlations[{key!r}]", value)

    def curve_for(self, commodity_id: str) -> ForwardCurve:
        """Return the forward curve for ``commodity_id``; raise if absent (Task 61).

        An intrinsic query (Tell-Don't-Ask): callers ask the market data for the
        curve instead of indexing into ``forward_curves`` themselves.

        Raises:
            ValidationError: If no curve is registered for ``commodity_id``, naming
                the missing commodity and listing the available ones.
        """
        curve = self.forward_curves.get(commodity_id)
        if curve is None:
            available = ", ".join(repr(key) for key in sorted(self.forward_curves)) or "none"
            raise ValidationError(
                f"market_data.forward_curves has no curve for commodity_id "
                f"{commodity_id!r}; available commodities: {available}"
            )
        return curve

    def surface_for(self, commodity_id: str) -> VolatilitySurface:
        """Return the volatility surface for ``commodity_id``; raise if absent.

        An intrinsic query (Tell-Don't-Ask), mirroring :meth:`curve_for`'s shape.

        Raises:
            ValidationError: If no surface is registered for ``commodity_id``, naming
                the missing commodity and listing the available ones.
        """
        surface = self.vol_surfaces.get(commodity_id)
        if surface is None:
            available = ", ".join(repr(key) for key in sorted(self.vol_surfaces)) or "none"
            raise ValidationError(
                f"market_data.vol_surfaces has no surface for commodity_id "
                f"{commodity_id!r}; available commodities: {available}"
            )
        return surface

    def correlation_for(self, a: str, b: str) -> float:
        """Return the correlation between ``a`` and ``b``, symmetric in argument order.

        Looks up ``(a, b)`` first, then ``(b, a)``; a pure query that never mutates and
        never re-validates the ``(-1, 1)`` range (already checked once at construction).

        Raises:
            ValidationError: If neither ``(a, b)`` nor ``(b, a)`` is registered, naming
                the missing pair and listing the available pair keys.
        """
        if (a, b) in self.correlations:
            return self.correlations[(a, b)]
        if (b, a) in self.correlations:
            return self.correlations[(b, a)]
        available = ", ".join(repr(key) for key in sorted(self.correlations)) or "none"
        raise ValidationError(
            f"market_data.correlations has no entry for pair {(a, b)!r} (or its reverse "
            f"{(b, a)!r}); available pairs: {available}"
        )


@dataclass(frozen=True, slots=True)
class PortfolioValuation:
    """Aggregate NPV plus per-position results, in portfolio order (Req 13.2, 13.3)."""

    total_npv: float  # sum over ``priced`` only; ``unpriced`` never contributes
    priced: tuple[PricedPosition, ...]
    unpriced: tuple[Position, ...]  # instrument type had no registered pricer


# --- Dispatch: instrument type -> how to value one position (Task 61) ---

# A pricer adapter values one position against the market data. Registered per
# instrument type; adding a type means adding an entry, not editing value_portfolio.
Pricer = Callable[[Position, MarketData], PricedPosition]


def _signed(
    side: OptionSide,
    *,
    npv: float,
    delta: Mapping[tuple[str, DeliveryPeriod], float],
    greeks: Greeks | None = None,
) -> tuple[float, dict[tuple[str, DeliveryPeriod], float], Greeks | None]:
    """Apply the SHORT-negates-LONG sign convention once, for every native pricer.

    ``short-side-instruments`` spec convention: ``sign`` is ``+1.0`` for ``OptionSide.LONG``
    and ``-1.0`` for ``OptionSide.SHORT``. It flips ``npv``, every value in ``delta``, and
    ``greeks`` (via :meth:`~quantvolt.models.greeks.Greeks.scale`) when given.

    ``reference_prices`` is **never** scaled -- neither here nor by any of this helper's
    callers -- because it stays the raw observed forward/curve price. The ``RiskEngine``'s
    scenario P&L (``delta x reference_price x shock``) already flips for a SHORT position
    through the flipped ``delta`` alone; scaling ``reference_prices`` too would double-flip it.
    """
    sign = 1.0 if side is OptionSide.LONG else -1.0
    signed_delta = {key: sign * value for key, value in delta.items()}
    signed_greeks = greeks.scale(sign) if greeks is not None else None
    return sign * npv, signed_delta, signed_greeks


def _price_forward_like(position: Position, market_data: MarketData) -> PricedPosition:
    """FuturesContract / ForwardContract via pricing.futures (Req 13.2).

    Direction lives in ``instrument.side`` (``short-side-instruments`` spec); see
    :func:`_signed` for the shared sign convention applied to ``npv``/``delta``.
    """
    instrument = position.instrument
    if not isinstance(instrument, FuturesContract | ForwardContract):
        raise ValidationError(
            "position.instrument must be a FuturesContract or ForwardContract for "
            f"this pricer, got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    curve = market_data.curve_for(commodity_id)
    result = price_futures(
        instrument,
        curve,
        market_data.valuation_date,
        market_data.discount_curve,
    )
    period = instrument.delivery_period
    key = (commodity_id, period)
    npv, delta, _ = _signed(instrument.side, npv=result.npv, delta={key: result.delta})
    return PricedPosition(
        position=position,
        npv=npv,
        delta=delta,
        reference_prices={key: curve.price_at(period)},
    )


def _price_swap(position: Position, market_data: MarketData) -> PricedPosition:
    """SwapContract via pricing.swap — one delta entry per schedule period (Req 13.2).

    Direction lives in ``instrument.side`` (``short-side-instruments`` spec): a ``SHORT``
    (receive-fixed / pay-floating) swap is the exact negation of the ``LONG`` (pay-fixed /
    receive-floating) perspective the kernel prices; see :func:`_signed` for the shared
    sign convention applied to ``npv`` and every per-period ``delta``.
    """
    instrument = position.instrument
    if not isinstance(instrument, SwapContract):
        raise ValidationError(
            "position.instrument must be a SwapContract for this pricer, "
            f"got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    curve = market_data.curve_for(commodity_id)
    result = price_swap(instrument, curve, market_data.discount_curve)
    raw_delta = {
        (commodity_id, period): period_delta
        for period, period_delta in zip(instrument.schedule.periods, result.delta, strict=True)
    }
    reference_prices = {
        (commodity_id, period): curve.price_at(period) for period in instrument.schedule.periods
    }
    npv, delta, _ = _signed(instrument.side, npv=result.npv, delta=raw_delta)
    return PricedPosition(
        position=position, npv=npv, delta=delta, reference_prices=reference_prices
    )


def _price_transport_right(position: Position, market_data: MarketData) -> PricedPosition:
    """TransmissionRight / PipelineRight via pricing.transmission_right (Req 24, Task 80).

    Prices the intrinsic transport value (market data carries no location vols, so no
    extrinsic term) over the shared periods of the origin (hub A) and destination
    (hub B) curves. The per-position ``delta`` carries one entry per (hub, period):
    ``delta_origin`` on the origin commodity and the opposite-signed ``delta_destination``
    on the destination — the right holder is short the origin and long the destination
    (module-level sign convention of :mod:`quantvolt.pricing.transmission_right`).
    """
    instrument = position.instrument
    if not isinstance(instrument, TransmissionRight | PipelineRight):
        raise ValidationError(
            "position.instrument must be a TransmissionRight or PipelineRight for this "
            f"pricer, got {type(instrument).__name__}"
        )
    origin_curve = market_data.curve_for(instrument.origin)
    destination_curve = market_data.curve_for(instrument.destination)
    result = value_transport_right(
        instrument,
        origin_curve,
        destination_curve,
        market_data.discount_curve,
    )
    delta: dict[tuple[str, DeliveryPeriod], float] = {}
    reference_prices: dict[tuple[str, DeliveryPeriod], float] = {}
    for period_value in result.per_period:
        period = period_value.period
        delta[(instrument.origin, period)] = period_value.delta_origin
        delta[(instrument.destination, period)] = period_value.delta_destination
        reference_prices[(instrument.origin, period)] = origin_curve.price_at(period)
        reference_prices[(instrument.destination, period)] = destination_curve.price_at(period)
    return PricedPosition(
        position=position, npv=result.total, delta=delta, reference_prices=reference_prices
    )


def _price_vanilla_option(position: Position, market_data: MarketData) -> PricedPosition:
    """VanillaOptionContract via pricing.vanilla.price_vanilla_option (Req 7).

    Conventions inherited verbatim from :mod:`quantvolt.pricing.tolling` (the in-repo
    anchor for turning a ``DeliveryPeriod`` + ``valuation_date`` into a Black-76 request):
    the discount factor is looked up at ``delivery_period.last_day``, time-to-expiry is
    ``actual_365(valuation_date, expiry or delivery_period.last_day)``, and the kernel
    premium is already discounted — it is never discounted a second time.

    A non-positive observed forward propagates the kernel's own ``ValidationError``
    (Black-76 requires ``forward > 0``); this adapter never clamps or floors it (Req 12).
    """
    instrument = position.instrument
    if not isinstance(instrument, VanillaOptionContract):
        raise ValidationError(
            "position.instrument must be a VanillaOptionContract for this pricer, "
            f"got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    period = instrument.delivery_period
    forward = market_data.curve_for(commodity_id).price_at(period)
    sigma = market_data.surface_for(commodity_id).sigma_at(period)
    settle = period.last_day
    discount_factor = market_data.discount_curve.discount_factor(settle)
    expiry = instrument.expiry or settle
    time_to_expiry = actual_365(market_data.valuation_date, expiry)
    result = price_vanilla_option(
        VanillaOptionRequest(
            option_type=instrument.option_type.value,
            strike=instrument.strike,
            notional=instrument.notional,
            forward=forward,
            sigma=sigma,
            time_to_expiry=time_to_expiry,
            discount_factor=discount_factor,
        )
    )
    key = (commodity_id, period)
    npv, delta, greeks = _signed(
        instrument.side,
        npv=result.premium,
        delta={key: result.greeks.delta},
        greeks=result.greeks,
    )
    return PricedPosition(
        position=position,
        npv=npv,
        delta=delta,
        greeks=greeks,
        reference_prices={key: forward},
    )


def _price_spread_option(position: Position, market_data: MarketData) -> PricedPosition:
    """SpreadOptionContract via pricing.spread_option (Req 8).

    ``leg2_weight == 1.0`` delegates to :func:`~quantvolt.pricing.spread_option.
    price_spread_option`; any other (strictly positive) ``leg2_weight`` delegates to
    :func:`~quantvolt.pricing.spread_option.price_spark_spread_option` with
    ``heat_rate = leg2_weight``, so the leg-2 delta is already chain-ruled back onto the
    raw ``forward2`` by the kernel's documented convention — no extra scaling here.

    ``greeks`` is deliberately left ``None``: a spread option's sensitivity vocabulary
    (``delta1``, ``delta2``, ``vega1``, ``vega2``, ``correlation_sensitivity``) does not
    map onto the single-underlying ``Greeks``, and forcing it would be a category error.
    """
    instrument = position.instrument
    if not isinstance(instrument, SpreadOptionContract):
        raise ValidationError(
            "position.instrument must be a SpreadOptionContract for this pricer, "
            f"got {type(instrument).__name__}"
        )
    commodity_1, commodity_2 = instrument.commodity_1, instrument.commodity_2
    period = instrument.delivery_period
    forward1 = market_data.curve_for(commodity_1).price_at(period)
    forward2 = market_data.curve_for(commodity_2).price_at(period)
    sigma1 = market_data.surface_for(commodity_1).sigma_at(period)
    sigma2 = market_data.surface_for(commodity_2).sigma_at(period)
    correlation = market_data.correlation_for(commodity_1, commodity_2)
    settle = period.last_day
    discount_factor = market_data.discount_curve.discount_factor(settle)
    expiry = instrument.expiry or settle
    time_to_expiry = actual_365(market_data.valuation_date, expiry)
    request = SpreadOptionRequest(
        forward1=forward1,
        forward2=forward2,
        strike=instrument.strike,
        sigma1=sigma1,
        sigma2=sigma2,
        correlation=correlation,
        time_to_expiry=time_to_expiry,
        discount_factor=discount_factor,
        notional=instrument.notional,
    )
    result = (
        price_spread_option(request)
        if instrument.leg2_weight == 1.0
        else price_spark_spread_option(request, instrument.leg2_weight)
    )
    npv, delta, _ = _signed(
        instrument.side,
        npv=result.premium,
        delta={(commodity_1, period): result.delta1, (commodity_2, period): result.delta2},
    )
    return PricedPosition(
        position=position,
        npv=npv,
        delta=delta,
        greeks=None,
        reference_prices={(commodity_1, period): forward1, (commodity_2, period): forward2},
    )


def _price_tolling_agreement(position: Position, market_data: MarketData) -> PricedPosition:
    """TollingAgreement via pricing.tolling.price_tolling_agreement (Req 14).

    Assembles the kernel's required 3x3 ``[power, fuel, eua]`` correlation matrix from
    three pairwise ``MarketData.correlations`` entries via ``correlation_for``, failing
    loud if any of ``(power, fuel)``, ``(power, eua)``, ``(fuel, eua)`` is missing. Per
    the kernel's documented "ONE volatility surface" convention, the power commodity's
    surface serves both the power and the combined fuel+carbon leg for every period.
    """
    instrument = position.instrument
    if not isinstance(instrument, TollingAgreement):
        raise ValidationError(
            "position.instrument must be a TollingAgreement for this pricer, "
            f"got {type(instrument).__name__}"
        )
    power_id = instrument.power_commodity_id
    fuel_id = instrument.fuel_commodity_id
    eua_id = instrument.eua_commodity_id
    power_curve = market_data.curve_for(power_id)
    fuel_curve = market_data.curve_for(fuel_id)
    eua_curve = market_data.curve_for(eua_id)
    vol_surface = market_data.surface_for(power_id)
    rho_power_fuel = market_data.correlation_for(power_id, fuel_id)
    rho_power_eua = market_data.correlation_for(power_id, eua_id)
    rho_fuel_eua = market_data.correlation_for(fuel_id, eua_id)
    correlation_matrix = np.array(
        [
            [1.0, rho_power_fuel, rho_power_eua],
            [rho_power_fuel, 1.0, rho_fuel_eua],
            [rho_power_eua, rho_fuel_eua, 1.0],
        ]
    )
    result = price_tolling_agreement(
        plant=instrument.plant,
        power_curve=power_curve,
        fuel_curve=fuel_curve,
        eua_curve=eua_curve,
        vol_surface=vol_surface,
        correlation_matrix=correlation_matrix,
        schedule=instrument.schedule,
        discount_curve=market_data.discount_curve,
        capacity=instrument.capacity,
        settlement_lag_days=instrument.settlement_lag_days,
    )
    delta: dict[tuple[str, DeliveryPeriod], float] = {}
    reference_prices: dict[tuple[str, DeliveryPeriod], float] = {}
    for period, power_delta, fuel_delta, eua_delta in zip(
        instrument.schedule.periods,
        result.per_period_deltas["power"],
        result.per_period_deltas["fuel"],
        result.per_period_deltas["eua"],
        strict=True,
    ):
        delta[(power_id, period)] = power_delta
        delta[(fuel_id, period)] = fuel_delta
        delta[(eua_id, period)] = eua_delta
        reference_prices[(power_id, period)] = power_curve.price_at(period)
        reference_prices[(fuel_id, period)] = fuel_curve.price_at(period)
        reference_prices[(eua_id, period)] = eua_curve.price_at(period)
    return PricedPosition(
        position=position, npv=result.npv, delta=delta, reference_prices=reference_prices
    )


def _price_cached_asset_valuation(position: Position, market_data: MarketData) -> PricedPosition:
    """CachedAssetValuation passthrough (Req 19, DEFERRED roadmap).

    This adapter never runs an LSMC or dispatch engine (Req 19.2): it only re-emits the
    wrapper's already-computed ``npv``/``delta`` as a ``PricedPosition``, after checking that
    ``instrument.valuation_date`` still matches ``market_data.valuation_date``. A mismatch
    means the cache is stale relative to the book being valued and raises rather than being
    silently repriced or reused, naming both dates.

    The ``ValuationSource`` provenance tag is propagated onto the re-emitted position's
    ``tags`` (the ``assets/long_dated.py`` Property-66 pattern: ``var_applicability_guard`` and
    other risk code read the tag from ``position.position.tags``) via a fresh ``Position``
    built from the original one plus that tag, added only if not already present.
    """
    instrument = position.instrument
    if not isinstance(instrument, CachedAssetValuation):
        raise ValidationError(
            "position.instrument must be a CachedAssetValuation for this pricer, "
            f"got {type(instrument).__name__}"
        )
    if instrument.valuation_date != market_data.valuation_date:
        raise ValidationError(
            f"CachedAssetValuation.valuation_date ({instrument.valuation_date!r}) does not "
            f"match MarketData.valuation_date ({market_data.valuation_date!r}); the cached "
            "LSMC/dispatch valuation is stale relative to the book being valued and "
            "value_portfolio never reprices it (Req 19.2) -- recompute the cache as of the "
            "current valuation date"
        )
    tag = instrument.source.value
    tags = position.tags if tag in position.tags else (*position.tags, tag)
    tagged_position = (
        position if tags is position.tags else dataclasses.replace(position, tags=tags)
    )
    return PricedPosition(
        position=tagged_position,
        npv=instrument.npv,
        delta=dict(instrument.delta),
    )


def _price_cap_floor_strip(position: Position, market_data: MarketData) -> PricedPosition:
    """CapFloorStripContract via pricing.vanilla.price_cap_floor (Req 20, DEFERRED roadmap).

    Builds one caplet/floorlet ``VanillaOptionRequest`` per ``schedule`` period, gathering
    forward/vol/discount-factor exactly like ``_price_vanilla_option``'s single-period adapter
    (``actual_365(valuation_date, period.last_day)`` time-to-expiry, discount factor at that
    same date, premium already discounted -- never twice), then delegates the assembled strip
    to :func:`~quantvolt.pricing.vanilla.price_cap_floor`. Per-period ``delta`` is keyed
    ``(commodity_id, period)`` from each caplet's own (unaggregated) result; the returned
    ``greeks`` is the kernel's own aggregate (summed across periods -- Property 16 / the
    external-validation spec's Property 94 strip-additivity), scaled by side exactly as the
    single-period vanilla adapter scales its own kernel ``Greeks``.
    """
    instrument = position.instrument
    if not isinstance(instrument, CapFloorStripContract):
        raise ValidationError(
            "position.instrument must be a CapFloorStripContract for this pricer, "
            f"got {type(instrument).__name__}"
        )
    commodity_id = instrument.commodity.commodity_id
    curve = market_data.curve_for(commodity_id)
    surface = market_data.surface_for(commodity_id)
    caplets: list[VanillaOptionRequest] = []
    reference_prices: dict[tuple[str, DeliveryPeriod], float] = {}
    for period in instrument.schedule.periods:
        forward = curve.price_at(period)
        sigma = surface.sigma_at(period)
        settle = period.last_day
        discount_factor = market_data.discount_curve.discount_factor(settle)
        time_to_expiry = actual_365(market_data.valuation_date, settle)
        caplets.append(
            VanillaOptionRequest(
                option_type=instrument.cap_floor_type.value,
                strike=instrument.strike,
                notional=instrument.notional,
                forward=forward,
                sigma=sigma,
                time_to_expiry=time_to_expiry,
                discount_factor=discount_factor,
            )
        )
        reference_prices[(commodity_id, period)] = forward
    result = price_cap_floor(
        CapFloorRequest(
            option_type=instrument.cap_floor_type.value,
            strike=instrument.strike,
            notional=instrument.notional,
            caplets=tuple(caplets),
        )
    )
    raw_delta = {
        (commodity_id, period): caplet_result.greeks.delta
        for period, caplet_result in zip(
            instrument.schedule.periods, result.per_period, strict=True
        )
    }
    npv, delta, greeks = _signed(
        instrument.side, npv=result.premium, delta=raw_delta, greeks=result.greeks
    )
    return PricedPosition(
        position=position,
        npv=npv,
        delta=delta,
        greeks=greeks,
        reference_prices=reference_prices,
    )


#: Built-in dispatch table: instrument type -> pricer adapter. A module-level constant,
#: **not** a Singleton (coding-style.md §3) and never mutated: ``value_portfolio`` merges
#: it with any caller-supplied ``pricers`` into a fresh dict per call, so registering an
#: extra instrument type needs no edit to this module (Req 13.4).
DEFAULT_PRICERS: dict[type[Any], Pricer] = {
    FuturesContract: _price_forward_like,
    ForwardContract: _price_forward_like,
    SwapContract: _price_swap,
    TransmissionRight: _price_transport_right,
    PipelineRight: _price_transport_right,
    VanillaOptionContract: _price_vanilla_option,
    SpreadOptionContract: _price_spread_option,
    TollingAgreement: _price_tolling_agreement,
    CachedAssetValuation: _price_cached_asset_valuation,
    CapFloorStripContract: _price_cap_floor_strip,
}


def value_portfolio(
    portfolio: Portfolio,
    market_data: MarketData,
    pricers: Mapping[type[Any], Pricer] | None = None,
) -> PortfolioValuation:
    """Value every position via its registered pricer and aggregate the NPV (Req 13.2-13.6).

    The dispatch registry is :data:`DEFAULT_PRICERS` merged with the caller-supplied
    ``pricers`` (caller entries win) — the open/closed extension seam: new instrument
    types are registered, never edited in (Req 13.4). Positions are processed in
    portfolio order; a position whose instrument type has no registered pricer is
    returned in ``unpriced`` rather than raising, so the rest of the book is still
    valued, and ``total_npv`` sums the priced positions only (Req 13.3).

    Pricing errors — :class:`~quantvolt.exceptions.ExpiredContractError`,
    :class:`~quantvolt.exceptions.MissingTenorError`, a missing forward curve from
    :meth:`MarketData.curve_for` — **propagate**: they are data errors on a position
    the registry *does* know how to price, not registry misses, and silently skipping
    them would hide a mispriced book.

    Inputs are never mutated, and identical inputs produce identical results (Req 13.6).

    **No LSMC or dispatch engine ever runs inside this function** (Req 19.2). A
    :class:`~quantvolt.models.instruments.CachedAssetValuation` position is priced by
    re-emitting its already-computed ``npv``/``delta`` (after a staleness check against
    ``market_data.valuation_date``) — ``value_portfolio`` itself never simulates or
    re-optimises anything; every native pricer here is a thin *validate -> gather inputs ->
    delegate to an existing closed-form kernel -> package a result* orchestration.
    """
    registry: dict[type[Any], Pricer] = {**DEFAULT_PRICERS, **(pricers or {})}
    priced: list[PricedPosition] = []
    unpriced: list[Position] = []
    for position in portfolio.positions:
        pricer = registry.get(type(position.instrument))
        if pricer is None:
            unpriced.append(position)
        else:
            priced.append(pricer(position, market_data))
    return PortfolioValuation(
        total_npv=float(sum(p.npv for p in priced)),
        priced=tuple(priced),
        unpriced=tuple(unpriced),
    )
