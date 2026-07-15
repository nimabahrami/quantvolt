"""Unit tests for perfect-foresight dispatch (Task 72; Req 21.1 partial, 21.4; Property 62).

Every valuation is checked against a hand-worked optimum. The shared plant has a
constant heat rate 2.0, ``c_min = 10``, ``c_max = 30``, zero VOM, ``RR = 10`` and
minimal durations unless a case overrides them, so the per-MWh margin is simply
``P - 2·G`` and hand arithmetic stays transparent.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

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
        ramp_rate=10.0,
        d_min=1,
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=1,
        warm_max_downtime=3,
    )
    params.update(overrides)
    return PlantModel(**params)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Case A: positive spread every period -> run, ramping up as fast as allowed.  #
# --------------------------------------------------------------------------- #
def test_run_all_periods_when_spread_positive() -> None:
    plant = make_plant()  # COLD start = 200
    schedule = dispatch_deterministic(
        plant,
        power_prices=[100.0, 100.0, 100.0, 100.0],
        fuel_prices=[20.0, 20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0, 15.0],
    )
    # Start COLD at c_min (10) then ramp 10 -> 20 -> 30, margin 60/MWh throughout.
    # 400 (=600-200 start) + 1200 + 1800 + 1800 = 5200.
    assert schedule.outputs == (10.0, 20.0, 30.0, 30.0)
    assert schedule.online == (True, True, True, True)
    assert schedule.started == (True, False, False, False)
    assert schedule.stopped == (False, False, False, False)
    assert schedule.margins == pytest.approx((400.0, 1200.0, 1800.0, 1800.0))
    assert schedule.total_value == pytest.approx(5200.0)


# --------------------------------------------------------------------------- #
# Case B: start cost exceeds the best achievable gross margin -> stay off.     #
# --------------------------------------------------------------------------- #
def test_high_start_cost_keeps_unit_off() -> None:
    plant = make_plant(start_costs=start_costs(cold=400.0))
    schedule = dispatch_deterministic(
        plant,
        power_prices=[45.0, 45.0, 45.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
    )
    # Best gross ramping 10->20->30 at 5/MWh is 50+100+150 = 300 < 400 start -> off.
    assert schedule.outputs == (0.0, 0.0, 0.0)
    assert schedule.online == (False, False, False)
    assert schedule.started == (False, False, False)
    assert schedule.total_value == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Case C: ramp rate binds at a single-period price spike.                      #
# --------------------------------------------------------------------------- #
def test_ramp_limit_binds_at_price_spike() -> None:
    plant = make_plant()
    # Already online at c_min entering the horizon; a spike in period 0.
    ramp_limited = dispatch_deterministic(
        plant,
        power_prices=[200.0, 50.0, 50.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
        initial_online=True,
        initial_output=10.0,
        output_step=10.0,
    )
    # From 10 MW the unit can reach only 20 in period 0 (RR = 10), not the 30 it
    # would want at a 160/MWh spread. Then 20 -> 30 -> 30.
    assert ramp_limited.outputs == (20.0, 30.0, 30.0)
    assert ramp_limited.total_value == pytest.approx(20 * 160 + 30 * 10 + 30 * 10)  # 3800

    # Relaxing only the ramp rate (same grid) lets period 0 reach 30 -> proof the
    # ramp rate, not capacity, was binding above.
    faster = make_plant(ramp_rate=20.0)
    relaxed = dispatch_deterministic(
        faster,
        power_prices=[200.0, 50.0, 50.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
        initial_online=True,
        initial_output=10.0,
        output_step=10.0,
    )
    assert relaxed.outputs[0] == 30.0
    assert relaxed.total_value > ramp_limited.total_value


# --------------------------------------------------------------------------- #
# Case D: minimum-run time forces the unit through loss-making periods.        #
# --------------------------------------------------------------------------- #
def test_min_run_forces_operation_through_losses() -> None:
    # Must-run level (c_min == c_max) isolates the commitment decision from ramp.
    plant = make_plant(c_max=const_c_max(10.0), d_min=3)
    forced = dispatch_deterministic(
        plant,
        power_prices=[5.0, 5.0, 100.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
        initial_online=True,
        initial_output=10.0,
        initial_uptime=1,  # only one producing period accrued -> min-run not yet met
    )
    # Uptime 1 < d_min 3, so periods 0 and 1 CANNOT shut down and run at a loss.
    assert forced.online == (True, True, True)
    assert forced.margins[0] < 0 and forced.margins[1] < 0
    assert forced.outputs == (10.0, 10.0, 10.0)
    assert forced.total_value == pytest.approx(-350.0 - 350.0 + 600.0)  # -100

    # With d_min = 1 the unit is free to shut on the first loss period and restart
    # for the profitable one -> a strictly better outcome.
    flexible = make_plant(c_max=const_c_max(10.0), d_min=1)
    optimal = dispatch_deterministic(
        flexible,
        power_prices=[5.0, 5.0, 100.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
        initial_online=True,
        initial_output=10.0,
        initial_uptime=1,
    )
    assert optimal.online[0] is False  # shuts down during the loss
    assert optimal.started[2] is True  # WARM restart (downtime 2) for the spike
    assert optimal.total_value == pytest.approx(600.0 - 100.0)  # 500 > -100
    assert optimal.total_value > forced.total_value


# --------------------------------------------------------------------------- #
# Case E: cold vs hot start cost flips the start decision on identical prices.  #
# --------------------------------------------------------------------------- #
def test_cold_vs_hot_start_changes_decision() -> None:
    plant = make_plant(
        c_max=const_c_max(10.0), start_costs=start_costs(hot=50.0, warm=200.0, cold=700.0)
    )
    prices = dict(
        power_prices=[60.0, 60.0, 60.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
    )
    # 3 periods of gross 200 = 600. HOT start (50) is worth it (net 550).
    hot = dispatch_deterministic(plant, initial_downtime=1, **prices)  # type: ignore[arg-type]
    assert hot.online == (True, True, True)
    assert hot.started[0] is True
    assert hot.total_value == pytest.approx(550.0)

    # Same prices, but a COLD start (700) is not recoverable (600 - 700 < 0) -> off.
    cold = dispatch_deterministic(plant, initial_downtime=10, **prices)  # type: ignore[arg-type]
    assert cold.online == (False, False, False)
    assert cold.total_value == pytest.approx(0.0)


# --------------------------------------------------------------------------- #
# Case F: a rising marginal heat-rate curve makes c_min the optimal output.    #
# --------------------------------------------------------------------------- #
def test_marginal_heat_rate_curve_favours_minimum_load() -> None:
    plant = make_plant(heat_rate=lambda q, _temp: 1.5 + 0.05 * q)
    schedule = dispatch_deterministic(
        plant,
        power_prices=[55.0, 55.0],
        fuel_prices=[20.0, 20.0],
        temperatures=[15.0, 15.0],
        initial_online=True,
        initial_output=10.0,
    )
    # At q=10 HR=2.0 -> 10*(55-40)=150; q=20 HR=2.5 -> 20*(55-50)=100; q=30 loses.
    # Rising heat rate makes running at c_min optimal despite spare capacity.
    assert schedule.outputs == (10.0, 10.0)
    assert schedule.total_value == pytest.approx(300.0)


# --------------------------------------------------------------------------- #
# Case G: temperature-dependent capacity forces a ramp-down when it is hot.     #
# --------------------------------------------------------------------------- #
def test_temperature_dependent_capacity_binds() -> None:
    plant = make_plant(c_max=lambda temp: 30.0 if temp <= 25.0 else 20.0)
    hot_afternoon = dispatch_deterministic(
        plant,
        power_prices=[100.0, 100.0],
        fuel_prices=[20.0, 20.0],
        temperatures=[10.0, 30.0],  # capacity drops 30 -> 20 in period 1
        initial_online=True,
        initial_output=30.0,
    )
    assert hot_afternoon.outputs == (30.0, 20.0)
    assert hot_afternoon.total_value == pytest.approx(30 * 60 + 20 * 60)  # 3000

    # Mild throughout: capacity stays 30, so the unit holds full output.
    mild = dispatch_deterministic(
        plant,
        power_prices=[100.0, 100.0],
        fuel_prices=[20.0, 20.0],
        temperatures=[10.0, 10.0],
        initial_online=True,
        initial_output=30.0,
    )
    assert mild.outputs == (30.0, 30.0)
    assert mild.total_value == pytest.approx(3600.0)


# --------------------------------------------------------------------------- #
# Case H: a start-up lag produces nothing until the unit is available.         #
# --------------------------------------------------------------------------- #
def test_start_up_lag_delays_production() -> None:
    plant = make_plant(c_max=const_c_max(10.0), d_startup=1, start_costs=start_costs(cold=100.0))
    schedule = dispatch_deterministic(
        plant,
        power_prices=[0.0, 100.0, 100.0],
        fuel_prices=[20.0, 20.0, 20.0],
        temperatures=[15.0, 15.0, 15.0],
    )
    # Start decided in period 0 (COLD 100 charged, no output during the lag);
    # unit reaches c_min in period 1 and produces 600 in periods 1 and 2.
    assert schedule.outputs == (0.0, 10.0, 10.0)
    assert schedule.online == (False, True, True)
    assert schedule.started == (True, False, False)
    assert schedule.margins == pytest.approx((-100.0, 600.0, 600.0))
    assert schedule.total_value == pytest.approx(1100.0)


# --------------------------------------------------------------------------- #
# Discounting: per-period margins scale and still sum to the total.            #
# --------------------------------------------------------------------------- #
def test_discount_factors_scale_and_sum_to_total() -> None:
    plant = make_plant()
    schedule = dispatch_deterministic(
        plant,
        power_prices=[100.0, 100.0],
        fuel_prices=[20.0, 20.0],
        temperatures=[15.0, 15.0],
        initial_online=True,
        initial_output=30.0,
        discount_factors=[1.0, 0.5],
    )
    # 30 MW * 60/MWh = 1800 gross; second period halved.
    assert schedule.margins == pytest.approx((1800.0, 900.0))
    assert schedule.total_value == pytest.approx(sum(schedule.margins))


# --------------------------------------------------------------------------- #
# Determinism and input immutability.                                          #
# --------------------------------------------------------------------------- #
def test_deterministic_repeated_calls_identical() -> None:
    plant = make_plant()
    args = dict(
        power_prices=[100.0, 40.0, 100.0, 100.0],
        fuel_prices=[20.0, 20.0, 20.0, 20.0],
        temperatures=[15.0, 20.0, 25.0, 30.0],
    )
    first = dispatch_deterministic(plant, **args)  # type: ignore[arg-type]
    second = dispatch_deterministic(plant, **args)  # type: ignore[arg-type]
    assert first == second
    assert isinstance(first, DispatchSchedule)


def test_inputs_not_mutated() -> None:
    plant = make_plant()
    power = [100.0, 100.0, 100.0]
    fuel = [20.0, 20.0, 20.0]
    temps = [15.0, 15.0, 15.0]
    discounts = [1.0, 0.99, 0.98]
    schedule = assert_input_unchanged(
        dispatch_deterministic,
        plant,
        power,
        fuel,
        temps,
        discount_factors=discounts,
    )
    assert schedule.total_value > 0.0


# --------------------------------------------------------------------------- #
# Validation error paths.                                                      #
# --------------------------------------------------------------------------- #
def test_empty_series_rejected() -> None:
    with pytest.raises(ValidationError, match="power_prices"):
        dispatch_deterministic(make_plant(), power_prices=[], fuel_prices=[], temperatures=[])


def test_mismatched_series_lengths_rejected() -> None:
    with pytest.raises(ValidationError, match="same length"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0, 100.0],
            fuel_prices=[20.0],
            temperatures=[15.0, 15.0],
        )


def test_non_positive_discount_factor_rejected() -> None:
    with pytest.raises(ValidationError, match="discount_factors"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            discount_factors=[0.0],
        )


def test_non_positive_output_step_rejected() -> None:
    with pytest.raises(ValidationError, match="output_step"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            output_step=0.0,
        )


def test_capacity_below_c_min_rejected_at_dispatch() -> None:
    plant = make_plant(c_max=const_c_max(5.0))  # c_max < c_min (10)
    with pytest.raises(ValidationError, match="c_max"):
        dispatch_deterministic(plant, power_prices=[100.0], fuel_prices=[20.0], temperatures=[15.0])


def test_non_positive_heat_rate_rejected_at_dispatch() -> None:
    plant = make_plant(heat_rate=const_heat_rate(0.0))
    with pytest.raises(ValidationError, match="heat_rate"):
        dispatch_deterministic(plant, power_prices=[100.0], fuel_prices=[20.0], temperatures=[15.0])


def test_initial_output_off_grid_rejected() -> None:
    with pytest.raises(ValidationError, match="output grid"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            initial_online=True,
            initial_output=17.0,  # not on {10, 20, 30}
        )


def test_initial_uptime_below_one_rejected() -> None:
    with pytest.raises(ValidationError, match="initial_uptime"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            initial_online=True,
            initial_output=10.0,
            initial_uptime=0,
        )


def test_negative_initial_downtime_rejected() -> None:
    with pytest.raises(ValidationError, match="initial_downtime"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            initial_downtime=-1,
        )


def test_zero_initial_downtime_rejected_when_offline() -> None:
    # Bugfix regression: initial_downtime=0 used to be silently accepted and then
    # clamped to 1 by max(1, min(downtime, down_cap)), relaxing the min-down
    # constraint by one period (a unit "not online" has necessarily been offline for
    # at least one period; 0 is a contradiction, not a valid edge case). With
    # d_shutdown=1 this let a caller's initial_downtime=0 restart the unit at t=0 as
    # if it had already served its one-period minimum-down time. Now rejected with a
    # ValidationError mirroring the online branch's "initial_uptime must be >= 1"
    # message style.
    with pytest.raises(ValidationError, match="initial_downtime must be >= 1 when offline"):
        dispatch_deterministic(
            make_plant(),
            power_prices=[100.0],
            fuel_prices=[20.0],
            temperatures=[15.0],
            initial_downtime=0,
        )


def test_initial_downtime_of_one_still_accepted_and_behaves_as_before() -> None:
    # initial_downtime=1 was (and remains) the smallest valid offline downtime; it
    # must keep working exactly as before the fix (the fix only tightens the
    # rejected range, it does not change the clamp-to-down_cap ceiling behaviour).
    plant = make_plant()  # d_shutdown=1: downtime=1 already satisfies the min-down gate
    result = dispatch_deterministic(
        plant,
        power_prices=[100.0],
        fuel_prices=[20.0],
        temperatures=[15.0],
        initial_downtime=1,
    )
    assert isinstance(result, DispatchSchedule)
    assert result.online[0] is True  # a start is immediately feasible at downtime=1


def test_infeasible_initial_condition_rejected() -> None:
    # Online at 30 MW, but period-0 capacity collapses to 10 (hot), the unit cannot
    # ramp down that far in one step (RR=5) and min-run (d_min=5) forbids shutting.
    plant = make_plant(c_max=lambda temp: 30.0 if temp <= 25.0 else 10.0, ramp_rate=5.0, d_min=5)
    with pytest.raises(ValidationError, match="no feasible schedule"):
        dispatch_deterministic(
            plant,
            power_prices=[100.0, 100.0],
            fuel_prices=[20.0, 20.0],
            temperatures=[100.0, 15.0],  # capacity 10 then 30
            initial_online=True,
            initial_output=30.0,
            initial_uptime=1,
        )
