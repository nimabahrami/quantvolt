"""Unit tests for transmission & pipeline rights (Task 80; Req 24.1-24.5; Properties 67-68).

Covers instrument validation/immutability, the intrinsic payoff and PV (hand-computed,
including loss, tariff and capacity), the spread-option extrinsic decomposition
(total == intrinsic + extrinsic, extrinsic >= 0, engine reuse), bidirectional best-of
selection and subadditivity (Property 68), the both-or-neither vols/correlation contract,
the no-overlap error, input immutability, and portfolio registration of both types with
no regression of the existing DEFAULT_PRICERS entries.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta

import pytest

from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import (
    FuturesContract,
    PipelineRight,
    TransmissionRight,
    TransportDirection,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.portfolio.model import Portfolio, Position
from quantvolt.portfolio.valuation import DEFAULT_PRICERS, MarketData, value_portfolio
from quantvolt.pricing.spread_option import SpreadOptionRequest, price_spread_option
from quantvolt.pricing.transmission_right import (
    TransportRightResult,
    value_transport_right,
)
from quantvolt.testing import assert_input_unchanged

REF = date(2026, 7, 1)
JAN = DeliveryPeriod(2027, 1)  # settles 2027-01-31
FEB = DeliveryPeriod(2027, 2)  # settles 2027-02-28
MAR = DeliveryPeriod(2027, 3)  # settles 2027-03-31
PERIODS = (JAN, FEB, MAR)
SCHEDULE = DeliverySchedule(PERIODS)

# Two distinct liquid hubs. A = origin, B = destination.
ORIGIN = CommodityConfig("HUB_A", "EUR/MWh", Hub("HUB_A", "EEX", "EUR/MWh"))
DEST = CommodityConfig("HUB_B", "EUR/MWh", Hub("HUB_B", "EEX", "EUR/MWh"))

# Discount factors are stored exactly at each period's settlement date, so
# discount_factor(last_day) returns the stored factor with no interpolation.
DF = {JAN: 0.99, FEB: 0.98, MAR: 0.97}


def make_curve(
    commodity: CommodityConfig,
    prices_by_period: dict[DeliveryPeriod, float],
) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=REF,
        nodes=tuple(
            CurveNode(period=period, price=price, status="observed")
            for period, price in sorted(prices_by_period.items())
        ),
    )


def make_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=REF,
        tenors=(JAN.last_day, FEB.last_day, MAR.last_day),
        factors=(DF[JAN], DF[FEB], DF[MAR]),
    )


class TestTransportDirection:
    def test_values(self) -> None:
        assert TransportDirection.A_TO_B == "a_to_b"
        assert TransportDirection.B_TO_A == "b_to_a"
        assert TransportDirection.BIDIRECTIONAL == "bidirectional"

    def test_members(self) -> None:
        assert {d.value for d in TransportDirection} == {"a_to_b", "b_to_a", "bidirectional"}


class TestInstrumentConstruction:
    def test_transmission_right_defaults(self) -> None:
        right = TransmissionRight(
            origin="HUB_A", destination="HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE
        )
        assert right.direction is TransportDirection.A_TO_B
        assert right.loss == 0.0
        assert right.capacity is None
        assert right.reverse_tariff is None

    def test_pipeline_right_defaults(self) -> None:
        right = PipelineRight(
            origin="HUB_A", destination="HUB_B", tariff=1.0, quantity=100.0, schedule=SCHEDULE
        )
        assert right.direction is TransportDirection.A_TO_B
        assert right.loss == 0.0

    def test_zero_quantity_and_zero_tariff_accepted(self) -> None:
        right = TransmissionRight("HUB_A", "HUB_B", tariff=0.0, quantity=0.0, schedule=SCHEDULE)
        assert right.quantity == 0.0
        assert right.tariff == 0.0

    @pytest.mark.parametrize("cls", [TransmissionRight, PipelineRight])
    def test_is_frozen(self, cls: type) -> None:
        right = cls("HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            right.tariff = 6.0  # type: ignore[misc]


class TestInstrumentValidation:
    @pytest.mark.parametrize("cls", [TransmissionRight, PipelineRight])
    def test_negative_quantity_rejected(self, cls: type) -> None:
        with pytest.raises(ValidationError, match="quantity"):
            cls("HUB_A", "HUB_B", tariff=5.0, quantity=-1.0, schedule=SCHEDULE)

    @pytest.mark.parametrize("cls", [TransmissionRight, PipelineRight])
    def test_negative_tariff_rejected(self, cls: type) -> None:
        with pytest.raises(ValidationError, match="tariff"):
            cls("HUB_A", "HUB_B", tariff=-0.5, quantity=10.0, schedule=SCHEDULE)

    @pytest.mark.parametrize("loss", [1.0, 1.5, -0.1])
    def test_loss_outside_unit_interval_rejected(self, loss: float) -> None:
        with pytest.raises(ValidationError, match="loss"):
            TransmissionRight(
                "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE, loss=loss
            )

    def test_loss_just_below_one_accepted(self) -> None:
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE, loss=0.999
        )
        assert right.loss == 0.999

    @pytest.mark.parametrize("capacity", [0.0, -5.0])
    def test_non_positive_capacity_rejected(self, capacity: float) -> None:
        with pytest.raises(ValidationError, match="capacity"):
            TransmissionRight(
                "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE, capacity=capacity
            )

    def test_negative_reverse_tariff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="reverse_tariff"):
            TransmissionRight(
                "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE, reverse_tariff=-1.0
            )


class TestIntrinsic:
    """Property 67: per-period payoff = Q_delivered*max(P_B-P_A-T_AB,0); PV = its discounted sum."""

    def make_inputs(
        self, quantity: float = 10.0, loss: float = 0.0, capacity: float | None = None
    ) -> tuple[TransmissionRight, ForwardCurve, ForwardCurve, DiscountCurve]:
        # Spreads P_B-P_A-T_AB: JAN 55-40-5=+10 (ITM), FEB 52-50-5=-3, MAR 45-60-5=-20.
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 50.0, MAR: 60.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 52.0, MAR: 45.0})
        right = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=quantity,
            schedule=SCHEDULE,
            loss=loss,
            capacity=capacity,
        )
        return right, curve_a, curve_b, make_discount_curve()

    def test_per_period_payoff_and_discounted_pv(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(right, curve_a, curve_b, disc)

        # Only JAN is in the money: payoff = 10 * 10 = 100 (undiscounted).
        jan = result.per_period[0]
        assert jan.period == JAN
        assert jan.payoff == pytest.approx(100.0)
        assert jan.intrinsic == pytest.approx(0.99 * 100.0)  # discounted
        assert jan.direction is TransportDirection.A_TO_B
        # FEB, MAR out of the money: zero payoff, no committed flow.
        assert result.per_period[1].payoff == 0.0
        assert result.per_period[2].payoff == 0.0
        # Aggregate PV = discounted sum over shared periods = 99.0.
        assert result.intrinsic == pytest.approx(99.0)
        assert result.extrinsic == 0.0
        assert result.total == pytest.approx(99.0)

    def test_pv_is_discount_factor_times_payoff_each_period(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(right, curve_a, curve_b, disc)
        for pv in result.per_period:
            assert pv.intrinsic == pytest.approx(pv.discount_factor * pv.payoff)
            assert pv.value == pytest.approx(pv.intrinsic + pv.extrinsic)

    def test_loss_scales_delivered_quantity(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs(loss=0.1)
        result = value_transport_right(right, curve_a, curve_b, disc)
        # delivered = 10 * (1 - 0.1) = 9; JAN PV = 0.99 * 9 * 10 = 89.1.
        assert result.per_period[0].payoff == pytest.approx(90.0)
        assert result.intrinsic == pytest.approx(0.99 * 90.0)

    def test_capacity_caps_quantity(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs(quantity=10.0, capacity=4.0)
        result = value_transport_right(right, curve_a, curve_b, disc)
        # effective = min(10, 4) = 4; JAN PV = 0.99 * 4 * 10 = 39.6.
        assert result.per_period[0].payoff == pytest.approx(40.0)
        assert result.intrinsic == pytest.approx(0.99 * 40.0)

    def test_zero_quantity_is_worthless(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs(quantity=0.0)
        result = value_transport_right(right, curve_a, curve_b, disc)
        assert result.total == 0.0

    def test_delta_signs_opposite_on_the_two_hubs(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(right, curve_a, curve_b, disc)
        # JAN active A->B: long destination (+), short origin (-); magnitude = DF*delivered.
        assert result.per_period[0].delta_destination == pytest.approx(0.99 * 10.0)
        assert result.per_period[0].delta_origin == pytest.approx(-0.99 * 10.0)
        assert result.delta_destination == pytest.approx(-result.delta_origin)

    def test_negative_prices_handled_on_intrinsic_path(self) -> None:
        # Negative power prices are real; intrinsic must still compute (no lognormal needed).
        curve_a = make_curve(ORIGIN, {JAN: -20.0})
        curve_b = make_curve(DEST, {JAN: -5.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=3.0, quantity=2.0, schedule=DeliverySchedule((JAN,))
        )
        result = value_transport_right(right, curve_a, curve_b, make_discount_curve())
        # spread = -5 - (-20) - 3 = 12 > 0; payoff = 2 * 12 = 24.
        assert result.per_period[0].payoff == pytest.approx(24.0)
        assert result.intrinsic == pytest.approx(0.99 * 24.0)

    def test_direction_b_to_a_uses_reverse_flow(self) -> None:
        # B->A right at its own tariff: payoff = max(P_A - P_B - T, 0).
        curve_a = make_curve(ORIGIN, {JAN: 60.0})
        curve_b = make_curve(DEST, {JAN: 45.0})
        right = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=DeliverySchedule((JAN,)),
            direction=TransportDirection.B_TO_A,
        )
        result = value_transport_right(right, curve_a, curve_b, make_discount_curve())
        # spread = 60 - 45 - 5 = 10; payoff = 100; PV = 99.
        assert result.per_period[0].payoff == pytest.approx(100.0)
        assert result.per_period[0].direction is TransportDirection.B_TO_A
        # B->A active: holder is long the ORIGIN (buys at B, sells at A) -> origin delta +.
        assert result.per_period[0].delta_origin == pytest.approx(0.99 * 10.0)
        assert result.per_period[0].delta_destination == pytest.approx(-0.99 * 10.0)


class TestExtrinsic:
    """Req 24.2: spread-option extrinsic value with strike = T_AB."""

    def make_inputs(self) -> tuple[TransmissionRight, ForwardCurve, ForwardCurve, DiscountCurve]:
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 50.0, MAR: 60.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 52.0, MAR: 45.0})
        right = TransmissionRight("HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE)
        return right, curve_a, curve_b, make_discount_curve()

    def test_total_equals_intrinsic_plus_extrinsic(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(
            right, curve_a, curve_b, disc, vols=(0.30, 0.35), correlation=0.5
        )
        assert result.total == pytest.approx(result.intrinsic + result.extrinsic)

    def test_extrinsic_is_non_negative(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(
            right, curve_a, curve_b, disc, vols=(0.30, 0.35), correlation=0.5
        )
        assert result.extrinsic > 0.0
        for pv in result.per_period:
            assert pv.extrinsic >= -1e-9

    def test_per_period_total_matches_spread_option_engine(self) -> None:
        # Prove reuse of the spread-option engine: forward1=P_B, forward2=P_A, strike=T_AB.
        right, curve_a, curve_b, disc = self.make_inputs()
        vols, rho = (0.30, 0.35), 0.5
        result = value_transport_right(right, curve_a, curve_b, disc, vols=vols, correlation=rho)

        from quantvolt.numerics.daycount import actual_365

        prices_a = {JAN: 40.0, FEB: 50.0, MAR: 60.0}
        prices_b = {JAN: 55.0, FEB: 52.0, MAR: 45.0}
        for pv in result.per_period:
            expected = price_spread_option(
                SpreadOptionRequest(
                    forward1=prices_b[pv.period],
                    forward2=prices_a[pv.period],
                    strike=5.0,
                    sigma1=vols[1],  # destination
                    sigma2=vols[0],  # origin
                    correlation=rho,
                    time_to_expiry=actual_365(REF, pv.period.last_day),
                    discount_factor=DF[pv.period],
                    notional=10.0,
                )
            )
            assert pv.value == pytest.approx(expected.premium)
            assert pv.delta_destination == pytest.approx(expected.delta1)
            assert pv.delta_origin == pytest.approx(expected.delta2)

    def test_extrinsic_exceeds_intrinsic_only_value(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        intrinsic_only = value_transport_right(right, curve_a, curve_b, disc)
        with_option = value_transport_right(
            right, curve_a, curve_b, disc, vols=(0.30, 0.35), correlation=0.5
        )
        assert with_option.total > intrinsic_only.total
        assert with_option.intrinsic == pytest.approx(intrinsic_only.total)


class TestBidirectional:
    """Req 24.3 & Property 68: best-of per period, subadditive vs two one-way rights."""

    def test_per_period_picks_best_direction_or_no_flow(self) -> None:
        # P1 favours A->B, P2 favours B->A, P3 favours neither.
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 60.0, MAR: 50.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 45.0, MAR: 51.0})
        right = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=SCHEDULE,
            direction=TransportDirection.BIDIRECTIONAL,
            reverse_tariff=5.0,
        )
        result = value_transport_right(right, curve_a, curve_b, make_discount_curve())

        assert result.per_period[0].direction is TransportDirection.A_TO_B
        assert result.per_period[0].payoff == pytest.approx(100.0)  # 10*(55-40-5)
        assert result.per_period[1].direction is TransportDirection.B_TO_A
        assert result.per_period[1].payoff == pytest.approx(100.0)  # 10*(60-45-5)
        assert result.per_period[2].direction is None  # no-flow
        assert result.per_period[2].value == 0.0
        # Aggregate intrinsic PV = 0.99*100 + 0.98*100 + 0 = 197.0.
        assert result.intrinsic == pytest.approx(197.0)

    def test_bidirectional_intrinsic_delta_follows_active_direction(self) -> None:
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 60.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 45.0})
        right = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=DeliverySchedule((JAN, FEB)),
            direction=TransportDirection.BIDIRECTIONAL,
        )
        result = value_transport_right(right, curve_a, curve_b, make_discount_curve())
        # P1 A->B: origin short (-), destination long (+).
        assert result.per_period[0].delta_origin == pytest.approx(-0.99 * 10.0)
        assert result.per_period[0].delta_destination == pytest.approx(0.99 * 10.0)
        # P2 B->A: origin long (+), destination short (-).
        assert result.per_period[1].delta_origin == pytest.approx(0.98 * 10.0)
        assert result.per_period[1].delta_destination == pytest.approx(-0.98 * 10.0)

    def test_intrinsic_bidirectional_equals_sum_of_directionals(self) -> None:
        # Directional payoffs are mutually exclusive per period, so intrinsically the
        # bound in Property 68 is tight (equality).
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 60.0, MAR: 50.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 45.0, MAR: 51.0})
        disc = make_discount_curve()
        bidir = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=SCHEDULE,
            direction=TransportDirection.BIDIRECTIONAL,
            reverse_tariff=5.0,
        )
        ab = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=SCHEDULE,
            direction=TransportDirection.A_TO_B,
        )
        ba = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=5.0,
            quantity=10.0,
            schedule=SCHEDULE,
            direction=TransportDirection.B_TO_A,
        )
        total_bidir = value_transport_right(bidir, curve_a, curve_b, disc).total
        total_ab = value_transport_right(ab, curve_a, curve_b, disc).total
        total_ba = value_transport_right(ba, curve_a, curve_b, disc).total
        assert total_bidir == pytest.approx(total_ab + total_ba)

    def test_subadditivity_strict_when_both_directions_carry_option_value(self) -> None:
        # Near-ATM both ways so both directional options have positive time value.
        curve_a = make_curve(ORIGIN, {JAN: 50.0, FEB: 50.0})
        curve_b = make_curve(DEST, {JAN: 51.0, FEB: 49.0})
        disc = make_discount_curve()
        schedule = DeliverySchedule((JAN, FEB))
        vols, rho = (0.5, 0.5), 0.2

        bidir = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=2.0,
            quantity=10.0,
            schedule=schedule,
            direction=TransportDirection.BIDIRECTIONAL,
            reverse_tariff=2.0,
        )
        ab = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=2.0,
            quantity=10.0,
            schedule=schedule,
            direction=TransportDirection.A_TO_B,
        )
        ba = TransmissionRight(
            "HUB_A",
            "HUB_B",
            tariff=2.0,
            quantity=10.0,
            schedule=schedule,
            direction=TransportDirection.B_TO_A,
        )
        r_bidir = value_transport_right(bidir, curve_a, curve_b, disc, vols=vols, correlation=rho)
        r_ab = value_transport_right(ab, curve_a, curve_b, disc, vols=vols, correlation=rho)
        r_ba = value_transport_right(ba, curve_a, curve_b, disc, vols=vols, correlation=rho)

        assert r_bidir.total > 0.0
        # Subadditivity (Property 68), strict because both directions have option value.
        assert r_bidir.total < r_ab.total + r_ba.total
        # And each period's bidirectional value is the max of the two directional values.
        for pv_bidir, pv_ab, pv_ba in zip(
            r_bidir.per_period, r_ab.per_period, r_ba.per_period, strict=True
        ):
            assert pv_bidir.value == pytest.approx(max(pv_ab.value, pv_ba.value))


class TestVolsCorrelationContract:
    """Req 24.2: vols and correlation must be supplied both-or-neither."""

    def make_inputs(self) -> tuple[TransmissionRight, ForwardCurve, ForwardCurve, DiscountCurve]:
        curve_a = make_curve(ORIGIN, {JAN: 40.0})
        curve_b = make_curve(DEST, {JAN: 55.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN,))
        )
        return right, curve_a, curve_b, make_discount_curve()

    def test_vols_without_correlation_raises(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        with pytest.raises(ValidationError, match="vols and correlation"):
            value_transport_right(right, curve_a, curve_b, disc, vols=(0.3, 0.3))

    def test_correlation_without_vols_raises(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        with pytest.raises(ValidationError, match="vols and correlation"):
            value_transport_right(right, curve_a, curve_b, disc, correlation=0.5)

    def test_neither_gives_intrinsic_only(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        result = value_transport_right(right, curve_a, curve_b, disc)
        assert result.extrinsic == 0.0


class TestCurveMismatchAndOverlap:
    def test_no_shared_period_raises_naming_both_commodities(self) -> None:
        # curve_a has only JAN, curve_b has only FEB -> no shared schedule period.
        curve_a = make_curve(ORIGIN, {JAN: 40.0})
        curve_b = make_curve(DEST, {FEB: 55.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN, FEB))
        )
        with pytest.raises(InsufficientDataError) as excinfo:
            value_transport_right(right, curve_a, curve_b, make_discount_curve())
        message = str(excinfo.value)
        assert "'HUB_A'" in message
        assert "'HUB_B'" in message

    def test_origin_curve_mismatch_raises(self) -> None:
        curve_a = make_curve(DEST, {JAN: 40.0})  # wrong commodity passed as curve_a
        curve_b = make_curve(DEST, {JAN: 55.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN,))
        )
        with pytest.raises(ValidationError, match="curve_a"):
            value_transport_right(right, curve_a, curve_b, make_discount_curve())

    def test_destination_curve_mismatch_raises(self) -> None:
        curve_a = make_curve(ORIGIN, {JAN: 40.0})
        curve_b = make_curve(ORIGIN, {JAN: 55.0})  # wrong commodity passed as curve_b
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN,))
        )
        with pytest.raises(ValidationError, match="curve_b"):
            value_transport_right(right, curve_a, curve_b, make_discount_curve())


class TestImmutability:
    def test_intrinsic_inputs_not_mutated(self) -> None:
        curve_a = make_curve(ORIGIN, {JAN: 40.0, FEB: 50.0})
        curve_b = make_curve(DEST, {JAN: 55.0, FEB: 52.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN, FEB))
        )
        result = assert_input_unchanged(
            value_transport_right, right, curve_a, curve_b, make_discount_curve()
        )
        assert isinstance(result, TransportRightResult)

    def test_extrinsic_inputs_not_mutated(self) -> None:
        curve_a = make_curve(ORIGIN, {JAN: 40.0})
        curve_b = make_curve(DEST, {JAN: 55.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN,))
        )
        result = assert_input_unchanged(
            value_transport_right,
            right,
            curve_a,
            curve_b,
            make_discount_curve(),
            vols=(0.3, 0.35),
            correlation=0.5,
        )
        assert result.total > 0.0


class TestPortfolioRegistration:
    """Task 80 / Req 24: both rights price through value_portfolio; no regression."""

    def make_market_data(self) -> MarketData:
        return MarketData(
            forward_curves={
                "HUB_A": make_curve(ORIGIN, {JAN: 40.0, FEB: 50.0, MAR: 60.0}),
                "HUB_B": make_curve(DEST, {JAN: 55.0, FEB: 52.0, MAR: 45.0}),
                "TTF": ForwardCurve(
                    commodity=CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE", "EUR/MWh")),
                    market_date=REF,
                    nodes=(CurveNode(JAN, 35.0, "observed"),),
                ),
            },
            discount_curve=make_discount_curve(),
            valuation_date=REF,
        )

    def test_both_rights_registered_in_default_pricers(self) -> None:
        assert TransmissionRight in DEFAULT_PRICERS
        assert PipelineRight in DEFAULT_PRICERS

    def test_transmission_and_pipeline_priced_through_portfolio(self) -> None:
        transmission = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE
        )
        pipeline = PipelineRight("HUB_A", "HUB_B", tariff=5.0, quantity=2.0, schedule=SCHEDULE)
        portfolio = Portfolio(
            positions=(
                Position(transmission, position_id="POS-TR"),  # type: ignore[arg-type]
                Position(pipeline, position_id="POS-PL"),  # type: ignore[arg-type]
            )
        )
        market_data = self.make_market_data()
        valuation = value_portfolio(portfolio, market_data)

        assert valuation.unpriced == ()
        assert len(valuation.priced) == 2

        # NPV of each priced position matches value_transport_right directly.
        tr_direct = value_transport_right(
            transmission,
            market_data.curve_for("HUB_A"),
            market_data.curve_for("HUB_B"),
            market_data.discount_curve,
        )
        assert valuation.priced[0].npv == pytest.approx(tr_direct.total)
        assert valuation.priced[0].npv == pytest.approx(99.0)  # 10 * 0.99 * 10

        # Delta carries opposite-signed entries on the two hubs for the JAN period.
        delta = valuation.priced[0].delta
        assert delta[("HUB_B", JAN)] == pytest.approx(0.99 * 10.0)
        assert delta[("HUB_A", JAN)] == pytest.approx(-0.99 * 10.0)

        # Pipeline (quantity 2) is one fifth of the transmission value.
        assert valuation.priced[1].npv == pytest.approx(0.99 * 2.0 * 10.0)

    def test_reference_prices_populated_for_both_hubs(self) -> None:
        """Regression: reference_prices feeds RiskEngine.apply_scenario's
        `delta * reference_price * shock` scaling (fix for the gas-crisis stress bug)."""
        transmission = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE
        )
        portfolio = Portfolio(positions=(Position(transmission),))  # type: ignore[arg-type]
        market_data = self.make_market_data()
        valuation = value_portfolio(portfolio, market_data)

        reference_prices = valuation.priced[0].reference_prices
        assert reference_prices[("HUB_A", JAN)] == pytest.approx(40.0)
        assert reference_prices[("HUB_B", JAN)] == pytest.approx(55.0)
        assert set(reference_prices) == set(valuation.priced[0].delta)

    def test_existing_pricers_still_work_no_regression(self) -> None:
        # A transport right plus a futures contract in one book: both price.
        transmission = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE
        )
        futures = FuturesContract(
            CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE", "EUR/MWh")),
            JAN,
            contract_price=30.0,
            notional=100.0,
        )
        portfolio = Portfolio(
            positions=(
                Position(futures),
                Position(transmission, position_id="POS-TR"),  # type: ignore[arg-type]
            )
        )
        valuation = value_portfolio(portfolio, self.make_market_data())
        assert valuation.unpriced == ()
        assert len(valuation.priced) == 2
        # Futures NPV = 0.99 * (35 - 30) * 100 = 495.0 (unchanged behaviour).
        assert valuation.priced[0].npv == pytest.approx(495.0)
        assert valuation.priced[1].npv == pytest.approx(99.0)

    def test_portfolio_inputs_not_mutated(self) -> None:
        transmission = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=SCHEDULE
        )
        portfolio = Portfolio(
            positions=(Position(transmission),)  # type: ignore[arg-type]
        )
        valuation = assert_input_unchanged(value_portfolio, portfolio, self.make_market_data())
        assert valuation.total_npv == pytest.approx(99.0)


class TestNewKeywordParameters:
    """New keyword-only day_count / settlement_lag_days on value_transport_right."""

    def make_inputs(self) -> tuple[TransmissionRight, ForwardCurve, ForwardCurve, DiscountCurve]:
        curve_a = make_curve(ORIGIN, {JAN: 40.0})
        curve_b = make_curve(DEST, {JAN: 55.0})
        right = TransmissionRight(
            "HUB_A", "HUB_B", tariff=5.0, quantity=10.0, schedule=DeliverySchedule((JAN,))
        )
        return right, curve_a, curve_b, make_discount_curve()

    def test_defaults_match_hardcoded_behaviour(self) -> None:
        from quantvolt.numerics.daycount import actual_365

        right, curve_a, curve_b, disc = self.make_inputs()
        baseline = value_transport_right(right, curve_a, curve_b, disc)
        explicit = value_transport_right(
            right, curve_a, curve_b, disc, day_count=actual_365, settlement_lag_days=0
        )
        assert explicit == baseline

    def test_day_count_override_changes_extrinsic_value(self) -> None:
        from quantvolt.numerics.daycount import actual_360

        right, curve_a, curve_b, disc = self.make_inputs()
        baseline = value_transport_right(
            right, curve_a, curve_b, disc, vols=(0.30, 0.35), correlation=0.5
        )
        with_360 = value_transport_right(
            right, curve_a, curve_b, disc, vols=(0.30, 0.35), correlation=0.5, day_count=actual_360
        )
        assert with_360.extrinsic != baseline.extrinsic
        # Intrinsic value has no time-to-expiry dependence, so it is unaffected.
        assert with_360.intrinsic == pytest.approx(baseline.intrinsic)

    def test_settlement_lag_days_shifts_discount_lookup(self) -> None:
        right, curve_a, curve_b, _ = self.make_inputs()
        # Shift the discount tenor by 2 days so a 2-day lag lands exactly on it.
        lagged_curve = DiscountCurve(
            reference_date=REF, tenors=(date(2027, 2, 2),), factors=(0.99,)
        )
        result = value_transport_right(right, curve_a, curve_b, lagged_curve, settlement_lag_days=2)
        assert result.per_period[0].payoff == pytest.approx(100.0)
        assert result.intrinsic == pytest.approx(0.99 * 100.0)

    def test_settlement_lag_days_negative_rejected(self) -> None:
        right, curve_a, curve_b, disc = self.make_inputs()
        with pytest.raises(ValidationError, match="settlement_lag_days"):
            value_transport_right(right, curve_a, curve_b, disc, settlement_lag_days=-1)

    def test_settlement_lag_days_shifts_extrinsic_discount_factor_only(self) -> None:
        """On the option (extrinsic) path, ``settlement_lag_days`` changes the total
        only via the discount factor (regression for the T-inflation bug: the lagged
        settlement date must NOT leak into ``time_to_expiry``).
        """
        right, curve_a, curve_b, _ = self.make_inputs()
        curve = DiscountCurve(
            reference_date=REF, tenors=(date(2027, 1, 31), date(2027, 3, 3)), factors=(0.95, 0.80)
        )
        baseline = value_transport_right(
            right, curve_a, curve_b, curve, vols=(0.30, 0.35), correlation=0.5
        )
        lag_days = 30
        lagged = value_transport_right(
            right,
            curve_a,
            curve_b,
            curve,
            vols=(0.30, 0.35),
            correlation=0.5,
            settlement_lag_days=lag_days,
        )
        assert lagged.total != pytest.approx(baseline.total)
        base_factor = curve.discount_factor(JAN.last_day)
        lag_factor = curve.discount_factor(JAN.last_day + timedelta(days=lag_days))
        assert lagged.total == pytest.approx(baseline.total * lag_factor / base_factor, rel=1e-9)

    def test_settlement_lag_days_with_flat_curve_does_not_change_extrinsic(self) -> None:
        """Regression: on a FLAT discount curve, ``settlement_lag_days`` must leave the
        extrinsic (option time) value unchanged. The only economic channel for the lag
        is the discount factor, constant on a flat curve; if the lagged settlement date
        instead leaked into ``time_to_expiry`` (the original bug), extrinsic value would
        change even here.
        """
        right, curve_a, curve_b, _ = self.make_inputs()
        flat_curve = DiscountCurve(
            reference_date=REF, tenors=(date(2027, 1, 31), date(2027, 3, 3)), factors=(0.9, 0.9)
        )
        baseline = value_transport_right(
            right, curve_a, curve_b, flat_curve, vols=(0.30, 0.35), correlation=0.5
        )
        lagged = value_transport_right(
            right,
            curve_a,
            curve_b,
            flat_curve,
            vols=(0.30, 0.35),
            correlation=0.5,
            settlement_lag_days=30,
        )
        assert lagged.total == pytest.approx(baseline.total)
        assert lagged.extrinsic == pytest.approx(baseline.extrinsic)
