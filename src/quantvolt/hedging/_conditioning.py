"""Shared 2-norm condition-number singularity guard (hedging-internal helper).

Both :func:`quantvolt.hedging.variance_min.variance_min_hedge` and
:func:`quantvolt.hedging.mean_variance.global_mean_variance` solve a normal-equation
linear system and must reject a singular / ill-conditioned covariance matrix rather
than silently fall back to a pseudo-inverse. The ``1/eps`` limit and the conditioning
check were duplicated between the two modules; this is the one place both import it
from. Each caller keeps its own (differently worded) error message, since each names
its own matrix and linear system — only the numeric guard itself is shared.

Not part of the public API — nothing here is re-exported from ``quantvolt.hedging``.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

from ..exceptions import ValidationError

#: Upper bound on the 2-norm condition number before a normal-equation matrix is
#: treated as numerically singular. ``1/eps`` is the point past which the linear
#: solve loses all significant digits.
CONDITION_LIMIT: float = 1.0 / np.finfo(np.float64).eps


def require_well_conditioned(
    matrix: NDArray[np.float64],
    condition_limit: float,
    message: Callable[[float], str],
) -> None:
    """Raise ``ValidationError(message(condition_number))`` if ``matrix`` is too ill-conditioned.

    ``condition_number`` is ``numpy.linalg.cond(matrix)`` (2-norm). Non-finite (exactly
    singular) or exceeding ``condition_limit`` both raise; ``message`` receives the
    computed condition number so each caller can format its own error text (naming its
    own matrix and linear system) while sharing the numeric check itself.
    """
    condition_number = float(np.linalg.cond(matrix))
    if not np.isfinite(condition_number) or condition_number > condition_limit:
        raise ValidationError(message(condition_number))
