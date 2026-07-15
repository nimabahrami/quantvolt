"""Unit tests for implied vol, moneyness, realised vol, and the surface builder.

Covers Tasks 35-36: (a) Property 31 premium -> implied-vol round-trip through the
public orchestration layer; (b) domain and no-arbitrage validation raising
ValidationError naming the parameter; (c) Property 32 moneyness classification
including the inclusive ATM boundary; (d) rolling annualised realised vol;
(e) volatility-surface construction (term structure, interpolation of missing
months, nearest-ATM aggregation across strikes) and input immutability.
"""

from __future__ import annotations

import math

import numpy as np
import polars as pl
import pytest

from quantvolt.exceptions import InsufficientDataError, MissingTenorError, ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.models.vol_surface import Moneyness, VolatilitySurface
from quantvolt.numerics.black76 import black76_price
from quantvolt.pricing.implied_vol import (
    ImpliedVolResult,
    OptionQuote,
    build_volatility_surface,
    classify_moneyness,
    cumulative_historical_vol,
    implied_vol,
)
from quantvolt.testing import assert_input_unchanged

COMMODITY = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
JAN = DeliveryPeriod(year=2026, month=1)
FEB = DeliveryPeriod(year=2026, month=2)
MAR = DeliveryPeriod(year=2026, month=3)
APR = DeliveryPeriod(year=2026, month=4)
MAY = DeliveryPeriod(year=2026, month=5)


# --- implied_vol: Property 31 round-trip ----------------------------------------


@pytest.mark.parametrize(
    ("option_type", "forward", "strike", "ttm", "df", "sigma0"),
    [
        ("call", 100.0, 100.0, 1.00, 1.000, 0.20),
        ("call", 100.0, 90.0, 0.50, 0.980, 0.35),
        ("put", 50.0, 60.0, 2.00, 0.930, 0.45),
        ("put", 120.0, 100.0, 0.25, 0.995, 0.15),
        ("call", 80.0, 85.0, 3.00, 0.900, 0.60),
    ],
)
def test_round_trip_recovers_sigma_within_tol(
    option_type: str, forward: float, strike: float, ttm: float, df: float, sigma0: float
) -> None:
    premium = black76_price(option_type, forward, strike, sigma0, ttm, df)  # type: ignore[arg-type]
    result = implied_vol(option_type, premium, forward, strike, ttm, df)  # type: ignore[arg-type]
    assert result.implied_vol == pytest.approx(sigma0, abs=1e-4)
    assert result.converged is True
    assert result.moneyness == classify_moneyness(strike, forward)


def test_default_sigma_bracket_matches_hardcoded_behaviour() -> None:
    # Default-unchanged: explicit defaults reproduce the implicit-default result exactly.
    premium = black76_price("call", 100.0, 100.0, 0.30, 1.0, 0.99)
    baseline = implied_vol("call", premium, 100.0, 100.0, 1.0, 0.99)
    explicit = implied_vol(
        "call", premium, 100.0, 100.0, 1.0, 0.99, sigma_lower=1e-9, sigma_upper=10.0
    )
    assert explicit == baseline


def test_narrower_sigma_bracket_still_recovers_vol_within_it() -> None:
    premium = black76_price("call", 100.0, 100.0, 0.30, 1.0, 0.99)
    result = implied_vol(
        "call", premium, 100.0, 100.0, 1.0, 0.99, sigma_lower=0.01, sigma_upper=1.0
    )
    assert result.implied_vol == pytest.approx(0.30, abs=1e-4)


def test_sigma_bracket_too_narrow_to_contain_root_raises() -> None:
    premium = black76_price("call", 100.0, 100.0, 0.30, 1.0, 0.99)
    with pytest.raises(ValidationError, match="cannot be reproduced"):
        implied_vol("call", premium, 100.0, 100.0, 1.0, 0.99, sigma_lower=0.5, sigma_upper=0.6)


def test_sigma_lower_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="sigma_lower"):
        implied_vol("call", 7.0, 100.0, 100.0, 1.0, 0.99, sigma_lower=0.0)


