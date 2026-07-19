"""Execute the statistics, market-utility, and workflow documentation examples."""

from datetime import date, timedelta

import numpy as np
import polars as pl

from quantvolt.market import Pipeline, degree_days, transmission_cost
from quantvolt.stats import (
    NormalityTestType,
    correlation_matrix,
    descriptive_stats,
    fit_ou,
    moments,
    rolling_correlation,
    test_normality,
    test_stationarity,
)
from quantvolt.workflow import (
    ModelingWorkflow,
    ModelSelectionCriteria,
    StructuredProduct,
)

rng = np.random.default_rng(42)
innovations = rng.normal(0.0, 0.65, 300)
values = np.empty(300)
values[0] = 34.0
for i in range(1, len(values)):
    values[i] = 34.0 + 0.92 * (values[i - 1] - 34.0) + innovations[i]
prices = pl.Series("TTF", values)
dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(len(values))]

summary = descriptive_stats(prices)
central = moments(prices, order=4)
assert summary.n == 300 and set(central) == {1, 2, 3, 4}
for method in NormalityTestType:
    assert test_normality(prices, test_type=method).test_type is method

stationarity = test_stationarity(
    prices,
    contract_expiry=date(2026, 12, 31),
    observation_dates=dates,
    min_observations=30,
)
assert 0.0 <= stationarity.adf_p_value <= 1.0

power = pl.Series("POWER", 45.0 + 1.4 * values + rng.normal(0, 2, 300))
eua = pl.Series("EUA", 80.0 + rng.normal(0, 1.5, 300))
frame = pl.DataFrame({"TTF": prices, "POWER": power, "EUA": eua})
assert correlation_matrix(frame).shape == (3, 4)
assert rolling_correlation(prices, power, window=30).null_count() == 29
ou = fit_ou(prices)
assert ou.reversion_speed > 0.0 and ou.half_life > 0.0

pipeline = Pipeline(distance=120.0, tariff=0.42)
assert transmission_cost(pipeline, volume=10_000.0) == 4_200.0
weather = pl.DataFrame(
    {
        "location": ["Amsterdam"] * 3,
        "date": [date(2026, 1, day) for day in (1, 2, 3)],
        "temp_celsius": [4.0, 7.5, 20.0],
    }
)
features = degree_days(weather)
assert features["hdd"].to_list() == [14.0, 10.5, 0.0]
assert features["cdd"].to_list() == [0.0, 0.0, 2.0]

criteria = ModelSelectionCriteria(
    min_observations=252,
    max_missing_pct=0.05,
    min_r_squared=0.70,
    max_rmse_pct=0.10,
    max_parameter_drift=0.20,
    require_risk_factor_separation=True,
)
product = StructuredProduct(
    name="TTF indexed supply",
    payoff_description="monthly indexed gas delivery",
    risk_factors=("price:gas",),
)
workflow = ModelingWorkflow().run(product, criteria)
assert workflow.steps_executed == (1, 2, 3, 4, 5, 6, 7)
assert workflow.risk_factor_separation_achieved

print(
    "research verified: "
    f"n={summary.n} kappa={ou.reversion_speed:.6f} "
    f"transport={transmission_cost(pipeline, 10_000.0):.2f} "
    f"workflow={workflow.steps_executed}"
)
