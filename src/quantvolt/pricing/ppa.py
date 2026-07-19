"""Interval PPA settlement and negative-price-safe realised option payoffs.

These functions calculate realised producer cash flow. They do not value an
unexpired PPA or option and therefore require no probability model. This is the
appropriate oracle for historical hedge experiments: every component reconciles
to the observed delivery volume and settlement prices.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, fields
from datetime import datetime
from enum import StrEnum

import polars as pl

from .._validation import require_non_empty, require_non_negative
from ..exceptions import ValidationError
from ..models.interval import PowerDeliveryInterval
from ..models.power_hedge import PowerHedgeContract
from ..models.ppa import PpaContract, PpaSettlementType, PpaVolumeBasis
from ..models.ppa_terms import (
    CurtailmentTreatment,
    NegativePriceClause,
    NegativePriceTreatment,
    PpaReconciliationPeriod,
)
from .power_hedge import settle_power_hedge_interval


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValidationError(f"{name} must be finite, got {value!r}")


def power_cap_payoff(spot_price: float, strike: float, volume_mwh: float) -> float:
    """Realised long-cap payoff ``max(spot - strike, 0) * volume``."""
    _require_finite("spot_price", spot_price)
    _require_finite("strike", strike)
    require_non_negative("volume_mwh", volume_mwh)
    return max(spot_price - strike, 0.0) * volume_mwh


def power_floor_payoff(spot_price: float, strike: float, volume_mwh: float) -> float:
    """Realised long-floor payoff ``max(strike - spot, 0) * volume``."""
    _require_finite("spot_price", spot_price)
    _require_finite("strike", strike)
    require_non_negative("volume_mwh", volume_mwh)
    return max(strike - spot_price, 0.0) * volume_mwh


@dataclass(frozen=True, slots=True)
class PpaIntervalSettlement:
    """An auditable producer cash-flow ledger for one delivery interval.

    ``effective_fixed_price_per_mwh`` is ``K_eff``, resolved in the fixed order
    indexation -> clamp -> negative-price clause (see
    :func:`settle_ppa_interval`); it equals ``contract.fixed_price_per_mwh``
    when no :class:`~quantvolt.models.ppa_terms.PpaTerms` are attached.
    ``ppa_cashflow`` includes any deemed-generation make-whole revenue without adding
    curtailed MWh to the contracted fixed leg for a ``PHYSICAL`` PPA (see
    :func:`settle_ppa_interval`), and ``tolerance_penalty`` is its own signed,
    non-positive ledger component (a producer cost) rather than being absorbed
    into another leg.
    """

    interval: PowerDeliveryInterval
    contracted_mwh: float
    metered_generation_mwh: float
    own_generation_delivered_mwh: float
    shortfall_mwh: float
    excess_mwh: float
    ppa_cashflow: float
    spot_cashflow: float
    imbalance_cashflow: float
    hedge_cashflow: float
    option_payoff: float
    option_premium: float
    variable_cost: float
    transaction_cost: float
    net_cashflow: float
    effective_fixed_price_per_mwh: float
    curtailed_mwh: float
    deemed_generation_mwh: float
    tolerance_penalty: float

    @property
    def component_sum(self) -> float:
        """Reconstruct net cash flow from its signed ledger components."""
        return (
            self.ppa_cashflow
            + self.spot_cashflow
            + self.imbalance_cashflow
            + self.hedge_cashflow
            + self.option_payoff
            - self.option_premium
            - self.variable_cost
            - self.transaction_cost
            + self.tolerance_penalty
        )


class MissingImbalancePricePolicy(StrEnum):
    """How batch settlement handles absent physical imbalance-price columns."""

    ERROR = "error"
    USE_SPOT = "use_spot"


@dataclass(frozen=True, slots=True)
class PpaDataColumns:
    """Map caller-owned column names onto QuantVolt's PPA settlement inputs."""

    interval_start_utc: str = "interval_start_utc"
    interval_end_utc: str = "interval_end_utc"
    contracted_mwh: str = "contracted_mwh"
    metered_generation_mwh: str = "metered_generation_mwh"
    spot_price_per_mwh: str = "spot_price_per_mwh"
    shortfall_price_per_mwh: str = "shortfall_price_per_mwh"
    excess_price_per_mwh: str = "excess_price_per_mwh"
    hedge_cashflow: str = "hedge_cashflow"
    option_payoff: str = "option_payoff"
    option_premium: str = "option_premium"
    variable_cost: str = "variable_cost"
    transaction_cost: str = "transaction_cost"
    curtailed_mwh: str = "curtailed_mwh"

    def __post_init__(self) -> None:
        mappings = [(field.name, getattr(self, field.name)) for field in fields(self)]
        names = [name for _, name in mappings]
        for field_name, name in mappings:
            require_non_empty(field_name, name)
        if len(names) != len(set(names)):
            raise ValidationError("PpaDataColumns mappings must use distinct column names")


