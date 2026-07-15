"""RiskEngine — holds the scenario catalogue; computes VaR/CVaR (Task 41).

``RiskEngine`` is a class because it carries configuration — the
:class:`~quantvolt.risk.scenarios.ScenarioCatalogue` used to resolve named
stress scenarios (Req 9.4 / 9.7) — while every computation stays pure and
deterministic: no input is ever mutated and identical inputs produce
identical results.

Factor-ordering convention
--------------------------
:meth:`RiskEngine.compute_risk` flattens the aggregated
:class:`~quantvolt.risk.aggregation.DeltaMatrix` **row-major**: commodities
are sorted lexicographically (rows) and delivery periods chronologically
(columns), so factor cell ``i * n_periods + j`` is
``(commodities[i], periods[j])``. The columns of ``scenario_matrix`` must be
in exactly this flattened order, and ``n_risk_factors`` must equal
``n_commodities * n_periods`` of the aggregated grid — otherwise a
:class:`~quantvolt.exceptions.ValidationError` naming both dimensions is
raised.

Shock-application convention
----------------------------
:meth:`RiskEngine.compute_risk` and :meth:`RiskEngine.apply_scenario` use two
different, independently documented conventions, because they consume shocks
of different units:

* ``compute_risk``'s ``scenario_matrix`` entries are applied directly per unit
  of delta: ``P&L = delta x shock``. This is the only convention computable
  from a caller-supplied historical scenario matrix in isolation (its columns
  carry no reference price); a caller whose ``scenario_matrix`` holds
  *relative* moves and whose deltas are per absolute price unit should
  pre-scale the matrix by the reference prices before calling.
* ``apply_scenario``'s :class:`~quantvolt.risk.scenarios.ScenarioShock` values
  (both the built-in catalogue and user-defined shocks) are documented
  *relative* fractional moves (see :mod:`quantvolt.risk.scenarios`), so they
  are applied as ``P&L = delta x reference_price x shock``, where
  ``reference_price`` is read from the position's
  ``PricedPosition.reference_prices`` mapping for that ``(commodity, period)``
  key. Every built-in pricer in :mod:`quantvolt.portfolio.valuation` populates
  ``reference_prices``, so positions produced by ``value_portfolio`` are
  scaled correctly. A key absent from ``reference_prices`` (including an
  entirely empty mapping — the default for hand-built ``PricedPosition``
  instances that never set it) falls back to a reference price of ``1.0``,
  reproducing the plain ``delta x shock`` convention for callers whose delta
  is already price-inclusive; this is a documented approximation, not a
  correctness guarantee, for such positions.
"""

from __future__ import annotations

import math
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np
import numpy.typing as npt

from .._validation import require_positive
from ..exceptions import ValidationError
from .aggregation import DeltaMatrix
from .aggregation import aggregate_delta as _aggregate_delta
from .scenarios import ScenarioCatalogue, ScenarioShock, ShockKey

if TYPE_CHECKING:
    from ..portfolio.model import PricedPosition

#: Default VaR confidence levels for compute_risk (95% / 99%), matching the fraction
#: convention of risk/parametric_var.py's ``DEFAULT_CONFIDENCES``.
DEFAULT_VAR_CONFIDENCES: tuple[float, float] = (0.95, 0.99)
#: Default CVaR confidence level for compute_risk (97.5%).
DEFAULT_CVAR_CONFIDENCE: float = 0.975


@dataclass(frozen=True, slots=True)
class ExcludedPosition:
    index: int
    reason: Literal["missing_delta", "missing_npv", "unresolvable_instrument"]


