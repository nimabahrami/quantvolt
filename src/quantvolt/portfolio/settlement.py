"""Realized interval settlement for PPA and power-hedge portfolio positions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import polars as pl

from ..exceptions import ValidationError
from ..models.power_hedge import PowerHedgeContract
from ..models.ppa import PpaContract
from ..pricing.power_hedge import PowerHedgeDataColumns, settle_power_hedges_frame
from ..pricing.ppa import (
    MissingImbalancePricePolicy,
    PpaDataColumns,
    settle_ppa_frame,
)
from .model import Portfolio, Position


@dataclass(frozen=True, slots=True)
class SettledPortfolioPosition:
    """One interval-settled position and its immutable aggregate result."""

    position: Position
    ledger: pl.DataFrame
    total_cashflow: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "ledger", self.ledger.clone())


@dataclass(frozen=True, slots=True)
class PortfolioSettlement:
    """Realized PPA/hedge cash flow plus positions not handled by this engine."""

    total_cashflow: float
    settled: tuple[SettledPortfolioPosition, ...]
    unsettled: tuple[Position, ...]


def _position_data_key(position: Position) -> str:
    if position.position_id is None or not position.position_id.strip():
        raise ValidationError(
            "interval-settled PPA and hedge positions require a non-empty position_id"
        )
    return position.position_id


def settle_energy_portfolio(
    portfolio: Portfolio,
    interval_data: Mapping[str, pl.DataFrame],
    *,
    ppa_columns: Mapping[str, PpaDataColumns] | None = None,
    hedge_columns: Mapping[str, PowerHedgeDataColumns] | None = None,
    imbalance_policies: Mapping[str, MissingImbalancePricePolicy] | None = None,
) -> PortfolioSettlement:
    """Settle all PPA and typed power-hedge positions using caller-owned data.

    ``interval_data`` is keyed by ``Position.position_id``. Other financial
    instruments remain in ``unsettled`` because their realized exchange/OTC
    settlement conventions belong to their own engines. PPA hedges represented as
    separate portfolio positions are not also embedded in the PPA ledger, preventing
    double counting at aggregation.
    """
    columns_by_id = dict(ppa_columns or {})
    hedge_columns_by_id = dict(hedge_columns or {})
    policies_by_id = dict(imbalance_policies or {})
    interval_positions = [
        position
        for position in portfolio
        if isinstance(position.instrument, PpaContract | PowerHedgeContract)
    ]
    keys = [_position_data_key(position) for position in interval_positions]
    if len(keys) != len(set(keys)):
        raise ValidationError("interval-settled portfolio position_id values must be unique")
    required_keys = set(keys)
    supplied_keys = set(interval_data)
    missing = sorted(required_keys - supplied_keys)
    extra = sorted(supplied_keys - required_keys)
    if missing:
        raise ValidationError(f"interval_data is missing position_id values: {', '.join(missing)}")
    if extra:
        raise ValidationError(f"interval_data has unknown position_id values: {', '.join(extra)}")
    invalid_column_keys = sorted(set(columns_by_id) - required_keys)
    invalid_hedge_column_keys = sorted(set(hedge_columns_by_id) - required_keys)
    invalid_policy_keys = sorted(set(policies_by_id) - required_keys)
    if invalid_column_keys or invalid_hedge_column_keys or invalid_policy_keys:
        invalid = sorted(set(invalid_column_keys + invalid_hedge_column_keys + invalid_policy_keys))
        raise ValidationError(
            f"PPA configuration has unknown position_id values: {', '.join(invalid)}"
        )

    settled: list[SettledPortfolioPosition] = []
    unsettled: list[Position] = []
    for position in portfolio:
        instrument = position.instrument
        if not isinstance(instrument, PpaContract | PowerHedgeContract):
            unsettled.append(position)
            continue
        key = _position_data_key(position)
        data = interval_data[key]
        if isinstance(instrument, PpaContract):
            if key in hedge_columns_by_id:
                raise ValidationError(f"hedge-only configuration was supplied for PPA {key!r}")
            ledger = settle_ppa_frame(
                instrument,
                data,
                columns=columns_by_id.get(key),
                imbalance_policy=policies_by_id.get(key, MissingImbalancePricePolicy.ERROR),
            )
        else:
            if key in columns_by_id or key in policies_by_id:
                raise ValidationError(f"PPA-only configuration was supplied for hedge {key!r}")
            ledger = settle_power_hedges_frame(
                [instrument], data, columns=hedge_columns_by_id.get(key)
            )
        total = float(ledger["net_cashflow"].sum())
        settled.append(SettledPortfolioPosition(position, ledger, total))
    return PortfolioSettlement(
        total_cashflow=float(sum(item.total_cashflow for item in settled)),
        settled=tuple(settled),
        unsettled=tuple(unsettled),
    )
