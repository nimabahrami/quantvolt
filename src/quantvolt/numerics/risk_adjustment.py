"""Price of risk / risk-adjustment kernels.

Pure scalar functions implementing the Chapter-10 risk-adjustment identities
(ASCII math notation matches the numerics/ house style; ``mu``, ``sigma``,
``lambda_s`` stand for the mu, sigma and lambda_S of the source text):

- :func:`price_of_risk` -- the price of risk ``lambda = (mu - r)/sigma`` (eq 10.4).
- :func:`tradable_price_of_risk` -- for a fully tradable underlying,
  ``lambda_S = (mu + y - r)/sigma`` with net convenience yield ``y`` (eq 10.6).
- :func:`risk_adjusted_drift` -- the drift of the risk-adjusted process
  ``dS*/S* = (mu - lambda_S*sigma)dt + sigma*dW``, i.e. ``mu - lambda_S*sigma`` (eq 10.5).

**Deviation from the numerics/ "float in, float out, no validation" house style.**
Sibling kernels (``black76.py``, ``daycount.py``) push all domain validation up to
their orchestration layer. This module is the sanctioned exception for this package:
Task 63 / Requirement 19 explicitly mandate that the ``sigma > 0`` guard, the
provenance vocabulary, and the physical-drift guard live *here* so that the
MC-VaR / CFaR risk engines (Tasks 66+) can reuse a single, tested definition --
mirroring how ``monte_carlo.py`` owns its own precondition guard. Validation
therefore goes through the shared :mod:`quantvolt._validation` helpers and raises
:class:`~quantvolt.exceptions.ValidationError`.

**Measure discipline.** ``PriceOfRiskKind`` (market vs corporate) is provenance
metadata that the *caller* states on the calling request and that this library
*never infers* -- the two are numerically identical adjustments but reflect
different sources of truth (traded quotes vs corporate risk policy; eq 10.4 text
and the "Market Price of Risk" section of Chapter 10). ``DriftKind`` tags whether
a drift lives under the physical measure P or the risk-neutral measure Q;
:func:`require_physical_drift` enforces that real-world risk measurement (VaR/CFaR)
is only ever fed a P-measure drift.
"""

from __future__ import annotations

from enum import StrEnum

from .._validation import require_positive
from ..exceptions import ValidationError


class PriceOfRiskKind(StrEnum):
    """Provenance of a price of risk lambda. Stated by the caller, never inferred.

    The two kinds produce the *same* risk-adjustment arithmetic (eqs 10.4 to 10.6);
    they differ only in where lambda comes from and therefore in how it may be used.
    """

    MARKET = "market"  # lambda_M implied from liquidly traded derivatives (eq 10.4)
    CORPORATE = "corporate"  # lambda set by the organisation's own risk policy / appetite


class DriftKind(StrEnum):
    """Probability measure a drift belongs to (used by the physical-drift guard)."""

    PHYSICAL = "physical"  # real-world P-measure drift mu (historical dynamics, VaR/CFaR)
    RISK_NEUTRAL = "risk_neutral"  # Q-measure drift (arbitrage-free valuation only)


def price_of_risk(mu: float, r: float, sigma: float) -> float:
    """Price of risk ``lambda = (mu - r)/sigma`` -- excess return per unit vol (eq 10.4).

    Args:
        mu: Drift of the underlying under the physical measure.
        r: Risk-free rate.
        sigma: Volatility of the underlying, strictly positive.

    Returns:
        The price of risk ``lambda``.

    Raises:
        ValidationError: If ``sigma`` is not strictly positive.
    """
    require_positive("sigma", sigma)
    return (mu - r) / sigma


def tradable_price_of_risk(mu: float, y: float, r: float, sigma: float) -> float:
    """Price of risk for a fully tradable underlying ``lambda_S = (mu + y - r)/sigma`` (eq 10.6).

    Adds the net convenience yield ``y`` (including storage costs) to the numerator.
    When the underlying is *not* fully hedgeable, lambda_S is instead a free,
    caller-supplied parameter and this function should not be used to derive it.

    Args:
        mu: Drift of the underlying under the physical measure.
        y: Net convenience yield including storage costs.
        r: Risk-free rate.
        sigma: Volatility of the underlying, strictly positive.

    Returns:
        The tradable price of risk ``lambda_S``.

    Raises:
        ValidationError: If ``sigma`` is not strictly positive.
    """
    require_positive("sigma", sigma)
    return (mu + y - r) / sigma


def risk_adjusted_drift(mu: float, lambda_s: float, sigma: float) -> float:
    """Risk-adjusted drift ``mu - lambda_S*sigma`` (eq 10.5).

    Drift term of the risk-adjusted process ``dS*/S* = (mu - lambda_S*sigma)dt + sigma*dW``.

    Args:
        mu: Drift of the underlying under the physical measure.
        lambda_s: Price of S risk ``lambda_S`` (from :func:`price_of_risk`,
            :func:`tradable_price_of_risk`, or a caller-supplied corporate value).
        sigma: Volatility of the underlying, strictly positive.

    Returns:
        The risk-adjusted drift. For a tradable underlying with
        ``lambda_S = (mu + y - r)/sigma`` this collapses to ``r - y``.

    Raises:
        ValidationError: If ``sigma`` is not strictly positive.
    """
    require_positive("sigma", sigma)
    return mu - lambda_s * sigma


def require_physical_drift(drift_kind: DriftKind, field_name: str = "drift") -> None:
    """Reject a risk-neutral drift where a physical (P-measure) drift is required.

    Reused by the MC-VaR / CFaR risk engines: real-world risk must evolve under the
    physical measure P, not the risk-neutral measure Q (Chapter-10 caveat), so a drift
    tagged :attr:`DriftKind.RISK_NEUTRAL` cannot be fed to a loss-distribution
    simulation. Accepts :attr:`DriftKind.PHYSICAL` silently.

    Args:
        drift_kind: The measure tag carried on the caller's drift.
        field_name: Name of the offending caller field, used in the error message.

    Raises:
        ValidationError: If ``drift_kind`` is not :attr:`DriftKind.PHYSICAL`, naming
            ``field_name`` and the physical-measure requirement.
    """
    if drift_kind != DriftKind.PHYSICAL:
        raise ValidationError(
            f"{field_name} must be tagged {DriftKind.PHYSICAL!r} (physical P-measure) "
            f"for real-world risk measurement (VaR/CFaR), got {drift_kind!r}; "
            f"risk must evolve under P, not the risk-neutral measure Q"
        )
