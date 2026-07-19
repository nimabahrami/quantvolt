"""Bachelier (normal) vanilla options — for forwards that can go negative.

Thin orchestration over the pure :mod:`quantvolt.numerics.bachelier` kernel, following the
pricing skeleton *validate -> kernel -> package* (base spec Reqs 5.4-5.6), exactly as
:mod:`quantvolt.pricing.vanilla` does for Black-76. All real math lives in the kernel; this
module only validates a typed request and packages the result.

**Why this exists.** Black-76 is lognormal and *raises* on non-positive forwards/strikes. The
Bachelier model prices the same European option under arithmetic Brownian motion, whose support
is the whole real line, so **negative and zero forwards and strikes are valid** — the point of
this feature (industry precedent: CME Clearing Advisory 20-171, 2020). Accordingly the request's
``forward`` and ``strike`` are validated for *finiteness only* (never sign): compare
:mod:`quantvolt.pricing.vanilla`, which requires them strictly positive.

**Volatility units — read this carefully.** ``normal_sigma`` is the **normal (absolute)
volatility** ``sigma_N``: a diffusion rate in price-units per ``sqrt(year)`` (e.g.
EUR/MWh/sqrt(yr)). It is **NOT** the dimensionless lognormal Black-76 ``sigma`` and the two are
**not interchangeable**. Passing a lognormal vol here (or a normal vol to the Black-76 pricer)
is a silent unit error. In particular, ``MarketData.vol_surfaces`` carry lognormal Black-76 vols;
they must NOT be reused as ``normal_sigma`` (see the spec's Requirement 7 — there is deliberately
no automatic Black-76 -> Bachelier fallback anywhere in the library).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .._validation import require_discount_factor, require_finite, require_positive
from ..models.greeks import Greeks
from ..numerics.bachelier import bachelier_greeks, bachelier_price


@dataclass(frozen=True, slots=True)
class BachelierOptionRequest:
    """A European vanilla call/put priced under the Bachelier (normal) model.

    ``forward`` and ``strike`` may be negative or zero (only finiteness is required).
    ``normal_sigma`` is the absolute normal volatility, NOT the lognormal Black-76 sigma.
    """

    option_type: Literal["call", "put"]
    strike: float
    notional: float
    forward: float
    normal_sigma: float
    time_to_expiry: float
    discount_factor: float


@dataclass(frozen=True, slots=True)
class BachelierOptionResult:
    premium: float
    greeks: Greeks


def price_bachelier_option(request: BachelierOptionRequest) -> BachelierOptionResult:
    """Price a single European vanilla option on a forward under the Bachelier (normal) model.

    Use this when the forward can be **negative or zero** (power, and — since 2020 — oil), where
    the lognormal :func:`quantvolt.pricing.vanilla.price_vanilla_option` would raise. Premium and
    Greeks are per-unit kernel outputs scaled by ``notional``.

    ``request.normal_sigma`` is the **absolute normal volatility** ``sigma_N`` (price-units per
    ``sqrt(year)``), **not** the dimensionless lognormal Black-76 sigma; the two are not
    interchangeable (see the module docstring).

    Args:
        request: Fully specified option; all domains are validated eagerly before any
            computation. ``forward`` and ``strike`` are validated for finiteness only — negative
            and zero are permitted — while ``normal_sigma``, ``time_to_expiry`` and ``notional``
            must be strictly positive and ``discount_factor`` must lie in ``(0, 1]``.

    Returns:
        The notional-scaled premium and Greeks.

    Raises:
        ValidationError: If ``forward`` or ``strike`` is not finite, ``normal_sigma``,
            ``time_to_expiry`` or ``notional`` is not > 0, or ``discount_factor`` is outside
            ``(0, 1]``.
    """
    require_finite("forward", request.forward)
    require_finite("strike", request.strike)
    require_positive("normal_sigma", request.normal_sigma)
    require_positive("time_to_expiry", request.time_to_expiry)
    require_discount_factor("discount_factor", request.discount_factor)
    require_positive("notional", request.notional)

    premium = request.notional * bachelier_price(
        request.option_type,
        request.forward,
        request.strike,
        request.normal_sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    greeks = bachelier_greeks(
        request.option_type,
        request.forward,
        request.strike,
        request.normal_sigma,
        request.time_to_expiry,
        request.discount_factor,
    ).scale(request.notional)
    return BachelierOptionResult(premium=premium, greeks=greeks)
