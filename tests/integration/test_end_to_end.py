"""End-to-end integration tests (Task 50; portfolio-native-pricers Task 13) —
exercised through the public facade only.

Five realistic mini-scenarios, each anchored by hand-checkable numbers:

1. **Curve build -> pricing -> risk**: TTF and EEX_PHELIX_DE curves are built by
   ``CurveBuilder`` from ``InstrumentPriceRecord``s with a gap month (proving
   interpolation), a futures and a swap are priced off them through
   ``value_portfolio``, and ``RiskEngine.compute_risk`` runs over a deterministic
   loss-ladder scenario matrix.
2. **Tolling**: power/gas/EUA curves + vol surface + 3x3 correlation matrix over a
   6-month schedule; NPV decomposes into intrinsic + time value and reacts
   economically to a +10 EUR power-curve shift.
3. **Portfolio risk, mixed book**: futures + forward + swap + an unregistered
   instrument type; the dummy lands in ``unpriced``, deltas aggregate exactly, and
   the built-in "European Gas Crisis 2022" scenario decomposes per position.
4. **Multi-commodity mark-to-market**: settlement prices for some positions,
   forward-curve fallback (flagged ``estimated``) for others, a missing-both case
   raising ``NoPricingDataError``, and idempotence.
5. **Portfolio-native options + transport right**: a future, a swap, a native
   vanilla option, a native spread option, and a transmission right in one book,
   all priced by ``value_portfolio`` with no ``pricers=`` argument; per-position
   NPVs match the direct kernel calls and deltas aggregate across every instrument
   type (Req 7, 8; base-spec Req 24).

All discount factors are stored exactly at the settlement-date tenors so every NPV
below is hand-computable without interpolation of the discount curve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import numpy.typing as npt
import pytest

from quantvolt import (
    BUILT_IN_COMMODITIES,
    CommodityConfig,
    CurveBuilder,
    CurveBuildResult,
    CurveNode,
    DeliveryPeriod,
    DeliverySchedule,
    DiscountCurve,
    ForwardContract,
    ForwardCurve,
    FuturesContract,
    InstrumentPriceRecord,
    MarketData,
    MtMPosition,
    NoPricingDataError,
    OptionSide,
    OptionType,
    PlantConfig,
    Portfolio,
    PortfolioValuation,
    Position,
    RiskEngine,
    RiskResult,
    SpreadOptionContract,
    SpreadOptionRequest,
    SwapContract,
    TollingResult,
    TransmissionRight,
    VanillaOptionContract,
    VanillaOptionRequest,
    VolatilitySurface,
    VolatilityTenor,
    aggregate_delta,
    mark_to_market,
    price_futures,
    price_spread_option,
    price_swap,
    price_tolling_agreement,
    price_vanilla_option,
    value_portfolio,
    value_transport_right,
)

VALUATION_DATE = date(2026, 7, 1)

TTF = BUILT_IN_COMMODITIES["TTF"]
POWER = BUILT_IN_COMMODITIES["EEX_PHELIX_DE"]
EUA = BUILT_IN_COMMODITIES["EUA"]

SIX_PERIODS = tuple(DeliveryPeriod(2027, month) for month in range(1, 7))
JAN, FEB, MAR, APR, MAY, JUN = SIX_PERIODS

# Discount factors stored exactly at each 2027 month-end settlement tenor.
DF_JAN, DF_FEB, DF_MAR = 0.99, 0.985, 0.98
DF_APR, DF_MAY, DF_JUN = 0.975, 0.97, 0.965


def make_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=VALUATION_DATE,
        tenors=(
            date(2027, 1, 31),
            date(2027, 2, 28),
            date(2027, 3, 31),
            date(2027, 4, 30),
            date(2027, 5, 31),
            date(2027, 6, 30),
        ),
        factors=(DF_JAN, DF_FEB, DF_MAR, DF_APR, DF_MAY, DF_JUN),
    )


def make_observed_curve(
    commodity: CommodityConfig,
    periods: tuple[DeliveryPeriod, ...],
    prices: tuple[float, ...],
) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=VALUATION_DATE,
        nodes=tuple(
            CurveNode(period=period, price=price, status="observed")
            for period, price in zip(periods, prices, strict=True)
        ),
    )


def price_record(
    commodity: CommodityConfig, period: DeliveryPeriod, price: float
) -> InstrumentPriceRecord:
    return InstrumentPriceRecord(
        instrument_id=f"{commodity.commodity_id}-{period.year}-{period.month:02d}",
        commodity=commodity,
        delivery_period=period,
        price=price,
    )


# =============================================================================
# Flow 1: curve build -> pricing -> portfolio valuation -> risk
# =============================================================================

# TTF quotes leave FEB unquoted; piecewise-linear fill on the monthly axis puts
# FEB midway between JAN 30 and MAR 34 -> 32.0 (the interpolation anchor).
TTF_RECORDS = ((JAN, 30.0), (MAR, 34.0), (APR, 36.0))
# Power quotes leave FEB unquoted too: midway between 90 and 98 -> 94.0.
POWER_RECORDS = ((JAN, 90.0), (MAR, 98.0))

FUT_TTF = FuturesContract(TTF, JAN, contract_price=28.0, notional=100.0)
FUT_POWER = FuturesContract(POWER, FEB, contract_price=90.0, notional=10.0)
SWAP_TTF = SwapContract(
    TTF,
    fixed_rate=31.0,
    floating_index="TTF_DA",
    notional=50.0,
    schedule=DeliverySchedule((JAN, FEB)),
)

# Hand-computed anchors (NPV = df * (forward - contract_price) * notional):
FUT_TTF_NPV = DF_JAN * (30.0 - 28.0) * 100.0  # 198.0
FUT_POWER_NPV = DF_FEB * (94.0 - 90.0) * 10.0  # 39.4  (interpolated node!)
SWAP_TTF_NPV = DF_JAN * (30.0 - 31.0) * 50.0 + DF_FEB * (32.0 - 31.0) * 50.0  # -0.25
FUT_TTF_DELTA = DF_JAN * 100.0  # 99.0
FUT_POWER_DELTA = DF_FEB * 10.0  # 9.85
SWAP_DELTA_JAN, SWAP_DELTA_FEB = DF_JAN * 50.0, DF_FEB * 50.0  # 49.5, 49.25
TOTAL_BOOK_DELTA = FUT_TTF_DELTA + FUT_POWER_DELTA + SWAP_DELTA_JAN + SWAP_DELTA_FEB  # 207.6


def build_ttf_result() -> CurveBuildResult:
    records = [price_record(TTF, period, price) for period, price in TTF_RECORDS]
    return CurveBuilder().build(TTF, VALUATION_DATE, records, interpolation="piecewise_linear")


def build_power_result() -> CurveBuildResult:
    records = [price_record(POWER, period, price) for period, price in POWER_RECORDS]
    return CurveBuilder().build(POWER, VALUATION_DATE, records, interpolation="piecewise_linear")


def make_flow_one_book() -> Portfolio:
    return Portfolio(
        positions=(
            Position(FUT_TTF, position_id="POS-FUT-TTF"),
            Position(FUT_POWER, position_id="POS-FUT-PWR"),
            Position(SWAP_TTF, position_id="POS-SWP-TTF"),
        ),
        name="curve-to-risk-book",
    )


def make_flow_one_market_data(ttf_curve: ForwardCurve, power_curve: ForwardCurve) -> MarketData:
    return MarketData(
        forward_curves={"TTF": ttf_curve, "EEX_PHELIX_DE": power_curve},
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
    )


def make_loss_ladder(n_scenarios: int, n_factors: int) -> npt.NDArray[np.float64]:
    """Row k (1-based) shocks EVERY factor by -0.01*k -> pnl_k = -0.01*k*sum(delta)."""
    return np.outer(-0.01 * np.arange(1.0, n_scenarios + 1.0), np.ones(n_factors))


def run_curve_to_risk_flow() -> tuple[PortfolioValuation, RiskResult]:
    """The full flow-1 pipeline, reused verbatim by the determinism test."""
    ttf_curve = build_ttf_result().curve
    power_curve = build_power_result().curve
    market_data = make_flow_one_market_data(ttf_curve, power_curve)
    valuation = value_portfolio(make_flow_one_book(), market_data)
    risk = RiskEngine().compute_risk(list(valuation.priced), make_loss_ladder(20, 4))
    return valuation, risk


class TestCurveToPricingToRiskFlow:
    def test_gap_months_are_interpolated_on_both_curves(self) -> None:
        ttf_curve = build_ttf_result().curve
        assert [node.period for node in ttf_curve.nodes] == [JAN, FEB, MAR, APR]
        assert [node.status for node in ttf_curve.nodes] == [
            "observed",
            "interpolated",
            "observed",
            "observed",
        ]
        assert ttf_curve.price_at(FEB) == pytest.approx(32.0)

        power_curve = build_power_result().curve
        assert [node.status for node in power_curve.nodes] == [
            "observed",
            "interpolated",
            "observed",
        ]
        assert power_curve.price_at(FEB) == pytest.approx(94.0)

    def test_curve_build_reprices_inputs_with_no_arbitrage_warnings(self) -> None:
        result = build_ttf_result()
        assert result.arbitrage_warnings == []  # contango inputs: nothing to flag
        assert set(result.reprice_residuals) == {
            "TTF-2027-01",
            "TTF-2027-03",
            "TTF-2027-04",
        }
        for residual in result.reprice_residuals.values():
            assert residual == pytest.approx(0.0, abs=1e-12)

    def test_portfolio_npvs_match_direct_pricer_calls(self) -> None:
        ttf_curve = build_ttf_result().curve
        power_curve = build_power_result().curve
        discount_curve = make_discount_curve()
        market_data = make_flow_one_market_data(ttf_curve, power_curve)

        valuation = value_portfolio(make_flow_one_book(), market_data)

        assert valuation.unpriced == ()
        fut_ttf = price_futures(FUT_TTF, ttf_curve, VALUATION_DATE, discount_curve)
        fut_power = price_futures(FUT_POWER, power_curve, VALUATION_DATE, discount_curve)
        swap = price_swap(SWAP_TTF, ttf_curve, discount_curve)
        assert valuation.priced[0].npv == fut_ttf.npv
        assert valuation.priced[1].npv == fut_power.npv
        assert valuation.priced[2].npv == swap.npv
        assert valuation.total_npv == pytest.approx(fut_ttf.npv + fut_power.npv + swap.npv)

    def test_hand_computed_npvs_flow_through_valuation(self) -> None:
        valuation, _ = run_curve_to_risk_flow()
        # The power futures and the swap's FEB leg both settle on INTERPOLATED
        # nodes (94.0 and 32.0), so these anchors prove interpolation feeds pricing.
        assert valuation.priced[0].npv == pytest.approx(198.0)
        assert valuation.priced[1].npv == pytest.approx(39.4)
        assert valuation.priced[2].npv == pytest.approx(-0.25)
        assert valuation.total_npv == pytest.approx(237.15)

    def test_risk_metrics_on_deterministic_loss_ladder(self) -> None:
        _, risk = run_curve_to_risk_flow()

        assert risk.exclusion_report == []
        assert risk.partial is False
        assert risk.unprocessed_indices == []

        matrix = risk.delta_matrix
        assert matrix.commodities == ("EEX_PHELIX_DE", "TTF")
        assert matrix.periods == (JAN, FEB)
        assert matrix.delta_at("TTF", JAN) == pytest.approx(148.5)  # futures + swap JAN
        assert matrix.delta_at("TTF", FEB) == pytest.approx(49.25)  # swap FEB leg
        assert matrix.delta_at("EEX_PHELIX_DE", FEB) == pytest.approx(9.85)
        assert matrix.delta_at("EEX_PHELIX_DE", JAN) == 0.0

        for value in (risk.var_95, risk.var_99, risk.cvar_975):
            assert math.isfinite(value)
        assert risk.var_99 >= risk.var_95
        # Losses are an exact ladder 1..20 scaled by 0.01 * 207.6; np.percentile's
        # linear interpolation on n=20 gives ranks 19.05 (q95), 19.81 (q99), and the
        # inclusive 97.5% tail {20} for CVaR.
        scale = 0.01 * TOTAL_BOOK_DELTA
        assert risk.var_95 == pytest.approx(19.05 * scale, rel=1e-9)
        assert risk.var_99 == pytest.approx(19.81 * scale, rel=1e-9)
        assert risk.cvar_975 == pytest.approx(20.0 * scale, rel=1e-9)


# =============================================================================
# Flow 2: tolling valuation across power / fuel / EUA curves
# =============================================================================

TOLL_POWER_PRICES = (95.0, 96.0, 84.0, 88.0, 100.0, 92.0)
TOLL_GAS_PRICES = (30.0, 32.0, 28.0, 30.0, 33.0, 31.0)
TOLL_EUA_PRICES = (70.0, 72.0, 68.0, 70.0, 74.0, 71.0)
TOLL_SIGMAS = (0.40, 0.38, 0.35, 0.33, 0.30, 0.28)

# Per-period forward spread = power - 2*gas - 0.4*eua - 3 (heat rate 2.0, emissions
# intensity 0.2 -> EUA weight 0.4, variable O&M 3.0):
#   +4.0, +0.2, -2.2, -3.0, +1.4, -1.4  ->  intrinsic = 4.0 + 0.2 + 1.4 = 5.6
PLANT = PlantConfig(heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas")
TOLL_INTRINSIC = 5.6


def make_vol_surface() -> VolatilitySurface:
    return VolatilitySurface(
        commodity=POWER,
        tenors=tuple(
            VolatilityTenor(period=period, sigma=sigma)
            for period, sigma in zip(SIX_PERIODS, TOLL_SIGMAS, strict=True)
        ),
    )


def make_correlation_matrix() -> npt.NDArray[np.float64]:
    return np.array(
        [
            [1.0, 0.6, 0.3],
            [0.6, 1.0, 0.4],
            [0.3, 0.4, 1.0],
        ]
    )


def price_toll(power_prices: tuple[float, ...] = TOLL_POWER_PRICES) -> TollingResult:
    return price_tolling_agreement(
        plant=PLANT,
        power_curve=make_observed_curve(POWER, SIX_PERIODS, power_prices),
        fuel_curve=make_observed_curve(TTF, SIX_PERIODS, TOLL_GAS_PRICES),
        eua_curve=make_observed_curve(EUA, SIX_PERIODS, TOLL_EUA_PRICES),
        vol_surface=make_vol_surface(),
        correlation_matrix=make_correlation_matrix(),
        schedule=DeliverySchedule(periods=SIX_PERIODS),
        discount_curve=make_discount_curve(),
    )


class TestTollingValuationFlow:
    def test_npv_decomposes_into_intrinsic_plus_time_value(self) -> None:
        result = price_toll()
        assert result.intrinsic_value == pytest.approx(TOLL_INTRINSIC)
        assert result.time_value == result.npv - result.intrinsic_value
        assert result.npv == pytest.approx(result.intrinsic_value + result.time_value)
        assert result.time_value > 0.0  # three periods are near/out of the money

    def test_aggregate_deltas_equal_per_period_sums(self) -> None:
        result = price_toll()
        assert set(result.per_period_deltas) == {"power", "fuel", "eua"}
        assert set(result.aggregate_deltas) == {"power", "fuel", "eua"}
        for leg, per_period in result.per_period_deltas.items():
            assert len(per_period) == len(SIX_PERIODS)
            assert result.aggregate_deltas[leg] == sum(per_period)
        # A tolling agreement is long power, short fuel and carbon.
        assert result.aggregate_deltas["power"] > 0.0
        assert result.aggregate_deltas["fuel"] < 0.0
        assert result.aggregate_deltas["eua"] < 0.0

    def test_npv_sits_in_a_hand_reasoned_band(self) -> None:
        # Lower bound: NPV > intrinsic (positive time value on an ATM-ish strip).
        # Upper bound: per period the time value of a spread call is below the ATM
        # Black bound 0.4 * F_power * sigma_eff * sqrt(T) <= 0.4*100*0.40*1.0 = 16,
        # so npv < 6*16 + intrinsic < 100 with lots of slack.
        result = price_toll()
        assert TOLL_INTRINSIC < result.npv < 100.0
        assert result.npv == sum(result.per_period_values)
        assert len(result.per_period_values) == len(SIX_PERIODS)

    def test_power_curve_shift_up_10_eur_increases_npv(self) -> None:
        base = price_toll()
        bumped = price_toll(power_prices=tuple(price + 10.0 for price in TOLL_POWER_PRICES))
        assert bumped.npv > base.npv  # long power: value rises with the power curve
        # All six spreads are now ITM by hand: 14.0+10.2+7.8+7.0+11.4+8.6 = 59.0.
        assert bumped.intrinsic_value == pytest.approx(59.0)


# =============================================================================
# Flow 3: portfolio risk with mixed instrument types
# =============================================================================


@dataclass(frozen=True, slots=True)
class _HeatRateOption:
    """An instrument type no built-in pricer knows about (must land in unpriced)."""

    commodity: CommodityConfig
    delivery_period: DeliveryPeriod
    strike: float


FWD_POWER = ForwardContract(
    POWER, JAN, contract_price=85.0, notional=50.0, counterparty="STADTWERKE_X"
)
DUMMY_POSITION = Position(
    _HeatRateOption(TTF, JAN, strike=40.0),  # type: ignore[arg-type]
    position_id="POS-HRO",
)

# Hand-computed anchors for the mixed book:
FWD_POWER_NPV = DF_JAN * (90.0 - 85.0) * 50.0  # 247.5
FWD_POWER_DELTA = DF_JAN * 50.0  # 49.5


def make_mixed_book() -> Portfolio:
    return Portfolio(
        positions=(
            Position(FUT_TTF, position_id="POS-FUT-TTF"),
            Position(FWD_POWER, position_id="POS-FWD-PWR"),
            Position(SWAP_TTF, position_id="POS-SWP-TTF"),
            DUMMY_POSITION,
        ),
        name="mixed-book",
    )


def make_mixed_market_data() -> MarketData:
    return MarketData(
        forward_curves={
            "TTF": make_observed_curve(TTF, (JAN, FEB), (30.0, 32.0)),
            "EEX_PHELIX_DE": make_observed_curve(POWER, (JAN,), (90.0,)),
        },
        discount_curve=make_discount_curve(),
        valuation_date=VALUATION_DATE,
    )


class TestMixedBookPortfolioRiskFlow:
    def test_unregistered_instrument_lands_in_unpriced(self) -> None:
        valuation = value_portfolio(make_mixed_book(), make_mixed_market_data())
        assert valuation.unpriced == (DUMMY_POSITION,)
        assert len(valuation.priced) == 3
        assert valuation.total_npv == pytest.approx(
            FUT_TTF_NPV + FWD_POWER_NPV + SWAP_TTF_NPV  # 198 + 247.5 - 0.25
        )
        assert valuation.total_npv == pytest.approx(445.25)

    def test_aggregate_delta_cells_are_sums_of_position_deltas(self) -> None:
        valuation = value_portfolio(make_mixed_book(), make_mixed_market_data())
        matrix = aggregate_delta(list(valuation.priced))

        assert matrix.commodities == ("EEX_PHELIX_DE", "TTF")
        assert matrix.periods == (JAN, FEB)
        assert matrix.delta_at("TTF", JAN) == pytest.approx(FUT_TTF_DELTA + SWAP_DELTA_JAN)
        assert matrix.delta_at("TTF", FEB) == pytest.approx(SWAP_DELTA_FEB)
        assert matrix.delta_at("EEX_PHELIX_DE", JAN) == pytest.approx(FWD_POWER_DELTA)
        assert matrix.delta_at("EEX_PHELIX_DE", FEB) == 0.0

        # Every grid cell equals the sum of the per-position contributions.
        expected: dict[tuple[str, DeliveryPeriod], float] = {}
        for priced in valuation.priced:
            for key, exposure in priced.delta.items():
                expected[key] = expected.get(key, 0.0) + exposure
        for (commodity_id, period), net in expected.items():
            assert matrix.delta_at(commodity_id, period) == pytest.approx(net)

    def test_gas_crisis_scenario_contributions_sum_to_total(self) -> None:
        # FIX (RiskEngine.apply_scenario price-scaling bug): the built-in scenario
        # catalogue documents its shocks as *relative* fractional moves (e.g. +3.0 =
        # +300 %; see quantvolt.risk.scenarios), so P&L must scale by the position's
        # reference forward price, not just delta * shock. This test used to assert
        # the un-scaled `delta * shock` figures (297.0, 99.0, 296.25); value_portfolio
        # now populates PricedPosition.reference_prices and apply_scenario multiplies
        # by it, giving the figures below instead (Property 23's "dot product of
        # delta with the shock vector" is preserved when "delta" is read as the
        # price-scaled `delta * reference_price`).
        valuation = value_portfolio(make_mixed_book(), make_mixed_market_data())
        result = RiskEngine().apply_scenario(list(valuation.priced), "European Gas Crisis 2022")

        assert result.scenario_name == "European Gas Crisis 2022"
        # Built-in shocks: TTF +300 % (3.0), EEX_PHELIX_DE +200 % (2.0), applied as
        # delta * reference_price * shock:
        #   futures (TTF, JAN):  99.0  * 30.0 * 3.0 = 8910.0
        #   forward (POWER,JAN): 49.5  * 90.0 * 2.0 = 8910.0
        #   swap: 49.5*30.0*3.0 + 49.25*32.0*3.0 = 4455.0 + 4728.0 = 9183.0
        assert result.per_position_pnl == pytest.approx((8910.0, 8910.0, 9183.0))
        assert result.total_pnl == sum(result.per_position_pnl)  # exact (Property 23)
        assert result.total_pnl == pytest.approx(27_003.0)


# =============================================================================
# Flow 4: multi-commodity mark-to-market
# =============================================================================

MTM_DATE = date(2027, 2, 1)

MTM_POWER_JAN = MtMPosition(
    "EEX_PHELIX_DE", JAN, notional=100.0, trade_price=85.0, prior_mark_price=88.0
)
MTM_TTF_JAN = MtMPosition("TTF", JAN, notional=200.0, trade_price=28.0, prior_mark_price=29.5)
MTM_TTF_FEB = MtMPosition("TTF", FEB, notional=150.0, trade_price=31.0, prior_mark_price=31.5)


def make_mtm_book() -> list[MtMPosition]:
    return [MTM_POWER_JAN, MTM_TTF_JAN, MTM_TTF_FEB]


def make_settlements() -> dict[tuple[str, DeliveryPeriod], float]:
    return {("EEX_PHELIX_DE", JAN): 92.5, ("TTF", JAN): 30.25}


def make_mtm_fallback_curve() -> ForwardCurve:
    # Covers TTF FEB (32.0) so the unsettled TTF position marks off the curve.
    return make_observed_curve(TTF, (JAN, FEB), (30.0, 32.0))


class TestMultiCommodityMarkToMarketFlow:
    def test_settled_and_estimated_marks_across_commodities(self) -> None:
        result = mark_to_market(
            make_mtm_book(), MTM_DATE, make_settlements(), make_mtm_fallback_curve()
        )
        assert [r.status for r in result.positions] == ["settled", "settled", "estimated"]
        assert result.estimated_count == 1
        assert [r.current_mark for r in result.positions] == pytest.approx([92.5, 30.25, 32.0])
        # Hand-computed P&L: daily = (mark - prior) * notional;
        #                    cumulative = (mark - trade) * notional.
        power, ttf_jan, ttf_feb = result.positions
        assert power.daily_pnl == pytest.approx((92.5 - 88.0) * 100.0)  # 450.0
        assert power.cumulative_pnl == pytest.approx((92.5 - 85.0) * 100.0)  # 750.0
        assert ttf_jan.daily_pnl == pytest.approx((30.25 - 29.5) * 200.0)  # 150.0
        assert ttf_jan.cumulative_pnl == pytest.approx((30.25 - 28.0) * 200.0)  # 450.0
        assert ttf_feb.daily_pnl == pytest.approx((32.0 - 31.5) * 150.0)  # 75.0
        assert ttf_feb.cumulative_pnl == pytest.approx((32.0 - 31.0) * 150.0)  # 150.0

    def test_position_with_neither_settlement_nor_curve_raises(self) -> None:
        stranded = MtMPosition(
            "EEX_PHELIX_DE", FEB, notional=25.0, trade_price=80.0, prior_mark_price=81.0
        )
        # No power settlement for FEB, and the fallback curve is for TTF, so the
        # position must fail loudly rather than be silently omitted.
        with pytest.raises(NoPricingDataError, match=r"'EEX_PHELIX_DE'.*month=2"):
            mark_to_market(
                [*make_mtm_book(), stranded],
                MTM_DATE,
                make_settlements(),
                make_mtm_fallback_curve(),
            )

    def test_mark_to_market_is_idempotent(self) -> None:
        first = mark_to_market(
            make_mtm_book(), MTM_DATE, make_settlements(), make_mtm_fallback_curve()
        )
        second = mark_to_market(
            make_mtm_book(), MTM_DATE, make_settlements(), make_mtm_fallback_curve()
        )
        assert first == second
        assert first.estimated_count == second.estimated_count


# =============================================================================
# Cross-flow determinism: repeat flow 1 end-to-end, results identical
# =============================================================================


def test_curve_to_risk_flow_is_deterministic_end_to_end() -> None:
    first_valuation, first_risk = run_curve_to_risk_flow()
    second_valuation, second_risk = run_curve_to_risk_flow()
    assert first_valuation == second_valuation
    assert first_risk == second_risk


# --- Flow 5: portfolio-native options + transport right (portfolio-native-pricers spec) ---

FLOW5_PERIOD = DeliveryPeriod(2027, 9)  # settles 2027-09-30
FLOW5_VALUATION_DATE = date(2027, 1, 1)
FLOW5_HUB_A = BUILT_IN_COMMODITIES["EPEX_NL"]
FLOW5_HUB_B = BUILT_IN_COMMODITIES["EPEX_BE"]

FLOW5_TTF_PRICE = 32.0
FLOW5_POWER_PRICE = 95.0
FLOW5_HUB_A_PRICE = 40.0
FLOW5_HUB_B_PRICE = 46.0
FLOW5_SWAP_FIXED = 30.0
FLOW5_FUTURES_PRICE = 88.0
FLOW5_DF = 0.96  # stored exactly at the 2027-09-30 tenor
FLOW5_TTF_SIGMA = 0.35
FLOW5_POWER_SIGMA = 0.42
FLOW5_RHO = 0.45

FLOW5_FUTURES = FuturesContract(
    POWER, FLOW5_PERIOD, contract_price=FLOW5_FUTURES_PRICE, notional=20.0
)
FLOW5_SWAP = SwapContract(
    TTF,
    fixed_rate=FLOW5_SWAP_FIXED,
    floating_index="TTF_DA",
    notional=100.0,
    schedule=DeliverySchedule((FLOW5_PERIOD,)),
)
FLOW5_OPTION = VanillaOptionContract(
    commodity=TTF,
    delivery_period=FLOW5_PERIOD,
    option_type=OptionType.CALL,
    strike=34.0,
    notional=1_000.0,
    side=OptionSide.LONG,
)
FLOW5_SPREAD = SpreadOptionContract(
    commodity_1="EEX_PHELIX_DE",
    commodity_2="TTF",
    delivery_period=FLOW5_PERIOD,
    strike=50.0,
    notional=500.0,
    side=OptionSide.SHORT,
)
FLOW5_TRANSPORT = TransmissionRight(
    origin="EPEX_NL",
    destination="EPEX_BE",
    tariff=2.0,
    quantity=25.0,
    schedule=DeliverySchedule((FLOW5_PERIOD,)),
)


def make_flow5_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=FLOW5_VALUATION_DATE,
        tenors=(FLOW5_PERIOD.last_day,),
        factors=(FLOW5_DF,),
    )


def make_flow5_market_data() -> MarketData:
    return MarketData(
        forward_curves={
            "EEX_PHELIX_DE": make_observed_curve(POWER, (FLOW5_PERIOD,), (FLOW5_POWER_PRICE,)),
            "TTF": make_observed_curve(TTF, (FLOW5_PERIOD,), (FLOW5_TTF_PRICE,)),
            "EPEX_NL": make_observed_curve(FLOW5_HUB_A, (FLOW5_PERIOD,), (FLOW5_HUB_A_PRICE,)),
            "EPEX_BE": make_observed_curve(FLOW5_HUB_B, (FLOW5_PERIOD,), (FLOW5_HUB_B_PRICE,)),
        },
        discount_curve=make_flow5_discount_curve(),
        valuation_date=FLOW5_VALUATION_DATE,
        vol_surfaces={
            "TTF": VolatilitySurface(TTF, (VolatilityTenor(FLOW5_PERIOD, FLOW5_TTF_SIGMA),)),
            "EEX_PHELIX_DE": VolatilitySurface(
                POWER, (VolatilityTenor(FLOW5_PERIOD, FLOW5_POWER_SIGMA),)
            ),
        },
        correlations={("EEX_PHELIX_DE", "TTF"): FLOW5_RHO},
    )


def make_flow5_book() -> Portfolio:
    return Portfolio(
        positions=(
            Position(FLOW5_FUTURES, position_id="POS-FUT"),
            Position(FLOW5_SWAP, position_id="POS-SWP"),
            Position(FLOW5_OPTION, position_id="POS-OPT"),
            Position(FLOW5_SPREAD, position_id="POS-SPR"),
            Position(FLOW5_TRANSPORT, position_id="POS-TRN"),
        ),
        name="native-options-and-transport-book",
    )


class TestPortfolioNativeOptionsAndTransportFlow:
    def test_no_positions_land_in_unpriced(self) -> None:
        valuation = value_portfolio(make_flow5_book(), make_flow5_market_data())
        assert valuation.unpriced == ()
        assert len(valuation.priced) == 5

    def test_each_position_npv_matches_its_direct_kernel_call(self) -> None:
        market_data = make_flow5_market_data()
        valuation = value_portfolio(make_flow5_book(), market_data)

        futures_npv = price_futures(
            FLOW5_FUTURES,
            market_data.curve_for("EEX_PHELIX_DE"),
            FLOW5_VALUATION_DATE,
            market_data.discount_curve,
        ).npv
        swap_npv = price_swap(
            FLOW5_SWAP, market_data.curve_for("TTF"), market_data.discount_curve
        ).npv
        option_result = price_vanilla_option(
            VanillaOptionRequest(
                option_type="call",
                strike=FLOW5_OPTION.strike,
                notional=FLOW5_OPTION.notional,
                forward=FLOW5_TTF_PRICE,
                sigma=FLOW5_TTF_SIGMA,
                time_to_expiry=(FLOW5_PERIOD.last_day - FLOW5_VALUATION_DATE).days / 365.0,
                discount_factor=FLOW5_DF,
            )
        )
        spread_result = price_spread_option(
            SpreadOptionRequest(
                forward1=FLOW5_POWER_PRICE,
                forward2=FLOW5_TTF_PRICE,
                strike=FLOW5_SPREAD.strike,
                sigma1=FLOW5_POWER_SIGMA,
                sigma2=FLOW5_TTF_SIGMA,
                correlation=FLOW5_RHO,
                time_to_expiry=(FLOW5_PERIOD.last_day - FLOW5_VALUATION_DATE).days / 365.0,
                discount_factor=FLOW5_DF,
                notional=FLOW5_SPREAD.notional,
            )
        )
        transport_result = value_transport_right(
            FLOW5_TRANSPORT,
            market_data.curve_for("EPEX_NL"),
            market_data.curve_for("EPEX_BE"),
            market_data.discount_curve,
        )

        assert valuation.priced[0].npv == pytest.approx(futures_npv)
        assert valuation.priced[1].npv == pytest.approx(swap_npv)
        assert valuation.priced[2].npv == pytest.approx(option_result.premium)
        assert valuation.priced[3].npv == pytest.approx(-spread_result.premium)  # SHORT
        assert valuation.priced[4].npv == pytest.approx(transport_result.total)
        assert valuation.total_npv == pytest.approx(
            futures_npv
            + swap_npv
            + option_result.premium
            - spread_result.premium
            + transport_result.total
        )

    def test_deltas_aggregate_across_every_instrument_type(self) -> None:
        valuation = value_portfolio(make_flow5_book(), make_flow5_market_data())
        matrix = aggregate_delta(list(valuation.priced))

        expected: dict[tuple[str, DeliveryPeriod], float] = {}
        for priced in valuation.priced:
            for key, exposure in priced.delta.items():
                expected[key] = expected.get(key, 0.0) + exposure
        for (commodity_id, period), net in expected.items():
            assert matrix.delta_at(commodity_id, period) == pytest.approx(net)
        # The spread option contributes to both legs' cells.
        assert ("EEX_PHELIX_DE", FLOW5_PERIOD) in expected
        assert ("TTF", FLOW5_PERIOD) in expected
