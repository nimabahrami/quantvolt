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
from enum import StrEnum

import polars as pl

from .._validation import require_non_empty, require_non_negative
from ..exceptions import ValidationError
from ..models.interval import PowerDeliveryInterval
from ..models.power_hedge import PowerHedgeContract
from ..models.ppa import PpaContract, PpaSettlementType, PpaVolumeBasis
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
    """An auditable producer cash-flow ledger for one delivery interval."""

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
                    )
                },
            }
        )
    inactive = sorted(set(hedge_ids) - active_hedge_ids)
    if inactive:
        raise ValidationError(f"hedges cover no supplied interval: {', '.join(inactive)}")
    return pl.DataFrame(rows)


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
) -> PpaIntervalSettlement:
    """Settle one PPA interval from a producer's perspective.

    For a physical PPA, contracted energy earns the fixed price; own generation
    serves that obligation first, a shortfall is bought at ``shortfall_price``,
    and excess generation is sold at ``excess_price``. Missing imbalance prices
    explicitly fall back to spot.

    For a financial CfD, all metered generation is sold spot and the contracted
    volume receives ``fixed - spot``. There is no physical delivery shortfall.
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

    if contract.settlement_type is PpaSettlementType.PHYSICAL:
        short_price = (
            spot_price_per_mwh if shortfall_price_per_mwh is None else shortfall_price_per_mwh
        )
        excess_price = spot_price_per_mwh if excess_price_per_mwh is None else excess_price_per_mwh
        _require_finite("shortfall_price_per_mwh", short_price)
        _require_finite("excess_price_per_mwh", excess_price)
        own_delivery = min(metered_generation_mwh, contracted_mwh)
        shortfall = max(contracted_mwh - metered_generation_mwh, 0.0)
        excess = max(metered_generation_mwh - contracted_mwh, 0.0)
        ppa_cashflow = contracted_mwh * contract.fixed_price_per_mwh
        spot_cashflow = excess * excess_price
        imbalance_cashflow = -shortfall * short_price
    else:
        own_delivery = 0.0
        shortfall = 0.0
        excess = 0.0
        ppa_cashflow = contracted_mwh * (contract.fixed_price_per_mwh - spot_price_per_mwh)
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
    )
    if not math.isclose(result.component_sum, result.net_cashflow, rel_tol=0.0, abs_tol=1e-9):
        raise AssertionError("PPA cash-flow ledger failed to reconcile")
    return result