@dataclass(frozen=True, slots=True)
class RiskResult:
    var_95: float
    var_99: float
    cvar_975: float
    delta_matrix: DeltaMatrix
    exclusion_report: list[ExcludedPosition]
    partial: bool
    unprocessed_indices: list[int]


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Outcome of applying one stress scenario to a book (Req 9.4).

    ``per_position_pnl`` is ordered exactly like the input position list, and
    ``total_pnl`` is the plain left-to-right sum of those contributions, so
    ``total_pnl == sum(per_position_pnl)`` holds exactly (Property 23).
    """

    scenario_name: str
    total_pnl: float
    per_position_pnl: tuple[float, ...]


def _exclusion_reason(
    position: PricedPosition,
) -> Literal["missing_delta", "missing_npv", "unresolvable_instrument"] | None:
    """Classify why a position cannot enter aggregated risk metrics (Req 9.5).

    ``PricedPosition`` already guarantees a finite ``npv`` at construction, so
    ``missing_npv`` is a defensive classification for values that bypassed that
    invariant (e.g. ``None`` or NaN injected by untyped callers). ``missing_delta``
    covers positions whose delta mapping is empty. ``unresolvable_instrument`` is
    reserved for instrument types whose exposures cannot be mapped onto the
    ``(commodity, period)`` factor grid; because ``PricedPosition.delta`` is
    already keyed by ``(commodity, period)``, no current code path emits it.
    """
    npv = position.npv
    if not (isinstance(npv, int | float) and math.isfinite(npv)):
        return "missing_npv"
    if len(position.delta) == 0:
        return "missing_delta"
    return None


def _require_scenario_matrix(scenario_matrix: npt.NDArray[np.float64]) -> None:
    """Eager boundary validation of the scenario matrix (coding-style.md section 7)."""
    if not isinstance(scenario_matrix, np.ndarray):
        raise ValidationError(
            "scenario_matrix must be a 2-D float numpy.ndarray, got "
            f"{type(scenario_matrix).__name__}"
        )
    if scenario_matrix.ndim != 2:
        raise ValidationError(
            "scenario_matrix must be 2-D with shape (n_scenarios, n_risk_factors), "
            f"got {scenario_matrix.ndim} dimension(s)"
        )
    if scenario_matrix.dtype.kind != "f":
        raise ValidationError(
            f"scenario_matrix must have a floating-point dtype, got {scenario_matrix.dtype}"
        )
    if not np.all(np.isfinite(scenario_matrix)):
        raise ValidationError(
            "scenario_matrix must contain only finite values (no NaN/Inf cells); a "
            "non-finite scenario would otherwise silently poison every downstream "
            "loss quantile"
        )
    if scenario_matrix.shape[0] == 0:
        raise ValidationError("scenario_matrix must contain at least one scenario row, got 0 rows")


def _validate_var_confidences(confidences: Sequence[float]) -> tuple[float, float]:
    """Coerce/validate the two VaR confidence levels (fractions in the open interval (0, 1)).

    Returns the corresponding percentage-point pair (``confidence * 100``) for
    :func:`numpy.percentile`, in ``(var_95_level, var_99_level)`` order.
    """
    levels = tuple(float(c) for c in confidences)
    if len(levels) != 2:
        raise ValidationError(
            f"confidences must contain exactly 2 levels (for var_95 and var_99), got {len(levels)}"
        )
    for confidence in levels:
        if not 0.0 < confidence < 1.0:
            raise ValidationError(
                f"each confidence must be in the open interval (0, 1), got {confidence!r}"
            )
    lo, hi = levels
    if not lo < hi:
        raise ValidationError(
            "confidences must be strictly ascending as (var_95_level, var_99_level) "
            f"— i.e. confidences[0] < confidences[1] — got {levels!r}"
        )
    return lo * 100.0, hi * 100.0


def _validate_cvar_confidence(cvar_confidence: float) -> float:
    """Coerce/validate ``cvar_confidence`` (a fraction in the open interval (0, 1)).

    Returns the corresponding percentage point (``cvar_confidence * 100``) for
    :func:`numpy.percentile`.
    """
    level = float(cvar_confidence)
    if not 0.0 < level < 1.0:
        raise ValidationError(f"cvar_confidence must be in the open interval (0, 1), got {level!r}")
    return level * 100.0


def _position_pnl(position: PricedPosition, shocks: Mapping[ShockKey, float]) -> float:
    """One position's scenario P&L: sum of ``delta x reference_price x shock``.

    A period-specific shock ``(commodity, period)`` wins over a commodity-wide
    shock ``(commodity, None)``; a factor with neither contributes 0.0.
    ``reference_price`` is ``position.reference_prices.get((commodity, period), 1.0)``
    (see the module docstring's shock-application convention): every built-in
    pricer populates it, so relative catalogue/user shocks scale correctly for a
    ``value_portfolio``-produced book; a position that never sets it is treated as
    already price-inclusive (reference price ``1.0``).
    """
    total = 0.0
    for (commodity, period), delta in position.delta.items():
        specific = shocks.get((commodity, period))
        shock = specific if specific is not None else shocks.get((commodity, None), 0.0)
        reference_price = position.reference_prices.get((commodity, period), 1.0)
        total += delta * reference_price * shock
    return total


class RiskEngine:
    """Portfolio risk metrics: VaR / CVaR, delta aggregation, stress scenarios (Req 9).

    A configured service, not a Singleton: it holds the scenario catalogue used to
    resolve named scenarios and nothing else. All methods are pure with respect to
    their inputs.
    """

    def __init__(self, catalogue: ScenarioCatalogue | None = None) -> None:
        self._catalogue = catalogue or ScenarioCatalogue()

    def compute_risk(
        self,
        positions: list[PricedPosition],
        scenario_matrix: npt.NDArray[np.float64],
        timeout_seconds: float = 60.0,
        *,
        confidences: Sequence[float] = DEFAULT_VAR_CONFIDENCES,
        cvar_confidence: float = DEFAULT_CVAR_CONFIDENCE,
    ) -> RiskResult:
        """Historical-simulation VaR (95/99 by default) and CVaR (97.5 by default).

        Flow (Req 9.1 / 9.2 / 9.5 / 9.6): filter positions in input order into the
        always-present ``exclusion_report``; net the included deltas into a
        :class:`DeltaMatrix`; flatten it row-major into a factor vector (see the
        module docstring for the ordering convention); then vectorise
        ``pnl = scenario_matrix @ delta_vector`` — one P&L per scenario row.
        Losses are ``-pnl``; ``var_95`` / ``var_99`` are the ``confidences`` percentiles
        of the losses via :func:`numpy.percentile` (default linear interpolation), and
        ``cvar_975`` is the mean of losses at or above the ``cvar_confidence``
        percentile (inclusive tail, so the tail is never empty). The result field names
        (``var_95``/``var_99``/``cvar_975``) are fixed regardless of the levels supplied.

        Timeout / partial results (Req 9.6): elapsed time (``time.monotonic``) is
        checked inside the per-position filtering loop — the only step whose cost
        grows per position; the vectorised P&L step afterwards is effectively
        instantaneous, so the guard lives in the loop. On expiry the loop stops
        and the result is built from the positions processed so far with
        ``partial=True`` and ``unprocessed_indices`` holding the remaining input
        indices. ``time.monotonic`` feeds only this guard, never any result
        value: without a timeout the method is fully deterministic.

        An included-exposure grid with zero cells (empty, fully excluded, or
        fully unprocessed book) short-circuits to zero P&L for every scenario;
        the factor-count check against ``scenario_matrix`` columns applies only
        to a non-empty grid, since the column-to-cell mapping is only defined
        then.

        Args:
            positions: Priced book, filtered in input order.
            scenario_matrix: ``(n_scenarios, n_risk_factors)`` shock matrix.
            timeout_seconds: Wall-clock budget for the filtering loop; defaults to 60.
            confidences: The two VaR confidence levels (fractions in ``(0, 1)``,
                matching :mod:`quantvolt.risk.parametric_var`'s convention) reported as
                ``var_95`` / ``var_99``; defaults to ``(0.95, 0.99)``.
            cvar_confidence: The CVaR confidence level (a fraction in ``(0, 1)``)
                reported as ``cvar_975``; defaults to ``0.975``.

        Raises:
            ValidationError: If ``scenario_matrix`` is not a finite 2-D float array with
                at least one row, or ``timeout_seconds`` is invalid, or ``confidences``
                does not contain exactly 2 strictly ascending levels in ``(0, 1)``, or
                ``cvar_confidence`` is not in ``(0, 1)``.
        """
        _require_scenario_matrix(scenario_matrix)
        require_positive("timeout_seconds", timeout_seconds)
        var_lo_pct, var_hi_pct = _validate_var_confidences(confidences)
        cvar_pct = _validate_cvar_confidence(cvar_confidence)

        included: list[PricedPosition] = []
        exclusion_report: list[ExcludedPosition] = []
        unprocessed_indices: list[int] = []
        partial = False

        start = time.monotonic()
        for index, position in enumerate(positions):
            if time.monotonic() - start > timeout_seconds:
                partial = True
                unprocessed_indices = list(range(index, len(positions)))
                break
            reason = _exclusion_reason(position)
            if reason is None:
                included.append(position)
            else:
                exclusion_report.append(ExcludedPosition(index=index, reason=reason))

        delta_matrix = _aggregate_delta(included)
        n_commodities = len(delta_matrix.commodities)
        n_periods = len(delta_matrix.periods)
        n_cells = n_commodities * n_periods
        n_scenarios, n_factors = scenario_matrix.shape

        if n_cells == 0:
            pnl = np.zeros(n_scenarios, dtype=np.float64)
        else:
            if n_factors != n_cells:
                raise ValidationError(
                    "scenario_matrix must have one column per aggregated delta factor "
                    f"cell: scenario_matrix has {n_factors} risk-factor columns but the "
                    f"aggregated delta grid is {n_commodities} commodities x {n_periods} "
                    f"periods = {n_cells} cells"
                )
            delta_vector = np.asarray(delta_matrix.values, dtype=np.float64).reshape(-1)
            pnl = scenario_matrix @ delta_vector

        losses = -pnl
        var_95 = float(np.percentile(losses, var_lo_pct))
        var_99 = float(np.percentile(losses, var_hi_pct))
        tail_threshold = np.percentile(losses, cvar_pct)
        cvar_975 = float(losses[losses >= tail_threshold].mean())

        return RiskResult(
            var_95=var_95,
            var_99=var_99,
            cvar_975=cvar_975,
            delta_matrix=delta_matrix,
            exclusion_report=exclusion_report,
            partial=partial,
            unprocessed_indices=unprocessed_indices,
        )

    def aggregate_delta(self, positions: list[PricedPosition]) -> DeltaMatrix:
        """Net delta by commodity x delivery period (Req 9.3).

        Delegates to :func:`quantvolt.risk.aggregation.aggregate_delta`.
        """
        return _aggregate_delta(positions)

    def apply_scenario(
        self, positions: list[PricedPosition], scenario: str | ScenarioShock
    ) -> ScenarioResult:
        """Apply a named or user-defined stress scenario to the book (Req 9.4).

        A ``str`` is resolved through the engine's catalogue;
        :class:`~quantvolt.exceptions.ScenarioNotFoundError` propagates for an
        unknown name, listing the available scenario names (Req 9.7). Each
        position contributes ``sum(delta x reference_price x shock)`` over its
        delta entries, where a period-specific shock wins over a commodity-wide
        one, an unshocked factor contributes zero, and ``reference_price`` comes
        from the position's ``reference_prices`` mapping (defaulting to ``1.0``
        when absent) — see the module docstring for the full shock-application
        convention. Positions with an empty delta mapping simply contribute
        0.0 — nothing is excluded here.
        """
        resolved = self._catalogue.get(scenario) if isinstance(scenario, str) else scenario
        per_position_pnl = tuple(_position_pnl(position, resolved.shocks) for position in positions)
        return ScenarioResult(
            scenario_name=resolved.name,
            total_pnl=float(sum(per_position_pnl)),
            per_position_pnl=per_position_pnl,
        )
