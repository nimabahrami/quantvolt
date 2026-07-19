"""Gas storage valuation: intrinsic + extrinsic.

A gas store is injection/withdrawal optionality against a term structure: buy and inject
when the curve is cheap, withdraw and sell when it is dear, subject to physical inventory
bounds, injection/withdrawal ratchets (rate limits that may vary with the fill level),
per-unit throughput costs, fuel-in-kind losses, a carry/financing cost on the stored gas,
and a terminal-inventory condition. This module supplies the value object and two
valuations at increasing fidelity, mirroring the physical-asset workflow used by
``quantvolt.assets.dispatch_deterministic``:

- ``storage_intrinsic``: the intrinsic value: the optimal forward-locked
  injection/withdrawal schedule priced against today's forward curve, computed by exact
  backward-induction dynamic programming over a discretised inventory grid.
  Because the schedule is fixed today it carries no re-optimisation (time) value; it is the
  deterministic baseline every stochastic policy is measured against.
- ``storage_value``: the total value (intrinsic + extrinsic) via Least-Squares
  Monte Carlo (LSM): spot-price paths are simulated with the single-factor forward-consistent
  model of ``StorageFactorModel`` (a documented one-factor reduction of the correlated
  engine in ``quantvolt.numerics.monte_carlo``), and a backward induction over
  ``(time, inventory)`` with regression continuation values finds the optimal adaptive
  policy. The extrinsic component is ``total - intrinsic``.

Conventions fixed by this module (documented; the idealized-case relations depend on them)
-----------------------------------------------------------------------------------------
- Undiscounted. Cash flows are summed at the forward/spot delivery prices with no
  present-value discounting, exactly as ``quantvolt.pricing.spreads.calendar_spread``
  does. Discounting, if wanted, is folded into the supplied forward prices by the caller.
  Keeping the intrinsic undiscounted is what makes the ``total >= intrinsic`` identity exact.
- **Inventory is working gas.** The inventory state and the ``injection``/``withdrawal``
  amounts in a result are volumes of *working* gas (what is added to / removed from the
  cavern). Fuel-in-kind losses act on the *cash* (market throughput) leg only, so the
  inventory grid stays exact under the DP:

  * injecting a working-gas amount ``a`` buys ``a / (1 - injection_loss)`` at the market
    (fuel burns a fraction of the delivered gas), costing
    ``price · a/(1 - injection_loss) + injection_cost · a``;
  * withdrawing a working-gas amount ``w`` delivers ``w · (1 - withdrawal_loss)`` to the
    sales meter, earning ``price · w·(1 - withdrawal_loss) - withdrawal_cost · w``.

  ``injection_cost`` / ``withdrawal_cost`` are per unit of *working* gas moved; the carry
  cost ``carry_cost · inventory_end`` is charged every period on the gas held into the next.
- **Ratchets.** ``injection_rate(inventory)`` / ``withdrawal_rate(inventory)`` are
  caller-supplied pure callables giving the maximum working-gas change *per period* at the
  current fill level (a constant rate is ``lambda inv: R``). This mirrors the caller-supplied
  curves of :class:`quantvolt.assets.plant.PlantModel`; the library treats them as data and
  never mutates them. They are checked ``>= 0`` at every grid level before optimisation.
- **Inventory grid.** ``[min_inventory, max_inventory]`` is discretised uniformly with
  spacing ``inventory_step`` (default ``(max - min) / _DEFAULT_GRID_STEPS``). ``initial_inventory``
  and ``terminal_inventory`` must fall on the grid (validated) so the DP optimum is exact for
  the discretised problem, and it equals the continuous optimum whenever the optimal fill
  levels lie on the grid — which they do by construction for the hand-worked cases and which
  is approached as ``inventory_step -> 0`` otherwise (the same exactness statement as the
  thermal dispatch DP).
- **Terminal condition.** A hard target (``terminal_penalty is None``) forces the schedule to
  finish exactly at ``terminal_inventory`` — grid levels that cannot reach it are infeasible
  (``-inf``); an unreachable target raises. A soft target (``terminal_penalty >= 0``) instead
  subtracts ``terminal_penalty · |inventory_end - terminal_inventory|`` from the value.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from .._validation import require_non_negative, require_positive
from ..exceptions import ValidationError
from ..models.curve import ForwardCurve
from ..numerics.monte_carlo import build_covariance, simulate_correlated_forwards
from ._tolerance import GRID_EPS

# Ratchet curve: maximum working-gas change (volume) per period at a given fill level.
RateCurve = Callable[[float], float]

# Grid-alignment / feasibility tolerance (volume units); shared with
# dispatch_deterministic (see assets/_tolerance.py).
_EPS = GRID_EPS
# Default number of inventory-grid intervals when no ``inventory_step`` is supplied.
_DEFAULT_GRID_STEPS = 50
# LSM regression basis degree in the spot price: 1, S, S**2 (documented in storage_value).
_LSM_BASIS_DEGREE = 2


@dataclass(frozen=True, slots=True)
class StorageModel:
    """Physical + commercial parameters of a gas store.

    Inventory bounds are time-invariant scalars, the lightest faithful representation;
    time-varying bounds would be a strictly heavier model and are deferred until a
    caller needs them. Ratchets carry the only state-dependence that matters here,
    as callables of the current fill level.

    All consistency constraints are validated eagerly in ``__post_init__`` (rate-curve
    non-negativity, which cannot be checked over all inventories for an opaque callable, is
    checked at every grid level when a valuation runs). Inconsistent bounds raise a
    ``ValidationError`` naming the offending fields.

    Attributes:
        min_inventory: Minimum working-gas inventory (volume).
        max_inventory: Maximum working-gas inventory (volume); must be ``>= min_inventory``.
        initial_inventory: Inventory entering the horizon; must lie in the bounds and on the
            grid.
        terminal_inventory: Target inventory at the horizon end; must lie in the bounds and
            on the grid.
        injection_rate: Ratchet ``injection_rate(inventory) -> max working-gas injected this
            period`` (``>= 0``).
        withdrawal_rate: Ratchet ``withdrawal_rate(inventory) -> max working-gas withdrawn
            this period`` (``>= 0``).
        injection_cost: Variable cost per unit working gas injected (``>= 0``).
        withdrawal_cost: Variable cost per unit working gas withdrawn (``>= 0``).
        injection_loss: Fuel-in-kind fraction burned on injection, in ``[0, 1)``.
        withdrawal_loss: Fuel-in-kind fraction burned on withdrawal, in ``[0, 1)``.
        carry_cost: Carry/financing cost per unit inventory held per period (``>= 0``).
        terminal_penalty: If ``None`` the terminal inventory is a hard constraint; otherwise a
            per-unit penalty (``>= 0``) on the terminal deviation from ``terminal_inventory``.
    """

    min_inventory: float
    max_inventory: float
    initial_inventory: float
    terminal_inventory: float
    injection_rate: RateCurve
    withdrawal_rate: RateCurve
    injection_cost: float = 0.0
    withdrawal_cost: float = 0.0
    injection_loss: float = 0.0
    withdrawal_loss: float = 0.0
    carry_cost: float = 0.0
    terminal_penalty: float | None = None

    def __post_init__(self) -> None:
        if self.min_inventory > self.max_inventory:
            raise ValidationError(
                "min_inventory must be <= max_inventory, got "
                f"min_inventory={self.min_inventory!r}, max_inventory={self.max_inventory!r}"
            )
        if not (self.min_inventory - _EPS <= self.initial_inventory <= self.max_inventory + _EPS):
            raise ValidationError(
                f"initial_inventory must be in [{self.min_inventory!r}, {self.max_inventory!r}], "
                f"got {self.initial_inventory!r}"
            )
        if not (self.min_inventory - _EPS <= self.terminal_inventory <= self.max_inventory + _EPS):
            raise ValidationError(
                f"terminal_inventory must be in [{self.min_inventory!r}, {self.max_inventory!r}], "
                f"got {self.terminal_inventory!r}"
            )
        require_non_negative("injection_cost", self.injection_cost)
        require_non_negative("withdrawal_cost", self.withdrawal_cost)
        require_non_negative("carry_cost", self.carry_cost)
        if not (0.0 <= self.injection_loss < 1.0):
            raise ValidationError(f"injection_loss must be in [0, 1), got {self.injection_loss!r}")
        if not (0.0 <= self.withdrawal_loss < 1.0):
            raise ValidationError(
                f"withdrawal_loss must be in [0, 1), got {self.withdrawal_loss!r}"
            )
        if self.terminal_penalty is not None:
            require_non_negative("terminal_penalty", self.terminal_penalty)

    @property
    def working_capacity(self) -> float:
        """The full working-gas volume ``max_inventory - min_inventory``."""
        return self.max_inventory - self.min_inventory


@dataclass(frozen=True, slots=True)
class IntrinsicResult:
    """The optimal forward-locked injection/withdrawal schedule and its value.

    Every per-period tuple is in delivery-period order with the horizon's length ``T``;
    ``inventory`` has length ``T + 1`` (level entering each period, then the terminal level).
    By construction the schedule respects the inventory bounds and ratchets at every step.

    Attributes:
        value: The intrinsic value — the optimal forward-locked total cash flow (including
            any terminal penalty).
        inventory: Working-gas inventory path; ``inventory[0] == initial_inventory`` and
            ``inventory[T] == terminal_inventory`` (hard target) or the optimal terminal level
            (soft penalty).
        injection: Working gas injected each period (``0`` when withdrawing/idle).
        withdrawal: Working gas withdrawn each period (``0`` when injecting/idle).
        cashflow: Market cash flow each period net of throughput and carry costs;
            ``sum(cashflow) == value`` when the terminal condition is a hard target (its
            penalty contribution is then zero), otherwise ``value == sum(cashflow) -
            terminal_penalty · |inventory[T] - terminal_inventory|``.
    """

    value: float
    inventory: tuple[float, ...]
    injection: tuple[float, ...]
    withdrawal: tuple[float, ...]
    cashflow: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class StorageFactorModel:
    """Single-factor forward-consistent spot model for the extrinsic (LSM) leg.

    A documented one-factor reduction of the correlated forward engine
    (:func:`quantvolt.numerics.monte_carlo.simulate_correlated_forwards`): a single Brownian
    log-factor ``X`` drives the whole curve multiplicatively. The period-``t`` spot price on a
    path is ``F(0, t) · exp(X_t)`` where ``X`` is simulated as GBM with per-step variance
    ``volatility**2 · dt`` under the risk-neutral drift ``-½·volatility**2·dt`` that makes
    ``exp(X)`` a unit martingale. Consequences that the valuation relies on:

    * ``X_0 = 0`` deterministically, so the period-0 spot equals ``F(0, 0)`` on every path
      (today's prompt price is known);
    * ``E[spot_t] = F(0, t)`` — the forward is the risk-neutral spot mean, so the deterministic
      intrinsic schedule earns exactly the intrinsic value in expectation, which is what
      guarantees ``extrinsic >= 0``.

    The model is *structured to admit* mean-reverting/OU dynamics without touching the
    valuation (only the simulated factor changes); GBM is the shipped default.

    Attributes:
        volatility: Annualised log-volatility ``sigma`` of the driving factor (``> 0``).
        dt: Step length in years between consecutive delivery periods (``> 0``).
        path_count: Number of Monte Carlo paths (``>= 1``); antithetic pairing is used, so an
            odd count rounds up.
    """

    volatility: float
    dt: float
    path_count: int = 4000

    def __post_init__(self) -> None:
        require_positive("volatility", self.volatility)
        require_positive("dt", self.dt)
        if self.path_count < 1:
            raise ValidationError(f"path_count must be >= 1, got {self.path_count!r}")


@dataclass(frozen=True, slots=True)
class StorageValueResult:
    """Total, intrinsic and extrinsic storage value with the MC standard error.

    ``total == intrinsic + extrinsic`` by construction (``total`` is anchored on the exact
    intrinsic value plus the control-variate extrinsic estimate). ``extrinsic`` is
    theoretically non-negative; it is reported honestly rather than clamped, and
    ``standard_error`` — the Monte Carlo standard error of the extrinsic estimate — is the
    natural yardstick for the ``extrinsic >= -epsilon`` tolerance floor (a few standard errors)
    within which a small negative sampling value is acceptable.

    Attributes:
        total: The total (intrinsic + extrinsic) value; ``intrinsic + extrinsic``.
        intrinsic: The forward-locked intrinsic value (see :func:`storage_intrinsic`).
        extrinsic: The re-optimisation (time) value — the control-variate mean of the adaptive
            minus fixed-schedule pathwise values; equals ``total - intrinsic``.
        standard_error: Monte Carlo standard error of the ``extrinsic`` estimate, computed
            by :func:`_standard_error` — pair-mean-aware when the simulated paths use
            antithetic variates (the default), rather than the naive iid formula over
            every path (which overstates the SE by ignoring the antithetic pairs'
            negative within-pair correlation).
    """

    total: float
    intrinsic: float
    extrinsic: float
    standard_error: float


# --- shared grid / transition machinery ------------------------------------------------


# A feasible transition from a grid level: (next_level_index, price_coeff, constant) where the
# period cash flow is ``price_coeff · price + constant`` (linear in the delivery/spot price).
_Transition = tuple[int, float, float]


def _build_grid(
    model: StorageModel,
    inventory_step: float | None,
    grid_steps: int = _DEFAULT_GRID_STEPS,
) -> tuple[npt.NDArray[np.float64], int]:
    """Uniform inventory grid over ``[min, max]`` plus the initial-inventory index.

    Validates that ``inventory_step > 0`` and that both ``initial_inventory`` and
    ``terminal_inventory`` land on the grid; a degenerate store
    (``max == min``) collapses to the single level ``{min}``.

    ``grid_steps`` sets the number of grid intervals when ``inventory_step`` is not
    supplied (default :data:`_DEFAULT_GRID_STEPS`, ``50``). Must be ``>= 1``.
    """
    span = model.max_inventory - model.min_inventory
    if span <= _EPS:
        return np.array([model.min_inventory], dtype=np.float64), 0
    if grid_steps < 1:
        raise ValidationError(f"grid_steps must be >= 1, got {grid_steps!r}")
    step = span / grid_steps if inventory_step is None else inventory_step
    require_positive("inventory_step", step)
    count = math.floor(span / step + _EPS)
    levels = model.min_inventory + step * np.arange(count + 1, dtype=np.float64)
    # Ensure the top of the range is represented within tolerance.
    if abs(levels[-1] - model.max_inventory) > _EPS:
        levels = np.append(levels, model.max_inventory)

    def _index_on_grid(name: str, value: float) -> int:
        offsets = np.abs(levels - value)
        idx = int(np.argmin(offsets))
        if offsets[idx] > _EPS:
            raise ValidationError(
                f"{name}={value!r} does not lie on the inventory grid (step={step!r}); "
                "choose an inventory_step that divides the distance from min_inventory"
            )
        return idx

    _index_on_grid("terminal_inventory", model.terminal_inventory)
    return levels, _index_on_grid("initial_inventory", model.initial_inventory)


def _transition_coeffs(
    model: StorageModel, level_from: float, level_to: float
) -> tuple[float, float]:
    """Price-coefficient and constant of the cash flow for a ``level_from -> level_to`` move.

    Cash flow at delivery/spot price ``P`` is ``price_coeff · P + constant`` (see the module
    docstring for the working-gas / fuel-in-kind conventions). Carry is charged on the
    end-of-period level ``level_to`` every period, injection/withdrawal alike.
    """
    delta = level_to - level_from
    carry = -model.carry_cost * level_to
    if delta > _EPS:  # inject working gas ``delta``
        market_volume = delta / (1.0 - model.injection_loss)
        return -market_volume, -model.injection_cost * delta + carry
    if delta < -_EPS:  # withdraw working gas ``w``
        w = -delta
        market_volume = w * (1.0 - model.withdrawal_loss)
        return market_volume, -model.withdrawal_cost * w + carry
    return 0.0, carry  # idle


def _feasible_transitions(
    model: StorageModel, levels: npt.NDArray[np.float64]
) -> list[list[_Transition]]:
    """Every price-independent feasible transition from each grid level (rates + bounds).

    Ratchets depend only on the fill level (not on time or price), so the feasible move set is
    computed once. Rate curves are checked ``>= 0`` here; the bounds are enforced by
    construction because every ``level_to`` is a grid point inside ``[min, max]``.
    """
    n = len(levels)
    transitions: list[list[_Transition]] = []
    for i in range(n):
        inv = float(levels[i])
        inj_cap = float(model.injection_rate(inv))
        wd_cap = float(model.withdrawal_rate(inv))
        if inj_cap < 0.0:
            raise ValidationError(f"injection_rate(inventory={inv!r}) = {inj_cap!r} must be >= 0")
        if wd_cap < 0.0:
            raise ValidationError(f"withdrawal_rate(inventory={inv!r}) = {wd_cap!r} must be >= 0")
        row: list[_Transition] = []
        for j in range(n):
            delta = float(levels[j] - inv)
            if delta > inj_cap + _EPS or -delta > wd_cap + _EPS:
                continue  # ratchet-infeasible this period
            coeff, const = _transition_coeffs(model, inv, float(levels[j]))
            row.append((j, coeff, const))
        transitions.append(row)
    return transitions


def _terminal_values(
    model: StorageModel, levels: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Terminal value per grid level: 0/``-inf`` (hard target) or penalty-adjusted (soft)."""
    deviation = np.abs(levels - model.terminal_inventory)
    if model.terminal_penalty is None:
        return np.where(deviation <= _EPS, 0.0, -np.inf)
    return -model.terminal_penalty * deviation


def _sorted_prices(forward_curve: ForwardCurve) -> npt.NDArray[np.float64]:
    """Delivery prices in chronological period order (curve nodes are already ordered)."""
    return np.array([node.price for node in forward_curve.nodes], dtype=np.float64)


# --- intrinsic valuation ---------------------------------------------------------------


def storage_intrinsic(
    model: StorageModel,
    forward_curve: ForwardCurve,
    *,
    inventory_step: float | None = None,
    grid_steps: int = _DEFAULT_GRID_STEPS,
) -> IntrinsicResult:
    """Optimal forward-locked injection/withdrawal schedule and its value.

    Exact backward-induction dynamic program over the discretised inventory grid: with the
    forward curve's per-period prices known, it finds the injection/withdrawal schedule that
    maximises total cash flow subject to the inventory bounds, the injection/withdrawal
    ratchets and the terminal-inventory condition — all enforced at *every* step by the
    feasible-transition set. See the module docstring for the discretisation,
    the cash-flow conventions and the exactness statement.

    Args:
        model: The storage parameters.
        forward_curve: The forward curve whose node prices drive the schedule; nodes are taken
            in chronological order, one delivery period per horizon step.
        inventory_step: Inventory-grid spacing (volume); defaults to
            ``working_capacity / grid_steps``. Must divide the distances from
            ``min_inventory`` to ``initial_inventory`` and ``terminal_inventory``.
        grid_steps: Number of inventory-grid intervals used to derive the default
            ``inventory_step`` when it is not supplied (default ``50``). Ignored when
            ``inventory_step`` is given explicitly. Must be ``>= 1``.

    Returns:
        The optimal :class:`IntrinsicResult`.

    Raises:
        ValidationError: If ``inventory_step`` is non-positive; if ``grid_steps < 1``; if the
            initial/terminal inventory is off-grid; if a ratchet returns a negative rate at a
            grid level; or if a hard terminal target is unreachable from the initial inventory
            over the horizon.
    """
    levels, k0 = _build_grid(model, inventory_step, grid_steps)
    transitions = _feasible_transitions(model, levels)
    prices = _sorted_prices(forward_curve)
    horizon = len(prices)
    n = len(levels)

    # Backward induction: value_next[i] = best value achievable from level i entering the next
    # boundary; the terminal boundary (after the last period) is the terminal-value function.
    value_next = _terminal_values(model, levels)
    # choice[t][i] = grid index chosen from level i entering period t (for the forward walk).
    choice: list[npt.NDArray[np.int_]] = []
    for _ in range(horizon):
        choice.append(np.full(n, -1, dtype=np.int_))

    for t in range(horizon - 1, -1, -1):
        price = float(prices[t])
        value_cur = np.full(n, -np.inf, dtype=np.float64)
        for i in range(n):
            best_value = -math.inf
            best_j = -1
            for j, coeff, const in transitions[i]:
                candidate = coeff * price + const + value_next[j]
                if candidate > best_value:
                    best_value = candidate
                    best_j = j
            value_cur[i] = best_value
            choice[t][i] = best_j
        value_next = value_cur

    intrinsic_value = float(value_next[k0])
    if not math.isfinite(intrinsic_value):
        raise ValidationError(
            "terminal_inventory is unreachable from initial_inventory within the horizon "
            "under the given ratchets; relax the rates, the terminal target, or use a "
            "terminal_penalty instead of a hard target"
        )

    inventory: list[float] = [float(levels[k0])]
    injection: list[float] = []
    withdrawal: list[float] = []
    cashflow: list[float] = []
    i = k0
    for t in range(horizon):
        j = int(choice[t][i])
        delta = float(levels[j] - levels[i])
        coeff, const = _transition_coeffs(model, float(levels[i]), float(levels[j]))
        cashflow.append(coeff * float(prices[t]) + const)
        injection.append(delta if delta > _EPS else 0.0)
        withdrawal.append(-delta if delta < -_EPS else 0.0)
        inventory.append(float(levels[j]))
        i = j

    return IntrinsicResult(
        value=intrinsic_value,
        inventory=tuple(inventory),
        injection=tuple(injection),
        withdrawal=tuple(withdrawal),
        cashflow=tuple(cashflow),
    )


def _standard_error(values: npt.NDArray[np.float64], antithetic: bool) -> float:
    """Monte Carlo standard error of ``mean(values)``, honest about antithetic pairing.

    When ``antithetic`` is on, ``values`` are interleaved ``(plus, minus)`` mirror
    pairs -- record ``2k`` is the ``+eps`` leg simulated by
    :func:`~quantvolt.numerics.monte_carlo.simulate_correlated_forwards`, record
    ``2k + 1`` its ``-eps`` mirror (the Rust engine's own convention,
    ``rust/src/paths.rs``). Treating every draw as an independent observation
    overstates the standard error, because within-pair draws are negatively
    correlated by construction rather than independent: the correct estimator is
    that of the ``n / 2`` **pair means** (each pair mean is one
    approximately-independent antithetic-variance-reduced draw), giving
    ``std(pair_means, ddof=1) / sqrt(n_pairs)``. With ``antithetic`` off every draw
    is independent and the usual ``std(values, ddof=1) / sqrt(n)`` applies.
    """
    if antithetic:
        pair_means = 0.5 * (values[0::2] + values[1::2])
        if pair_means.size > 1:
            return float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
        return 0.0
    if values.size > 1:
        return float(np.std(values, ddof=1) / math.sqrt(values.size))
    return 0.0


# --- total (intrinsic + extrinsic) valuation via LSM -----------------------------------


def _simulate_spot_paths(
    forward_curve: ForwardCurve,
    factor_model: StorageFactorModel,
    seed: int,
    antithetic: bool = True,
) -> npt.NDArray[np.float64]:
    """Spot-price paths ``F(0, t) · exp(X_t)`` from the single factor (shape ``(N, T)``).

    Drives the correlated engine with a one-dimensional state: covariance ``[[sigma**2·dt]]``,
    risk-neutral drift ``-½·sigma**2·dt`` (so ``exp(X)`` is a unit martingale and
    ``E[spot_t] = F(0, t)``), and ``T - 1`` steps to produce the log-factor at each of the
    ``T`` delivery periods (record 0 is ``X_0 = 0``). ``antithetic`` selects antithetic-variate
    pairing in the underlying path simulator (default ``True``, matching prior behaviour).
    """
    prices = _sorted_prices(forward_curve)
    horizon = len(prices)
    cov = build_covariance(
        np.array([factor_model.volatility]),
        np.array([[1.0]]),
        factor_model.dt,
    )
    drift = -0.5 * np.diag(cov)
    steps = max(horizon - 1, 1)
    log_paths = simulate_correlated_forwards(
        np.zeros(1),
        drift,
        cov,
        steps=steps,
        path_count=factor_model.path_count,
        seed=seed,
        antithetic=antithetic,
    )
    factor = np.exp(log_paths[:, :horizon, 0])  # (N, T); factor[:, 0] == 1 exactly
    return prices[np.newaxis, :] * factor


def _basis_matrix(
    spot: npt.NDArray[np.float64], basis_degree: int = _LSM_BASIS_DEGREE
) -> npt.NDArray[np.float64]:
    """Regression design matrix ``[1, S, S**2, ..., S**basis_degree]`` for the LSM continuation.

    At the default ``basis_degree = 2`` this is exactly the documented ``[1, S, S**2]`` basis.
    """
    return np.vander(spot, N=basis_degree + 1, increasing=True)


def storage_value(
    model: StorageModel,
    forward_curve: ForwardCurve,
    factor_model: StorageFactorModel,
    seed: int,
    *,
    inventory_step: float | None = None,
    grid_steps: int = _DEFAULT_GRID_STEPS,
    lsm_basis_degree: int = _LSM_BASIS_DEGREE,
    antithetic: bool = True,
) -> StorageValueResult:
    """Total (intrinsic + extrinsic) storage value via Least-Squares Monte Carlo.

    Simulates forward-consistent spot paths with ``factor_model`` (see
    :class:`StorageFactorModel`) and runs a backward induction over ``(time, inventory)`` that
    finds the optimal *adaptive* injection/withdrawal policy. At each period and inventory
    level the decision maximises ``immediate cash flow + continuation value``, where the
    continuation value of each reachable next level is estimated by regressing the pathwise
    next-period value on the polynomial basis ``[1, S, S**2]`` of the current spot ``S``
    (Longstaff-Schwartz). The regression is used only to choose the action; the value is then
    accumulated from the *realised* pathwise continuation to limit foldback bias. All the
    inventory-bound, ratchet and terminal constraints are enforced by the same
    feasible-transition set as the intrinsic DP.

    Extrinsic value via a control variate
    ---------------------------------------------------
    The extrinsic component is estimated as the mean pathwise difference between the adaptive
    policy value and the *fixed intrinsic schedule* evaluated on the **same** simulated paths
    (common random numbers): ``extrinsic = mean_p[V_adaptive(p) - V_fixed(p)]``. Because the
    fixed forward-locked schedule is one feasible policy available to the optimal adaptive
    policy, the difference is non-negative in expectation, and sharing the price paths cancels
    the bulk of the sampling variance — so ``extrinsic >= 0`` holds robustly rather than being
    swamped by the (large) variance of ``total`` alone. ``total`` is anchored on the exact
    intrinsic value as ``intrinsic + extrinsic``, and ``extrinsic`` is reported honestly with
    its standard error rather than clamped; a small negative value within a few standard
    errors can arise from Monte Carlo noise.

    Args:
        model: The storage parameters.
        forward_curve: The forward curve (its node prices are the per-period forward means).
        factor_model: The single-factor spot model and MC controls.
        seed: RNG seed; identical inputs and seed give identical results.
        inventory_step: Inventory-grid spacing, shared with :func:`storage_intrinsic`.
        grid_steps: Number of inventory-grid intervals used to derive the default
            ``inventory_step`` when it is not supplied, shared with :func:`storage_intrinsic`
            (default ``50``). Must be ``>= 1``.
        lsm_basis_degree: Degree of the polynomial regression basis
            ``[1, S, ..., S**lsm_basis_degree]`` used for the LSM continuation value (default
            ``2``, i.e. ``[1, S, S**2]``). Must be ``>= 1``.
        antithetic: Whether the simulated spot paths use antithetic variates (default
            ``True``, matching prior behaviour). Also selects the pair-mean-aware
            standard-error estimator used for ``standard_error`` (see
            :func:`_standard_error`).

    Returns:
        The :class:`StorageValueResult` with ``total``, ``intrinsic``, ``extrinsic`` and the
        Monte Carlo ``standard_error`` of ``total``.

    Raises:
        ValidationError: For the same grid/ratchet/terminal violations as
            :func:`storage_intrinsic`, if ``seed`` is negative, or if ``lsm_basis_degree < 1``.
    """
    if seed < 0:
        raise ValidationError(f"seed must be a non-negative integer, got {seed!r}")
    if lsm_basis_degree < 1:
        raise ValidationError(f"lsm_basis_degree must be >= 1, got {lsm_basis_degree!r}")
    intrinsic = storage_intrinsic(
        model, forward_curve, inventory_step=inventory_step, grid_steps=grid_steps
    )

    levels, k0 = _build_grid(model, inventory_step, grid_steps)
    horizon = len(forward_curve.nodes)
    n = len(levels)
    if horizon < 2 or n < 2:
        # No cross-period optionality (single period or a degenerate store): no extrinsic value.
        return StorageValueResult(
            total=intrinsic.value, intrinsic=intrinsic.value, extrinsic=0.0, standard_error=0.0
        )

    transitions = _feasible_transitions(model, levels)
    spot = _simulate_spot_paths(forward_curve, factor_model, seed, antithetic)
    n_paths = spot.shape[0]

    # value_next[path, i] = pathwise value from level i entering the next boundary.
    value_next = np.broadcast_to(_terminal_values(model, levels), (n_paths, n)).copy()

    for t in range(horizon - 1, -1, -1):
        s = spot[:, t]  # (N,)
        design = _basis_matrix(s, lsm_basis_degree)
        # Regression continuation estimate per reachable next level; dead levels stay -inf.
        continuation = np.full((n_paths, n), -np.inf, dtype=np.float64)
        for j in range(n):
            col = value_next[:, j]
            if np.all(np.isfinite(col)):
                coef, *_ = np.linalg.lstsq(design, col, rcond=None)
                continuation[:, j] = design @ coef
        value_cur = np.full((n_paths, n), -np.inf, dtype=np.float64)
        for i in range(n):
            row = transitions[i]
            if not row:
                continue
            # Decision by regression continuation; realised value from the true next value.
            decision = np.empty((n_paths, len(row)), dtype=np.float64)
            realised = np.empty((n_paths, len(row)), dtype=np.float64)
            for c, (j, coeff, const) in enumerate(row):
                immediate = coeff * s + const
                decision[:, c] = immediate + continuation[:, j]
                realised[:, c] = immediate + value_next[:, j]
            chosen = np.argmax(decision, axis=1)
            value_cur[:, i] = np.take_along_axis(realised, chosen[:, None], axis=1)[:, 0]
        value_next = value_cur

    adaptive_values = value_next[:, k0]
    fixed_values = _fixed_schedule_values(model, intrinsic, spot)
    extrinsic_paths = adaptive_values - fixed_values
    extrinsic = float(np.mean(extrinsic_paths))
    standard_error = _standard_error(extrinsic_paths, antithetic)
    return StorageValueResult(
        total=intrinsic.value + extrinsic,
        intrinsic=intrinsic.value,
        extrinsic=extrinsic,
        standard_error=standard_error,
    )


def _fixed_schedule_values(
    model: StorageModel, intrinsic: IntrinsicResult, spot: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Pathwise value of the fixed intrinsic schedule on the simulated spot paths.

    The forward-locked inventory path from :func:`storage_intrinsic` is replayed against every
    price path — the control variate whose common randomness cancels the bulk of the extrinsic
    estimator's variance. Its Monte Carlo mean equals the intrinsic value in expectation (the
    forward is the risk-neutral spot mean).
    """
    n_paths = spot.shape[0]
    horizon = spot.shape[1]
    values = np.zeros(n_paths, dtype=np.float64)
    for t in range(horizon):
        coeff, const = _transition_coeffs(model, intrinsic.inventory[t], intrinsic.inventory[t + 1])
        values += coeff * spot[:, t] + const
    terminal = _terminal_values(model, np.array([intrinsic.inventory[horizon]]))[0]
    return values + float(terminal)
