"""Execute the foundations used by the models, numerics and curves guides."""
from __future__ import annotations

import math

import numpy as np
import quantvolt as qv
from quantvolt.numerics import (
    black76_greeks,
    black76_implied_vol,
    black76_price,
    brent_root,
    build_covariance,
    finite_difference_bump,
    simulate_correlated_forwards,
)

from shared_setup import DEC_26, MARKET_DATE, TTF, example_market


def main() -> None:
    market = example_market()
    assert market.ttf_curve.price_at(DEC_26) == 36.85
    assert {node.status for node in market.ttf_curve.nodes} == {"observed", "interpolated"}

    premium = black76_price("call", 36.85, 38.0, 0.55, 0.4, 0.99)
    greeks = black76_greeks("call", 36.85, 38.0, 0.55, 0.4, 0.99)
    recovered = black76_implied_vol("call", premium, 36.85, 38.0, 0.4, 0.99)
    assert math.isclose(recovered, 0.55, abs_tol=1e-4)
    assert premium > 0.0 and greeks.delta > 0.0

    covariance = build_covariance(
        np.array([0.55, 0.38]),
        np.array([[1.0, 0.61], [0.61, 1.0]]),
        dt=0.5,
    )
    paths = simulate_correlated_forwards(
        z0=np.log(np.array([36.85, 92.0])),
        drift=-0.5 * np.diag(covariance),
        cov=covariance,
        steps=1,
        path_count=10_000,
        seed=42,
    )
    assert paths.shape == (10_000, 2, 2)
    assert np.array_equal(
        paths,
        simulate_correlated_forwards(
            np.log(np.array([36.85, 92.0])),
            -0.5 * np.diag(covariance),
            covariance,
            1,
            10_000,
            42,
        ),
    )

    assert math.isclose(brent_root(lambda x: x * x - 2.0, 0.0, 2.0), math.sqrt(2), abs_tol=1e-4)
    assert math.isclose(finite_difference_bump(lambda x: x * x, 3.0, 1e-4), 6.0, abs_tol=1e-8)
    assert len(qv.check_arbitrage(market.ttf_curve, storage_cost=0.5)) == 3

    future = qv.FuturesContract(TTF, DEC_26, contract_price=35.0, notional=5_000.0)
    result = qv.price_futures(
        future,
        market.ttf_curve,
        MARKET_DATE,
        market.discount_curve,
    )
    assert result.npv > 0.0 and result.delta > 0.0
    print(
        "foundations verified:",
        f"premium={premium:.6f}",
        f"delta={greeks.delta:.6f}",
        f"futures_npv={result.npv:.6f}",
    )


if __name__ == "__main__":
    main()
