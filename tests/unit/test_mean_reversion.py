"""Unit tests for Ornstein-Uhlenbeck mean-reversion fitting (Task 24, Property 37)."""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.stats.mean_reversion import MeanReversionParams, fit_ou

# Known true parameters for the simulated path (documented in the design "Mean Reversion").
TRUE_KAPPA = 2.0
TRUE_MU = 50.0
TRUE_SIGMA = 5.0
DT = 1 / 252
N = 20_000
SEED = 7


def _simulate_ou(kappa: float, mu: float, sigma: float, dt: float, n: int, seed: int) -> pl.Series:
    """Simulate an OU path via its exact discrete-time (AR(1)) transition.

    ``X_{t+1} = mu + (X_t - mu)*exp(-kappa*dt) + noise``,
    ``noise ~ N(0, sigma**2 * (1 - exp(-2*kappa*dt)) / (2*kappa))``.
    """
    rng = np.random.default_rng(seed)
    b = math.exp(-kappa * dt)
    noise_std = sigma * math.sqrt((1.0 - b * b) / (2.0 * kappa))
    shocks = rng.standard_normal(n - 1)
    x = np.empty(n, dtype=np.float64)
    x[0] = mu  # start at the long-run mean
    for i in range(1, n):
        x[i] = mu + (x[i - 1] - mu) * b + noise_std * shocks[i - 1]
    return pl.Series("price", x)


def test_fit_ou_recovers_known_parameters() -> None:
    series = _simulate_ou(TRUE_KAPPA, TRUE_MU, TRUE_SIGMA, DT, N, SEED)

    params = fit_ou(series, dt=DT)

    # Loose relative tolerances: kappa is the most estimation-sensitive (log of a slope
    # near 1), mu and sigma are recovered tightly.
    assert params.reversion_speed == pytest.approx(TRUE_KAPPA, rel=0.30)
    assert params.long_run_mean == pytest.approx(TRUE_MU, rel=0.05)
    assert params.volatility == pytest.approx(TRUE_SIGMA, rel=0.20)


def test_fit_ou_returns_positive_and_consistent_params() -> None:
    series = _simulate_ou(TRUE_KAPPA, TRUE_MU, TRUE_SIGMA, DT, N, SEED)

    params = fit_ou(series, dt=DT)

    assert isinstance(params, MeanReversionParams)
    assert params.reversion_speed > 0.0
    assert params.volatility > 0.0
    assert params.half_life > 0.0
    # half_life is exactly ln(2)/kappa for the returned reversion speed.
    assert params.half_life == pytest.approx(math.log(2.0) / params.reversion_speed, rel=1e-12)


def test_default_dt_matches_explicit_daily_dt() -> None:
    series = _simulate_ou(TRUE_KAPPA, TRUE_MU, TRUE_SIGMA, DT, N, SEED)

    # The documented default dt is one trading day (1/252).
    assert fit_ou(series) == fit_ou(series, dt=1 / 252)


def test_fit_ou_does_not_mutate_input() -> None:
    # The shipped assert_input_unchanged helper compares with `!=`, which is element-wise
    # (ambiguous truth value) for a polars Series, so snapshot the values directly instead.
    series = _simulate_ou(TRUE_KAPPA, TRUE_MU, TRUE_SIGMA, DT, N, SEED)
    before = series.to_list()

    result = fit_ou(series, dt=DT)

    assert isinstance(result, MeanReversionParams)
    assert series.to_list() == before


def test_too_short_series_raises() -> None:
    with pytest.raises(InsufficientDataError):
        fit_ou(pl.Series("price", [50.0, 51.0]), dt=DT)


def test_empty_series_raises() -> None:
    with pytest.raises(InsufficientDataError):
        fit_ou(pl.Series("price", [], dtype=pl.Float64), dt=DT)


def test_constant_series_raises() -> None:
    with pytest.raises(InsufficientDataError):
        fit_ou(pl.Series("price", [42.0] * 100), dt=DT)


def test_non_mean_reverting_series_raises() -> None:
    # A pure linear trend has regression slope b == 1 (not in (0, 1)): kappa is
    # undefined, so the fit must reject it as non-mean-reverting.
    trend = pl.Series("price", np.arange(100, dtype=np.float64))
    with pytest.raises(InsufficientDataError):
        fit_ou(trend, dt=DT)


@pytest.mark.parametrize("bad_dt", [0.0, -1.0, -0.5])
def test_non_positive_dt_raises(bad_dt: float) -> None:
    series = _simulate_ou(TRUE_KAPPA, TRUE_MU, TRUE_SIGMA, DT, 100, SEED)
    with pytest.raises(ValidationError):
        fit_ou(series, dt=bad_dt)
