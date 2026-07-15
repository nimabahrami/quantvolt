"""Performance SLA benchmarks (Task 51) — pytest-benchmark gates for the six SLAs.

One benchmark per requirement, workload built outside the timed callable:

- Req 1.5  — 120-monthly-period curve build (cubic_spline, the heavy path) < 5 s
- Req 4.5  — swap NPV + Greeks, 120 monthly settlement periods            < 500 ms
- Req 5.5  — single vanilla option, premium + Greeks                      < 50 ms
- Req 6.5  — Asian option, 252-period averaging schedule, closed form     < 2 s
- Req 9.6  — VaR/CVaR/portfolio delta, 500 positions x 252 scenarios      < 60 s
- Req 10.4 — mark-to-market, 500 positions (mixed settled/estimated)      < 30 s

Gate: ``benchmark.stats.stats.max`` must beat the SLA. Max — not mean — is asserted
so CI fails on tail regressions (a single slow round breaches the SLA a caller
would experience), not just on average drift.

Req 6.5 note: the closed forms (Turnbull-Wakeman / Kemna-Vorst) assume continuous
averaging and are schedule-free, so the 252-averaging-point workload collapses to a
single ``price_asian`` call — the same collapse documented in
``tests/unit/test_pricing_exotic.py``.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from quantvolt.curves.builder import CurveBuilder
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import FuturesContract, InstrumentPriceRecord, SwapContract
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.pricing.exotic import AsianOptionRequest, price_asian
from quantvolt.pricing.mark_to_market import MtMPosition, mark_to_market
from quantvolt.pricing.swap import price_swap
from quantvolt.pricing.vanilla import VanillaOptionRequest, price_vanilla_option
from quantvolt.risk.engine import RiskEngine

# Cap calibrated measurement at ~2 s per benchmark so the suite stays moderate
# under plain ``pytest tests/benchmarks -q`` while still collecting enough rounds
# for a meaningful max.
pytestmark = pytest.mark.benchmark(group="sla", max_time=2.0, min_rounds=5)

TTF = BUILT_IN_COMMODITIES["TTF"]
MARKET_DATE = date(2025, 1, 1)

# SLA budgets in seconds, verbatim from requirements.md.
SLA_CURVE_BUILD_120_PERIODS = 5.0  # Req 1.5
SLA_SWAP_120_PERIODS = 0.5  # Req 4.5
SLA_VANILLA_SINGLE_OPTION = 0.05  # Req 5.5
SLA_ASIAN_252_CLOSED_FORM = 2.0  # Req 6.5
SLA_RISK_500_POSITIONS = 60.0  # Req 9.6
SLA_MTM_500_POSITIONS = 30.0  # Req 10.4


def _assert_within_sla(benchmark: BenchmarkFixture, sla_seconds: float) -> None:
    """Hard gate: the worst observed round must beat the SLA (tail, not average)."""
    worst = benchmark.stats.stats.max
    assert worst < sla_seconds, f"SLA regression: worst round {worst:.6f}s >= budget {sla_seconds}s"


def _month_sequence(start_year: int, start_month: int, count: int) -> tuple[DeliveryPeriod, ...]:
    periods: list[DeliveryPeriod] = []
    year, month = start_year, start_month
    for _ in range(count):
        periods.append(DeliveryPeriod(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(periods)


# --- Req 1.5: 120-monthly-period curve build < 5 s ---------------------------


def test_req_1_5_curve_build_120_monthly_periods(benchmark: BenchmarkFixture) -> None:
    builder = CurveBuilder()
    instruments = [
        InstrumentPriceRecord(
            instrument_id=f"TTF-{period.year}-{period.month:02d}",
            commodity=TTF,
            delivery_period=period,
            price=20.0 + 0.1 * index,
        )
        for index, period in enumerate(_month_sequence(2025, 1, 120))
    ]

    result = benchmark(builder.build, TTF, MARKET_DATE, instruments, interpolation="cubic_spline")

    assert len(result.curve.nodes) == 120
    _assert_within_sla(benchmark, SLA_CURVE_BUILD_120_PERIODS)


# --- Req 4.5: 120-period swap < 500 ms ---------------------------------------


def test_req_4_5_swap_120_settlement_periods(benchmark: BenchmarkFixture) -> None:
    periods = _month_sequence(2025, 1, 120)
    swap = SwapContract(
        commodity=TTF,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=DeliverySchedule(periods),
    )
    forward_curve = ForwardCurve(
        commodity=TTF,
        market_date=date(2024, 12, 31),
        nodes=tuple(
            CurveNode(period, 45.0 + 0.1 * index, "observed")
            for index, period in enumerate(periods)
        ),
    )
    discount_curve = DiscountCurve(
        reference_date=date(2024, 12, 31),
        tenors=tuple(period.last_day for period in periods),
        factors=tuple(0.999 ** (index + 1) for index in range(len(periods))),
    )

    result = benchmark(price_swap, swap, forward_curve, discount_curve)

    assert len(result.delta) == 120
    _assert_within_sla(benchmark, SLA_SWAP_120_PERIODS)


# --- Req 5.5: single vanilla option < 50 ms ----------------------------------


def test_req_5_5_single_vanilla_option(benchmark: BenchmarkFixture) -> None:
    request = VanillaOptionRequest(
        option_type="call",
        strike=95.0,
        notional=100.0,
        forward=100.0,
        sigma=0.25,
        time_to_expiry=0.5,
        discount_factor=0.97,
    )

    result = benchmark(price_vanilla_option, request)

    assert result.premium > 0.0
    _assert_within_sla(benchmark, SLA_VANILLA_SINGLE_OPTION)


# --- Req 6.5: 252-averaging-point Asian, closed form < 2 s --------------------


def test_req_6_5_asian_252_periods_closed_form(benchmark: BenchmarkFixture) -> None:
    # Turnbull-Wakeman is continuous-averaging: the 252-point schedule collapses
    # to one closed-form call (see module docstring).
    request = AsianOptionRequest(
        option_type="call",
        averaging="arithmetic",
        strike=95.0,
        forward=100.0,
        sigma=0.25,
        time_to_expiry=1.0,  # a full 252-trading-day averaging year
        discount_factor=0.97,
        method="turnbull_wakeman",
    )

    result = benchmark(price_asian, request)

    assert result.premium > 0.0
    assert result.standard_error is None  # closed form, not Monte Carlo
    _assert_within_sla(benchmark, SLA_ASIAN_252_CLOSED_FORM)


# --- Req 9.6: risk for 500 positions x 252 scenarios < 60 s -------------------


def test_req_9_6_risk_500_positions_252_scenarios(benchmark: BenchmarkFixture) -> None:
    engine = RiskEngine()
    periods = _month_sequence(2026, 1, 6)
    commodities = ("EEX_PHELIX_DE", "TTF")
    futures = FuturesContract(TTF, periods[0], contract_price=30.0, notional=100.0)
    delta = {(commodity, period): 10.0 for commodity in commodities for period in periods}
    positions = [
        PricedPosition(position=Position(futures), npv=float(index), delta=dict(delta))
        for index in range(500)
    ]
    scenario_matrix = np.random.default_rng(7).normal(size=(252, len(commodities) * len(periods)))

    # Heavier workload: pin the round count instead of letting calibration run.
    result = benchmark.pedantic(
        engine.compute_risk,
        args=(positions, scenario_matrix),
        kwargs={"timeout_seconds": 60.0},
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    assert result.partial is False
    assert result.unprocessed_indices == []
    _assert_within_sla(benchmark, SLA_RISK_500_POSITIONS)


# --- Req 10.4: mark-to-market for 500 positions < 30 s ------------------------


def test_req_10_4_mark_to_market_500_positions(benchmark: BenchmarkFixture) -> None:
    periods = _month_sequence(2025, 1, 24)
    # First 12 periods settle; the last 12 fall back to curve marks (estimated),
    # so the 500-position book is mixed settled/estimated.
    settlements: dict[tuple[str, DeliveryPeriod], float] = {
        ("TTF", period): 50.0 + index for index, period in enumerate(periods[:12])
    }
    curve = ForwardCurve(
        commodity=TTF,
        market_date=MARKET_DATE,
        nodes=tuple(
            CurveNode(period=period, price=60.0 + index, status="observed")
            for index, period in enumerate(periods[12:])
        ),
    )
    positions = [
        MtMPosition(
            commodity_id="TTF",
            delivery_period=periods[index % 24],
            notional=10.0 + index,
            trade_price=50.0,
            prior_mark_price=52.0,
        )
        for index in range(500)
    ]

    result = benchmark.pedantic(
        mark_to_market,
        args=(positions, MARKET_DATE, settlements, curve),
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    assert len(result.positions) == 500
    assert 0 < result.estimated_count < 500  # genuinely mixed book
    _assert_within_sla(benchmark, SLA_MTM_500_POSITIONS)
