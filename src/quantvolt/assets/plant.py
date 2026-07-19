"""Thermal-plant operational model.

``PlantModel`` is the value object consumed by the dispatch optimizers
(``quantvolt.assets.dispatch_deterministic`` and ``dispatch_sdp``).
It carries the operating characteristics of Appendix B eq. B.1: the marginal
heat-rate curve ``HR(q, temp)``, minimum stable generation ``c_min``, the
temperature-dependent maximum capacity ``c_max(temp)``, variable O&M, the three
start-cost buckets ``SC``/``FSC``/``PSC`` keyed by cold/warm/hot state, ramp
rate ``RR``, the minimum-run / minimum-down / start-up durations, and the
forced-outage rate ``λ``.

Construct choices (kept as light as faithful)
-----------------------------------------------------------------------
- ``HR(q, temp)`` and ``c_max(temp)`` are **caller-supplied pure callables**
  (``heat_rate`` and ``c_max`` fields). A constant heat rate is only an
  approximation, so the model must admit an arbitrary curve; a 2-D piecewise
  table for ``HR`` and a 1-D one for ``c_max`` would be strictly heavier for no
  extra fidelity. The callables must be pure (no hidden state) — the library
  treats them as data and never mutates them.
- Start costs are the three ``StartCost`` records of a ``StartState``-keyed
  mapping. Each start's cash cost is ``fixed + fuel·G_t + power·P_t`` (the
  ``SC + FSC·G + PSC·P`` term of eq. B.1), with ``fuel`` in MWh_fuel and
  ``power`` in MWh consumed from the grid during the start.

Eager vs. dispatch-time validation
-----------------------------------
Scalar constraints are checked eagerly in ``__post_init__``: ``c_min ≥ 0``,
``RR > 0``, ``variable_om_cost ≥ 0``, the three durations ``≥ 0``,
``0 ≤ λ < 1``, ``0 ≤ hot_max_downtime ≤ warm_max_downtime``, all three start
buckets present, and each start-cost component ``≥ 0``. The curve constraints
``c_max(temp) ≥ c_min`` and ``HR(q, temp) > 0`` cannot be checked over all
temperatures for an opaque callable, so they are checked (a) eagerly at each
temperature in the optional ``representative_temperatures`` smoke set, and
(b) exhaustively at dispatch time for every temperature actually supplied
(see ``quantvolt.assets.dispatch_deterministic.dispatch_deterministic``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from .._validation import require_non_negative, require_positive
from ..exceptions import ValidationError

# HR(q, temp) -> heat rate in MWh_fuel / MWh_power; c_max(temp) -> capacity in MW.
HeatRateCurve = Callable[[float, float], float]
MaxCapacityCurve = Callable[[float], float]


class StartState(StrEnum):
    """Thermal state of a stopped unit, keying the start-up cost (eq. B.1).

    ``HOT`` follows a short shutdown (the boiler is still warm; cheapest start),
    ``COLD`` a long one (most expensive), ``WARM`` in between. The mapping from
    elapsed downtime to a state is :meth:`PlantModel.start_state_for_downtime`.
    """

    COLD = "cold"
    WARM = "warm"
    HOT = "hot"


@dataclass(frozen=True, slots=True)
class StartCost:
    """One start-up's cost components (the ``SC``/``FSC``/``PSC`` triple of eq. B.1).

    ``fixed`` is the currency cost ``SC``; ``fuel`` is the fuel burned during the
    start ``FSC`` (MWh_fuel, priced at that period's fuel price); ``power`` is the
    grid power drawn during the start ``PSC`` (MWh, priced at that period's power
    price). All three are non-negative — a start never earns money.
    """

    fixed: float
    fuel: float
    power: float

    def __post_init__(self) -> None:
        require_non_negative("StartCost.fixed", self.fixed)
        require_non_negative("StartCost.fuel", self.fuel)
        require_non_negative("StartCost.power", self.power)


@dataclass(frozen=True, slots=True)
class PlantModel:
    """Operating model of a dispatchable thermal unit (eq. B.1 parameters).

    Durations (``d_min``, ``d_shutdown``, ``d_startup``, the ``*_max_downtime``
    thresholds) are counted in dispatch periods — whatever resolution the
    caller's price/temperature series use.

    Attributes:
        heat_rate: Marginal heat-rate curve ``HR(q, temp)`` (MWh_fuel/MWh_power).
        c_min: Minimum stable generation while online (MW), ``≥ 0``.
        c_max: Temperature-dependent maximum capacity ``c_max(temp)`` (MW).
        variable_om_cost: Variable O&M ``VOM`` per MWh, ``≥ 0``.
        start_costs: One :class:`StartCost` per :class:`StartState`; all three
            buckets required.
        ramp_rate: Ramp rate ``RR`` (MW per period), ``> 0``.
        d_min: Minimum-run duration (periods) once producing, ``≥ 0``.
        d_shutdown: Minimum-down duration (periods) before a restart, ``≥ 0``.
        d_startup: Start-up lag (periods) from the start decision to first
            production, ``≥ 0``.
        outage_rate: Forced-outage rate ``λ`` in ``[0, 1)`` (used by the
            stochastic model; deterministic dispatch assumes full availability).
        hot_max_downtime: Downtime ``≤`` this keys a ``HOT`` start.
        warm_max_downtime: Downtime ``≤`` this (but ``>`` hot) keys a ``WARM``
            start; anything longer keys a ``COLD`` start. Must be ``≥
            hot_max_downtime``.
        representative_temperatures: Optional smoke-test temperatures at which
            ``c_max(temp) ≥ c_min`` and ``HR(c_min, temp) > 0`` are checked
            eagerly. Empty by default (curve feasibility is then verified only
            at dispatch time, against the temperatures actually supplied).
    """

    heat_rate: HeatRateCurve
    c_min: float
    c_max: MaxCapacityCurve
    variable_om_cost: float
    start_costs: Mapping[StartState, StartCost]
    ramp_rate: float
    d_min: int
    d_shutdown: int
    d_startup: int
    outage_rate: float
    hot_max_downtime: int
    warm_max_downtime: int
    representative_temperatures: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        require_non_negative("c_min", self.c_min)
        require_positive("ramp_rate", self.ramp_rate)
        require_non_negative("variable_om_cost", self.variable_om_cost)
        require_non_negative("d_min", self.d_min)
        require_non_negative("d_shutdown", self.d_shutdown)
        require_non_negative("d_startup", self.d_startup)
        if not (0.0 <= self.outage_rate < 1.0):
            raise ValidationError(f"outage_rate must be in [0, 1), got {self.outage_rate!r}")
        require_non_negative("hot_max_downtime", self.hot_max_downtime)
        if self.warm_max_downtime < self.hot_max_downtime:
            raise ValidationError(
                "warm_max_downtime must be >= hot_max_downtime, got "
                f"warm_max_downtime={self.warm_max_downtime!r}, "
                f"hot_max_downtime={self.hot_max_downtime!r}"
            )
        missing = [state for state in StartState if state not in self.start_costs]
        if missing:
            raise ValidationError(
                "start_costs must define every StartState; missing "
                + ", ".join(repr(state.value) for state in missing)
            )
        self._validate_representative_temperatures()

    def _validate_representative_temperatures(self) -> None:
        """Eagerly sanity-check the curves at the caller's smoke temperatures."""
        for temp in self.representative_temperatures:
            capacity = self.c_max(temp)
            if capacity < self.c_min:
                raise ValidationError(
                    f"c_max(temp={temp!r}) = {capacity!r} must be >= c_min = {self.c_min!r}"
                )
            rate = self.heat_rate(self.c_min, temp)
            if not rate > 0:
                raise ValidationError(
                    f"heat_rate(q={self.c_min!r}, temp={temp!r}) = {rate!r} must be > 0"
                )

    def start_state_for_downtime(self, downtime: int) -> StartState:
        """Classify a stopped unit's start-up state from elapsed downtime (periods)."""
        if downtime <= self.hot_max_downtime:
            return StartState.HOT
        if downtime <= self.warm_max_downtime:
            return StartState.WARM
        return StartState.COLD

    def start_cost(self, state: StartState, power_price: float, fuel_price: float) -> float:
        """Cash cost of one start in ``state``: ``SC + FSC·fuel + PSC·power`` (eq. B.1)."""
        cost = self.start_costs[state]
        return cost.fixed + cost.fuel * fuel_price + cost.power * power_price

    def marginal_heat_rate(self, output: float, temperature: float) -> float:
        """``HR(q, temp)`` — the plant's own curve, evaluated for the caller."""
        return self.heat_rate(output, temperature)

    def max_capacity(self, temperature: float) -> float:
        """``c_max(temp)`` — the plant's own temperature-dependent ceiling."""
        return self.c_max(temperature)
