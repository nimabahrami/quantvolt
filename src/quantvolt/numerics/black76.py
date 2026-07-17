"""Black-76 kernel — pure functions (Task 14).

Pure numeric kernels: ``float`` in, ``float`` / :class:`Greeks` out. No domain
types and no domain validation live here — orchestration (``pricing/vanilla.py``,
``pricing/implied_vol.py``, cap/floor and tolling strips) validates typed
requests and reuses these functions. :func:`black76_greeks` returning the shared
:class:`Greeks` value object is the single sanctioned exception to the
"float in, float out" rule for this package (design §2.7).

The three functions cover the Black-76 model for a European option on a forward:

- :func:`black76_price` — the discounted call/put premium.
- :func:`black76_greeks` — first-order sensitivities (plus gamma).
- :func:`black76_implied_vol` — Brent inversion of the premium, with the
  no-arbitrage bounds checked *before* inversion (Brent, not Newton, so it
  cannot diverge near zero vega — design §2.7).

The standard normal CDF ``N`` and PDF ``n`` come from ``scipy.stats.norm``.
"""

from __future__ import annotations

import math
from typing import Literal

from ..exceptions import NumericalError
from ..models.greeks import Greeks
from ._normal import norm_cdf as _norm_cdf
from ._normal import norm_pdf as _norm_pdf
from .rootfind import brent_root


def _black76_d1(
    forward: float, strike: float, sigma: float, time_to_expiry: float, sqrt_t: float
) -> float:
    """``d1 = (ln(F/K) + 0.5*sigma**2*T) / (sigma*sqrt(T))``, the moneyness term shared
    by :func:`black76_price` and :func:`black76_greeks`. Callers pass their own
    already-computed ``sqrt_t`` so it is not recomputed here."""
    return (math.log(forward / strike) + 0.5 * sigma**2 * time_to_expiry) / (sigma * sqrt_t)


def _black76_price_from_d(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    discount_factor: float,
    d1: float,
    d2: float,
) -> float:
    """``call = DF*(F*N(d1) - K*N(d2))``, ``put = DF*(K*N(-d2) - F*N(-d1))``, given an
    already-computed ``d1``/``d2`` (the non-degenerate branch of :func:`black76_price`,
    factored out so :func:`black76_greeks` can reuse it without recomputing ``d1``)."""
    if option_type == "call":
        return discount_factor * (forward * _norm_cdf(d1) - strike * _norm_cdf(d2))
    return discount_factor * (strike * _norm_cdf(-d2) - forward * _norm_cdf(-d1))


