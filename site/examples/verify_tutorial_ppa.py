"""Tutorial: degree-days -> jointly-sampled generation/price scenarios ->
settle_ppa_frame WITH contract terms (floor + negative-price clause) ->
cash_flow_at_risk (site "Renewable PPA to CFaR" tutorial).

Crosses ``quantvolt.market`` (weather -> degree-day feature, informational context
for the scenario set), ``quantvolt.models.ppa_terms`` (the embedded floor and
negative-price clause — new contract terms, not a separate hedge instrument),
``quantvolt.pricing.ppa`` (``settle_ppa_frame``) and ``quantvolt.risk``
(``cash_flow_at_risk``). Generation and price are deliberately sampled from the
SAME correlated shock per scenario (merit-order cannibalisation: high wind output
depresses the price in the same hour) — sampling them independently would hide
the exact downside CFaR is meant to measure.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl

import quantvolt as qv
from quantvolt.market import degree_days


def main() -> None:
    # 1. Weather context: heating/cooling degree days from caller-owned temperatures.
    #    (Informational for this tutorial: it shows how a caller would attach a weather
    #    covariate to the same interval calendar the PPA settles against; the scenario
    #    generation below is driven by an explicit correlated shock, not degree days.)
    temperatures = pl.DataFrame(
        {
            "location": ["North Sea"] * 5,
            "date": [date(2026, 1, 1) + timedelta(days=i) for i in range(5)],
            "temp_celsius": [2.0, 4.0, -1.0, 6.0, 9.0],
        }
    )
    features = degree_days(temperatures, base_celsius=15.0)
    print("degree-day feature (day 1):", features.row(0, named=True))

    # 2. A wind PPA: pay-as-produced, fixed price 55 EUR/MWh, with a floor at
    #    30 EUR/MWh and a negative-price clause (no compensation below 0 EUR/MWh).
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 2, tzinfo=UTC)
    contract = qv.PpaContract(
        contract_id="wind-farm-ppa",
        bidding_zone="DE-LU",
        fixed_price_per_mwh=55.0,
        start_utc=start,
        end_utc=end,
        volume_basis=qv.PpaVolumeBasis.PAY_AS_PRODUCED,
        settlement_type=qv.PpaSettlementType.PHYSICAL,
        terms=qv.PpaTerms(
            price=qv.PpaPriceTerms(floor_price_per_mwh=30.0),
            negative_price=qv.NegativePriceClause(
                treatment=qv.NegativePriceTreatment.NO_COMPENSATION,
                threshold_per_mwh=0.0,
            ),
        ),
    )

    # 3. Jointly sample daily generation and price per scenario from ONE correlated
    #    shock (rho = -0.6: high wind output depresses the day-ahead price).
    rng = np.random.default_rng(7)
    n_scenarios = 5_000
    rho = -0.6
    z = rng.standard_normal((n_scenarios, 2))
    generation_shock = z[:, 0]
    price_shock = rho * z[:, 0] + np.sqrt(1.0 - rho**2) * z[:, 1]
    base_generation_mwh, sigma_generation = 400.0, 150.0
    base_price, sigma_price = 55.0, 45.0
    generation_mwh = np.clip(base_generation_mwh + sigma_generation * generation_shock, 0.0, 480.0)
    price_eur_mwh = base_price + sigma_price * price_shock

    scenarios = [
        {"generation_mwh": float(g), "price_eur_mwh": float(p)}
        for g, p in zip(generation_mwh, price_eur_mwh, strict=True)
    ]
    print("scenario count:", len(scenarios))
    print(
        "min / max sampled price:",
        round(min(price_eur_mwh), 2),
        "/",
        round(max(price_eur_mwh), 2),
    )
    print("negative-price scenario share:", round(float((price_eur_mwh < 0).mean()), 4))

    def cashflow_model(scenario: dict[str, float]) -> np.ndarray:
        """Settle one day's PPA cash flow for one jointly-sampled scenario."""
        data = pl.DataFrame(
            {
                "interval_start_utc": [start],
                "interval_end_utc": [end],
                "contracted_mwh": [scenario["generation_mwh"]],
                "metered_generation_mwh": [scenario["generation_mwh"]],
                "spot_price_per_mwh": [scenario["price_eur_mwh"]],
            }
        )
        ledger = qv.settle_ppa_frame(
            contract, data, imbalance_policy=qv.MissingImbalancePricePolicy.USE_SPOT
        )
        return np.array([ledger["net_cashflow"].item()])

    # Sanity: floor + negative-price clause bind on illustrative extreme scenarios.
    low_price = cashflow_model({"generation_mwh": 400.0, "price_eur_mwh": 10.0})[0]
    negative_price = cashflow_model({"generation_mwh": 400.0, "price_eur_mwh": -20.0})[0]
    print("cash flow, generation=400 MWh, price=10 EUR/MWh (floor binds):", round(low_price, 2))
    print(
        "cash flow, generation=400 MWh, price=-20 EUR/MWh (no-compensation clause binds):",
        round(negative_price, 2),
    )

    cfar = qv.cash_flow_at_risk(
        cashflow_model,
        scenarios,
        horizon=1,
        seed=7,
        consistency={"generation": "same correlated shock as price (merit-order effect)"},
        confidence_level=0.95,
    )
    print("expected cash flow:", round(cfar.expected, 2))
    print("p5 cash flow:", round(cfar.p5, 2))
    print("CFaR 95:", round(cfar.cfar_95, 2))


if __name__ == "__main__":
    main()
