"""Execute the complete physical PPA and typed-hedge settlement example."""
from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import quantvolt as qv


def main() -> None:
    start = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    end = datetime(2026, 1, 1, 2, 0, tzinfo=UTC)
    contract = qv.PpaContract(
        "plant-ppa", "DE-LU", 70.0, start, end,
        qv.PpaVolumeBasis.BASELOAD,
        qv.PpaSettlementType.PHYSICAL,
        "Buyer GmbH",
    )
    data = pl.DataFrame(
        {
            "from": [start, datetime(2026, 1, 1, 1, 0, tzinfo=UTC)],
            "to": [datetime(2026, 1, 1, 1, 0, tzinfo=UTC), end],
            "nomination_mwh": [10.0, 10.0],
            "meter_mwh": [8.0, 12.0],
            "day_ahead": [90.0, 80.0],
            "short_buy": [100.0, 95.0],
            "excess_sell": [40.0, 45.0],
        }
    )
    columns = qv.PpaDataColumns(
        interval_start_utc="from",
        interval_end_utc="to",
        contracted_mwh="nomination_mwh",
        metered_generation_mwh="meter_mwh",
        spot_price_per_mwh="day_ahead",
        shortfall_price_per_mwh="short_buy",
        excess_price_per_mwh="excess_sell",
    )
    floor = qv.PowerHedgeContract(
        "revenue-floor",
        qv.PowerHedgeType.FLOOR,
        qv.PowerHedgePosition.LONG,
        start,
        end,
        10.0,
        60.0,
        allocated_premium_per_mwh=2.0,
    )
    ledger = qv.settle_ppa_frame(contract, data, columns=columns, hedges=[floor])
    assert ledger.height == 2
    assert ledger["contracted_mwh"].to_list() == [10.0, 10.0]
    assert ledger["shortfall_mwh"].to_list() == [2.0, 0.0]
    assert ledger["excess_mwh"].to_list() == [0.0, 2.0]
    assert all(value == -20.0 for value in ledger["hedge_cashflow"].to_list())
    print("PPA verified:", ledger.select(pl.col("net_cashflow").sum()).item())


if __name__ == "__main__":
    main()
