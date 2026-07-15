"""Chapter-10 performance benchmarks (Task 78) — pytest-benchmark gates.

Three workloads, each built outside the timed callable, gated on
``benchmark.stats.stats.max`` (the worst observed round, so CI fails on tail
regressions rather than average drift — matching ``test_sla_benchmarks``):

- **Req 14.5** — parametric VaR on 2000 risk factors                < 2 s   (spec SLA)
- **Correlated-MC throughput** — ``simulate_correlated_forwards``,
  10k paths x 12 steps x 6 factors                                  < 5 s   (reference)
- **Dispatch-SDP timing budget** — a small LSM ``dispatch_value``   < 30 s  (reference)

Only the parametric-VaR ceiling is a requirements.md SLA (Req 14.5). The correlated-MC
and dispatch ceilings are generous throughput references documenting the current
performance envelope, not contractual limits — they guard against order-of-magnitude
regressions in the Rust kernel and the LSM engine.
"""

from __future__ import annotations

import numpy as np
import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from quantvolt.assets.dispatch_sdp import DispatchFactorModel, PeakKind, dispatch_value
from quantvolt.assets.plant import MaxCapacityCurve, PlantModel, StartCost, StartState
from quantvolt.numerics.monte_carlo import build_covariance, simulate_correlated_forwards
from quantvolt.numerics.risk_adjustment import DriftKind
from quantvolt.risk.parametric_var import parametric_var

# Cap calibrated measurement at ~2 s per benchmark so the suite stays moderate under
# plain ``pytest tests/benchmarks -q`` while still collecting enough rounds for a
# meaningful max.
pytestmark = pytest.mark.benchmark(group="ch10", max_time=2.0, min_rounds=5)

# Budgets in seconds.
SLA_PARAMETRIC_VAR_2000_FACTORS = 2.0  # Req 14.5 (spec SLA)
CEILING_CORRELATED_MC = 5.0  # throughput reference, not a spec SLA
CEILING_DISPATCH_LSM = 30.0  # throughput reference, not a spec SLA


def _assert_within(benchmark: BenchmarkFixture, budget_seconds: float) -> None:
    """Hard gate: the worst observed round must beat the budget (tail, not average)."""
    worst = benchmark.stats.stats.max
    assert worst < budget_seconds, (
        f"performance regression: worst round {worst:.6f}s >= budget {budget_seconds}s"
    )


# --- Req 14.5: parametric VaR, 2000 factors < 2 s ----------------------------


def test_req_14_5_parametric_var_2000_factors(benchmark: BenchmarkFixture) -> None:
    rng = np.random.default_rng(20260715)
    n = 2000
    a = rng.standard_normal((n, n))
    cov = (a @ a.T) / n  # symmetric PSD by construction
    deltas = rng.standard_normal(n)

    result = benchmark(parametric_var, deltas, cov)

    assert result.n_factors == n
    _assert_within(benchmark, SLA_PARAMETRIC_VAR_2000_FACTORS)


# --- Correlated-MC throughput: 10k paths x 12 steps x 6 factors < 5 s ---------


def test_correlated_mc_throughput_10k_paths(benchmark: BenchmarkFixture) -> None:
    n_factors, steps, path_count = 6, 12, 10_000
    sigma = np.full(n_factors, 0.30)
    corr = np.full((n_factors, n_factors), 0.30)
    np.fill_diagonal(corr, 1.0)
    cov = build_covariance(sigma, corr, 1.0 / 12.0)
    z0 = np.log(np.full(n_factors, 50.0))
    drift = np.zeros(n_factors)

    paths = benchmark(
        simulate_correlated_forwards,
        z0,
        drift,
        cov,
        steps=steps,
        path_count=path_count,
        seed=1,
        antithetic=True,
    )

    assert paths.shape == (path_count, steps + 1, n_factors)
    _assert_within(benchmark, CEILING_CORRELATED_MC)


# --- Dispatch-SDP timing budget: small LSM dispatch_value < 30 s --------------


def _const_c_max(capacity: float) -> MaxCapacityCurve:
    return lambda _temp: capacity


def _make_plant() -> PlantModel:
    return PlantModel(
        heat_rate=lambda _q, _temp: 2.0,
        c_min=10.0,
        c_max=_const_c_max(30.0),
        variable_om_cost=0.0,
        start_costs={
            StartState.HOT: StartCost(fixed=50.0, fuel=0.0, power=0.0),
            StartState.WARM: StartCost(fixed=100.0, fuel=0.0, power=0.0),
            StartState.COLD: StartCost(fixed=200.0, fuel=0.0, power=0.0),
        },
        ramp_rate=10.0,
        d_min=2,
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=1,
        warm_max_downtime=3,
    )


def _make_factor_model() -> DispatchFactorModel:
    dt, horizon = 1.0 / 50.0, 5
    sigmas = [0.35, 0.30, 0.45]
    corr = np.eye(3)
    corr[0, 2] = corr[2, 0] = 0.3
    corr[1, 2] = corr[2, 1] = 0.3
    covariance = build_covariance(sigmas, corr, dt)
    peaks = tuple(PeakKind.ON_PEAK if t % 2 == 0 else PeakKind.OFF_PEAK for t in range(horizon))
    return DispatchFactorModel(
        log_forward0=np.log(np.array([55.0, 42.0, 20.0])),
        drift=-0.5 * np.diag(covariance),
        covariance=covariance,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=peaks,
        temperatures=(15.0,) * horizon,
        power_on_index=0,
        power_off_index=1,
        gas_index=2,
    )


def test_dispatch_sdp_lsm_timing_budget(benchmark: BenchmarkFixture) -> None:
    plant = _make_plant()
    factor_model = _make_factor_model()

    result = benchmark.pedantic(
        dispatch_value,
        args=(plant, factor_model),
        kwargs={"method": "lsm", "seed": 7, "path_count": 2048},
        rounds=5,
        iterations=1,
        warmup_rounds=1,
    )

    assert result.value > 0.0
    _assert_within(benchmark, CEILING_DISPATCH_LSM)
