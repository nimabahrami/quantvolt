"""Normalize the public gas-market datasets stored under ``data/raw``.

Raw source files are intentionally never modified. Run this module from the
repository root after downloading the files listed in ``data/README.md``.
"""

from pathlib import Path

import pandas as pd
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def _write(frame: pd.DataFrame, name: str) -> None:
    """Write stable CSV and Parquet representations of a pandas frame."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    csv_path = PROCESSED / f"{name}.csv"
    frame.to_csv(csv_path, index=False, lineterminator="\n")
    # Reading the stable CSV avoids imposing pyarrow solely for pandas conversion.
    pl.read_csv(csv_path, try_parse_dates=True, infer_schema_length=None).write_parquet(
        PROCESSED / f"{name}.parquet"
    )


def prepare_eia() -> None:
    """Extract daily Henry Hub spot and rolling NYMEX contracts 1-4."""
    source = RAW / "eia" / "NG_PRI_FUT_S1_D.xls"

    spot = pd.read_excel(source, sheet_name="Data 1", skiprows=2)
    spot.columns = ["date", "henry_hub_spot_usd_per_mmbtu"]
    spot["date"] = pd.to_datetime(spot["date"]).dt.date
    spot["henry_hub_spot_usd_per_mmbtu"] = pd.to_numeric(
        spot["henry_hub_spot_usd_per_mmbtu"], errors="coerce"
    )
    spot = spot.dropna(subset=["date", "henry_hub_spot_usd_per_mmbtu"])
    _write(spot, "eia_henry_hub_spot_daily")

    futures = pd.read_excel(source, sheet_name="Data 2", skiprows=2)
    futures.columns = ["date", "contract_1", "contract_2", "contract_3", "contract_4"]
    futures["date"] = pd.to_datetime(futures["date"]).dt.date
    for column in futures.columns[1:]:
        futures[column] = pd.to_numeric(futures[column], errors="coerce")
    futures = futures.dropna(subset=list(futures.columns[1:]), how="all")
    _write(futures, "eia_nymex_gas_futures_daily")


def prepare_world_bank() -> None:
    """Extract the three monthly natural-gas benchmarks from the Pink Sheet."""
    source = RAW / "world_bank" / "CMO-Historical-Data-Monthly.xlsx"
    frame = pd.read_excel(source, sheet_name="Monthly Prices", header=4)
    frame = frame.iloc[:, [0, 7, 8, 9]].copy()
    frame.columns = [
        "period",
        "natural_gas_us_usd_per_mmbtu",
        "natural_gas_europe_usd_per_mmbtu",
        "lng_japan_usd_per_mmbtu",
    ]
    frame = frame[frame["period"].astype(str).str.fullmatch(r"\d{4}M\d{2}")].copy()
    frame.insert(
        0,
        "date",
        pd.to_datetime(frame["period"].str.replace("M", "-", regex=False))
        .dt.to_period("M")
        .dt.to_timestamp(),
    )
    for column in frame.columns[2:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    _write(frame, "world_bank_natural_gas_monthly")


def prepare_jrc() -> None:
    """Normalize JRC ENaGaD daily physical-demand records."""
    source = RAW / "jrc" / "ENAGAD.csv"
    frame = pl.read_csv(
        source,
        skip_rows=25,
        null_values="NA",
        try_parse_dates=True,
        infer_schema_length=None,
    ).rename(
        {
            "GASDAY": "date",
            "COUNTRY": "country",
            "DD": "day",
            "MONTH": "month",
            "YEAR": "year",
            "JULIANDAY": "julian_day",
            "TOT": "total_gwh_per_day",
            "GPP": "power_generation_gwh_per_day",
            "IND": "industry_gwh_per_day",
            "DIS": "distribution_gwh_per_day",
            "OTHER": "other_gwh_per_day",
            "IND+GPP": "industry_and_power_gwh_per_day",
            "PROC": "provenance_flag",
        }
    )
    PROCESSED.mkdir(parents=True, exist_ok=True)
    frame.write_csv(PROCESSED / "jrc_enagad_daily_demand.csv")
    frame.write_parquet(PROCESSED / "jrc_enagad_daily_demand.parquet")


if __name__ == "__main__":
    prepare_eia()
    prepare_world_bank()
    prepare_jrc()
