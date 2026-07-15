"""Unit tests for mark-to-market (Tasks 37-38; Req 10.1-10.5; Properties 25, 26, 27)."""

from __future__ import annotations

import time
from datetime import date

import pytest

from quantvolt.exceptions import NoPricingDataError, ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.mark_to_market import (
    MtMPosition,
    MtMPositionResult,
    MtMResult,
    mark_to_market,
)
from quantvolt.testing import assert_input_unchanged

TTF = BUILT_IN_COMMODITIES["TTF"]
NBP = BUILT_IN_COMMODITIES["NBP"]
MARKET_DATE = date(2025, 7, 14)
AUG = DeliveryPeriod(year=2025, month=8)
SEP = DeliveryPeriod(year=2025, month=9)
OCT = DeliveryPeriod(year=2025, month=10)
NOTIONAL = 100.0
AUG_SETTLEMENT = 55.0
SEP_CURVE_PRICE = 58.25


def make_position(
    commodity_id: str = "TTF",
    period: DeliveryPeriod = AUG,
    notional: float = NOTIONAL,
    trade_price: float = 50.0,
    prior_mark_price: float = 52.0,
) -> MtMPosition:
    return MtMPosition(
        commodity_id=commodity_id,
        delivery_period=period,
        notional=notional,
        trade_price=trade_price,
        prior_mark_price=prior_mark_price,
    )


def make_settlements() -> dict[tuple[str, DeliveryPeriod], float]:
    return {("TTF", AUG): AUG_SETTLEMENT}


def make_ttf_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=TTF,
        market_date=MARKET_DATE,
        nodes=(
            CurveNode(period=AUG, price=57.5, status="observed"),
            CurveNode(period=SEP, price=SEP_CURVE_PRICE, status="observed"),
        ),
    )


# --- settled path (Property 25) -------------------------------------------------


def test_settled_position_hand_computed_pnl() -> None:
    result = mark_to_market([make_position()], MARKET_DATE, make_settlements())
    assert isinstance(result, MtMResult)
    (position_result,) = result.positions
    # daily = (55 - 52) * 100; cumulative = (55 - 50) * 100
    assert position_result.current_mark == pytest.approx(AUG_SETTLEMENT, abs=1e-12)
    assert position_result.daily_pnl == pytest.approx(300.0, abs=1e-10)
    assert position_result.cumulative_pnl == pytest.approx(500.0, abs=1e-10)
    assert position_result.status == "settled"
    assert result.estimated_count == 0


def test_settled_position_with_negative_prices() -> None:
    # Negative energy prices are real: settlement -5, prior mark -2, trade +3.
    settlements: dict[tuple[str, DeliveryPeriod], float] = {("TTF", AUG): -5.0}
    position = make_position(trade_price=3.0, prior_mark_price=-2.0)
    result = mark_to_market([position], MARKET_DATE, settlements)
    (position_result,) = result.positions
    # daily = (-5 - (-2)) * 100 = -300; cumulative = (-5 - 3) * 100 = -800
    assert position_result.current_mark == pytest.approx(-5.0, abs=1e-12)
    assert position_result.daily_pnl == pytest.approx(-300.0, abs=1e-10)
    assert position_result.cumulative_pnl == pytest.approx(-800.0, abs=1e-10)
    assert position_result.status == "settled"


def test_settlement_price_wins_over_forward_curve() -> None:
    # AUG has both a settlement and a curve node: the settlement is used, unflagged.
    result = mark_to_market([make_position()], MARKET_DATE, make_settlements(), make_ttf_curve())
    (position_result,) = result.positions
    assert position_result.current_mark == pytest.approx(AUG_SETTLEMENT, abs=1e-12)
    assert position_result.status == "settled"
    assert result.estimated_count == 0


# --- estimated fallback (Req 10.2) -----------------------------------------------


def test_estimated_fallback_flags_position_and_counts_it() -> None:
    position = make_position(period=SEP)  # no SEP settlement; curve covers SEP
    result = mark_to_market([position], MARKET_DATE, make_settlements(), make_ttf_curve())
    (position_result,) = result.positions
    assert position_result.current_mark == pytest.approx(SEP_CURVE_PRICE, abs=1e-12)
    assert position_result.status == "estimated"
    assert result.estimated_count == 1
    # P&L is computed for estimated marks exactly as for settled ones (Req 10.1).
    assert position_result.daily_pnl == pytest.approx((SEP_CURVE_PRICE - 52.0) * NOTIONAL)
    assert position_result.cumulative_pnl == pytest.approx((SEP_CURVE_PRICE - 50.0) * NOTIONAL)


def test_mixed_book_preserves_input_order_and_counts_estimates() -> None:
    positions = [
        make_position(period=SEP),  # estimated (curve)
        make_position(period=AUG),  # settled
        make_position(period=SEP, trade_price=60.0),  # estimated (curve)
    ]
    result = mark_to_market(positions, MARKET_DATE, make_settlements(), make_ttf_curve())
    assert [r.status for r in result.positions] == ["estimated", "settled", "estimated"]
    assert [r.current_mark for r in result.positions] == pytest.approx(
        [SEP_CURVE_PRICE, AUG_SETTLEMENT, SEP_CURVE_PRICE]
    )
    assert result.positions[2].cumulative_pnl == pytest.approx((SEP_CURVE_PRICE - 60.0) * NOTIONAL)
    assert result.estimated_count == 2


