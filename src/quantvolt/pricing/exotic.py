"""Exotic options — Asian, barrier, lookback (Tasks 28-29).

Option *type* is an attribute of the request; closed-form kernels live in
``numerics.exotic``, Monte Carlo in ``numerics.monte_carlo``. This module is thin
orchestration on the pricing skeleton *validate -> kernel -> package*: every public
entry point validates its request eagerly — before any computation, each error naming
the offending parameter and the violated constraint (Req 6.4, Task 29) — then hands
off to a pure numeric kernel and packages an :class:`ExoticOptionResult`.

Method selection is dispatch dicts / Simple Factories, never conditional chains
(coding-style.md §4, Switch Statements):

- Asian (Req 6.1): ``turnbull_wakeman`` by default for arithmetic averaging,
  ``kemna_vorst`` by default for geometric, ``monte_carlo`` only on explicit request —
  and then only with an explicit ``seed`` (determinism) and ``path_count >= 1000``.
- Lookback (Req 6.3): floating strike -> Goldman-Sosin-Gatto, fixed strike ->
  Conze-Viswanathan.

Greeks for the closed forms are central finite differences of the *selected* kernel
(:func:`~quantvolt.numerics.rootfind.finite_difference_bump`), under the Black-76 sign
conventions of :func:`~quantvolt.numerics.black76.black76_greeks`:

- ``delta``/``gamma``: forward bumped by ``1e-4 * forward``;
- ``vega``: sigma bumped by ``1e-4`` (capped at ``sigma / 2`` so the bumped vol stays
  positive);
- ``theta = -d(price)/dT`` with ``T`` bumped by ``1e-6`` (capped at ``T / 2``) at a
  fixed short rate ``r = -ln(DF)/T`` — the discount factor is rebuilt as
  ``exp(-r * T')`` under the bump, matching the ``black76_greeks`` theta convention;
- ``rho = -T * premium`` exactly: every kernel premium here is proportional to ``DF``,
  so ``d(price)/dr`` at a fixed forward with ``DF = e^{-rT}`` is ``-T * price`` — the
  same convention as ``black76_greeks``.

The Monte Carlo path returns ``standard_error`` from the native kernel and
``Greeks.zero()``: pathwise MC Greeks arrive with the Rust engine (Task 59).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Final, Literal

from .._validation import require_discount_factor, require_positive
from ..exceptions import ValidationError
from ..models.greeks import Greeks
from ..numerics.exotic import (
    barrier_analytic,
    kemna_vorst,
    lookback_fixed,
    lookback_floating,
    turnbull_wakeman,
)
from ..numerics.monte_carlo import asian_monte_carlo
from ..numerics.rootfind import finite_difference_bump


@dataclass(frozen=True, slots=True)
class AsianOptionRequest:
    option_type: Literal["call", "put"]
    averaging: Literal["arithmetic", "geometric"]
    strike: float
    forward: float
    sigma: float
    time_to_expiry: float
    discount_factor: float
    method: Literal["turnbull_wakeman", "kemna_vorst", "monte_carlo"] | None = None
    seed: int | None = None
    path_count: int = 10_000


@dataclass(frozen=True, slots=True)
class BarrierOptionRequest:
    option_type: Literal["call", "put"]
    barrier_type: Literal["up_in", "up_out", "down_in", "down_out"]
    strike: float
    barrier: float
    forward: float
    sigma: float
    time_to_expiry: float
    discount_factor: float


@dataclass(frozen=True, slots=True)
class LookbackOptionRequest:
    option_type: Literal["call", "put"]
    strike_type: Literal["floating", "fixed"]
    forward: float
    sigma: float
    time_to_expiry: float
    discount_factor: float
    strike: float | None = None


@dataclass(frozen=True, slots=True)
class ExoticOptionResult:
    premium: float
    greeks: Greeks
    standard_error: float | None = None


_AsianMethod = Literal["turnbull_wakeman", "kemna_vorst", "monte_carlo"]
_Averaging = Literal["arithmetic", "geometric"]

# Closed-form Asian kernel: (forward, strike, sigma, time_to_expiry, DF, option_type).
_AsianKernel = Callable[[float, float, float, float, float, Literal["call", "put"]], float]

# A pricer-specific premium closure: (forward, sigma, time_to_expiry, DF) -> premium.
# The finite-difference Greeks bump exactly these four market inputs.
_PremiumFn = Callable[[float, float, float, float], float]

# Central-difference bump sizes (module docstring documents the conventions).
_FORWARD_BUMP_FRACTION: Final[float] = 1e-4
_VOL_BUMP: Final[float] = 1e-4
_TIME_BUMP: Final[float] = 1e-6

# Monte Carlo floor (Req 6.4) and the fixing-schedule convention: the request carries no
# explicit averaging schedule, so MC uses daily fixings over one trading year — 252
# points, the Req 6.5 benchmark schedule size.
_MIN_MC_PATH_COUNT: Final[int] = 1000
_MC_AVERAGING_POINTS: Final[int] = 252

# Simple Factory (Req 6.1): default closed form per averaging type.
_DEFAULT_ASIAN_METHOD: Final[dict[_Averaging, _AsianMethod]] = {
    "arithmetic": "turnbull_wakeman",
    "geometric": "kemna_vorst",
}

# Each closed form prices exactly one averaging type; monte_carlo handles both.
_CLOSED_FORM_AVERAGING: Final[dict[_AsianMethod, _Averaging]] = {
    "turnbull_wakeman": "arithmetic",
    "kemna_vorst": "geometric",
}


def _validate_market_domains(
    forward: float, sigma: float, time_to_expiry: float, discount_factor: float
) -> None:
    """Domain checks shared by all three exotics (Req 6.4), before any computation."""
    require_positive("forward", forward)
    require_positive("sigma", sigma)
    require_positive("time_to_expiry", time_to_expiry)
    require_discount_factor("discount_factor", discount_factor)


def _validate_bumps(forward_bump_fraction: float, vol_bump: float, time_bump: float) -> None:
    """Shared finite-difference bump validation for the three public pricers."""
    require_positive("forward_bump_fraction", forward_bump_fraction)
    require_positive("vol_bump", vol_bump)
    require_positive("time_bump", time_bump)


def _closed_form_greeks(
    premium_fn: _PremiumFn,
    premium: float,
    forward: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    forward_bump_fraction: float,
    vol_bump: float,
    time_bump: float,
) -> Greeks:
    """Central finite-difference Greeks of a closed-form premium (module docstring)."""
    rate = -math.log(discount_factor) / time_to_expiry

    def value(bumped_forward: float, bumped_sigma: float, bumped_expiry: float) -> float:
        return premium_fn(
            bumped_forward, bumped_sigma, bumped_expiry, math.exp(-rate * bumped_expiry)
        )

    forward_bump = forward_bump_fraction * forward
    vol_bump = min(vol_bump, 0.5 * sigma)
    time_bump = min(time_bump, 0.5 * time_to_expiry)
    # Delta and gamma share the same forward +/- bump evaluations (one kernel call each,
    # not two); gamma's base term reuses the already-computed `premium` instead of
    # re-evaluating the kernel at the unbumped inputs.
    forward_up = value(forward + forward_bump, sigma, time_to_expiry)
    forward_down = value(forward - forward_bump, sigma, time_to_expiry)
    delta = (forward_up - forward_down) / (2.0 * forward_bump)
    gamma = (forward_up - 2.0 * premium + forward_down) / forward_bump**2
    return Greeks(
        delta=delta,
        gamma=gamma,
        vega=finite_difference_bump(lambda s: value(forward, s, time_to_expiry), sigma, vol_bump),
        theta=-finite_difference_bump(
            lambda t: value(forward, sigma, t), time_to_expiry, time_bump
        ),
        rho=-time_to_expiry * premium,
    )


def _package_closed_form(
    premium_fn: _PremiumFn,
    forward: float,
    sigma: float,
    time_to_expiry: float,
    discount_factor: float,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    time_bump: float = _TIME_BUMP,
) -> ExoticOptionResult:
    """Shared *kernel -> package* tail: premium at the request inputs, FD Greeks, no SE."""
    premium = premium_fn(forward, sigma, time_to_expiry, discount_factor)
    greeks = _closed_form_greeks(
        premium_fn,
        premium,
        forward,
        sigma,
        time_to_expiry,
        discount_factor,
        forward_bump_fraction,
        vol_bump,
        time_bump,
    )
    return ExoticOptionResult(premium=premium, greeks=greeks, standard_error=None)


# --- Asian (Reqs 6.1, 6.4, 6.5) ---------------------------------------------


def _price_asian_closed_form(
    kernel: _AsianKernel,
    request: AsianOptionRequest,
    forward_bump_fraction: float,
    vol_bump: float,
    time_bump: float,
    averaging_points: int,
) -> ExoticOptionResult:
    del averaging_points  # closed forms are schedule-free (continuous averaging)

    def premium_fn(
        forward: float, sigma: float, time_to_expiry: float, discount_factor: float
    ) -> float:
        return kernel(
            forward, request.strike, sigma, time_to_expiry, discount_factor, request.option_type
        )

    return _package_closed_form(
        premium_fn,
        request.forward,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
        forward_bump_fraction,
        vol_bump,
        time_bump,
    )


def _price_asian_monte_carlo(
    request: AsianOptionRequest,
    forward_bump_fraction: float,
    vol_bump: float,
    time_bump: float,
    averaging_points: int,
) -> ExoticOptionResult:
    """MC path: validate the MC-only preconditions, then call the native kernel.

    ``seed`` and ``path_count`` are checked here — still before any computation — so
    the requirements bind exactly when ``method="monte_carlo"`` is selected. Greeks are
    ``Greeks.zero()`` until the Rust engine lands (Task 59, which also unblocks
    ``asian_monte_carlo`` itself); ``standard_error`` comes from the kernel tuple.
    """
    del forward_bump_fraction, vol_bump, time_bump  # MC returns Greeks.zero(), no FD bumps used
    if request.seed is None:
        raise ValidationError(
            "seed is required (must not be None) for method='monte_carlo' — an explicit "
            "seed keeps the simulation deterministic"
        )
    if request.path_count < _MIN_MC_PATH_COUNT:
        raise ValidationError(
            f"path_count must be >= {_MIN_MC_PATH_COUNT} for method='monte_carlo', "
            f"got {request.path_count!r}"
        )
    premium, standard_error = asian_monte_carlo(
        forward=request.forward,
        strike=request.strike,
        sigma=request.sigma,
        time_to_expiry=request.time_to_expiry,
        discount_factor=request.discount_factor,
        averaging_points=averaging_points,
        option_type=request.option_type,
        geometric=request.averaging == "geometric",
        seed=request.seed,
        path_count=request.path_count,
    )
    return ExoticOptionResult(premium=premium, greeks=Greeks.zero(), standard_error=standard_error)


_AsianPricer = Callable[[AsianOptionRequest, float, float, float, int], ExoticOptionResult]

_ASIAN_PRICERS: Final[dict[_AsianMethod, _AsianPricer]] = {
    "turnbull_wakeman": partial(_price_asian_closed_form, turnbull_wakeman),
    "kemna_vorst": partial(_price_asian_closed_form, kemna_vorst),
    "monte_carlo": _price_asian_monte_carlo,
}


def price_asian(
    request: AsianOptionRequest,
    *,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    time_bump: float = _TIME_BUMP,
    averaging_points: int = _MC_AVERAGING_POINTS,
) -> ExoticOptionResult:
    """Price an average-price Asian option on a forward (Req 6.1).

    Method dispatch (Simple Factory): ``request.method`` if given, otherwise the
    averaging-type default — Turnbull-Wakeman for ``"arithmetic"``, Kemna-Vorst for
    ``"geometric"``. Each closed form prices exactly one averaging type, so an explicit
    method that contradicts ``request.averaging`` is rejected rather than silently
    repriced (fail loudly, coding-style.md §7). ``"monte_carlo"`` must be requested
    explicitly and additionally requires ``seed`` and ``path_count >= 1000``.

    Closed forms return central finite-difference Greeks of the selected kernel; the
    Monte Carlo path returns ``Greeks.zero()`` (MC Greeks arrive with the Rust engine,
    Task 59) plus the kernel's ``standard_error``.

    Args:
        request: Fully specified Asian option; validated eagerly before any
            computation (Req 6.4).
        forward_bump_fraction: Relative forward bump used for the closed-form
            delta/gamma finite differences, positive (default ``1e-4``). Unused
            for ``method="monte_carlo"``.
        vol_bump: Absolute vol bump for the closed-form vega finite difference,
            positive (default ``1e-4``). Unused for ``method="monte_carlo"``.
        time_bump: Absolute time bump for the closed-form theta finite
            difference, positive (default ``1e-6``). Unused for
            ``method="monte_carlo"``.
        averaging_points: Number of discrete fixings in the Monte Carlo averaging
            schedule, at least 1 (default 252, one trading year of daily
            fixings). Unused for the closed forms (continuous averaging).

    Returns:
        Premium, Greeks, and — for Monte Carlo only — the standard error.

    Raises:
        ValidationError: If ``forward``, ``strike``, ``sigma`` or ``time_to_expiry``
            is not > 0, ``discount_factor`` is outside ``(0, 1]``, ``method``
            contradicts ``averaging``, ``forward_bump_fraction``/``vol_bump``/
            ``time_bump`` is not > 0, ``averaging_points`` < 1, or — for
            ``method="monte_carlo"`` — ``seed`` is missing or ``path_count`` < 1000.
        NativeExtensionError: If ``method="monte_carlo"`` is requested without a
            built native Rust extension.
    """
    _validate_market_domains(
        request.forward, request.sigma, request.time_to_expiry, request.discount_factor
    )
    require_positive("strike", request.strike)
    _validate_bumps(forward_bump_fraction, vol_bump, time_bump)
    if averaging_points < 1:
        raise ValidationError(f"averaging_points must be >= 1, got {averaging_points!r}")
    method: _AsianMethod = request.method or _DEFAULT_ASIAN_METHOD[request.averaging]
    closed_form_averaging = _CLOSED_FORM_AVERAGING.get(method)
    if closed_form_averaging is not None and closed_form_averaging != request.averaging:
        raise ValidationError(
            f"method {method!r} is the {closed_form_averaging}-averaging closed form and "
            f"cannot price averaging={request.averaging!r}; use "
            f"method={_DEFAULT_ASIAN_METHOD[request.averaging]!r} or method='monte_carlo'"
        )
    return _ASIAN_PRICERS[method](
        request, forward_bump_fraction, vol_bump, time_bump, averaging_points
    )


# --- Barrier (Reqs 6.2, 6.4; Property 17) ------------------------------------


def price_barrier(
    request: BarrierOptionRequest,
    *,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    time_bump: float = _TIME_BUMP,
) -> ExoticOptionResult:
    """Price a single-barrier option via the Reiner-Rubinstein closed form (Req 6.2).

    Barrier-vs-forward consistency (Property 17): an *up* barrier must sit strictly
    above the forward and a *down* barrier strictly below — a barrier on the wrong
    side (or exactly at the forward) is already breached at inception and is rejected
    before any computation. Greeks are central finite differences of the barrier
    kernel.

    Args:
        request: Fully specified barrier option; validated eagerly before any
            computation (Req 6.4).
        forward_bump_fraction: Relative forward bump for delta/gamma, positive
            (default ``1e-4``).
        vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).
        time_bump: Absolute time bump for theta, positive (default ``1e-6``).

    Returns:
        Premium and Greeks (``standard_error`` is ``None`` for closed forms).

    Raises:
        ValidationError: If ``forward``, ``strike``, ``barrier``, ``sigma`` or
            ``time_to_expiry`` is not > 0, ``discount_factor`` is outside ``(0, 1]``,
            ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, or
            ``barrier`` is on the wrong side of ``forward`` for ``barrier_type``.
    """
    _validate_market_domains(
        request.forward, request.sigma, request.time_to_expiry, request.discount_factor
    )
    require_positive("strike", request.strike)
    require_positive("barrier", request.barrier)
    _validate_bumps(forward_bump_fraction, vol_bump, time_bump)
    if request.barrier_type.startswith("up"):
        if not request.barrier > request.forward:
            raise ValidationError(
                f"barrier must be > forward for barrier_type={request.barrier_type!r} "
                f"(an up barrier knocks at a level above the forward), got "
                f"barrier={request.barrier!r} and forward={request.forward!r}"
            )
    elif not request.barrier < request.forward:
        raise ValidationError(
            f"barrier must be < forward for barrier_type={request.barrier_type!r} "
            f"(a down barrier knocks at a level below the forward), got "
            f"barrier={request.barrier!r} and forward={request.forward!r}"
        )

    def premium_fn(
        forward: float, sigma: float, time_to_expiry: float, discount_factor: float
    ) -> float:
        return barrier_analytic(
            request.option_type,
            request.barrier_type,
            forward,
            request.strike,
            request.barrier,
            sigma,
            time_to_expiry,
            discount_factor,
        )

    return _package_closed_form(
        premium_fn,
        request.forward,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
        forward_bump_fraction,
        vol_bump,
        time_bump,
    )


# --- Lookback (Reqs 6.3, 6.4) -------------------------------------------------


def _floating_lookback_premium(request: LookbackOptionRequest) -> _PremiumFn:
    """Goldman-Sosin-Gatto: no fixed strike — a supplied ``strike`` is rejected."""
    if request.strike is not None:
        raise ValidationError(
            f"strike must be None for strike_type='floating' — a floating-strike "
            f"lookback is struck at the running extreme, not at a fixed strike; got "
            f"strike={request.strike!r}"
        )

    def premium_fn(
        forward: float, sigma: float, time_to_expiry: float, discount_factor: float
    ) -> float:
        return lookback_floating(
            request.option_type, forward, sigma, time_to_expiry, discount_factor
        )

    return premium_fn


def _fixed_lookback_premium(request: LookbackOptionRequest) -> _PremiumFn:
    """Conze-Viswanathan: requires a positive fixed ``strike`` (Req 6.4)."""
    if request.strike is None:
        raise ValidationError(
            "strike is required (must not be None) for strike_type='fixed' — a "
            "fixed-strike lookback pays off against an explicit strike"
        )
    strike = request.strike
    require_positive("strike", strike)

    def premium_fn(
        forward: float, sigma: float, time_to_expiry: float, discount_factor: float
    ) -> float:
        return lookback_fixed(
            request.option_type, forward, strike, sigma, time_to_expiry, discount_factor
        )

    return premium_fn


# Strategy dispatch (Req 6.3): each factory validates the strike/strike_type pairing,
# then returns the kernel closure — floating -> GSG, fixed -> Conze-Viswanathan.
_LOOKBACK_PREMIUMS: Final[dict[str, Callable[[LookbackOptionRequest], _PremiumFn]]] = {
    "floating": _floating_lookback_premium,
    "fixed": _fixed_lookback_premium,
}


def price_lookback(
    request: LookbackOptionRequest,
    *,
    forward_bump_fraction: float = _FORWARD_BUMP_FRACTION,
    vol_bump: float = _VOL_BUMP,
    time_bump: float = _TIME_BUMP,
) -> ExoticOptionResult:
    """Price a lookback option on a forward (Req 6.3).

    Strike-type dispatch: ``"floating"`` prices via Goldman-Sosin-Gatto and must carry
    ``strike=None`` (the strike *is* the running extreme); ``"fixed"`` prices via
    Conze-Viswanathan and requires a positive ``strike``. Greeks are central finite
    differences of the selected kernel.

    Args:
        request: Fully specified lookback option; validated eagerly before any
            computation (Req 6.4).
        forward_bump_fraction: Relative forward bump for delta/gamma, positive
            (default ``1e-4``).
        vol_bump: Absolute vol bump for vega, positive (default ``1e-4``).
        time_bump: Absolute time bump for theta, positive (default ``1e-6``).

    Returns:
        Premium and Greeks (``standard_error`` is ``None`` for closed forms).

    Raises:
        ValidationError: If ``forward``, ``sigma`` or ``time_to_expiry`` is not > 0,
            ``discount_factor`` is outside ``(0, 1]``,
            ``forward_bump_fraction``/``vol_bump``/``time_bump`` is not > 0, a
            floating-strike request carries a ``strike``, or a fixed-strike request
            is missing a positive ``strike``.
    """
    _validate_market_domains(
        request.forward, request.sigma, request.time_to_expiry, request.discount_factor
    )
    _validate_bumps(forward_bump_fraction, vol_bump, time_bump)
    premium_fn = _LOOKBACK_PREMIUMS[request.strike_type](request)
    return _package_closed_form(
        premium_fn,
        request.forward,
        request.sigma,
        request.time_to_expiry,
        request.discount_factor,
        forward_bump_fraction,
        vol_bump,
        time_bump,
    )
