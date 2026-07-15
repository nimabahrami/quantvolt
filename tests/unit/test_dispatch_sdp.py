"""Unit tests for stochastic dispatch valuation (Task 73; Req 21.1, 21.2, 21.5, 21.6).

Property 62 (stochastic <= perfect foresight) is asserted on the *same* scenario
set: every simulated path is valued with ``dispatch_deterministic`` and the mean
of those perfect-foresight optima must dominate the non-anticipative value. The
dominance is path-wise -- the schedule the stochastic policy executes on a path
is one feasible schedule for that path -- so it holds up to float noise, not
just statistically. For the tree the scenario set is the lattice itself: all
``(2^D)^H`` equally likely branch sequences are enumerated exactly.

Property 63 (dispatch-tolling reconciliation) removes every binding constraint
(``c_min = 0``, ramp = full capacity, zero start costs, zero durations) so the
optimal policy is myopic: run at ``c_max`` iff the spread is positive. The value
must then equal ``c_max`` times the Req-8 tolling strip built on matching
inputs. Mapping: risk-neutral drift keeps ``E*[P_t] = F_power`` (curve price);
per-tenor implied vols ``sigma * sqrt(t_sim_k / T_act365_k)`` equate the
simulation's per-period log-variance ``(k+1)*sigma^2*dt`` with the tolling
kernel's ``sigma_imp_k^2 * actual_365(ref, last_day_k)``; both legs share one
vol (the tolling module's single-surface convention); ``emissions_intensity=0``
zeroes the EUA leg; ``variable_om_cost = 0`` makes every period price through
exact Margrabe; discounting is flat 1.0 on both sides.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date

import numpy as np
import pytest

from quantvolt.assets.dispatch_deterministic import dispatch_deterministic
from quantvolt.assets.dispatch_sdp import (
    DispatchFactorModel,
    DispatchResult,
    FactorTransform,
    MonteCarloEvaluation,
    PeakKind,
    PhysicalFactorMapping,
    dispatch_value,
)
from quantvolt.assets.plant import MaxCapacityCurve, PlantModel, StartCost, StartState
from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES, CommodityConfig
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import PlantConfig
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.daycount import actual_365
from quantvolt.numerics.monte_carlo import build_covariance
from quantvolt.numerics.risk_adjustment import DriftKind
from quantvolt.pricing.tolling import price_tolling_agreement
from quantvolt.testing import assert_input_unchanged

# One trading-day step; small enough that the 10-30 MW plant sees mixed regimes.
DT = 1.0 / 50.0
TEMP = 15.0


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
        d_min=2,
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=1,
        warm_max_downtime=3,
    )
    params.update(overrides)
    return PlantModel(**params)  # type: ignore[arg-type]


def make_factor_model(
    *,
    forwards: Sequence[float] = (55.0, 42.0, 20.0),
    sigmas: Sequence[float] = (0.35, 0.30, 0.45),
    horizon: int = 5,
    dt: float = DT,
    peak_kinds: tuple[PeakKind, ...] | None = None,
    power_on_index: int = 0,
    power_off_index: int = 1,
    gas_index: int = 2,
) -> DispatchFactorModel:
    """A risk-neutral-drift factor model: power_on / power_off / gas by default."""
    d = len(forwards)
    corr = np.eye(d)
    corr[power_on_index, gas_index] = corr[gas_index, power_on_index] = 0.3
    if power_off_index != power_on_index:
        corr[power_off_index, gas_index] = corr[gas_index, power_off_index] = 0.3
    cov = build_covariance(list(sigmas), corr, dt)
    if peak_kinds is None:
        peak_kinds = tuple(
            PeakKind.ON_PEAK if t % 2 == 0 else PeakKind.OFF_PEAK for t in range(horizon)
        )
    return DispatchFactorModel(
        log_forward0=np.log(np.asarray(forwards, dtype=np.float64)),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=peak_kinds,
        temperatures=(TEMP,) * horizon,
        power_on_index=power_on_index,
        power_off_index=power_off_index,
        gas_index=gas_index,
    )


# --------------------------------------------------------------------------- #
# Property 62: stochastic value <= perfect foresight on the same scenario set. #
# --------------------------------------------------------------------------- #
def test_property_62_lsm_bounded_by_perfect_foresight_on_same_paths() -> None:
    plant = make_plant()
    fm = make_factor_model()
    seed, path_count = 11, 256
    result = dispatch_value(plant, fm, method="lsm", seed=seed, path_count=path_count)

    # The exact scenario set the LSM engine used (same seed => bit-identical paths).
    paths = fm.simulate(seed, path_count)
    horizon = fm.horizon
    foresight = []
    for p in range(paths.shape[0]):
        power = [float(np.exp(paths[p, t + 1, fm.active_power_index(t)])) for t in range(horizon)]
        gas = [float(np.exp(paths[p, t + 1, fm.gas_index])) for t in range(horizon)]
        foresight.append(dispatch_deterministic(plant, power, gas, [TEMP] * horizon).total_value)
    perfect = float(np.mean(foresight))
    assert result.value <= perfect + 1e-9


def test_property_62_tree_bounded_by_perfect_foresight_on_exact_lattice() -> None:
    # Near-ATM spread (42 - 2*20 = 2) with the unit already online: foresight has
    # real optionality (dodge negative-spread branches), so the bound is strict.
    plant = make_plant()
    fm = make_factor_model(
        forwards=(42.0, 20.0),
        sigmas=(0.35, 0.45),
        horizon=3,
        dt=1.0 / 12.0,
        peak_kinds=(PeakKind.ON_PEAK,) * 3,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
    )
    tree = dispatch_value(
        plant, fm, method="tree", seed=0, initial_online=True, initial_output=10.0
    )

    # Enumerate the lattice's entire (equally likely) scenario set: (2^2)^3 paths.
    chol = np.linalg.cholesky(fm.covariance)
    foresight = []
    for eps_seq in itertools.product(itertools.product((-1.0, 1.0), repeat=2), repeat=3):
        z = fm.log_forward0.copy()
        power, gas = [], []
        for eps in eps_seq:
            z = z + fm.drift + chol @ np.asarray(eps)
            power.append(float(np.exp(z[0])))
            gas.append(float(np.exp(z[1])))
        foresight.append(
            dispatch_deterministic(
                plant, power, gas, [TEMP] * 3, initial_online=True, initial_output=10.0
            ).total_value
        )
    perfect = float(np.mean(foresight))
    assert tree.value <= perfect + 1e-9
    assert tree.value < perfect  # optionality makes the dominance strict here


# --------------------------------------------------------------------------- #
# Property 63: no binding constraints -> reconciles with the tolling strip.    #
# --------------------------------------------------------------------------- #
def test_property_63_reconciles_with_tolling_strip() -> None:
    c_max, heat_rate, sigma, rho, dt = 50.0, 2.0, 0.35, 0.4, 1.0 / 12.0
    f_power, f_gas = 60.0, 25.0
    ref = date(2026, 12, 15)
    periods = (DeliveryPeriod(2027, 1), DeliveryPeriod(2027, 2), DeliveryPeriod(2027, 3))
    horizon = len(periods)

    # No binding constraints: c_min = 0, ramp = c_max, zero start costs / durations.
    plant = make_plant(
        heat_rate=const_heat_rate(heat_rate),
        c_min=0.0,
        c_max=const_c_max(c_max),
        start_costs=start_costs(hot=0.0, warm=0.0, cold=0.0),
        ramp_rate=c_max,
        d_min=0,
        d_shutdown=0,
        d_startup=0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )
    cov = build_covariance([sigma, sigma], np.array([[1.0, rho], [rho, 1.0]]), dt)
    fm = DispatchFactorModel(
        log_forward0=np.log([f_power, f_gas]),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * horizon,
        temperatures=(TEMP,) * horizon,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
    )
    # Online at 0 MW entering the horizon so period 0 already has the full choice
    # {0, c_max} (a start would otherwise come online *at* c_min = 0).
    dispatch = dispatch_value(
        plant, fm, method="lsm", seed=42, path_count=8192, initial_online=True, initial_output=0.0
    )

    # The Req-8 tolling strip on matching inputs (see module docstring mapping).
    def curve(commodity: CommodityConfig, price: float) -> ForwardCurve:
        return ForwardCurve(
            commodity=commodity,
            market_date=ref,
            nodes=tuple(CurveNode(p, price, "observed") for p in periods),
        )

    surface = VolatilitySurface(
        commodity=BUILT_IN_COMMODITIES["EEX_PHELIX_DE"],
        tenors=tuple(
            VolatilityTenor(p, sigma * math.sqrt((k + 1) * dt / actual_365(ref, p.last_day)))
            for k, p in enumerate(periods)
        ),
    )
    tolling = price_tolling_agreement(
        PlantConfig(
            heat_rate=heat_rate, variable_om_cost=0.0, emissions_intensity=0.0, fuel_type="gas"
        ),
        curve(BUILT_IN_COMMODITIES["EEX_PHELIX_DE"], f_power),
        curve(BUILT_IN_COMMODITIES["TTF"], f_gas),
        curve(BUILT_IN_COMMODITIES["EUA"], 70.0),
        surface,
        np.array([[1.0, rho, 0.0], [rho, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        DeliverySchedule(periods=periods),
        DiscountCurve(
            reference_date=ref,
            tenors=tuple(p.last_day for p in periods),
            factors=(1.0,) * horizon,
        ),
    )
    strip_value = c_max * tolling.npv  # tolling is unit-capacity (1 MWh/period)
    assert dispatch.value == pytest.approx(strip_value, rel=0.02)


# --------------------------------------------------------------------------- #
# Method agreement and determinism.                                            #
# --------------------------------------------------------------------------- #
def test_tree_and_lsm_agree_on_small_case() -> None:
    plant = make_plant()
    fm = make_factor_model()
    lsm = dispatch_value(plant, fm, method="lsm", seed=7, path_count=2048)
    tree = dispatch_value(plant, fm, method="tree", seed=7)
    assert lsm.value == pytest.approx(tree.value, rel=0.05)


def test_deterministic_under_seed() -> None:
    plant = make_plant()
    fm = make_factor_model()
    first = dispatch_value(plant, fm, method="lsm", seed=7, path_count=512)
    second = dispatch_value(plant, fm, method="lsm", seed=7, path_count=512)
    assert first == second
    assert isinstance(first, DispatchResult)
    assert dispatch_value(plant, fm, method="tree", seed=0) == dispatch_value(
        plant, fm, method="tree", seed=1
    )  # the lattice is seed-independent by construction
    different = dispatch_value(plant, fm, method="lsm", seed=8, path_count=512)
    assert different.value != first.value


# --------------------------------------------------------------------------- #
# Critical exercise surfaces (eq. B.5).                                        #
# --------------------------------------------------------------------------- #
def test_surfaces_populated_and_start_dominates_shutdown() -> None:
    plant = make_plant()
    fm = make_factor_model()
    for result in (
        dispatch_value(plant, fm, method="lsm", seed=11, path_count=1024),
        dispatch_value(plant, fm, method="tree", seed=0),
    ):
        horizon = fm.horizon
        for surface in (
            result.start_surface,
            result.shutdown_surface,
            result.rampup_surface,
            result.rampdown_surface,
        ):
            assert len(surface) == horizon
        # Hysteresis: the spread that justifies paying a start cost is never below
        # the spread at which a running unit would rather keep running.
        for start, shutdown in zip(result.start_surface, result.shutdown_surface, strict=True):
            if math.isfinite(start) and math.isfinite(shutdown):
                assert start >= shutdown


def test_terminal_period_surfaces_match_hand_values() -> None:
    # In the last period the continuation is 0, so the boundaries are exact:
    # start iff c_min*spread - SC_cold > 0 (threshold SC/c_min = 200/10 = 20);
    # ramp up/down iff the extra 10 MW earn a positive spread (threshold 0).
    plant = make_plant()
    fm = make_factor_model()
    result = dispatch_value(plant, fm, method="lsm", seed=11, path_count=1024)
    assert result.start_surface[-1] == pytest.approx(200.0 / 10.0, abs=1e-6)
    assert result.rampup_surface[-1] == pytest.approx(0.0, abs=1e-6)
    assert result.rampdown_surface[-1] == pytest.approx(0.0, abs=1e-6)


def test_lsm_reports_independent_evaluation_diagnostics() -> None:
    result = dispatch_value(
        make_plant(),
        make_factor_model(),
        method="lsm",
        seed=11,
        path_count=256,
        evaluation=MonteCarloEvaluation(seed=29, path_count=300, confidence_level=0.9),
    )
    assert result.diagnostics is not None
    assert result.diagnostics.training_path_count == 256
    assert result.diagnostics.evaluation_path_count == 300
    assert result.diagnostics.evaluation_standard_error > 0.0
    low, high = result.diagnostics.confidence_interval
    assert low < result.value < high
    assert math.isfinite(result.diagnostics.max_regression_condition)


def test_time_varying_dynamics_and_physical_factor_mappings() -> None:
    base = make_factor_model(horizon=3)
    z0 = np.concatenate([base.log_forward0, np.array([15.0, 0.0])])
    drift = np.zeros((3, 5))
    covariance = np.zeros((3, 5, 5))
    covariance[:, :3, :3] = base.covariance
    mapped = DispatchFactorModel(
        log_forward0=z0,
        drift=drift,
        covariance=covariance,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=base.peak_kinds,
        temperatures=base.temperatures,
        temperature_factor=PhysicalFactorMapping(3, FactorTransform.IDENTITY),
        availability_factor=PhysicalFactorMapping(4, FactorTransform.LOGISTIC),
    )
    result = dispatch_value(
        mapped_plant := make_plant(), factor_model=mapped, seed=7, path_count=128
    )
    full = dispatch_value(mapped_plant, base, seed=7, path_count=128)
    assert result.value < full.value
    assert result.diagnostics is not None


def test_ramp_surfaces_nan_when_single_output_level() -> None:
    # c_min == c_max: the grid has one level, so ramp decisions never arise.
    plant = make_plant(c_max=const_c_max(10.0))
    fm = make_factor_model(horizon=3)
    result = dispatch_value(plant, fm, method="lsm", seed=5, path_count=256)
    assert all(math.isnan(x) for x in result.rampup_surface)
    assert all(math.isnan(x) for x in result.rampdown_surface)
    assert all(math.isfinite(x) for x in result.start_surface)


# --------------------------------------------------------------------------- #
# Markov on-/off-peak split (Req 21.6, eq. B.4).                               #
# --------------------------------------------------------------------------- #
def test_peak_kind_selects_the_active_power_coordinate() -> None:
    plant = make_plant()
    on = make_factor_model(
        forwards=(60.0, 30.0, 20.0), horizon=4, peak_kinds=(PeakKind.ON_PEAK,) * 4
    )
    off = make_factor_model(
        forwards=(60.0, 30.0, 20.0), horizon=4, peak_kinds=(PeakKind.OFF_PEAK,) * 4
    )
    value_on = dispatch_value(plant, on, method="lsm", seed=3, path_count=512).value
    value_off = dispatch_value(plant, off, method="lsm", seed=3, path_count=512).value
    # On-peak spot 60 vs off-peak 30 (spread +20 vs -10 at HR=2, G=20).
    assert value_on > value_off
    assert value_off >= 0.0  # staying offline is always feasible


# --------------------------------------------------------------------------- #
# Forced-outage seam (eq. B.1 M_ti).                                           #
# --------------------------------------------------------------------------- #
def test_availability_derates_capacity_and_reduces_value() -> None:
    plant = make_plant()
    fm = make_factor_model()
    full = dispatch_value(plant, fm, method="lsm", seed=11, path_count=512)
    derated = dispatch_value(
        plant, fm, method="lsm", seed=11, path_count=512, availability=[0.6] * fm.horizon
    )
    # M = 0.6 caps output at 18 MW (grid level 10 instead of 30) on an ITM plant.
    assert derated.value < full.value


def test_availability_below_c_min_forces_unit_offline() -> None:
    plant = make_plant()
    fm = make_factor_model()
    result = dispatch_value(
        plant, fm, method="lsm", seed=11, path_count=128, availability=[0.2] * fm.horizon
    )
    # M*c_max = 6 < c_min = 10: producing is infeasible (eq. B.1 constraint 5), so
    # the only policy is to stay offline, worth exactly zero.
    assert result.value == 0.0


def test_outage_derate_forces_min_run_locked_unit_offline_rather_than_raising() -> None:
    # Bugfix regression (dispatch_sdp -inf lstsq targets, "SEVERE"): online below
    # min-run (uptime 1 < d_min 5) with a uniform outage derate (0.2 * 30 = 6 MW)
    # below c_min (10) leaves no *ordinary* state-machine move -- the unit cannot
    # produce (every level exceeds the derated ceiling) and cannot yet legally shut
    # down (min-run timer not reached). This used to raise "no feasible schedule".
    # The module's own eq. B.1 constraint 5 ("if the derated ceiling falls below
    # c_min the unit is forced offline") is documented unconditionally, so `_moves`
    # now supplies a forced-shutdown fallback whenever no ordinary move survives an
    # online state -- overriding the min-run lock only in this physically-forced
    # case. Every period here derates below c_min, so the unit is forced off at t=0
    # and, unable to restart at the same derated ceiling, stays off throughout: the
    # schedule is feasible and worth exactly 0 (no cash, no start cost) rather than
    # infeasible.
    plant = make_plant(d_min=5)
    fm = make_factor_model(horizon=3)
    result = dispatch_value(
        plant,
        fm,
        method="lsm",
        seed=1,
        path_count=64,
        availability=[0.2] * 3,
        initial_online=True,
        initial_output=10.0,
        initial_uptime=1,
    )
    assert result.value == 0.0


# --------------------------------------------------------------------------- #
# Input immutability (Req 11.4).                                               #
# --------------------------------------------------------------------------- #
def test_inputs_not_mutated() -> None:
    plant = make_plant()
    cov = build_covariance(
        [0.35, 0.30, 0.45],
        np.array([[1.0, 0.0, 0.3], [0.0, 1.0, 0.3], [0.3, 0.3, 1.0]]),
        DT,
    )
    z0 = np.log(np.array([55.0, 42.0, 20.0]))
    drift = -0.5 * np.diag(cov)
    peaks = [PeakKind.ON_PEAK, PeakKind.OFF_PEAK, PeakKind.ON_PEAK]
    temps = [TEMP, TEMP, TEMP]
    availability = [0.95, 0.9, 1.0]
    discounts = [1.0, 0.99, 0.98]

    def run(
        z0_in: np.ndarray,
        drift_in: np.ndarray,
        cov_in: np.ndarray,
        peaks_in: list[PeakKind],
        temps_in: list[float],
        availability_in: list[float],
        discounts_in: list[float],
    ) -> DispatchResult:
        model = DispatchFactorModel(
            log_forward0=z0_in,
            drift=drift_in,
            covariance=cov_in,
            drift_kind=DriftKind.RISK_NEUTRAL,
            peak_kinds=tuple(peaks_in),
            temperatures=tuple(temps_in),
        )
        return dispatch_value(
            plant,
            model,
            method="lsm",
            seed=3,
            path_count=64,
            availability=availability_in,
            discount_factors=discounts_in,
        )

    result = assert_input_unchanged(run, z0, drift, cov, peaks, temps, availability, discounts)
    assert isinstance(result, DispatchResult)


# --------------------------------------------------------------------------- #
# Validation error paths.                                                      #
# --------------------------------------------------------------------------- #
def test_unknown_method_rejected() -> None:
    with pytest.raises(ValidationError, match="method must be one of"):
        dispatch_value(make_plant(), make_factor_model(), method="pde", seed=1)


def test_physical_drift_rejected_for_valuation() -> None:
    fm = make_factor_model()
    physical = DispatchFactorModel(
        log_forward0=fm.log_forward0,
        drift=fm.drift,
        covariance=fm.covariance,
        drift_kind=DriftKind.PHYSICAL,
        peak_kinds=fm.peak_kinds,
        temperatures=fm.temperatures,
    )
    with pytest.raises(ValidationError, match="drift must be tagged"):
        dispatch_value(make_plant(), physical, method="lsm", seed=1)


def test_negative_seed_rejected() -> None:
    with pytest.raises(ValidationError, match="seed"):
        dispatch_value(make_plant(), make_factor_model(), method="lsm", seed=-1)


def test_non_positive_path_count_rejected() -> None:
    with pytest.raises(ValidationError, match="path_count"):
        dispatch_value(make_plant(), make_factor_model(), method="lsm", seed=1, path_count=0)


def test_mis_sized_discount_factors_rejected() -> None:
    with pytest.raises(ValidationError, match="discount_factors must have length"):
        dispatch_value(
            make_plant(), make_factor_model(), method="lsm", seed=1, discount_factors=[1.0]
        )


def test_non_positive_discount_factor_rejected() -> None:
    fm = make_factor_model()
    with pytest.raises(ValidationError, match="discount_factors"):
        dispatch_value(make_plant(), fm, method="lsm", seed=1, discount_factors=[0.0] * fm.horizon)


def test_mis_sized_availability_rejected() -> None:
    with pytest.raises(ValidationError, match="availability must have length"):
        dispatch_value(make_plant(), make_factor_model(), method="lsm", seed=1, availability=[1.0])


def test_out_of_range_availability_rejected() -> None:
    fm = make_factor_model()
    with pytest.raises(ValidationError, match="availability"):
        dispatch_value(make_plant(), fm, method="lsm", seed=1, availability=[0.0] * fm.horizon)


def test_capacity_below_c_min_rejected_at_dispatch() -> None:
    plant = make_plant(c_max=const_c_max(5.0))  # c_max < c_min (10)
    with pytest.raises(ValidationError, match="c_max"):
        dispatch_value(plant, make_factor_model(), method="lsm", seed=1)


def test_tree_rejects_singular_covariance() -> None:
    cov = build_covariance([0.35, 0.0, 0.45], np.eye(3), DT)  # expired middle tenor
    fm = DispatchFactorModel(
        log_forward0=np.log([55.0, 42.0, 20.0]),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * 3,
        temperatures=(TEMP,) * 3,
    )
    with pytest.raises(ValidationError, match="positive-definite"):
        dispatch_value(make_plant(), fm, method="tree", seed=1)


# --------------------------------------------------------------------------- #
# antithetic / regression_basis_degree keyword params.                        #
# --------------------------------------------------------------------------- #
def test_antithetic_default_matches_explicit_true() -> None:
    plant = make_plant()
    fm = make_factor_model()
    default = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256)
    explicit = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256, antithetic=True)
    assert default == explicit


def test_antithetic_override_changes_result() -> None:
    plant = make_plant()
    fm = make_factor_model()
    default = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256)
    no_antithetic = dispatch_value(
        plant, fm, method="lsm", seed=11, path_count=256, antithetic=False
    )
    assert no_antithetic.value != default.value


# --------------------------------------------------------------------------- #
# Bugfix regression: pair-aware standard error under antithetic variates.     #
# --------------------------------------------------------------------------- #
def test_evaluation_standard_error_uses_pair_mean_estimator_under_antithetic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Antithetic evaluation draws are interleaved ``(plus, minus)`` mirror pairs
    (record ``2k`` / ``2k + 1``, per ``rust/src/paths.rs``), not iid draws. Treating
    every draw as independent (the naive ``std(x, ddof=1) / sqrt(n)`` formula)
    overstates the standard error because within-pair draws are negatively
    correlated by construction; the correct estimator is that of the pair means,
    ``std(pair_means, ddof=1) / sqrt(n_pairs)``. Captures the raw (pre-averaged)
    evaluation values via the module's own ``_standard_error`` seam so the
    assertion is exact, not a re-derivation from an already-reduced array.
    """
    import quantvolt.assets.dispatch_sdp as dispatch_sdp_module

    captured: dict[str, np.ndarray] = {}
    original = dispatch_sdp_module._standard_error

    def spy(values: np.ndarray, antithetic: bool) -> float:
        captured["values"] = np.array(values, copy=True)
        return original(values, antithetic)

    monkeypatch.setattr(dispatch_sdp_module, "_standard_error", spy)

    plant = make_plant(variable_om_cost=2.0, ramp_rate=50.0, c_min=50.0, c_max=const_c_max(100.0))
    fm = make_factor_model(
        forwards=(22.0, 10.0),
        sigmas=(0.3, 0.2),
        horizon=4,
        peak_kinds=(PeakKind.ON_PEAK,) * 4,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
    )
    result = dispatch_value(plant, fm, method="lsm", seed=7, path_count=512)

    values = captured["values"]
    pair_means = 0.5 * (values[0::2] + values[1::2])
    expected_se = float(np.std(pair_means, ddof=1) / math.sqrt(pair_means.size))
    naive_iid_se = float(np.std(values, ddof=1) / math.sqrt(values.size))

    assert result.diagnostics is not None
    assert result.diagnostics.evaluation_standard_error == pytest.approx(expected_se, rel=1e-12)
    # The bug this pins: the naive iid formula materially overstates the SE here.
    assert naive_iid_se > result.diagnostics.evaluation_standard_error * 1.05