# --- no pricing data (Req 10.3) ---------------------------------------------------


def test_missing_both_raises_error_naming_commodity_and_period() -> None:
    position = make_position(period=OCT)  # no OCT settlement, no curve supplied
    with pytest.raises(NoPricingDataError, match=r"'TTF'.*DeliveryPeriod\(year=2025, month=10\)"):
        mark_to_market([position], MARKET_DATE, make_settlements())


def test_curve_for_different_commodity_does_not_satisfy_fallback() -> None:
    nbp_curve = ForwardCurve(
        commodity=NBP,
        market_date=MARKET_DATE,
        nodes=(CurveNode(period=SEP, price=40.0, status="observed"),),
    )
    position = make_position(period=SEP)  # TTF position; only an NBP curve is given
    with pytest.raises(NoPricingDataError, match="TTF"):
        mark_to_market([position], MARKET_DATE, make_settlements(), nbp_curve)


def test_same_commodity_curve_without_matching_node_raises() -> None:
    # The curve is for TTF but has no OCT node: MissingTenorError inside the
    # fallback means "unavailable", so NoPricingDataError is raised instead.
    position = make_position(period=OCT)
    with pytest.raises(NoPricingDataError, match=r"month=10"):
        mark_to_market([position], MARKET_DATE, make_settlements(), make_ttf_curve())


def test_failing_position_is_never_silently_omitted() -> None:
    # A pricable position before an unpricable one must not yield a partial result.
    positions = [make_position(period=AUG), make_position(period=OCT)]
    with pytest.raises(NoPricingDataError):
        mark_to_market(positions, MARKET_DATE, make_settlements(), make_ttf_curve())


# --- MtMPosition validation -------------------------------------------------------


@pytest.mark.parametrize("bad_notional", [0.0, -100.0])
def test_non_positive_notional_rejected(bad_notional: float) -> None:
    with pytest.raises(ValidationError, match="notional"):
        make_position(notional=bad_notional)


def test_negative_trade_and_prior_mark_prices_are_accepted() -> None:
    position = make_position(trade_price=-3.0, prior_mark_price=-1.5)
    assert position.trade_price == -3.0
    assert position.prior_mark_price == -1.5


def test_result_objects_are_frozen() -> None:
    result = mark_to_market([make_position()], MARKET_DATE, make_settlements())
    with pytest.raises(AttributeError):
        result.estimated_count = 5  # type: ignore[misc]
    with pytest.raises(AttributeError):
        result.positions[0].daily_pnl = 0.0  # type: ignore[misc]


def test_empty_book_yields_empty_result() -> None:
    result = mark_to_market([], MARKET_DATE, make_settlements())
    assert result == MtMResult(positions=(), estimated_count=0)


# --- idempotence (Req 10.5; Property 27) -------------------------------------------


def test_idempotence_identical_inputs_yield_identical_results() -> None:
    positions = [
        make_position(period=AUG),
        make_position(period=SEP, trade_price=-3.0, prior_mark_price=-1.5),
    ]
    first = mark_to_market(positions, MARKET_DATE, make_settlements(), make_ttf_curve())
    second = mark_to_market(positions, MARKET_DATE, make_settlements(), make_ttf_curve())
    assert first == second
    assert first.estimated_count == second.estimated_count
    for a, b in zip(first.positions, second.positions, strict=True):
        assert isinstance(a, MtMPositionResult)
        # Exact equality of every field — no tolerance (Property 27).
        assert a.daily_pnl == b.daily_pnl
        assert a.cumulative_pnl == b.cumulative_pnl
        assert a.current_mark == b.current_mark
        assert a.status == b.status


# --- performance sanity (Req 10.4) --------------------------------------------------


def test_500_position_book_computes_well_within_limit() -> None:
    periods = [
        DeliveryPeriod(year=2025 + offset // 12, month=offset % 12 + 1) for offset in range(24)
    ]
    settlements: dict[tuple[str, DeliveryPeriod], float] = {
        ("TTF", period): 50.0 + index for index, period in enumerate(periods[:12])
    }
    curve = ForwardCurve(
        commodity=TTF,
        market_date=MARKET_DATE,
        nodes=tuple(
            CurveNode(period=period, price=60.0 + index, status="observed")
            for index, period in enumerate(periods[12:])
        ),
    )
    positions = [
        make_position(period=periods[index % 24], notional=10.0 + index) for index in range(500)
    ]
    start = time.perf_counter()
    result = mark_to_market(positions, MARKET_DATE, settlements, curve)
    elapsed = time.perf_counter() - start
    assert len(result.positions) == 500
    expected_estimated = sum(
        1 for position in positions if ("TTF", position.delivery_period) not in settlements
    )
    assert result.estimated_count == expected_estimated
    # Req 10.4 allows 30 s for 500 positions; this should take milliseconds.
    assert elapsed < 5.0


# --- immutability --------------------------------------------------------------------


def test_mark_to_market_does_not_mutate_inputs() -> None:
    positions = [make_position(period=AUG), make_position(period=SEP)]
    result = assert_input_unchanged(
        mark_to_market, positions, MARKET_DATE, make_settlements(), make_ttf_curve()
    )
    assert [r.status for r in result.positions] == ["settled", "estimated"]
    assert result.estimated_count == 1
