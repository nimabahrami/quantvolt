"""Composable PPA contract-term objects — explicit settlement mechanics.

This is a **framework for explicit settlement mechanics, not a legal model of any
specific European PPA**. Each term object states exactly *one* cash-flow rule; a
caller composes only the rules needed via :class:`PpaTerms` and leaves everything
else at its default of ``None``. When no terms are attached (``terms=None`` or
``PpaTerms()`` with every field ``None``), :func:`quantvolt.pricing.ppa.settle_ppa_interval`
and :func:`quantvolt.pricing.ppa.settle_ppa_frame` produce output byte-identical to
attaching no terms at all — see Property 85 in
``.kiro/specs/ppa-contract-terms/design.md``.

Every numeric convention fixed here — clamp order (floor then cap), the strict
negative-price trigger (spot *strictly* below threshold), and the tolerance
penalty charged on out-of-band MWh only — is a **declared design decision of
this framework**, not an attribution to any external market standard. Negative
prices are always valid inputs, never error conditions.

All indexation *resolution* (e.g. CPI look-ups) happens caller-side: an
:class:`IndexationStep` carries only a precomputed, piecewise-constant restated
price. No object in this module performs I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .._validation import (
    require_finite,
    require_integer_at_least,
    require_non_negative,
    require_probability,
)
from ..exceptions import ValidationError


def _require_utc(name: str, value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationError(f"{name} must be timezone-aware UTC, got naive datetime {value!r}")
    if value.utcoffset() != timedelta(0):
        raise ValidationError(f"{name} must be expressed in UTC, got offset {value.utcoffset()}")


def _clamp(value: float, floor: float | None, cap: float | None) -> float:
    """Apply ``floor`` then ``cap``; a bound that is ``None`` is not applied."""
    result = value
    if floor is not None:
        result = max(result, floor)
    if cap is not None:
        result = min(result, cap)
    return result


class NegativePriceTreatment(StrEnum):
    """How the fixed leg behaves for an interval where the negative-price clause triggers."""

    NO_COMPENSATION = "no_compensation"
    PRICE_AT_ZERO = "price_at_zero"


class CurtailmentTreatment(StrEnum):
    """How curtailed energy is compensated."""

    PRODUCER_BEARS = "producer_bears"
    DEEMED_GENERATION = "deemed_generation"


@dataclass(frozen=True, slots=True)
class IndexationStep:
    """One piecewise-constant restatement of the contract's base fixed price.

    ``fixed_price_per_mwh`` is a caller-precomputed restatement (for example the
    output of a CPI look-up performed caller-side); this library resolves no
    index and performs no I/O.
    """

    effective_from_utc: datetime
    fixed_price_per_mwh: float

    def __post_init__(self) -> None:
        _require_utc("effective_from_utc", self.effective_from_utc)
        require_finite("fixed_price_per_mwh", self.fixed_price_per_mwh)


@dataclass(frozen=True, slots=True)
class PpaPriceTerms:
    """Floor/cap bounds and piecewise-constant indexation for the contract price.

    These bounds apply to the *contract's own fixed price* (``K_eff``) — this is
    economically distinct from a ``hedges=`` overlay (a separate
    :class:`~quantvolt.models.power_hedge.PowerHedgeContract` instrument with its
    own premium and payoff, settled into ``hedge_cashflow``) and from
    caller-supplied ``option_payoff`` ledger columns. There is no premium and no
    separate instrument for an embedded floor/cap: it simply changes what the
    fixed leg pays. See
    :func:`quantvolt.pricing.ppa.settle_ppa_interval` for the full distinction
    (no double-count guard is added; these are genuinely different cash flows).
    """

    floor_price_per_mwh: float | None = None
    cap_price_per_mwh: float | None = None
    indexation: tuple[IndexationStep, ...] = ()

    def __post_init__(self) -> None:
        if self.floor_price_per_mwh is not None:
            require_finite("floor_price_per_mwh", self.floor_price_per_mwh)
        if self.cap_price_per_mwh is not None:
            require_finite("cap_price_per_mwh", self.cap_price_per_mwh)
        if (
            self.floor_price_per_mwh is not None
            and self.cap_price_per_mwh is not None
            and not self.floor_price_per_mwh < self.cap_price_per_mwh
        ):
            raise ValidationError(
                "floor_price_per_mwh must be strictly less than cap_price_per_mwh "
                "(equal bounds are rejected), got "
                f"floor_price_per_mwh={self.floor_price_per_mwh!r}, "
                f"cap_price_per_mwh={self.cap_price_per_mwh!r}"
            )
        previous: datetime | None = None
        for index, step in enumerate(self.indexation):
            if not isinstance(step, IndexationStep):
                raise ValidationError(
                    f"indexation[{index}] must be an IndexationStep, got {type(step).__name__}"
                )
            if previous is not None and not step.effective_from_utc > previous:
                raise ValidationError(
                    f"indexation[{index}].effective_from_utc must be strictly increasing, "
                    f"got {step.effective_from_utc!r} after previous step {previous!r}"
                )
            previous = step.effective_from_utc

    def step_price_at(self, when_utc: datetime, *, base: float) -> float:
        """The latest indexation step's price active at ``when_utc``, else ``base``.

        Selects the ``fixed_price_per_mwh`` of the latest step whose
        ``effective_from_utc <= when_utc``; the step boundary switches exactly at
        ``effective_from_utc``.
        """
        price = base
        for step in self.indexation:
            if step.effective_from_utc <= when_utc:
                price = step.fixed_price_per_mwh
            else:
                break
        return price

    def effective_price(self, when_utc: datetime, *, base: float) -> float:
        """``clamp(step_price_at(when_utc, base=base), floor, cap)`` (floor then cap)."""
        return _clamp(
            self.step_price_at(when_utc, base=base),
            self.floor_price_per_mwh,
            self.cap_price_per_mwh,
        )


@dataclass(frozen=True, slots=True)
class NegativePriceClause:
    """How the fixed leg behaves when spot is strictly below a threshold.

    The clause triggers for an interval **iff** the interval's spot price is
    strictly less than ``threshold_per_mwh``; a spot exactly equal to the
    threshold does NOT trigger (a declared design decision).

    ``min_consecutive_intervals`` (default ``None``) is the optional EEG-style
    consecutive-hour trigger length: when set, the clause
    only applies to a *maximal run* of intervals whose spot is strictly below
    ``threshold_per_mwh`` that reaches or exceeds this length. **A consecutive-
    hour clause cannot be evaluated interval-locally** — determining run
    membership needs neighbouring-row state that a single
    :func:`~quantvolt.pricing.ppa.settle_ppa_interval` call does not have. This
    is a **declared design decision**: when ``min_consecutive_intervals`` is
    set, the interval pass treats the clause as inert (``K_eff`` is resolved
    exactly as if no negative-price clause were attached at all) and the
    cross-row suspension is instead computed entirely by the post-processing
    :func:`~quantvolt.pricing.ppa.reconcile_ppa_ledger` pass, as an explicit
    ``consecutive_hour_true_up`` cash flow per reconciliation period.
    A length of 1 would be indistinguishable from the
    ordinary per-interval clause already covered by the interval-local trigger, so
    ``min_consecutive_intervals``, when given, must be an integer ``>= 2``.
    """

    treatment: NegativePriceTreatment
    threshold_per_mwh: float = 0.0
    min_consecutive_intervals: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.treatment, NegativePriceTreatment):
            raise ValidationError(
                f"treatment must be a NegativePriceTreatment, got {self.treatment!r}"
            )
        require_finite("threshold_per_mwh", self.threshold_per_mwh)
        if self.min_consecutive_intervals is not None:
            require_integer_at_least("min_consecutive_intervals", self.min_consecutive_intervals, 2)

    def triggers(self, spot_price_per_mwh: float) -> bool:
        """Whether the clause applies: ``spot_price_per_mwh < threshold_per_mwh`` (strict).

        This is the interval-local trigger test used by Requirement 3. It does
        NOT consult ``min_consecutive_intervals``: run-length gating is a
        cross-row concern resolved only by
        :func:`~quantvolt.pricing.ppa.reconcile_ppa_ledger`.
        """
        return spot_price_per_mwh < self.threshold_per_mwh


@dataclass(frozen=True, slots=True)
class PpaToleranceBand:
    """A volume tolerance band charging a penalty on out-of-band MWh only.

    MWh inside ``[min_fraction * contracted, max_fraction * contracted]`` incur
    zero penalty; charging the penalty on out-of-band MWh only — rather than on
    the whole volume — is a declared design decision.
    """

    min_fraction: float
    max_fraction: float
    penalty_per_mwh: float = 0.0

    def __post_init__(self) -> None:
        require_probability("min_fraction", self.min_fraction)
        if not self.max_fraction >= 1.0:
            raise ValidationError(f"max_fraction must be >= 1, got {self.max_fraction!r}")
        require_non_negative("penalty_per_mwh", self.penalty_per_mwh)

    def out_of_band_mwh(self, metered: float, contracted: float) -> float:
        """Non-negative MWh by which ``metered`` falls outside the band for ``contracted``."""
        lower = self.min_fraction * contracted
        upper = self.max_fraction * contracted
        return max(lower - metered, 0.0) + max(metered - upper, 0.0)


@dataclass(frozen=True, slots=True)
class PpaVolumeTerms:
    """Curtailment treatment and optional volume tolerance band."""

    curtailment: CurtailmentTreatment
    tolerance: PpaToleranceBand | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.curtailment, CurtailmentTreatment):
            raise ValidationError(
                f"curtailment must be a CurtailmentTreatment, got {self.curtailment!r}"
            )
        if self.tolerance is not None and not isinstance(self.tolerance, PpaToleranceBand):
            raise ValidationError(
                f"tolerance must be None or a PpaToleranceBand, got {type(self.tolerance).__name__}"
            )

    @property
    def needs_curtailment_input(self) -> bool:
        """Whether settlement requires a curtailed-MWh input (True iff ``DEEMED_GENERATION``)."""
        return self.curtailment is CurtailmentTreatment.DEEMED_GENERATION


class PpaReconciliationPeriod(StrEnum):
    """The cadence at which :func:`~quantvolt.pricing.ppa.reconcile_ppa_ledger` aggregates rows."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    ANNUAL = "annual"


