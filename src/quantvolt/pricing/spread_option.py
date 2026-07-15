"""Spread options — Margrabe / Kirk (Task 30; Req 7.1-7.4).

Thin pricer over the pure kernels in :mod:`quantvolt.numerics.spread_models`
(coding-style: validate -> kernel -> package). Model selection by strike is a
Simple Factory (Property 18): ``strike == 0.0`` selects Margrabe's exact
exchange-option formula, any other strike selects Kirk's approximation.

Sensitivities (Req 7.2) are central finite differences of the selected kernel
premium — the kernels return the premium only — each scaled by ``notional``:

- ``delta1`` / ``delta2``: relative forward bumps of ``1e-4 x forward``;
- ``vega1`` / ``vega2``: absolute volatility bumps of ``1e-4``;
- ``correlation_sensitivity``: absolute bump of ``1e-4``, clamped so that
  ``correlation +/- bump`` stays strictly inside ``(-1, 1)``.

A spark spread (Req 7.3) is the option on ``F_power - heat_rate * F_gas - K``,
i.e. the gas-leg notional is ``notional_power x heat_rate``. This is realised
by pricing a transformed request with ``forward2 * heat_rate`` and ``sigma2``
unchanged — scaling a lognormal forward by a constant leaves its lognormal
volatility untouched — so the transformation is exact for both kernels.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from .._validation import (
    require_correlation,
    require_discount_factor,
    require_non_negative,
    require_positive,
)
from ..numerics.rootfind import finite_difference_bump
from ..numerics.spread_models import kirk, margrabe

_FORWARD_BUMP_FRACTION = 1e-4
_VOL_BUMP = 1e-4
_CORRELATION_BUMP = 1e-4

_SpreadKernel = Callable[[float, float, float, float, float, float, float, float], float]
"""``(forward1, forward2, strike, sigma1, sigma2, rho, time_to_expiry, discount_factor)``
-> discounted call premium on the spread."""


@dataclass(frozen=True, slots=True)
class SpreadOptionRequest:
    """Inputs for a call on ``forward1 - forward2 - strike`` (Req 7.1)."""

    forward1: float
    forward2: float
    strike: float
    sigma1: float
    sigma2: float
    correlation: float
    time_to_expiry: float
    discount_factor: float
    notional: float = 1.0


@dataclass(frozen=True, slots=True)
class SpreadOptionResult:
    """Premium plus finite-difference sensitivities, all scaled by notional (Req 7.2).

    ``delta1``/``delta2`` are sensitivities to ``forward1``/``forward2`` exactly as
    passed to :func:`price_spread_option`. :func:`price_spark_spread_option` is the
    one exception: it chain-rules ``delta2`` back onto the RAW gas forward it was
    given (``request.forward2``, before the internal ``heat_rate`` scaling), so that
    ``delta2`` always means "sensitivity to the underlying commodity forward the
    caller supplied" — the same convention :mod:`quantvolt.pricing.tolling` uses when
    it chain-rules a spread option's ``delta2`` onto the raw fuel/EUA forwards.
    """

    premium: float
    delta1: float
    delta2: float
    vega1: float
    vega2: float
    correlation_sensitivity: float


def _margrabe_kernel(
    forward1: float,
    forward2: float,
    strike: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Adapt :func:`margrabe` to the uniform kernel signature.

    Margrabe is the exact zero-strike closed form; ``strike`` (identically
    ``0.0`` by selection) is not consumed.
    """
    del strike
    return margrabe(forward1, forward2, sigma1, sigma2, rho, time_to_expiry, discount_factor)


def _select_kernel(strike: float) -> _SpreadKernel:
    """Simple Factory (Property 18): ``strike == 0.0`` -> Margrabe exact, else Kirk."""
    return _margrabe_kernel if strike == 0.0 else kirk


def _validate_request(request: SpreadOptionRequest) -> None:
    """Eager boundary validation before any computation (Req 7.1, 7.4; Property 19)."""
    require_correlation("correlation", request.correlation)
    require_positive("forward1", request.forward1)
    require_positive("forward2", request.forward2)
    require_non_negative("strike", request.strike)
    require_positive("sigma1", request.sigma1)
    require_positive("sigma2", request.sigma2)
    require_positive("time_to_expiry", request.time_to_expiry)
    require_discount_factor("discount_factor", request.discount_factor)
    require_positive("notional", request.notional)


