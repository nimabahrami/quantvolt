"""Stochastic dispatch valuation (Task 73; Req 21.1, 21.2, 21.5, 21.6; Properties 62-63).

``dispatch_value`` computes the risk-adjusted expected value of a thermal unit by
stochastic dynamic programming -- the Bellman recursion of Appendix B eqs. B.2-B.3
solved by backward induction over the *same* commitment state machine as
:mod:`quantvolt.assets.dispatch_deterministic`. Two solution methods are offered
(Req 21.2): ``method="tree"`` (recombining lattice / binomial-forest backward
induction) and ``method="lsm"`` (least-squares Monte Carlo, Longstaff-Schwartz).
Both return a :class:`DispatchResult` carrying the value and the four critical
exercise surfaces of eq. B.5 (start-up / shutdown / ramp-up / ramp-down).

Relationship to the deterministic benchmark
--------------------------------------------
The perfect-foresight optimum (:func:`dispatch_deterministic`, eq. B.1) is the
upper bound of any non-anticipating policy: valuing each realised path with
perfect foresight and averaging bounds the stochastic value from above
(Property 62). This module reuses the deterministic module's *private* state
machine (the status codes, output grid, initial-state translation and the
feasible-transition enumerator ``_transitions``) so the two solvers optimise over
an identical feasible set -- the reuse, not a re-implementation, is what makes
Property 62 hold exactly on shared conventions. Only the immediate-cash-flow
arithmetic is recomputed here (vectorised over scenarios); the intricate
feasibility logic is never duplicated. Should ``dispatch_deterministic`` ever
need to change those helpers, this module must be revisited (documented coupling).

Reused state machine (see ``dispatch_deterministic`` for the full account)
--------------------------------------------------------------------------
State ``(status, output-level index, timer)`` with ``status`` offline / starting /
online; a **start** brings the unit online at ``c_min`` and pays the cold/warm/hot
start cost; ``d_startup`` delays first production; ``d_min`` / ``d_shutdown`` gate
shutdown / restart; a running unit ramps by at most ``RR`` within
``[c_min, c_max(S_t)]``. Discounting follows the deterministic convention: each
period's whole cash flow is scaled by ``discount_factors[t]`` (to-today factors),
so the Bellman continuation is the plain (undiscounted-further) sum of future
discounted cash flows -- equivalent to eq. B.2's stepwise ``e^{-r dt}`` when the
factors are ``e^{-r t dt}``.

The Markov state and the on-peak / off-peak split (Req 21.6, eq. B.4)
---------------------------------------------------------------------
Appendix B stresses that an hourly power-price *sequence* is **not** Markovian:
tomorrow's on-peak price depends on recent on-peak prices, only weakly on the
current off-peak price. The fix (eq. B.4) is to carry **two** power spot processes
-- one on-peak, one off-peak -- as separate state coordinates, restoring the
Markov property. :class:`DispatchFactorModel` implements the split *in the factor
definition*: ``power_on_index`` and ``power_off_index`` name two coordinates of the
simulated log-forward state (they may coincide when every period shares a peak
kind), and ``peak_kinds[t]`` selects which coordinate is the *active* spot price
for period ``t``. Both coordinates evolve on every step and both enter the LSM
regression basis / the lattice, so the conditioning information is the full
Markov state ``(P_on, P_off, G, ...)`` -- exactly the eq. B.4 construction.

Risk-adjusted expectation (Req 21.5, consistent with Req 19)
------------------------------------------------------------
eq. B.2 optimises under a *risk-adjusted* expectation ``E*``. The factor model's
per-step drift ``mu`` is therefore tagged with
:class:`~quantvolt.numerics.risk_adjustment.DriftKind`, and ``dispatch_value``
requires :attr:`~quantvolt.numerics.risk_adjustment.DriftKind.RISK_NEUTRAL` -- the
pricing / valuation measure in this library's vocabulary ("arbitrage-free
valuation only"). A :attr:`DriftKind.PHYSICAL` drift is **rejected**: valuing a
not-fully-hedgeable asset under the real-world measure would overstate its value,
the very failure this optimiser guards against. The caller forms the risk-adjusted
drift ``mu* = mu - lambda_S * sigma`` (eq. 10.5, via
:func:`~quantvolt.numerics.risk_adjustment.risk_adjusted_drift`) -- for a fully
tradable factor this collapses to the risk-neutral ``r - y`` -- and tags it
``RISK_NEUTRAL`` to signal "this drift is under the pricing measure ``E*``".

Forced outages (the outage seam)
--------------------------------
An optional per-period ``availability`` vector ``M`` in ``(0, 1]`` derates the
capacity ceiling to ``M_t * c_max(S_t)`` for period ``t`` (eq. B.1's ``M_ti``). A
caller with an :class:`~quantvolt.market.outages.OutageDataset` supplies
``M_t = dataset.forced_outage_multiplier(period_hours, installed_capacity_mw)``
(design 2.23). Online outputs above the derated ceiling become infeasible that
period; if the derated ceiling falls below ``c_min`` the unit is forced offline
(eq. B.1 constraint 5).

Critical exercise surfaces (eq. B.5)
------------------------------------
``K_i(...)`` are the boundaries analogous to an American option's critical price.
Each surface is represented as a per-period tuple of **critical spark-spread
thresholds** (EUR/MWh_power at ``c_min``), estimated -- in the spirit of the
Schwartz-Litzenberger regressed boundary (eq. B.6) -- as the zero-crossing of a
linear fit of the "more-generation vs. less-generation" value advantage against
the spark spread, across the period's scenarios (paths for LSM, nodes for the
tree). By convention each threshold is the spark spread at which the
more-generation action becomes preferred; ``float('nan')`` marks a decision that
does not arise in the period (e.g. a ramp threshold with a single online level).
Hysteresis makes ``start_surface >= shutdown_surface`` (a unit keeps running at
spreads below the level at which it would incur a start cost to start up).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from statistics import NormalDist
from typing import NamedTuple

import numpy as np
import numpy.typing as npt

from .._validation import require_integer_at_least, require_length
from ..exceptions import ValidationError
from ..numerics.monte_carlo import (
    CorrelatedSimulationRequest,
    simulate_correlated_forwards,
    simulate_correlated_term_structure,
)
from ..numerics.risk_adjustment import DriftKind
from .dispatch_deterministic import (
    _EPS,
    _NO_LEVEL,
    _OFFLINE,
    _ONLINE,
    _all_states,
    _build_output_grid,
    _initial_state,
    _State,
    _transitions,
)
from .plant import PlantModel, StartState

# Slope below which a critical-surface linear fit is treated as flat (no crossing).
_SURFACE_SLOPE_EPS = 1e-9

Vector = npt.NDArray[np.float64]


class PeakKind(StrEnum):
    """Which power spot process is active in a period (the eq. B.4 Markov split)."""

    ON_PEAK = "on_peak"
    OFF_PEAK = "off_peak"


class FactorTransform(StrEnum):
    """Transform a simulated state coordinate into a physical observable."""

    IDENTITY = "identity"
    EXP = "exp"
    LOGISTIC = "logistic"


def _logistic(raw: Vector) -> Vector:
    """Numerically safe logistic ``1/(1+exp(-raw))``, clamped to ``(0, 1]``.

    ``exp(-raw)`` overflows to ``inf`` for ``raw <~ -709.8`` (float64), so the plain
    ratio underflows to *exactly* ``0.0`` there -- and an availability mapped through
    :attr:`FactorTransform.LOGISTIC` must stay strictly positive (``_scenario_context``
    requires ``(0, 1]``, eq. B.1's ``M_ti``): a hard ``0.0`` would otherwise abort the
    whole valuation mid-simulation on an ordinary (if extreme) simulated draw. Treat
    the underflow as the smallest representable positive derating,
    ``np.finfo(np.float64).tiny``, rather than exact zero -- the derated capacity is
    then negligible but the (0, 1] invariant holds and the simulation completes. The
    overflow in ``exp(-raw)`` is expected and handled here, so it is suppressed
    locally rather than surfacing a spurious warning.
    """
    with np.errstate(over="ignore"):
        logistic = 1.0 / (1.0 + np.exp(-raw))
    return np.clip(logistic, np.finfo(np.float64).tiny, 1.0)


@dataclass(frozen=True, slots=True)
class PhysicalFactorMapping:
    """Map one simulated coordinate to temperature or availability."""

    index: int
    transform: FactorTransform = FactorTransform.IDENTITY
    scale: float = 1.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValidationError(f"index must be >= 0, got {self.index}")
        if not (math.isfinite(self.scale) and math.isfinite(self.offset)):
            raise ValidationError("scale and offset must be finite")
        if not isinstance(self.transform, FactorTransform):
            raise ValidationError(f"transform must be a FactorTransform, got {self.transform!r}")

    def values(self, state: Vector) -> Vector:
        raw = state[:, self.index]
        transforms: dict[FactorTransform, Callable[[Vector], Vector]] = {
            FactorTransform.IDENTITY: lambda value: value,
            FactorTransform.EXP: np.exp,
            FactorTransform.LOGISTIC: _logistic,
        }
        return self.offset + self.scale * transforms[self.transform](raw)


@dataclass(frozen=True, slots=True)
class MonteCarloEvaluation:
    """Independent policy-evaluation controls for dispatch LSM."""

    seed: int
    path_count: int
    confidence_level: float = 0.95


@dataclass(frozen=True, slots=True)
class DispatchDiagnostics:
    """Sampling and regression evidence for an LSM dispatch value.

    Attributes:
        training_value: Mean realised value on the training paths (before the
            independent policy-evaluation re-simulation).
        evaluation_standard_error: Monte Carlo standard error of ``value`` (the
            evaluation-path mean). Computed by :func:`_standard_error`, which accounts
            for antithetic pairing when the evaluation paths use it (the default):
            the estimator is ``std(pair_means, ddof=1) / sqrt(n_pairs)`` over the
            antithetic pair means, not the naive iid formula over every path (which
            would overstate the SE by ignoring the pairs' negative within-pair
            correlation).
        confidence_interval: Normal-approximation interval around ``value`` at
            ``evaluation.confidence_level``, built from ``evaluation_standard_error``.
        training_path_count: Number of training paths.
        evaluation_path_count: Number of independent policy-evaluation paths.
        max_regression_condition: Worst LSM regression design-matrix condition number
            across periods (and, when a state's regression is masked to its finite
            paths, across states within a period too).
    """

    training_value: float
    evaluation_standard_error: float
    confidence_interval: tuple[float, float]
    training_path_count: int
    evaluation_path_count: int
    max_regression_condition: float


@dataclass(frozen=True, slots=True)
class DispatchFactorModel:
    """Risk-adjusted factor dynamics driving stochastic dispatch (eqs. B.2-B.4).

    The stochastic factors are correlated log-forwards evolved by the Task-62
    engine ``ΔZ = mu + L·ε`` (GBM). At least a power and a gas coordinate are
    required; the on-peak / off-peak Markov split (eq. B.4) is expressed by naming
    two power coordinates (which may coincide) and a per-period peak label.
    Temperature is supplied deterministically (``temperatures``) -- it drives
    ``HR`` and ``c_max`` but is not simulated here; a stochastic temperature factor
    would simply be another simulated coordinate added to the basis.

    Attributes:
        log_forward0: Initial log-forward vector ``z0 = log F(0, ·)`` over the
            flattened factor state, dimension ``D`` (``>= 2``).
        drift: Per-step drift ``mu`` (length ``D``). Must be the **risk-adjusted**
            (pricing-measure) drift and is tagged by ``drift_kind``.
        covariance: Per-step covariance ``C`` (``D x D``), assembled by
            :func:`~quantvolt.numerics.monte_carlo.build_covariance`.
        drift_kind: Measure tag on ``drift``; ``dispatch_value`` requires
            :attr:`DriftKind.RISK_NEUTRAL` (Req 21.5).
        peak_kinds: Per-period :class:`PeakKind` selecting the active power
            coordinate; its length is the dispatch horizon ``H`` (``>= 1``).
        temperatures: Per-period ambient temperature ``S_t`` (length ``H``).
        power_on_index: Coordinate of ``z0`` used as the on-peak power spot.
        power_off_index: Coordinate used as the off-peak power spot (may equal
            ``power_on_index`` when the horizon is single-regime).
        gas_index: Coordinate used as the gas / fuel price.
    """

    log_forward0: Vector
    drift: Vector
    covariance: Vector
    drift_kind: DriftKind
    peak_kinds: tuple[PeakKind, ...]
    temperatures: tuple[float, ...]
    power_on_index: int = 0
    power_off_index: int = 1
    gas_index: int = 2
    temperature_factor: PhysicalFactorMapping | None = None
    availability_factor: PhysicalFactorMapping | None = None

    def __post_init__(self) -> None:
        # Defensive snapshot: copy the caller's arrays and freeze them, so the value
        # object can never alias (or be used to mutate) caller-owned buffers.
        z0 = np.array(self.log_forward0, dtype=np.float64, copy=True)
        mu = np.array(self.drift, dtype=np.float64, copy=True)
        cov = np.array(self.covariance, dtype=np.float64, copy=True)
        for array in (z0, mu, cov):
            array.setflags(write=False)
        object.__setattr__(self, "log_forward0", z0)
        object.__setattr__(self, "drift", mu)
        object.__setattr__(self, "covariance", cov)
        object.__setattr__(self, "peak_kinds", tuple(self.peak_kinds))
        object.__setattr__(self, "temperatures", tuple(float(t) for t in self.temperatures))

        if z0.ndim != 1 or z0.shape[0] < 2:
            raise ValidationError(
                f"log_forward0 must be 1-D with >= 2 factors, got shape {z0.shape}"
            )
        d = int(z0.shape[0])
        horizon = len(self.peak_kinds)
        if mu.shape not in ((d,), (horizon, d)):
            raise ValidationError(
                f"drift must have shape ({d},) or ({horizon}, {d}), got {mu.shape}"
            )
        if cov.shape not in ((d, d), (horizon, d, d)):
            raise ValidationError(
                f"covariance must have shape ({d}, {d}) or ({horizon}, {d}, {d}), got {cov.shape}"
            )
        if not (bool(np.all(np.isfinite(z0))) and bool(np.all(np.isfinite(mu)))):
            raise ValidationError("log_forward0 and drift must be finite")
        for name, index in (
            ("power_on_index", self.power_on_index),
            ("power_off_index", self.power_off_index),
            ("gas_index", self.gas_index),
        ):
            if not (0 <= index < d):
                raise ValidationError(f"{name} must be in [0, {d}), got {index!r}")
        for name, mapping in (
            ("temperature_factor", self.temperature_factor),
            ("availability_factor", self.availability_factor),
        ):
            if mapping is not None and not (0 <= mapping.index < d):
                raise ValidationError(f"{name}.index must be in [0, {d}), got {mapping.index}")
        if len(self.peak_kinds) == 0:
            raise ValidationError("peak_kinds must be non-empty (the dispatch horizon)")
        if len(self.temperatures) != len(self.peak_kinds):
            raise ValidationError(
                "temperatures and peak_kinds must have the same length (horizon), got "
                f"{len(self.temperatures)} and {len(self.peak_kinds)}"
            )

    @property
    def horizon(self) -> int:
        """Number of dispatch periods ``H``."""
        return len(self.peak_kinds)

    def active_power_index(self, period: int) -> int:
        """Power coordinate active in ``period`` (on-peak vs off-peak, eq. B.4)."""
        if self.peak_kinds[period] is PeakKind.ON_PEAK:
            return self.power_on_index
        return self.power_off_index

    def simulate(self, seed: int, path_count: int, *, antithetic: bool = True) -> Vector:
        """Simulate ``(n_paths, H + 1, D)`` log-forward paths (Task-62 engine).

        Record 0 is ``log_forward0``; record ``t + 1`` holds the prices realised in
        dispatch period ``t``. Deterministic under ``seed`` (Req 11.2), so a caller
        (or a Property-62 test) can reproduce the exact scenario set.
        """
        if self.drift.ndim == 1 and self.covariance.ndim == 2:
            return simulate_correlated_forwards(
                self.log_forward0,
                self.drift,
                self.covariance,
                steps=self.horizon,
                path_count=path_count,
                seed=seed,
                antithetic=antithetic,
            )
        drift = np.broadcast_to(self.drift, (self.horizon, self.log_forward0.size))
        covariance = np.broadcast_to(
            self.covariance, (self.horizon, self.log_forward0.size, self.log_forward0.size)
        )
        return simulate_correlated_term_structure(
            CorrelatedSimulationRequest(
                self.log_forward0,
                drift,
                covariance,
                path_count,
                seed,
                antithetic=antithetic,
            )
        )


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Stochastic dispatch value and the eq. B.5 critical exercise surfaces.

    Attributes:
        value: Risk-adjusted expected plant value (eq. B.3), a to-today NPV.
        start_surface: Per-period critical spark spread above which starting up is
            optimal (from a cold, restart-ready unit).
        shutdown_surface: Per-period critical spark spread above which continuing
            to run beats shutting down (a running unit shuts down below it).
        rampup_surface: Per-period critical spark spread above which ramping up
            from ``c_min`` beats holding.
        rampdown_surface: Per-period critical spark spread above which holding the
            top feasible level beats ramping down.

    Each surface is a length-``H`` tuple of EUR/MWh_power thresholds (measured at
    ``c_min``); ``float('nan')`` marks a decision that does not arise in the period.
    """

    value: float
    start_surface: tuple[float, ...]
    shutdown_surface: tuple[float, ...]
    rampup_surface: tuple[float, ...]
    rampdown_surface: tuple[float, ...]
    diagnostics: DispatchDiagnostics | None = None


class _Move(NamedTuple):
    """A feasible per-period action, decoupled from any scenario's prices.

    ``bucket`` is the cold/warm/hot start category when this action initiates a
    start (charging that bucket's cost), else ``None``. The immediate cash flow is
    recomputed per scenario by :func:`_move_cash` from these fields -- the *what is
    feasible* decision comes wholesale from the reused ``_transitions``.
    """

    next_state: _State
    output: float
    online: bool
    started: bool
    stopped: bool
    bucket: StartState | None


def _moves(
    state: _State,
    plant: PlantModel,
    levels: tuple[float, ...],
    temperature: float,
    eff_capacity: float,
    up_cap: int,
    down_cap: int,
) -> list[_Move]:
    """Feasible actions from ``state`` this period, filtered by derated capacity.

    Structure comes from the reused deterministic ``_transitions`` (feasibility,
    ramp, min-run/-down, start bucketing); the per-scenario cash flow is discarded
    here (dummy unit prices) and recomputed vectorised. Online actions producing
    above the forced-outage-derated ``eff_capacity`` are dropped (eq. B.1 ``M_ti``).

    Forced outage below ``c_min`` while min-run-locked (the ``_moves``-level fallback
    for eq. B.1 constraint 5): a running unit whose min-run timer has not yet reached
    ``d_min`` cannot use ``_transitions``'s own shutdown transition, so if the derate
    also drops every ramp target below ``eff_capacity`` the state machine would offer
    *no* feasible action at all -- a dead end the reused deterministic state space
    never has to consider (it assumes full availability, Req 21.4). A physical
    derating below ``c_min`` overrides the min-run rule (the unit cannot keep
    producing regardless of the timer), so when no ordinary move survives the filter
    a forced shutdown at zero cash is appended, mirroring the already-documented
    "the unit is forced offline" convention for the offline/on-grid case. This is
    used only as a last resort: whenever any ordinary transition (including the
    state machine's own shutdown) survives, it is preferred untouched.
    """
    downtime = state[2] if state[0] == _OFFLINE else None
    moves: list[_Move] = []
    for next_state, _margin, output, online, started, stopped in _transitions(
        state,
        plant,
        levels,
        power=1.0,
        fuel=1.0,
        temperature=temperature,
        discount=1.0,
        up_cap=up_cap,
        down_cap=down_cap,
    ):
        if online and output > eff_capacity + _EPS:
            continue
        bucket = (
            plant.start_state_for_downtime(downtime) if (started and downtime is not None) else None
        )
        moves.append(_Move(next_state, output, online, started, stopped, bucket))
    if not moves and state[0] == _ONLINE:
        moves.append(_Move((_OFFLINE, _NO_LEVEL, 1), 0.0, False, False, True, None))
    return moves


def _move_cash(
    move: _Move, plant: PlantModel, temperature: float, discount: float, power: Vector, gas: Vector
) -> Vector:
    """Immediate discounted cash flow of ``move`` across scenarios (eq. B.1 integrand).

    ``q·(P - HR(q)·G - VOM) - [start]·(SC + FSC·G + PSC·P)`` scaled by ``discount``.
    """
    cash = np.zeros_like(power)
    if move.online:
        rate = plant.marginal_heat_rate(move.output, temperature)
        cash = cash + move.output * (power - rate * gas - plant.variable_om_cost)
    if move.bucket is not None:
        start = plant.start_costs[move.bucket]
        cash = cash - (start.fixed + start.fuel * gas + start.power * power)
    return discount * cash


def _poly_basis(z: Vector, degree: int = 2) -> Vector:
    """Polynomial regression basis for the LSM continuation (eq. B.6 / Schwartz-Litzenberger).

    ``z`` is ``(M, D)`` log-factors; the returned design matrix conditions the LSM
    continuation regression on the full Markov state (all factors, incl. both power
    coordinates).

    At the default ``degree=2`` this is *exactly* the historical construction --
    intercept, linears, squares, then pairwise cross terms, in that column order --
    kept verbatim so results at the default are bit-for-bit unchanged. For any other
    ``degree`` the basis generalizes to every monomial of total degree ``1..degree``
    (via multiset combinations of the factor indices), intercept first.
    """
    m, d = z.shape
    if degree == 2:
        columns: list[Vector] = [np.ones(m, dtype=np.float64)]
        columns.extend(z[:, k] for k in range(d))
        columns.extend(z[:, k] * z[:, k] for k in range(d))
        columns.extend(z[:, i] * z[:, j] for i in range(d) for j in range(i + 1, d))
        return np.column_stack(columns)

    columns = [np.ones(m, dtype=np.float64)]
    for total_degree in range(1, degree + 1):
        for exponents in itertools.combinations_with_replacement(range(d), total_degree):
            term = np.ones(m, dtype=np.float64)
            for index in exponents:
                term = term * z[:, index]
            columns.append(term)
    return np.column_stack(columns)


def _threshold(spread: Vector, advantage: Vector) -> float:
    """Spark spread at which ``advantage`` (more-gen minus less-gen value) crosses 0.

    Linear fit ``advantage ≈ a + b·spread``; the critical spread is ``-a / b``.
    Returns ``nan`` for a flat fit (``|b|`` below tolerance) or too few points.
    """
    if spread.shape[0] < 2:
        return math.nan
    slope, intercept = np.polyfit(spread, advantage, 1)
    if abs(slope) < _SURFACE_SLOPE_EPS or not math.isfinite(slope):
        return math.nan
    return float(-intercept / slope)


def _period_surfaces(
    plant: PlantModel,
    levels: tuple[float, ...],
    temperature: float,
    eff_capacity: float,
    discount: float,
    up_cap: int,
    down_cap: int,
    power: Vector,
    gas: Vector,
    spread: Vector,
    continuation: dict[_State, Vector],
) -> tuple[float, float, float, float]:
    """The four eq. B.5 critical spreads for one period, from a continuation oracle.

    ``continuation[ns]`` is the (regressed or lattice-exact) value-to-go of entering
    the next period in state ``ns``, aligned with the scenario axis of
    ``power``/``gas``/``spread``. Each threshold is the zero-crossing of the
    more-generation advantage; missing decisions yield ``nan``.
    """

    def value_of(move: _Move) -> Vector | None:
        if move.next_state not in continuation:
            return None
        return (
            _move_cash(move, plant, temperature, discount, power, gas)
            + continuation[move.next_state]
        )

    start_thr = shutdown_thr = rampup_thr = rampdown_thr = math.nan

    # Start-up: from a cold, restart-ready offline unit -- start vs stay off.
    off_moves = _moves(
        (_OFFLINE, _NO_LEVEL, down_cap), plant, levels, temperature, eff_capacity, up_cap, down_cap
    )
    stay = next((m for m in off_moves if not m.started), None)
    start = next((m for m in off_moves if m.started), None)
    if stay is not None and start is not None:
        q_stay, q_start = value_of(stay), value_of(start)
        if q_stay is not None and q_start is not None:
            start_thr = _threshold(spread, q_start - q_stay)

    # Running decisions from an online, min-run-satisfied unit at c_min.
    on_moves = _moves(
        (_ONLINE, 0, up_cap), plant, levels, temperature, eff_capacity, up_cap, down_cap
    )
    online_values = [value for m in on_moves if m.online and (value := value_of(m)) is not None]
    stop = next((m for m in on_moves if m.stopped), None)
    if online_values and stop is not None and (q_stop := value_of(stop)) is not None:
        q_run = np.max(np.stack(online_values), axis=0)
        shutdown_thr = _threshold(spread, q_run - q_stop)

    hold_low = next((m for m in on_moves if m.online and m.output == levels[0]), None)
    ramp_up = next(
        (m for m in on_moves if m.online and len(levels) > 1 and m.output == levels[1]), None
    )
    if hold_low is not None and ramp_up is not None:
        q_hold, q_up = value_of(hold_low), value_of(ramp_up)
        if q_hold is not None and q_up is not None:
            rampup_thr = _threshold(spread, q_up - q_hold)

    # Ramp-down: from the top feasible level -- hold vs step down.
    top_idx = max((i for i, level in enumerate(levels) if level <= eff_capacity + _EPS), default=0)
    if top_idx > 0:
        top_moves = _moves(
            (_ONLINE, top_idx, up_cap), plant, levels, temperature, eff_capacity, up_cap, down_cap
        )
        hold_high = next((m for m in top_moves if m.online and m.output == levels[top_idx]), None)
        ramp_down = next(
            (m for m in top_moves if m.online and m.output == levels[top_idx - 1]), None
        )
        if hold_high is not None and ramp_down is not None:
            q_high, q_down = value_of(hold_high), value_of(ramp_down)
            if q_high is not None and q_down is not None:
                rampdown_thr = _threshold(spread, q_high - q_down)

    return start_thr, shutdown_thr, rampup_thr, rampdown_thr


def _period_context(
    factor_model: DispatchFactorModel,
    plant: PlantModel,
    period: int,
    power: Vector,
    gas: Vector,
    availability: Sequence[float] | None,
) -> tuple[float, float, Vector]:
    """Return ``(temperature, effective_capacity, spark_spread)`` for a period."""
    temperature = factor_model.temperatures[period]
    ceiling = plant.max_capacity(temperature)
    eff_capacity = ceiling if availability is None else availability[period] * ceiling
    spread = (
        power - plant.marginal_heat_rate(plant.c_min, temperature) * gas - plant.variable_om_cost
    )
    return temperature, eff_capacity, spread


def _scenario_context(
    factor_model: DispatchFactorModel,
    plant: PlantModel,
    period: int,
    state: Vector,
    power: Vector,
    gas: Vector,
    availability: Sequence[float] | None,
) -> tuple[Vector, Vector, Vector]:
    """Return pathwise temperature, available capacity, and spark spread."""
    count = state.shape[0]
    temperature = (
        np.full(count, factor_model.temperatures[period], dtype=np.float64)
        if factor_model.temperature_factor is None
        else factor_model.temperature_factor.values(state)
    )
    if not bool(np.all(np.isfinite(temperature))):
        raise ValidationError("temperature_factor produced non-finite values")
    ceiling = np.fromiter(
        (plant.max_capacity(float(value)) for value in temperature), dtype=np.float64, count=count
    )
    availability_values = np.ones(count, dtype=np.float64)
    if availability is not None:
        availability_values *= availability[period]
    if factor_model.availability_factor is not None:
        availability_values *= factor_model.availability_factor.values(state)
    if not bool(np.all((availability_values > 0.0) & (availability_values <= 1.0))):
        raise ValidationError("availability_factor must produce values in (0, 1]")
    capacity = ceiling * availability_values
    heat_rate = np.fromiter(
        (plant.marginal_heat_rate(plant.c_min, float(value)) for value in temperature),
        dtype=np.float64,
        count=count,
    )
    spread = power - heat_rate * gas - plant.variable_om_cost
    return temperature, capacity, spread


def _scenario_cash(
    move: _Move,
    plant: PlantModel,
    temperature: Vector,
    capacity: Vector,
    discount: float,
    power: Vector,
    gas: Vector,
) -> Vector:
    """Pathwise immediate cash, with infeasible outputs marked negative infinity."""
    cash = np.zeros_like(power)
    if move.online:
        rates = np.fromiter(
            (plant.marginal_heat_rate(move.output, float(value)) for value in temperature),
            dtype=np.float64,
            count=temperature.size,
        )
        cash = move.output * (power - rates * gas - plant.variable_om_cost)
        cash = np.where(move.output <= capacity + _EPS, cash, -np.inf)
    if move.bucket is not None:
        start = plant.start_costs[move.bucket]
        cash = cash - (start.fixed + start.fuel * gas + start.power * power)
    return discount * cash


def _standard_error(values: Vector, antithetic: bool) -> float:
    """Monte Carlo standard error of ``mean(values)``, honest about antithetic pairing.

    When ``antithetic`` is on, ``values`` are interleaved ``(plus, minus)`` mirror
    pairs -- record ``2k`` is the ``+eps`` leg simulated by
    :func:`~quantvolt.numerics.monte_carlo.simulate_correlated_forwards` /
    ``simulate_correlated_term_structure``, record ``2k + 1`` its ``-eps`` mirror (the
    Rust engine's own convention, ``rust/src/paths.rs``). Treating every draw as an
    independent observation overstates the standard error, because within-pair draws
    are negatively correlated by construction rather than independent: the correct
    estimator is that of the ``n / 2`` **pair means** (each pair mean is one
    approximately-independent antithetic-variance-reduced draw), giving
    ``std(pair_means, ddof=1) / sqrt(n_pairs)``. With ``antithetic`` off every draw is
    independent and the usual ``std(values, ddof=1) / sqrt(n)`` applies.
    """
    if antithetic:
        pair_means = 0.5 * (values[0::2] + values[1::2])
        if pair_means.size > 1:
            return float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
        return 0.0
    if values.size > 1:
        return float(np.std(values, ddof=1) / math.sqrt(values.size))
    return 0.0


def _dispatch_lsm(
    plant: PlantModel,
    factor_model: DispatchFactorModel,
    levels: tuple[float, ...],
    states: list[_State],
    initial: _State,
    discounts: list[float],
    availability: Sequence[float] | None,
    up_cap: int,
    down_cap: int,
    seed: int,
    path_count: int,
    evaluation: MonteCarloEvaluation | None,
    antithetic: bool,
    regression_basis_degree: int,
) -> DispatchResult:
    """Least-squares Monte Carlo backward induction (eqs. B.2-B.3, B.6).

    ``seed`` / ``path_count`` drive the simulation; the signature matches
    :func:`_dispatch_tree` so both are selected through one dispatch table.
    """
    horizon = factor_model.horizon
    paths = factor_model.simulate(seed, path_count, antithetic=antithetic)
    n_paths = int(paths.shape[0])

    # Terminal layer: value 0 in every state (no salvage). Realised value-to-go and
    # the continuation used for decisions are kept separately per Longstaff-Schwartz.
    realized: dict[_State, Vector] = {s: np.zeros(n_paths) for s in states}
    surfaces: list[tuple[float, float, float, float]] = []
    policy_coefficients: list[dict[_State, Vector | None]] = []
    conditions: list[float] = []

    for t in range(horizon - 1, -1, -1):
        z_t = paths[:, t + 1, :]
        power = np.exp(z_t[:, factor_model.active_power_index(t)])
        gas = np.exp(z_t[:, factor_model.gas_index])
        temperatures, capacities, spread = _scenario_context(
            factor_model, plant, t, z_t, power, gas, availability
        )
        representative_index = int(np.argmax(capacities))
        temperature = float(temperatures[representative_index])
        eff_capacity = float(capacities[representative_index])
        discount = discounts[t]

        feasible_next = list(realized.keys())
        if t == horizon - 1:
            continuation = {s: np.zeros(n_paths) for s in feasible_next}
            coefficients: dict[_State, Vector | None] = {s: None for s in feasible_next}
        else:
            basis = _poly_basis(z_t, regression_basis_degree)
            targets = {s: realized[s] for s in feasible_next}
            if all(bool(np.all(np.isfinite(target))) for target in targets.values()):
                # Common case: no state is (per-path) infeasible from here forward --
                # fit every state's continuation in one batched multi-RHS lstsq call,
                # exactly as before this fix.
                stacked = np.column_stack(list(targets.values()))
                coeffs, *_ = np.linalg.lstsq(basis, stacked, rcond=None)
                conditions.append(float(np.linalg.cond(basis)))
                predicted = basis @ coeffs
                continuation = {s: predicted[:, j] for j, s in enumerate(feasible_next)}
                # .astype(np.float64) (not .copy()): numpy's lstsq stub types its first
                # return value as floating[Any] on some numpy releases (narrower Vector =
                # NDArray[float64] elsewhere) -- this pins the static (and, since the data
                # is already float64, identical-at-runtime) dtype across numpy versions.
                coefficients = {
                    s: coeffs[:, j].astype(np.float64) for j, s in enumerate(feasible_next)
                }
            else:
                # A min-run-locked online state whose derated capacity has collapsed
                # below every feasible level on *some* paths realizes -inf there (a
                # genuine "no feasible move" outcome, not sampling noise -- see
                # `_scenario_cash` / `_moves`'s forced-shutdown fallback). Feeding a
                # -inf target into `lstsq` would corrupt the whole regression (a
                # least-squares fit has no finite solution against an infinite
                # target), producing non-finite coefficients that then poison every
                # other state's continuation sharing this basis. Fit each state's
                # regression only on the paths where it is finite, and never let a
                # state that is infeasible on *every* path enter a regression at all
                # -- its continuation is -inf everywhere instead, so the emitting
                # (t-1) period's argmax still avoids transitioning into it there.
                continuation = {}
                coefficients = {}
                step_conditions: list[float] = []
                for state, target in targets.items():
                    finite = np.isfinite(target)
                    if not bool(finite.any()):
                        coefficients[state] = None
                        continuation[state] = np.full(n_paths, -np.inf)
                        continue
                    design = basis[finite]
                    coeffs_s, *_ = np.linalg.lstsq(design, target[finite], rcond=None)
                    step_conditions.append(float(np.linalg.cond(design)))
                    predicted_s = basis @ coeffs_s
                    continuation[state] = np.where(finite, predicted_s, -np.inf)
                    coefficients[state] = coeffs_s.astype(np.float64)
                conditions.append(max(step_conditions, default=1.0))
        policy_coefficients.append(coefficients)

        current: dict[_State, Vector] = {}
        for state in states:
            moves = [
                (m, _scenario_cash(m, plant, temperatures, capacities, discount, power, gas))
                for m in _moves(state, plant, levels, temperature, eff_capacity, up_cap, down_cap)
                if m.next_state in continuation
            ]
            if not moves:
                continue
            estimate = np.stack([cash + continuation[m.next_state] for m, cash in moves])
            realized_next = np.stack([cash + realized[m.next_state] for m, cash in moves])
            best = np.argmax(estimate, axis=0)
            current[state] = np.take_along_axis(realized_next, best[None, :], axis=0)[0]

        surfaces.append(
            _period_surfaces(
                plant,
                levels,
                temperature,
                eff_capacity,
                discount,
                up_cap,
                down_cap,
                power,
                gas,
                spread,
                continuation,
            )
        )
        realized = current

    if initial not in realized:
        raise ValidationError(
            "the supplied initial condition admits no feasible schedule over the horizon"
        )
    training_value = float(np.mean(realized[initial]))
    controls = evaluation or MonteCarloEvaluation(seed=seed + 1, path_count=path_count)
    evaluation_values = _evaluate_lsm_policy(
        plant,
        factor_model,
        levels,
        initial,
        discounts,
        availability,
        up_cap,
        down_cap,
        controls,
        list(reversed(policy_coefficients)),
        antithetic,
        regression_basis_degree,
    )
    value = float(np.mean(evaluation_values))
    standard_error = _standard_error(evaluation_values, antithetic)
    quantile = NormalDist().inv_cdf(0.5 + controls.confidence_level / 2.0)
    diagnostics = DispatchDiagnostics(
        training_value=training_value,
        evaluation_standard_error=standard_error,
        confidence_interval=(value - quantile * standard_error, value + quantile * standard_error),
        training_path_count=n_paths,
        evaluation_path_count=int(evaluation_values.size),
        max_regression_condition=max(conditions, default=1.0),
    )
    return _package(value, surfaces, diagnostics)


def _evaluate_lsm_policy(
    plant: PlantModel,
    factor_model: DispatchFactorModel,
    levels: tuple[float, ...],
    initial: _State,
    discounts: list[float],
    availability: Sequence[float] | None,
    up_cap: int,
    down_cap: int,
    controls: MonteCarloEvaluation,
    coefficients: list[dict[_State, Vector | None]],
    antithetic: bool,
    regression_basis_degree: int,
) -> Vector:
    """Roll a fitted LSM policy forward on an independent scenario set."""
    paths = factor_model.simulate(controls.seed, controls.path_count, antithetic=antithetic)
    values = np.zeros(paths.shape[0], dtype=np.float64)
    states = [initial] * paths.shape[0]
    for period in range(factor_model.horizon):
        z_t = paths[:, period + 1, :]
        power = np.exp(z_t[:, factor_model.active_power_index(period)])
        gas = np.exp(z_t[:, factor_model.gas_index])
        temperatures, capacities, _ = _scenario_context(
            factor_model, plant, period, z_t, power, gas, availability
        )
        basis = _poly_basis(z_t, regression_basis_degree)
        next_states: list[_State] = []
        for path_index, state in enumerate(states):
            temperature = float(temperatures[path_index])
            capacity = float(capacities[path_index])
            moves = _moves(state, plant, levels, temperature, capacity, up_cap, down_cap)
            candidates: list[tuple[float, float, _State]] = []
            for move in moves:
                if move.next_state not in coefficients[period]:
                    continue
                cash = float(
                    _move_cash(
                        move,
                        plant,
                        temperature,
                        discounts[period],
                        power[path_index : path_index + 1],
                        gas[path_index : path_index + 1],
                    )[0]
                )
                coefficient = coefficients[period][move.next_state]
                continuation = (
                    0.0 if coefficient is None else float(basis[path_index] @ coefficient)
                )
                candidates.append((cash + continuation, cash, move.next_state))
            if not candidates:
                raise ValidationError("fitted dispatch policy has no feasible forward action")
            _, cash, next_state = max(candidates, key=lambda candidate: candidate[0])
            values[path_index] += cash
            next_states.append(next_state)
        states = next_states
    return values


def _tree_nodes(step: int, dim: int) -> list[tuple[int, ...]]:
    """Recombining-lattice nodes at ``step``: up-move counts in each decorrelated axis."""
    return list(itertools.product(range(step + 1), repeat=dim))


def _dispatch_tree(
    plant: PlantModel,
    factor_model: DispatchFactorModel,
    levels: tuple[float, ...],
    states: list[_State],
    initial: _State,
    discounts: list[float],
    availability: Sequence[float] | None,
    up_cap: int,
    down_cap: int,
    seed: int,
    path_count: int,
    evaluation: MonteCarloEvaluation | None,
    antithetic: bool,
    regression_basis_degree: int,
) -> DispatchResult:
    """Recombining-lattice backward induction (Appendix B binomial/multinomial forest).

    Each factor's decorrelated coordinate follows an independent +/-1 binomial walk
    (mean 0, variance 1 per step), mapped back through ``L = chol(C)`` so the joint
    log-increment matches ``mu + L·ε`` in its first two moments -- the same dynamics
    the LSM engine simulates, discretised. Nodes recombine; each of the ``2^D``
    children carries equal probability ``(1/2)^D``, giving an exact conditional
    expectation ``E*`` at every node. The lattice is deterministic: ``seed``,
    ``path_count``, ``antithetic`` and ``regression_basis_degree`` are accepted only
    so both solvers share one dispatch-table signature, and are unused (the tree has
    no simulation or regression).
    """
    del seed, path_count, evaluation, antithetic, regression_basis_degree
    if factor_model.drift.ndim != 1 or factor_model.covariance.ndim != 2:
        raise ValidationError("method='tree' requires time-homogeneous drift and covariance")
    if factor_model.temperature_factor is not None or factor_model.availability_factor is not None:
        raise ValidationError("method='tree' does not support stochastic physical-factor mappings")
    horizon = factor_model.horizon
    dim = int(factor_model.log_forward0.shape[0])
    try:
        chol = np.linalg.cholesky(factor_model.covariance)
    except np.linalg.LinAlgError as exc:
        raise ValidationError(
            "method='tree' requires a positive-definite covariance (no expired / zero-variance "
            "factors); use method='lsm' otherwise"
        ) from exc

    def node_prices(nodes: list[tuple[int, ...]], step: int) -> Vector:
        net = 2.0 * np.asarray(nodes, dtype=np.float64) - step
        return factor_model.log_forward0 + step * factor_model.drift + net @ chol.T

    branches = list(itertools.product((0, 1), repeat=dim))
    # Terminal continuation: value 0 in every state, at every node of the last step.
    value_next: dict[tuple[int, ...], dict[_State, float]] = {}
    feasible_next: set[_State] = set(states)
    surfaces: list[tuple[float, float, float, float]] = []

    for t in range(horizon - 1, -1, -1):
        step = t + 1
        nodes = _tree_nodes(step, dim)
        node_index = {node: i for i, node in enumerate(nodes)}
        log_prices = node_prices(nodes, step)
        power = np.exp(log_prices[:, factor_model.active_power_index(t)])
        gas = np.exp(log_prices[:, factor_model.gas_index])
        temperature, eff_capacity, spread = _period_context(
            factor_model, plant, t, power, gas, availability
        )
        discount = discounts[t]

        # Continuation array per next-state, aligned to this step's node order.
        continuation: dict[_State, Vector] = {}
        if t == horizon - 1:
            continuation = {s: np.zeros(len(nodes)) for s in feasible_next}
        else:
            for state in feasible_next:
                values = np.empty(len(nodes))
                for i, node in enumerate(nodes):
                    children = [tuple(node[k] + b[k] for k in range(dim)) for b in branches]
                    values[i] = float(np.mean([value_next[c][state] for c in children]))
                continuation[state] = values

        moves_by_state = {
            s: [
                m
                for m in _moves(s, plant, levels, temperature, eff_capacity, up_cap, down_cap)
                if m.next_state in continuation
            ]
            for s in states
        }
        feasible_cur = {s for s, moves in moves_by_state.items() if moves}
        value_cur: dict[tuple[int, ...], dict[_State, float]] = {node: {} for node in nodes}
        for state in feasible_cur:
            estimate = np.stack(
                [
                    _move_cash(m, plant, temperature, discount, power, gas)
                    + continuation[m.next_state]
                    for m in moves_by_state[state]
                ]
            )
            best = np.max(estimate, axis=0)
            for node in nodes:
                value_cur[node][state] = float(best[node_index[node]])

        surfaces.append(
            _period_surfaces(
                plant,
                levels,
                temperature,
                eff_capacity,
                discount,
                up_cap,
                down_cap,
                power,
                gas,
                spread,
                continuation,
            )
        )
        value_next = value_cur
        feasible_next = feasible_cur

    if initial not in feasible_next:
        raise ValidationError(
            "the supplied initial condition admits no feasible schedule over the horizon"
        )
    # Value today: average of period-0 (step-1) node values in the initial state.
    step1_nodes = _tree_nodes(1, dim)
    value = float(np.mean([value_next[node][initial] for node in step1_nodes]))
    return _package(value, surfaces)


def _package(
    value: float,
    surfaces: list[tuple[float, float, float, float]],
    diagnostics: DispatchDiagnostics | None = None,
) -> DispatchResult:
    """Assemble the result; ``surfaces`` were appended backward, so reverse to time order."""
    ordered = list(reversed(surfaces))
    return DispatchResult(
        value=value,
        start_surface=tuple(row[0] for row in ordered),
        shutdown_surface=tuple(row[1] for row in ordered),
        rampup_surface=tuple(row[2] for row in ordered),
        rampdown_surface=tuple(row[3] for row in ordered),
        diagnostics=diagnostics,
    )


# Strategy-as-dispatch-dict (coding-style 2): method name -> solver. Both solvers share
# one signature; adding a method means adding an entry, not editing dispatch_value (OCP).
_Solver = Callable[
    [
        PlantModel,
        DispatchFactorModel,
        tuple[float, ...],
        list[_State],
        _State,
        list[float],
        Sequence[float] | None,
        int,
        int,
        int,
        int,
        MonteCarloEvaluation | None,
        bool,
        int,
    ],
    DispatchResult,
]
_SOLVERS: dict[str, _Solver] = {"lsm": _dispatch_lsm, "tree": _dispatch_tree}


def _require_risk_adjusted_drift(drift_kind: DriftKind) -> None:
    """Reject a physical drift for valuation (Req 21.5; mirror of the VaR guard).

    Valuation optimises under the risk-adjusted expectation ``E*`` (eq. B.2), whose
    drift is ``RISK_NEUTRAL`` in this library's ``DriftKind`` vocabulary
    ("arbitrage-free valuation only"). A ``PHYSICAL`` drift carries the real-world
    risk premium and would overstate a not-fully-hedgeable asset's value.
    """
    if drift_kind != DriftKind.RISK_NEUTRAL:
        raise ValidationError(
            f"factor_model.drift must be tagged {DriftKind.RISK_NEUTRAL!r} (the risk-adjusted "
            f"pricing measure E*, Req 21.5 / Req 19) for dispatch valuation, got {drift_kind!r}; "
            "form the risk-adjusted drift mu* = mu - lambda_S*sigma (eq. 10.5) and tag it "
            "RISK_NEUTRAL"
        )


def dispatch_value(
    plant: PlantModel,
    factor_model: DispatchFactorModel,
    *,
    method: str = "lsm",
    seed: int,
    path_count: int = 4096,
    output_step: float | None = None,
    availability: Sequence[float] | None = None,
    discount_factors: Sequence[float] | None = None,
    initial_online: bool = False,
    initial_output: float = 0.0,
    initial_uptime: int | None = None,
    initial_downtime: int | None = None,
    evaluation: MonteCarloEvaluation | None = None,
    antithetic: bool = True,
    regression_basis_degree: int = 2,
) -> DispatchResult:
    """Value ``plant`` under uncertainty by stochastic DP (eqs. B.2-B.3; Req 21.1-21.2).

    Solves the Bellman recursion over the deterministic module's commitment state
    machine, under the risk-adjusted expectation carried by ``factor_model``
    (Req 21.5). See the module docstring for the state machine, the on-peak /
    off-peak Markov split (Req 21.6), the risk-adjusted-drift requirement, the
    forced-outage seam, and the critical-surface representation. All inputs are
    validated before any computation and never mutated.

    Args:
        plant: The operating model (heat-rate curve, capacities, start costs,
            ramp rate, durations).
        factor_model: Risk-adjusted factor dynamics and the per-period peak /
            temperature context (also fixes the horizon ``H``).
        method: ``"lsm"`` (least-squares Monte Carlo) or ``"tree"`` (recombining
            lattice); selected via a dispatch table.
        seed: Monte Carlo / lattice seed (Req 11.2 determinism); ``>= 0``.
        path_count: Simulated paths for ``"lsm"`` (ignored by ``"tree"``); ``>= 1``.
        output_step: Output-grid spacing (MW); defaults to the ramp rate.
        availability: Optional per-period forced-outage multiplier ``M`` in
            ``(0, 1]`` (length ``H``) derating ``c_max``; ``None`` = full
            availability. A caller may source it from
            :meth:`OutageDataset.forced_outage_multiplier`.
        discount_factors: Per-period to-today discount factors (default all 1.0).
        initial_online: Whether the unit is producing entering the horizon.
        initial_output: Output entering the horizon (MW); on-grid when online.
        initial_uptime: Producing periods already accrued (min-run).
        initial_downtime: Periods already offline (start bucket / min-down); must be
            ``>= 1`` when not ``initial_online`` (delegated to the reused
            :func:`~quantvolt.assets.dispatch_deterministic._initial_state`).
        evaluation: Independent LSM policy-evaluation sample. By default, the fitted
            policy is evaluated on ``path_count`` fresh paths using ``seed + 1``.
        antithetic: Whether ``"lsm"``'s simulated paths use antithetic variates
            (default ``True``, matching prior behaviour); ignored by ``"tree"``
            (the lattice has no simulation). Also selects the pair-mean-aware
            standard-error estimator used for ``evaluation_standard_error``
            (:class:`DispatchDiagnostics`).
        regression_basis_degree: Degree of the polynomial regression basis used by
            ``"lsm"``'s continuation-value fit (default ``2``: intercept, linears,
            squares, pairwise cross terms -- the historical basis); ignored by
            ``"tree"``. Must be ``>= 1``.

    Returns:
        The :class:`DispatchResult` (value + eq. B.5 critical surfaces).

    Raises:
        ValidationError: If ``method`` is unknown; if ``factor_model.drift`` is not
            risk-adjusted (Req 21.5); if ``path_count`` / ``seed`` /
            ``discount_factors`` / ``availability`` / ``regression_basis_degree`` are
            out of range or mis-sized; if a plant curve is infeasible at a supplied
            temperature; if ``initial_downtime < 1`` while offline; or if the initial
            condition admits no feasible schedule.
    """
    solver = _SOLVERS.get(method)
    if solver is None:
        raise ValidationError(f"method must be one of {sorted(_SOLVERS)!r}, got {method!r}")
    _require_risk_adjusted_drift(factor_model.drift_kind)
    require_integer_at_least("seed", seed, 0)
    require_integer_at_least("path_count", path_count, 1)
    require_integer_at_least("regression_basis_degree", regression_basis_degree, 1)
    if evaluation is not None:
        require_integer_at_least("evaluation.seed", evaluation.seed, 0)
        require_integer_at_least("evaluation.path_count", evaluation.path_count, 1)
        if not (0.0 < evaluation.confidence_level < 1.0):
            raise ValidationError(
                "evaluation.confidence_level must be in (0, 1), got "
                f"{evaluation.confidence_level!r}"
            )

    horizon = factor_model.horizon
    if discount_factors is not None:
        require_length("discount_factors", discount_factors, horizon)
        for index, factor in enumerate(discount_factors):
            if not factor > 0:
                raise ValidationError(f"discount_factors[{index}] must be > 0, got {factor!r}")
    if availability is not None:
        require_length("availability", availability, horizon)
        for index, multiplier in enumerate(availability):
            if not (0.0 < multiplier <= 1.0):
                raise ValidationError(
                    f"availability[{index}] must be in (0, 1], got {multiplier!r}"
                )

    levels = _build_output_grid(plant, factor_model.temperatures, output_step)
    up_cap = max(plant.d_min, 1)
    down_cap = max(plant.d_shutdown, plant.warm_max_downtime + 1, 1)
    discounts = [1.0] * horizon if discount_factors is None else list(discount_factors)
    states = _all_states(levels, plant, up_cap, down_cap)
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

    return solver(
        plant,
        factor_model,
        levels,
        states,
        initial,
        discounts,
        availability,
        up_cap,
        down_cap,
        seed,
        path_count,
        evaluation,
        antithetic,
        regression_basis_degree,
    )
