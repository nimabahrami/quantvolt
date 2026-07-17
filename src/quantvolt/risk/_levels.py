"""Shared VaR/CVaR confidence-level validation and loss-quantile helpers (risk-internal).

``engine.py``, ``mc_var.py``, and ``credit_var.py`` each validate a pair of strictly
ascending confidence levels and (for ``engine``/``mc_var``) turn a loss sample into
``(var_lo, var_hi, cvar)`` via ``numpy.percentile`` plus an inclusive-tail mean. This
module is the single place that logic lives; the three callers import it rather than
each carrying a byte-identical (or near-identical, for the message labels) copy.

Not part of the public API — nothing here is re-exported from ``quantvolt.risk``.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from ..exceptions import ValidationError

#: Default VaR/credit-VaR confidence levels (95% / 99%), matching the fraction
#: convention used across risk/parametric_var.py, risk/engine.py, risk/mc_var.py, and
#: risk/credit_var.py.
DEFAULT_CONFIDENCES: tuple[float, float] = (0.95, 0.99)

#: Default CVaR confidence level (97.5%), shared by risk/engine.py and risk/mc_var.py.
DEFAULT_CVAR_CONFIDENCE: float = 0.975


def validate_confidence_pair(
    confidences: Sequence[float],
    *,
    low_name: str = "var_95",
    high_name: str = "var_99",
) -> tuple[float, float]:
    """Coerce/validate two confidence levels (fractions in the open interval (0, 1)).

    Returns the corresponding percentage-point pair (``confidence * 100``) for
    :func:`numpy.percentile`, in ``(low_level, high_level)`` order. ``low_name`` /
    ``high_name`` customize only the error-message labels (e.g. ``credit_var_95`` /
    ``credit_var_99``); the validation itself — exactly 2 levels, each in the open
    interval ``(0, 1)``, strictly ascending — is identical for every caller.
    """
    levels = tuple(float(c) for c in confidences)
    if len(levels) != 2:
        raise ValidationError(
            f"confidences must contain exactly 2 levels (for {low_name} and {high_name}), "
            f"got {len(levels)}"
        )
    for confidence in levels:
        if not 0.0 < confidence < 1.0:
            raise ValidationError(
                f"each confidence must be in the open interval (0, 1), got {confidence!r}"
            )
    lo, hi = levels
    if not lo < hi:
        raise ValidationError(
            f"confidences must be strictly ascending as ({low_name}_level, {high_name}_level) "
            f"— i.e. confidences[0] < confidences[1] — got {levels!r}"
        )
    return lo * 100.0, hi * 100.0


def validate_single_confidence(confidence: float, *, name: str) -> float:
    """Coerce/validate a single confidence level (a fraction in the open interval (0, 1)).

    Returns the corresponding percentage point (``confidence * 100``) for
    :func:`numpy.percentile`.
    """
    level = float(confidence)
    if not 0.0 < level < 1.0:
        raise ValidationError(f"{name} must be in the open interval (0, 1), got {level!r}")
    return level * 100.0


def var_quantiles(
    losses: npt.NDArray[np.float64], var_lo_pct: float, var_hi_pct: float
) -> tuple[float, float]:
    """``(var_lo, var_hi)``: the two loss-sample percentiles at the given levels."""
    return (
        float(np.percentile(losses, var_lo_pct)),
        float(np.percentile(losses, var_hi_pct)),
    )


def loss_metrics(
    losses: npt.NDArray[np.float64], var_lo_pct: float, var_hi_pct: float, cvar_pct: float
) -> tuple[float, float, float]:
    """``(var_lo, var_hi, cvar)`` from a loss sample at the given percentile levels.

    ``cvar`` is the mean loss at or above the ``cvar_pct`` percentile (inclusive tail,
    so the tail mean is never taken over an empty selection).
    """
    var_lo, var_hi = var_quantiles(losses, var_lo_pct, var_hi_pct)
    tail_threshold = np.percentile(losses, cvar_pct)
    cvar = float(losses[losses >= tail_threshold].mean())
    return var_lo, var_hi, cvar
