"""Perfect-foresight thermal dispatch (Task 72; Req 21.1 partial, 21.4; Property 62).

``dispatch_deterministic`` solves the deterministic optimization of Appendix B
eq. B.1: with all prices, fuel costs and temperatures known in advance, it finds
the commitment-and-output schedule that maximizes total margin subject to the
operational and state-transition constraints. Because it optimizes over the
*fully known* path, its value is the **upper bound** that any non-anticipating
(stochastic) policy is tested against — the ``dispatch_value ≤
dispatch_deterministic`` guarantee of Property 62 (validated with the Task-73
stochastic engine). ``total_value`` is therefore the headline field.

Objective (eq. B.1), per period ``t`` when producing ``q_t``::

    q_t·(P_t - HR(q_t, S_t)·G_t - VOM) - [start decided]·(SC + FSC·G_t + PSC·P_t)

summed over the horizon; ``P`` power price, ``G`` fuel price, ``S`` temperature.
No carbon term appears — eq. B.1 as written has none; a caller who wants a clean
spread folds the carbon cost into ``VOM`` or the fuel series.

Solution method — exact DP over a discretised commitment/output state
---------------------------------------------------------------------
No external solver (per the pure-computation mandate). The problem is a finite
deterministic dynamic program solved by exact backward induction:

- **Output grid.** Online output is discretised to
  ``{c_min + k·step : k = 0, 1, …}`` capped at ``max_t c_max(S_t)``, where
  ``step`` defaults to the ramp rate ``RR`` (Appendix B's own suggestion:
  "divide the generation level into units measured by the maximum adjustment
  allowed by the unit ramp rate"). A finer ``output_step`` refines the grid.
  A period only admits grid levels ``≤ c_max(S_t)`` (temperature-dependent
  ceiling), and a ramp to level ``q'`` from ``q`` is feasible iff
  ``|q' - q| ≤ RR`` (checked by value, so any ``step`` is exact for its grid).
- **State.** ``(status, output-level, timer)`` where ``status`` is offline /
  starting / online. Offline carries the downtime (min-down feasibility and the
  cold/warm/hot start bucket); online carries the output-level index (ramp) and
  the up-time (min-run feasibility); starting carries the lag counter. Timers
  saturate at the largest value that changes any decision, keeping the state
  space finite.
- **Transitions** implement the eq. B.1 state-transition constraints exactly:
  a start is allowed only after ``d_shutdown`` periods off and pays the bucketed
  start cost; a start-up lag of ``d_startup`` periods produces nothing before the
  unit reaches ``c_min``; a shutdown is allowed only after ``d_min`` producing
  periods; a running unit ramps by at most ``RR`` and stays within
  ``[c_min, c_max(S_t)]``.

**Exactness.** The DP is the exact optimum *of the discretised problem*; it
equals the true continuous optimum whenever the optimal outputs lie on the grid
— which they do by construction for the hand-worked test cases — and converges
as ``output_step → 0`` otherwise.

Conventions (documented, standard unit-commitment)
--------------------------------------------------
- A **start** brings the unit online at ``c_min`` (minimum stable generation);
  a **shutdown** takes it from its current level directly to ``0``. The ramp
  limit binds only between two consecutive *producing* periods — commitment
  transitions are governed by the min-run / min-down / start-cost logic, not the
  ramp rate (this is why eq. B.1's ramp constraint is read as an online-only
  constraint).
- ``started[t]`` marks the period a start is *initiated* (the period the start
  cost is charged); the later period the unit first produces after a start-up
  lag is not itself a "start".
- **Full availability.** The deterministic perfect-foresight benchmark assumes
  no forced outages (derate multiplier ``M ≡ 1``); the plant's ``outage_rate``
  ``λ`` is consumed only by the stochastic model (Task 73). Perfect foresight
  *and* no outages is exactly the upper bound Property 62 needs.
- **Terminal condition.** No salvage or penalty at the horizon end: the unit may
  finish online without having completed its min-run (finite-window truncation).
- **Discounting.** ``discount_factors`` (default all 1.0, matching eq. B.1's
  undiscounted sum) scales each period's whole cash flow; ``margins[t]`` is that
  discounted contribution, so ``sum(margins) == total_value`` exactly.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .._validation import require_positive
from ..exceptions import ValidationError
from .plant import PlantModel

# Commitment status codes for the DP state tuple ``(status, level_idx, timer)``.
_OFFLINE = 0
_STARTING = 1
_ONLINE = 2
# level_idx placeholder when the unit is not producing.
_NO_LEVEL = -1
# Feasibility tolerance for grid / ramp / capacity comparisons (MW).
_EPS = 1e-9

# A DP state: (status, output-level index, timer). See module docstring.
_State = tuple[int, int, int]
# A transition: (next_state, margin, output, online, started, stopped).
_Transition = tuple[_State, float, float, bool, bool, bool]


@dataclass(frozen=True, slots=True)
class DispatchSchedule:
    """The perfect-foresight optimal dispatch (eq. B.1) over the horizon.

    Every tuple is in period order and has the horizon's length.

    Attributes:
        outputs: Generation ``q_t`` per period (MW); ``0`` when not producing.
        online: Whether the unit is producing in the period.
        started: Whether a start-up is initiated in the period (start cost charged).
        stopped: Whether the unit shuts down in the period.
        margins: Per-period contribution to ``total_value`` (discounted cash
            flow, net of any start cost); ``sum(margins) == total_value``.
        total_value: The optimal total value — the perfect-foresight upper bound
            (Property 62).
    """

    outputs: tuple[float, ...]
    online: tuple[bool, ...]
    started: tuple[bool, ...]
    stopped: tuple[bool, ...]
    margins: tuple[float, ...]
    total_value: float


def _validate_series(
    power_prices: Sequence[float],
    fuel_prices: Sequence[float],
    temperatures: Sequence[float],
    discount_factors: Sequence[float] | None,
) -> int:
    """Check the market series are non-empty and equal length; return the horizon."""
    horizon = len(power_prices)
    if horizon == 0:
        raise ValidationError("power_prices must be non-empty")
    lengths = {
        "power_prices": len(power_prices),
        "fuel_prices": len(fuel_prices),
        "temperatures": len(temperatures),
    }
    if discount_factors is not None:
        lengths["discount_factors"] = len(discount_factors)
    mismatched = {name: length for name, length in lengths.items() if length != horizon}
    if mismatched:
        raise ValidationError(
            "power_prices, fuel_prices, temperatures"
            + (", discount_factors" if discount_factors is not None else "")
            + f" must all have the same length {horizon}; got "
            + ", ".join(f"{name}={length}" for name, length in lengths.items())
        )
    if discount_factors is not None:
        for index, factor in enumerate(discount_factors):
            if not factor > 0:
                raise ValidationError(f"discount_factors[{index}] must be > 0, got {factor!r}")
    return horizon


def _build_output_grid(
    plant: PlantModel, temperatures: Sequence[float], output_step: float | None
) -> tuple[float, ...]:
    """The online output levels: ``c_min + k·step`` up to ``max_t c_max(S_t)``.

    Also validates the temperature-dependent capacity: ``c_max(temp) ≥ c_min``
    for every supplied temperature (the dispatch-time half of the plant's curve
    validation).
    """
    step = plant.ramp_rate if output_step is None else output_step
    require_positive("output_step", step)
    capacities: list[float] = []
    for temp in temperatures:
        capacity = plant.max_capacity(temp)
        if capacity < plant.c_min:
            raise ValidationError(
                f"c_max(temp={temp!r}) = {capacity!r} must be >= c_min = {plant.c_min!r}"
            )
        capacities.append(capacity)
    ceiling = max(capacities)
    level_count = math.floor((ceiling - plant.c_min) / step + _EPS)
    return tuple(plant.c_min + k * step for k in range(level_count + 1))


def _initial_state(
    plant: PlantModel,
    levels: tuple[float, ...],
    *,
    initial_online: bool,
    initial_output: float,
    initial_uptime: int | None,
    initial_downtime: int | None,
    up_cap: int,
    down_cap: int,
) -> _State:
    """Translate the caller's initial condition into a DP state."""
    if initial_online:
        matches = [i for i, level in enumerate(levels) if abs(level - initial_output) <= _EPS]
        if not matches:
            raise ValidationError(
                f"initial_output = {initial_output!r} is not on the output grid "
                f"{levels!r}; an online unit must start on a grid level"
            )
        uptime = up_cap if initial_uptime is None else initial_uptime
        if uptime < 1:
            raise ValidationError(f"initial_uptime must be >= 1 when online, got {uptime!r}")
        return (_ONLINE, matches[0], min(uptime, up_cap))
    downtime = down_cap if initial_downtime is None else initial_downtime
    if downtime < 1:
        raise ValidationError(f"initial_downtime must be >= 1 when offline, got {downtime!r}")
    return (_OFFLINE, _NO_LEVEL, min(downtime, down_cap))


