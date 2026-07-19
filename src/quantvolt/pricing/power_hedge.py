"""Realized settlement for financially settled power hedges."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields

import polars as pl

from .._validation import require_finite, require_non_empty
from ..exceptions import ValidationError
from ..models.interval import PowerDeliveryInterval
from ..models.power_hedge import PowerHedgeContract, PowerHedgePosition, PowerHedgeType


@dataclass(frozen=True, slots=True)
class PowerHedgeSettlement:
    """Auditable realized cash flow for one hedge and delivery interval."""

    hedge_id: str
    interval: PowerDeliveryInterval
    spot_price_per_mwh: float
    volume_mwh: float
    gross_payoff: float
    premium_cashflow: float
    net_cashflow: float


@dataclass(frozen=True, slots=True)
class PowerHedgeDataColumns:
    """Map caller-owned frame columns to realized hedge inputs."""

    interval_start_utc: str = "interval_start_utc"
    interval_end_utc: str = "interval_end_utc"
    spot_price_per_mwh: str = "spot_price_per_mwh"

    def __post_init__(self) -> None:
        mappings = [(field.name, getattr(self, field.name)) for field in fields(self)]
        for field_name, column_name in mappings:
            require_non_empty(field_name, column_name)
        if len(mappings) != len({column_name for _, column_name in mappings}):
            raise ValidationError("PowerHedgeDataColumns mappings must be distinct")


def settle_power_hedge_interval(
    contract: PowerHedgeContract,
    interval: PowerDeliveryInterval,
    spot_price_per_mwh: float,
) -> PowerHedgeSettlement:
    """Settle one observed interval; this is realized payoff, not option valuation."""
    if not contract.covers(interval):
        raise ValidationError(f"interval {interval!r} falls outside hedge {contract.hedge_id!r}")
    require_finite("spot_price_per_mwh", spot_price_per_mwh)
    strike = contract.strike_per_mwh
    if contract.hedge_type is PowerHedgeType.FIXED_PRICE_SWAP:
        payoff_per_mwh = strike - spot_price_per_mwh
    elif contract.hedge_type is PowerHedgeType.CAP:
        payoff_per_mwh = max(spot_price_per_mwh - strike, 0.0)
    elif contract.hedge_type is PowerHedgeType.FLOOR:
        payoff_per_mwh = max(strike - spot_price_per_mwh, 0.0)
    else:
        upper = contract.upper_strike_per_mwh
        if upper is None:  # defensive; contract validation makes this unreachable
            raise AssertionError("validated collar has no upper strike")
        payoff_per_mwh = max(strike - spot_price_per_mwh, 0.0) - max(
            spot_price_per_mwh - upper, 0.0
        )
    sign = 1.0 if contract.position is PowerHedgePosition.LONG else -1.0
    gross = sign * payoff_per_mwh * contract.volume_mwh
    premium = -sign * contract.allocated_premium_per_mwh * contract.volume_mwh
    return PowerHedgeSettlement(
        hedge_id=contract.hedge_id,
        interval=interval,
        spot_price_per_mwh=spot_price_per_mwh,
        volume_mwh=contract.volume_mwh,
        gross_payoff=gross,
        premium_cashflow=premium,
        net_cashflow=gross + premium,
    )


def settle_power_hedges_frame(
    contracts: Sequence[PowerHedgeContract],
    data: pl.DataFrame,
    *,
    interval_start_column: str = "interval_start_utc",
    interval_end_column: str = "interval_end_utc",
    spot_price_column: str = "spot_price_per_mwh",
    columns: PowerHedgeDataColumns | None = None,
) -> pl.DataFrame:
    """Settle hedges against caller data, returning one row per active hedge/interval.

    Input order is preserved. Intervals need not be contiguous because hedge books
    may be evaluated on selected observations, but duplicate starts and unsorted
    observations are rejected.
    """
    if not isinstance(data, pl.DataFrame):
        raise ValidationError(f"data must be a polars DataFrame, got {type(data).__name__}")
    if columns is not None:
        if (
            interval_start_column != "interval_start_utc"
            or interval_end_column != "interval_end_utc"
            or spot_price_column != "spot_price_per_mwh"
        ):
            raise ValidationError("use either columns or individual column arguments, not both")
        interval_start_column = columns.interval_start_utc
        interval_end_column = columns.interval_end_utc
        spot_price_column = columns.spot_price_per_mwh
    require_non_empty("contracts", contracts)
    if any(not isinstance(contract, PowerHedgeContract) for contract in contracts):
        raise ValidationError("contracts must contain only PowerHedgeContract values")
    column_names = [interval_start_column, interval_end_column, spot_price_column]
    for name, value in (
        ("interval_start_column", interval_start_column),
        ("interval_end_column", interval_end_column),
        ("spot_price_column", spot_price_column),
    ):
        require_non_empty(name, value)
    if len(column_names) != len(set(column_names)):
        raise ValidationError("hedge data column mappings must be distinct")
    hedge_ids = [contract.hedge_id for contract in contracts]
    if len(hedge_ids) != len(set(hedge_ids)):
        raise ValidationError("contracts must have unique hedge_id values")
    required = {interval_start_column, interval_end_column, spot_price_column}
    missing = sorted(required - set(data.columns))
    if missing:
        raise ValidationError(f"data is missing required columns: {', '.join(missing)}")
    if data.height == 0:
        raise ValidationError("data must be non-empty")
    if not data.schema[spot_price_column].is_numeric():
        raise ValidationError(f"data column must be numeric: {spot_price_column}")
    if data.select(pl.col(sorted(required)).null_count()).row(0) != (0, 0, 0):
        raise ValidationError("data contains null hedge-settlement inputs")
    starts = data[interval_start_column]
    if starts.n_unique() != data.height:
        raise ValidationError("data contains duplicate interval starts")
    if not starts.is_sorted():
        raise ValidationError("data intervals must be sorted by interval_start_utc")

    rows: list[dict[str, object]] = []
    for input_row, row in enumerate(data.iter_rows(named=True)):
        try:
            interval = PowerDeliveryInterval(row[interval_start_column], row[interval_end_column])
            spot = float(row[spot_price_column])
            active = [contract for contract in contracts if contract.covers(interval)]
            for contract in active:
                result = settle_power_hedge_interval(contract, interval, spot)
                rows.append(
                    {
                        "input_row": input_row,
                        "hedge_id": result.hedge_id,
                        "hedge_type": contract.hedge_type.value,
                        "position": contract.position.value,
                        "interval_start_utc": interval.start_utc,
                        "interval_end_utc": interval.end_utc,
                        "spot_price_per_mwh": spot,
                        "volume_mwh": result.volume_mwh,
                        "gross_payoff": result.gross_payoff,
                        "premium_cashflow": result.premium_cashflow,
                        "net_cashflow": result.net_cashflow,
                    }
                )
        except (TypeError, ValueError, ValidationError) as exc:
            raise ValidationError(f"invalid hedge data at row {input_row}: {exc}") from exc
    if not rows:
        raise ValidationError("no hedge contract covers any supplied interval")
    return pl.DataFrame(rows)
