"""Dispatch heuristics and approximations.

Three caller-selectable approximations to the dispatch optimisation, each trading
fidelity for tractability, plus a specific warning when the state-aggregation
("bang-bang") one is used. This module implements them as documented input/problem
transformations around the exact deterministic solver
``quantvolt.assets.dispatch_deterministic.dispatch_deterministic``: the
perfect-foresight optimum that is itself the upper bound the stochastic value
is measured against. Wrapping the deterministic DP (rather than the
Monte-Carlo ``quantvolt.assets.dispatch_sdp.dispatch_value``) keeps every
approximation's error exactly comparable to a noise-free benchmark: the
block-constant, decoupling, and bias identities below are equalities up to float
tolerance, not statistical statements. The same three transformations apply
unchanged to the stochastic solver: a caller may block-average the factor
model's per-step structure, divide the simulated horizon, or feed a bang-bang
plant to ``dispatch_value``, but the heuristic itself is the transform, and
it is cleanest to specify and test against the deterministic optimum.

The three approximations
------------------------
- ``time_aggregate``: time aggregation (hourly -> 4/8/16-hour blocks).
  Averages the price/temperature series into equal blocks, solves the (much
  shorter) coarse dispatch, and rescales the coarse value back to the original
  number of hours. Exact on block-constant prices for a unit that incurs no start
  within the horizon; the intra-block ramp/commitment freedom it drops is the
  approximation.
- ``horizon_divide``: horizon division (weekly / monthly sub-horizons).
  Splits the horizon into consecutive sub-horizons solved independently and sums
  their values. The boundary-state approximation: each sub-horizon after the
  first restarts from a cold, restart-ready offline state, dropping the true
  carried-over commitment state, decouples the subproblems. Exact when the
  periods decouple (zero start costs and non-binding min-run / min-down / ramp).
- ``bang_bang``: state aggregation for steep heat-rate curves. Collapses
  the online output grid to the single full-load level, so the unit is either off
  or running at ``c_max`` ({0, c_max}). Exact for a linear (constant marginal)
  heat rate, where the optimal load is always a corner; a downward-biased lower
  bound for a steep (rising-marginal) curve, where the exact optimum runs at an
  efficient part load the approximation cannot represent. Emits
  ``BangBangHedgeWarning``: hedges are far more sensitive than
  values to the heat-curve approximation.

Direction-of-bias summary (the "documented direction" the tests assert)
-----------------------------------------------------------------------
- ``bang_bang`` is a **lower bound** on the exact deterministic value whenever the
  full-load level is reachable in one step (ramp rate >= operating range, so the
  bang-bang on/off policy set is a strict subset of the exact one): restricting
  the load choice can only lose value; equality holds for a linear heat rate.
- ``time_aggregate`` **understates** value when a start cost is incurred inside an
  aggregated block (the once-per-block start charge is replicated across the
  block's sub-periods); it is exact on block-constant prices with no such start.
- ``horizon_divide`` **typically understates** value (spurious restart costs at
  each boundary) but *can* overstate it when a binding min-run / min-down
  constraint spanning a boundary is artificially relaxed by the split; it is exact
  when the periods decouple.

All three are pure and deterministic (they only call the deterministic DP), never
mutate their inputs, and validate every argument before any computation.
"""

from __future__ import annotations

import math
import warnings
from collections.abc import Sequence
from dataclasses import replace

from ..exceptions import ValidationError
from .dispatch_deterministic import DispatchSchedule, _validate_series, dispatch_deterministic
from .plant import MaxCapacityCurve, PlantModel


class BangBangHedgeWarning(UserWarning):
    """Advisory that bang-bang state aggregation biases hedges far more than values.

    Collapsing the output grid to {0, c_max} pins the operating point to full load,
    so the plant value loses only the (often small) part-load optionality. The
    sensitivities (the deltas and critical-dispatch surfaces used to hedge) are
    a different matter: they read the slope of value against price, and the
    approximation replaces the true, curved heat-rate response with a single kink
    at the on/off boundary. A hedge derived from a bang-bang model can therefore be
    badly wrong even when the headline value looks reasonable. The approximation is
    not rejected: for a sufficiently steep heat curve the value error is genuinely
    negligible, but the caller is warned so the choice is deliberate.
    """


def _block_mean(values: Sequence[float], start: int, stop: int) -> float:
    """Arithmetic mean of ``values[start:stop]`` (float-stable via ``math.fsum``)."""
    chunk = values[start:stop]
    return math.fsum(chunk) / len(chunk)


def _const_capacity(capacity: float) -> MaxCapacityCurve:
    """A temperature-independent ``c_max(temp) == capacity`` curve for the bang-bang plant."""
    return lambda _temp: capacity