@dataclass(frozen=True, slots=True)
class PpaAvailabilityGuarantee:
    """A one-directional deemed-vs-measured availability guarantee.

    ``deemed_availability_fraction`` is the contractually guaranteed minimum
    fraction of contracted volume the asset must make available over a
    reconciliation period. This is a **declared design decision**: the
    guarantee is modelled as **shortfall-only** — it charges a true-up when
    measured availability falls below the deemed threshold, and pays nothing
    back when measured availability exceeds it. It is not a symmetric two-way
    true-up.
    """

    deemed_availability_fraction: float

    def __post_init__(self) -> None:
        require_probability("deemed_availability_fraction", self.deemed_availability_fraction)

    def shortfall_fraction(self, measured_availability_fraction: float) -> float:
        """``max(deemed - measured, 0)``, the non-negative availability shortfall."""
        return max(self.deemed_availability_fraction - measured_availability_fraction, 0.0)


@dataclass(frozen=True, slots=True)
class PpaReconciliationTerms:
    """Period reconciliation and true-up terms.

    ``period`` sets the aggregation cadence used by
    :func:`~quantvolt.pricing.ppa.reconcile_ppa_ledger`, a **pure post-
    processing pass over an already-settled interval ledger that makes no
    change to the interval pass**. ``volume_band``, when
    present, reuses :class:`PpaToleranceBand` **applied to the period's
    aggregate** contracted/metered MWh (summed across the period's rows)
    rather than to a single interval — this is economically distinct from any
    interval-level ``PpaVolumeTerms.tolerance``, which the two
    may coexist with; its own ``penalty_per_mwh`` prices the aggregate true-up.
    ``true_up_price_per_mwh`` (the explicit true-up price basis) is a
    **caller-supplied price, not derived from spot or any ledger column** —
    consistent with this framework's I/O-boundary doctrine
    (:class:`IndexationStep` is likewise a precomputed restatement); it prices
    only the availability true-up when ``availability`` is
    attached. This split (the volume band prices itself via
    ``penalty_per_mwh``; the availability guarantee is priced by
    ``true_up_price_per_mwh``) is a **declared design decision** resolving the
    otherwise-ambiguous case of an aggregate volume band coexisting with an
    explicit true-up price basis into two independently configurable true-up
    mechanisms.
    """

    period: PpaReconciliationPeriod
    true_up_price_per_mwh: float
    volume_band: PpaToleranceBand | None = None
    availability: PpaAvailabilityGuarantee | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.period, PpaReconciliationPeriod):
            raise ValidationError(f"period must be a PpaReconciliationPeriod, got {self.period!r}")
        require_finite("true_up_price_per_mwh", self.true_up_price_per_mwh)
        if self.volume_band is not None and not isinstance(self.volume_band, PpaToleranceBand):
            raise ValidationError(
                "volume_band must be None or a PpaToleranceBand, got "
                f"{type(self.volume_band).__name__}"
            )
        if self.availability is not None and not isinstance(
            self.availability, PpaAvailabilityGuarantee
        ):
            raise ValidationError(
                "availability must be None or a PpaAvailabilityGuarantee, got "
                f"{type(self.availability).__name__}"
            )