def test_evaluation_standard_error_matches_naive_iid_when_antithetic_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import quantvolt.assets.dispatch_sdp as dispatch_sdp_module

    captured: dict[str, np.ndarray] = {}
    original = dispatch_sdp_module._standard_error

    def spy(values: np.ndarray, antithetic: bool) -> float:
        captured["values"] = np.array(values, copy=True)
        return original(values, antithetic)

    monkeypatch.setattr(dispatch_sdp_module, "_standard_error", spy)
    plant = make_plant()
    fm = make_factor_model()
    result = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256, antithetic=False)

    values = captured["values"]
    expected_se = float(np.std(values, ddof=1) / math.sqrt(values.size))
    assert result.diagnostics is not None
    assert result.diagnostics.evaluation_standard_error == pytest.approx(expected_se, rel=1e-12)


# --------------------------------------------------------------------------- #
# Bugfix regressions: -inf LSM continuation targets (SEVERE) and LOGISTIC      #
# underflow aborting the valuation.                                           #
# --------------------------------------------------------------------------- #
def test_min_run_locked_state_with_stochastic_derate_below_c_min_completes() -> None:
    """SEVERE bugfix regression (dispatch_sdp -inf lstsq targets).

    A min-run-locked ONLINE initial state (``d_min=2``, ``initial_uptime=1``)
    combined with a LOGISTIC availability factor straddling ``c_min / c_max`` (sigma
    5 per step) puts roughly half the training paths' derated capacity below
    ``c_min`` while the unit cannot yet legally shut down. Before the fix this fed
    ``-inf`` continuation targets into the LSM regression's ``lstsq`` for *every*
    state sharing that period's basis (non-finite coefficients corrupting the whole
    valuation), and ``_evaluate_lsm_policy`` then raised "no feasible forward
    action". The fix (i) masks ``-inf`` realised values out of each state's own
    regression fit and out of its own continuation (``_dispatch_lsm``), and (ii)
    gives ``_moves`` a forced-shutdown fallback when a min-run-locked online state
    has no other feasible action left at all (eq. B.1 constraint 5's "the unit is
    forced offline" applied even inside the min-run window when there is no
    alternative).
    """
    plant = PlantModel(
        heat_rate=const_heat_rate(2.0),
        c_min=50.0,
        c_max=const_c_max(100.0),
        variable_om_cost=0.0,
        start_costs=start_costs(hot=0.0, warm=0.0, cold=0.0),
        ramp_rate=50.0,
        d_min=2,  # min-run lock: shutdown blocked while uptime < 2
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )
    fm = DispatchFactorModel(
        log_forward0=np.array([math.log(100.0), math.log(10.0), 0.0]),
        drift=np.zeros(3),
        covariance=np.diag([0.01, 0.01, 25.0]),  # availability raw factor sigma=5/step
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * 3,
        temperatures=(10.0,) * 3,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
        availability_factor=PhysicalFactorMapping(index=2, transform=FactorTransform.LOGISTIC),
    )
    result = dispatch_value(
        plant,
        fm,
        seed=0,
        path_count=64,
        initial_online=True,
        initial_output=50.0,
        initial_uptime=1,
    )
    assert math.isfinite(result.value)
    assert result.diagnostics is not None
    assert math.isfinite(result.diagnostics.evaluation_standard_error)
    assert not math.isnan(result.diagnostics.training_value)  # never NaN; -inf is a legitimate
    # diagnostic here (an "unlucky" training path can still be a genuine forced-outage
    # dead end at t=0's representative-capacity granularity) -- only the *reported*
    # value (evaluated per-path) must be finite.


