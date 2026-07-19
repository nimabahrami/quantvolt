"""Physical-asset correctness properties (design Properties 62-66; Task 77).

Covers the perfect-foresight dominance bound on stochastic dispatch (Property 62), the
dispatch/tolling reconciliation (Property 63), storage extrinsic non-negativity and bounds
(Property 64), storage vs the replicable calendar-spread value (Property 65), and
long-dated projected-spot governance (Property 66).

The dispatch and storage properties are simulation-heavy (LSM / SDP over a state machine),
so they use reduced example counts and small workloads, as noted at each test. Property 63
is a single deterministic example (the reconciliation needs an 8k-path LSM plus a full
tolling strip, per the Task-77 brief). Property 66 is a cheap governance property and runs
the full profile.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from datetime import date

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from quantvolt.assets.dispatch_deterministic import dispatch_deterministic
from quantvolt.assets.dispatch_sdp import DispatchFactorModel, PeakKind, dispatch_value
from quantvolt.assets.long_dated import (
    CorporatePremium,
    ValuationSource,
    furthest_forward_lower_bound,
    valuation_benchmark,
    var_applicability_guard,
)
from quantvolt.assets.plant import MaxCapacityCurve, PlantModel, StartCost, StartState
from quantvolt.assets.storage import (
    StorageFactorModel,
    StorageModel,
    storage_intrinsic,
    storage_value,
)
from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES, CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import FuturesContract, PlantConfig
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.models.vol_surface import VolatilitySurface, VolatilityTenor
from quantvolt.numerics.daycount import actual_365
from quantvolt.numerics.monte_carlo import build_covariance
from quantvolt.numerics.risk_adjustment import DriftKind, PriceOfRiskKind
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.pricing.spreads import calendar_spread
from quantvolt.pricing.tolling import price_tolling_agreement

_TEMP = 15.0
_DT = 1.0 / 50.0


def _const_heat_rate(rate: float) -> Callable[[float, float], float]:
    return lambda _q, _temp: rate


def _const_c_max(capacity: float) -> MaxCapacityCurve:
    return lambda _temp: capacity


def _start_costs(cost: float = 0.0) -> Mapping[StartState, StartCost]:
    return {state: StartCost(fixed=cost, fuel=0.0, power=0.0) for state in StartState}


def _plant(**overrides: object) -> PlantModel:
    params: dict[str, object] = dict(
        heat_rate=_const_heat_rate(2.0),
        c_min=10.0,
        c_max=_const_c_max(30.0),
        variable_om_cost=0.0,
        start_costs=_start_costs(50.0),
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


# ---------------------------------------------------------------------------------------
# Property 62: Stochastic Value Bounded by Perfect Foresight.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 62: Stochastic Value Bounded by Perfect
# Foresight
# On the *same* simulated scenario set, valuing each path with perfect foresight
# (dispatch_deterministic) and averaging must dominate the non-anticipating LSM value.
# Reduced examples with a small path count / horizon (each example runs one LSM solve plus
# one deterministic DP per path).
@given(
    seed=st.integers(min_value=0, max_value=2**16),
    power_on=st.floats(min_value=45.0, max_value=75.0),
    gas=st.floats(min_value=18.0, max_value=28.0),
    sigma=st.floats(min_value=0.20, max_value=0.45),
)
@settings(max_examples=6, deadline=None)
def test_property_62_stochastic_value_bounded_by_perfect_foresight(
    seed: int, power_on: float, gas: float, sigma: float
) -> None:
    plant = _plant()
    horizon, path_count = 3, 128
    forwards = np.array([power_on, power_on * 0.8, gas], dtype=np.float64)
    corr = np.eye(3)
    corr[0, 2] = corr[2, 0] = corr[1, 2] = corr[2, 1] = 0.3
    cov = build_covariance([sigma, sigma, sigma * 1.2], corr, _DT)
    factor_model = DispatchFactorModel(
        log_forward0=np.log(forwards),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=tuple(
            PeakKind.ON_PEAK if t % 2 == 0 else PeakKind.OFF_PEAK for t in range(horizon)
        ),
        temperatures=(_TEMP,) * horizon,
        power_on_index=0,
        power_off_index=1,
        gas_index=2,
    )
    result = dispatch_value(plant, factor_model, method="lsm", seed=seed, path_count=path_count)

    # The reported value is the fitted policy rolled forward on an independent sample.
    # With default controls that sample uses seed + 1 and the same path count.
    paths = factor_model.simulate(seed + 1, path_count)
    foresight = []
    for p in range(paths.shape[0]):
        power = [
            float(np.exp(paths[p, t + 1, factor_model.active_power_index(t)]))
            for t in range(horizon)
        ]
        fuel = [float(np.exp(paths[p, t + 1, factor_model.gas_index])) for t in range(horizon)]
        foresight.append(dispatch_deterministic(plant, power, fuel, [_TEMP] * horizon).total_value)
    perfect = float(np.mean(foresight))
    assert result.value <= perfect + 1e-9


# ---------------------------------------------------------------------------------------
# Property 63: Dispatch-Tolling Reconciliation.
# ---------------------------------------------------------------------------------------


# Feature: power-energy-quant-analysis, Property 63: Dispatch-Tolling Reconciliation
# Single deterministic example (not hypothesis-driven): the reconciliation needs an
# 8192-path LSM plus a full Req-8 tolling strip, which is far too expensive to repeat over
# 100 examples. Removing every binding constraint (c_min=0, ramp=c_max, zero start
# costs/durations) makes the optimal policy myopic — run at c_max iff the spark spread is
# positive — so the plant value must equal c_max times the matching unit-capacity tolling
# strip (per-tenor implied vols map the simulation's log-variance to the tolling kernel's).
def test_property_63_reconciles_with_tolling_strip() -> None:
    c_max, heat_rate, sigma, rho, dt = 50.0, 2.0, 0.35, 0.4, 1.0 / 12.0
    f_power, f_gas = 60.0, 25.0
    ref = date(2026, 12, 15)
    periods = (DeliveryPeriod(2027, 1), DeliveryPeriod(2027, 2), DeliveryPeriod(2027, 3))
    horizon = len(periods)

    plant = _plant(
        heat_rate=_const_heat_rate(heat_rate),
        c_min=0.0,
        c_max=_const_c_max(c_max),
        start_costs=_start_costs(0.0),
        ramp_rate=c_max,
        d_min=0,
        d_shutdown=0,
        d_startup=0,
        hot_max_downtime=0,
        warm_max_downtime=0,
    )
    cov = build_covariance([sigma, sigma], np.array([[1.0, rho], [rho, 1.0]]), dt)
    factor_model = DispatchFactorModel(
        log_forward0=np.log([f_power, f_gas]),
        drift=-0.5 * np.diag(cov),
        covariance=cov,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=(PeakKind.ON_PEAK,) * horizon,
        temperatures=(_TEMP,) * horizon,
        power_on_index=0,
        power_off_index=0,
        gas_index=1,
    )
    dispatch = dispatch_value(
        plant,
        factor_model,
        method="lsm",
        seed=42,
        path_count=8192,
        initial_online=True,
        initial_output=0.0,
    )

    def curve(commodity: CommodityConfig, price: float) -> ForwardCurve:
        return ForwardCurve(
            commodity=commodity,
            market_date=ref,
            nodes=tuple(CurveNode(period, price, "observed") for period in periods),
        )

    surface = VolatilitySurface(
        commodity=BUILT_IN_COMMODITIES["EEX_PHELIX_DE"],
        tenors=tuple(
            VolatilityTenor(
                period, sigma * math.sqrt((k + 1) * dt / actual_365(ref, period.last_day))
            )
            for k, period in enumerate(periods)
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
            reference_date=ref, tenors=tuple(p.last_day for p in periods), factors=(1.0,) * horizon
        ),
    )
    strip_value = c_max * tolling.npv  # tolling is unit-capacity (1 MWh/period)
    assert dispatch.value == pytest.approx(strip_value, rel=0.02)


# ---------------------------------------------------------------------------------------
# Property 64: Storage Extrinsic Non-Negativity and Bounds.
# ---------------------------------------------------------------------------------------


def _storage_curve(prices: Sequence[float]) -> ForwardCurve:
    gas = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE", "EUR/MWh"))
    nodes = tuple(
        CurveNode(DeliveryPeriod(2026 + i // 12, i % 12 + 1), float(price), "observed")
        for i, price in enumerate(prices)
    )
    return ForwardCurve(commodity=gas, market_date=date(2026, 1, 1), nodes=nodes)


def _storage_model() -> StorageModel:
    return StorageModel(
        min_inventory=0.0,
        max_inventory=2.0,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda _inv: 2.0,
        withdrawal_rate=lambda _inv: 2.0,
    )


# Feature: power-energy-quant-analysis, Property 64: Storage Extrinsic Non-Negativity and
# Bounds
# extrinsic = total - intrinsic >= 0 (down to the documented Monte-Carlo tolerance floor of
# a few standard errors), total == intrinsic + extrinsic exactly, and the intrinsic
# schedule respects the inventory/rate bounds at every step. Reduced examples with a small
# path count (each example runs an LSM backward induction).
@given(
    prices=st.lists(st.floats(min_value=1.0, max_value=50.0), min_size=2, max_size=4),
    volatility=st.floats(min_value=0.2, max_value=0.9),
    seed=st.integers(min_value=0, max_value=2**16),
)
@settings(max_examples=8, deadline=None)
def test_property_64_extrinsic_non_negative_and_bounds_hold(
    prices: list[float], volatility: float, seed: int
) -> None:
    model = _storage_model()
    curve = _storage_curve(prices)
    factor = StorageFactorModel(volatility=volatility, dt=1.0 / 12.0, path_count=800)
    result = storage_value(model, curve, factor, seed=seed, inventory_step=1.0)

    assert result.total == result.intrinsic + result.extrinsic  # exact, by construction
    assert result.extrinsic >= -3.0 * result.standard_error - 1e-6  # Property 64 MC floor

    intrinsic = storage_intrinsic(model, curve, inventory_step=1.0)
    tol = 1e-9
    horizon = len(intrinsic.injection)
    assert len(intrinsic.inventory) == horizon + 1
    for t in range(horizon):
        inv = intrinsic.inventory[t]
        assert model.min_inventory - tol <= inv <= model.max_inventory + tol
        assert 0.0 <= intrinsic.injection[t] <= model.injection_rate(inv) + tol
        assert 0.0 <= intrinsic.withdrawal[t] <= model.withdrawal_rate(inv) + tol
        assert intrinsic.inventory[t + 1] == pytest.approx(
            inv + intrinsic.injection[t] - intrinsic.withdrawal[t], abs=tol
        )
    assert model.min_inventory - tol <= intrinsic.inventory[horizon] <= model.max_inventory + tol


# Feature: power-energy-quant-analysis, Property 64: Storage Extrinsic Non-Negativity and
# Bounds
# Inconsistent inventory bounds raise a ValidationError naming the offending fields.
def test_property_64_inconsistent_bounds_raise() -> None:
    with pytest.raises(ValidationError, match=r"min_inventory.*max_inventory"):
        StorageModel(
            min_inventory=3.0,
            max_inventory=1.0,
            initial_inventory=1.0,
            terminal_inventory=1.0,
            injection_rate=lambda _inv: 1.0,
            withdrawal_rate=lambda _inv: 1.0,
        )


# ---------------------------------------------------------------------------------------
# Property 65: Storage >= Calendar-Spread-Option Value.
# ---------------------------------------------------------------------------------------


def _round_trip_store(volume: float) -> StorageModel:
    """A frictionless full-capacity store: it IS the buy-low/sell-high spread strategy."""
    return StorageModel(
        min_inventory=0.0,
        max_inventory=volume,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda _inv: volume,
        withdrawal_rate=lambda _inv: volume,
    )


# Feature: power-energy-quant-analysis, Property 65: Storage >= Calendar-Spread-Option
# Value
# Idealized two-period frictionless full-capacity store: the intrinsic value equals the
# replicable calendar-spread payoff max(0, spread)·volume exactly (floored at zero in
# backwardation), and the stochastic total dominates that locked value down to the MC floor.
@pytest.mark.parametrize(
    ("early", "late"),
    [(10.0, 14.0), (2.0, 7.0), (7.0, 2.0), (20.0, 20.0)],
)
def test_property_65_storage_dominates_replicable_calendar_spread(
    early: float, late: float
) -> None:
    volume = 2.0
    model = _round_trip_store(volume)
    curve = _storage_curve([early, late])
    spread = calendar_spread(curve, DeliveryPeriod(2026, 1), DeliveryPeriod(2026, 2))
    locked = max(0.0, spread.spread) * volume

    intrinsic = storage_intrinsic(model, curve, inventory_step=1.0)
    assert intrinsic.value == pytest.approx(locked, abs=1e-9)
    assert intrinsic.value >= spread.spread * volume  # option floor dominates the raw spread

    factor = StorageFactorModel(volatility=0.6, dt=1.0 / 12.0, path_count=2000)
    total = storage_value(model, curve, factor, seed=2024, inventory_step=1.0)
    assert total.total >= locked - 3.0 * total.standard_error


# ---------------------------------------------------------------------------------------
# Property 66: Projected-Spot Tagging and VaR Inapplicability.
# ---------------------------------------------------------------------------------------

_GAS = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
_POWER = CommodityConfig("EEX_PHELIX_DE", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh"))
_LIQUID = DeliveryPeriod(2027, 1)
_ILLIQUID = DeliveryPeriod(2035, 6)


def _long_dated_curve(commodity: CommodityConfig = _GAS) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=date(2026, 12, 1),
        nodes=(
            CurveNode(_LIQUID, 20.0, "observed"),
            CurveNode(DeliveryPeriod(2027, 2), 24.0, "interpolated"),
        ),
    )


def _spot_model(period: DeliveryPeriod) -> float:
    return 40.0 + 0.5 * (period.year - 2030)


# Feature: power-energy-quant-analysis, Property 66: Projected-Spot Tagging and VaR
# Inapplicability
# A liquid period is tagged FORWARD (value = the curve price and VaR applies); an illiquid
# period is tagged PROJECTED (value = spot_model + corporate premium, VaR inapplicable).
@given(premium=st.floats(min_value=-20.0, max_value=20.0), on_curve=st.booleans())
@settings(max_examples=100)
def test_property_66_valuation_source_and_var_applicability(premium: float, on_curve: bool) -> None:
    curve = _long_dated_curve()
    corporate = CorporatePremium(premium=premium, kind=PriceOfRiskKind.CORPORATE)
    period = _LIQUID if on_curve else _ILLIQUID
    benchmark = valuation_benchmark(period, curve, _spot_model, corporate)

    if on_curve:
        assert benchmark.source is ValuationSource.FORWARD
        assert benchmark.value == pytest.approx(20.0)
        assert benchmark.var_applicable is True
    else:
        assert benchmark.source is ValuationSource.PROJECTED
        assert benchmark.value == pytest.approx(_spot_model(period) + premium)
        assert benchmark.var_applicable is False

    # A position carrying the projected tag is flagged VaR-inapplicable (Req 23.3).
    tag = () if benchmark.source is ValuationSource.FORWARD else (ValuationSource.PROJECTED.value,)
    position = PricedPosition(
        position=Position(
            instrument=FuturesContract(_GAS, period, contract_price=50.0, notional=1.0),
            tags=tag,
        ),
        npv=benchmark.value,
    )
    verdict = var_applicability_guard(position)
    assert verdict.applicable is (benchmark.source is ValuationSource.FORWARD)
    if not verdict.applicable:
        with pytest.raises(ValidationError):
            var_applicability_guard(position, strict=True)


# Feature: power-energy-quant-analysis, Property 66: Projected-Spot Tagging and VaR
# Inapplicability
# The furthest-forward lower bound is a storable-only cash-and-carry trick; it is refused
# for non-storable power, and a market-tagged premium is rejected.
def test_property_66_furthest_forward_and_premium_governance() -> None:
    curve = _long_dated_curve(_POWER)
    with pytest.raises(ValidationError, match="storable"):
        furthest_forward_lower_bound(curve, _ILLIQUID, storable=False)
    # Storable commodities get the bound (the furthest visible forward price).
    bound = furthest_forward_lower_bound(_long_dated_curve(_GAS), _ILLIQUID, storable=True)
    assert bound.lower_bound == pytest.approx(24.0)
    # A market-tagged premium is rejected (never applied silently, Req 19.3/23.2).
    market_premium = CorporatePremium(premium=5.0, kind=PriceOfRiskKind.MARKET)
    with pytest.raises(ValidationError, match=r"CORPORATE|corporate"):
        valuation_benchmark(_ILLIQUID, _long_dated_curve(_GAS), _spot_model, market_premium)
