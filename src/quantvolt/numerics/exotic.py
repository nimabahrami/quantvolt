"""Exotic-option closed-form kernels — one cohesive model family (Tasks 16-17).

Grouped like ``spread_models`` and ``pricing/exotic``: Asian, barrier, and lookback are option
*types*, priced here by closed form. Monte Carlo lives in ``monte_carlo`` (native Rust).

Pure numeric kernels: ``float`` in, ``float`` out. No domain types and no domain validation
live here — the orchestrator (``pricing/exotic.py``) validates typed requests. Every form is a
Black-76 world on a *forward* (cost of carry ``b == 0``); the risk-free rate, when a formula
needs it, is recovered as ``r = -ln(DF)/T``. The two Asian closed forms reuse
:func:`~quantvolt.numerics.black76.black76_price` after adjusting the forward / volatility.

The standard normal CDF ``N`` and PDF ``n`` come from ``scipy.stats.norm``.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Literal

from scipy.stats import norm  # type: ignore[import-untyped]

from .black76 import black76_price


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function ``N(x)``."""
    return float(norm.cdf(x))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function ``n(x)``."""
    return float(norm.pdf(x))


# --- Asian (Task 16) -------------------------------------------------------


# Below this ``var = sigma**2*T`` threshold, ``exp(var) - 1 - var`` computed directly
# suffers catastrophic cancellation (its true magnitude is O(var**2) while the
# intermediate ``exp(var)`` carries only ~1e-16 relative precision around 1.0), so the
# small-``var`` branch below uses a cancellation-free Taylor series instead (Fix 1).
_ASIAN_MOMENT_SMALL_VAR_THRESHOLD = 1e-3


def _asian_second_moment_ratio(var: float) -> float:
    """Stable ``M2/F**2 - 1`` for the Turnbull-Wakeman arithmetic-average moment match.

    ``M2/F**2 = 2*(exp(var) - 1 - var)/var**2`` with ``var = sigma**2*T``. Computed
    directly, ``exp(var) - 1 - var`` loses nearly all significance once ``var`` drops
    below roughly ``1e-3``: the term is ``O(var**2)`` but ``exp(var)`` itself carries only
    ``~1e-16`` *relative* precision, i.e. ``~1e-16`` *absolute* error near 1.0, which
    swamps an ``O(var**2)`` result once ``var`` is small enough.

    Below :data:`_ASIAN_MOMENT_SMALL_VAR_THRESHOLD` the ratio minus one is instead
    evaluated from its convergent Taylor series in ``var``

        ``x = var/3 + var**2/12 + var**3/60 + var**4/360 + var**5/2520 + O(var**6)``,

    obtained by expanding ``exp(var) - 1 - var = sum_{n>=2} var**n/n!`` term-by-term and
    dividing by ``var**2/2``. Every term is a plain sum of positive quantities, so there
    is no cancellation, and five terms are accurate to machine precision over the
    threshold's range (the omitted ``var**6/20160`` term is ``< 5e-23`` at the
    threshold). Above the threshold, :func:`math.expm1` removes the cancellation in
    ``exp(var) - 1`` itself, leaving only a benign subtraction of ``var``.

    Returns:
        ``M2/F**2 - 1``, so the matched log-variance is ``log1p(result)`` (stable for
        the small quantity this function returns), never ``log`` of a value near 1.
    """
    if var < _ASIAN_MOMENT_SMALL_VAR_THRESHOLD:
        return var * (
            1.0 / 3.0 + var * (1.0 / 12.0 + var * (1.0 / 60.0 + var * (1.0 / 360.0 + var / 2520.0)))
        )
    return 2.0 * (math.expm1(var) - var) / var**2 - 1.0


def turnbull_wakeman(
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    option_type: Literal["call", "put"],
) -> float:
    """Arithmetic-average Asian option, Turnbull-Wakeman moment-matched closed form.

    The arithmetic average of the forward is not lognormal, so its first two moments under
    the forward measure are matched to a lognormal and priced with Black-76. With ``b == 0``
    the expected average equals the forward, ``M1 = F``, and the second moment is

        ``M2 = F**2 * 2*(exp(sigma**2*T) - 1 - sigma**2*T) / (sigma**2*T)**2``.

    The matched volatility is ``sigma_a = sqrt(ln(M2/M1**2)/T)`` and the option is
    ``black76_price(option_type, M1, K, sigma_a, T, DF)``. As ``sigma*sqrt(T) -> 0`` the average
    is deterministic (``= F``) and both moments collapse to ``M1**2``, so the price falls back
    to the discounted intrinsic value ``DF*max(F-K, 0)`` (call) / ``DF*max(K-F, 0)`` (put).
    ``M1`` cancels out of ``M2/M1**2``, so the moment ratio (:func:`_asian_second_moment_ratio`)
    is evaluated directly in ``var = sigma**2*T``, avoiding the catastrophic cancellation of
    a naive ``exp(var) - 1 - var`` for small ``var``.

    Args:
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.
        option_type: ``"call"`` or ``"put"``.

    Returns:
        The discounted arithmetic-average Asian option premium.
    """
    sqrt_t = math.sqrt(time_to_expiry)
    if sigma * sqrt_t == 0.0:
        if option_type == "call":
            return discount_factor * max(forward - strike, 0.0)
        return discount_factor * max(strike - forward, 0.0)
    var = sigma**2 * time_to_expiry
    moment_ratio_minus_one = _asian_second_moment_ratio(var)
    sigma_a = math.sqrt(math.log1p(moment_ratio_minus_one) / time_to_expiry)
    return black76_price(option_type, forward, strike, sigma_a, time_to_expiry, discount_factor)


def kemna_vorst(
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    option_type: Literal["call", "put"],
) -> float:
    """Geometric-average Asian option, Kemna-Vorst *exact* closed form.

    The continuous geometric average of a lognormal forward is itself lognormal, so the option
    is priced exactly by Black-76 on an adjusted forward and volatility:
    ``sigma_g = sigma/sqrt(3)`` and ``F_g = F*exp(-sigma**2*T/12)`` (the convexity correction
    of the geometric average under the forward measure with ``b == 0``). Geometric averaging
    lowers both the effective level and the effective volatility, so this price sits below the
    corresponding vanilla Black-76 premium. The ``sigma -> 0`` limit is handled inside
    :func:`~quantvolt.numerics.black76.black76_price` (``F_g -> F``, ``sigma_g -> 0``).

    Args:
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.
        option_type: ``"call"`` or ``"put"``.

    Returns:
        The discounted geometric-average Asian option premium.
    """
    sigma_g = sigma / math.sqrt(3.0)
    forward_g = forward * math.exp(-(sigma**2) * time_to_expiry / 12.0)
    return black76_price(option_type, forward_g, strike, sigma_g, time_to_expiry, discount_factor)


# --- Barrier (Task 17) -----------------------------------------------------


def barrier_analytic(
    option_type: Literal["call", "put"],
    barrier_type: Literal["up_in", "up_out", "down_in", "down_out"],
    forward: float,
    strike: float,
    barrier: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Single-barrier option, Reiner-Rubinstein / Merton closed form (no rebate).

    The full set of ``{up, down} x {in, out} x {call, put}`` barriers is assembled from the
    standard building blocks ``A, B, C, D`` (Haug, *The Complete Guide to Option Pricing
    Formulas*), with ``phi = +1`` for a call / ``-1`` for a put and ``eta = +1`` for a *down*
    barrier / ``-1`` for an *up* barrier. With the forward-world carry ``b == 0`` the drift
    parameter is ``mu = -1/2`` and ``exp((b-r)T) = DF``, so block ``A`` reduces exactly to the
    vanilla Black-76 premium. Because a knock-in and its matching knock-out partition that
    vanilla premium, ``in + out`` reprices the vanilla by construction (in/out parity, rebate 0).

    The combination selected depends on whether the strike sits above or below the barrier, per
    the Reiner-Rubinstein table; the choice of blocks is a dispatch on
    ``(option_type, barrier_type)`` rather than a nested switch.

    Args:
        option_type: ``"call"`` or ``"put"``.
        barrier_type: ``"up_in"``, ``"up_out"``, ``"down_in"`` or ``"down_out"``.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        barrier: Barrier level (``H``); must sit above ``F`` for *up* and below ``F`` for *down*.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        The discounted single-barrier option premium (no rebate).
    """
    phi = 1.0 if option_type == "call" else -1.0
    eta = 1.0 if barrier_type.startswith("down") else -1.0
    s, k, h, df = forward, strike, barrier, discount_factor
    vst = sigma * math.sqrt(time_to_expiry)
    mu = -0.5  # (b - sigma**2/2)/sigma**2 with the forward-world carry b = 0.

    x1 = math.log(s / k) / vst + (1.0 + mu) * vst
    x2 = math.log(s / h) / vst + (1.0 + mu) * vst
    y1 = math.log(h**2 / (s * k)) / vst + (1.0 + mu) * vst
    y2 = math.log(h / s) / vst + (1.0 + mu) * vst
    hs_a = (h / s) ** (2.0 * (mu + 1.0))
    hs_b = (h / s) ** (2.0 * mu)

    a = phi * s * df * _norm_cdf(phi * x1) - phi * k * df * _norm_cdf(phi * x1 - phi * vst)
    b = phi * s * df * _norm_cdf(phi * x2) - phi * k * df * _norm_cdf(phi * x2 - phi * vst)
    c = phi * s * df * hs_a * _norm_cdf(eta * y1) - phi * k * df * hs_b * _norm_cdf(
        eta * y1 - eta * vst
    )
    d = phi * s * df * hs_a * _norm_cdf(eta * y2) - phi * k * df * hs_b * _norm_cdf(
        eta * y2 - eta * vst
    )
    above = strike >= barrier

    combos: dict[tuple[str, str], Callable[[], float]] = {
        ("call", "down_in"): lambda: c if above else a - b + d,
        ("call", "down_out"): lambda: (a - c) if above else (b - d),
        ("call", "up_in"): lambda: a if above else (b - c + d),
        ("call", "up_out"): lambda: 0.0 if above else (a - b + c - d),
        ("put", "down_in"): lambda: (b - c + d) if above else a,
        ("put", "down_out"): lambda: (a - b + c - d) if above else 0.0,
        ("put", "up_in"): lambda: (a - b + d) if above else c,
        ("put", "up_out"): lambda: (b - d) if above else (a - c),
    }
    return combos[(option_type, barrier_type)]()