def black76_price(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Black-76 discounted premium for a European option on a forward.

    ``d1 = (ln(F/K) + 0.5*sigma**2*T) / (sigma*sqrt(T))``,
    ``d2 = d1 - sigma*sqrt(T)``,
    ``call = DF*(F*N(d1) - K*N(d2))``, ``put = DF*(K*N(-d2) - F*N(-d1))``.

    When ``sigma*sqrt(T)`` collapses to zero (zero vol or zero time-to-expiry)
    the forward is deterministic, so the premium falls back to the discounted
    intrinsic value: ``DF*max(F-K, 0)`` for a call, ``DF*max(K-F, 0)`` for a put.

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        The discounted option premium.
    """
    sqrt_t = math.sqrt(time_to_expiry)
    if sigma * sqrt_t == 0.0:
        if option_type == "call":
            return discount_factor * max(forward - strike, 0.0)
        return discount_factor * max(strike - forward, 0.0)
    d1 = _black76_d1(forward, strike, sigma, time_to_expiry, sqrt_t)
    d2 = d1 - sigma * sqrt_t
    return _black76_price_from_d(option_type, forward, strike, discount_factor, d1, d2)


def _black76_greeks_degenerate(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
) -> Greeks:
    """The ``sigma*sqrt(T) == 0`` limit of :func:`black76_greeks` (Fix 4).

    Mirrors :func:`black76_price`'s degenerate-limit convention: the forward is
    deterministic, so the price is the discounted intrinsic value and every
    diffusion-driven sensitivity (``gamma``, ``vega``) vanishes.

    - ``delta``: the limit of ``DF*N(d1)`` (call) / ``DF*(N(d1)-1)`` (put) as
      ``sigma*sqrt(T) -> 0`` with ``F != K`` is a step at the strike:
      ``DF*1{F>K}`` (call), ``-DF*1{F<K}`` (put). At the ``F == K`` boundary this
      function instead takes the *continuous* limit reached by holding ``F == K``
      fixed and letting ``sigma*sqrt(T) -> 0+`` in the full formula (``d1 -> 0``,
      ``N(0) = 0.5``): ``delta = DF/2`` (call), ``delta = -DF/2`` (put). This is the
      convention this function documents and pins; :func:`black76_price` itself has
      no kink to resolve (both the call and put payoff are exactly 0 at ``F == K``).
    - ``gamma`` = ``vega`` = 0: the deterministic forward has no convexity or
      volatility sensitivity left. At ``F == K`` this is a *choice*, not the unique
      limit: ``gamma``'s true ``sigma -> 0`` limit diverges (``~ 1/sigma``) and
      ``vega``'s depends on which of ``sigma`` / ``T`` is sent to zero (fixing ``T``
      and taking ``sigma -> 0`` gives a finite nonzero ``vega``; fixing ``sigma`` and
      taking ``T -> 0`` gives ``vega -> 0``) — the limit is direction-dependent and
      therefore not well-defined as a single value, so both are defined to be exactly
      ``0`` here by convention, consistent with the payoff having no genuine
      optionality left to be sensitive to.
    - ``theta``: the surviving *carry* term of the normal-branch formula,
      ``rate*price`` with ``rate = -ln(DF)/T`` — the vega-driven term
      ``DF*F*n(d1)*sigma/(2*sqrt(T))`` vanishes in this limit because ``sigma -> 0``
      dominates the ``1/sqrt(T)`` blow-up (and, when ``T -> 0`` instead, ``price`` is
      already the terminal intrinsic value with nothing left to decay). At ``T == 0``
      ``rate`` itself is undefined (``0/0``), so the carry contribution is defined to
      be exactly ``0`` there — a fully realized (matured) position has no further
      time decay to speak of.
    - ``rho`` = ``-T*price``, unchanged from the normal branch's formula (already
      well-defined, and exactly ``0`` at ``T == 0``).
    """
    price = black76_price(option_type, forward, strike, 0.0, time_to_expiry, discount_factor)
    if option_type == "call":
        if forward > strike:
            delta = discount_factor
        elif forward < strike:
            delta = 0.0
        else:
            delta = 0.5 * discount_factor
    else:
        if forward < strike:
            delta = -discount_factor
        elif forward > strike:
            delta = 0.0
        else:
            delta = -0.5 * discount_factor
    theta = -math.log(discount_factor) / time_to_expiry * price if time_to_expiry > 0.0 else 0.0
    rho = -time_to_expiry * price
    return Greeks(delta=delta, gamma=0.0, vega=0.0, theta=theta, rho=rho)


def black76_greeks(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> Greeks:
    """Black-76 sensitivities for a European option on a forward.

    Sign conventions (each sensitivity is per unit of the named input):

    - ``delta`` = ``d(price)/d(forward)`` = ``DF*N(d1)`` (call), ``DF*(N(d1)-1)`` (put).
    - ``gamma`` = second derivative of price w.r.t. the forward =
      ``DF*n(d1)/(F*sigma*sqrt(T))`` — identical for call and put.
    - ``vega``  = ``d(price)/d(sigma)`` = ``DF*F*n(d1)*sqrt(T)`` per unit vol —
      identical for call and put, and strictly positive.
    - ``theta`` = time *decay* ``-d(price)/d(T)`` (negative for a long option when
      ``r == 0``) = ``r*price - DF*F*n(d1)*sigma/(2*sqrt(T))`` with ``r = -ln(DF)/T``.
    - ``rho``   = ``d(price)/d(r)`` with the forward held fixed and ``DF = e^{-rT}``
      = ``-T*price`` (uses the call price for a call, the put price for a put).

    When ``sigma*sqrt(T)`` collapses to zero (zero vol or zero time-to-expiry) the
    forward is deterministic, exactly as in :func:`black76_price`, and this function
    falls back to the degenerate limit (:func:`_black76_greeks_degenerate`): ``gamma``
    and ``vega`` vanish, ``delta`` is a step at the strike (``DF/2`` at ``F == K``, by
    convention — see :func:`_black76_greeks_degenerate`), ``theta`` keeps only the
    discounting-carry term, and ``rho`` is unchanged.

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        A :class:`Greeks` value object ``(delta, gamma, vega, theta, rho)``.
    """
    sqrt_t = math.sqrt(time_to_expiry)
    if sigma * sqrt_t == 0.0:
        return _black76_greeks_degenerate(
            option_type, forward, strike, time_to_expiry, discount_factor
        )
    d1 = _black76_d1(forward, strike, sigma, time_to_expiry, sqrt_t)
    d2 = d1 - sigma * sqrt_t
    pdf_d1 = _norm_pdf(d1)
    price = _black76_price_from_d(option_type, forward, strike, discount_factor, d1, d2)
    rate = -math.log(discount_factor) / time_to_expiry

    if option_type == "call":
        delta = discount_factor * _norm_cdf(d1)
    else:
        delta = discount_factor * (_norm_cdf(d1) - 1.0)
    gamma = discount_factor * pdf_d1 / (forward * sigma * sqrt_t)
    vega = discount_factor * forward * pdf_d1 * sqrt_t
    theta = rate * price - discount_factor * forward * pdf_d1 * sigma / (2.0 * sqrt_t)
    rho = -time_to_expiry * price
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def black76_implied_vol(
    option_type: Literal["call", "put"],
    market_premium: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
    tol: float = 1e-4,
    *,
    vol_lower: float = 1e-9,
    vol_upper: float = 10.0,
    max_iter: int = 100,
) -> float:
    """Recover the Black-76 volatility that reprices ``market_premium``.

    The premium is monotonically increasing in ``sigma``, bounded below by the
    discounted intrinsic value (as ``sigma -> 0``) and above by the discounted
    forward/strike (as ``sigma -> inf``). The market premium must therefore lie
    strictly inside those no-arbitrage bounds, checked *before* inversion
    (Req 5.3):

    - call: ``DF*max(F-K, 0) < premium < DF*F``
    - put:  ``DF*max(K-F, 0) < premium < DF*K``

    A premium outside its bounds cannot be reproduced by any volatility, so this
    is a numeric precondition on the caller-supplied premium and raises
    :class:`~quantvolt.exceptions.NumericalError` (a ``ValueError`` subclass, for
    compatibility with callers using the low-level kernel API directly).
    Inversion then uses Brent's method over ``[vol_lower, vol_upper]`` (default
    ``[1e-9, 10.0]``) — a bracketing solver, so it cannot diverge near zero vega
    the way Newton-Raphson would (design §2.7).

    Args:
        option_type: ``"call"`` or ``"put"``.
        market_premium: Observed (discounted) option premium to invert.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.
        tol: Absolute x-tolerance on the recovered volatility.
        vol_lower: Lower Brent bracket endpoint for the recovered volatility,
            must be strictly positive.
        vol_upper: Upper Brent bracket endpoint, must be strictly greater than
            ``vol_lower``.
        max_iter: Maximum number of Brent iterations.

    Returns:
        The implied volatility ``sigma`` located in ``[vol_lower, vol_upper]``.

    Raises:
        NumericalError: If ``market_premium`` lies outside the no-arbitrage bounds,
            or if ``vol_lower``/``vol_upper`` do not form a valid bracket.
    """
    if not vol_lower > 0.0:
        raise NumericalError(f"vol_lower must be > 0, got {vol_lower!r}")
    if not vol_upper > vol_lower:
        raise NumericalError(f"vol_upper must be > vol_lower ({vol_lower!r}), got {vol_upper!r}")
    if option_type == "call":
        lower = discount_factor * max(forward - strike, 0.0)
        upper = discount_factor * forward
    else:
        lower = discount_factor * max(strike - forward, 0.0)
        upper = discount_factor * strike
    if not lower < market_premium < upper:
        raise NumericalError(
            f"market_premium {market_premium} is outside the no-arbitrage bounds "
            f"({lower}, {upper}) for a {option_type}; no implied volatility exists"
        )

    def objective(sigma: float) -> float:
        return (
            black76_price(option_type, forward, strike, sigma, time_to_expiry, discount_factor)
            - market_premium
        )

    return brent_root(objective, vol_lower, vol_upper, tol=tol, max_iter=max_iter)
