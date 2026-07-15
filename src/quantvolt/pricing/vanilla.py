"""Vanilla options (calls, puts, caps, floors) — Black-76 (Task 27).

Thin orchestration over the pure :mod:`quantvolt.numerics.black76` kernel,
following the pricing skeleton *validate -> kernel -> package* (Reqs 5.4-5.6).
A cap/floor is the Composite intent: a strip of caplets/floorlets priced
independently, returning per-period **and** aggregate premium/Greeks
(Property 16). All real math lives in the kernel; this module only validates
typed requests and packages results.

Option-type mapping: a caplet *is* a call on the floating price and a floorlet
*is* a put, so ``"cap"`` prices through the ``"call"`` kernel branch and
``"floor"`` through ``"put"``. The mapping is a dispatch dict, not a
conditional chain (coding-style.md §4, Switch Statements).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from .._validation import require_discount_factor, require_non_empty, require_positive
from ..exceptions import ValidationError
from ..models.greeks import Greeks
from ..numerics.black76 import black76_greeks, black76_price


@dataclass(frozen=True, slots=True)
class VanillaOptionRequest:
    option_type: Literal["call", "put", "cap", "floor"]
    strike: float
    notional: float
    forward: float
    sigma: float
    time_to_expiry: float
    discount_factor: float


@dataclass(frozen=True, slots=True)
class VanillaOptionResult:
    premium: float
    greeks: Greeks


@dataclass(frozen=True, slots=True)
class CapFloorRequest:
    option_type: Literal["cap", "floor"]
    strike: float
    notional: float
    caplets: tuple[VanillaOptionRequest, ...]  # <= 120


@dataclass(frozen=True, slots=True)
class CapFloorResult:
    premium: float
    greeks: Greeks
    per_period: tuple[VanillaOptionResult, ...]


# A caplet is a call on the floating price; a floorlet is a put (Req 5.6).
_KERNEL_SIDE: Final[dict[str, Literal["call", "put"]]] = {
    "call": "call",
    "cap": "call",
    "put": "put",
    "floor": "put",
}

# Maximum caplets/floorlets in a cap/floor strip (Req 5.6).
_MAX_STRIP_PERIODS: Final[int] = 120


def price_vanilla_option(request: VanillaOptionRequest) -> VanillaOptionResult:
    """Price a single vanilla European option on a forward under Black-76.

    ``"cap"`` and ``"floor"`` requests denote a single caplet/floorlet and are
    priced as the equivalent call/put on the floating (forward) price. Premium
    and Greeks are per-unit kernel outputs scaled by ``notional``.

    Args:
        request: Fully specified option; all domains are validated eagerly
            before any computation (Req 5.4).

    Returns:
        The notional-scaled premium and Greeks.

    Raises:
        ValidationError: If ``forward``, ``strike``, ``sigma``,
            ``time_to_expiry`` or ``notional`` is not > 0, or
            ``discount_factor`` is outside ``(0, 1]``.
    """
    require_positive("forward", request.forward)
    require_positive("strike", request.strike)
    require_positive("sigma", request.sigma)
    require_positive("time_to_expiry", request.time_to_expiry)
    require_discount_factor("discount_factor", request.discount_factor)
    require_positive("notional", request.notional)

    side = _KERNEL_SIDE[request.option_type]
    premium = request.notional * black76_price(
        side,
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    )
    greeks = black76_greeks(
        side,
        request.forward,
        request.strike,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
    ).scale(request.notional)
    return VanillaOptionResult(premium=premium, greeks=greeks)


def price_cap_floor(
    request: CapFloorRequest, *, max_strip_periods: int = _MAX_STRIP_PERIODS
) -> CapFloorResult:
    """Price a cap/floor as a strip of independently priced caplets/floorlets.

    Composite intent (Req 5.6, Property 16): each period is priced through
    :func:`price_vanilla_option` with its own forward, volatility,
    time-to-expiry, discount factor and notional; the result carries both the
    per-period results and their plain sums (aggregate premium via ``sum``,
    aggregate Greeks via ``Greeks.__add__`` from ``Greeks.zero()``), so the
    aggregate equals the sum of the per-period values exactly.

    Consistency rule: each caplet's own ``option_type`` must price on the same
    call/put side as the strip — ``"call"``/``"cap"`` labels inside a ``"cap"``
    strip, ``"put"``/``"floor"`` inside a ``"floor"`` strip. A mismatched
    caplet is rejected with a :class:`ValidationError` rather than silently
    repriced as the strip side (fail loudly, coding-style.md §7).

    Strike/notional consistency (Req 5.6): a cap/floor strip has ONE strike
    (the cap/floor rate) and ONE notional; per Req 5.6 only ``forward``,
    ``discount_factor`` and ``time_to_expiry`` vary caplet-by-caplet. Every
    caplet's own ``strike`` and ``notional`` fields (each caplet is a full
    :class:`VanillaOptionRequest`, so it structurally carries them) must
    therefore equal ``request.strike`` / ``request.notional`` exactly; a
    divergent caplet is rejected with a :class:`ValidationError` naming the
    caplet index rather than silently pricing on its own (ignored) values.

    Args:
        request: The strip; validated eagerly — including the strip-length
            cap — before any pricing.
        max_strip_periods: Maximum number of caplets/floorlets in the strip,
            at least 1 (default 120, Req 5.6).

    Returns:
        Aggregate premium/Greeks plus the per-period results, ordered as the
        input caplets.

    Raises:
        ValidationError: If ``strike`` or ``notional`` is not > 0,
            ``max_strip_periods`` < 1, ``caplets`` is empty or exceeds
            ``max_strip_periods``, a caplet's ``option_type`` is on the wrong
            side for the strip, a caplet's ``strike``/``notional`` diverges
            from the strip's (naming the caplet index), or any caplet fails
            the :func:`price_vanilla_option` domain checks.
    """
    require_positive("strike", request.strike)
    require_positive("notional", request.notional)
    require_non_empty("caplets", request.caplets)
    if max_strip_periods < 1:
        raise ValidationError(f"max_strip_periods must be >= 1, got {max_strip_periods!r}")
    if len(request.caplets) > max_strip_periods:
        raise ValidationError(
            f"caplets must contain at most {max_strip_periods} caplets/floorlets "
            f"(Req 5.6), got {len(request.caplets)}"
        )
    strip_side = _KERNEL_SIDE[request.option_type]
    for index, caplet in enumerate(request.caplets):
        if _KERNEL_SIDE[caplet.option_type] != strip_side:
            raise ValidationError(
                f"caplets[{index}].option_type must price on the {strip_side!r} side "
                f"like the {request.option_type!r} strip, got {caplet.option_type!r}"
            )
        if caplet.strike != request.strike:
            raise ValidationError(
                f"caplets[{index}].strike ({caplet.strike!r}) must equal the strip's "
                f"strike ({request.strike!r}); a cap/floor strip prices every period "
                "at the same strike (Req 5.6)"
            )
        if caplet.notional != request.notional:
            raise ValidationError(
                f"caplets[{index}].notional ({caplet.notional!r}) must equal the "
                f"strip's notional ({request.notional!r}); a cap/floor strip prices "
                "every period at the same notional (Req 5.6)"
            )

    per_period = tuple(price_vanilla_option(caplet) for caplet in request.caplets)
    premium = sum(result.premium for result in per_period)
    greeks = Greeks.zero()
    for result in per_period:
        greeks = greeks + result.greeks
    return CapFloorResult(premium=premium, greeks=greeks, per_period=per_period)
