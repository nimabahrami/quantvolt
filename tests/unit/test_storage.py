"""Unit / property tests for gas storage valuation (Task 75).

Exercises ``assets.storage`` — ``StorageModel``, ``storage_intrinsic`` (forward-locked
DP, Req 22.1) and ``storage_value`` (LSM total/extrinsic, Req 22.2). Coverage maps to
Requirements 22.1-22.4 and design Properties 64-65:

* Req 22.1 — hand-worked 3-period intrinsic optimum (inject low, withdraw high, ratchet
  forces the injection split over two periods), exact to the currency unit; costs, losses
  and carry verified against a closed-form 2-period case.
* Req 22.3 / Property 64 — inventory bounds and ratchets hold at *every* step of any
  returned schedule (checked explicitly); inconsistent models raise ``ValidationError``
  naming the offending fields; hard terminal targets are enforced exactly and unreachable
  targets raise.
* Req 22.2 / Property 64 — ``extrinsic = total - intrinsic >= 0``: strictly positive on a
  flat curve (pure time value) across seeds, and never below the documented Monte Carlo
  tolerance floor (3 standard errors) in the drift-dominated contango case where the true
  timing value is ~0. ``total == intrinsic + extrinsic`` exactly by construction.
* Req 22.4 / Property 65 — idealized two-period frictionless full-capacity store:
  ``storage_intrinsic == max(0, calendar_spread * volume)`` against
  :func:`quantvolt.pricing.spreads.calendar_spread`, in contango and backwardation.
* Req 11.2 — determinism under a fixed seed; Req 11.4 — input immutability via
  :func:`quantvolt.testing.assert_input_unchanged`.

Conventions under test (see the module docstring of ``assets.storage``): undiscounted cash
flows; inventory is working gas with fuel-in-kind losses on the market leg
(``buy a/(1-loss_in)`` to inject ``a``; deliver ``w·(1-loss_out)`` when withdrawing ``w``);
carry charged on end-of-period inventory; uniform inventory grid with on-grid
initial/terminal levels.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest

from quantvolt.assets.storage import (
    IntrinsicResult,
    StorageFactorModel,
    StorageModel,
    storage_intrinsic,
    storage_value,
)
from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.spreads import calendar_spread
from quantvolt.testing import assert_input_unchanged

_GAS = CommodityConfig(
    commodity_id="TTF",
    price_unit="EUR/MWh",
    hub=Hub(hub_id="TTF", exchange="ICE", price_unit="EUR/MWh"),
)


def _curve(prices: list[float]) -> ForwardCurve:
    """Monthly forward curve starting 2026-01 with the given node prices."""
    nodes = tuple(
        CurveNode(
            period=DeliveryPeriod(year=2026 + index // 12, month=index % 12 + 1),
            price=price,
            status="observed",
        )
        for index, price in enumerate(prices)
    )
    return ForwardCurve(commodity=_GAS, market_date=date(2026, 1, 1), nodes=nodes)


def _model(**overrides: object) -> StorageModel:
    """A frictionless 0..2 store, rate 1 in / 2 out, empty-to-empty."""
    params: dict[str, object] = {
        "min_inventory": 0.0,
        "max_inventory": 2.0,
        "initial_inventory": 0.0,
        "terminal_inventory": 0.0,
        "injection_rate": lambda inv: 1.0,
        "withdrawal_rate": lambda inv: 2.0,
    }
    params.update(overrides)
    return StorageModel(**params)  # type: ignore[arg-type]


def _assert_schedule_feasible(model: StorageModel, result: IntrinsicResult) -> None:
    """Bounds, ratchets and the inventory balance hold at every step (Req 22.3)."""
    tol = 1e-9
    horizon = len(result.injection)
    assert len(result.inventory) == horizon + 1
    for t in range(horizon):
        inv = result.inventory[t]
        assert model.min_inventory - tol <= inv <= model.max_inventory + tol
        assert 0.0 <= result.injection[t] <= model.injection_rate(inv) + tol
        assert 0.0 <= result.withdrawal[t] <= model.withdrawal_rate(inv) + tol
        assert not (result.injection[t] > tol and result.withdrawal[t] > tol)
        balance = inv + result.injection[t] - result.withdrawal[t]
        assert result.inventory[t + 1] == pytest.approx(balance, abs=tol)
    final = result.inventory[horizon]
    assert model.min_inventory - tol <= final <= model.max_inventory + tol


# --- Req 22.1: hand-worked intrinsic optimum --------------------------------------


def test_intrinsic_three_period_hand_worked_exact() -> None:
    # Prices (1, 1, 5); inject at most 1/period, withdraw at most 2/period, capacity 2.
    # Optimal: inject 1 @ 1, inject 1 @ 1, withdraw 2 @ 5 -> value = -1 - 1 + 10 = 8.
    # The injection ratchet (rate 1 < capacity 2) is what forces the two-period fill.
    model = _model()
    result = storage_intrinsic(model, _curve([1.0, 1.0, 5.0]), inventory_step=1.0)
    assert result.value == pytest.approx(8.0, abs=1e-12)
    assert result.inventory == (0.0, 1.0, 2.0, 0.0)
    assert result.injection == (1.0, 1.0, 0.0)
    assert result.withdrawal == (0.0, 0.0, 2.0)
    assert result.cashflow == pytest.approx((-1.0, -1.0, 10.0), abs=1e-12)
    assert sum(result.cashflow) == pytest.approx(result.value, abs=1e-12)
    _assert_schedule_feasible(model, result)


def test_intrinsic_level_dependent_ratchet_respected() -> None:
    # injection_rate(inv) = 2 - inv: full speed empty, zero when full. Optimal with
    # prices (1, 2, 10): fill both units at t=0 (-2), idle, withdraw 2 @ 10 -> 18.
    # Splitting the fill (1 @ 1, 1 @ 2) would earn only 17.
    model = _model(injection_rate=lambda inv: 2.0 - inv)
    result = storage_intrinsic(model, _curve([1.0, 2.0, 10.0]), inventory_step=1.0)
    assert result.value == pytest.approx(18.0, abs=1e-12)
    assert result.injection == (2.0, 0.0, 0.0)
    assert result.withdrawal == (0.0, 0.0, 2.0)
    _assert_schedule_feasible(model, result)


def test_intrinsic_costs_losses_and_carry_closed_form() -> None:
    # 0..1 store, prices (10, 50): inject 1 then withdraw 1. Cash flows follow the
    # documented working-gas conventions:
    #   inject:   -10 / (1 - 0.1) - 0.5·1 - 0.1·1   (buy grossed-up gas, cost, carry on 1)
    #   withdraw:  50 · (1 - 0.2) - 0.25·1 - 0.1·0  (sell net-of-fuel gas, cost, carry on 0)
    model = _model(
        max_inventory=1.0,
        injection_rate=lambda inv: 1.0,
        withdrawal_rate=lambda inv: 1.0,
        injection_cost=0.5,
        withdrawal_cost=0.25,
        injection_loss=0.1,
        withdrawal_loss=0.2,
        carry_cost=0.1,
    )
    result = storage_intrinsic(model, _curve([10.0, 50.0]), inventory_step=1.0)
    inject_cash = -10.0 / 0.9 - 0.5 - 0.1
    withdraw_cash = 50.0 * 0.8 - 0.25
    assert result.cashflow == pytest.approx((inject_cash, withdraw_cash), abs=1e-12)
    assert result.value == pytest.approx(inject_cash + withdraw_cash, abs=1e-12)
    _assert_schedule_feasible(model, result)


def test_intrinsic_backwardation_with_empty_start_stays_idle() -> None:
    # Falling prices and an empty store: nothing profitable is feasible -> idle, value 0.
    model = _model()
    result = storage_intrinsic(model, _curve([9.0, 6.0, 3.0]), inventory_step=1.0)
    assert result.value == pytest.approx(0.0, abs=1e-12)
    assert result.inventory == (0.0, 0.0, 0.0, 0.0)
    _assert_schedule_feasible(model, result)


# --- Req 22.3: terminal condition ---------------------------------------------------


def test_hard_terminal_target_enforced_exactly() -> None:
    # Selling the initial unit at 100 is tempting, but the hard target says finish full.
    model = _model(
        max_inventory=1.0,
        initial_inventory=1.0,
        terminal_inventory=1.0,
        withdrawal_rate=lambda inv: 1.0,
    )
    result = storage_intrinsic(model, _curve([100.0]), inventory_step=1.0)
    assert result.inventory[-1] == pytest.approx(model.terminal_inventory, abs=1e-12)
    assert result.value == pytest.approx(0.0, abs=1e-12)


def test_soft_terminal_penalty_trades_off_against_price() -> None:
    # Same store with a soft penalty of 1/unit: selling @ 100 and paying |0 - 1| = 1 wins.
    model = _model(
        max_inventory=1.0,
        initial_inventory=1.0,
        terminal_inventory=1.0,
        withdrawal_rate=lambda inv: 1.0,
        terminal_penalty=1.0,
    )
    result = storage_intrinsic(model, _curve([100.0]), inventory_step=1.0)
    assert result.inventory[-1] == pytest.approx(0.0, abs=1e-12)
    assert result.value == pytest.approx(99.0, abs=1e-12)


def test_unreachable_hard_terminal_target_raises() -> None:
    # Empty store, target full, but the horizon is too short at rate 1 to inject 2.
    model = _model(terminal_inventory=2.0)
    with pytest.raises(ValidationError, match="terminal_inventory is unreachable"):
        storage_intrinsic(model, _curve([1.0]), inventory_step=1.0)


# --- Req 22.3: inconsistent models raise naming the fields ---------------------------


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"min_inventory": 3.0}, "min_inventory.*max_inventory"),
        ({"initial_inventory": 5.0}, "initial_inventory"),
        ({"terminal_inventory": -1.0}, "terminal_inventory"),
        ({"injection_cost": -0.1}, "injection_cost"),
        ({"withdrawal_cost": -0.1}, "withdrawal_cost"),
        ({"carry_cost": -0.1}, "carry_cost"),
        ({"injection_loss": 1.0}, "injection_loss"),
        ({"withdrawal_loss": -0.2}, "withdrawal_loss"),
        ({"terminal_penalty": -1.0}, "terminal_penalty"),
    ],
)
def test_inconsistent_model_raises_naming_field(overrides: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        _model(**overrides)


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"injection_rate": lambda inv: -1.0}, "injection_rate"),
        ({"withdrawal_rate": lambda inv: -1.0}, "withdrawal_rate"),
    ],
)
def test_negative_rate_curve_raises_at_valuation(overrides: dict, match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        storage_intrinsic(_model(**overrides), _curve([1.0, 5.0]), inventory_step=1.0)


def test_off_grid_initial_inventory_and_bad_step_raise() -> None:
    with pytest.raises(ValidationError, match=r"initial_inventory.*grid"):
        storage_intrinsic(_model(initial_inventory=0.5), _curve([1.0, 5.0]), inventory_step=1.0)
    with pytest.raises(ValidationError, match="inventory_step"):
        storage_intrinsic(_model(), _curve([1.0, 5.0]), inventory_step=-1.0)


def test_negative_seed_raises() -> None:
    factor = StorageFactorModel(volatility=0.5, dt=1 / 12, path_count=100)
    with pytest.raises(ValidationError, match="seed"):
        storage_value(_model(), _curve([1.0, 5.0]), factor, seed=-1, inventory_step=1.0)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"volatility": 0.0}, "volatility"),
        ({"dt": 0.0}, "dt"),
        ({"path_count": 0}, "path_count"),
    ],
)
def test_factor_model_rejects_bad_inputs(kwargs: dict, match: str) -> None:
    base: dict = {"volatility": 0.5, "dt": 1 / 12, "path_count": 100}
    base.update(kwargs)
    with pytest.raises(ValidationError, match=match):
        StorageFactorModel(**base)


# --- Property 65: storage >= calendar-spread strategy (idealized, Req 22.4) ----------


def test_property_65_contango_matches_calendar_spread_times_volume() -> None:
    # Idealized: two periods, no costs/losses/carry, rates = full working capacity.
    # The store then IS the calendar-spread strategy: buy volume V in the early period,
    # sell it in the late period -> intrinsic == max(0, spread) · V, exactly.
    volume = 3.0
    model = StorageModel(
        min_inventory=0.0,
        max_inventory=volume,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda inv: volume,
        withdrawal_rate=lambda inv: volume,
    )
    curve = _curve([2.0, 7.0])
    spread = calendar_spread(curve, DeliveryPeriod(2026, 1), DeliveryPeriod(2026, 2))
    result = storage_intrinsic(model, curve)  # default grid: covers the no-step path
    assert spread.spread == pytest.approx(5.0, abs=1e-12)
    assert result.value == pytest.approx(max(0.0, spread.spread) * volume, abs=1e-9)
    _assert_schedule_feasible(model, result)


def test_property_65_backwardation_floor_at_zero() -> None:
    # Backwardation: the spread strategy would lock a loss; the store optimally idles,
    # so its value is the option floor max(0, spread · V) = 0 >= spread · V.
    volume = 3.0
    model = StorageModel(
        min_inventory=0.0,
        max_inventory=volume,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda inv: volume,
        withdrawal_rate=lambda inv: volume,
    )
    curve = _curve([7.0, 2.0])
    spread = calendar_spread(curve, DeliveryPeriod(2026, 1), DeliveryPeriod(2026, 2))
    result = storage_intrinsic(model, curve)
    assert spread.spread < 0.0
    assert result.value == pytest.approx(0.0, abs=1e-9)
    assert result.value >= spread.spread * volume


# --- Property 64: extrinsic >= 0; total = intrinsic + extrinsic (Req 22.2) -----------

_FLAT_CURVE = [20.0] * 6
_FLAT_FACTOR = StorageFactorModel(volatility=0.8, dt=1 / 12, path_count=4000)


def _fast_store() -> StorageModel:
    return _model(injection_rate=lambda inv: 2.0, withdrawal_rate=lambda inv: 2.0)


@pytest.mark.parametrize("seed", [1, 7, 2024])
def test_extrinsic_positive_on_flat_curve(seed: int) -> None:
    # A flat curve has zero intrinsic value; everything the adaptive policy earns is
    # re-optimisation (time) value, so extrinsic must be strictly positive (Property 64).
    result = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=seed, inventory_step=1.0
    )
    assert result.intrinsic == pytest.approx(0.0, abs=1e-12)
    assert result.extrinsic > 0.0
    assert result.total == result.intrinsic + result.extrinsic  # exact, by construction
    assert result.standard_error > 0.0


def test_extrinsic_never_below_mc_tolerance_floor_in_contango() -> None:
    # Steep contango under a martingale factor: holding to the end is optimal, so the
    # true extrinsic is ~0 and the estimate may sample slightly negative. The documented
    # tolerance floor is a few standard errors; assert extrinsic >= -3·SE, unclamped.
    factor = StorageFactorModel(volatility=0.7, dt=1 / 12, path_count=4000)
    curve = _curve([15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
    for seed in (1, 2024):
        result = storage_value(_fast_store(), curve, factor, seed=seed, inventory_step=1.0)
        assert result.intrinsic == pytest.approx(10.0, abs=1e-9)
        assert result.extrinsic >= -3.0 * result.standard_error
        assert result.total == result.intrinsic + result.extrinsic


def test_total_value_dominates_calendar_spread_strategy() -> None:
    # Property 65 at the stochastic level: total >= the locked spread strategy's value
    # (= the intrinsic here) minus the MC tolerance floor.
    volume = 2.0
    model = StorageModel(
        min_inventory=0.0,
        max_inventory=volume,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda inv: volume,
        withdrawal_rate=lambda inv: volume,
    )
    curve = _curve([10.0, 14.0])
    spread = calendar_spread(curve, DeliveryPeriod(2026, 1), DeliveryPeriod(2026, 2))
    factor = StorageFactorModel(volatility=0.6, dt=1 / 12, path_count=2000)
    result = storage_value(model, curve, factor, seed=2024, inventory_step=1.0)
    locked = max(0.0, spread.spread) * volume
    assert result.intrinsic == pytest.approx(locked, abs=1e-9)
    assert result.total >= locked - 3.0 * result.standard_error


def test_single_period_and_degenerate_store_have_no_extrinsic() -> None:
    # One period (no cross-period optionality) and a zero-capacity store both collapse
    # to the intrinsic value with extrinsic exactly 0.
    factor = StorageFactorModel(volatility=0.5, dt=1 / 12, path_count=200)
    single = storage_value(_model(), _curve([5.0]), factor, seed=1, inventory_step=1.0)
    assert single.extrinsic == 0.0
    assert single.total == single.intrinsic
    degenerate = _model(max_inventory=0.0)
    flat = storage_value(degenerate, _curve([5.0, 6.0]), factor, seed=1)
    assert flat.extrinsic == 0.0
    assert flat.total == flat.intrinsic == 0.0


# --- Req 11.2: determinism under seed ------------------------------------------------


def test_storage_value_deterministic_under_seed() -> None:
    a = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=2024, inventory_step=1.0
    )
    b = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=2024, inventory_step=1.0
    )
    assert a == b  # bit-identical result object, not just approx


def test_storage_value_differs_across_seeds() -> None:
    a = storage_value(_fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=1, inventory_step=1.0)
    b = storage_value(_fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=2, inventory_step=1.0)
    assert a.total != b.total


# --- Req 11.4: input immutability -----------------------------------------------------


def test_storage_intrinsic_does_not_mutate_inputs() -> None:
    assert_input_unchanged(storage_intrinsic, _model(), _curve([1.0, 1.0, 5.0]), inventory_step=1.0)


def test_storage_value_does_not_mutate_inputs() -> None:
    factor = StorageFactorModel(volatility=0.5, dt=1 / 12, path_count=200)
    assert_input_unchanged(
        storage_value,
        _fast_store(),
        _curve([10.0, 12.0, 11.0]),
        factor,
        seed=7,
        inventory_step=1.0,
    )


# --- grid_steps (default _DEFAULT_GRID_STEPS = 50) ------------------------------------


def test_grid_steps_default_matches_explicit_50() -> None:
    model = _model()  # min=0, max=2
    curve = _curve([1.0, 1.0, 5.0])
    default_result = storage_intrinsic(model, curve)
    explicit_result = storage_intrinsic(model, curve, grid_steps=50)
    assert default_result == explicit_result


def test_grid_steps_override_changes_grid_resolution() -> None:
    model = _model(initial_inventory=0.6, terminal_inventory=0.6)
    curve = _curve([1.0, 1.0, 5.0])
    # default grid_steps=50 over [0, 2] -> step 0.04; 0.6 lies exactly on the grid.
    result = storage_intrinsic(model, curve)
    assert result.inventory[0] == pytest.approx(0.6)
    # grid_steps=3 over [0, 2] -> step ~0.667; 0.6 no longer lands on the grid.
    with pytest.raises(ValidationError, match="grid"):
        storage_intrinsic(model, curve, grid_steps=3)


def test_grid_steps_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError, match="grid_steps"):
        storage_intrinsic(_model(), _curve([1.0, 5.0]), grid_steps=0)


# --- lsm_basis_degree (default _LSM_BASIS_DEGREE = 2) ---------------------------------


def test_lsm_basis_degree_default_matches_explicit_2() -> None:
    default_result = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=1, inventory_step=1.0
    )
    explicit_result = storage_value(
        _fast_store(),
        _curve(_FLAT_CURVE),
        _FLAT_FACTOR,
        seed=1,
        inventory_step=1.0,
        lsm_basis_degree=2,
    )
    assert default_result == explicit_result


def test_lsm_basis_degree_override_changes_result() -> None:
    default_result = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=1, inventory_step=1.0
    )
    degree_one_result = storage_value(
        _fast_store(),
        _curve(_FLAT_CURVE),
        _FLAT_FACTOR,
        seed=1,
        inventory_step=1.0,
        lsm_basis_degree=1,
    )
    assert degree_one_result.total != default_result.total


def test_lsm_basis_degree_must_be_at_least_one() -> None:
    factor = StorageFactorModel(volatility=0.5, dt=1 / 12, path_count=200)
    with pytest.raises(ValidationError, match="lsm_basis_degree"):
        storage_value(
            _fast_store(),
            _curve([5.0, 6.0]),
            factor,
            seed=1,
            inventory_step=1.0,
            lsm_basis_degree=0,
        )


# --- antithetic (default True) ---------------------------------------------------------


def test_antithetic_default_matches_explicit_true() -> None:
    default_result = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=1, inventory_step=1.0
    )
    explicit_result = storage_value(
        _fast_store(),
        _curve(_FLAT_CURVE),
        _FLAT_FACTOR,
        seed=1,
        inventory_step=1.0,
        antithetic=True,
    )
    assert default_result == explicit_result


def test_antithetic_override_changes_result() -> None:
    default_result = storage_value(
        _fast_store(), _curve(_FLAT_CURVE), _FLAT_FACTOR, seed=1, inventory_step=1.0
    )
    no_antithetic_result = storage_value(
        _fast_store(),
        _curve(_FLAT_CURVE),
        _FLAT_FACTOR,
        seed=1,
        inventory_step=1.0,
        antithetic=False,
    )
    assert no_antithetic_result.total != default_result.total


# --- bugfix regression: pair-aware standard error under antithetic variates -----------


def test_standard_error_uses_pair_mean_estimator_under_antithetic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Antithetic ``extrinsic_paths`` are interleaved ``(plus, minus)`` mirror pairs
    (record ``2k`` / ``2k + 1``, per ``rust/src/paths.rs``), not iid draws. Treating
    every draw as independent (the naive ``std(x, ddof=1) / sqrt(n)`` formula)
    overstates the standard error because within-pair draws are negatively
    correlated by construction; the correct estimator is that of the pair means,
    ``std(pair_means, ddof=1) / sqrt(n_pairs)``. Captures the raw (pre-averaged)
    extrinsic values via the module's own ``_standard_error`` seam so the assertion
    is exact, not a re-derivation from an already-reduced array.
    """
    import quantvolt.assets.storage as storage_module

    captured: dict[str, np.ndarray] = {}
    original = storage_module._standard_error

    def spy(values: np.ndarray, antithetic: bool) -> float:
        captured["values"] = np.array(values, copy=True)
        return original(values, antithetic)

    monkeypatch.setattr(storage_module, "_standard_error", spy)

    store = StorageModel(
        min_inventory=0.0,
        max_inventory=2.0,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda inv: 1.0,
        withdrawal_rate=lambda inv: 2.0,
    )
    factor = StorageFactorModel(volatility=0.8, dt=1.0 / 12.0, path_count=2000)
    result = storage_value(store, _curve(_FLAT_CURVE), factor, seed=123)

    values = captured["values"]
    pair_means = 0.5 * (values[0::2] + values[1::2])
    expected_se = float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
    naive_iid_se = float(np.std(values, ddof=1) / math.sqrt(values.size))

    assert result.standard_error == pytest.approx(expected_se, rel=1e-12)
    # The bug this pins: the naive iid formula overstates the SE here.
    assert naive_iid_se > result.standard_error


def test_standard_error_matches_naive_iid_when_antithetic_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quantvolt.assets.storage as storage_module

    captured: dict[str, np.ndarray] = {}
    original = storage_module._standard_error

    def spy(values: np.ndarray, antithetic: bool) -> float:
        captured["values"] = np.array(values, copy=True)
        return original(values, antithetic)

    monkeypatch.setattr(storage_module, "_standard_error", spy)
    result = storage_value(
        _fast_store(),
        _curve(_FLAT_CURVE),
        _FLAT_FACTOR,
        seed=1,
        inventory_step=1.0,
        antithetic=False,
    )

    values = captured["values"]
    expected_se = float(np.std(values, ddof=1) / math.sqrt(values.size))
    assert result.standard_error == pytest.approx(expected_se, rel=1e-12)
