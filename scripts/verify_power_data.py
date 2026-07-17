"""Fail-fast integrity audit for the checked-in SMARD power experiment data.

This script performs no network calls and does not rewrite data. Run it after a
download/normalization refresh and before using the PPA experiment outputs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import polars as pl
from data_access import local_or_fetch

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "smard"
PROCESSED = ROOT / "data" / "processed"
PRICE_MANIFEST = RAW / "day_ahead_price_de_lu" / "manifest.json"
FUNDAMENTALS_MANIFEST = RAW / "power_fundamentals_de" / "manifest.json"
PRICE_DATA = PROCESSED / "smard_de_lu_day_ahead_native.parquet"
FUNDAMENTALS_DATA = PROCESSED / "smard_de_power_fundamentals_quarter_hour.parquet"
EXPERIMENT_DATA = PROCESSED / "smard_de_power_experiment_intervals.parquet"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _verify_manifest(path: Path) -> dict[str, object]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _require(manifest.get("source") == "Bundesnetzagentur | SMARD.de", f"bad source: {path}")
    _require(manifest.get("licence") == "CC BY 4.0", f"bad licence: {path}")
    base = path.parent
    files = manifest.get("files")
    _require(isinstance(files, list) and bool(files), f"empty file manifest: {path}")
    for entry in files:
        _require(isinstance(entry, dict), f"malformed manifest entry: {path}")
        raw_path = base / str(entry["path"])
        _require(raw_path.is_file(), f"missing raw file: {raw_path}")
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        _require(digest == entry["sha256"], f"SHA-256 mismatch: {raw_path}")
    return manifest


def _verify_ordered_intervals(frame: pl.DataFrame, minutes: int, label: str) -> None:
    starts = frame["interval_start_utc"]
    _require(starts.n_unique() == frame.height, f"{label}: duplicate interval starts")
    _require(starts.is_sorted(), f"{label}: interval starts are not sorted")
    durations = frame.select(
        (pl.col("interval_end_utc") - pl.col("interval_start_utc")).dt.total_minutes()
    ).to_series()
    _require(bool((durations == minutes).all()), f"{label}: wrong interval duration")
    gaps = starts.diff().drop_nulls().dt.total_minutes()
    _require(bool((gaps == minutes).all()), f"{label}: gap or overlap in UTC timeline")


def main() -> None:
    price_manifest = _verify_manifest(PRICE_MANIFEST)
    fundamentals_manifest = _verify_manifest(FUNDAMENTALS_MANIFEST)

    prices = pl.read_parquet(local_or_fetch(PRICE_DATA, "smard-de-lu-day-ahead"))
    fundamentals = pl.read_parquet(
        local_or_fetch(FUNDAMENTALS_DATA, "smard-de-power-fundamentals")
    )
    experiment = pl.read_parquet(
        local_or_fetch(EXPERIMENT_DATA, "smard-de-power-experiment")
    )

    _require(prices.height == price_manifest["rows"], "price manifest row count mismatch")
    _require(
        fundamentals.height == fundamentals_manifest["rows"],
        "fundamentals manifest row count mismatch",
    )
    _verify_ordered_intervals(fundamentals, 15, "fundamentals")
    _verify_ordered_intervals(experiment, 15, "experiment")

    transition = datetime.fromisoformat(str(price_manifest["native_resolution_transition_utc"]))
    before = prices.filter(pl.col("interval_start_utc") < transition)
    after = prices.filter(pl.col("interval_start_utc") >= transition)
    _require(bool((before["duration_minutes"] == 60).all()), "pre-transition price is not hourly")
    _require(
        bool((after["duration_minutes"] == 15).all()),
        "post-transition price is not 15-minute",
    )
    _require(
        before["interval_end_utc"].max() == transition,
        "hourly price series misses transition",
    )
    _require(
        after["interval_start_utc"].min() == transition,
        "15-minute price series misses transition",
    )
    _require(prices["interval_start_utc"].n_unique() == prices.height, "duplicate price starts")
    _require(
        bool(
            (
                prices["interval_start_utc"].slice(1)
                == prices["interval_end_utc"].slice(0, prices.height - 1)
            ).all()
        ),
        "price timeline has a gap or overlap",
    )

    _require(experiment.height == fundamentals.height, "join changed fundamentals cardinality")
    _require(experiment["price_eur_per_mwh"].null_count() == 0, "unpriced experiment intervals")
    _require(
        bool(
            (
                (experiment["interval_start_utc"] >= experiment["price_product_start_utc"])
                & (experiment["interval_end_utc"] <= experiment["price_product_end_utc"])
            ).all()
        ),
        "experiment interval lies outside its price product",
    )

    counts_by_day = fundamentals.group_by("local_date").len()
    complete_days = counts_by_day.filter(
        (pl.col("local_date") != pl.col("local_date").min())
        & (pl.col("local_date") != pl.col("local_date").max())
    )
    local_counts = complete_days["len"]
    _require(set(local_counts.unique().to_list()) <= {92, 96, 100}, "invalid local-day length")
    _require(bool((local_counts == 92).any()), "no spring DST day found")
    _require(bool((local_counts == 100).any()), "no autumn DST day found")

    print(
        json.dumps(
            {
                "status": "ok",
                "raw_files_verified": len(price_manifest["files"])
                + len(fundamentals_manifest["files"]),
                "price_intervals": prices.height,
                "physical_intervals": fundamentals.height,
                "experiment_intervals": experiment.height,
                "native_price_transition_utc": transition.isoformat(),
                "negative_price_intervals": int((prices["price_eur_per_mwh"] < 0).sum()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
