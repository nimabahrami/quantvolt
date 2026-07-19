"""Bachelier (normal) kernel — pure functions (spec ``bachelier-negative-forwards``).

Pure numeric kernels: ``float`` in, ``float`` / :class:`Greeks` out. No domain types and no
domain validation live here — the pricing layer (``pricing/bachelier.py``) validates typed
requests and reuses these functions. :func:`bachelier_greeks` returning the shared
:class:`Greeks` value object is the sanctioned exception to the "float in, float out" rule,
following :mod:`quantvolt.numerics.black76`'s precedent.

The Bachelier model prices a European option on a forward under **arithmetic** Brownian motion
``dF_t = sigma_N dW_t``. Unlike Black-76 (lognormal, ``ln(F/K)``, needs ``F, K > 0``), its
support is the whole real line, so **negative and zero forwards and strikes are valid inputs** —
that is the entire purpose of this module (industry precedent: CME Clearing Advisory 20-171,
2020, switched negative-priced energy options from Black-Scholes to Bachelier).

``sigma_N`` is the **normal (absolute) volatility**: a diffusion rate in price-units-per-sqrt(year)
(e.g. EUR/MWh/sqrt(yr)), NOT the dimensionless lognormal Black-76 ``sigma``. The two are not
interchangeable; conflating them is a unit error.

Mathematics is transcribed from the cited source, never written from memory (spec
``.kiro/specs/bachelier-negative-forwards/design.md`` References):

- Choi, Kwak, Tee, Wang, "A Black-Scholes user's guide to the Bachelier model",
  arXiv:2104.08686 (J. Futures Markets 42(5), 2022): premium Eq. (1) / Footnote 5 (Section 2.1),
  ATM identity Eq. (2), Greeks Section 5.1.

The three functions cover the Bachelier model for a European option on a forward:

- :func:`bachelier_price` — the discounted call/put premium (Eq. (1) / Footnote 5).
- :func:`bachelier_greeks` — first-order sensitivities plus gamma (Section 5.1, plus the
  discounted ``theta``/``rho`` derived from Eq. (1)).
- :func:`bachelier_implied_vol` — Brent inversion of the premium for ``sigma_N``, with the
  ``sigma_N -> 0`` no-arbitrage lower bound checked before inversion (the Bachelier call premium
  is unbounded above, so there is no finite upper no-arbitrage bound).

The standard normal CDF ``N`` and PDF ``n`` come from the shared :mod:`quantvolt.numerics._normal`.
"""

from __future__ import annotations

import math
from typing import Literal

from ..exceptions import NumericalError
from ..models.greeks import Greeks
from ._degenerate import _degenerate_greeks
from ._normal import norm_cdf as _norm_cdf
from ._normal import norm_pdf as _norm_pdf
from .rootfind import brent_root


def _bachelier_d(forward: float, strike: float, total_stdev: float) -> float:
    """``d_N = (F - K) / (sigma_N * sqrt(T))``, the normalised moneyness of source Eq. (1).

    Callers pass their own already-computed ``total_stdev = sigma_N * sqrt(T)`` so it is not
    recomputed. A single ``d_N`` (contrast Black-76's ``d1``/``d2``) suffices because the
    arithmetic-Brownian terminal law ``F_T = F + sigma_N sqrt(T) Z`` is symmetric.
    """
    return (forward - strike) / total_stdev


def _bachelier_price_from_d(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    total_stdev: float,
    discount_factor: float,
    d: float,
) -> float:
    """Discounted premium given an already-computed ``d`` and ``total_stdev = sigma_N sqrt(T)``.

    ``call = DF*[(F-K)N(d) + sigma_N sqrt(T) n(d)]`` (source Eq. (1)),
    ``put  = DF*[(K-F)N(-d) + sigma_N sqrt(T) n(d)]`` (source Footnote 5). Factored out so
    :func:`bachelier_greeks` reuses it without recomputing ``d``.
    """
    pdf_term = total_stdev * _norm_pdf(d)
    if option_type == "call":
        return discount_factor * ((forward - strike) * _norm_cdf(d) + pdf_term)
    return discount_factor * ((strike - forward) * _norm_cdf(-d) + pdf_term)