def test_logistic_availability_underflow_does_not_abort_valuation() -> None:
    """Bugfix regression: LOGISTIC underflows to exactly ``0.0`` for ``raw < ~-709.8``
    (``exp(-raw)`` overflows to ``inf``). The ``(0, 1]`` availability guard used to
    abort the *entire* valuation whenever any single simulated path underflowed;
    ``_logistic`` now clamps to ``np.finfo(float).tiny`` instead of exact zero.
    """
    plant = PlantModel(
        heat_rate=const_heat_rate(2.0),
        c_min=0.0,
        c_max=const_c_max(100.0),
        variable_om_cost=0.0,
        start_costs=start_costs(hot=0.0, warm=0.0, cold=0.0),
        ramp_rate=100.0,
        d_min=0,
        d_shutdown=0,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )
    fm = DispatchFactorModel(
        # Availability raw coordinate starts at -706 (finite, passes validation);
        # sigma=4/step: some paths dip below ~-709.8 where the plain logistic ratio
        # would underflow to exactly 0.0.
        log_forward0=np.array([math.log(100.0), math.log(10.0), -706.0]),
        drift=np.zeros(3),
        covariance=np.diag([0.01, 0.01, 16.0]),
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * 2,
        temperatures=(10.0,) * 2,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
        availability_factor=PhysicalFactorMapping(index=2, transform=FactorTransform.LOGISTIC),
    )
    paths = fm.simulate(0, 64, antithetic=True)
    raw = paths[:, 1, 2]
    with np.errstate(over="ignore"):
        assert bool(np.any(1.0 / (1.0 + np.exp(-raw)) == 0.0))  # confirm the regime is reached

    result = dispatch_value(plant, fm, seed=0, path_count=64)
    assert math.isfinite(result.value)


