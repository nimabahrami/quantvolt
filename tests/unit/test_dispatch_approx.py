"""Unit tests for dispatch heuristics and approximations (Task 74; Req 21.3).

Every approximation is checked against the *exact* deterministic DP
(:func:`dispatch_deterministic`), which is noise-free, so the reconciliation
identities are equalities up to float tolerance rather than statistical claims:

- ``time_aggregate`` is exact on block-constant prices (no start within the
  horizon);
- ``horizon_divide`` equals the full solve when the periods decouple (zero start
  costs, non-binding durations);
- ``bang_bang`` is exact for a linear heat rate and a downward-biased lower bound
  for a steep one (documented direction of bias), and emits the Req-21.3 warning.

The shared plant mirrors the deterministic-dispatch tests: constant heat rate 2.0,
``c_min = 10``, ``c_max = 30``, zero VOM, ``RR`` large enough that the full load is
reachable in one step, so a per-MWh margin is simply ``P - 2·G`` and hand
arithmetic stays transparent unless a case overrides the curve.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Mapping

import pytest

from quantvolt.assets.dispatch_approx import (
    BangBangHedgeWarning,
    bang_bang,
    horizon_divide,
    time_aggregate,
)
from quantvolt.assets.dispatch_deterministic import DispatchSchedule, dispatch_deterministic
from quantvolt.assets.plant import MaxCapacityCurve, PlantModel, StartCost, StartState
from quantvolt.exceptions import ValidationError
from quantvolt.testing import assert_input_unchanged


def const_heat_rate(rate: float) -> Callable[[float, float], float]:
    return lambda _q, _temp: rate


def const_c_max(capacity: float) -> MaxCapacityCurve:
    return lambda _temp: capacity


def start_costs(
    *, hot: float = 50.0, warm: float = 100.0, cold: float = 200.0
) -> Mapping[StartState, StartCost]:
    return {
        StartState.HOT: StartCost(fixed=hot, fuel=0.0, power=0.0),
        StartState.WARM: StartCost(fixed=warm, fuel=0.0, power=0.0),
        StartState.COLD: StartCost(fixed=cold, fuel=0.0, power=0.0),
    }


def make_plant(**overrides: object) -> PlantModel:
    params: dict[str, object] = dict(
        heat_rate=const_heat_rate(2.0),
        c_min=10.0,
        c_max=const_c_max(30.0),
        variable_om_cost=0.0,
        start_costs=start_costs(),
        ramp_rate=20.0,  # >= operating range (30 - 10): full load reachable in one step
        d_min=1,
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=1,
        warm_max_downtime=3,
    )
    params.update(overrides)
    return PlantModel(**params)  # type: ignore[arg-type]


def bang_bang_quiet(plant: PlantModel, *args: object, **kwargs: object) -> DispatchSchedule:
    """Call ``bang_bang`` suppressing its advisory warning (the warning is tested separately)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", BangBangHedgeWarning)
        return bang_bang(plant, *args, **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# time_aggregate: exact on block-constant prices.                             #
# --------------------------------------------------------------------------- #
def test_time_aggregate_exact_on_block_constant_prices() -> None:
    plant = make_plant()
    # Block-constant power (two 4-hour blocks); positive spread throughout so an
    # already-online unit never starts/stops -> no start-cost replication artifact.
    power = [100.0, 100.0, 100.0, 100.0, 80.0, 80.0, 80.0, 80.0]
    fuel = [20.0] * 8
    temps = [15.0] * 8
    common = dict(initial_online=True, initial_output=30.0, output_step=10.0)

    full = dispatch_deterministic(plant, power, fuel, temps, **common)  # type: ignore[arg-type]
    approx = time_aggregate(plant, power, fuel, temps, 4, **common)  # type: ignore[arg-type]

    # spread 60 for 4h then 40 for 4h at 30 MW: 4*1800 + 4*1200 = 12000.
    assert full.total_value == pytest.approx(12000.0)
    assert approx.total_value == pytest.approx(full.total_value)
    assert approx.outputs == full.outputs == (30.0,) * 8
    assert approx.online == (True,) * 8


def test_time_aggregate_block_hours_one_is_identity() -> None:
    plant = make_plant()
    power = [100.0, 40.0, 100.0]
    fuel = [20.0] * 3
    temps = [15.0] * 3
    full = dispatch_deterministic(plant, power, fuel, temps)
    approx = time_aggregate(plant, power, fuel, temps, 1)
    assert approx.outputs == full.outputs
    assert approx.online == full.online
    assert approx.total_value == pytest.approx(full.total_value)


# --------------------------------------------------------------------------- #
# horizon_divide: equals the full solve when the periods decouple.            #
# --------------------------------------------------------------------------- #
def _decoupled_plant() -> PlantModel:
    # Single online level (c_min == c_max) removes the ramp transient; zero start
    # costs and zero durations make the dispatch myopic -> fully decoupled.
    return make_plant(
        c_min=20.0,
        c_max=const_c_max(20.0),
        start_costs=start_costs(hot=0.0, warm=0.0, cold=0.0),
        ramp_rate=10.0,
        d_min=0,
        d_shutdown=0,
        d_startup=0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )


def test_horizon_divide_equals_full_solve_when_decoupled() -> None:
    plant = _decoupled_plant()
    power = [100.0, 30.0, 100.0, 30.0, 100.0, 30.0]  # spread 60 / -10 alternating
    fuel = [20.0] * 6
    temps = [15.0] * 6

    full = dispatch_deterministic(plant, power, fuel, temps)
    approx = horizon_divide(plant, power, fuel, temps, 2)

    # Each profitable period runs at 20 (1200); each unprofitable one is off.
    assert full.total_value == pytest.approx(3600.0)
    assert approx.total_value == pytest.approx(full.total_value)
    assert approx.outputs == full.outputs == (20.0, 0.0, 20.0, 0.0, 20.0, 0.0)


def test_horizon_divide_boundary_state_approximation_understates() -> None:
    # Costly restart + always-profitable spread: the full solve starts once and runs;
    # dividing forces a spurious restart at every sub-horizon boundary.
    plant = make_plant(
        c_min=20.0,
        c_max=const_c_max(20.0),
        start_costs=start_costs(hot=300.0, warm=300.0, cold=300.0),
        ramp_rate=10.0,
        d_min=0,
        d_shutdown=0,
        d_startup=0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )
    power = [100.0] * 6  # spread 60 -> 1200/period at 20 MW
    fuel = [20.0] * 6
    temps = [15.0] * 6

    full = dispatch_deterministic(plant, power, fuel, temps)
    approx = horizon_divide(plant, power, fuel, temps, 2)

    # Full: one cold start (300) + 6*1200 = 6900. Divided: three starts -> 3*2100 = 6300.
    assert full.total_value == pytest.approx(6900.0)
    assert approx.total_value == pytest.approx(6300.0)
    assert approx.total_value < full.total_value
    assert sum(approx.started) == 3  # one restart per sub-horizon
    assert sum(full.started) == 1


# --------------------------------------------------------------------------- #
# bang_bang: exact for a linear heat rate, lower bound for a steep one.        #
# --------------------------------------------------------------------------- #
def test_bang_bang_exact_for_linear_heat_rate() -> None:
    # Constant (linear) heat rate: the optimal load is always a corner, so pinning
    # to c_max loses nothing when the spread is positive throughout.
    plant = make_plant()
    power = [100.0, 60.0, 100.0, 60.0]  # spread 60 / 20, both positive
    fuel = [20.0] * 4
    temps = [15.0] * 4
    common = dict(initial_online=True, initial_output=30.0, output_step=10.0)

    exact = dispatch_deterministic(plant, power, fuel, temps, **common)  # type: ignore[arg-type]
    approx = bang_bang_quiet(plant, power, fuel, temps, **common)

    assert exact.total_value == pytest.approx(4800.0)
    assert approx.total_value == pytest.approx(exact.total_value)
    assert approx.outputs == exact.outputs == (30.0,) * 4


def test_bang_bang_lower_bounds_exact_on_steep_heat_curve() -> None:
    # Steep rising marginal heat rate: margin q*(25 - q) peaks at part load (q=10 ->
    # 150) and is negative at full load (q=30 -> -150). The exact DP runs efficiently
    # at c_min; bang-bang, pinned to c_max, would lose money and shuts off instead.
    plant = make_plant(heat_rate=lambda q, _temp: 1.5 + 0.05 * q)
    power = [55.0] * 4
    fuel = [20.0] * 4
    temps = [15.0] * 4
    common = dict(initial_online=True, initial_output=30.0, output_step=10.0)

    exact = dispatch_deterministic(plant, power, fuel, temps, **common)  # type: ignore[arg-type]
    approx = bang_bang_quiet(plant, power, fuel, temps, **common)

    assert exact.total_value == pytest.approx(600.0)  # runs at c_min = 10, 150/period
    assert exact.outputs == (10.0,) * 4
    # Documented direction: bang-bang is a lower bound, strict here.
    assert approx.total_value <= exact.total_value + 1e-9
    assert approx.total_value < exact.total_value
    assert approx.total_value == pytest.approx(0.0)  # off: full load is loss-making
    assert approx.outputs == (0.0,) * 4


def test_bang_bang_pins_online_output_to_full_load() -> None:
    # Whatever the interior optimum, bang-bang only ever produces 0 or c_max.
    plant = make_plant()
    power = [100.0, 100.0, 100.0]
    fuel = [20.0] * 3
    temps = [15.0] * 3
    approx = bang_bang_quiet(plant, power, fuel, temps)
    assert set(approx.outputs) <= {0.0, 30.0}
    assert approx.outputs == (30.0, 30.0, 30.0)  # positive spread -> full load


# --------------------------------------------------------------------------- #
# bang_bang: the Req-21.3 hedge-sensitivity warning fires.                     #
# --------------------------------------------------------------------------- #
def test_bang_bang_emits_hedge_warning() -> None:
    plant = make_plant()
    with pytest.warns(BangBangHedgeWarning, match="hedge") as record:
        bang_bang(plant, [100.0, 100.0], [20.0, 20.0], [15.0, 15.0])
    assert len(record) == 1
    assert "value" in str(record[0].message)


def test_time_aggregate_and_horizon_divide_do_not_warn() -> None:
    plant = make_plant()
    power = [100.0, 100.0, 100.0, 100.0]
    fuel = [20.0] * 4
    temps = [15.0] * 4
    with warnings.catch_warnings():
        warnings.simplefilter("error", BangBangHedgeWarning)
        time_aggregate(plant, power, fuel, temps, 2)
        horizon_divide(plant, power, fuel, temps, 2)


# --------------------------------------------------------------------------- #
# Determinism.                                                                 #
# --------------------------------------------------------------------------- #
def test_all_approximations_deterministic() -> None:
    plant = make_plant()
    power = [100.0, 40.0, 100.0, 40.0]
    fuel = [20.0] * 4
    temps = [15.0, 20.0, 25.0, 30.0]

    assert time_aggregate(plant, power, fuel, temps, 2) == time_aggregate(
        plant, power, fuel, temps, 2
    )
    assert horizon_divide(plant, power, fuel, temps, 2) == horizon_divide(
        plant, power, fuel, temps, 2
    )
    assert bang_bang_quiet(plant, power, fuel, temps) == bang_bang_quiet(plant, power, fuel, temps)
    assert isinstance(time_aggregate(plant, power, fuel, temps, 2), DispatchSchedule)


# --------------------------------------------------------------------------- #
# Input immutability (Req 11.4).                                              #
# --------------------------------------------------------------------------- #
def test_time_aggregate_inputs_not_mutated() -> None:
    plant = make_plant()
    power = [100.0, 100.0, 100.0, 100.0]
    fuel = [20.0] * 4
    temps = [15.0] * 4
    discounts = [1.0, 0.99, 0.98, 0.97]
    result = assert_input_unchanged(
        time_aggregate, plant, power, fuel, temps, 2, discount_factors=discounts
    )
    assert result.total_value > 0.0


def test_horizon_divide_inputs_not_mutated() -> None:
    plant = make_plant()
    power = [100.0, 40.0, 100.0, 40.0]
    fuel = [20.0] * 4
    temps = [15.0] * 4
    discounts = [1.0, 0.99, 0.98, 0.97]
    result = assert_input_unchanged(
        horizon_divide, plant, power, fuel, temps, 2, discount_factors=discounts
    )
    assert isinstance(result, DispatchSchedule)


def test_bang_bang_inputs_not_mutated() -> None:
    plant = make_plant()
    power = [100.0, 100.0, 100.0]
    fuel = [20.0] * 3
    temps = [15.0] * 3
    result = assert_input_unchanged(bang_bang_quiet, plant, power, fuel, temps)
    assert result.total_value > 0.0


# --------------------------------------------------------------------------- #
# Validation error paths.                                                      #
# --------------------------------------------------------------------------- #
def test_time_aggregate_non_positive_block_hours_rejected() -> None:
    with pytest.raises(ValidationError, match="block_hours"):
        time_aggregate(make_plant(), [100.0], [20.0], [15.0], 0)


def test_time_aggregate_block_hours_must_divide_horizon() -> None:
    with pytest.raises(ValidationError, match="divide the horizon"):
        time_aggregate(make_plant(), [100.0] * 5, [20.0] * 5, [15.0] * 5, 2)


def test_time_aggregate_empty_series_rejected() -> None:
    with pytest.raises(ValidationError, match="power_prices"):
        time_aggregate(make_plant(), [], [], [], 4)


def test_horizon_divide_non_positive_sub_horizon_rejected() -> None:
    with pytest.raises(ValidationError, match="sub_horizon"):
        horizon_divide(make_plant(), [100.0], [20.0], [15.0], 0)


def test_horizon_divide_mismatched_series_rejected() -> None:
    with pytest.raises(ValidationError, match="same length"):
        horizon_divide(make_plant(), [100.0, 100.0], [20.0], [15.0, 15.0], 1)


def test_bang_bang_mismatched_series_rejected() -> None:
    with pytest.raises(ValidationError, match="same length"):
        bang_bang(make_plant(), [100.0, 100.0], [20.0], [15.0, 15.0])


def test_bang_bang_capacity_below_c_min_rejected() -> None:
    plant = make_plant(c_max=const_c_max(5.0))  # c_max 5 < c_min 10 everywhere
    with pytest.raises(ValidationError, match="falls below"):
        bang_bang(plant, [100.0], [20.0], [15.0])


def test_horizon_divide_tolerates_ragged_final_sub_horizon() -> None:
    # horizon_divide tolerates a short final sub-horizon (no divisibility requirement).
    plant = _decoupled_plant()
    power = [100.0, 30.0, 100.0]  # 3 periods, sub_horizon 2 -> blocks [0,1] and [2]
    fuel = [20.0] * 3
    temps = [15.0] * 3
    full = dispatch_deterministic(plant, power, fuel, temps)
    approx = horizon_divide(plant, power, fuel, temps, 2)
    assert approx.total_value == pytest.approx(full.total_value)
    assert approx.outputs == full.outputs
