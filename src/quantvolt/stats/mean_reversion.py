"""Ornstein-Uhlenbeck mean-reversion estimation (Task 24).

Fits ``dX = kappa*(mu - X) dt + sigma dW`` by ordinary least squares on the exact
discrete-time (AR(1)) representation of the process. Used for power prices (strong
mean reversion), gas-storage valuation, and spread modelling (design "Mean Reversion").
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import polars as pl

from .._validation import require_positive
from ..exceptions import InsufficientDataError

# Minimum observations: two consecutive pairs are the fewest that give a regression
# with a residual degree of freedom, so the OU fit needs at least three prices.
_MIN_OBSERVATIONS = 3


@dataclass(frozen=True, slots=True)
class MeanReversionParams:
    long_run_mean: float
    reversion_speed: float
    volatility: float
    half_life: float


def fit_ou(price_series: pl.Series, dt: float = 1 / 252) -> MeanReversionParams:
    """Fit an Ornstein-Uhlenbeck process ``dX = kappa*(mu - X) dt + sigma dW`` by OLS.

    The OU SDE has the exact discrete-time solution of an AR(1) process, so regressing
    each observation on its predecessor, ``X_{t+1} = a + b*X_t + eps``, recovers the
    continuous-time parameters:

    * ``b`` (slope) and ``a`` (intercept) come from OLS of ``X_{t+1}`` on ``X_t``.
    * ``reversion_speed`` ``kappa = -ln(b) / dt`` — valid only for ``b`` in ``(0, 1)``;
      outside that range the series does not mean-revert (``b <= 0`` has no real log,
      ``b >= 1`` implies zero/negative reversion), so ``kappa`` cannot be estimated.
    * ``long_run_mean`` ``mu = a / (1 - b)``.
    * ``volatility`` ``sigma = std(residuals) * sqrt(2*kappa / (1 - b**2))``, the standard
      discrete-time OU estimator that maps the fitted residual dispersion back to the
      instantaneous diffusion. ``std(residuals)`` is the OLS residual standard error
      (sum of squares divided by ``n - 2``, the two fitted parameters).
    * ``half_life`` ``= ln(2) / kappa`` — time for a deviation to decay by half.

    Args:
        price_series: Observed price/level path ``X_t``, in observation order.
        dt: Time step between consecutive observations (years); defaults to one
            trading day, ``1/252``.

    Returns:
        The fitted :class:`MeanReversionParams`.

    Raises:
        ValidationError: If ``dt <= 0``.
        InsufficientDataError: If fewer than three observations are supplied, if the
            series is constant (no variation to regress on), or if the fitted slope
            lies outside ``(0, 1)`` so the series is not mean-reverting.
    """
    require_positive("dt", dt)

    n = len(price_series)
    if n < _MIN_OBSERVATIONS:
        raise InsufficientDataError(
            f"price_series must have at least {_MIN_OBSERVATIONS} observations to fit an "
            f"Ornstein-Uhlenbeck process, got {n}"
        )

    # Copy into a float64 array; polars Series is not mutated (no input mutation).
    values = np.asarray(price_series.to_numpy(), dtype=np.float64)
    x_prev = values[:-1]
    x_next = values[1:]

    mean_prev = float(x_prev.mean())
    mean_next = float(x_next.mean())
    centered_prev = x_prev - mean_prev
    var_prev = float(centered_prev @ centered_prev)
    if var_prev == 0.0:
        raise InsufficientDataError(
            "price_series is constant; reversion_speed (kappa) cannot be estimated from "
            "a series with no variation"
        )

    slope = float((centered_prev @ (x_next - mean_next)) / var_prev)
    intercept = mean_next - slope * mean_prev

    if not 0.0 < slope < 1.0:
        raise InsufficientDataError(
            f"regression slope b={slope!r} is not in (0, 1); the series is not "
            "mean-reverting, so reversion_speed (kappa) cannot be estimated"
        )

    reversion_speed = -math.log(slope) / dt
    long_run_mean = intercept / (1.0 - slope)

    residuals = x_next - (intercept + slope * x_prev)
    # Residual standard error: divide by (n_pairs - 2) for the two fitted parameters.
    n_pairs = residuals.size
    ddof = 2 if n_pairs > 2 else 0
    residual_std = float(np.std(residuals, ddof=ddof))
    volatility = residual_std * math.sqrt(2.0 * reversion_speed / (1.0 - slope * slope))

    half_life = math.log(2.0) / reversion_speed

    return MeanReversionParams(
        long_run_mean=long_run_mean,
        reversion_speed=reversion_speed,
        volatility=volatility,
        half_life=half_life,
    )