class PpaCreditSupportType(StrEnum):
    """The form of credit support, if any, backing a PPA counterparty's obligations."""

    NONE = "none"
    PARENT_GUARANTEE = "parent_guarantee"
    LETTER_OF_CREDIT = "letter_of_credit"
    CASH_COLLATERAL = "cash_collateral"


class ChangeInLawAllocation(StrEnum):
    """Which party bears the economic consequence of a change-in-law event."""

    PRODUCER = "producer"
    BUYER = "buyer"
    SHARED = "shared"


@dataclass(frozen=True, slots=True)
class PpaContractMetadata:
    """Carried contract metadata with **ZERO settlement semantics**.

    Guarantee-of-Origin, credit-support, and change-in-law fields are carried
    and validated but never enter ``K_eff`` resolution, any ledger component,
    ``component_sum``, or ``net_cashflow`` — this is verified by
    property-based tests covering arbitrary metadata content, not only the
    all-default instance.
    """

    goo_transfer: bool = False
    goo_price_per_mwh: float | None = None
    credit_support_type: PpaCreditSupportType = PpaCreditSupportType.NONE
    credit_support_amount: float | None = None
    credit_support_threshold: float | None = None
    change_in_law_allocation: ChangeInLawAllocation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.goo_transfer, bool):
            raise ValidationError(
                f"goo_transfer must be a bool, got {type(self.goo_transfer).__name__}"
            )
        if self.goo_price_per_mwh is not None:
            require_finite("goo_price_per_mwh", self.goo_price_per_mwh)
        if not isinstance(self.credit_support_type, PpaCreditSupportType):
            raise ValidationError(
                "credit_support_type must be a PpaCreditSupportType, got "
                f"{self.credit_support_type!r}"
            )
        if self.credit_support_amount is not None:
            require_non_negative("credit_support_amount", self.credit_support_amount)
        if self.credit_support_threshold is not None:
            require_non_negative("credit_support_threshold", self.credit_support_threshold)
        if self.change_in_law_allocation is not None and not isinstance(
            self.change_in_law_allocation, ChangeInLawAllocation
        ):
            raise ValidationError(
                "change_in_law_allocation must be None or a ChangeInLawAllocation, got "
                f"{type(self.change_in_law_allocation).__name__}"
            )


