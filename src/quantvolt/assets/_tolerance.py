"""Shared floating-point tolerance for discretised grid / feasibility comparisons.

:mod:`~quantvolt.assets.storage` and :mod:`~quantvolt.assets.dispatch_deterministic`
each discretise a continuous state (inventory volume, output level) onto a uniform
grid and then compare floats against grid boundaries / ramp limits / capacity ceilings.
Both encode the *same* tolerance for the *same* reason — absorbing floating-point
rounding in grid-step arithmetic (``floor(span / step + eps)``) and in ``<=``/``>=``
feasibility checks at a grid boundary — so it is defined once here rather than as two
independently chosen ``1e-9`` literals.

This is distinct from :mod:`~quantvolt.assets.dispatch_sdp`'s
``_SURFACE_SLOPE_EPS``, which guards a regression-slope near-singularity (a
different tolerance for a different purpose) and is not consolidated here.
"""

from __future__ import annotations

#: Grid-alignment / feasibility tolerance shared by storage and deterministic dispatch.
GRID_EPS = 1e-9
