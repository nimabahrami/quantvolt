"""Run a transparent PPA risk-management check on real SMARD observations.

This is a software-validation experiment, not an investable backtest. National
onshore-wind output is scaled into a documented virtual 10 MW profile; it is not
represented as a real plant. Contract quantities, fixed price, floor strike, and
the historical premium proxy use 2019-2021 only. Evaluation is 2022-2025.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from data_access import local_or_fetch

from quantvolt import (
    PowerDeliveryInterval,
    PpaContract,
    PpaNominationColumns,
    PpaNominationObjective,
    PpaVolumeBasis,
    apply_ppa_nomination,
    calibrate_ppa_nomination,
    compare_cashflow_strategies,
    settle_ppa_interval,
    walk_forward_ppa_nomination,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "processed" / "smard_de_power_experiment_intervals.parquet"
OUTPUT = ROOT / "data" / "experiments"
CALIBRATION_START = datetime(2019, 1, 1, tzinfo=UTC)
CALIBRATION_END = datetime(2022, 1, 1, tzinfo=UTC)
EVALUATION_START = CALIBRATION_END
EVALUATION_END = datetime(2026, 1, 1, tzinfo=UTC)
VIRTUAL_CAPACITY_MW = 10.0
INTERVAL_HOURS = 0.25


def _summary(frame: pl.DataFrame, column: str) -> dict[str, float | int]:
    values = frame[column]
    mean = float(values.mean())
    p05 = float(values.quantile(0.05, interpolation="linear"))
    return {
        "total_eur": float(values.sum()),
        "monthly_mean_eur": mean,
        "monthly_std_eur": float(values.std()),
        "monthly_p05_eur": p05,
        "monthly_min_eur": float(values.min()),
        "monthly_max_eur": float(values.max()),
        "monthly_cfar95_eur": max(mean - p05, 0.0),
        "negative_months": int((values < 0.0).sum()),
    }


def main() -> None:
    input_path = local_or_fetch(INPUT, "smard-de-power-experiment")
    data = pl.read_parquet(input_path).filter(
        (pl.col("interval_start_utc") >= CALIBRATION_START)
        & (pl.col("interval_start_utc") < EVALUATION_END)
    )
    calibration = data.filter(pl.col("interval_start_utc") < CALIBRATION_END)
    max_interval_energy = VIRTUAL_CAPACITY_MW * INTERVAL_HOURS
    national_wind_q99 = float(
        calibration["wind_onshore_generation_mwh"].quantile(0.99, interpolation="linear")
    )
    scale = max_interval_energy / national_wind_q99
    data = data.with_columns(
        (pl.col("wind_onshore_generation_mwh") * scale)
        .clip(upper_bound=max_interval_energy)
        .alias("virtual_generation_mwh")
    )
    calibration = data.filter(pl.col("interval_start_utc") < CALIBRATION_END)
    evaluation = data.filter(pl.col("interval_start_utc") >= EVALUATION_START)

    contracted_mwh = float(
        calibration["virtual_generation_mwh"].quantile(0.25, interpolation="linear")
    )
    fixed_price = float(
        (calibration["virtual_generation_mwh"] * calibration["price_eur_per_mwh"]).sum()
        / calibration["virtual_generation_mwh"].sum()
    )
    floor_strike = float(calibration["price_eur_per_mwh"].quantile(0.25, interpolation="linear"))
    calibration_floor_payoff = (pl.lit(floor_strike) - pl.col("price_eur_per_mwh")).clip(
        lower_bound=0.0
    ) * pl.col("virtual_generation_mwh")
    floor_premium_per_mwh = float(
        calibration.select(calibration_floor_payoff.sum()).item()
        / calibration["virtual_generation_mwh"].sum()
    )

    optimization_contract = PpaContract(
        contract_id="calibration-only-baseload-optimization",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=fixed_price,
        start_utc=CALIBRATION_START,
        end_utc=EVALUATION_END,
        volume_basis=PpaVolumeBasis.BASELOAD,
    )
    nomination_fit = calibrate_ppa_nomination(
        optimization_contract,
        calibration.with_columns(
            pl.col("price_eur_per_mwh").alias("shortfall_price_per_mwh"),
            pl.col("price_eur_per_mwh").alias("excess_price_per_mwh"),
        ),
        calibration_end_utc=CALIBRATION_END,
        capacity_mwh_per_interval=max_interval_energy,
        columns=PpaNominationColumns(metered_generation_mwh="virtual_generation_mwh"),
        objective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
        risk_aversion=1.0,
        confidence_level=0.95,
        grid_steps=100,
    )
    evaluation = apply_ppa_nomination(
        nomination_fit,
        evaluation,
        output_column="optimized_contracted_mwh",
    )
    optimized_contracted_mwh = nomination_fit.selected_mwh_per_interval
    walk_forward = walk_forward_ppa_nomination(
        optimization_contract,
        data.with_columns(
            pl.col("price_eur_per_mwh").alias("shortfall_price_per_mwh"),
            pl.col("price_eur_per_mwh").alias("excess_price_per_mwh"),
        ),
        [datetime(year, 1, 1, tzinfo=UTC) for year in range(2022, 2026)],
        evaluation_end_utc=EVALUATION_END,
        capacity_mwh_per_interval=max_interval_energy,
        columns=PpaNominationColumns(metered_generation_mwh="virtual_generation_mwh"),
        objective=PpaNominationObjective.MAX_MEAN_MINUS_CFAR,
        risk_aversion=1.0,
        confidence_level=0.95,
        grid_steps=100,
    )
    walk_evaluation = walk_forward.evaluation
    if not evaluation["interval_start_utc"].equals(walk_evaluation["interval_start_utc"]):
        raise AssertionError("walk-forward output does not align with evaluation data")
    evaluation = evaluation.with_columns(
        walk_evaluation["contracted_mwh"].alias("walk_forward_contracted_mwh"),
        walk_evaluation["walk_forward_fit_index"],
    )

    evaluation = evaluation.with_columns(
        (pl.col("virtual_generation_mwh") * pl.col("price_eur_per_mwh")).alias(
            "merchant_cashflow_eur"
        ),
        (
            contracted_mwh * fixed_price
            + (pl.col("virtual_generation_mwh") - contracted_mwh) * pl.col("price_eur_per_mwh")
        ).alias("baseload_ppa_cashflow_eur"),
        (
            pl.col("optimized_contracted_mwh") * fixed_price
            + (pl.col("virtual_generation_mwh") - pl.col("optimized_contracted_mwh"))
            * pl.col("price_eur_per_mwh")
        ).alias("optimized_baseload_ppa_cashflow_eur"),
        (
            pl.col("walk_forward_contracted_mwh") * fixed_price
            + (pl.col("virtual_generation_mwh") - pl.col("walk_forward_contracted_mwh"))
            * pl.col("price_eur_per_mwh")
        ).alias("walk_forward_baseload_ppa_cashflow_eur"),
        (pl.col("virtual_generation_mwh") * fixed_price).alias("pay_as_produced_ppa_cashflow_eur"),
        (
            pl.col("virtual_generation_mwh") * pl.col("price_eur_per_mwh")
            + (pl.lit(floor_strike) - pl.col("price_eur_per_mwh")).clip(lower_bound=0.0)
            * pl.col("virtual_generation_mwh")
            - floor_premium_per_mwh * pl.col("virtual_generation_mwh")
        ).alias("floor_proxy_cashflow_eur"),
    )

    # Cross-check the vectorized physical-PPA formula against the public ledger API.
    contract = PpaContract(
        contract_id="validation-baseload-ppa",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=fixed_price,
        start_utc=EVALUATION_START,
        end_utc=EVALUATION_END,
        volume_basis=PpaVolumeBasis.BASELOAD,
    )
    for row in evaluation.head(100).iter_rows(named=True):
        result = settle_ppa_interval(
            contract,
            PowerDeliveryInterval(row["interval_start_utc"], row["interval_end_utc"]),
            contracted_mwh=contracted_mwh,
            metered_generation_mwh=row["virtual_generation_mwh"],
            spot_price_per_mwh=row["price_eur_per_mwh"],
        )
        expected = row["baseload_ppa_cashflow_eur"]
        if abs(result.net_cashflow - expected) > 1e-9:
            raise AssertionError("vectorized PPA backtest disagrees with interval ledger")

    monthly = (
        evaluation.with_columns(pl.col("interval_start_utc").dt.truncate("1mo").alias("month"))
        .group_by("month")
        .agg(
            pl.col("virtual_generation_mwh").sum(),
            pl.col("merchant_cashflow_eur").sum(),
            pl.col("baseload_ppa_cashflow_eur").sum(),
            pl.col("optimized_baseload_ppa_cashflow_eur").sum(),
            pl.col("walk_forward_baseload_ppa_cashflow_eur").sum(),
            pl.col("pay_as_produced_ppa_cashflow_eur").sum(),
            pl.col("floor_proxy_cashflow_eur").sum(),
        )
        .sort("month")
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    monthly.write_csv(OUTPUT / "power_ppa_backtest_monthly.csv")
    monthly.write_parquet(OUTPUT / "power_ppa_backtest_monthly.parquet")

    strategies = {
        "merchant": "merchant_cashflow_eur",
        "baseload_ppa": "baseload_ppa_cashflow_eur",
        "optimized_baseload_ppa": "optimized_baseload_ppa_cashflow_eur",
        "walk_forward_baseload_ppa": "walk_forward_baseload_ppa_cashflow_eur",
        "pay_as_produced_ppa": "pay_as_produced_ppa_cashflow_eur",
        "floor_proxy": "floor_proxy_cashflow_eur",
    }
    comparison = compare_cashflow_strategies(
        monthly, strategies, benchmark="merchant", confidence_level=0.95
    )
    total_generation = float(monthly["virtual_generation_mwh"].sum())
    summary = {
        "status": "software-validation experiment; not investment advice or a plant forecast",
        "data_source": "Bundesnetzagentur | SMARD.de (CC BY 4.0)",
        "profile": "national German onshore-wind shape scaled to a virtual 10 MW cap",
        "calibration_period_utc": [
            CALIBRATION_START.isoformat(),
            CALIBRATION_END.isoformat(),
        ],
        "evaluation_period_utc": [EVALUATION_START.isoformat(), EVALUATION_END.isoformat()],
        "calibrated_terms": {
            "national_wind_q99_mwh": national_wind_q99,
            "national_to_virtual_scale": scale,
            "baseload_contract_mwh_per_15min": contracted_mwh,
            "optimized_baseload_contract_mwh_per_15min": optimized_contracted_mwh,
            "optimized_nomination_objective": nomination_fit.objective.value,
            "optimized_nomination_risk_aversion": nomination_fit.risk_aversion,
            "optimized_nomination_confidence_level": nomination_fit.confidence_level,
            "walk_forward_nomination_mwh_per_15min": [
                fit.selected_mwh_per_interval for fit in walk_forward.fits
            ],
            "walk_forward_calibration_end_utc": [
                fit.calibration_end_utc.isoformat() for fit in walk_forward.fits
            ],
            "ppa_fixed_price_eur_per_mwh": fixed_price,
            "floor_strike_eur_per_mwh": floor_strike,
            "floor_historical_premium_proxy_eur_per_mwh": floor_premium_per_mwh,
        },
        "limitations": [
            "National wind shape is synthetic when scaled; it is not a real plant meter.",
            (
                "Shortfall and excess settle at day-ahead price because imbalance data "
                "is not yet joined."
            ),
            (
                "Floor premium is a calibration-period historical payoff proxy, not a "
                "traded option quote."
            ),
            (
                "Cash flows are gross market revenue before plant capex, fixed opex, tax, "
                "and financing."
            ),
        ],
        "total_generation_mwh": total_generation,
        "strategies": {
            name: {
                **_summary(monthly, column),
                "capture_price_eur_per_mwh": float(monthly[column].sum()) / total_generation,
            }
            for name, column in strategies.items()
        },
        "benchmark_comparison": {
            item.strategy: {
                "total_difference_vs_merchant_eur": item.total_difference_vs_benchmark,
                "cfar95_reduction_vs_merchant_eur": item.cfar_reduction_vs_benchmark,
                "monthly_volatility_reduction_vs_merchant_eur": (
                    item.volatility_reduction_vs_benchmark
                ),
            }
            for item in comparison.metrics
        },
    }
    (OUTPUT / "power_ppa_backtest_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
