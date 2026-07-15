"""Implied volatility, moneyness, and vol-surface construction (Tasks 35-36).

Thin orchestration over the Black-76 kernel (design "Implied Volatility"): validate
eagerly at the boundary, invert the premium via Brent, and package typed results.

- :func:`implied_vol` re-implements the kernel inversion locally with
  :func:`~quantvolt.numerics.rootfind.brent_root` and a *call-counting objective*
  because :func:`~quantvolt.numerics.black76.black76_implied_vol` does not expose
  Brent's iteration count, and ``ImpliedVolResult.iteration_count`` must report one.
  The kernel's no-arbitrage precondition (a numeric ``ValueError`` in ``numerics/``)
  is raised here as :class:`~quantvolt.exceptions.ValidationError` naming
  ``market_premium`` and the bounds, because this is the public orchestration layer
  (Req 5.3; ``coding-style.md`` §7).
- :func:`classify_moneyness` classifies from the *call* perspective (Property 32).
- :func:`build_volatility_surface` builds the seasonal vol term structure; the
  interpolation method is selected via a dispatch dict (Strategy as functions).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from .._validation import (
    require_discount_factor,
    require_non_empty,
    require_non_negative,
    require_positive,
)
from ..exceptions import InsufficientDataError, ValidationError
from ..models.commodity import CommodityConfig
from ..models.schedule import DeliveryPeriod
from ..models.vol_surface import Moneyness, VolatilitySurface, VolatilityTenor
from ..numerics.black76 import black76_price
from ..numerics.interpolation import InterpolationMethod, cubic_spline, piecewise_linear
from ..numerics.rootfind import brent_root

if TYPE_CHECKING:
    import polars as pl

# Brent search bracket for the implied volatility, identical to the kernel's
# (numerics.black76.black76_implied_vol) so both inversions locate the same root.
_SIGMA_LOWER = 1e-9
_SIGMA_UPPER = 10.0

# Annualisation constant for daily realised volatility (design: sqrt(252)).
_TRADING_DAYS_PER_YEAR = 252

# Strategy selection for the surface term structure via dispatch dict (no if/elif;
# coding-style.md §2). Maps the public method names onto the numerics kernels.
_SURFACE_INTERPOLATION: dict[str, InterpolationMethod] = {
    "linear": piecewise_linear,
    "cubic_spline": cubic_spline,
}


@dataclass(frozen=True, slots=True)
class ImpliedVolResult:
    """Outcome of a premium inversion (design "Implied Volatility Calculator").

    ``iteration_count`` is the number of objective (Black-76 repricing) evaluations
    Brent performed, including the two bracket-endpoint evaluations — the closest
    observable proxy for the solver's iteration count. This matches
    :func:`scipy.optimize.brentq`'s own evaluation count exactly (verified by
    ``test_implied_vol.py::test_iteration_count_matches_scipy_brentq_call_count_exactly``):
    :func:`~quantvolt.numerics.rootfind.brent_root` no longer pre-evaluates the
    endpoints itself before delegating to ``brentq`` (which evaluates them again
    internally), a redundant pre-check that previously double-counted them and
    inflated this value by exactly 2. ``converged`` is ``True`` whenever a result is
    returned; non-convergence raises instead of returning a partial result (fail
    loudly, ``coding-style.md`` §7).
    """

    implied_vol: float
    moneyness: Moneyness
    iteration_count: int
    converged: bool


def implied_vol(
    option_type: Literal["call", "put"],
    market_premium: float,
    forward: float,
    strike: float,
    time_to_expiry: float,
    discount_factor: float,
    tol: float = 1e-4,
    max_iter: int = 100,
    *,
    sigma_lower: float = _SIGMA_LOWER,
    sigma_upper: float = _SIGMA_UPPER,
    tolerance_pct: float = 2.0,
) -> ImpliedVolResult:
    """Recover the Black-76 volatility implied by a market premium (Property 31).

    Round-trip contract (Property 31): ``implied_vol`` applied to
    ``black76_price(sigma0, ...)`` recovers ``sigma0`` within ``tol``. Inversion uses
    Brent over ``[sigma_lower, sigma_upper]`` (default ``[1e-9, 10.0]``) — a bracketing
    solver, so it cannot diverge near zero vega the way Newton-Raphson would (design
    §2.7). The inversion is performed locally with :func:`brent_root` and a
    call-counting objective (instead of delegating to
    :func:`~quantvolt.numerics.black76.black76_implied_vol`) so that
    :attr:`ImpliedVolResult.iteration_count` can be reported — the kernel does not
    expose its iteration count. Both use the same bracket, objective, and tolerance.

    No-arbitrage precondition (Req 5.3), checked before inversion:

    - call: ``DF*max(F-K, 0) < market_premium < DF*F``
    - put:  ``DF*max(K-F, 0) < market_premium < DF*K``

    Args:
        option_type: ``"call"`` or ``"put"``.
        market_premium: Observed (discounted) option premium to invert, positive.
        forward: Forward price of the underlying (``F``), positive.
        strike: Option strike (``K``), positive.
        time_to_expiry: Time to expiry in years (``T``), positive.
        discount_factor: Discount factor to settlement (``DF``), in ``(0, 1]``.
        tol: Absolute tolerance on the recovered volatility, positive.
        max_iter: Maximum Brent iterations, at least 1.
        sigma_lower: Lower end of the Brent search bracket, positive and strictly
            below ``sigma_upper`` (default ``1e-9``, matching the kernel's bracket).
        sigma_upper: Upper end of the Brent search bracket, strictly above
            ``sigma_lower`` (default ``10.0``).
        tolerance_pct: ATM band half-width (percent of the forward) passed through to
            :func:`classify_moneyness` for the reported moneyness (default 2.0).

    Returns:
        An :class:`ImpliedVolResult` with the recovered vol, the moneyness of the
        quote (at ``tolerance_pct``, default 2% ATM tolerance), the
        objective-evaluation count, and ``converged=True``.

    Raises:
        ValidationError: If any input violates its domain, or if ``market_premium``
            lies outside the no-arbitrage bounds (no volatility can reproduce it).
    """
    if option_type not in ("call", "put"):
        raise ValidationError(f"option_type must be 'call' or 'put', got {option_type!r}")
    require_positive("market_premium", market_premium)
    require_positive("forward", forward)
    require_positive("strike", strike)
    require_positive("time_to_expiry", time_to_expiry)
    require_discount_factor("discount_factor", discount_factor)
    require_positive("tol", tol)
    if max_iter < 1:
        raise ValidationError(f"max_iter must be >= 1, got {max_iter!r}")
    require_positive("sigma_lower", sigma_lower)
    if not sigma_upper > sigma_lower:
        raise ValidationError(
            f"sigma_upper must be > sigma_lower ({sigma_lower!r}), got {sigma_upper!r}"
        )
    require_non_negative("tolerance_pct", tolerance_pct)

    # No-arbitrage bounds (Req 5.3). The lower bound is the discounted intrinsic
    # value, which is exactly the kernel's sigma -> 0 premium; the upper bound is
    # the sigma -> inf limit. The kernel raises the built-in ValueError for this
    # numeric precondition — at this public boundary it is a ValidationError.
    lower = black76_price(option_type, forward, strike, 0.0, time_to_expiry, discount_factor)
    upper = discount_factor * (forward if option_type == "call" else strike)
    if not lower < market_premium < upper:
        raise ValidationError(
            f"market_premium must lie strictly inside the no-arbitrage bounds "
            f"({lower}, {upper}) for a {option_type}, got {market_premium!r}; "
            f"no volatility can reproduce it"
        )

    evaluations = 0

    def objective(sigma: float) -> float:
        nonlocal evaluations
        evaluations += 1
        return (
            black76_price(option_type, forward, strike, sigma, time_to_expiry, discount_factor)
            - market_premium
        )

    try:
        sigma = brent_root(objective, sigma_lower, sigma_upper, tol=tol, max_iter=max_iter)
    except ValueError as error:
        # In-bounds premium that still cannot be bracketed within the searchable
        # sigma range: translate the numeric ValueError at this public boundary.
        raise ValidationError(
            f"market_premium {market_premium!r} cannot be reproduced by any volatility "
            f"in [{sigma_lower}, {sigma_upper}]: {error}"
        ) from error

    return ImpliedVolResult(
        implied_vol=sigma,
        moneyness=classify_moneyness(strike, forward, tolerance_pct=tolerance_pct),
        iteration_count=evaluations,
        converged=True,
    )


def classify_moneyness(strike: float, forward: float, tolerance_pct: float = 2.0) -> Moneyness:
    """Classify option moneyness relative to the forward price (Property 32).

    Classification is from the **call perspective**: a strike above the forward has
    no intrinsic value for a call (OTM); a strike below the forward is ITM. The put
    classification is the mirror image, so callers holding puts should swap
    ITM/OTM. Deviations of at most ``tolerance_pct`` percent of the forward — the
    boundary is *inclusive* — classify as ATM:

    - ``|strike - forward| / forward * 100 <= tolerance_pct`` -> ATM
    - ``strike > forward * (1 + tolerance_pct/100)`` -> OTM
    - ``strike < forward * (1 - tolerance_pct/100)`` -> ITM

    Args:
        strike: Option strike (``K``), positive.
        forward: Forward price of the underlying (``F``), positive.
        tolerance_pct: ATM band half-width as a percentage of the forward,
            non-negative (default 2.0 = within 2% of the forward).

    Returns:
        Exactly one of :class:`Moneyness` ``ATM`` / ``OTM`` / ``ITM``.

    Raises:
        ValidationError: If ``strike`` or ``forward`` is not positive, or
            ``tolerance_pct`` is negative.
    """
    require_positive("strike", strike)
    require_positive("forward", forward)
    require_non_negative("tolerance_pct", tolerance_pct)
    deviation_pct = abs(strike - forward) * 100.0 / forward
    if deviation_pct <= tolerance_pct:
        return Moneyness.ATM
    if strike > forward:
        return Moneyness.OTM
    return Moneyness.ITM


def cumulative_historical_vol(
    price_series: pl.Series, window: int = 252, *, periods_per_year: int = _TRADING_DAYS_PER_YEAR
) -> pl.Series:
    """Rolling annualised realised volatility of log returns (implied-vs-realised).

    Computes ``log(P_t / P_{t-1})`` via Polars, then
    ``rolling_std(window) * sqrt(periods_per_year)``. The output has the same length
    as the input; the warm-up (the first ``window`` entries: one for the return
    differencing plus ``window - 1`` for the rolling window) is null.

    Args:
        price_series: Strictly positive price observations, length > ``window``.
        window: Rolling window length in observations, at least 2 (default 252,
            one trading year).
        periods_per_year: Annualisation factor under the square-root-of-time rule,
            at least 1 (default 252, trading days per year).

    Returns:
        A ``pl.Series`` of annualised realised vols with leading nulls for the
        warm-up. The input series is never mutated.

    Raises:
        ValidationError: If ``window < 2``, ``periods_per_year < 1``, or any price
            is not strictly positive.
        InsufficientDataError: If ``price_series`` has fewer than ``window + 1``
            observations (no full rolling window of returns exists).
    """
    import polars as pl  # runtime import: polars is only needed by this entry point

    if window < 2:
        raise ValidationError(f"window must be >= 2, got {window!r}")
    if periods_per_year < 1:
        raise ValidationError(f"periods_per_year must be >= 1, got {periods_per_year!r}")
    if len(price_series) <= window:
        raise InsufficientDataError(
            f"price_series must have more than window={window} observations to "
            f"produce a rolling value, got {len(price_series)}"
        )
    prices = price_series.cast(pl.Float64)
    if bool((prices <= 0.0).any()):
        raise ValidationError(
            "price_series must be strictly positive to take log returns; found a value <= 0"
        )
    log_returns = prices.log().diff()
    return log_returns.rolling_std(window_size=window) * math.sqrt(periods_per_year)


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """One observed option quote used to build a volatility surface (design
    "Volatility Surface Builder"). A plain immutable carrier: every field is
    validated at the :func:`implied_vol` boundary when the quote is inverted."""

    period: DeliveryPeriod
    strike: float
    premium: float
    forward: float
    option_type: Literal["call", "put"]
    time_to_expiry: float
    discount_factor: float


def _month_index(period: DeliveryPeriod) -> int:
    """Monotone month counter (year*12 + month-1): the surface's numeric time axis."""
    return period.year * 12 + (period.month - 1)


def _monthly_grid(start: DeliveryPeriod, end: DeliveryPeriod) -> list[DeliveryPeriod]:
    """Every calendar month from ``start`` to ``end`` inclusive, in order."""
    return [
        DeliveryPeriod(year=index // 12, month=index % 12 + 1)
        for index in range(_month_index(start), _month_index(end) + 1)
    ]


def build_volatility_surface(
    option_quotes: list[OptionQuote],
    interpolation: Literal["linear", "cubic_spline"] = "linear",
    extrapolate: bool = False,
    *,
    commodity: CommodityConfig,
) -> VolatilitySurface:
    """Build an implied-volatility surface from option quotes (Task 36).

    Every quote is inverted through :func:`implied_vol` (so every quote is fully
    validated — a bad quote fails loudly rather than being dropped). Because
    :class:`~quantvolt.models.vol_surface.VolatilitySurface` holds **one sigma per
    period tenor** (a term structure), multiple strikes quoted for the same period
    are aggregated to the *ATM-nearest* quote's vol: the quote whose strike is
    closest to its forward (relative distance; first quote wins a tie). This
    anchors each tenor at the most liquid, smile-neutral point; the smile across
    strikes is thereby collapsed by nearest-ATM selection.

    Calendar months missing between the first and last quoted period are filled by
    interpolating the vol term structure on a monotone month axis with the selected
    method; quoted periods keep their exactly inverted vols. With
    ``extrapolate=False`` the surface covers only ``[first, last]`` quoted period.

    ``commodity`` is required and keyword-only: the stub signature carried no
    commodity, but :class:`VolatilitySurface` requires one, and guessing a default
    would silently mislabel the surface — an additive keyword parameter completes
    the stub without breaking positional callers.

    Args:
        option_quotes: Non-empty list of :class:`OptionQuote` observations.
        interpolation: ``"linear"`` (piecewise linear) or ``"cubic_spline"``
            (natural cubic spline), selected via a dispatch dict.
        extrapolate: Must be ``False``; extrapolation beyond the quoted period
            range is not supported (there is no principled extension target).
        commodity: The commodity the surface belongs to (keyword-only, required).

    Returns:
        A :class:`VolatilitySurface` with one tenor per calendar month from the
        first to the last quoted period, inclusive. Inputs are never mutated.

    Raises:
        ValidationError: If ``option_quotes`` is empty, ``interpolation`` is
            unknown, ``extrapolate`` is ``True``, or any quote fails the
            :func:`implied_vol` domain / no-arbitrage checks.
    """
    require_non_empty("option_quotes", option_quotes)
    if interpolation not in _SURFACE_INTERPOLATION:
        raise ValidationError(
            f"interpolation must be one of {sorted(_SURFACE_INTERPOLATION)}, got {interpolation!r}"
        )
    if extrapolate:
        raise ValidationError(
            "extrapolate must be False: the surface covers only the quoted period "
            "range [first, last], got extrapolate=True"
        )

    # Invert every quote (full boundary validation per quote), then keep, per
    # period, the vol of the ATM-nearest quote (see docstring).
    atm_nearest: dict[DeliveryPeriod, tuple[float, float]] = {}  # period -> (distance, vol)
    for quote in option_quotes:
        vol = implied_vol(
            quote.option_type,
            quote.premium,
            quote.forward,
            quote.strike,
            quote.time_to_expiry,
            quote.discount_factor,
        ).implied_vol
        distance = abs(quote.strike - quote.forward) / quote.forward
        best = atm_nearest.get(quote.period)
        if best is None or distance < best[0]:
            atm_nearest[quote.period] = (distance, vol)

    quoted_periods = sorted(atm_nearest)
    vols: dict[DeliveryPeriod, float] = {
        period: atm_nearest[period][1] for period in quoted_periods
    }

    grid = _monthly_grid(quoted_periods[0], quoted_periods[-1])
    missing = [period for period in grid if period not in vols]
    if missing:
        knot_times = np.array([_month_index(p) for p in quoted_periods], dtype=np.float64)
        knot_vols = np.array([vols[p] for p in quoted_periods], dtype=np.float64)
        query_times = np.array([_month_index(p) for p in missing], dtype=np.float64)
        filled = _SURFACE_INTERPOLATION[interpolation](knot_times, knot_vols, query_times)
        for position, period in enumerate(missing):
            vols[period] = float(filled[position])

    tenors = tuple(VolatilityTenor(period=period, sigma=vols[period]) for period in grid)
    return VolatilitySurface(commodity=commodity, tenors=tenors)
