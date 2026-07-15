"""Instrument hierarchy (all instruments are data — kept in one module).

Every instrument is a frozen, slotted value object. Granularity is the single
shared :class:`~quantvolt.models.schedule.Granularity` from ``schedule.py`` (Task 3),
not an instrument-local enum. Validation is eager (``__post_init__``) and only rejects
quantities that are physically meaningless: notional and plant heat rate must be
strictly positive, and plant cost/emissions non-negative. Prices, contract prices, and
swap fixed rates are left unconstrained — negative power prices and negative fixed legs
are real market outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .._validation import require_non_negative, require_positive
from ..exceptions import ValidationError
from .commodity import CommodityConfig
from .schedule import DeliveryPeriod, DeliverySchedule, Granularity


class SettlementType(StrEnum):
    """How a contract settles at delivery."""

    PHYSICAL = "physical"  # Actual delivery of the commodity
    FINANCIAL = "financial"  # Cash settlement against an index


class TransportDirection(StrEnum):
    """Permitted flow direction of a transmission (power) or pipeline (gas) right.

    ``A_TO_B`` / ``B_TO_A`` are one-way rights (origin A -> destination B, or the
    reverse). ``BIDIRECTIONAL`` is a single capacity unit usable in *either*
    direction per period — the holder commits it to the economically best flow, so
    a bidirectional right is worth no more than owning both one-way rights (Property
    68 subadditivity).
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


@dataclass(frozen=True, slots=True)
class FuturesContract:
    """Exchange-traded futures — standardised, margined, typically financial settlement."""

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    contract_price: float  # may be negative
    notional: float
    granularity: Granularity = Granularity.MONTHLY
    settlement_type: SettlementType = SettlementType.FINANCIAL

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class ForwardContract:
    """Bilateral forward — customisable, OTC, physical or financial settlement.

    ``counterparty`` is retained for credit-risk tracking.
    """

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    contract_price: float  # fixed payment; may be negative
    notional: float
    granularity: Granularity = Granularity.MONTHLY
    settlement_type: SettlementType = SettlementType.PHYSICAL
    counterparty: str | None = None

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


@dataclass(frozen=True, slots=True)
class SwapContract:
    """Fixed-for-floating swap — OTC, customisable, financial settlement."""

    commodity: CommodityConfig
    fixed_rate: float  # may be negative
    floating_index: str  # e.g. "TTF_DA", "EPEX_SPOT_DE"
    notional: float
    schedule: DeliverySchedule
    granularity: Granularity = Granularity.MONTHLY

    def __post_init__(self) -> None:
        require_positive("notional", self.notional)


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
    """Shared eager validation for transmission and pipeline rights (Req 24.4).

    ``quantity`` (Q) and ``tariff`` (T_AB) must be non-negative; ``loss`` must lie
    in the half-open interval ``[0, 1)`` (a 100% loss would deliver nothing and is
    rejected); an optional ``capacity`` cap must be strictly positive; an optional
    ``reverse_tariff`` (T_BA, used by a bidirectional right) must be non-negative.
    Every message names the offending field and the violated constraint (Req 11.5).
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
    """A right to move **power** from origin hub A to destination hub B (Req 24).

    The per-period payoff to the holder is ``Q_delivered * max(P_B - P_A - T_AB, 0)``
    (§12): buy at the origin ``P_A``, pay the transport tariff ``T_AB``, sell at the
    destination ``P_B`` — an option exercised only when the locational spread covers
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
    """A right to move **gas** from origin hub A to destination hub B (Req 24).

    Economically identical to :class:`TransmissionRight` — same payoff
    ``Q_delivered * max(P_B - P_A - T_AB, 0)`` and the same field set — differing
    only in intent (gas pipeline capacity rather than power transmission). Kept a
    distinct type so a book never silently conflates power transmission with gas
    transport; both are priced by the one ``value_transport_right`` engine.

    See :class:`TransmissionRight` for the field semantics.
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
