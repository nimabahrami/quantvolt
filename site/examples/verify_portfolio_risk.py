"""End-to-end run of the documentation site's "Portfolio valuation & risk" guide.

Self-contained: every object the guide's numbered blocks use — commodities,
both forward curves, discount curve, portfolio, scenario matrix — is built
inline, in the same order as the page, and every printed number is pasted
verbatim into the guide in ``site/content.js``. If a future change makes this
script print different numbers, the page has drifted and must be regenerated.

The TTF curve and discount curve deliberately repeat the Quickstart inputs
(three observed TTF quotes, piecewise-linear), so the gas future's NPV here
matches the Quickstart book NPV.
"""

from __future__ import annotations

from datetime import date

import numpy as np

import quantvolt as qv


def main() -> None:
    market_date = date(2026, 7, 15)
    ttf = qv.BUILT_IN_COMMODITIES["TTF"]
    power = qv.BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]

    # --- Forward curves (guide block 3 setup) --------------------------------
    ttf_curve = (
        qv.CurveBuilder()
        .build(
            ttf,
            market_date,
            [
                qv.InstrumentPriceRecord("TTF-OCT26", ttf, qv.DeliveryPeriod(2026, 10), 31.40),
                qv.InstrumentPriceRecord("TTF-DEC26", ttf, qv.DeliveryPeriod(2026, 12), 36.85),
                qv.InstrumentPriceRecord("TTF-MAR27", ttf, qv.DeliveryPeriod(2027, 3), 34.10),
            ],
            interpolation="piecewise_linear",
        )
        .curve
    )
    power_curve = (
        qv.CurveBuilder()
        .build(
            power,
            market_date,
            [
                qv.InstrumentPriceRecord("PHELIX-OCT26", power, qv.DeliveryPeriod(2026, 10), 88.40),
                qv.InstrumentPriceRecord("PHELIX-DEC26", power, qv.DeliveryPeriod(2026, 12), 92.00),
                qv.InstrumentPriceRecord("PHELIX-MAR27", power, qv.DeliveryPeriod(2027, 3), 85.30),
            ],
            interpolation="piecewise_linear",
        )
        .curve
    )

    # --- 1. Create the instruments -------------------------------------------
    period = qv.DeliveryPeriod(2026, 12)
    gas_future = qv.FuturesContract(
        commodity=ttf,
        delivery_period=period,
        contract_price=35.00,
        notional=5_000.0,
    )
    power_schedule = qv.DeliverySchedule((period,))
    power_swap = qv.SwapContract(
        commodity=power,
        fixed_rate=82.00,
        floating_index="EPEX_SPOT_DE",
        notional=1_000.0,
        schedule=power_schedule,
    )

    # --- 2. Positions with stable IDs ----------------------------------------
    portfolio = qv.Portfolio(
        positions=(
            qv.Position(
                instrument=gas_future,
                position_id="gas-future-dec26",
                tags=("desk:gas", "strategy:winter-hedge"),
            ),
            qv.Position(
                instrument=power_swap,
                position_id="power-swap-dec26",
                tags=("desk:power", "strategy:generation-hedge"),
            ),
        )
    )

    # --- 3. Market data -------------------------------------------------------
    discounting = qv.DiscountCurve(
        reference_date=market_date,
        tenors=(date(2026, 7, 16), date(2027, 12, 31)),
        factors=(1.0, 0.96),
    )
    market = qv.MarketData(
        forward_curves={"TTF": ttf_curve, "EEX_PHELIX_DE": power_curve},
        discount_curve=discounting,
        valuation_date=market_date,
    )

    # --- 4. Value the portfolio ----------------------------------------------
    valuation = qv.value_portfolio(portfolio, market)
    assert len(valuation.priced) == 2 and len(valuation.unpriced) == 0
    for item in valuation.priced:
        print(f"{item.position.position_id:<18}  EUR {item.npv:>9,.0f}")
    print(f"{'total NPV':<18}  EUR {valuation.total_npv:>9,.0f}")

    # --- 5. Scenario VaR / CVaR ------------------------------------------------
    scenarios = np.random.default_rng(42).normal(loc=0.0, scale=1.5, size=(10_000, 2))
    risk = qv.RiskEngine().compute_risk(list(valuation.priced), scenarios)
    print(f"VaR 95     EUR {risk.var_95:,.0f}")
    print(f"VaR 99     EUR {risk.var_99:,.0f}")
    print(f"CVaR 97.5  EUR {risk.cvar_975:,.0f}")

    # --- 6. Named stress scenario ----------------------------------------------
    stress = qv.RiskEngine().apply_scenario(list(valuation.priced), "European Gas Crisis 2022")
    print(f"stress P&L EUR {stress.total_pnl:+,.0f}")

    # --- 7. Factor ordering / delta aggregation --------------------------------
    matrix = qv.aggregate_delta(list(valuation.priced))
    print("commodities:", matrix.commodities)
    print("periods:    ", [f"{p.year}-{p.month:02d}" for p in matrix.periods])
    print("values:     ", np.round(matrix.values, 1).tolist())


if __name__ == "__main__":
    main()