def _required_batch_columns(
    contract: PpaContract,
    columns: PpaDataColumns,
    imbalance_policy: MissingImbalancePricePolicy,
) -> set[str]:
    required = {
        columns.interval_start_utc,
        columns.interval_end_utc,
        columns.contracted_mwh,
        columns.metered_generation_mwh,
        columns.spot_price_per_mwh,
    }
    if (
        contract.settlement_type is PpaSettlementType.PHYSICAL
        and imbalance_policy is MissingImbalancePricePolicy.ERROR
    ):
        required.update({columns.shortfall_price_per_mwh, columns.excess_price_per_mwh})
    if (
        contract.terms is not None
        and contract.terms.volume is not None
        and contract.terms.volume.needs_curtailment_input
    ):
        required.add(columns.curtailed_mwh)
    return required


def settle_ppa_frame(
    contract: PpaContract,
    data: pl.DataFrame,
    *,
    columns: PpaDataColumns | None = None,
    imbalance_policy: MissingImbalancePricePolicy = MissingImbalancePricePolicy.ERROR,
    require_contiguous: bool = True,
    hedges: Sequence[PowerHedgeContract] = (),
) -> pl.DataFrame:
    """Validate and settle caller-supplied interval data into a canonical ledger.

    Inputs remain caller-owned and are never modified. Column names may be mapped
    with ``PpaDataColumns``. By default physical PPAs require genuine shortfall and
    excess prices: using spot as an imbalance proxy must be explicitly requested.

    The result contains one row per input interval and every signed cash-flow
    component used to reconstruct ``net_cashflow``.
    """
    if columns is None:
        columns = PpaDataColumns()
    if not isinstance(data, pl.DataFrame):
        raise ValidationError(f"data must be a polars DataFrame, got {type(data).__name__}")
    if not isinstance(imbalance_policy, MissingImbalancePricePolicy):
        raise ValidationError(f"invalid imbalance_policy: {imbalance_policy!r}")
    if not isinstance(require_contiguous, bool):
        raise ValidationError("require_contiguous must be a boolean")
    if data.height == 0:
        raise ValidationError("data must be non-empty")
    if any(not isinstance(hedge, PowerHedgeContract) for hedge in hedges):
        raise ValidationError("hedges must contain only PowerHedgeContract values")
    hedge_ids = [hedge.hedge_id for hedge in hedges]
    if len(hedge_ids) != len(set(hedge_ids)):
        raise ValidationError("hedges must have unique hedge_id values")
    if hedges and columns.hedge_cashflow in data.columns:
        raise ValidationError(
            "data hedge_cashflow cannot be combined with typed hedges; this would double count"
        )
    required = _required_batch_columns(contract, columns, imbalance_policy)
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValidationError(f"data is missing required columns: {', '.join(missing)}")
    relevant = required | {
        name
        for name in (
            columns.hedge_cashflow,
            columns.option_payoff,
            columns.option_premium,
            columns.variable_cost,
            columns.transaction_cost,
            columns.curtailed_mwh,
        )
        if name in data.columns
    }
    numeric_relevant = relevant - {columns.interval_start_utc, columns.interval_end_utc}
    non_numeric = sorted(name for name in numeric_relevant if not data.schema[name].is_numeric())
    if non_numeric:
        raise ValidationError(f"data columns must be numeric: {', '.join(non_numeric)}")
    nulls = data.select(pl.col(sorted(relevant)).null_count()).row(0, named=True)
    null_columns = sorted(name for name, count in nulls.items() if count)
    if null_columns:
        raise ValidationError(f"data contains nulls in columns: {', '.join(null_columns)}")

    starts = data[columns.interval_start_utc]
    ends = data[columns.interval_end_utc]
    if starts.n_unique() != data.height:
        raise ValidationError("data contains duplicate interval starts")
    if not starts.is_sorted():
        raise ValidationError("data intervals must be sorted by interval_start_utc")
    if require_contiguous and data.height > 1:
        previous_ends = ends.slice(0, data.height - 1)
        following_starts = starts.slice(1)
        if not bool((previous_ends == following_starts).all()):
            raise ValidationError("data intervals contain a gap or overlap")

    rows: list[dict[str, object]] = []
    active_hedge_ids: set[str] = set()
    for row_number, row in enumerate(data.iter_rows(named=True)):
        try:
            interval = PowerDeliveryInterval(
                row[columns.interval_start_utc], row[columns.interval_end_utc]
            )
            shortfall_price = row.get(columns.shortfall_price_per_mwh)
            excess_price = row.get(columns.excess_price_per_mwh)
            if imbalance_policy is MissingImbalancePricePolicy.USE_SPOT:
                shortfall_price = row[columns.spot_price_per_mwh]
                excess_price = row[columns.spot_price_per_mwh]
            spot_price = float(row[columns.spot_price_per_mwh])
            hedge_cashflow = float(row.get(columns.hedge_cashflow, 0.0))
            for hedge in hedges:
                if hedge.covers(interval):
                    active_hedge_ids.add(hedge.hedge_id)
                    hedge_cashflow += settle_power_hedge_interval(
                        hedge, interval, spot_price
                    ).net_cashflow
            settlement = settle_ppa_interval(
                contract,
                interval,
                contracted_mwh=float(row[columns.contracted_mwh]),
                metered_generation_mwh=float(row[columns.metered_generation_mwh]),
                spot_price_per_mwh=spot_price,
                shortfall_price_per_mwh=(
                    None if shortfall_price is None else float(shortfall_price)
                ),
                excess_price_per_mwh=None if excess_price is None else float(excess_price),
                hedge_cashflow=hedge_cashflow,
                option_payoff=float(row.get(columns.option_payoff, 0.0)),
                option_premium=float(row.get(columns.option_premium, 0.0)),
                variable_cost=float(row.get(columns.variable_cost, 0.0)),
                transaction_cost=float(row.get(columns.transaction_cost, 0.0)),
                curtailed_mwh=float(row.get(columns.curtailed_mwh, 0.0)),
            )
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValidationError(f"invalid PPA data at row {row_number}: {exc}") from exc
        rows.append(
            {
                "input_row": row_number,
                "interval_start_utc": interval.start_utc,
                "interval_end_utc": interval.end_utc,
                **{
                    field: getattr(settlement, field)
                    for field in (
                        "contracted_mwh",
                        "metered_generation_mwh",
                        "own_generation_delivered_mwh",
                        "shortfall_mwh",
                        "excess_mwh",
                        "ppa_cashflow",
                        "spot_cashflow",
                        "imbalance_cashflow",
                        "hedge_cashflow",
                        "option_payoff",
                        "option_premium",
                        "variable_cost",
                        "transaction_cost",
                        "net_cashflow",
                        "effective_fixed_price_per_mwh",
                        "curtailed_mwh",
                        "deemed_generation_mwh",
                        "tolerance_penalty",
                    )
                },
            }
        )
    inactive = sorted(set(hedge_ids) - active_hedge_ids)
    if inactive:
        raise ValidationError(f"hedges cover no supplied interval: {', '.join(inactive)}")
    return pl.DataFrame(rows)