def _transitions(
    state: _State,
    plant: PlantModel,
    levels: tuple[float, ...],
    *,
    power: float,
    fuel: float,
    temperature: float,
    discount: float,
    up_cap: int,
    down_cap: int,
) -> list[_Transition]:
    """Every feasible action from ``state`` this period (eq. B.1 constraints)."""
    status, level_idx, timer = state
    capacity = plant.max_capacity(temperature)

    def producing_margin(output: float) -> float:
        rate = plant.marginal_heat_rate(output, temperature)
        if not rate > 0:
            raise ValidationError(
                f"heat_rate(q={output!r}, temp={temperature!r}) = {rate!r} must be > 0"
            )
        return output * (power - rate * fuel - plant.variable_om_cost)

    out: list[_Transition] = []

    if status == _OFFLINE:
        downtime = timer
        # Stay off.
        stay = (_OFFLINE, _NO_LEVEL, min(downtime + 1, down_cap))
        out.append((stay, 0.0, 0.0, False, False, False))
        # Start (only after the minimum-down time has elapsed).
        if downtime >= plant.d_shutdown:
            bucket = plant.start_state_for_downtime(downtime)
            start_cash = plant.start_cost(bucket, power, fuel)
            if plant.d_startup == 0:
                c_min_level = levels[0]  # start comes online at minimum stable generation
                cash = producing_margin(c_min_level) - start_cash
                out.append(((_ONLINE, 0, 1), discount * cash, c_min_level, True, True, False))
            else:
                out.append(
                    ((_STARTING, _NO_LEVEL, 1), discount * -start_cash, 0.0, False, True, False)
                )
        return out

    if status == _STARTING:
        lag = timer
        if lag < plant.d_startup:
            out.append(((_STARTING, _NO_LEVEL, lag + 1), 0.0, 0.0, False, False, False))
        else:  # start-up complete: unit reaches c_min this period (cost already paid).
            c_min_level = levels[0]
            margin = discount * producing_margin(c_min_level)
            out.append(((_ONLINE, 0, 1), margin, c_min_level, True, False, False))
        return out

    # status == _ONLINE
    current = levels[level_idx]
    uptime = timer
    for j, target in enumerate(levels):
        if target <= capacity + _EPS and abs(target - current) <= plant.ramp_rate + _EPS:
            out.append(
                (
                    (_ONLINE, j, min(uptime + 1, up_cap)),
                    discount * producing_margin(target),
                    target,
                    True,
                    False,
                    False,
                )
            )
    # Shut down (only after the minimum-run time has elapsed).
    if uptime >= plant.d_min:
        out.append(((_OFFLINE, _NO_LEVEL, 1), 0.0, 0.0, False, False, True))
    return out


