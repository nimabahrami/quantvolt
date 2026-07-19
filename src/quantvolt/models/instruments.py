"""Instrument hierarchy (all instruments are data — kept in one module).

Every instrument is a frozen, slotted value object. Granularity is the single
shared ``Granularity`` from ``schedule.py``, not an instrument-local enum. Validation
is eager (``__post_init__``) and only rejects
quantities that are physically meaningless: notional and plant heat rate must be
strictly positive, and plant cost/emissions non-negative. Prices, contract prices, and
swap fixed rates are left unconstrained — negative power prices and negative fixed legs
are real market outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from .._validation import require_non_empty, require_non_negative, require_positive
from ..exceptions import ValidationError
from .commodity import CommodityConfig
from .schedule import DeliveryPeriod, DeliverySchedule, Granularity


class ValuationSource(StrEnum):
    """Provenance tag for a valuation regime: the shared vocabulary a caller propagates
    onto a ``Position``'s ``tags`` so that downstream risk/portfolio code can tell how a
    number was produced.

    Defined here (not in ``assets/long_dated.py``, which produces two of its three
    values) because this leaf-ish module is importable from both ``assets/long_dated.py``
    (via ``portfolio/model.py``) and from ``CachedAssetValuation`` below without creating
    an import cycle.

    - ``FORWARD`` / ``PROJECTED``: the long-dated valuation-governance regimes produced by
      ``quantvolt.assets.long_dated.valuation_benchmark``.
    - ``SIMULATED``: a precomputed LSMC/dispatch valuation cache, produced by
      ``CachedAssetValuation``; neither a liquid forward quote nor a simple
      projected-spot-plus-premium figure, so it is tagged as its own third regime rather
      than folded into ``PROJECTED``.
    """

    FORWARD = "forward"  # liquid forward curve covers the period
    PROJECTED = "projected"  # projected from a spot model + corporate premium
    SIMULATED = "simulated"  # precomputed LSMC/dispatch cache


class SettlementType(StrEnum):
    """How a contract settles at delivery."""

    PHYSICAL = "physical"  # Actual delivery of the commodity
    FINANCIAL = "financial"  # Cash settlement against an index


class TransportDirection(StrEnum):
    """Permitted flow direction of a transmission (power) or pipeline (gas) right.

    ``A_TO_B`` / ``B_TO_A`` are one-way rights (origin A -> destination B, or the
    reverse). ``BIDIRECTIONAL`` is a single capacity unit usable in either direction
    per period; the holder commits it to the economically best flow, so a
    bidirectional right is worth no more than owning both one-way rights.
    """

    A_TO_B = "a_to_b"
    B_TO_A = "b_to_a"
    BIDIRECTIONAL = "bidirectional"


class RiskType(StrEnum):
    """Risk categories for derivatives and physical positions."""

    EXECUTION = "execution"  # Trade cannot be executed at the expected price
    BASIS = "basis"  # Hedge instrument imperfectly correlated with exposure
    LIQUIDITY = "liquidity"  # Cannot exit without price impact
    CREDIT = "credit"  # Counterparty default
    STORAGE = "storage"  # Physical storage constraints
    TRANSMISSION = "transmission"  # Pipeline / congestion constraints


@dataclass(frozen=True, slots=True)
class InstrumentPriceRecord:
    """An observed price for a commodity over a delivery period."""

    instrument_id: str
    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    price: float  # may be negative (negative power prices are real)


class OptionType(StrEnum):
    """Whether a vanilla option is a call or a put."""

    CALL = "call"
    PUT = "put"


class OptionSide(StrEnum):
    """Direction of a position, expressed only through ``side`` (never a signed notional):
    notional is always positive; ``LONG`` is a holder/buyer, ``SHORT`` a writer/seller.

    Also governs the direction of the forward-like instruments (``FuturesContract``,
    ``ForwardContract``, ``SwapContract``). It is deliberately named ``OptionSide`` (not a
    generic ``Side``) to keep the public facade export unchanged; the members are the
    plain ``LONG``/``SHORT`` pair, correct for any two-sided position.
    """

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class FuturesContract:
    """Exchange-traded futures: standardised, margined, typically financial settlement.

    Direction lives only in ``side``; ``notional`` is always strictly positive. A
    ``SHORT`` future prices to the exact negation of the ``LONG`` position
    (``portfolio.valuation._price_forward_like`` sign-flips npv and delta), exactly as
    ``VanillaOptionContract`` does. ``side`` defaults to ``LONG``.
    """

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    contract_price: float  # may be negative
    notional: float
    granularity: Granularity = Granularity.MONTHLY
    settlement_type: SettlementType = SettlementType.FINANCIAL
    side: OptionSide = OptionSide.LONG

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class ForwardContract:
    """Bilateral forward: customisable, OTC, physical or financial settlement.

    ``counterparty`` is retained for credit-risk tracking. Direction lives only in
    ``side``; ``notional`` is always strictly positive and ``side`` defaults to ``LONG``.
    """

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    contract_price: float  # fixed payment; may be negative
    notional: float
    granularity: Granularity = Granularity.MONTHLY
    settlement_type: SettlementType = SettlementType.PHYSICAL
    counterparty: str | None = None
    side: OptionSide = OptionSide.LONG

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class SwapContract:
    """Fixed-for-floating swap: OTC, customisable, financial settlement.

    Direction lives only in ``side``: ``LONG`` is the pay-fixed / receive-floating leg
    (the pricer's native perspective), ``SHORT`` its exact negation (receive-fixed /
    pay-floating). ``notional`` is always strictly positive and ``side`` defaults to
    ``LONG``.
    """

    commodity: CommodityConfig
    fixed_rate: float  # may be negative
    floating_index: str  # e.g. "TTF_DA", "EPEX_SPOT_DE"
    notional: float
    schedule: DeliverySchedule
    granularity: Granularity = Granularity.MONTHLY
    side: OptionSide = OptionSide.LONG

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class VanillaOptionContract:
    """A European vanilla option on one commodity's forward.

    Priced natively by ``portfolio.valuation._price_vanilla_option``, which delegates to
    ``quantvolt.pricing.vanilla.price_vanilla_option`` (Black-76). Direction lives only
    in ``side``; ``notional`` is always strictly positive.

    ``expiry`` defaults to ``None``, in which case the pricer treats expiry as
    ``delivery_period.last_day``, the same decision-horizon convention
    ``quantvolt.pricing.tolling`` uses (the option is exercised over the whole delivery
    period, not before it).

    Black-76 requires a strictly positive forward and strike. A delivery period whose
    observed forward is ``<= 0`` (a real occurrence for European power) makes this
    contract unpriceable under Black-76: the pricer propagates the kernel's
    ``ValidationError`` rather than clamping or flooring the forward. For a forward that
    may be zero or negative, price the equivalent request with the separate Bachelier
    (normal-model) pricer, ``quantvolt.pricing.bachelier.price_bachelier_option``;
    this library never switches models automatically.
    """

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    option_type: OptionType
    strike: float
    notional: float
    side: OptionSide = OptionSide.LONG
    expiry: date | None = None

    def __post_init__(self) -> None:
        require_positive("strike", self.strike)
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class SpreadOptionContract:
    """A spread (or spark-spread) option between two forward-curve commodities.

    Priced natively by ``portfolio.valuation._price_spread_option``, which delegates to
    ``quantvolt.pricing.spread_option.price_spread_option`` (``leg2_weight == 1.0``,
    Margrabe/Kirk selection by strike) or
    ``quantvolt.pricing.spread_option.price_spark_spread_option`` (``leg2_weight != 1.0``,
    e.g. a heat rate).

    ``commodity_1`` / ``commodity_2`` are forward-curve keys (``MarketData.curve_for``),
    not ``CommodityConfig`` objects; the two legs may live on different curves (e.g.
    power vs. gas). ``strike == 0.0`` selects the exact Margrabe exchange-option branch;
    any other non-negative strike selects Kirk's approximation. ``expiry`` defaults to
    ``delivery_period.last_day``, exactly as ``VanillaOptionContract``.
    """

    commodity_1: str
    commodity_2: str
    delivery_period: DeliveryPeriod
    strike: float
    notional: float
    leg2_weight: float = 1.0
    side: OptionSide = OptionSide.LONG
    expiry: date | None = None

    def __post_init__(self) -> None:
        require_non_negative("strike", self.strike)
        require_positive("notional", self.notional)
        require_positive("leg2_weight", self.leg2_weight)


@dataclass(frozen=True, slots=True)
class PlantConfig:
    """Thermal-plant conversion parameters."""

    heat_rate: float  # MWh_fuel / MWh_power
    variable_om_cost: float  # per MWh
    emissions_intensity: float  # tCO2 / MWh_fuel
    fuel_type: Literal["gas", "coal"]

    def __post_init__(self) -> None:
        require_positive("heat_rate", self.heat_rate)
        require_non_negative("variable_om_cost", self.variable_om_cost)
        require_non_negative("emissions_intensity", self.emissions_intensity)


def _validate_transport_right(
    quantity: float,
    tariff: float,
    loss: float,
    capacity: float | None,
    reverse_tariff: float | None,
) -> None:
    """Shared eager validation for transmission and pipeline rights.

    ``quantity`` (Q) and ``tariff`` (T_AB) must be non-negative; ``loss`` must lie
    in the half-open interval ``[0, 1)`` (a 100% loss would deliver nothing and is
    rejected); an optional ``capacity`` cap must be strictly positive; an optional
    ``reverse_tariff`` (T_BA, used by a bidirectional right) must be non-negative.
    Every message names the offending field and the violated constraint.
    """
    require_non_negative("quantity", quantity)
    require_non_negative("tariff", tariff)
    if not 0.0 <= loss < 1.0:
        raise ValidationError(f"loss must be in [0, 1), got {loss!r}")
    if capacity is not None:
        require_positive("capacity", capacity)
    if reverse_tariff is not None:
        require_non_negative("reverse_tariff", reverse_tariff)


@dataclass(frozen=True, slots=True)
class TransmissionRight:
    """A right to move power from origin hub A to destination hub B.

    The per-period payoff to the holder is ``Q_delivered * max(P_B - P_A - T_AB, 0)``:
    buy at the origin ``P_A``, pay the transport tariff ``T_AB``, sell at the
    destination ``P_B``, an option exercised only when the locational spread covers
    the tariff. ``delivered = quantity * (1 - loss)``, further capped by ``capacity``.

    Fields:
        origin: commodity_id of hub A (the origin forward curve). Matched against
            the origin curve's commodity when priced.
        destination: commodity_id of hub B (the destination forward curve).
        tariff: per-period transport cost T_AB (>= 0), in the price unit.
        quantity: per-period available quantity Q (>= 0).
        schedule: the delivery periods the right covers.
        direction: A_TO_B (default), B_TO_A, or BIDIRECTIONAL.
        loss: transmission loss fraction in [0, 1); delivered = Q * (1 - loss).
        capacity: optional physical cap; effective quantity = min(Q, capacity).
        reverse_tariff: T_BA (>= 0) for the B->A leg of a BIDIRECTIONAL right;
            when omitted a bidirectional right reuses ``tariff`` symmetrically.
    """

    origin: str
    destination: str
    tariff: float
    quantity: float
    schedule: DeliverySchedule
    direction: TransportDirection = TransportDirection.A_TO_B
    loss: float = 0.0
    capacity: float | None = None
    reverse_tariff: float | None = None

    def __post_init__(self) -> None:
        _validate_transport_right(
            self.quantity, self.tariff, self.loss, self.capacity, self.reverse_tariff
        )


@dataclass(frozen=True, slots=True)
class PipelineRight:
    """A right to move gas from origin hub A to destination hub B.

    Economically identical to ``TransmissionRight``: same payoff
    ``Q_delivered * max(P_B - P_A - T_AB, 0)`` and the same field set, differing only
    in intent (gas pipeline capacity rather than power transmission). Kept a distinct
    type so a book never silently conflates power transmission with gas transport;
    both are priced by the one ``value_transport_right`` engine.

    See ``TransmissionRight`` for the field semantics.
    """

    origin: str
    destination: str
    tariff: float
    quantity: float
    schedule: DeliverySchedule
    direction: TransportDirection = TransportDirection.A_TO_B
    loss: float = 0.0
    capacity: float | None = None
    reverse_tariff: float | None = None

    def __post_init__(self) -> None:
        _validate_transport_right(
            self.quantity, self.tariff, self.loss, self.capacity, self.reverse_tariff
        )


@dataclass(frozen=True, slots=True)
class TollingAgreement:
    """A tolling (conversion) agreement, priced as a strip of clean spread options.

    Lets a tolling position sit in a ``Portfolio`` like any other instrument, backed
    by the stateless kernel ``quantvolt.pricing.tolling.price_tolling_agreement``.

    Priced natively by ``portfolio.valuation._price_tolling_agreement``, which assembles the
    3x3 ``[power, fuel, eua]`` correlation matrix from three pairwise
    ``MarketData.correlations`` entries (via ``correlation_for``, failing loud if any of
    ``(power, fuel)``, ``(power, eua)``, ``(fuel, eua)`` is missing) and delegates to
    ``quantvolt.pricing.tolling.price_tolling_agreement``.

    ``power_commodity_id`` / ``fuel_commodity_id`` / ``eua_commodity_id`` are forward-curve
    keys (``MarketData.curve_for``). Following the kernel's documented "ONE volatility
    surface serves both legs" simplification, the adapter uses
    ``market_data.surface_for(power_commodity_id)`` for every period of the strip.

    Fields:
        plant: Heat rate, variable O&M cost, emissions intensity, fuel type.
        power_commodity_id: Forward-curve key for the power leg.
        fuel_commodity_id: Forward-curve key for the fuel (gas/coal) leg.
        eua_commodity_id: Forward-curve key for the EUA (carbon) leg.
        schedule: The delivery periods the strip covers (1-1200 periods, kernel-enforced).
        capacity: Per-period notional in MWh, strictly positive (default 1.0 -- unit
            capacity, the kernel's historical default).
        settlement_lag_days: Calendar days added to each period's last day to get the
            discount-factor settlement date (default 0, non-negative); does not affect
            the option's time-to-expiry (the kernel's decision-horizon convention).
    """

    plant: PlantConfig
    power_commodity_id: str
    fuel_commodity_id: str
    eua_commodity_id: str
    schedule: DeliverySchedule
    capacity: float = 1.0
    settlement_lag_days: int = 0

    def __post_init__(self) -> None:
        require_positive("capacity", self.capacity)
        require_non_negative("settlement_lag_days", self.settlement_lag_days)


@dataclass(frozen=True, slots=True)
class CachedAssetValuation:
    """A precomputed, staleness-checked LSMC/dispatch valuation cache.

    Folds an expensive Monte-Carlo/dispatch-priced asset (a long-dated power plant,
    storage position, ...) into a ``Portfolio`` as an already-computed number. This
    library does not itself run an LSMC or dispatch engine: it is the caller's
    responsibility to produce ``npv``/``delta`` (e.g. via ``assets.long_dated`` or a
    caller's own simulation) and wrap the result in this type.
    ``portfolio.valuation._price_cached_asset_valuation``, the pricer registered for this
    type, only re-emits this wrapper's ``npv``/``delta`` as a ``PricedPosition``, after
    checking that ``valuation_date`` still matches ``MarketData.valuation_date``. A
    mismatch means the cache is stale relative to the book being valued and the pricer
    raises a ``ValidationError`` naming both dates rather than silently repricing or
    reusing it.

    The pricer also propagates ``source`` onto the re-emitted position's ``tags``
    (downstream risk code, e.g. ``var_applicability_guard``, reads the tag from
    ``position.position.tags``), so a cached/simulated valuation is as visibly tagged as
    a projected-spot one.

    Fields:
        asset_id: Identifier for the underlying asset the cache was computed for -- an audit
            trail back to the LSMC/dispatch run that produced ``npv``/``delta``.
        npv: The precomputed net present value as of ``valuation_date``. Must be finite.
        delta: Precomputed per-``(commodity_id, delivery period)`` exposure, in the same
            convention as every other native pricer's ``PricedPosition.delta``. Defensively
            copied at construction.
        valuation_date: The date the cache was computed as of. Must equal
            ``MarketData.valuation_date`` when priced, or the pricer raises.
        source: The ``ValuationSource`` provenance tag for this cache -- ordinarily
            ``ValuationSource.SIMULATED`` (an LSMC/dispatch cache is neither a liquid
            forward quote nor a simple projected-spot figure); accepted as a field rather than
            hard-coded so a caller with a different provenance can still state it explicitly.
        standard_error: Optional Monte-Carlo standard error of ``npv``, carried through for
            audit. ``None`` for a deterministic dispatch valuation. Must be finite and >= 0
            when given.
    """

    asset_id: str
    npv: float
    delta: Mapping[tuple[str, DeliveryPeriod], float]
    valuation_date: date
    source: ValuationSource
    standard_error: float | None = None

    def __post_init__(self) -> None:
        require_non_empty("asset_id", self.asset_id)
        if not math.isfinite(self.npv):
            raise ValidationError(f"npv must be finite, got {self.npv!r}")
        if self.standard_error is not None:
            require_non_negative("standard_error", self.standard_error)
        object.__setattr__(self, "delta", dict(self.delta))


class CapFloorType(StrEnum):
    """Whether a cap/floor strip prices call-side (``CAP``) or put-side (``FLOOR``)
    caplets/floorlets.

    Mirrors the existing ``Literal["cap", "floor"]`` vocabulary of
    ``quantvolt.pricing.vanilla.CapFloorRequest`` / ``VanillaOptionRequest`` as a typed
    enum field on the instrument, exactly as ``OptionType`` does for
    ``VanillaOptionContract``'s ``Literal["call", "put"]``.
    """

    CAP = "cap"
    FLOOR = "floor"


@dataclass(frozen=True, slots=True)
class CapFloorStripContract:
    """A cap or floor strip on one commodity's forward curve.

    Priced natively by ``portfolio.valuation._price_cap_floor_strip``, which builds one
    ``VanillaOptionRequest`` caplet per ``schedule`` period, forward/vol/discount-factor
    sourced exactly like ``VanillaOptionContract``'s adapter (``actual_365(valuation_date,
    period.last_day)`` time-to-expiry, discount factor at that same date, premium already
    discounted -- never twice), and delegates the assembled strip to
    ``quantvolt.pricing.vanilla.price_cap_floor``.

    ONE ``strike`` and ONE ``notional`` apply to every caplet/floorlet in the strip. This
    mirrors the kernel's own ``CapFloorRequest`` invariant exactly ("a cap/floor strip has
    ONE strike ... and ONE notional"; only forward, discount factor and time-to-expiry vary
    caplet-by-caplet); a per-period notional would let this value object represent a request
    the kernel itself rejects, so it is not offered. There is also no separate ``expiry``
    override field (unlike ``VanillaOptionContract``): each caplet's decision horizon is
    always its own period's ``last_day``, the convention every per-period strip in this
    library already uses (``TollingAgreement``, ``pricing/tolling.py``).

    Fields:
        commodity: The single underlying commodity every caplet/floorlet strikes against.
        schedule: The delivery periods the strip covers (kernel-enforced 1-120 caplets by
            default -- ``price_cap_floor``'s ``max_strip_periods``).
        cap_floor_type: ``CapFloorType.CAP`` (call side) or ``CapFloorType.FLOOR``
            (put side); feeds the kernel's ``option_type`` literal via ``.value``.
        strike: The strip's single cap/floor rate, strictly positive.
        notional: The strip's single per-period notional, strictly positive.
        side: Direction, exactly as ``VanillaOptionContract`` / ``SpreadOptionContract``,
            never a signed notional.
    """

    commodity: CommodityConfig
    schedule: DeliverySchedule
    cap_floor_type: CapFloorType
    strike: float
    notional: float
    side: OptionSide = OptionSide.LONG

    def __post_init__(self) -> None:
        require_positive("strike", self.strike)
        require_positive("notional", self.notional)
