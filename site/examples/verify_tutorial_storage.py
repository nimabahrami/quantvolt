"""Tutorial: seasonal curve -> storage_intrinsic -> storage_value (extrinsic, seeded) ->
forward hedge built from the intrinsic schedule (site "Storage intrinsic to hedge"
tutorial).

Crosses ``curves`` (the seasonal TTF curve from ``shared_setup.seasonal_gas_curve``),
``quantvolt.assets`` (``storage_intrinsic`` / ``storage_value``) and ``portfolio``
(replicating the intrinsic schedule as monthly futures positions). The tutorial page
is explicit about what this does NOT show: ``storage_intrinsic``'s dynamic program is
**undiscounted** (see the module docstring and the external-validation storage
grid-refinement study), so the futures book built here is a like-for-like forward
replication at the curve's own prices, not a discounted trading P&L.
"""

from __future__ import annotations

from shared_setup import MARKET_DATE, TTF, seasonal_gas_curve

import quantvolt as qv
from quantvolt.assets.storage import (
    StorageFactorModel,
    StorageModel,
    storage_intrinsic,
    storage_value,
)


def main() -> None:
    curve = seasonal_gas_curve()
    periods = [node.period for node in curve.nodes]

    model = StorageModel(
        min_inventory=0.0,
        max_inventory=100.0,
        initial_inventory=50.0,
        terminal_inventory=50.0,
        injection_rate=lambda inventory: 40.0,
        withdrawal_rate=lambda inventory: 40.0,
        injection_cost=0.05,
        withdrawal_cost=0.05,
        injection_loss=0.01,
        withdrawal_loss=0.01,
        carry_cost=0.02,
        terminal_penalty=None,
    )

    # 1. Deterministic intrinsic value: the optimal forward-locked injection/withdrawal
    #    schedule against the seasonal curve (Jan-27 .. Dec-27), 100-step inventory grid.
    intrinsic = storage_intrinsic(model, curve, grid_steps=100)
    print("intrinsic value:", round(intrinsic.value, 2))
    print("injection schedule (MWh):", [round(v, 2) for v in intrinsic.injection])
    print("withdrawal schedule (MWh):", [round(v, 2) for v in intrinsic.withdrawal])
    print("inventory path:", [round(v, 2) for v in intrinsic.inventory])

    # 2. Extrinsic (re-optimisation) value under a seeded single-factor GBM spot model.
    factor_model = StorageFactorModel(volatility=0.5, dt=1.0 / 12.0, path_count=3_000)
    total = storage_value(model, curve, factor_model, seed=7, grid_steps=100)
    print("total value:", round(total.total, 2))
    print("intrinsic (from storage_value):", round(total.intrinsic, 2))
    print("extrinsic value:", round(total.extrinsic, 4))
    print("extrinsic standard error:", round(total.standard_error, 4))
    assert total.intrinsic == intrinsic.value

    # 3. Forward hedge built directly from the intrinsic schedule, BOTH legs:
    #      - buy a future (LONG) in every month with net injection, and
    #      - sell a future (SHORT) in every month with net withdrawal,
    #    each at THAT month's own curve price. Because contract_price equals the curve's
    #    own forward, every position's day-one NPV is exactly
    #    +/- DF * (forward - contract_price) * notional == 0 (long and short alike) --
    #    these trades REPLICATE the schedule's forward-locked purchase and sale, they do
    #    not add extra valuation today.
    #
    #    Direction is carried by FuturesContract.side (OptionSide.LONG / SHORT), never by
    #    a signed notional: notional stays strictly positive and the SHORT withdrawal leg
    #    prices to the exact negation of the same LONG position (the portfolio pricer
    #    sign-flips npv and delta), so the withdrawal (sale) months are now hedged too.
    discount_curve = qv.DiscountCurve(
        reference_date=MARKET_DATE,
        tenors=(periods[0].last_day, periods[-1].last_day),
        factors=(0.99, 0.90),
    )
    positions = []
    for period, injected, withdrawn in zip(
        periods, intrinsic.injection, intrinsic.withdrawal, strict=True
    ):
        if injected >= 1e-9:
            side, notional, leg = qv.OptionSide.LONG, injected, "buy"
        elif withdrawn >= 1e-9:
            side, notional, leg = qv.OptionSide.SHORT, withdrawn, "sell"
        else:
            continue
        future = qv.FuturesContract(
            commodity=TTF,
            delivery_period=period,
            contract_price=curve.price_at(period),
            notional=notional,
            side=side,
        )
        position_id = f"storage-hedge-{leg}-{period.year}-{period.month:02d}"
        positions.append(qv.Position(instrument=future, position_id=position_id))
    hedge_portfolio = qv.Portfolio(tuple(positions))
    market_data = qv.MarketData(
        forward_curves={"TTF": curve}, discount_curve=discount_curve, valuation_date=MARKET_DATE
    )
    valuation = qv.value_portfolio(hedge_portfolio, market_data)
    print("hedge positions:", len(valuation.priced))
    print(
        "hedge book total NPV (must be ~0: transacted at the curve's own forward):",
        round(valuation.total_npv, 8),
    )


if __name__ == "__main__":
    main()