def price_spread_option(
    request: SpreadOptionRequest,
    *,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    correlation_bump: float = _CORRELATION_BUMP,
) -> SpreadOptionResult:
    """Price a spread call and its sensitivities (Req 7.1, 7.2).

    ``strike == 0.0`` prices via Margrabe's exact formula, any other strike via
    Kirk's approximation (Property 18). The premium is the kernel premium
    scaled by ``request.notional``; the five sensitivities are central finite
    differences of the same kernel, likewise notional-scaled (module docstring
    lists the bump sizes).

    Args:
        request: Fully specified spread-option request; validated eagerly
            before any computation.
        forward_bump_fraction: Relative forward bump for delta1/delta2,
            positive (default ``1e-4``).
        vol_bump: Absolute vol bump for vega1/vega2, positive (default
            ``1e-4``).
        correlation_bump: Absolute correlation bump for
            ``correlation_sensitivity``, positive (default ``1e-4``); clamped
            so ``correlation +/- bump`` stays strictly inside ``(-1, 1)``.

    Raises:
        ValidationError: If ``correlation`` is outside ``(-1, 1)`` (Req 7.4),
            any of ``forward1``, ``forward2``, ``sigma1``, ``sigma2``,
            ``time_to_expiry``, ``notional`` is not > 0, ``strike`` < 0,
            ``discount_factor`` is outside ``(0, 1]``, or
            ``forward_bump_fraction``/``vol_bump``/``correlation_bump`` is not
            > 0.
    """
    _validate_request(request)
    require_positive("forward_bump_fraction", forward_bump_fraction)
    require_positive("vol_bump", vol_bump)
    require_positive("correlation_bump", correlation_bump)
    kernel = _select_kernel(request.strike)

    def premium(
        forward1: float, forward2: float, sigma1: float, sigma2: float, correlation: float
    ) -> float:
        return kernel(
            forward1,
            forward2,
            request.strike,
            sigma1,
            sigma2,
            correlation,
            request.time_to_expiry,
            request.discount_factor,
        )

    f1, f2 = request.forward1, request.forward2
    s1, s2 = request.sigma1, request.sigma2
    rho = request.correlation
    notional = request.notional
    # Keep rho +/- bump strictly inside (-1, 1); rho itself is strictly inside, so
    # half the distance to the nearer boundary is always a positive valid bump.
    clamped_correlation_bump = min(correlation_bump, 0.5 * (1.0 - abs(rho)))
    return SpreadOptionResult(
        premium=notional * premium(f1, f2, s1, s2, rho),
        delta1=notional
        * finite_difference_bump(
            lambda bumped: premium(bumped, f2, s1, s2, rho), f1, forward_bump_fraction * f1
        ),
        delta2=notional
        * finite_difference_bump(
            lambda bumped: premium(f1, bumped, s1, s2, rho), f2, forward_bump_fraction * f2
        ),
        vega1=notional
        * finite_difference_bump(lambda bumped: premium(f1, f2, bumped, s2, rho), s1, vol_bump),
        vega2=notional
        * finite_difference_bump(lambda bumped: premium(f1, f2, s1, bumped, rho), s2, vol_bump),
        correlation_sensitivity=notional
        * finite_difference_bump(
            lambda bumped: premium(f1, f2, s1, s2, bumped), rho, clamped_correlation_bump
        ),
    )


def price_spark_spread_option(
    request: SpreadOptionRequest,
    heat_rate: float,
    *,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    correlation_bump: float = _CORRELATION_BUMP,
) -> SpreadOptionResult:
    """Price a spark spread: a call on ``F_power - heat_rate * F_gas - strike`` (Req 7.3).

    ``request.forward1`` is the power forward and ``request.forward2`` the RAW gas
    forward. The gas-leg notional is ``notional_power x heat_rate``, realised by
    transforming the request to ``forward2 * heat_rate`` (``sigma2`` unchanged: a
    constant multiple of a lognormal forward keeps the same lognormal volatility)
    and delegating to :func:`price_spread_option`. ``forward_bump_fraction``/
    ``vol_bump``/``correlation_bump`` are passed through unchanged.

    ``delta2`` convention (Req 7.2): the transformed request's ``delta2`` is the
    sensitivity to the SCALED gas forward (``heat_rate x F_gas``); this function
    chain-rules it back onto the raw ``F_gas`` the caller passed
    (``delta2_raw = delta2_transformed x heat_rate``), so ``delta2`` always means
    "sensitivity to the underlying commodity forward the caller supplied" — the
    same convention :mod:`quantvolt.pricing.tolling` uses for its fuel/EUA deltas.

    Raises:
        ValidationError: If ``heat_rate`` is not > 0, or the (transformed)
            request violates any :func:`price_spread_option` constraint.
    """
    require_positive("heat_rate", heat_rate)
    transformed = replace(request, forward2=request.forward2 * heat_rate)
    result = price_spread_option(
        transformed,
        forward_bump_fraction=forward_bump_fraction,
        vol_bump=vol_bump,
        correlation_bump=correlation_bump,
    )
    return replace(result, delta2=result.delta2 * heat_rate)
