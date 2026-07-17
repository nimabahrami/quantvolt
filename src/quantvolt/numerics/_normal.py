"""Shared standard-normal CDF helper (numerics-internal).

``black76.py`` and ``exotic.py`` both price European options via the standard normal
distribution and previously each defined an identical ``scipy.stats.norm``-backed
``_norm_cdf``/``_norm_pdf`` pair; this module is the single shared implementation
both import (Dispensables / Duplicate Code, ``coding-style.md`` §4).

``spread_models.py`` also imports :func:`norm_cdf` from here (its own former
``math.erf``-based implementation agreed with this one to within 1 ULP across the
module's test coverage, so it was folded in rather than kept as a third copy); it
needs no PDF.
"""

from __future__ import annotations

from scipy.stats import norm  # type: ignore[import-untyped]


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function ``N(x)``."""
    return float(norm.cdf(x))


def norm_pdf(x: float) -> float:
    """Standard normal probability density function ``n(x)``."""
    return float(norm.pdf(x))
