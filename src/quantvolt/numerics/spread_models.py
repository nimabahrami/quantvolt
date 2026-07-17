"""Spread-option model kernels (Task 15).

Pure numeric kernels: ``float`` in, ``float`` out. No domain types and no
domain validation live here — the orchestrator (``pricing/spread_option.py``)
validates inputs and finite-differences these premiums for Greeks. The two
kernels both price a *call* on a spread and return the discounted premium:

- :func:`margrabe` — the zero-strike exchange option, ``max(F1 - F2, 0)``,
  priced by Margrabe's exact closed form.
- :func:`kirk` — the non-zero-strike spread option, ``max(F1 - F2 - K, 0)``,
  priced by Kirk's approximation. With ``strike == 0`` it reduces to Margrabe.

The standard normal CDF is the shared :func:`~quantvolt.numerics._normal.norm_cdf`
(also used by ``black76.py`` / ``exotic.py``).
"""

from __future__ import annotations

import math

from ..exceptions import ValidationError
from ._normal import norm_cdf as _norm_cdf


def margrabe(
    forward1: float,
    forward2: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Zero-strike spread (exchange) option: a call on ``forward1 - forward2``.

    Margrabe's exact closed form for the option to exchange one asset for
    another (equivalently, a zero-strike spread call). The spread volatility

        ``sigma = sqrt(sigma1**2 + sigma2**2 - 2*rho*sigma1*sigma2)``

    rises as ``rho`` falls, so the premium increases as correlation decreases.

    Args:
        forward1: Forward price of the long leg (``F1``), positive.
        forward2: Forward price of the short leg (``F2``), positive.
        sigma1: Volatility of ``forward1``.
        sigma2: Volatility of ``forward2``.
        rho: Correlation between the two legs, in ``(-1, 1)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to the settlement date, in ``(0, 1]``.

    Returns:
        The discounted call premium on the spread.
    """
    sqrt_t = math.sqrt(time_to_expiry)
    sigma = math.sqrt(sigma1**2 + sigma2**2 - 2.0 * rho * sigma1 * sigma2)
    if sigma * sqrt_t == 0.0:
        return discount_factor * max(forward1 - forward2, 0.0)
    d1 = (math.log(forward1 / forward2) + 0.5 * sigma**2 * time_to_expiry) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return discount_factor * (forward1 * _norm_cdf(d1) - forward2 * _norm_cdf(d2))


def kirk(
    forward1: float,
    forward2: float,
    strike: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Kirk's approximation for a call on ``forward1 - forward2 - strike``.

    Kirk approximates the spread option by treating the shifted short leg
    ``F2K = forward2 + strike`` as a single lognormal asset with an effective
    volatility

        ``sigma_eff = sqrt(sigma1**2 + (sigma2*w)**2 - 2*rho*sigma1*sigma2*w)``

    where ``w = forward2 / F2K``. When ``strike == 0`` this collapses to the
    exact Margrabe form (``F2K == forward2`` and ``w == 1``). The premium is
    monotonically decreasing in ``strike``.

    The approximation's domain is exactly ``forward2 + strike > 0``: the shifted
    short leg ``F2K`` must itself be a positive "asset" for Kirk's single-lognormal
    treatment to mean anything (a lognormal cannot have a non-positive level). So
    ``strike`` may be negative, but only down to just above ``-forward2``; at
    ``strike == -forward2`` the weight ``w = forward2 / F2K`` divides by zero, and
    below it ``F2K < 0`` makes ``log(forward1 / F2K)`` undefined.

    Args:
        forward1: Forward price of the long leg (``F1``), positive.
        forward2: Forward price of the short leg (``F2``), positive.
        strike: Spread strike ``K``; may be negative, zero, or positive, but
            ``forward2 + strike`` must be strictly positive.
        sigma1: Volatility of ``forward1``.
        sigma2: Volatility of ``forward2``.
        rho: Correlation between the two legs, in ``(-1, 1)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to the settlement date, in ``(0, 1]``.

    Returns:
        The discounted call premium on the spread.

    Raises:
        ValidationError: If ``forward2 + strike`` is not strictly positive (Kirk's
            approximation has no shifted-asset representation there).
    """
    forward2_shifted = forward2 + strike
    if not forward2_shifted > 0.0:
        raise ValidationError(
            "strike must satisfy forward2 + strike > 0 for Kirk's approximation "
            f"(the shifted short leg must be a positive asset), got forward2={forward2!r}, "
            f"strike={strike!r} (forward2 + strike = {forward2_shifted!r})"
        )
    weight = forward2 / forward2_shifted
    sqrt_t = math.sqrt(time_to_expiry)
    sigma_eff = math.sqrt(sigma1**2 + (sigma2 * weight) ** 2 - 2.0 * rho * sigma1 * sigma2 * weight)
    if sigma_eff * sqrt_t == 0.0:
        return discount_factor * max(forward1 - forward2_shifted, 0.0)
    d1 = (math.log(forward1 / forward2_shifted) + 0.5 * sigma_eff**2 * time_to_expiry) / (
        sigma_eff * sqrt_t
    )
    d2 = d1 - sigma_eff * sqrt_t
    return discount_factor * (forward1 * _norm_cdf(d1) - forward2_shifted * _norm_cdf(d2))
