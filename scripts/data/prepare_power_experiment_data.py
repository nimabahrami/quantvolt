"""Align native day-ahead prices with quarter-hour physical power observations.

Before 2025-10-01 an hourly auction product prices four physical 15-minute
metering intervals.  The output retains both clocks explicitly so repeating an
hourly settlement price across its four underlying meter intervals is visible,
not mistaken for four separately traded historical products.
"""

from pathlib import Path

import polars as pl
from data_access import local_or_fetch

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"


def main() -> None:
    price_path = local_or_fetch(
        PROCESSED / "smard_de_lu_day_ahead_native.parquet",
        "smard-de-lu-day-ahead",
    )
    fundamentals_path = local_or_fetch(
        PROCESSED / "smard_de_power_fundamentals_quarter_hour.parquet",
        "smard-de-power-fundamentals",
    )
    prices = pl.read_parquet(price_path).select(
        pl.col("interval_start_utc").alias("price_product_start_utc"),
        pl.col("interval_end_utc").alias("price_product_end_utc"),
        pl.col("duration_minutes").alias("price_product_duration_minutes"),
        "price_eur_per_mwh",
    )
    physical = pl.read_parquet(fundamentals_path).sort("interval_start_utc")
    aligned = physical.join_asof(
        prices.sort("price_product_start_utc"),
        left_on="interval_start_utc",
        right_on="price_product_start_utc",
        strategy="backward",
    ).filter(pl.col("interval_start_utc") < pl.col("price_product_end_utc"))
    if aligned.height != physical.height:
        raise RuntimeError(
            "not every physical interval mapped to exactly one active price product: "
            f"physical={physical.height}, aligned={aligned.height}"
        )
    if aligned["price_eur_per_mwh"].null_count() != 0:
        raise RuntimeError("aligned power experiment data contains an unpriced physical interval")

    aligned = aligned.with_columns(
        (
            pl.col("wind_onshore_generation_mwh")
            + pl.col("wind_offshore_generation_mwh")
            + pl.col("solar_generation_mwh")
        ).alias("renewable_generation_mwh"),
        (
            pl.col("total_load_mwh")
            - pl.col("wind_onshore_generation_mwh")
            - pl.col("wind_offshore_generation_mwh")
            - pl.col("solar_generation_mwh")
        ).alias("residual_load_mwh"),
    )
    PROCESSED.mkdir(parents=True, exist_ok=True)
    aligned.write_csv(PROCESSED / "smard_de_power_experiment_intervals.csv")
    aligned.write_parquet(PROCESSED / "smard_de_power_experiment_intervals.parquet")


if __name__ == "__main__":
    main()