def _resolve_effective_price(
    contract: PpaContract, interval: PowerDeliveryInterval, spot_price_per_mwh: float
) -> tuple[float, bool]:
    """Resolve ``K_eff`` in the declared fixed order: indexation -> clamp -> negative-price.

    This order is a declared design decision of the ``ppa-contract-terms``
    framework (see ``.kiro/specs/ppa-contract-terms/design.md``), not an
    external convention. Returns ``(k_eff, fixed_leg_suspended)``:
    ``fixed_leg_suspended`` is True only when a ``NO_COMPENSATION``
    negative-price clause has triggered for this interval, and forces the
    ``FINANCIAL_CFD`` fixed-for-floating difference payment to zero outright
    (bypassing the ``K_eff``-based formula, since ``contracted_mwh * (0 -
    spot)`` is not itself zero) per Requirement 3.4. The physical fixed leg
    needs no such special case: ``contracted_mwh * K_eff`` is already zero
    whenever the clause triggers, under either treatment.

    A clause carrying ``min_consecutive_intervals`` (an EEG-style consecutive-
    hour trigger, Requirement 11) is **never applied here**: whether an
    interval belongs to a qualifying run of consecutive sub-threshold
    intervals cannot be determined from this interval alone (it needs
    neighbouring-row state). This interval pass stays fully stateless for
    such a clause — treating it as if absent — and :func:`reconcile_ppa_ledger`
    computes the run-based suspension separately as a post-processing true-up.
    """
    terms = contract.terms
    base = contract.fixed_price_per_mwh
    price_terms = terms.price if terms is not None else None
    k_eff = (
        price_terms.effective_price(interval.start_utc, base=base)
        if price_terms is not None
        else base
    )
    negative_price = terms.negative_price if terms is not None else None
    fixed_leg_suspended = False
    if (
        negative_price is not None
        and negative_price.min_consecutive_intervals is None
        and negative_price.triggers(spot_price_per_mwh)
    ):
        k_eff = 0.0
        fixed_leg_suspended = negative_price.treatment is NegativePriceTreatment.NO_COMPENSATION
    return k_eff, fixed_leg_suspended


