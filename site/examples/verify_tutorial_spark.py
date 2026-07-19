"""Tutorial: power + gas + EUA curves -> clean spark spread option -> tolling position
in a portfolio -> variance-minimizing hedge (site "Spark spread to hedge" tutorial).

Crosses ``pricing.spreads`` (informational margin), ``pricing.spread_option`` /
``portfolio`` (the priced optionality, native ``SpreadOptionContract`` /
``TollingAgreement`` instruments — no PPA-style registration needed), and
``quantvolt.hedging`` (variance-minimizing ratios against the two commodities the
tolling position is actually exposed to). Every intermediate value printed here is
pasted verbatim into the tutorial-spark page in ``site/complete-guides.js``.
"""

from __future__ import annotations

import numpy as np
from shared_setup import DEC_26, example_market

import quantvolt as qv


def main() -> None:
    market = example_market()
    period = DEC_26

    # 1. Physical clean spark spread: the plant's per-MWh margin if it always ran.
    spark = qv.spark_spread(
        market.power_curve,
        market.ttf_curve,
        heat_rate=2.0,
        variable_cost=3.5,
        emissions_cost=0.0,
    )
    clean = qv.clean_spread(spark, market.eua_curve, emissions_intensity=0.37)
    print("clean spark spread (Dec-26):", round(clean.per_period[period], 4), "EUR/MWh")

    # 2. Clean spark spread OPTION: the right (not obligation) to run in Dec-26.
    #    Kirk's approximation (heat_rate != 1 collapses forward2 -> heat_rate * forward2);
    #    the strike nets out variable O&M plus the (deterministic) carbon cost so the
    #    priced optionality is on power vs. gas only.
    heat_rate = 2.0
    variable_cost = 3.5
    emissions_intensity = 0.37
    eua_forward = market.eua_curve.price_at(period)
    strike = variable_cost + emissions_intensity * eua_forward
    request = qv.SpreadOptionRequest(
        forward1=market.power_curve.price_at(period),
        forward2=market.ttf_curve.price_at(period),
        strike=strike,
        sigma1=0.38,
        sigma2=0.52,
        correlation=0.61,
        time_to_expiry=0.4,
        discount_factor=market.discount_curve.discount_factor(period.last_day),
        notional=1_000.0,
    )
    option = qv.price_spark_spread_option(request, heat_rate=heat_rate)
    print("clean spark spread option premium:", round(option.premium, 2), "EUR")
    print("model: Kirk (approximation; strike != 0)")

    # 3. The same underlying exposure as a richer tolling structure: a TollingAgreement.
    plant = qv.PlantConfig(
        heat_rate=heat_rate,
        variable_om_cost=variable_cost,
        emissions_intensity=emissions_intensity,
        fuel_type="gas",
    )
    schedule = qv.DeliverySchedule((period,))
    tolling = qv.TollingAgreement(
        plant=plant,
        power_commodity_id="EEX_PHELIX_DE",
        fuel_commodity_id="TTF",
        eua_commodity_id="EUA",
        schedule=schedule,
        capacity=1_000.0,
    )
    position = qv.Position(instrument=tolling, position_id="plant-tolling-dec26")
    portfolio = qv.Portfolio((position,))
    vol_surfaces = {
        "EEX_PHELIX_DE": qv.VolatilitySurface(
            commodity=market.power_curve.commodity,
            tenors=(qv.VolatilityTenor(period, 0.38),),
        ),
        "TTF": qv.VolatilitySurface(
            commodity=market.ttf_curve.commodity,
            tenors=(qv.VolatilityTenor(period, 0.52),),
        ),
        "EUA": qv.VolatilitySurface(
            commodity=market.eua_curve.commodity,
            tenors=(qv.VolatilityTenor(period, 0.25),),
        ),
    }
    correlations = {
        ("EEX_PHELIX_DE", "TTF"): 0.61,
        ("EEX_PHELIX_DE", "EUA"): 0.28,
        ("TTF", "EUA"): 0.35,
    }
    market_data = qv.MarketData(
        forward_curves={
            "EEX_PHELIX_DE": market.power_curve,
            "TTF": market.ttf_curve,
            "EUA": market.eua_curve,
        },
        discount_curve=market.discount_curve,
        valuation_date=market.ttf_curve.market_date,
        vol_surfaces=vol_surfaces,
        correlations=correlations,
    )
    valuation = qv.value_portfolio(portfolio, market_data)
    assert len(valuation.priced) == 1
    assert len(valuation.unpriced) == 0
    priced = valuation.priced[0]
    print("tolling position NPV:", round(priced.npv, 2), "EUR")
    fuel_delta = priced.delta[("TTF", period)]
    eua_delta = priced.delta[("EUA", period)]
    print("fuel (TTF) delta:", round(fuel_delta, 4), "EUR per EUR/MWh")
    print("EUA delta:", round(eua_delta, 4), "EUR per EUR/MWh")

    # 4. Variance-minimizing hedge of the tolling position's gas/EUA exposure using
    #    traded TTF and EUA futures. sigma_hh is the assumed covariance of the two hedge
    #    instruments' returns; sigma_ht is each hedge's assumed covariance with the
    #    tolling position's P&L. Both would be *estimated* from historical joint returns
    #    in production; here they are illustrative fixed numbers, not derived from the
    #    deltas above (deriving sigma_ht mechanically from delta would make the optimal
    #    ratio trivially equal to delta and would not illustrate the method).
    sigma_hh = np.array([[4.00, 0.90], [0.90, 1.00]])  # TTF, EUA return covariance (assumed)
    sigma_ht = np.array([-52.0, -14.0])  # TTF-, EUA-with-P&L covariance (assumed)
    hedge_ratios = qv.variance_min_hedge(sigma_hh, sigma_ht)
    print("hedge ratios (TTF futures, EUA futures):", np.round(hedge_ratios, 4).tolist())
    print("(position deltas were TTF", round(fuel_delta, 2), "EUA", round(eua_delta, 2), ")")


if __name__ == "__main__":
    main()