def test_regression_basis_degree_default_matches_explicit_2() -> None:
    plant = make_plant()
    fm = make_factor_model()
    default = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256)
    explicit = dispatch_value(
        plant, fm, method="lsm", seed=11, path_count=256, regression_basis_degree=2
    )
    assert default == explicit


def test_regression_basis_degree_override_changes_result() -> None:
    plant = make_plant()
    fm = make_factor_model()
    default = dispatch_value(plant, fm, method="lsm", seed=11, path_count=256)
    degree_one = dispatch_value(
        plant, fm, method="lsm", seed=11, path_count=256, regression_basis_degree=1
    )
    assert degree_one.value != default.value


def test_regression_basis_degree_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError, match="regression_basis_degree"):
        dispatch_value(
            make_plant(), make_factor_model(), method="lsm", seed=1, regression_basis_degree=0
        )


def test_tree_ignores_antithetic_and_regression_basis_degree() -> None:
    plant = make_plant()
    fm = make_factor_model()
    default = dispatch_value(plant, fm, method="tree", seed=0)
    other = dispatch_value(
        plant, fm, method="tree", seed=0, antithetic=False, regression_basis_degree=5
    )
    assert default == other


def test_factor_model_shape_and_index_validation() -> None:
    cov = build_covariance([0.3, 0.4], np.eye(2), DT)
    good = dict(
        log_forward0=np.log([55.0, 20.0]),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * 2,
        temperatures=(TEMP,) * 2,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
    )
    DispatchFactorModel(**good)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="log_forward0"):
        DispatchFactorModel(**{**good, "log_forward0": np.log([55.0])})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="drift must have shape"):
        DispatchFactorModel(**{**good, "drift": np.zeros(3)})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="covariance must have shape"):
        DispatchFactorModel(**{**good, "covariance": np.eye(3)})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="gas_index"):
        DispatchFactorModel(**{**good, "gas_index": 5})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="peak_kinds must be non-empty"):
        DispatchFactorModel(**{**good, "peak_kinds": (), "temperatures": ()})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="same length"):
        DispatchFactorModel(**{**good, "temperatures": (TEMP,)})  # type: ignore[arg-type]
