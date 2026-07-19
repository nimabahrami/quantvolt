"""End-to-end run of the documentation site's Quickstart guide (site "Quickstart" page).

Self-contained by design (unlike the other ``verify_*.py`` scripts in this
directory, it does not import ``shared_setup``): a Quickstart is the reader's
very first QuantVolt program, so every object it needs — commodity, curve,
market data, portfolio, scenario matrix — is constructed inline, exactly as it
should appear on the docs page. The three sections below map 1:1 onto the
three Quickstart guide blocks (curve, option, portfolio risk) and each section
is independently copy-pasteable: re-run in isolation (with its own imports),
it reproduces the same numbers, because ``MARKET_DATE`` and the TTF quotes are
repeated rather than threaded through shared state.

Every printed number here is pasted verbatim into the Quickstart page in
``site/content.js``. If a future change makes this script print different
numbers, the page has drifted and must be regenerated.
"""

from __future__ import annotations

from datetime import date

import numpy as np

import quantvolt as qv


def main() -> None:
    # ------------------------------------------------------------------
    # 1. Build a forward curve from observed instrument prices.
    # ------------------------------------------------------------------
    market_date = date(2026, 7, 15)
    ttf = qv.BUILT_IN_COMMODITIES["TTF"]
    observed = [
        qv.InstrumentPriceRecord("TTF-OCT26", ttf, qv.DeliveryPeriod(2026, 10), 31.40),
        qv.InstrumentPriceRecord("TTF-DEC26", ttf, qv.DeliveryPeriod(2026, 12), 36.85),
        qv.InstrumentPriceRecord("TTF-MAR27", ttf, qv.DeliveryPeriod(2027, 3), 34.10),
    ]
    build_result = qv.CurveBuilder().build(
        ttf, market_date, observed, interpolation="piecewise_linear"
    )
    curve = build_result.curve
    assert len(curve.nodes) == 6
    for node in curve.nodes:
        label = f"{node.period.year} {node.period.month:02d}"
        print(f"{label}  {node.price:6.2f}  {node.status}")

    # ------------------------------------------------------------------
    # 2. Price a European call option on the Dec-26 forward (Black-76).
    # ------------------------------------------------------------------
    dec_26_forward = curve.price_at(qv.DeliveryPeriod(2026, 12))
    option = qv.price_vanilla_option(
        qv.VanillaOptionRequest(
            option_type="call",
            strike=38.0,
            notional=10_000.0,
            forward=dec_26_forward,
            sigma=0.55,
            time_to_expiry=0.4,
            discount_factor=0.99,
        )
    )
    assert option.premium > 0.0 and option.greeks.delta > 0.0
    print(f"premium   EUR {option.premium:,.0f}")
    print(f"delta     {option.greeks.delta:,.0f} EUR per EUR/MWh")

    # ------------------------------------------------------------------
    # 3. Value a small book and measure its risk.
    #
    #    RiskEngine.compute_risk's scenario_matrix has one column per
    #    (commodity, delivery period) risk factor in the book's *aggregated*
    #    delta grid (row-major: commodities sorted lexicographically, then
    #    periods chronologically — see quantvolt.risk.engine's module
    #    docstring). This book has exactly one commodity (TTF) and one
    #    delivery period (Dec-26) in scope, so the grid has 1 factor and
    #    scenario_matrix has shape (n_scenarios, 1).
    # ------------------------------------------------------------------
    future = qv.FuturesContract(
        ttf, qv.DeliveryPeriod(2026, 12), contract_price=35.0, notional=5_000.0
    )
    portfolio = qv.Portfolio(positions=(qv.Position(instrument=future),))
    discount_curve = qv.DiscountCurve(
        reference_date=market_date,
        tenors=(date(2026, 7, 16), date(2027, 12, 31)),
        factors=(1.0, 0.96),
    )
    market = qv.MarketData(
        forward_curves={"TTF": curve},
        discount_curve=discount_curve,
        valuation_date=market_date,
    )
    valuation = qv.value_portfolio(portfolio, market)
    assert len(valuation.priced) == 1 and len(valuation.unpriced) == 0

    scenarios = np.random.default_rng(42).normal(loc=0.0, scale=1.5, size=(500, 1))
    risk = qv.RiskEngine().compute_risk(list(valuation.priced), scenarios)
    print(f"Book NPV    EUR {valuation.total_npv:,.0f}")
    print(f"VaR 95      EUR {risk.var_95:,.0f}")
    print(f"VaR 99      EUR {risk.var_99:,.0f}")
    print(f"CVaR 97.5   EUR {risk.cvar_975:,.0f}")


if __name__ == "__main__":
    main()