def time_aggregate(
    plant: PlantModel,
    power_prices: Sequence[float],
    fuel_prices: Sequence[float],
    temperatures: Sequence[float],
    block_hours: int,
    *,
    initial_online: bool = False,
    initial_output: float = 0.0,
    initial_uptime: int | None = None,
    initial_downtime: int | None = None,
    output_step: float | None = None,
    discount_factors: Sequence[float] | None = None,
) -> DispatchSchedule:
    """Time-aggregation heuristic: solve on ``block_hours``-hour blocks, rescale.

    Each consecutive run of ``block_hours`` periods is averaged into one coarse
    period (power, fuel, temperature, and — if supplied — discount factor), the
    deterministic dispatch is solved on the coarse series, and the coarse per-period
    result is expanded back to the original resolution with each block's cash flow
    recurring ``block_hours`` times (the rescaling). The returned
    :class:`DispatchSchedule` therefore has the original horizon's length and a
    ``total_value`` equal to ``block_hours`` times the coarse value.

    Exactness and bias. On **block-constant** prices (each series constant within
    every block) the block average is lossless and, for a unit that incurs no start
    within the horizon, the rescaled value equals the full-resolution optimum
    exactly. When a start *is* incurred inside a block, the once-per-block start
    cost is replicated across the block's sub-periods, understating the value — a
    documented downward bias that shrinks with fewer/cheaper starts. Sub-block ramp
    and commitment freedom (and any intra-block discount-factor variation) are the
    other, generally small, sources of error. Duration/timer arguments are counted
    in *coarse* periods (blocks) inside the coarse solve; pass them accordingly.

    Args:
        plant: The operating model (unchanged; passed to the coarse solve).
        power_prices: Power price ``P_t`` per (fine) period.
        fuel_prices: Fuel price ``G_t`` per period.
        temperatures: Ambient temperature ``S_t`` per period.
        block_hours: Periods per aggregation block; must be an integer ``>= 1`` that
            divides the horizon evenly.
        initial_online: Whether the unit is producing entering the horizon.
        initial_output: Output entering the horizon (MW); on the coarse grid when
            online.
        initial_uptime: Producing (coarse) periods already accrued (min-run).
        initial_downtime: Offline (coarse) periods already accrued (start bucket /
            min-down).
        output_step: Output-grid spacing (MW); defaults to the ramp rate.
        discount_factors: Per-period to-today discount factors (default all 1.0);
            block-averaged before the coarse solve.

    Returns:
        A full-resolution :class:`DispatchSchedule`; ``total_value`` is the rescaled
        coarse value.

    Raises:
        ValidationError: If the series are empty or of unequal length; if a discount
            factor or ``output_step`` is non-positive; if ``block_hours`` is not an
            integer ``>= 1`` or does not divide the horizon; or if the coarse problem
            is itself infeasible (delegated to the deterministic solver).
    """
    horizon = _validate_series(power_prices, fuel_prices, temperatures, discount_factors)
    if not isinstance(block_hours, int) or block_hours < 1:
        raise ValidationError(f"block_hours must be an integer >= 1, got {block_hours!r}")
    if horizon % block_hours != 0:
        raise ValidationError(
            f"block_hours must divide the horizon evenly; horizon {horizon} is not a "
            f"multiple of block_hours {block_hours}"
        )
    n_blocks = horizon // block_hours

    power_blocks: list[float] = []
    fuel_blocks: list[float] = []
    temp_blocks: list[float] = []
    discount_blocks: list[float] | None = None if discount_factors is None else []
    for j in range(n_blocks):
        lo, hi = j * block_hours, (j + 1) * block_hours
        power_blocks.append(_block_mean(power_prices, lo, hi))
        fuel_blocks.append(_block_mean(fuel_prices, lo, hi))
        temp_blocks.append(_block_mean(temperatures, lo, hi))
        if discount_factors is not None and discount_blocks is not None:
            discount_blocks.append(_block_mean(discount_factors, lo, hi))

    coarse = dispatch_deterministic(
        plant,
        power_blocks,
        fuel_blocks,
        temp_blocks,
        initial_online=initial_online,
        initial_output=initial_output,
        initial_uptime=initial_uptime,
        initial_downtime=initial_downtime,
        output_step=output_step,
        discount_factors=discount_blocks,
    )

    outputs: list[float] = []
    online: list[bool] = []
    started: list[bool] = []
    stopped: list[bool] = []
    margins: list[float] = []
    for j in range(n_blocks):
        for h in range(block_hours):
            outputs.append(coarse.outputs[j])
            online.append(coarse.online[j])
            # A start / stop is one event: mark only the block's first / last sub-period.
            started.append(coarse.started[j] and h == 0)
            stopped.append(coarse.stopped[j] and h == block_hours - 1)
            margins.append(coarse.margins[j])

    return DispatchSchedule(
        outputs=tuple(outputs),
        online=tuple(online),
        started=tuple(started),
        stopped=tuple(stopped),
        margins=tuple(margins),
        total_value=math.fsum(margins),
    )