def test_sigma_upper_must_exceed_sigma_lower() -> None:
    with pytest.raises(ValidationError, match="sigma_upper"):
        implied_vol("call", 7.0, 100.0, 100.0, 1.0, 0.99, sigma_lower=1.0, sigma_upper=1.0)


def test_implied_vol_tolerance_pct_default_matches_classify_moneyness_default() -> None:
    premium = black76_price("call", 100.0, 105.0, 0.30, 1.0, 0.99)
    baseline = implied_vol("call", premium, 100.0, 105.0, 1.0, 0.99)
    explicit = implied_vol("call", premium, 100.0, 105.0, 1.0, 0.99, tolerance_pct=2.0)
    assert explicit.moneyness == baseline.moneyness == classify_moneyness(105.0, 100.0)


def test_implied_vol_tolerance_pct_widens_reported_moneyness_to_atm() -> None:
    # 105 vs forward 100 is OTM at the default 2% band, ATM once the band widens to 10%.
    premium = black76_price("call", 100.0, 105.0, 0.30, 1.0, 0.99)
    default_result = implied_vol("call", premium, 100.0, 105.0, 1.0, 0.99)
    widened_result = implied_vol("call", premium, 100.0, 105.0, 1.0, 0.99, tolerance_pct=10.0)
    assert default_result.moneyness == Moneyness.OTM
    assert widened_result.moneyness == Moneyness.ATM


def test_result_reports_objective_evaluation_count() -> None:
    premium = black76_price("call", 100.0, 100.0, 0.30, 1.0, 0.99)
    result = implied_vol("call", premium, 100.0, 100.0, 1.0, 0.99)
    assert isinstance(result, ImpliedVolResult)
    # Brent evaluates at least the two bracket endpoints before iterating.
    assert result.iteration_count >= 2


def test_iteration_count_matches_scipy_brentq_call_count_exactly() -> None:
    # Fix 8 regression: rootfind.brent_root previously pre-evaluated f(a) and f(b)
    # before calling scipy's brentq (which evaluates them again itself), inflating
    # iteration_count by exactly 2 over brentq's own evaluation count (verified: 9 vs
    # 7 for this exact case). The docstring's claim that iteration_count "includes the
    # two bracket-endpoint evaluations" is only true once it matches brentq's own
    # count one-for-one, which this test confirms by counting independently.
    from scipy.optimize import brentq  # type: ignore[import-untyped]

    forward, strike, ttm, df = 100.0, 100.0, 1.0, 0.99
    premium = black76_price("call", forward, strike, 0.30, ttm, df)

    result = implied_vol("call", premium, forward, strike, ttm, df)

    scipy_calls = 0

    def counted_objective(sigma: float) -> float:
        nonlocal scipy_calls
        scipy_calls += 1
        return black76_price("call", forward, strike, sigma, ttm, df) - premium

    brentq(counted_objective, 1e-9, 10.0, xtol=1e-4, maxiter=100)

    assert result.iteration_count == scipy_calls


def test_result_is_frozen() -> None:
    premium = black76_price("call", 100.0, 100.0, 0.30, 1.0, 0.99)
    result = implied_vol("call", premium, 100.0, 100.0, 1.0, 0.99)
    with pytest.raises(AttributeError):
        result.implied_vol = 0.0  # type: ignore[misc]


# --- implied_vol: validation ------------------------------------------------------


def test_call_premium_above_upper_bound_raises_naming_market_premium() -> None:
    # Upper no-arbitrage bound for a call is DF*F = 100.
    with pytest.raises(ValidationError, match=r"market_premium.*no-arbitrage"):
        implied_vol("call", 150.0, 100.0, 100.0, 1.0, 1.0)


def test_call_premium_below_intrinsic_raises() -> None:
    # Discounted intrinsic value is 1.0*(110-100) = 10; a premium of 5 violates it.
    with pytest.raises(ValidationError, match=r"market_premium.*no-arbitrage"):
        implied_vol("call", 5.0, 110.0, 100.0, 1.0, 1.0)


