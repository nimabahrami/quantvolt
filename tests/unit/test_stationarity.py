"""Unit tests for stationarity analysis and Samuelson-effect detection (Task 22)."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import polars as pl
import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.stats.stationarity import StationarityResult
from quantvolt.stats.stationarity import test_stationarity as run_stationarity


def _observation_dates(count: int, start: date = date(2024, 1, 1)) -> list[date]:
    """Consecutive daily dates, oldest first (parallel to a price series)."""
    return [start + timedelta(days=offset) for offset in range(count)]


def test_random_walk_is_not_stationary() -> None:
    # A random walk (cumsum of i.i.d. normals) has a unit root: ADF should fail to
    # reject it, so the combined verdict is not stationary.
    rng = np.random.default_rng(20240714)
    n = 300
    walk = np.cumsum(rng.standard_normal(n))
    series = pl.Series("price", walk)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    result = run_stationarity(series, expiry, _observation_dates(n))

    assert isinstance(result, StationarityResult)
    assert result.adf_p_value > 0.05  # unit root not rejected
    assert result.is_stationary is False


def test_white_noise_is_stationary() -> None:
    # I.i.d. Gaussian noise is stationary: ADF rejects the unit root and KPSS fails
    # to reject stationarity, so both tests agree.
    rng = np.random.default_rng(11)
    n = 300
    noise = rng.standard_normal(n)
    series = pl.Series("price", noise)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    result = run_stationarity(series, expiry, _observation_dates(n))

    assert result.adf_p_value < 0.05  # unit root rejected
    assert result.kpss_p_value > 0.05  # stationarity not rejected
    assert result.is_stationary is True


def test_samuelson_detected_when_near_expiry_more_volatile() -> None:
    # Build a series whose later (near-expiry) half has far larger increments than
    # its earlier half; the Samuelson effect should be detected.
    rng = np.random.default_rng(7)
    n = 300
    half = n // 2
    increments = np.concatenate(
        [rng.normal(0.0, 0.2, size=half), rng.normal(0.0, 3.0, size=n - half)]
    )
    prices = 100.0 + np.cumsum(increments)
    series = pl.Series("price", prices)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    result = run_stationarity(series, expiry, _observation_dates(n))

    assert result.samuelson_effect_detected is True


def test_samuelson_not_detected_when_near_expiry_calmer() -> None:
    # Reverse the volatility regime: the near-expiry half is the calm one, so the
    # Samuelson effect should not be flagged.
    rng = np.random.default_rng(7)
    n = 300
    half = n // 2
    increments = np.concatenate(
        [rng.normal(0.0, 3.0, size=half), rng.normal(0.0, 0.2, size=n - half)]
    )
    prices = 100.0 + np.cumsum(increments)
    series = pl.Series("price", prices)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    result = run_stationarity(series, expiry, _observation_dates(n))

    assert result.samuelson_effect_detected is False


def test_mismatched_dates_length_raises() -> None:
    rng = np.random.default_rng(3)
    n = 300
    series = pl.Series("price", rng.standard_normal(n))
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    with pytest.raises(ValidationError, match="observation_dates length"):
        run_stationarity(series, expiry, _observation_dates(n - 1))


def test_too_short_series_raises() -> None:
    rng = np.random.default_rng(5)
    n = 10  # below the ADF/KPSS minimum
    series = pl.Series("price", rng.standard_normal(n))
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    with pytest.raises(InsufficientDataError, match="at least"):
        run_stationarity(series, expiry, _observation_dates(n))


def test_empty_series_raises() -> None:
    series = pl.Series("price", [], dtype=pl.Float64)
    expiry = date(2024, 1, 5)

    with pytest.raises(ValidationError, match="non-empty"):
        run_stationarity(series, expiry, [])


def test_input_series_not_mutated() -> None:
    rng = np.random.default_rng(99)
    n = 300
    values = rng.standard_normal(n)
    series = pl.Series("price", values)
    before = series.to_list()
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    run_stationarity(series, expiry, _observation_dates(n))

    assert series.to_list() == before


# --- caller-configurable parameters (task: expose hardcoded values) -----------


def test_default_keyword_params_match_previous_hardcoded_behaviour() -> None:
    rng = np.random.default_rng(11)
    n = 300
    noise = rng.standard_normal(n)
    series = pl.Series("price", noise)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)
    dates = _observation_dates(n)

    baseline = run_stationarity(series, expiry, dates)
    defaulted = run_stationarity(
        series,
        expiry,
        dates,
        min_observations=30,
        adf_significance=0.05,
        kpss_significance=0.05,
        adf_regression="c",
        adf_maxlag=None,
        adf_autolag="AIC",
        kpss_regression="c",
        kpss_nlags="auto",
    )
    assert defaulted == baseline


def test_overriding_min_observations_changes_the_insufficient_data_threshold() -> None:
    rng = np.random.default_rng(5)
    n = 40  # below the raised min_observations, above the module default of 30
    series = pl.Series("price", rng.standard_normal(n))
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)

    # Passes at the (lower) default threshold...
    run_stationarity(series, expiry, _observation_dates(n))
    # ...but raises once min_observations is raised above the series length.
    with pytest.raises(InsufficientDataError, match="at least 50"):
        run_stationarity(series, expiry, _observation_dates(n), min_observations=50)


def test_overriding_significance_levels_changes_the_stationarity_verdict() -> None:
    rng = np.random.default_rng(11)
    n = 300
    noise = rng.standard_normal(n)
    series = pl.Series("price", noise)
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)
    dates = _observation_dates(n)

    result = run_stationarity(series, expiry, dates)
    assert result.is_stationary is True  # baseline: white noise is stationary (default levels)
    assert result.kpss_p_value < 0.5  # precondition for the flip below

    # Raising kpss_significance above the observed KPSS p-value flips the "fails to
    # reject stationarity" leg (kpss_p_value > kpss_significance) to False, flipping
    # the combined verdict to non-stationary even though the statistics are unchanged.
    strict = run_stationarity(series, expiry, dates, kpss_significance=0.5)
    assert strict.is_stationary is False
    assert strict.adf_statistic == result.adf_statistic  # only the verdict threshold moved
    assert strict.kpss_statistic == result.kpss_statistic


def test_bad_significance_levels_raise() -> None:
    rng = np.random.default_rng(1)
    n = 40
    series = pl.Series("price", rng.standard_normal(n))
    expiry = date(2024, 1, 1) + timedelta(days=n + 5)
    dates = _observation_dates(n)

    with pytest.raises(ValidationError, match="adf_significance"):
        run_stationarity(series, expiry, dates, adf_significance=1.5)
    with pytest.raises(ValidationError, match="kpss_significance"):
        run_stationarity(series, expiry, dates, kpss_significance=0.0)