def horizon_divide(
    plant: PlantModel,
    power_prices: Sequence[float],
    fuel_prices: Sequence[float],
    temperatures: Sequence[float],
    sub_horizon: int,
    *,
    initial_online: bool = False,
    initial_output: float = 0.0,
    initial_uptime: int | None = None,
    initial_downtime: int | None = None,
    output_step: float | None = None,
    discount_factors: Sequence[float] | None = None,
) -> DispatchSchedule:
    """Horizon-division heuristic: solve independent sub-horizons and sum.

    The horizon is cut into consecutive sub-horizons of length ``sub_horizon`` (the
    last may be shorter) that are solved independently by the deterministic DP and
    concatenated; ``total_value`` is the sum of the sub-values. This is the weekly /
    monthly sub-period heuristic that keeps each solve small.

    Boundary-state approximation. Only the first sub-horizon sees the caller's
    initial condition; every later sub-horizon restarts from a cold, restart-ready
    offline state. Dropping the true carried-over commitment state is exactly what
    decouples the subproblems, and is the approximation. It is exact when the
    periods decouple (zero start costs and non-binding min-run / min-down / ramp),
    because the dispatch is then myopic and the start-up state is immaterial. It
    typically understates value otherwise (each boundary can pay a spurious
    restart cost), but it can overstate value when a binding min-run / min-down
    constraint that would span a boundary in the full solve is artificially relaxed
    by the cut.

    Args:
        plant: The operating model (unchanged; passed to each sub-solve).
        power_prices: Power price ``P_t`` per period.
        fuel_prices: Fuel price ``G_t`` per period.
        temperatures: Ambient temperature ``S_t`` per period.
        sub_horizon: Periods per sub-horizon; must be an integer ``>= 1``.
        initial_online: Whether the unit is producing entering the *first*
            sub-horizon.
        initial_output: Output entering the first sub-horizon (MW); on the grid when
            online.
        initial_uptime: Producing periods already accrued entering the first
            sub-horizon (min-run).
        initial_downtime: Offline periods already accrued entering the first
            sub-horizon (start bucket / min-down).
        output_step: Output-grid spacing (MW); defaults to the ramp rate.
        discount_factors: Per-period to-today discount factors (default all 1.0);
            sliced per sub-horizon.

    Returns:
        The concatenated full-horizon :class:`DispatchSchedule`; ``total_value`` is
        the sum of the sub-horizon values.

    Raises:
        ValidationError: If the series are empty or of unequal length; if a discount
            factor or ``output_step`` is non-positive; if ``sub_horizon`` is not an
            integer ``>= 1``; or if any sub-problem is infeasible (delegated to the
            deterministic solver).
    """
    horizon = _validate_series(power_prices, fuel_prices, temperatures, discount_factors)
    if not isinstance(sub_horizon, int) or sub_horizon < 1:
        raise ValidationError(f"sub_horizon must be an integer >= 1, got {sub_horizon!r}")

    outputs: list[float] = []
    online: list[bool] = []
    started: list[bool] = []
    stopped: list[bool] = []
    margins: list[float] = []
    for k, lo in enumerate(range(0, horizon, sub_horizon)):
        hi = min(lo + sub_horizon, horizon)
        if k == 0:
            sub_online, sub_output = initial_online, initial_output
            sub_uptime, sub_downtime = initial_uptime, initial_downtime
        else:
            # Boundary-state approximation: fresh cold, restart-ready offline state.
            sub_online, sub_output = False, 0.0
            sub_uptime, sub_downtime = None, None
        sub_discounts = None if discount_factors is None else list(discount_factors[lo:hi])
        sub = dispatch_deterministic(
            plant,
            list(power_prices[lo:hi]),
            list(fuel_prices[lo:hi]),
            list(temperatures[lo:hi]),
            initial_online=sub_online,
            initial_output=sub_output,
            initial_uptime=sub_uptime,
            initial_downtime=sub_downtime,
            output_step=output_step,
            discount_factors=sub_discounts,
        )
        outputs.extend(sub.outputs)
        online.extend(sub.online)
        started.extend(sub.started)
        stopped.extend(sub.stopped)
        margins.extend(sub.margins)

    return DispatchSchedule(
        outputs=tuple(outputs),
        online=tuple(online),
        started=tuple(started),
        stopped=tuple(stopped),
        margins=tuple(margins),
        total_value=math.fsum(margins),
    )


