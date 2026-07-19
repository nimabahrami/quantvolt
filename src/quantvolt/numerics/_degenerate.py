"""Shared degenerate-limit Greeks helper (numerics-internal).

``black76.py``'s ``_black76_greeks_degenerate`` and ``bachelier.py``'s
``_bachelier_greeks_degenerate`` each computed the ``sigma*sqrt(T) == 0`` limit of their
model's Greeks with byte-identical delta-step / theta-carry / rho arithmetic; only the
price line differed (``black76_price(...)`` vs. ``bachelier_price(...)``), and that price
line itself collapses to the same discounted intrinsic value in this limit. This module is
the single shared implementation both kernels delegate to (Dispensables / Duplicate Code,
``coding-style.md`` §4), following the precedent of ``_normal.py`` (the previous dedup of
this kind for the shared standard-normal CDF/PDF helpers).

The discounted intrinsic is computed **inline** here rather than by calling either model's
price kernel, so this module has no dependency on ``black76.py`` or ``bachelier.py`` (both
of those modules import *this* one; the reverse would be a cycle).
"""

from __future__ import annotations

import math
from typing import Literal

from ..models.greeks import Greeks


def _degenerate_greeks(
    option_type: Literal["call", "put"],
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
) -> Greeks:
    """The ``sigma*sqrt(T) == 0`` (or ``sigma_N*sqrt(T) == 0``) limit shared by Black-76
    and Bachelier Greeks.

    The forward is deterministic in this limit, so the price is the discounted intrinsic
    value and every diffusion-driven sensitivity (``gamma``, ``vega``) vanishes.

    - ``delta``: the limit of ``DF*N(d) `` (call) / ``DF*(N(d)-1)`` (put) as the total
      standard deviation ``-> 0`` with ``F != K`` is a step at the strike: ``DF*1{F>K}``
      (call), ``-DF*1{F<K}`` (put). At the ``F == K`` boundary this instead takes the
      *continuous* limit reached by holding ``F == K`` fixed and letting the total standard
      deviation ``-> 0+`` in the full formula (``d -> 0``, ``N(0) = 0.5``): ``delta = DF/2``
      (call), ``delta = -DF/2`` (put). This is a convention choice, not the unique limit.
    - ``gamma`` = ``vega`` = 0 by the same convention: the true limits are direction-dependent
      (and, for ``gamma`` at ``F == K``, divergent), so both are defined to be exactly ``0``.
    - ``theta``: the surviving *carry* term, ``rate*price`` with ``rate = -ln(DF)/T`` — the
      vega-driven term vanishes in this limit. At ``T == 0`` ``rate`` is undefined (``0/0``),
      so the carry contribution is defined to be exactly ``0`` there.
    - ``rho`` = ``-T*price``, unchanged from the non-degenerate branch's formula.

    See ``black76.py::_black76_greeks_degenerate`` and
    ``bachelier.py::_bachelier_greeks_degenerate`` for the model-specific framing of each
    of these points.
    """
    if option_type == "call":
        price = discount_factor * max(forward - strike, 0.0)
    else:
        price = discount_factor * max(strike - forward, 0.0)
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