# --- Lookback (Task 17) ----------------------------------------------------


def _lookback_tail(
    sign: float, s: float, level: float, sigma: float, time_to_expiry: float, discount_factor: float
) -> float:
    """``S*DF`` times the ``b -> 0`` limit of the Goldman-Sosin-Gatto / Conze tail term.

    The generalized floating- and fixed-strike lookback forms carry a ``sigma**2/(2b)`` factor
    that is singular at the forward-world carry ``b == 0``. Its finite limit (via L'Hopital in
    ``b``) is, with ``k = ln(S/level)`` and ``g0 = k/(sigma*sqrt(T)) + sigma*sqrt(T)/2``,

        call/minimum (``sign = +1``):  ``(k + sigma**2*T/2)*N(g0)  + sigma*sqrt(T)*n(g0)``
        put/maximum  (``sign = -1``):  ``-(k + sigma**2*T/2)*N(-g0) + sigma*sqrt(T)*n(g0)``.
    """
    vst = sigma * math.sqrt(time_to_expiry)
    k = math.log(s / level)
    g0 = k / vst + vst / 2.0
    drift = k + sigma**2 * time_to_expiry / 2.0
    if sign > 0.0:
        return s * discount_factor * (drift * _norm_cdf(g0) + vst * _norm_pdf(g0))
    return s * discount_factor * (-drift * _norm_cdf(-g0) + vst * _norm_pdf(g0))