def test_put_premium_above_upper_bound_raises() -> None:
    # Upper no-arbitrage bound for a put is DF*K = 0.95*90 = 85.5.
    with pytest.raises(ValidationError, match=r"market_premium.*no-arbitrage"):
        implied_vol("put", 90.0, 100.0, 90.0, 1.0, 0.95)


def test_unknown_option_type_rejected() -> None:
    with pytest.raises(ValidationError, match="option_type"):
        implied_vol("straddle", 5.0, 100.0, 100.0, 1.0, 0.99)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("market_premium", 0.0, "market_premium"),
        ("market_premium", -1.0, "market_premium"),
        ("forward", 0.0, "forward"),
        ("strike", -1.0, "strike"),
        ("time_to_expiry", 0.0, "time_to_expiry"),
        ("discount_factor", 0.0, "discount_factor"),
        ("discount_factor", 1.1, "discount_factor"),
        ("tol", 0.0, "tol"),
        ("max_iter", 0, "max_iter"),
    ],
)
def test_domain_validation_names_offending_parameter(field: str, value: float, match: str) -> None:
    kwargs: dict[str, object] = {
        "option_type": "call",
        "market_premium": 7.0,
        "forward": 100.0,
        "strike": 100.0,
        "time_to_expiry": 1.0,
        "discount_factor": 0.99,
    }
    kwargs[field] = value
    with pytest.raises(ValidationError, match=match):
        implied_vol(**kwargs)  # type: ignore[arg-type]


# --- classify_moneyness: Property 32 ---------------------------------------------


def test_atm_when_strike_equals_forward() -> None:
    assert classify_moneyness(100.0, 100.0) is Moneyness.ATM


def test_atm_within_default_two_percent_band() -> None:
    assert classify_moneyness(101.9, 100.0) is Moneyness.ATM
    assert classify_moneyness(98.1, 100.0) is Moneyness.ATM


def test_atm_boundary_at_exactly_two_percent_is_inclusive() -> None:
    # Property 32: |K - F| / F * 100 == tolerance_pct classifies as ATM.
    assert classify_moneyness(102.0, 100.0) is Moneyness.ATM
    assert classify_moneyness(98.0, 100.0) is Moneyness.ATM


def test_otm_when_strike_above_forward_band() -> None:
    # Call convention: strike above the forward has no intrinsic value.
    assert classify_moneyness(105.0, 100.0) is Moneyness.OTM


def test_itm_when_strike_below_forward_band() -> None:
    assert classify_moneyness(95.0, 100.0) is Moneyness.ITM


def test_custom_tolerance_widens_the_atm_band() -> None:
    assert classify_moneyness(105.0, 100.0, tolerance_pct=10.0) is Moneyness.ATM
    assert classify_moneyness(111.0, 100.0, tolerance_pct=10.0) is Moneyness.OTM


def test_zero_tolerance_only_exact_strike_is_atm() -> None:
    assert classify_moneyness(100.0, 100.0, tolerance_pct=0.0) is Moneyness.ATM
    assert classify_moneyness(100.5, 100.0, tolerance_pct=0.0) is Moneyness.OTM
    assert classify_moneyness(99.5, 100.0, tolerance_pct=0.0) is Moneyness.ITM


