"""Cash Flow at Risk (CFaR) over multi-period horizons (Task 67, Req 16).

CFaR is a long-horizon earnings/liquidity risk measure, not a mark-to-market VaR.
It asks: over the next ``horizon`` periods, how far below its *expected* level could
the aggregated operating cash flow realistically fall? The measure is driven by a
caller-supplied **pure** cash-flow model — a callable mapping one scenario of market
*and* operational factors to a per-period cash-flow vector.

Request surface
---------------
``cash_flow_at_risk(cashflow_model, scenarios, horizon, seed, consistency=None)``

* ``cashflow_model: Callable[[Scenario], NDArray]`` — a pure callable. Given one
  scenario it returns a 1-D per-period cash-flow vector of length ``horizon``. It is
  treated as pure: called exactly once per scenario and never handed a mutated input
  (deep-copy protection is the caller's concern; this function mutates nothing).
* ``scenarios: Sequence[Scenario]`` where ``Scenario = Mapping[str, float]`` — the
  factor scenario set. Each scenario maps a factor *name* to its realised value, so
  operational factors (e.g. ``"generation_growth"``, ``"demand"``, ``"availability"``)
  sit alongside market factors (e.g. ``"power_price"``, ``"gas_price"``) in the same
  mapping (Req 16.2). The set is treated as **exhaustive** — every scenario is
  evaluated — so no sampling occurs here and determinism is structural.
* ``horizon: int`` — number of periods, must be >= 1.
* ``seed: int`` — recorded on the result for reproducibility (Req 16.3). Because the
  scenario set is exhaustive there is no internal sampling to seed; the seed is still
  accepted and carried so a caller that generates ``scenarios`` from the same seed has
  one place recording it. Were sampling ever introduced here it would use
  ``numpy.random.default_rng(seed)``.
* ``consistency: Mapping[str, str] | None`` — caller-supplied consistency metadata
  linking operational and market factors (Req 16.2). It is carried through to the
  result verbatim (as an equal copy) rather than silently ignored; this function does
  not interpret it.

CFaR definition and sign convention
-----------------------------------
For each scenario the per-period vector is aggregated (plain sum) into one realised
aggregate cash flow. Over the scenario set that yields the distribution of aggregated
cash flow, from which we report ``expected`` (mean) and the 5th / 50th / 95th
percentiles (``numpy.percentile``, default linear interpolation — matching the house
convention in :mod:`quantvolt.risk.engine`).

The 95% CFaR is the shortfall of realised aggregate cash flow **below its expected
level** that is not exceeded at the 95% confidence level::

    cfar_95 = max(0.0, expected - p5)

where ``p5`` is the 5th percentile of the aggregate distribution. It is a
non-negative currency amount in the units of the model's cash flows: with 95%
probability the realised aggregate cash flow lands at or above ``p5``, so the shortfall
below the expected level is at most ``expected - p5``. This formula is pinned by Req 16.1
and Property 52 and is **not** reinterpreted here — including its known collapse mode
documented next.

Within its ordinary (non-degenerate, non-catastrophic) range a larger ``cfar_95`` means
more downside earnings/liquidity risk, and the ``max(0.0, ...)`` floor makes the measure
non-negative: a degenerate distribution (every scenario identical) has ``expected == p5``
and therefore ``cfar_95 == 0.0``.

**Known zero-collapse mode.** ``cfar_95`` is *not* a monotonic "bigger number = more
downside risk" indicator in isolation, because ``expected`` (the full-sample mean) and
``p5`` (an order statistic) respond very differently to one extreme scenario. A single
catastrophic-tail scenario can drag ``expected`` itself below ``p5`` — e.g. worsening one
scenario in an otherwise mild set from a modest loss to a ruinous one can move ``expected``
from just above ``p5`` to far below it — at which point ``expected - p5`` is negative and
the ``max(0.0, ...)`` floor reports ``cfar_95 == 0.0`` even though the underlying book is
unambiguously riskier (its ``expected`` is far more negative). Callers should not read
``cfar_95`` alone as a risk ranking; inspect ``expected`` and the ``p5``/``p50``/``p95``
percentiles (and, ideally, ``expected < p5`` as a collapse flag) alongside it.

Note (physical-drift guard, deferred wiring): where a caller generates ``scenarios``
from a stochastic drift, Property 59 requires rejecting a risk-neutral-tagged drift on
VaR/CFaR calls. This surface accepts already-realised scenarios (no drift argument), so
the guard does not apply here; if a drift-driven scenario generator is added later it
should route through ``numerics/risk_adjustment.require_physical_drift`` before reaching
this function.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .._validation import require_non_empty, require_positive, require_probability
from ..exceptions import ValidationError

Scenario = Mapping[str, float]
CashFlowModel = Callable[[Scenario], npt.NDArray[np.float64]]


@dataclass(frozen=True, slots=True)
class CFaRResult:
    """Outcome of a :func:`cash_flow_at_risk` computation (Req 16.1).

    ``cfar_95`` is the shortfall below the expected aggregate cash flow at the
    caller's ``confidence_level`` (95% by default; see the module docstring for the
    exact definition and sign convention); it is always ``>= 0``. ``expected`` is the
    mean and ``p5`` / ``p50`` / ``p95`` are percentiles of the aggregate cash-flow
    distribution (``p5`` sits at ``confidence_level``'s complement — the 5th
    percentile at the default 95% confidence level; ``p50`` / ``p95`` are always the
    50th / 95th percentiles). ``aggregate_cashflows`` is the per-scenario aggregated
    cash flow in the input scenario order, exposing the full distribution. ``horizon``
    and ``seed`` are echoed for reproducibility, and ``consistency`` is the
    caller-supplied market/operational consistency metadata carried verbatim.
    """

    cfar_95: float
    expected: float
    p5: float
    p50: float
    p95: float
    horizon: int
    seed: int
    aggregate_cashflows: tuple[float, ...]
    consistency: Mapping[str, str] | None


def cash_flow_at_risk(
    cashflow_model: CashFlowModel,
    scenarios: Sequence[Scenario],
    horizon: int,
    seed: int,
    consistency: Mapping[str, str] | None = None,
    *,
    confidence_level: float = 0.95,
) -> CFaRResult:
    """Compute CFaR plus summary statistics over a factor scenario set (Req 16).

    For every scenario the pure ``cashflow_model`` is called exactly once, its returned
    per-period vector is validated to have length ``horizon`` and aggregated (summed)
    into one realised aggregate cash flow. Across scenarios this forms the distribution
    of aggregated cash flow, from which the mean, the percentiles, and the
    shortfall-below-expected at ``confidence_level`` are computed. See the module
    docstring for the request surface, the exact CFaR definition, and the sign
    convention.

    Args:
        cashflow_model: Pure callable mapping one scenario to a 1-D per-period
            cash-flow vector of length ``horizon``. Called once per scenario; never
            mutated.
        scenarios: Non-empty exhaustive factor scenario set (market + operational
            factors keyed by name).
        horizon: Number of periods, ``>= 1``.
        seed: Reproducibility seed, echoed on the result (Req 16.3).
        consistency: Optional market/operational consistency metadata, carried through
            to the result verbatim (Req 16.2).
        confidence_level: Confidence level for the ``cfar_95`` / ``p5`` shortfall
            measure; defaults to ``0.95``, reproducing the 5th-percentile shortfall
            documented in the module docstring. Must be in ``[0, 1]``. ``p50`` / ``p95``
            always report the 50th / 95th percentiles regardless of this parameter.

    Returns:
        A :class:`CFaRResult`.

    Raises:
        ValidationError: If ``horizon < 1``; if ``scenarios`` is empty; if
            ``confidence_level`` is outside ``[0, 1]``; or if the model returns, for
            any scenario, a vector whose shape is not ``(horizon,)`` — the message
            names the returned shape, the horizon, and the scenario index (Req 16.4).
    """
    require_positive("horizon", horizon)
    require_non_empty("scenarios", scenarios)
    require_probability("confidence_level", confidence_level)

    aggregates = np.empty(len(scenarios), dtype=np.float64)
    for index, scenario in enumerate(scenarios):
        vector = np.asarray(cashflow_model(scenario), dtype=np.float64)
        if vector.ndim != 1 or vector.shape[0] != horizon:
            raise ValidationError(
                f"cash-flow model returned a vector of shape {vector.shape} for "
                f"scenario index {index}, but the per-period cash-flow vector length "
                f"must equal horizon={horizon}"
            )
        aggregates[index] = vector.sum()

    expected = float(aggregates.mean())
    # Multiplying by 100 first (rather than subtracting fractions before scaling) keeps
    # the default 0.95 bit-exact with the previously-hardcoded percentile level 5.0.
    p_low_pct = 100.0 - confidence_level * 100.0
    p5 = float(np.percentile(aggregates, p_low_pct))
    p50 = float(np.percentile(aggregates, 50.0))
    p95 = float(np.percentile(aggregates, 95.0))
    cfar_95 = max(0.0, expected - p5)

    return CFaRResult(
        cfar_95=cfar_95,
        expected=expected,
        p5=p5,
        p50=p50,
        p95=p95,
        horizon=horizon,
        seed=seed,
        aggregate_cashflows=tuple(aggregates.tolist()),
        consistency=dict(consistency) if consistency is not None else None,
    )