def lookback_floating(
    option_type: Literal["call", "put"],
    forward: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Goldman-Sosin-Gatto floating-strike lookback (running extreme = forward at inception).

    A floating-strike lookback pays ``F_T - min_t F_t`` (call, struck at the running minimum) or
    ``max_t F_t - F_T`` (put, struck at the running maximum). At inception the running extreme
    equals the forward, so ``ln(F/extreme) = 0``; with the forward-world carry ``b == 0`` the two
    ``N(.)`` terms collapse to ``F*DF*(N(a) - N(-a))`` with ``a = sigma*sqrt(T)/2``, and the
    singular ``sigma**2/(2b)`` tail is replaced by its finite limit (:func:`_lookback_tail`).
    The value is strictly positive and dominates the corresponding vanilla premium.

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        The discounted floating-strike lookback premium.
    """
    alpha = sigma * math.sqrt(time_to_expiry) / 2.0
    base = forward * discount_factor * (_norm_cdf(alpha) - _norm_cdf(-alpha))
    # A call is struck at the running minimum (sign = -1), a put at the running maximum (+1).
    sign = -1.0 if option_type == "call" else 1.0
    return base + _lookback_tail(sign, forward, forward, sigma, time_to_expiry, discount_factor)


def lookback_fixed(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
) -> float:
    """Conze-Viswanathan fixed-strike lookback (running extreme = forward at inception).

    A fixed-strike lookback pays ``max(max_t F_t - K, 0)`` (call) or ``max(K - min_t F_t, 0)``
    (put). With the running extreme equal to the forward at inception and the forward-world carry
    ``b == 0``:

    - Call, ``K > F``: the two leading terms are exactly the vanilla Black-76 call, plus the
      finite tail :func:`_lookback_tail` struck at ``K``.
    - Call, ``K <= F``: ``max_t F_t >= F >= K`` so the payoff is ``(max_t F_t - F) + (F - K)`` —
      the discounted deterministic part ``DF*(F - K)`` plus a floating-strike lookback *put*
      (whose payoff is exactly ``max_t F_t - F_T`` and prices ``DF*(E[max_t F_t] - F)``).
    - Put mirrors the call about ``K = F`` (running minimum), reusing the floating-strike call.

    Args:
        option_type: ``"call"`` or ``"put"``.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        sigma: Volatility of the forward, per ``sqrt(year)``.
        time_to_expiry: Time to expiry in years (``T``).
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.

    Returns:
        The discounted fixed-strike lookback premium.
    """
    df = discount_factor
    if option_type == "call":
        if strike > forward:
            return black76_price(
                "call", forward, strike, sigma, time_to_expiry, df
            ) + _lookback_tail(1.0, forward, strike, sigma, time_to_expiry, df)
        return df * (forward - strike) + lookback_floating(
            "put", forward, sigma, time_to_expiry, df
        )
    if strike < forward:
        return black76_price("put", forward, strike, sigma, time_to_expiry, df) + _lookback_tail(
            -1.0, forward, strike, sigma, time_to_expiry, df
        )
    return df * (strike - forward) + lookback_floating("call", forward, sigma, time_to_expiry, df)