def bachelier_price(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    normal_sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Bachelier (normal) discounted premium for a European option on a forward.

    ``d_N = (F - K) / (sigma_N sqrt(T))``,
    ``call = DF*[(F-K)N(d_N) + sigma_N sqrt(T) n(d_N)]`` (source Eq. (1)),
    ``put  = DF*[(K-F)N(-d_N) + sigma_N sqrt(T) n(d_N)]`` (source Footnote 5).

    ``forward`` and ``strike`` may be **negative or zero** — the arithmetic-Brownian support is
    the whole real line, so no sign special-casing is needed (that is the point of this model).

    When ``sigma_N*sqrt(T)`` collapses to zero (zero normal vol or zero time-to-expiry) the
    forward is deterministic, so the premium falls back to the discounted intrinsic value:
    ``DF*max(F-K, 0)`` for a call, ``DF*max(K-F, 0)`` for a put (mirroring
    ``black76.py:88-92``'s convention).

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``); may be negative or zero.
        strike: Option strike (``K``); may be negative or zero.
        normal_sigma: **Normal (absolute) volatility** ``sigma_N`` of the forward, in
            price-units per ``sqrt(year)`` — NOT the dimensionless lognormal Black-76 sigma.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        The discounted option premium.
    """
    total_stdev = normal_sigma * math.sqrt(time_to_expiry)
    if total_stdev == 0.0:
        if option_type == "call":
            return discount_factor * max(forward - strike, 0.0)
        return discount_factor * max(strike - forward, 0.0)
    d = _bachelier_d(forward, strike, total_stdev)
    return _bachelier_price_from_d(option_type, forward, strike, total_stdev, discount_factor, d)


def _bachelier_greeks_degenerate(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
) -> Greeks:
    """The ``sigma_N*sqrt(T) == 0`` limit of :func:`bachelier_greeks`.

    Mirrors :func:`bachelier_price`'s degenerate-limit convention (and
    ``black76.py``'s ``_black76_greeks_degenerate``): the forward is deterministic, so the price
    is the discounted intrinsic value and every diffusion-driven sensitivity (``gamma``, ``vega``)
    vanishes.

    - ``delta``: the limit of ``DF*N(d_N)`` (call) / ``DF*(N(d_N)-1)`` (put) as
      ``sigma_N*sqrt(T) -> 0`` with ``F != K`` is a step at the strike: ``DF*1{F>K}`` (call),
      ``-DF*1{F<K}`` (put). At ``F == K`` this takes the continuous limit (``d_N -> 0``,
      ``N(0) = 0.5``): ``delta = DF/2`` (call), ``-DF/2`` (put) — the same convention choice as
      the Black-76 kernel.
    - ``gamma`` = ``vega`` = 0: the deterministic forward has no convexity or volatility
      sensitivity left (at ``F == K`` this is a convention, not a unique limit — the same
      reasoning as ``black76.py``).
    - ``theta`` = ``rate*price`` carry term with ``rate = -ln(DF)/T``; the vega-decay term
      ``DF*sigma_N n(d_N)/(2 sqrt(T))`` vanishes as ``sigma_N -> 0``, and ``rate`` itself is
      undefined at ``T == 0`` (``0/0``) so the carry is defined to be ``0`` there.
    - ``rho`` = ``-T*price``, unchanged from the non-degenerate branch.

    Delegates the shared arithmetic to :func:`~quantvolt.numerics._degenerate._degenerate_greeks`
    (model-specific framing only lives in this docstring; Bachelier's degenerate limit is
    numerically identical to Black-76's).
    """
    return _degenerate_greeks(option_type, forward, strike, time_to_expiry, discount_factor)


def bachelier_greeks(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    normal_sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> Greeks:
    """Bachelier (normal) sensitivities for a European option on a forward.

    The diffusion Greeks are the ``DF``-discounted forms of source Section 5.1 (with
    ``d_N = (F-K)/(sigma_N sqrt(T))``); ``theta``/``rho`` follow the same discounted-price
    conventions as ``black76.py:158-180`` so the two models are directly comparable. Each
    sensitivity is per unit of the named input:

    - ``delta`` = ``d(price)/dF`` = ``DF*N(d_N)`` (call), ``DF*(N(d_N)-1)`` (put)
      (source Section 5.1 Delta, times ``DF``).
    - ``gamma`` = ``d2(price)/dF2`` = ``DF*n(d_N)/(sigma_N sqrt(T))`` — identical for call and put
      (source Section 5.1 Gamma, times ``DF``).
    - ``vega``  = ``d(price)/d(sigma_N)`` = ``DF*sqrt(T)*n(d_N)`` — identical for call and put,
      strictly positive (source Section 5.1 Vega, times ``DF``). Note there is **no ``F``
      factor** (contrast Black-76's ``DF*F*n(d1)*sqrt(T)``): ``sigma_N`` already carries price
      units.
    - ``theta`` = time *decay* ``-d(price)/dT`` (``F``, ``r`` fixed, ``DF = e^{-rT}``) =
      ``r*price - DF*sigma_N n(d_N)/(2 sqrt(T))`` with ``r = -ln(DF)/T``. **Derived from cited
      Eq. (1)**: with ``price = DF*C_und`` and the source undiscounted
      ``Theta_n = d(C_und)/d(-T) = -sigma_N n(d_N)/(2 sqrt(T))``, ``-d(price)/dT = r*price -
      DF*d(C_und)/dT = r*price - DF*sigma_N n(d_N)/(2 sqrt(T))``. The ``r*price`` carry term makes
      discounted theta differ between call and put (source Footnote 13).
    - ``rho``   = ``d(price)/dr`` (``F, sigma_N, T`` fixed, ``DF = e^{-rT}``) = ``-T*price``.
      **Derived from cited Eq. (1)**: ``d(e^{-rT})/dr * C_und = -T*price``.

    When ``sigma_N*sqrt(T)`` collapses to zero (zero normal vol or zero time-to-expiry) the
    forward is deterministic, exactly as in :func:`bachelier_price`, and this function falls back
    to the degenerate limit (:func:`_bachelier_greeks_degenerate`): ``gamma`` and ``vega``
    vanish, ``delta`` is a step at the strike (``DF/2`` at ``F == K``), ``theta`` keeps only the
    discounting-carry term, and ``rho`` is unchanged.

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``); may be negative or zero.
        strike: Option strike (``K``); may be negative or zero.
        normal_sigma: **Normal (absolute) volatility** ``sigma_N``, per ``sqrt(year)`` — NOT the
            lognormal Black-76 sigma.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        A :class:`Greeks` value object ``(delta, gamma, vega, theta, rho)``.
    """
    total_stdev = normal_sigma * math.sqrt(time_to_expiry)
    if total_stdev == 0.0:
        return _bachelier_greeks_degenerate(
            option_type, forward, strike, time_to_expiry, discount_factor
        )
    sqrt_t = math.sqrt(time_to_expiry)
    d = _bachelier_d(forward, strike, total_stdev)
    pdf_d = _norm_pdf(d)
    price = _bachelier_price_from_d(option_type, forward, strike, total_stdev, discount_factor, d)
    rate = -math.log(discount_factor) / time_to_expiry

    if option_type == "call":
        delta = discount_factor * _norm_cdf(d)
    else:
        delta = discount_factor * (_norm_cdf(d) - 1.0)
    gamma = discount_factor * pdf_d / total_stdev
    vega = discount_factor * sqrt_t * pdf_d
    theta = rate * price - discount_factor * normal_sigma * pdf_d / (2.0 * sqrt_t)
    rho = -time_to_expiry * price
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta, rho=rho)


def bachelier_atm_seed(undiscounted_atm_premium: float, time_to_expiry: float) -> float:
    """Bachelier ATM normal-vol seed from source Eq. (2): ``sigma_N = C_N(F0) * sqrt(2*pi/T)``.

    ``C_N(F0)`` is the *undiscounted* at-the-money premium (``discounted / DF``). This is the
    natural scale for ``sigma_N`` and anchors :func:`bachelier_implied_vol`'s search bracket.
    """
    return undiscounted_atm_premium * math.sqrt(2.0 * math.pi / time_to_expiry)


def bachelier_implied_vol(
    option_type: Literal["call", "put"],
    market_premium: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
    tol: float = 1e-4,
    *,
    vol_lower: float = 1e-9,
    vol_upper: float = 1e6,
    max_iter: int = 100,
) -> float:
    """Recover the Bachelier normal volatility ``sigma_N`` that reprices ``market_premium``.

    The premium is monotonically increasing in ``sigma_N``, bounded below by the discounted
    intrinsic value (as ``sigma_N -> 0``). Unlike Black-76, the Bachelier call premium is
    **unbounded above** as ``sigma_N -> inf`` (``C ~ DF*sigma_N sqrt(T)/sqrt(2*pi) -> inf``), so
    there is no finite closed-form upper no-arbitrage bound; instead the premium must be
    reachable within the search bracket ``[vol_lower, vol_upper]``:

    - lower no-arbitrage bound: ``premium > DF*max(F-K, 0)`` (call) / ``> DF*max(K-F, 0)`` (put).
    - bracket reach: ``premium < bachelier_price(..., vol_upper, ...)``; otherwise raise
      ``vol_upper``.

    The ATM identity source Eq. (2) (:func:`bachelier_atm_seed`) gives the natural ``sigma_N``
    scale; the default ``vol_upper`` sits well above any market-implied normal vol. Inversion
    then uses Brent's method (a bracketing solver — it cannot diverge near zero vega).

    Args:
        option_type: ``"call"`` or ``"put"``.
        market_premium: Observed (discounted) option premium to invert.
        forward: Forward price of the underlying (``F``); may be negative or zero.
        strike: Option strike (``K``); may be negative or zero.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.
        tol: Absolute x-tolerance on the recovered normal volatility.
        vol_lower: Lower Brent bracket endpoint, strictly positive.
        vol_upper: Upper Brent bracket endpoint, strictly greater than ``vol_lower``.
        max_iter: Maximum number of Brent iterations.

    Returns:
        The implied normal volatility ``sigma_N`` located in ``[vol_lower, vol_upper]``.

    Raises:
        NumericalError: If ``market_premium`` is not above the discounted-intrinsic lower bound,
            exceeds the premium reachable at ``vol_upper``, or ``vol_lower``/``vol_upper`` do not
            form a valid bracket.
    """
    if not vol_lower > 0.0:
        raise NumericalError(f"vol_lower must be > 0, got {vol_lower!r}")
    if not vol_upper > vol_lower:
        raise NumericalError(f"vol_upper must be > vol_lower ({vol_lower!r}), got {vol_upper!r}")
    if option_type == "call":
        intrinsic = discount_factor * max(forward - strike, 0.0)
    else:
        intrinsic = discount_factor * max(strike - forward, 0.0)
    if not market_premium > intrinsic:
        raise NumericalError(
            f"market_premium {market_premium} is not above the discounted intrinsic lower bound "
            f"{intrinsic} for a {option_type}; no positive normal volatility exists"
        )
    upper_premium = bachelier_price(
        option_type, forward, strike, vol_upper, time_to_expiry, discount_factor
    )
    if not market_premium < upper_premium:
        raise NumericalError(
            f"market_premium {market_premium} exceeds the premium {upper_premium} reachable at "
            f"vol_upper={vol_upper} for a {option_type}; raise vol_upper to invert it"
        )

    def objective(sigma: float) -> float:
        return (
            bachelier_price(option_type, forward, strike, sigma, time_to_expiry, discount_factor)
            - market_premium
        )

    return brent_root(objective, vol_lower, vol_upper, tol=tol, max_iter=max_iter)