@dataclass(frozen=True, slots=True)
class PpaTerms:
    """Optional bundle of composable PPA settlement terms.

    Every field defaults to ``None``. ``PpaTerms()`` (all fields ``None``)
    represents "no additional terms" and is semantically equivalent to
    attaching no terms at all. ``reconciliation`` (Requirements
    9-11), when attached, drives :func:`~quantvolt.pricing.ppa.reconcile_ppa_ledger`'s
    period-level true-ups (volume-band and availability) via its four fields
    (:class:`PpaReconciliationTerms`); ``metadata`` (:class:`PpaContractMetadata`)
    remains a settlement-inert bundle of non-computational, world-facing facts
    that no pricing or reconciliation path ever reads.
    """

    price: PpaPriceTerms | None = None
    negative_price: NegativePriceClause | None = None
    volume: PpaVolumeTerms | None = None
    reconciliation: PpaReconciliationTerms | None = None
    metadata: PpaContractMetadata | None = None

    def __post_init__(self) -> None:
        if self.price is not None and not isinstance(self.price, PpaPriceTerms):
            raise ValidationError(
                f"price must be None or a PpaPriceTerms, got {type(self.price).__name__}"
            )
        if self.negative_price is not None and not isinstance(
            self.negative_price, NegativePriceClause
        ):
            raise ValidationError(
                "negative_price must be None or a NegativePriceClause, got "
                f"{type(self.negative_price).__name__}"
            )
        if self.volume is not None and not isinstance(self.volume, PpaVolumeTerms):
            raise ValidationError(
                f"volume must be None or a PpaVolumeTerms, got {type(self.volume).__name__}"
            )
        if self.reconciliation is not None and not isinstance(
            self.reconciliation, PpaReconciliationTerms
        ):
            raise ValidationError(
                "reconciliation must be None or a PpaReconciliationTerms, got "
                f"{type(self.reconciliation).__name__}"
            )
        if self.metadata is not None and not isinstance(self.metadata, PpaContractMetadata):
            raise ValidationError(
                "metadata must be None or a PpaContractMetadata, got "
                f"{type(self.metadata).__name__}"
            )
