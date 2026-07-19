"""Execute representative examples from every major pricing family."""

from __future__ import annotations

from datetime import date

from shared_setup import DEC_26, MARKET_DATE, POWER, TTF, example_market

import quantvolt as qv


def main() -> None:
    market = example_market()
    future = qv.FuturesContract(TTF, DEC_26, 35.0, 5_000.0)
    forward = qv.ForwardContract(TTF, DEC_26, 34.5, 5_000.0, counterparty="Utility BV")
    assert qv.price_futures(future, market.ttf_curve, MARKET_DATE, market.discount_curve).npv > 0
    assert qv.price_futures(forward, market.ttf_curve, MARKET_DATE, market.discount_curve).npv > 0

    swap = qv.SwapContract(
        TTF,
        fixed_rate=34.0,
        floating_index="TTF_MONTH_AHEAD",
        notional=2_000.0,
        schedule=qv.DeliverySchedule((DEC_26,)),
    )
    assert len(qv.price_swap(swap, market.ttf_curve, market.discount_curve).delta) == 1

    request = qv.VanillaOptionRequest("call", 38.0, 10_000.0, 36.85, 0.55, 0.4, 0.99)
    vanilla = qv.price_vanilla_option(request)
    assert vanilla.premium > 0 and vanilla.greeks.delta > 0
    cap = qv.price_cap_floor(qv.CapFloorRequest("cap", 38.0, 10_000.0, (request,)))
    assert cap.premium == vanilla.premium

    asian = qv.price_asian(
        qv.AsianOptionRequest(
            "call",
            "arithmetic",
            38.0,
            36.85,
            0.55,
            0.4,
            0.99,
            method="monte_carlo",
            seed=7,
            path_count=10_000,
        )
    )
    barrier = qv.price_barrier(
        qv.BarrierOptionRequest("call", "up_out", 38.0, 55.0, 36.85, 0.55, 0.4, 0.99)
    )
    lookback = qv.price_lookback(
        qv.LookbackOptionRequest("call", "fixed", 36.85, 0.55, 0.4, 0.99, strike=38.0)
    )
    assert asian.standard_error is not None and barrier.premium >= 0 and lookback.premium >= 0

    spread = qv.price_spread_option(
        qv.SpreadOptionRequest(92.0, 73.7, 4.0, 0.38, 0.52, 0.61, 0.5, 0.98, 1_000.0)
    )
    assert spread.premium >= 0

    mtm = qv.mark_to_market(
        [qv.MtMPosition("TTF", DEC_26, 5_000.0, 35.0, 36.0)],
        date(2026, 7, 16),
        {("TTF", DEC_26): 36.85},
        market.ttf_curve,
    )
    assert abs(mtm.positions[0].daily_pnl - 4_250.0) < 1e-9
    assert abs(mtm.positions[0].cumulative_pnl - 9_250.0) < 1e-9

    clean = qv.clean_spread(
        qv.spark_spread(market.power_curve, market.ttf_curve, 2.0, 3.5, 0.0),
        market.eua_curve,
        0.37,
    )
    assert DEC_26 in clean.per_period
    print(
        "pricing verified:",
        f"vanilla={vanilla.premium:.6f}",
        f"asian={asian.premium:.6f}",
        f"spread={spread.premium:.6f}",
        f"clean_spread={clean.per_period[DEC_26]:.6f}",
        f"power={POWER.commodity_id}",
    )


if __name__ == "__main__":
    main()