@pytest.mark.parametrize(
    ("strike", "forward", "tolerance_pct", "match"),
    [
        (0.0, 100.0, 2.0, "strike"),
        (100.0, -1.0, 2.0, "forward"),
        (100.0, 100.0, -0.5, "tolerance_pct"),
    ],
)
def test_classify_moneyness_validation(
    strike: float, forward: float, tolerance_pct: float, match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        classify_moneyness(strike, forward, tolerance_pct)


# --- cumulative_historical_vol ----------------------------------------------------


def test_constant_series_has_zero_realised_vol() -> None:
    series = pl.Series("price", [100.0] * 300)
    result = cumulative_historical_vol(series)
    assert len(result) == 300
    realised = result.drop_nulls()
    assert len(realised) == 300 - 252
    assert float(realised.abs().max()) <= 1e-12  # type: ignore[arg-type]


def test_warm_up_is_null_then_values_start() -> None:
    series = pl.Series("price", [100.0 + i for i in range(10)])
    result = cumulative_historical_vol(series, window=3)
    # One null from the return differencing + (window - 1) from the rolling std.
    assert result.null_count() == 3
    assert result[3] is not None


def test_gbm_sample_recovers_annualised_sigma_loosely() -> None:
    rng = np.random.default_rng(7)
    sigma_annual = 0.4
    daily_returns = rng.normal(0.0, sigma_annual / math.sqrt(252.0), size=1500)
    prices = 100.0 * np.exp(np.cumsum(daily_returns))
    result = cumulative_historical_vol(pl.Series("price", prices), window=252)
    assert float(result.drop_nulls().mean()) == pytest.approx(  # type: ignore[arg-type]
        sigma_annual, rel=0.1
    )


def test_window_below_two_rejected() -> None:
    with pytest.raises(ValidationError, match="window"):
        cumulative_historical_vol(pl.Series("price", [100.0, 101.0, 102.0]), window=1)


def test_series_not_longer_than_window_rejected() -> None:
    series = pl.Series("price", [100.0] * 252)
    with pytest.raises(InsufficientDataError, match="price_series"):
        cumulative_historical_vol(series, window=252)


def test_non_positive_prices_rejected() -> None:
    series = pl.Series("price", [100.0, -1.0, 100.0, 100.0])
    with pytest.raises(ValidationError, match="price_series"):
        cumulative_historical_vol(series, window=2)


def test_periods_per_year_default_matches_hardcoded_252() -> None:
    series = pl.Series("price", [100.0 + 0.1 * i for i in range(10)])
    baseline = cumulative_historical_vol(series, window=3)
    explicit = cumulative_historical_vol(series, window=3, periods_per_year=252)
    assert (baseline == explicit).fill_null(True).all()


def test_periods_per_year_rescales_annualisation() -> None:
    series = pl.Series("price", [100.0 + 0.1 * i for i in range(10)])
    default = cumulative_historical_vol(series, window=3).drop_nulls()
    weekly = cumulative_historical_vol(series, window=3, periods_per_year=52).drop_nulls()
    ratio = (weekly / default).to_list()
    for value in ratio:
        assert value == pytest.approx(math.sqrt(52.0 / 252.0), rel=1e-9)


def test_periods_per_year_below_one_rejected() -> None:
    series = pl.Series("price", [100.0] * 300)
    with pytest.raises(ValidationError, match="periods_per_year"):
        cumulative_historical_vol(series, periods_per_year=0)


def test_cumulative_historical_vol_does_not_mutate_input() -> None:
    series = pl.Series("price", [100.0, 101.0, 99.0, 102.0, 103.0, 101.0, 104.0, 105.0])
    result = assert_input_unchanged(cumulative_historical_vol, series, window=3)
    assert len(result) == len(series)


# --- build_volatility_surface ------------------------------------------------------


def make_atm_quote(period: DeliveryPeriod, sigma: float, time_to_expiry: float) -> OptionQuote:
    forward = 50.0
    discount_factor = 0.99
    premium = black76_price("call", forward, forward, sigma, time_to_expiry, discount_factor)
    return OptionQuote(
        period=period,
        strike=forward,
        premium=premium,
        forward=forward,
        option_type="call",
        time_to_expiry=time_to_expiry,
        discount_factor=discount_factor,
    )


def make_three_month_quotes() -> list[OptionQuote]:
    # Quoted Jan/Mar/May 2026; Feb and Apr are missing and must be interpolated.
    return [
        make_atm_quote(JAN, 0.30, 0.50),
        make_atm_quote(MAR, 0.40, 0.67),
        make_atm_quote(MAY, 0.50, 0.83),
    ]


def test_surface_matches_inversion_at_quoted_periods() -> None:
    surface = build_volatility_surface(make_three_month_quotes(), commodity=COMMODITY)
    assert isinstance(surface, VolatilitySurface)
    assert surface.commodity == COMMODITY
    assert surface.sigma_at(JAN) == pytest.approx(0.30, abs=5e-4)
    assert surface.sigma_at(MAR) == pytest.approx(0.40, abs=5e-4)
    assert surface.sigma_at(MAY) == pytest.approx(0.50, abs=5e-4)


def test_missing_months_are_linearly_interpolated() -> None:
    surface = build_volatility_surface(make_three_month_quotes(), commodity=COMMODITY)
    # Feb sits midway between the Jan and Mar knots on the month axis.
    assert surface.sigma_at(FEB) == pytest.approx(0.35, abs=1e-3)
    assert surface.sigma_at(APR) == pytest.approx(0.45, abs=1e-3)
    assert surface.sigma_at(JAN) < surface.sigma_at(FEB) < surface.sigma_at(MAR)


def test_cubic_spline_interpolation_is_dispatched() -> None:
    surface = build_volatility_surface(
        make_three_month_quotes(), interpolation="cubic_spline", commodity=COMMODITY
    )
    # The three knots are collinear on the month axis, so the natural spline
    # reproduces the straight line through them.
    assert surface.sigma_at(FEB) == pytest.approx(0.35, abs=2e-3)
    assert surface.sigma_at(JAN) == pytest.approx(0.30, abs=5e-4)


def test_surface_covers_only_quoted_range() -> None:
    surface = build_volatility_surface(make_three_month_quotes(), commodity=COMMODITY)
    assert len(surface.tenors) == 5  # Jan..May inclusive, nothing beyond
    with pytest.raises(MissingTenorError):
        surface.sigma_at(DeliveryPeriod(year=2025, month=12))
    with pytest.raises(MissingTenorError):
        surface.sigma_at(DeliveryPeriod(year=2026, month=6))


def test_multiple_strikes_per_period_pick_nearest_atm_vol() -> None:
    forward = 50.0
    discount_factor = 0.99
    time_to_expiry = 0.5
    smile = [(45.0, 0.35), (50.0, 0.30), (60.0, 0.40)]  # strike closest to F=50 wins
    quotes = [
        OptionQuote(
            period=JAN,
            strike=strike,
            premium=black76_price("call", forward, strike, sigma, time_to_expiry, discount_factor),
            forward=forward,
            option_type="call",
            time_to_expiry=time_to_expiry,
            discount_factor=discount_factor,
        )
        for strike, sigma in smile
    ]
    surface = build_volatility_surface(quotes, commodity=COMMODITY)
    assert len(surface.tenors) == 1
    assert surface.sigma_at(JAN) == pytest.approx(0.30, abs=5e-4)


def test_empty_quotes_rejected() -> None:
    with pytest.raises(ValidationError, match="option_quotes"):
        build_volatility_surface([], commodity=COMMODITY)


def test_unknown_interpolation_rejected() -> None:
    with pytest.raises(ValidationError, match="interpolation"):
        build_volatility_surface(
            make_three_month_quotes(),
            interpolation="quadratic",  # type: ignore[arg-type]
            commodity=COMMODITY,
        )


def test_extrapolate_true_rejected() -> None:
    with pytest.raises(ValidationError, match="extrapolate"):
        build_volatility_surface(make_three_month_quotes(), extrapolate=True, commodity=COMMODITY)


def test_invalid_quote_fails_loudly() -> None:
    # A premium above DF*F cannot be inverted; the surface build must fail, not drop it.
    bad = OptionQuote(
        period=FEB,
        strike=50.0,
        premium=60.0,
        forward=50.0,
        option_type="call",
        time_to_expiry=0.5,
        discount_factor=0.99,
    )
    with pytest.raises(ValidationError, match=r"market_premium.*no-arbitrage"):
        build_volatility_surface([*make_three_month_quotes(), bad], commodity=COMMODITY)


def test_build_volatility_surface_does_not_mutate_inputs() -> None:
    quotes = make_three_month_quotes()
    surface = assert_input_unchanged(build_volatility_surface, quotes, commodity=COMMODITY)
    assert surface.sigma_at(JAN) == pytest.approx(0.30, abs=5e-4)
