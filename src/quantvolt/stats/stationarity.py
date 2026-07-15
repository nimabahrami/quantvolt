"""Stationarity analysis with Samuelson-effect detection (Task 22)."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray
from statsmodels.tsa.stattools import adfuller, kpss  # type: ignore[import-untyped]

from .._validation import require_non_empty, require_positive
from ..exceptions import InsufficientDataError, ValidationError

if TYPE_CHECKING:
    import polars as pl

# ADF/KPSS need enough observations to fit their lag structure; below this the
# statsmodels estimators become unstable, so we fail loudly at the boundary instead.
_MIN_OBSERVATIONS = 30

# is_stationary decision thresholds (design "Stationarity Analysis").
_ADF_REJECT_LEVEL = 0.05  # ADF p below this rejects the unit-root null.
_KPSS_ACCEPT_LEVEL = 0.05  # KPSS p above this fails to reject the stationarity null.


@dataclass(frozen=True, slots=True)
class StationarityResult:
    adf_statistic: float
    adf_p_value: float
    kpss_statistic: float
    kpss_p_value: float
    is_stationary: bool
    samuelson_effect_detected: bool


def test_stationarity(
    price_series: pl.Series,
    contract_expiry: date,
    observation_dates: list[date],
    *,
    min_observations: int = _MIN_OBSERVATIONS,
    adf_significance: float = _ADF_REJECT_LEVEL,
    kpss_significance: float = _KPSS_ACCEPT_LEVEL,
    adf_regression: str = "c",
    adf_maxlag: int | None = None,
    adf_autolag: str | None = "AIC",
    kpss_regression: str = "c",
    kpss_nlags: str | int = "auto",
) -> StationarityResult:
    """Test a price history for a unit root (ADF) and for stationarity (KPSS).

    The series is judged stationary only when the ADF test rejects the unit-root
    null (``adf_p_value < adf_significance``) *and* the KPSS test fails to reject
    the stationarity null (``kpss_p_value > kpss_significance``) — the two tests
    must agree.

    The Samuelson effect — return volatility rising as a futures contract nears
    expiry — is detected by ordering the observations from furthest-from-expiry to
    nearest (using ``observation_dates`` relative to ``contract_expiry``) and
    comparing the return volatility of the later (near-expiry) half against the
    earlier half; ``True`` when the near-expiry half is more volatile.

    Args:
        price_series: Observed prices, one per entry in ``observation_dates``.
        contract_expiry: Expiry date of the contract being sampled; fixes which
            observations sit closest to expiry.
        observation_dates: Sampling date of each price, parallel to ``price_series``.
        min_observations: Minimum number of prices required for ADF/KPSS testing;
            defaults to ``30`` (below this the statsmodels estimators become
            unstable).
        adf_significance: Significance level below which the ADF p-value rejects
            the unit-root null; defaults to ``0.05``. Must be in ``(0, 1)``.
        kpss_significance: Significance level above which the KPSS p-value fails
            to reject the stationarity null; defaults to ``0.05``. Must be in
            ``(0, 1)``.
        adf_regression: ``statsmodels.tsa.stattools.adfuller`` regression
            (trend) specification; defaults to ``"c"`` (constant only).
        adf_maxlag: ``adfuller`` maximum lag; defaults to ``None`` (statsmodels
            picks a default based on sample size).
        adf_autolag: ``adfuller`` lag-selection criterion; defaults to ``"AIC"``.
        kpss_regression: ``statsmodels.tsa.stattools.kpss`` regression (trend)
            specification; defaults to ``"c"`` (level stationarity).
        kpss_nlags: ``kpss`` lag-truncation parameter; defaults to ``"auto"``.

    Returns:
        A :class:`StationarityResult` with the ADF/KPSS statistics and p-values,
        the combined stationarity verdict, and the Samuelson-effect flag.

    Raises:
        ValidationError: If ``price_series`` is empty, its length does not match
            ``observation_dates``, ``min_observations`` is not strictly positive,
            or ``adf_significance`` / ``kpss_significance`` is not in ``(0, 1)``.
        InsufficientDataError: If fewer than ``min_observations`` prices are given.
    """
    import polars as pl  # runtime import: polars is only needed inside this call.

    require_non_empty("price_series", price_series)
    if len(observation_dates) != len(price_series):
        raise ValidationError(
            "observation_dates length must match price_series length, "
            f"got {len(observation_dates)} and {len(price_series)}"
        )
    require_positive("min_observations", min_observations)
    if not 0.0 < adf_significance < 1.0:
        raise ValidationError(f"adf_significance must be in (0, 1), got {adf_significance!r}")
    if not 0.0 < kpss_significance < 1.0:
        raise ValidationError(f"kpss_significance must be in (0, 1), got {kpss_significance!r}")
    if len(price_series) < min_observations:
        raise InsufficientDataError(
            f"price_series must have at least {min_observations} observations for "
            f"ADF/KPSS testing, got {len(price_series)}"
        )

    # cast() returns a new Series, so the caller's input is never mutated.
    prices: NDArray[np.float64] = price_series.cast(pl.Float64).to_numpy()

    with warnings.catch_warnings():
        # KPSS emits InterpolationWarning when the statistic is off its p-value
        # table; the capped p-value is the documented, intended behaviour.
        warnings.simplefilter("ignore")
        adf_result = adfuller(
            prices, maxlag=adf_maxlag, regression=adf_regression, autolag=adf_autolag
        )
        kpss_result = kpss(prices, regression=kpss_regression, nlags=kpss_nlags)

    adf_statistic = float(adf_result[0])
    adf_p_value = float(adf_result[1])
    kpss_statistic = float(kpss_result[0])
    kpss_p_value = float(kpss_result[1])

    is_stationary = adf_p_value < adf_significance and kpss_p_value > kpss_significance

    return StationarityResult(
        adf_statistic=adf_statistic,
        adf_p_value=adf_p_value,
        kpss_statistic=kpss_statistic,
        kpss_p_value=kpss_p_value,
        is_stationary=is_stationary,
        samuelson_effect_detected=_detect_samuelson(prices, observation_dates, contract_expiry),
    )


def _detect_samuelson(
    prices: NDArray[np.float64],
    observation_dates: list[date],
    contract_expiry: date,
) -> bool:
    """Return ``True`` when near-expiry return volatility exceeds far-from-expiry.

    Observations are ordered by time-to-expiry (furthest first) so the arrangement
    is robust to unordered ``observation_dates``. Period-over-period price changes
    stand in for returns — a proxy that stays well-defined for the non-positive
    prices that occur in power markets. The changes are split into an earlier
    (far-from-expiry) and later (near-expiry) half whose standard deviations are
    compared.
    """
    days_to_expiry = np.array(
        [(contract_expiry - observed).days for observed in observation_dates],
        dtype=np.float64,
    )
    far_to_near = np.argsort(-days_to_expiry, kind="stable")
    changes = np.diff(prices[far_to_near])

    midpoint = changes.size // 2
    earlier_vol = float(np.std(changes[:midpoint]))
    later_vol = float(np.std(changes[midpoint:]))
    return later_vol > earlier_vol
