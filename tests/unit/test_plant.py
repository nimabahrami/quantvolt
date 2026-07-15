"""Unit tests for the thermal-plant model (Task 72; Req 21.1 partial)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from quantvolt.assets.plant import (
    MaxCapacityCurve,
    PlantModel,
    StartCost,
    StartState,
)
from quantvolt.exceptions import ValidationError


def const_heat_rate(rate: float) -> Callable[[float, float], float]:
    return lambda _q, _temp: rate


def const_c_max(capacity: float) -> MaxCapacityCurve:
    return lambda _temp: capacity


def start_costs(
    *,
    hot: float = 50.0,
    warm: float = 100.0,
    cold: float = 200.0,
    fuel: float = 0.0,
    power: float = 0.0,
) -> Mapping[StartState, StartCost]:
    return {
        StartState.HOT: StartCost(fixed=hot, fuel=fuel, power=power),
        StartState.WARM: StartCost(fixed=warm, fuel=fuel, power=power),
        StartState.COLD: StartCost(fixed=cold, fuel=fuel, power=power),
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


def test_valid_plant_constructs_and_is_frozen() -> None:
    plant = make_plant()
    assert plant.c_min == 10.0
    with pytest.raises((AttributeError, TypeError)):
        plant.c_min = 5.0  # type: ignore[misc]


def test_start_state_for_downtime_buckets() -> None:
    plant = make_plant(hot_max_downtime=2, warm_max_downtime=5)
    assert plant.start_state_for_downtime(1) is StartState.HOT
    assert plant.start_state_for_downtime(2) is StartState.HOT
    assert plant.start_state_for_downtime(3) is StartState.WARM
    assert plant.start_state_for_downtime(5) is StartState.WARM
    assert plant.start_state_for_downtime(6) is StartState.COLD
    assert plant.start_state_for_downtime(100) is StartState.COLD


def test_start_cost_combines_components() -> None:
    plant = make_plant(start_costs=start_costs(cold=200.0, fuel=1.5, power=0.5))
    # COLD: fixed 200 + fuel 1.5 * G(20) + power 0.5 * P(60) = 200 + 30 + 30 = 260.
    assert plant.start_cost(StartState.COLD, power_price=60.0, fuel_price=20.0) == 260.0


def test_curve_accessors_delegate_to_callables() -> None:
    plant = make_plant(
        heat_rate=lambda q, _temp: 1.5 + 0.05 * q, c_max=lambda temp: 30.0 if temp <= 25 else 20.0
    )
    assert plant.marginal_heat_rate(20.0, 15.0) == pytest.approx(2.5)
    assert plant.max_capacity(10.0) == 30.0
    assert plant.max_capacity(30.0) == 20.0


def test_representative_temperatures_pass_when_curves_valid() -> None:
    plant = make_plant(representative_temperatures=(0.0, 15.0, 35.0))
    assert plant.max_capacity(0.0) == 30.0


@pytest.mark.parametrize(
    ("overrides", "field_name"),
    [
        ({"c_min": -1.0}, "c_min"),
        ({"ramp_rate": 0.0}, "ramp_rate"),
        ({"ramp_rate": -5.0}, "ramp_rate"),
        ({"variable_om_cost": -0.1}, "variable_om_cost"),
        ({"d_min": -1}, "d_min"),
        ({"d_shutdown": -1}, "d_shutdown"),
        ({"d_startup": -1}, "d_startup"),
        ({"outage_rate": 1.0}, "outage_rate"),
        ({"outage_rate": -0.01}, "outage_rate"),
        ({"outage_rate": 1.5}, "outage_rate"),
        ({"hot_max_downtime": -1}, "hot_max_downtime"),
    ],
)
def test_scalar_validation_names_field(overrides: dict[str, object], field_name: str) -> None:
    with pytest.raises(ValidationError, match=field_name):
        make_plant(**overrides)


def test_warm_below_hot_threshold_rejected() -> None:
    with pytest.raises(ValidationError, match="warm_max_downtime"):
        make_plant(hot_max_downtime=5, warm_max_downtime=2)


def test_missing_start_state_rejected() -> None:
    partial = {
        StartState.HOT: StartCost(50.0, 0.0, 0.0),
        StartState.WARM: StartCost(100.0, 0.0, 0.0),
    }
    with pytest.raises(ValidationError, match="cold"):
        make_plant(start_costs=partial)


@pytest.mark.parametrize(
    ("components", "field_name"),
    [
        ((-1.0, 0.0, 0.0), "StartCost.fixed"),
        ((0.0, -1.0, 0.0), "StartCost.fuel"),
        ((0.0, 0.0, -1.0), "StartCost.power"),
    ],
)
def test_negative_start_cost_component_rejected(
    components: tuple[float, float, float], field_name: str
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        StartCost(*components)


def test_representative_temperature_capacity_below_c_min_rejected() -> None:
    with pytest.raises(ValidationError, match="c_max"):
        make_plant(c_max=const_c_max(5.0), representative_temperatures=(15.0,))


def test_representative_temperature_non_positive_heat_rate_rejected() -> None:
    with pytest.raises(ValidationError, match="heat_rate"):
        make_plant(heat_rate=const_heat_rate(0.0), representative_temperatures=(15.0,))