def _all_states(
    levels: tuple[float, ...], plant: PlantModel, up_cap: int, down_cap: int
) -> list[_State]:
    """Enumerate the finite state space for backward induction."""
    states: list[_State] = [(_OFFLINE, _NO_LEVEL, d) for d in range(1, down_cap + 1)]
    states += [(_STARTING, _NO_LEVEL, k) for k in range(1, plant.d_startup + 1)]
    states += [(_ONLINE, i, r) for i in range(len(levels)) for r in range(1, up_cap + 1)]
    return states


def dispatch_deterministic(
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
    """Solve the perfect-foresight optimal dispatch of ``plant`` (eq. B.1).

    Exact backward-induction DP over a discretised commitment/output state (see
    the module docstring for the objective, the state space, the discretisation
    and its exactness, and the unit-commitment conventions). All inputs are
    validated before any computation and never mutated.

    Args:
        plant: The operating model (heat-rate curve, capacities, start costs,
            ramp rate, durations).
        power_prices: Power price ``P_t`` per period (may be negative).
        fuel_prices: Fuel price ``G_t`` per period.
        temperatures: Ambient temperature ``S_t`` per period (drives ``HR`` and
            ``c_max``).
        initial_online: Whether the unit is producing entering the horizon.
        initial_output: Output entering the horizon (MW); must be on the grid
            when ``initial_online`` (ignored otherwise).
        initial_uptime: Producing periods already accrued (min-run); defaults to
            "min-run already satisfied". Only used when ``initial_online``.
        initial_downtime: Periods already offline (keys the first start's bucket
            and min-down); must be ``>= 1`` (a unit "not online" has been offline for
            at least one period); defaults to a long, cold, restart-ready downtime.
            Only used when not ``initial_online``.
        output_step: Output-grid spacing (MW); defaults to the ramp rate.
        discount_factors: Per-period discount factors (default all 1.0).

    Returns:
        The optimal :class:`DispatchSchedule`; ``total_value`` is the
        perfect-foresight upper bound of Property 62.

    Raises:
        ValidationError: If the series are empty or of unequal length; if a
            discount factor or ``output_step`` is non-positive; if
            ``c_max(temp) < c_min`` or ``heat_rate(q, temp) ≤ 0`` at a supplied
            temperature; if ``initial_output`` is off-grid while online; if
            ``initial_downtime < 1`` while offline; or if the supplied initial
            condition admits no feasible schedule.
    """
    horizon = _validate_series(power_prices, fuel_prices, temperatures, discount_factors)
    levels = _build_output_grid(plant, temperatures, output_step)
    up_cap = max(plant.d_min, 1)
    down_cap = max(plant.d_shutdown, plant.warm_max_downtime + 1, 1)
    discounts = [1.0] * horizon if discount_factors is None else list(discount_factors)

    states = _all_states(levels, plant, up_cap, down_cap)
    # Backward induction: value[t][state] = best value achievable from ``state``
    # entering period t; the terminal value (period ``horizon``) is 0 everywhere.
    value: list[dict[_State, float]] = [{} for _ in range(horizon)]
    choice: list[dict[_State, _Transition]] = [{} for _ in range(horizon)]
    for t in range(horizon - 1, -1, -1):
        future = value[t + 1] if t + 1 < horizon else None
        for state in states:
            best_value = -math.inf
            best_transition: _Transition | None = None
            for transition in _transitions(
                state,
                plant,
                levels,
                power=power_prices[t],
                fuel=fuel_prices[t],
                temperature=temperatures[t],
                discount=discounts[t],
                up_cap=up_cap,
                down_cap=down_cap,
            ):
                next_state, margin, *_ = transition
                continuation = 0.0 if future is None else future.get(next_state, -math.inf)
                candidate = margin + continuation
                if candidate > best_value:
                    best_value = candidate
                    best_transition = transition
            if best_transition is not None:
                value[t][state] = best_value
                choice[t][state] = best_transition

    initial = _initial_state(
        plant,
        levels,
        initial_online=initial_online,
        initial_output=initial_output,
        initial_uptime=initial_uptime,
        initial_downtime=initial_downtime,
        up_cap=up_cap,
        down_cap=down_cap,
    )
    if initial not in value[0]:
        raise ValidationError(
            "the supplied initial condition admits no feasible schedule over the horizon"
        )

    outputs: list[float] = []
    online: list[bool] = []
    started: list[bool] = []
    stopped: list[bool] = []
    margins: list[float] = []
    state = initial
    for t in range(horizon):
        next_state, margin, output, is_online, is_started, is_stopped = choice[t][state]
        outputs.append(output)
        online.append(is_online)
        started.append(is_started)
        stopped.append(is_stopped)
        margins.append(margin)
        state = next_state

    return DispatchSchedule(
        outputs=tuple(outputs),
        online=tuple(online),
        started=tuple(started),
        stopped=tuple(stopped),
        margins=tuple(margins),
        total_value=math.fsum(margins),
    )
