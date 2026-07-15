"""Chapter-10 & extended-component end-to-end integration tests (Tasks 78 & 84).

Seven realistic mini-scenarios exercised through the public facade, each anchored by
hand-checkable numbers rather than a bare no-raise:

1. **MC-VaR on a mixed book** — futures + forward + swap over a two-commodity factor
   grid, valued by ``monte_carlo_var`` under a physical-tagged drift. Anchors:
   ``var_99 >= var_95 > 0``, all bootstrap standard errors positive, and bit-identical
   determinism across two runs with the same seed.
2. **Parametric-vs-MC agreement on a linear book** — the book's aggregated deltas
   (read straight out of ``aggregate_delta``) plus the first-order lognormal
   price-change covariance feed ``parametric_var``; on a linear book at a one-day
   horizon this matches full-revaluation ``monte_carlo_var`` (8000 paths) to well
   within a documented ~10% tolerance (observed ~1%).
3. **Storage & dispatch end-to-end** — ``storage_value`` decomposes as
   ``total == intrinsic + extrinsic`` with ``extrinsic >= -3·SE`` (MC tolerance floor,
   contango), and ``dispatch_value`` (LSM) never beats the mean perfect-foresight
   optimum on its own scenario set (Property 62).
4. **Hedge-ratio round-trip** — on one linear cross-commodity input the four hedges
   coincide: ``linear_cross_hedge == variance_min_hedge`` (1-D) ``== local_mean_variance
   == global_mean_variance == rho·sigma_t/sigma_h`` (Property 56).
5. **Transport right across two hubs (Task 84)** — ``value_transport_right`` decomposes
   ``total == intrinsic + extrinsic`` with ``extrinsic >= 0``, and ``value_portfolio``
   prices a ``TransmissionRight`` to the same intrinsic PV.
6. **Schwartz-Smith -> tolling (Task 84)** — a power forward curve built from the
   two-factor ``forward_curve`` closed form feeds ``price_tolling_agreement`` (whose
   spread-option engine handles the correlated legs); near-ATM the NPV is finite,
   positive, and carries positive time value.
7. **Outage state feeding dispatch (Task 84)** — ``OutageDataset.forced_outage_multiplier``
   derates the dispatch availability and strictly reduces value vs full availability.

Workloads are deliberately small (reusing the shapes from ``tests/unit``) so the whole
module runs in a few seconds.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from quantvolt import (
    BUILT_IN_COMMODITIES,
    CommodityConfig,
    DiscountCurve,
    ForwardContract,
    ForwardCurve,
    FuturesContract,
    Hub,
    MarketData,
    PlantConfig,
    Portfolio,
    Position,
    StorageModel,
    SwapContract,
    TransmissionRight,
    VolatilitySurface,
    VolatilityTenor,
    aggregate_delta,
    dispatch_deterministic,
    dispatch_value,
    linear_cross_hedge,
    monte_carlo_var,
    parametric_var,
    price_tolling_agreement,
    storage_value,
    value_portfolio,
    value_transport_right,
    variance_min_hedge,
)
from quantvolt.assets.dispatch_sdp import DispatchFactorModel, PeakKind
from quantvolt.assets.plant import MaxCapacityCurve, PlantModel, StartCost, StartState
from quantvolt.assets.storage import StorageFactorModel
from quantvolt.curvemodels.schwartz_smith import SchwartzSmithParams, forward_curve
from quantvolt.hedging.mean_variance import global_mean_variance, local_mean_variance
from quantvolt.market.outages import OutageDataset, OutageRecord, OutageStatus, OutageType
from quantvolt.models.curve import CurveNode
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.numerics.daycount import actual_365
from quantvolt.numerics.monte_carlo import build_covariance
from quantvolt.numerics.risk_adjustment import DriftKind
from quantvolt.risk.mc_var import FactorModel, TaggedDrift

POWER = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
TTF = BUILT_IN_COMMODITIES["TTF"]
EUA = BUILT_IN_COMMODITIES["EUA"]
POWER_ID, TTF_ID = "EEX_PHELIX_DE", "TTF"

VALUATION_DATE = date(2026, 1, 1)
JUN = DeliveryPeriod(2026, 6)
DEC = DeliveryPeriod(2026, 12)


# =============================================================================
# Flows 1 & 2: a shared linear two-commodity book + GBM factor model
# =============================================================================
#
# Factors are strictly ascending by (commodity_id, period) as FactorModel requires:
#   0: (EEX_PHELIX_DE, JUN)  1: (EEX_PHELIX_DE, DEC)
#   2: (TTF, JUN)            3: (TTF, DEC)
F0 = np.array([100.0, 110.0, 30.0, 35.0])  # current forwards, factor order
SIGMA = np.array([0.25, 0.20, 0.30, 0.28])  # per-factor lognormal vol
CORR = np.array(
    [
        [1.0, 0.6, 0.3, 0.2],
        [0.6, 1.0, 0.2, 0.3],
        [0.3, 0.2, 1.0, 0.5],
        [0.2, 0.3, 0.5, 1.0],
    ]
)
DF_JUN, DF_DEC = 0.99, 0.98
FACTORS = ((POWER_ID, JUN), (POWER_ID, DEC), (TTF_ID, JUN), (TTF_ID, DEC))
# One trading day: sigma*sqrt(h) is small, so the linear-book MC VaR sits close to the
# Gaussian delta-normal (parametric) VaR — the documented consistency criterion.
HOLDING_PERIOD = 1.0 / 252.0

# Position notionals; every leg is long, so every aggregated delta is positive.
FUT_NOTIONAL, FWD_NOTIONAL, SWAP_NOTIONAL = 10.0, 5.0, 8.0


def make_market_data() -> MarketData:
    power_curve = ForwardCurve(
        commodity=POWER,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JUN, F0[0], "observed"), CurveNode(DEC, F0[1], "observed")),
    )
    ttf_curve = ForwardCurve(
        commodity=TTF,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(JUN, F0[2], "observed"), CurveNode(DEC, F0[3], "observed")),
    )
    discount = DiscountCurve(
        reference_date=VALUATION_DATE,
        tenors=(JUN.last_day, DEC.last_day),
        factors=(DF_JUN, DF_DEC),
    )
    return MarketData(
        forward_curves={POWER_ID: power_curve, TTF_ID: ttf_curve},
        discount_curve=discount,
        valuation_date=VALUATION_DATE,
    )


def make_factor_model() -> FactorModel:
    return FactorModel(
        market_data=make_market_data(), factors=FACTORS, sigma=SIGMA.copy(), corr=CORR.copy()
    )


def make_linear_book() -> list[Position]:
    """Long futures (power JUN) + long forward (power DEC) + long swap (TTF JUN/DEC)."""
    futures = FuturesContract(POWER, JUN, contract_price=95.0, notional=FUT_NOTIONAL)
    forward = ForwardContract(POWER, DEC, contract_price=100.0, notional=FWD_NOTIONAL)
    swap = SwapContract(
        TTF,
        fixed_rate=31.0,
        floating_index="TTF_DA",
        notional=SWAP_NOTIONAL,
        schedule=DeliverySchedule((JUN, DEC)),
    )
    return [Position(futures), Position(forward), Position(swap)]


# Hand-computed aggregated delta per factor = discount_factor * notional (each leg long).
AGG_DELTA = np.array(
    [
        DF_JUN * FUT_NOTIONAL,  # power JUN futures  -> 9.90
        DF_DEC * FWD_NOTIONAL,  # power DEC forward  -> 4.90
        DF_JUN * SWAP_NOTIONAL,  # TTF JUN swap leg   -> 7.92
        DF_DEC * SWAP_NOTIONAL,  # TTF DEC swap leg   -> 7.84
    ]
)


class TestMonteCarloVaROnMixedBook:
    """Flow 1: full-revaluation MC-VaR under a physical-tagged drift."""

    def test_var_ordering_ses_and_determinism(self) -> None:
        physical = TaggedDrift(values=np.array([0.01, 0.01, 0.0, -0.01]), kind=DriftKind.PHYSICAL)
        first = monte_carlo_var(
            make_linear_book(),
            make_factor_model(),
            physical,
            HOLDING_PERIOD,
            path_count=4000,
            seed=20260714,
        )
        # VaR ladder is well-ordered and strictly positive on a long, volatile book.
        assert first.var_99 >= first.var_95 > 0.0
        # 97.5% tail mean sits at/above the 95% quantile (it can be below the 99% VaR).
        assert first.cvar_975 >= first.var_95
        # Every reported quantile carries a positive bootstrap sampling error.
        assert first.var_95_se > 0.0
        assert first.var_99_se > 0.0
        assert first.cvar_975_se > 0.0

        # Determinism (Req 15.3): same seed -> a bit-identical result object.
        second = monte_carlo_var(
            make_linear_book(),
            make_factor_model(),
            physical,
            HOLDING_PERIOD,
            path_count=4000,
            seed=20260714,
        )
        assert first == second


class TestParametricVsMonteCarloAgreement:
    """Flow 2: parametric (delta-normal) VaR agrees with full-revaluation MC on a linear book."""

    def test_aggregated_deltas_are_discount_times_notional(self) -> None:
        valuation = value_portfolio(
            Portfolio(positions=tuple(make_linear_book())), make_market_data()
        )
        matrix = aggregate_delta(list(valuation.priced))
        deltas = np.array([matrix.delta_at(cid, period) for cid, period in FACTORS])
        # These aggregated deltas are exactly what the parametric VaR consumes below.
        np.testing.assert_allclose(deltas, AGG_DELTA)
        np.testing.assert_allclose(deltas, np.array([9.90, 4.90, 7.92, 7.84]))

    def test_parametric_matches_mc_within_ten_percent(self) -> None:
        # Aggregate the book's deltas through the public risk facade.
        valuation = value_portfolio(
            Portfolio(positions=tuple(make_linear_book())), make_market_data()
        )
        matrix = aggregate_delta(list(valuation.priced))
        deltas = np.array([matrix.delta_at(cid, period) for cid, period in FACTORS])

        # Matching covariance: the first-order lognormal price-change covariance over the
        # horizon, Cov(dP_a, dP_b) = F0_a F0_b sigma_a sigma_b rho_ab h (see risk/mc_var).
        price_cov = np.array(
            [
                [
                    F0[a] * F0[b] * SIGMA[a] * SIGMA[b] * CORR[a, b] * HOLDING_PERIOD
                    for b in range(4)
                ]
                for a in range(4)
            ]
        )
        parametric = parametric_var(deltas, price_cov)

        zero_drift = TaggedDrift(values=np.zeros(4), kind=DriftKind.PHYSICAL)
        mc = monte_carlo_var(
            make_linear_book(),
            make_factor_model(),
            zero_drift,
            HOLDING_PERIOD,
            path_count=8000,
            seed=20260714,
        )

        # A linear book with small sigma*sqrt(h) makes full-revaluation MC converge to the
        # Gaussian delta-normal VaR. Tolerance ~10% covers MC sampling error plus the
        # O(sigma^2 h) lognormal-vs-normal bias (observed agreement here is ~1%).
        assert parametric.var_at(0.95) == pytest.approx(mc.var_95, rel=0.10)
        assert parametric.var_at(0.99) == pytest.approx(mc.var_99, rel=0.10)
        assert parametric.var_at(0.99) > parametric.var_at(0.95) > 0.0
        assert mc.var_99 > mc.var_95 > 0.0


# =============================================================================
# Flow 3: storage + dispatch valuation end-to-end
# =============================================================================


def _gas_curve(prices: list[float]) -> ForwardCurve:
    gas = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE", "EUR/MWh"))
    nodes = tuple(
        CurveNode(DeliveryPeriod(2026 + index // 12, index % 12 + 1), price, "observed")
        for index, price in enumerate(prices)
    )
    return ForwardCurve(commodity=gas, market_date=date(2026, 1, 1), nodes=nodes)


def _const_heat_rate(rate: float):
    return lambda _q, _temp: rate


def _const_c_max(capacity: float) -> MaxCapacityCurve:
    return lambda _temp: capacity


def _start_costs() -> dict[StartState, StartCost]:
    return {
        StartState.HOT: StartCost(fixed=50.0, fuel=0.0, power=0.0),
        StartState.WARM: StartCost(fixed=100.0, fuel=0.0, power=0.0),
        StartState.COLD: StartCost(fixed=200.0, fuel=0.0, power=0.0),
    }


def _make_plant() -> PlantModel:
    return PlantModel(
        heat_rate=_const_heat_rate(2.0),
        c_min=10.0,
        c_max=_const_c_max(30.0),
        variable_om_cost=0.0,
        start_costs=_start_costs(),
        ramp_rate=10.0,
        d_min=2,
        d_shutdown=1,
        d_startup=0,
        outage_rate=0.0,
        hot_max_downtime=1,
        warm_max_downtime=3,
    )


_DISPATCH_DT = 1.0 / 50.0
_DISPATCH_TEMP = 15.0
_DISPATCH_HORIZON = 5


def _make_dispatch_factor_model() -> DispatchFactorModel:
    forwards = (55.0, 42.0, 20.0)  # power_on, power_off, gas
    sigmas = [0.35, 0.30, 0.45]
    corr = np.eye(3)
    corr[0, 2] = corr[2, 0] = 0.3
    corr[1, 2] = corr[2, 1] = 0.3
    covariance = build_covariance(sigmas, corr, _DISPATCH_DT)
    peaks = tuple(
        PeakKind.ON_PEAK if t % 2 == 0 else PeakKind.OFF_PEAK for t in range(_DISPATCH_HORIZON)
    )
    return DispatchFactorModel(
        log_forward0=np.log(np.asarray(forwards, dtype=np.float64)),
        drift=-0.5 * np.diag(covariance),
        covariance=covariance,
        drift_kind=DriftKind.RISK_NEUTRAL,
        peak_kinds=peaks,
        temperatures=(_DISPATCH_TEMP,) * _DISPATCH_HORIZON,
        power_on_index=0,
        power_off_index=1,
        gas_index=2,
    )


class TestStorageAndDispatchEndToEnd:
    def test_storage_value_decomposes_and_respects_tolerance_floor(self) -> None:
        # Frictionless fast store, empty-to-empty, steep contango: intrinsic locks the
        # forward calendar spread; extrinsic (timing value) is ~0 and may sample slightly
        # negative, bounded below by the documented -3*SE Monte Carlo floor (Property 64).
        model = StorageModel(
            min_inventory=0.0,
            max_inventory=2.0,
            initial_inventory=0.0,
            terminal_inventory=0.0,
            injection_rate=lambda inv: 2.0,
            withdrawal_rate=lambda inv: 2.0,
        )
        factor = StorageFactorModel(volatility=0.7, dt=1 / 12, path_count=4000)
        curve = _gas_curve([15.0, 16.0, 17.0, 18.0, 19.0, 20.0])
        result = storage_value(model, curve, factor, seed=2024, inventory_step=1.0)

        assert result.intrinsic == pytest.approx(10.0, abs=1e-9)  # buy 15/16, sell 19/20
        assert result.total == result.intrinsic + result.extrinsic  # exact by construction
        assert result.standard_error > 0.0
        assert result.extrinsic >= -3.0 * result.standard_error

    def test_dispatch_value_bounded_by_mean_perfect_foresight(self) -> None:
        # Property 62: the non-anticipative LSM value never beats the mean of the
        # per-path perfect-foresight optima evaluated on the *same* scenario set.
        plant = _make_plant()
        factor_model = _make_dispatch_factor_model()
        seed, path_count = 11, 256
        result = dispatch_value(plant, factor_model, method="lsm", seed=seed, path_count=path_count)

        paths = factor_model.simulate(seed, path_count)
        foresight = []
        for p in range(paths.shape[0]):
            power = [
                float(np.exp(paths[p, t + 1, factor_model.active_power_index(t)]))
                for t in range(_DISPATCH_HORIZON)
            ]
            gas = [
                float(np.exp(paths[p, t + 1, factor_model.gas_index]))
                for t in range(_DISPATCH_HORIZON)
            ]
            foresight.append(
                dispatch_deterministic(
                    plant, power, gas, [_DISPATCH_TEMP] * _DISPATCH_HORIZON
                ).total_value
            )
        mean_perfect = float(np.mean(foresight))

        assert result.value <= mean_perfect + 1e-9
        assert result.value > 0.0  # the plant is in the money on the on-peak strip


# =============================================================================
# Flow 4: hedge-ratio round-trip on a linear cross-commodity input
# =============================================================================


class TestHedgeRatioRoundTrip:
    def test_four_hedges_coincide_on_linear_product(self) -> None:
        # Example 10.2 linear two-asset product: target F_P, hedge F_G, dW_P dW_G = rho dt.
        rho, sigma_target, sigma_hedge = 0.8, 0.3, 0.2
        dt, n_periods = 1.0 / 12.0, 3
        expected = rho * sigma_target / sigma_hedge  # eq 10.22 -> 1.2

        # (a) direct closed form
        direct = linear_cross_hedge(rho=rho, sigma_target=sigma_target, sigma_hedge=sigma_hedge)
        # (b) the 1-D variance-minimizing solve: Sigma_hh = [[sigma_h^2]],
        #     Sigma_ht = [rho * sigma_t * sigma_h].
        vm = variance_min_hedge(
            np.array([[sigma_hedge**2]]), np.array([rho * sigma_target * sigma_hedge])
        )
        # (c)/(d) mean-variance over n independent equal periods: M and C both diagonal.
        cov_target_hedge = (rho * sigma_target * sigma_hedge * dt) * np.eye(n_periods)
        cov_hedge = (sigma_hedge**2 * dt) * np.eye(n_periods)
        local = local_mean_variance(cov_target_hedge, cov_hedge)
        glob = global_mean_variance(cov_target_hedge, cov_hedge)

        assert direct == pytest.approx(1.2)
        assert vm.shape == (1,)
        assert vm[0] == pytest.approx(direct)
        # local == global == the direct/1-D hedge, every period (Property 56 triple identity).
        np.testing.assert_allclose(local, np.full(n_periods, expected), rtol=1e-12)
        np.testing.assert_allclose(glob, np.full(n_periods, expected), rtol=1e-12)
        np.testing.assert_allclose(local, glob, rtol=1e-12)


# =============================================================================
# Flow 5 (Task 84): transport right across two hub curves + portfolio pricing
# =============================================================================

_TR_REF = date(2026, 7, 1)
_TR_JAN = DeliveryPeriod(2027, 1)
_TR_FEB = DeliveryPeriod(2027, 2)
_TR_MAR = DeliveryPeriod(2027, 3)
_TR_PERIODS = (_TR_JAN, _TR_FEB, _TR_MAR)
_ORIGIN = CommodityConfig("HUB_A", "EUR/MWh", Hub("HUB_A", "EEX", "EUR/MWh"))
_DEST = CommodityConfig("HUB_B", "EUR/MWh", Hub("HUB_B", "EEX", "EUR/MWh"))


def _hub_curve(commodity: CommodityConfig, prices: dict[DeliveryPeriod, float]) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=_TR_REF,
        nodes=tuple(
            CurveNode(period, price, "observed") for period, price in sorted(prices.items())
        ),
    )


def _transport_discount() -> DiscountCurve:
    return DiscountCurve(
        reference_date=_TR_REF,
        tenors=(_TR_JAN.last_day, _TR_FEB.last_day, _TR_MAR.last_day),
        factors=(0.99, 0.98, 0.97),
    )


class TestTransportRightEndToEnd:
    def _inputs(self) -> tuple[TransmissionRight, ForwardCurve, ForwardCurve, DiscountCurve]:
        # Spreads P_B - P_A - T_AB: JAN 55-40-5=+10 (ITM), FEB -3, MAR -20.
        curve_a = _hub_curve(_ORIGIN, {_TR_JAN: 40.0, _TR_FEB: 50.0, _TR_MAR: 60.0})
        curve_b = _hub_curve(_DEST, {_TR_JAN: 55.0, _TR_FEB: 52.0, _TR_MAR: 45.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule(_TR_PERIODS)
        )
        return right, curve_a, curve_b, _transport_discount()

    def test_intrinsic_extrinsic_consistency(self) -> None:
        right, curve_a, curve_b, discount = self._inputs()
        result = value_transport_right(
            right, curve_a, curve_b, discount, vols=(0.30, 0.35), correlation=0.5
        )
        # Only JAN is in the money intrinsically: PV = 0.99 * 10 * 10 = 99.0.
        assert result.intrinsic == pytest.approx(99.0)
        assert result.extrinsic > 0.0  # OTM Feb/Mar still carry spread-option time value
        assert result.total == pytest.approx(result.intrinsic + result.extrinsic)
        for pv in result.per_period:
            assert pv.value == pytest.approx(pv.intrinsic + pv.extrinsic)
            assert pv.extrinsic >= -1e-9

    def test_portfolio_prices_transmission_right(self) -> None:
        right, curve_a, curve_b, discount = self._inputs()
        market_data = MarketData(
            forward_curves={"HUB_A": curve_a, "HUB_B": curve_b},
            discount_curve=discount,
            valuation_date=_TR_REF,
        )
        valuation = value_portfolio(Portfolio(positions=(Position(right),)), market_data)  # type: ignore[arg-type]

        assert valuation.unpriced == ()
        assert len(valuation.priced) == 1
        # Portfolio NPV equals the direct intrinsic PV (no vols supplied -> intrinsic only).
        direct = value_transport_right(right, curve_a, curve_b, discount)
        assert valuation.priced[0].npv == pytest.approx(direct.total)
        assert valuation.priced[0].npv == pytest.approx(99.0)
        # Opposite-signed deltas on the two hubs for the active JAN period.
        delta = valuation.priced[0].delta
        assert delta[("HUB_B", _TR_JAN)] == pytest.approx(0.99 * 10.0)
        assert delta[("HUB_A", _TR_JAN)] == pytest.approx(-0.99 * 10.0)


# =============================================================================
# Flow 6 (Task 84): Schwartz-Smith forward curve -> correlated tolling valuation
# =============================================================================

_SS_PARAMS = SchwartzSmithParams(
    kappa=1.2, sigma_chi=0.30, sigma_xi=0.15, mu_xi=0.02, rho=-0.3, lambda_chi=0.05, lambda_xi=0.01
)
_TOLL_PERIODS = tuple(DeliveryPeriod(2027, month) for month in range(1, 7))
_TOLL_REF = date(2026, 7, 1)


class TestSchwartzSmithToTolling:
    def test_ss_curve_feeds_tolling_with_positive_time_value(self) -> None:
        # Build the power forward strip from the two-factor closed form (§31.2).
        maturities = np.array([actual_365(_TOLL_REF, period.last_day) for period in _TOLL_PERIODS])
        power_prices = forward_curve(_SS_PARAMS, chi=0.4, xi=4.0, t=0.0, tenors=maturities)
        assert np.all(np.isfinite(power_prices))
        assert np.all(power_prices > 0.0)

        power_curve = ForwardCurve(
            commodity=POWER,
            market_date=_TOLL_REF,
            nodes=tuple(
                CurveNode(period, float(price), "observed")
                for period, price in zip(_TOLL_PERIODS, power_prices, strict=True)
            ),
        )

        def _flat(commodity: CommodityConfig, price: float) -> ForwardCurve:
            return ForwardCurve(
                commodity=commodity,
                market_date=_TOLL_REF,
                nodes=tuple(CurveNode(period, price, "observed") for period in _TOLL_PERIODS),
            )

        # Fuel/EUA chosen so the clean-spark breakeven (2*22 + 0.4*45 + 3 = 65) sits inside
        # the SS power strip (~61.7-66.5): a near-ATM tolling agreement.
        fuel_curve = _flat(TTF, 22.0)
        eua_curve = _flat(EUA, 45.0)
        vol_surface = VolatilitySurface(
            commodity=POWER,
            tenors=tuple(VolatilityTenor(period=period, sigma=0.35) for period in _TOLL_PERIODS),
        )
        correlation = np.array([[1.0, 0.6, 0.3], [0.6, 1.0, 0.4], [0.3, 0.4, 1.0]])
        discount = DiscountCurve(
            reference_date=_TOLL_REF,
            tenors=tuple(period.last_day for period in _TOLL_PERIODS),
            factors=tuple(0.99 - 0.005 * index for index in range(len(_TOLL_PERIODS))),
        )
        plant = PlantConfig(
            heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas"
        )

        result = price_tolling_agreement(
            plant,
            power_curve,
            fuel_curve,
            eua_curve,
            vol_surface,
            correlation,
            DeliverySchedule(periods=_TOLL_PERIODS),
            discount,
        )

        assert math.isfinite(result.npv)
        assert result.npv > 0.0
        assert result.time_value > 0.0  # near-ATM strip carries genuine optionality
        assert result.npv == pytest.approx(result.intrinsic_value + result.time_value)


# =============================================================================
# Flow 7 (Task 84): outage state derates the dispatch availability
# =============================================================================

_OUTAGE_START = datetime(2026, 1, 1)
_OUTAGE_PERIOD_HOURS = 100.0
_OUTAGE_INSTALLED = 100.0


def _outage_record(outage_type: OutageType, unavailable: float, hours: float) -> OutageRecord:
    return OutageRecord(
        asset_id="A1",
        unit_id="U1",
        technology="CCGT",
        market_zone="DE",
        outage_id="O1",
        outage_type=outage_type,
        status=OutageStatus.COMPLETED,
        announcement_time=_OUTAGE_START - timedelta(days=1),
        start_time=_OUTAGE_START,
        expected_end_time=_OUTAGE_START + timedelta(hours=hours),
        installed_capacity_mw=100.0,
        unavailable_capacity_mw=unavailable,
        available_capacity_mw=100.0 - unavailable,
        source="TSO",
        revision_number=0,
        actual_end_time=None,
    )


class TestOutageFeedsDispatch:
    def test_forced_outage_multiplier_derates_dispatch_value(self) -> None:
        # Forced energy = 100*10 + 50*10 = 1500 MWh -> M = 1 - 1500/(100*100) = 0.85.
        dataset = OutageDataset(
            (
                _outage_record(OutageType.FORCED, 100.0, 10.0),
                _outage_record(OutageType.FORCED, 50.0, 10.0),
            )
        )
        multiplier = dataset.forced_outage_multiplier(_OUTAGE_PERIOD_HOURS, _OUTAGE_INSTALLED)
        assert multiplier == pytest.approx(0.85)
        assert 0.0 <= multiplier <= 1.0

        plant = _make_plant()
        factor_model = _make_dispatch_factor_model()
        full = dispatch_value(plant, factor_model, method="lsm", seed=11, path_count=512)
        derated = dispatch_value(
            plant,
            factor_model,
            method="lsm",
            seed=11,
            path_count=512,
            availability=[multiplier] * factor_model.horizon,
        )
        # Derating the available capacity strictly reduces the optionality value.
        assert derated.value < full.value
        assert derated.value >= 0.0