def bang_bang(
    plant: PlantModel,
    power_prices: Sequence[float],
    fuel_prices: Sequence[float],
    temperatures: Sequence[float],
    *,
    initial_online: bool = False,
    initial_output: float = 0.0,
    initial_uptime: int | None = None,
    initial_downtime: int | None = None,
    output_step: float | None = None,
    discount_factors: Sequence[float] | None = None,
) -> DispatchSchedule:
    """Bang-bang state aggregation: run at full load or off, {0, c_max}.

    Collapses the online output grid to a single full-load level so the unit is
    either off or running at ``c_max``, recommended for a sufficiently steep
    heat-rate curve, where the optimal load is (almost)
    always a corner. Implemented by solving the deterministic DP on a derived plant
    whose ``c_min`` and ``c_max`` are both pinned to that full-load level; every
    other operating characteristic (heat-rate curve, start costs, ramp, durations)
    is unchanged. The input plant is not mutated: a new ``PlantModel`` is
    derived.

    Full-load level. With a constant capacity the pinned level is ``c_max``. With a
    temperature-dependent ``c_max(temp)`` the level is the horizon-minimum ``c_max``
    (the largest constant full-output level feasible in every period); a period
    whose capacity falls below the plant's own ``c_min`` makes the plant infeasible
    there and is rejected, mirroring the deterministic solver's curve check.

    Exactness and bias. For a linear (constant-marginal) heat rate the per-MWh
    margin is output-independent, so the exact optimum is a corner and bang-bang is
    exact. For a steep (rising-marginal) curve the exact optimum may run at an
    efficient part load that bang-bang cannot represent, so the value is a
    downward-biased lower bound: whenever the full-load level is reachable in one
    step (ramp rate >= operating range) the bang-bang on/off policy set is a strict
    subset of the exact one, and restricting the load choice can only lose value.

    Warning. Emits ``BangBangHedgeWarning``: hedges (sensitivities
    and critical-dispatch surfaces) are far more sensitive than the value itself to
    the heat-rate-curve approximation, because they read the slope of value
    against price, which the single on/off kink distorts even where the value error
    is negligible.

    Args:
        plant: The operating model; a full-load-pinned copy is derived from it.
        power_prices: Power price ``P_t`` per period.
        fuel_prices: Fuel price ``G_t`` per period.
        temperatures: Ambient temperature ``S_t`` per period.
        initial_online: Whether the unit is producing entering the horizon; an
            online unit is treated as running at the full-load level.
        initial_output: Ignored when ``initial_online`` (the unit is pinned to full
            load); retained for signature parity with the deterministic solver.
        initial_uptime: Producing periods already accrued (min-run).
        initial_downtime: Offline periods already accrued (start bucket / min-down).
        output_step: Output-grid spacing (MW); immaterial here (single online level)
            but validated ``> 0`` by the solver; defaults to the ramp rate.
        discount_factors: Per-period to-today discount factors (default all 1.0).

    Returns:
        The bang-bang :class:`DispatchSchedule` (outputs are 0 or the full-load
        level).

    Raises:
        ValidationError: If the series are empty or of unequal length; if a discount
            factor or ``output_step`` is non-positive; if ``c_max`` falls below
            ``c_min`` at some temperature; or if the initial condition admits no
            feasible schedule (delegated to the deterministic solver).
    """
    _validate_series(power_prices, fuel_prices, temperatures, discount_factors)
    capacity = min(plant.max_capacity(float(temp)) for temp in temperatures)
    if capacity < plant.c_min:
        raise ValidationError(
            f"bang-bang full-load level = min c_max(temp) = {capacity!r} falls below "
            f"c_min = {plant.c_min!r}; the plant cannot run at some supplied temperature"
        )

    warnings.warn(
        "bang-bang state aggregation ({0, c_max}) is in use: hedges — deltas and the "
        "critical-dispatch surfaces — are far more sensitive than the plant value to the "
        "heat-rate-curve approximation, so a hedge read off this result can be badly biased "
        "even where the value is accurate (Req 21.3).",
        BangBangHedgeWarning,
        stacklevel=2,
    )

    bang_plant = replace(plant, c_min=capacity, c_max=_const_capacity(capacity))
    pinned_output = capacity if initial_online else initial_output
    return dispatch_deterministic(
        bang_plant,
        power_prices,
        fuel_prices,
        temperatures,
        initial_online=initial_online,
        initial_output=pinned_output,
        initial_uptime=initial_uptime,
        initial_downtime=initial_downtime,
        output_step=output_step,
        discount_factors=discount_factors,
    )