def settle_ppa_interval(
    contract: PpaContract,
    interval: PowerDeliveryInterval,
    *,
    contracted_mwh: float,
    metered_generation_mwh: float,
    spot_price_per_mwh: float,
    shortfall_price_per_mwh: float | None = None,
    excess_price_per_mwh: float | None = None,
    hedge_cashflow: float = 0.0,
    option_payoff: float = 0.0,
    option_premium: float = 0.0,
    variable_cost: float = 0.0,
    transaction_cost: float = 0.0,
    curtailed_mwh: float = 0.0,
) -> PpaIntervalSettlement:
    """Settle one PPA interval from a producer's perspective.

    For a physical PPA, contracted energy earns the fixed price; own generation
    serves that obligation first, a shortfall is bought at ``shortfall_price``,
    and excess generation is sold at ``excess_price``. Missing imbalance prices
    explicitly fall back to spot.

    For a financial CfD, all metered generation is sold spot and the contracted
    volume receives ``fixed - spot``. There is no physical delivery shortfall.

    When ``contract.terms`` (a :class:`~quantvolt.models.ppa_terms.PpaTerms`) is
    attached, the contracted fixed leg uses the resolved effective price
    ``K_eff`` instead of ``contract.fixed_price_per_mwh`` — see
    :func:`_resolve_effective_price` for the fixed indexation -> clamp ->
    negative-price resolution order.

    ``curtailed_mwh`` (default ``0.0``) is compensated per
    ``contract.terms.volume.curtailment`` under an **indifference** principle: a producer
    curtailed under ``DEEMED_GENERATION`` is never worse off, and never *better* off, than had it
    delivered in full — curtailed MWh count *as delivery toward the contracted
    volume*, they are not an extra, separately-paid quantity on top of it.

    - ``PHYSICAL``: curtailed MWh offset the shortfall instead of adding to
      ``ppa_cashflow``. ``deemed_generation_mwh = min(curtailed_mwh,
      max(contracted_mwh - metered_generation_mwh, 0.0))`` — the curtailed MWh
      *actually credited* against the metered/contracted gap (any curtailed MWh
      beyond that gap cannot offset a shortfall that does not exist, and earns
      nothing further). ``shortfall = max(contracted_mwh -
      metered_generation_mwh - deemed_generation_mwh, 0.0)``; ``ppa_cashflow =
      contracted_mwh * K_eff`` (no curtailment add-on). A fully-curtailed
      shortfall (``deemed_generation_mwh == shortfall_gap``) reconciles to
      exactly the full-delivery net cash flow.
    - ``FINANCIAL_CFD``: there is no physical shortfall to offset, so
      ``deemed_generation_mwh = curtailed_mwh`` in full, and the make-whole pays
      the curtailed MWh's *lost spot revenue* at the signed spot price:
      ``ppa_cashflow = contracted_mwh * (K_eff - spot_price_per_mwh) +
      deemed_generation_mwh * spot_price_per_mwh``. ``spot_cashflow`` keeps its
      plain ``metered_generation_mwh * spot_price_per_mwh`` meaning; the deemed
      make-whole is carried entirely on the contractual (``ppa_cashflow``) leg.
    - ``PRODUCER_BEARS`` (or no volume terms at all): ``deemed_generation_mwh =
      0.0`` and curtailed MWh earn nothing, on either settlement type.
    - **Declared decision — negative spot:** exact indifference means that at a
      negative spot price, ``DEEMED_GENERATION`` yields *less* net cash flow than
      ``PRODUCER_BEARS`` (bearing the curtailment, rather than being made whole
      for it, is genuinely the better outcome when spot is negative — being
      credited for energy priced negatively is a cost, not a benefit). This
      inversion only occurs for ``spot_price_per_mwh < 0``; for ``spot >= 0``,
      ``DEEMED_GENERATION`` net cash flow is always ``>=`` ``PRODUCER_BEARS``'s.

    A volume tolerance band, if attached, charges ``penalty_per_mwh`` on
    out-of-band MWh only, recorded as the separate, always-non-positive
    ``tolerance_penalty`` ledger component.

    When ``contract.terms`` is ``None`` or ``PpaTerms()`` (every field ``None``)
    and ``curtailed_mwh == 0.0``, every shared field is byte-identical to the
    as-built (no-terms) output; the four new fields take their inert values.

    Embedded floor/cap price bounds (``PpaPriceTerms``), a ``hedges=`` overlay
    (:class:`~quantvolt.models.power_hedge.PowerHedgeContract`, settled into
    ``hedge_cashflow``), and caller-supplied ``option_payoff`` are economically
    distinct cash flows — a bound on the contract's own price is not a separate
    financial instrument — and are never conflated or double-counted here.
    """
    if not contract.covers(interval):
        raise ValidationError(
            f"interval {interval!r} falls outside PPA term "
            f"{contract.start_utc!r}..{contract.end_utc!r}"
        )
    require_non_negative("contracted_mwh", contracted_mwh)
    require_non_negative("metered_generation_mwh", metered_generation_mwh)
    require_non_negative("option_premium", option_premium)
    require_non_negative("variable_cost", variable_cost)
    require_non_negative("transaction_cost", transaction_cost)
    require_non_negative("curtailed_mwh", curtailed_mwh)
    for name, value in (
        ("spot_price_per_mwh", spot_price_per_mwh),
        ("hedge_cashflow", hedge_cashflow),
        ("option_payoff", option_payoff),
    ):
        _require_finite(name, value)
    if contract.volume_basis is PpaVolumeBasis.PAY_AS_PRODUCED and not math.isclose(
        contracted_mwh, metered_generation_mwh, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValidationError(
            "pay_as_produced contracted_mwh must equal metered_generation_mwh; "
            f"got {contracted_mwh!r} and {metered_generation_mwh!r}"
        )

    k_eff, fixed_leg_suspended = _resolve_effective_price(contract, interval, spot_price_per_mwh)
    volume_terms = contract.terms.volume if contract.terms is not None else None
    default_curtailment = CurtailmentTreatment.PRODUCER_BEARS
    curtailment = volume_terms.curtailment if volume_terms is not None else default_curtailment
    is_deemed = curtailment is CurtailmentTreatment.DEEMED_GENERATION
    tolerance = volume_terms.tolerance if volume_terms is not None else None
    tolerance_penalty = (
        0.0
        if tolerance is None
        else -tolerance.penalty_per_mwh
        * tolerance.out_of_band_mwh(metered_generation_mwh, contracted_mwh)
    )

    if contract.settlement_type is PpaSettlementType.PHYSICAL:
        short_price = (
            spot_price_per_mwh if shortfall_price_per_mwh is None else shortfall_price_per_mwh
        )
        excess_price = spot_price_per_mwh if excess_price_per_mwh is None else excess_price_per_mwh
        _require_finite("shortfall_price_per_mwh", short_price)
        _require_finite("excess_price_per_mwh", excess_price)
        own_delivery = min(metered_generation_mwh, contracted_mwh)
        # Curtailed MWh count AS delivery toward the contracted volume (indifference:
        # the producer is never better off, never worse off, for being curtailed) —
        # capped at the metered-vs-contracted gap itself, since crediting more than
        # that gap could not reduce a shortfall that does not exist (AMENDED
        # 2026-07-19, code review FIX 1).
        shortfall_gap = max(contracted_mwh - metered_generation_mwh, 0.0)
        deemed_generation_mwh = min(curtailed_mwh, shortfall_gap) if is_deemed else 0.0
        shortfall = max(contracted_mwh - metered_generation_mwh - deemed_generation_mwh, 0.0)
        excess = max(metered_generation_mwh - contracted_mwh, 0.0)
        ppa_cashflow = contracted_mwh * k_eff
        spot_cashflow = excess * excess_price
        imbalance_cashflow = -shortfall * short_price
    else:
        own_delivery = 0.0
        shortfall = 0.0
        excess = 0.0
        # A CfD has no physical shortfall to offset: curtailed MWh are made whole in
        # full by paying the lost spot revenue at the signed spot price (AMENDED
        # 2026-07-19, code review FIX 1).
        deemed_generation_mwh = curtailed_mwh if is_deemed else 0.0
        ppa_cashflow = (
            0.0
            if fixed_leg_suspended
            else contracted_mwh * (k_eff - spot_price_per_mwh)
            + deemed_generation_mwh * spot_price_per_mwh
        )
        spot_cashflow = metered_generation_mwh * spot_price_per_mwh
        imbalance_cashflow = 0.0

    net = (
        ppa_cashflow
        + spot_cashflow
        + imbalance_cashflow
        + hedge_cashflow
        + option_payoff
        - option_premium
        - variable_cost
        - transaction_cost
        + tolerance_penalty
    )
    result = PpaIntervalSettlement(
        interval=interval,
        contracted_mwh=contracted_mwh,
        metered_generation_mwh=metered_generation_mwh,
        own_generation_delivered_mwh=own_delivery,
        shortfall_mwh=shortfall,
        excess_mwh=excess,
        ppa_cashflow=ppa_cashflow,
        spot_cashflow=spot_cashflow,
        imbalance_cashflow=imbalance_cashflow,
        hedge_cashflow=hedge_cashflow,
        option_payoff=option_payoff,
        option_premium=option_premium,
        variable_cost=variable_cost,
        transaction_cost=transaction_cost,
        net_cashflow=net,
        effective_fixed_price_per_mwh=k_eff,
        curtailed_mwh=curtailed_mwh,
        deemed_generation_mwh=deemed_generation_mwh,
        tolerance_penalty=tolerance_penalty,
    )
    if not math.isclose(result.component_sum, result.net_cashflow, rel_tol=0.0, abs_tol=1e-9):
        raise AssertionError("PPA cash-flow ledger failed to reconcile")
    return result


@dataclass(frozen=True, slots=True)
class PpaReconciliationColumns:
    """Map caller-owned column names onto :func:`reconcile_ppa_ledger`'s ledger inputs.

    All five columns are ordinary columns of a :func:`settle_ppa_frame` ledger
    **except** ``spot_price_per_mwh``, which that ledger does not carry (the
    interval pass never records raw spot). A caller
    whose ``contract.terms.negative_price`` carries a consecutive-hour trigger
    length must join a spot-price column onto the ledger themselves (for
    example from the original input frame) before calling
    :func:`reconcile_ppa_ledger`; it is required only in that case.
    """

    interval_start_utc: str = "interval_start_utc"
    interval_end_utc: str = "interval_end_utc"
    contracted_mwh: str = "contracted_mwh"
    metered_generation_mwh: str = "metered_generation_mwh"
    effective_fixed_price_per_mwh: str = "effective_fixed_price_per_mwh"
    spot_price_per_mwh: str = "spot_price_per_mwh"

    def __post_init__(self) -> None:
        mappings = [(field.name, getattr(self, field.name)) for field in fields(self)]
        names = [name for _, name in mappings]
        for field_name, name in mappings:
            require_non_empty(field_name, name)
        if len(names) != len(set(names)):
            raise ValidationError(
                "PpaReconciliationColumns mappings must use distinct column names"
            )


def _row_correction(
    settlement_type: PpaSettlementType,
    treatment: NegativePriceTreatment,
    contracted_mwh: float,
    effective_fixed_price_per_mwh: float,
    spot_price_per_mwh: float,
) -> float:
    """The contracted-volume-only fixed-leg correction for one qualifying row.

    Reconstructs, from the ledger's own recorded ``contracted_mwh`` and
    ``effective_fixed_price_per_mwh`` (which the interval pass resolved
    ignoring any consecutive-hour trigger — see
    :func:`_resolve_effective_price`), the delta that a per-interval
    ``NegativePriceClause`` would have applied to the contracted-volume fixed
    leg *only* (Requirement 3.4/3.5): never the deemed-generation portion, and
    for a ``PHYSICAL`` PPA never the imbalance legs.

    ``PHYSICAL`` (either treatment) and ``FINANCIAL_CFD`` ``PRICE_AT_ZERO``
    both zero the contracted-volume fixed leg's *own* ``K_eff``-based
    revenue, so both correct by ``-(contracted * K_eff)``. ``FINANCIAL_CFD``
    ``NO_COMPENSATION`` zeroes the *entire* difference payment
    ``contracted * (K_eff - spot)``, which is not itself zero, so it corrects
    by the negative of that whole payment instead.
    """
    if settlement_type is PpaSettlementType.PHYSICAL:
        return -(contracted_mwh * effective_fixed_price_per_mwh)
    if treatment is NegativePriceTreatment.NO_COMPENSATION:
        return -(contracted_mwh * (effective_fixed_price_per_mwh - spot_price_per_mwh))
    return -(contracted_mwh * effective_fixed_price_per_mwh)


def _consecutive_hour_corrections(
    settlement_type: PpaSettlementType,
    negative_price: NegativePriceClause,
    *,
    spot_price_per_mwh: Sequence[float],
    contracted_mwh: Sequence[float],
    effective_fixed_price_per_mwh: Sequence[float],
    interval_start_utc: Sequence[datetime],
    interval_end_utc: Sequence[datetime],
) -> list[float]:
    """Per-row true-up correction for maximal, **clock-contiguous** runs meeting the
    trigger length.

    Identifies maximal runs of rows with ``negative_price.triggers(spot_price_per_mwh)``;
    rows in a run whose length is ``>= min_consecutive_intervals``
    get :func:`_row_correction`, every other row (including rows in a sub-threshold
    run that is too short) gets exactly ``0.0`` (consecutive-hour locality).

    "Consecutive" means **clock-time contiguous**, not merely row-adjacent
    (EEG-style Section 51 windows are defined
    on wall-clock time). Row ``i + 1`` continues row ``i``'s run only when
    ``interval_start_utc[i + 1] == interval_end_utc[i]``; any other relationship (a
    gap, or an overlap that should never occur in a validated ledger) breaks the
    run. This matters because a caller may supply a non-contiguous ledger — for
    example one built via ``settle_ppa_frame(..., require_contiguous=False)`` or by
    joining rows from more than one source — where naive row adjacency would
    silently concatenate two clock-time-disjoint sub-threshold stretches into one
    run and misapply the trigger.
    """
    min_run_length = negative_price.min_consecutive_intervals
    if min_run_length is None:
        raise ValidationError(
            "negative_price.min_consecutive_intervals must be set to compute "
            "consecutive-hour corrections"
        )
    below = [negative_price.triggers(spot) for spot in spot_price_per_mwh]
    n = len(below)
    corrections = [0.0] * n
    row = 0
    while row < n:
        if not below[row]:
            row += 1
            continue
        run_end = row + 1
        while (
            run_end < n
            and below[run_end]
            and interval_start_utc[run_end] == interval_end_utc[run_end - 1]
        ):
            run_end += 1
        if run_end - row >= min_run_length:
            for k in range(row, run_end):
                corrections[k] = _row_correction(
                    settlement_type,
                    negative_price.treatment,
                    contracted_mwh[k],
                    effective_fixed_price_per_mwh[k],
                    spot_price_per_mwh[k],
                )
        row = run_end
    return corrections


def reconcile_ppa_ledger(
    contract: PpaContract,
    ledger: pl.DataFrame,
    *,
    columns: PpaReconciliationColumns | None = None,
) -> pl.DataFrame:
    """Compute per-reconciliation-period true-up cash flows over a settled ledger.

    A **pure post-processing pass**: it never modifies, re-derives, or
    contradicts a single row of the interval-level ledger produced by
    :func:`settle_ppa_frame` / :func:`settle_ppa_interval`.
    Requires ``contract.terms.reconciliation`` (a
    :class:`~quantvolt.models.ppa_terms.PpaReconciliationTerms`); returns one
    row per reconciliation period, sorted chronologically,
    with these columns:

    - ``period_start_utc`` / ``period_end_utc`` — the bounds of the ledger
      rows assigned to this period (the *data's* bounds, not calendar
      bounds — a declared design decision that needs no calendar library).
    - ``interval_count`` — number of ledger rows in the period.
    - ``total_contracted_mwh`` / ``total_metered_generation_mwh`` — summed
      over the period's rows.
    - ``volume_band_true_up`` — ``0.0`` unless ``reconciliation.volume_band``
      is attached, else ``-volume_band.penalty_per_mwh *
      volume_band.out_of_band_mwh(total_metered, total_contracted)``
      (the *aggregate* analogue of the interval-level
      ``PpaVolumeTerms.tolerance``, economically distinct from it).
    - ``availability_true_up`` — ``0.0`` unless ``reconciliation.availability``
      is attached, else ``-true_up_price_per_mwh *
      availability.shortfall_fraction(measured) * total_contracted``, where
      ``measured = total_metered / total_contracted`` (``1.0`` when
      ``total_contracted == 0``, a declared decision avoiding division by
      zero).
    - ``consecutive_hour_true_up`` — ``0.0`` unless
      ``contract.terms.negative_price.min_consecutive_intervals`` is set, else
      the period's sum of :func:`_consecutive_hour_corrections`; a run spanning
      a period boundary is attributed row-by-row to
      whichever period contains each corrected row (a declared design
      decision — it is not specially split or reallocated). "Consecutive"
      means **clock-time contiguous**, not merely row-adjacent: row ``i + 1`` only
      continues row ``i``'s run when
      ``interval_start_utc[i + 1] == interval_end_utc[i]``; a gapped ledger
      (for example from ``settle_ppa_frame(require_contiguous=False)``, or one
      the caller assembled by joining rows from more than one source) has its
      clock-time-disjoint sub-threshold stretches evaluated as separate runs,
      never concatenated across the gap.
    - ``net_true_up`` — the sum of the three true-up components above.

    Each period's ``net_true_up`` is, by construction, exactly the sum of its
    own three stated formulas evaluated over that period's rows only
    (each period self-reconciles).
    """
    if columns is None:
        columns = PpaReconciliationColumns()
    if not isinstance(ledger, pl.DataFrame):
        raise ValidationError(f"ledger must be a polars DataFrame, got {type(ledger).__name__}")
    if ledger.height == 0:
        raise ValidationError("ledger must be non-empty")
    if contract.terms is None or contract.terms.reconciliation is None:
        raise ValidationError(
            "contract.terms.reconciliation must be a PpaReconciliationTerms to call "
            "reconcile_ppa_ledger; got None"
        )
    reconciliation = contract.terms.reconciliation
    negative_price = contract.terms.negative_price
    needs_consecutive_hour = (
        negative_price is not None and negative_price.min_consecutive_intervals is not None
    )

    required = {
        columns.interval_start_utc,
        columns.interval_end_utc,
        columns.contracted_mwh,
        columns.metered_generation_mwh,
        columns.effective_fixed_price_per_mwh,
    }
    if needs_consecutive_hour:
        required.add(columns.spot_price_per_mwh)
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise ValidationError(f"ledger is missing required columns: {', '.join(missing)}")
    numeric_required = required - {columns.interval_start_utc, columns.interval_end_utc}
    non_numeric = sorted(name for name in numeric_required if not ledger.schema[name].is_numeric())
    if non_numeric:
        raise ValidationError(f"ledger columns must be numeric: {', '.join(non_numeric)}")
    nulls = ledger.select(pl.col(sorted(required)).null_count()).row(0, named=True)
    null_columns = sorted(name for name, count in nulls.items() if count)
    if null_columns:
        raise ValidationError(f"ledger contains nulls in columns: {', '.join(null_columns)}")

    starts = ledger[columns.interval_start_utc]
    if starts.n_unique() != ledger.height:
        raise ValidationError("ledger contains duplicate interval starts")
    if not starts.is_sorted():
        raise ValidationError("ledger intervals must be sorted by interval_start_utc")

    if needs_consecutive_hour:
        assert negative_price is not None  # narrowed by needs_consecutive_hour above
        contracted_mwh = [float(v) for v in ledger[columns.contracted_mwh]]
        effective_fixed_price_per_mwh = [
            float(v) for v in ledger[columns.effective_fixed_price_per_mwh]
        ]
        spot_price_per_mwh = [float(v) for v in ledger[columns.spot_price_per_mwh]]
        interval_start_utc = list(ledger[columns.interval_start_utc])
        interval_end_utc = list(ledger[columns.interval_end_utc])
        consecutive_hour_corrections = _consecutive_hour_corrections(
            contract.settlement_type,
            negative_price,
            spot_price_per_mwh=spot_price_per_mwh,
            contracted_mwh=contracted_mwh,
            effective_fixed_price_per_mwh=effective_fixed_price_per_mwh,
            interval_start_utc=interval_start_utc,
            interval_end_utc=interval_end_utc,
        )
    else:
        consecutive_hour_corrections = [0.0] * ledger.height

    ts_col = pl.col(columns.interval_start_utc)
    if reconciliation.period is PpaReconciliationPeriod.MONTHLY:
        bucket_expr = ts_col.dt.month().alias("_period_bucket")
    elif reconciliation.period is PpaReconciliationPeriod.QUARTERLY:
        bucket_expr = (((ts_col.dt.month() - 1) // 3) + 1).alias("_period_bucket")
    else:
        bucket_expr = pl.lit(1).alias("_period_bucket")

    working = ledger.with_columns(
        ts_col.dt.year().alias("_period_year"),
        bucket_expr,
        pl.Series("_consecutive_hour_true_up", consecutive_hour_corrections),
    )
    grouped = (
        working.group_by(["_period_year", "_period_bucket"], maintain_order=True)
        .agg(
            pl.col(columns.interval_start_utc).min().alias("period_start_utc"),
            pl.col(columns.interval_end_utc).max().alias("period_end_utc"),
            pl.len().alias("interval_count"),
            pl.col(columns.contracted_mwh).sum().alias("total_contracted_mwh"),
            pl.col(columns.metered_generation_mwh).sum().alias("total_metered_generation_mwh"),
            pl.col("_consecutive_hour_true_up").sum().alias("consecutive_hour_true_up"),
        )
        .sort("period_start_utc")
    )

    rows: list[dict[str, object]] = []
    for row in grouped.iter_rows(named=True):
        total_contracted = float(row["total_contracted_mwh"])
        total_metered = float(row["total_metered_generation_mwh"])
        volume_band_true_up = 0.0
        if reconciliation.volume_band is not None:
            out_of_band = reconciliation.volume_band.out_of_band_mwh(
                metered=total_metered, contracted=total_contracted
            )
            volume_band_true_up = -reconciliation.volume_band.penalty_per_mwh * out_of_band
        availability_true_up = 0.0
        if reconciliation.availability is not None:
            measured_fraction = 1.0 if total_contracted == 0.0 else total_metered / total_contracted
            shortfall = reconciliation.availability.shortfall_fraction(measured_fraction)
            availability_true_up = (
                -reconciliation.true_up_price_per_mwh * shortfall * total_contracted
            )
        consecutive_hour_true_up = float(row["consecutive_hour_true_up"])
        rows.append(
            {
                "period_start_utc": row["period_start_utc"],
                "period_end_utc": row["period_end_utc"],
                "interval_count": int(row["interval_count"]),
                "total_contracted_mwh": total_contracted,
                "total_metered_generation_mwh": total_metered,
                "volume_band_true_up": volume_band_true_up,
                "availability_true_up": availability_true_up,
                "consecutive_hour_true_up": consecutive_hour_true_up,
                "net_true_up": (
                    volume_band_true_up + availability_true_up + consecutive_hour_true_up
                ),
            }
        )
    return pl.DataFrame(rows)
