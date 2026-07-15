"""Unit tests for futures/forward pricing (Task 25; Req 3.1-3.4; Properties 10, 11)."""

from __future__ import annotations

from datetime import date

import pytest

from quantvolt.exceptions import ExpiredContractError, MissingTenorError, ValidationError
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import ForwardContract, FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.futures import FuturesPricingResult, futures_delta, price_futures
from quantvolt.testing import assert_input_unchanged

COMMODITY = BUILT_IN_COMMODITIES["TTF"]
VALUATION_DATE = date(2025, 1, 15)
JUNE = DeliveryPeriod(year=2025, month=6)  # settles 2025-06-30
FORWARD_PRICE = 55.0
CONTRACT_PRICE = 50.0
NOTIONAL = 100.0
JUNE_DF = 0.98  # stored exactly at the 2025-06-30 tenor below


def make_forward_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=COMMODITY,
        market_date=VALUATION_DATE,
        nodes=(
            CurveNode(period=JUNE, price=FORWARD_PRICE, status="observed"),
            CurveNode(period=DeliveryPeriod(year=2025, month=7), price=56.0, status="observed"),
        ),
    )


def make_discount_curve() -> DiscountCurve:
    return DiscountCurve(
        reference_date=date(2025, 1, 1),
        tenors=(date(2025, 1, 31), date(2025, 6, 30), date(2025, 12, 31)),
        factors=(0.999, JUNE_DF, 0.96),
    )


def make_futures(period: DeliveryPeriod = JUNE) -> FuturesContract:
    return FuturesContract(
        commodity=COMMODITY,
        delivery_period=period,
        contract_price=CONTRACT_PRICE,
        notional=NOTIONAL,
    )


def price_june() -> FuturesPricingResult:
    return price_futures(
        make_futures(), make_forward_curve(), VALUATION_DATE, make_discount_curve()
    )


def delta_june(bump: float = 1.0) -> float:
    return futures_delta(
        make_futures(), make_forward_curve(), VALUATION_DATE, make_discount_curve(), bump=bump
    )


# --- NPV (Property 10) --------------------------------------------------------


def test_npv_matches_hand_computed_value() -> None:
    result = price_june()
    # df(settlement) * (F - K) * notional = 0.98 * (55 - 50) * 100
    assert result.npv == pytest.approx(0.98 * 5.0 * 100.0, abs=1e-10)
    assert result.npv == pytest.approx(490.0, abs=1e-10)


def test_result_is_frozen_result_object() -> None:
    result = price_june()
    assert isinstance(result, FuturesPricingResult)
    with pytest.raises(AttributeError):
        result.npv = 0.0  # type: ignore[misc]


def test_negative_npv_when_contract_price_exceeds_forward() -> None:
    contract = FuturesContract(
        commodity=COMMODITY, delivery_period=JUNE, contract_price=60.0, notional=NOTIONAL
    )
    result = price_futures(contract, make_forward_curve(), VALUATION_DATE, make_discount_curve())
    assert result.npv == pytest.approx(0.98 * (55.0 - 60.0) * 100.0, abs=1e-10)


def test_forward_contract_is_accepted_and_prices_identically() -> None:
    forward = ForwardContract(
        commodity=COMMODITY,
        delivery_period=JUNE,
        contract_price=CONTRACT_PRICE,
        notional=NOTIONAL,
        counterparty="ACME Energy BV",
    )
    result = price_futures(forward, make_forward_curve(), VALUATION_DATE, make_discount_curve())
    assert result == price_june()


def test_settlement_on_valuation_date_is_not_expired() -> None:
    # Delivery ends exactly on the valuation date: not *strictly* before, so it prices.
    january = DeliveryPeriod(year=2025, month=1)
    curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=date(2025, 1, 31),
        nodes=(CurveNode(period=january, price=52.0, status="observed"),),
    )
    result = price_futures(make_futures(january), curve, date(2025, 1, 31), make_discount_curve())
    assert result.npv == pytest.approx(0.999 * (52.0 - 50.0) * 100.0, abs=1e-10)


# --- delta --------------------------------------------------------------------


def test_delta_equals_discount_factor_times_notional() -> None:
    assert delta_june() == pytest.approx(JUNE_DF * NOTIONAL, abs=1e-10)


@pytest.mark.parametrize("bump", [0.5, 1.0, 10.0, 100.0])
def test_delta_is_exact_for_any_bump_size(bump: float) -> None:
    # NPV is linear in the forward price, so the central difference is bump-invariant
    # (bumps of order one and above; far smaller bumps only add float cancellation noise).
    assert delta_june(bump=bump) == pytest.approx(JUNE_DF * NOTIONAL, abs=1e-10)


def test_result_delta_matches_futures_delta() -> None:
    assert price_june().delta == delta_june()


@pytest.mark.parametrize("bad_bump", [0.0, -1.0])
def test_non_positive_bump_rejected(bad_bump: float) -> None:
    with pytest.raises(ValidationError, match="bump"):
        delta_june(bump=bad_bump)


# --- expired contracts (Property 11) -------------------------------------------


def test_expired_contract_raises_naming_period_and_valuation_date() -> None:
    december_2024 = DeliveryPeriod(year=2024, month=12)  # ended 2024-12-31 < valuation
    with pytest.raises(ExpiredContractError, match=r"2024-12-31.*2025-01-15"):
        price_futures(
            make_futures(december_2024), make_forward_curve(), VALUATION_DATE, make_discount_curve()
        )


def test_expired_check_precedes_curve_lookups() -> None:
    # The expired period is absent from both curves; ExpiredContractError must still
    # win because validation happens before any computation (Property 11).
    december_2024 = DeliveryPeriod(year=2024, month=12)
    with pytest.raises(ExpiredContractError):
        price_futures(
            make_futures(december_2024), make_forward_curve(), VALUATION_DATE, make_discount_curve()
        )


def test_futures_delta_also_rejects_expired_contract() -> None:
    december_2024 = DeliveryPeriod(year=2024, month=12)
    with pytest.raises(ExpiredContractError):
        futures_delta(
            make_futures(december_2024), make_forward_curve(), VALUATION_DATE, make_discount_curve()
        )


# --- missing tenors (Req 3.4) ---------------------------------------------------


def test_missing_forward_curve_period_propagates_missing_tenor_error() -> None:
    september = DeliveryPeriod(year=2025, month=9)  # not on the forward curve
    with pytest.raises(MissingTenorError, match="no forward-curve node"):
        price_futures(
            make_futures(september), make_forward_curve(), VALUATION_DATE, make_discount_curve()
        )


def test_uncovered_discount_tenor_propagates_missing_tenor_error() -> None:
    june_2026 = DeliveryPeriod(year=2026, month=6)  # settles past the last discount tenor
    curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(period=june_2026, price=54.0, status="observed"),),
    )
    with pytest.raises(MissingTenorError, match="outside the covered range"):
        price_futures(make_futures(june_2026), curve, VALUATION_DATE, make_discount_curve())


def test_uncovered_discount_tenor_propagates_from_futures_delta() -> None:
    june_2026 = DeliveryPeriod(year=2026, month=6)
    curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=VALUATION_DATE,
        nodes=(CurveNode(period=june_2026, price=54.0, status="observed"),),
    )
    with pytest.raises(MissingTenorError, match="outside the covered range"):
        futures_delta(make_futures(june_2026), curve, VALUATION_DATE, make_discount_curve())


# --- immutability ----------------------------------------------------------------


def test_price_futures_does_not_mutate_inputs() -> None:
    result = assert_input_unchanged(
        price_futures,
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        make_discount_curve(),
    )
    assert result.npv == pytest.approx(490.0, abs=1e-10)


def test_futures_delta_does_not_mutate_inputs() -> None:
    delta = assert_input_unchanged(
        futures_delta,
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        make_discount_curve(),
        bump=2.0,
    )
    assert delta == pytest.approx(JUNE_DF * NOTIONAL, abs=1e-10)


# --- settlement_lag_days (new keyword-only parameter) ---------------------------


def test_settlement_lag_days_default_matches_hardcoded_behaviour() -> None:
    baseline = price_june()
    explicit = price_futures(
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        make_discount_curve(),
        settlement_lag_days=0,
    )
    assert explicit == baseline
    assert delta_june() == futures_delta(
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        make_discount_curve(),
        settlement_lag_days=0,
    )


def test_settlement_lag_days_shifts_discount_lookup_for_price_and_delta() -> None:
    # Shift the discount tenors 3 days so a 3-day lag lands exactly on the shifted date.
    lagged_curve = DiscountCurve(
        reference_date=date(2025, 1, 1),
        tenors=(date(2025, 1, 31), date(2025, 7, 3), date(2025, 12, 31)),
        factors=(0.999, JUNE_DF, 0.96),
    )
    result = price_futures(
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        lagged_curve,
        settlement_lag_days=3,
    )
    assert result.npv == pytest.approx(0.98 * 5.0 * 100.0, abs=1e-10)
    delta = futures_delta(
        make_futures(),
        make_forward_curve(),
        VALUATION_DATE,
        lagged_curve,
        settlement_lag_days=3,
    )
    assert delta == pytest.approx(JUNE_DF * NOTIONAL, abs=1e-10)
    assert result.delta == delta  # price and delta agree on the same lag


def test_settlement_lag_days_negative_rejected() -> None:
    with pytest.raises(ValidationError, match="settlement_lag_days"):
        price_futures(
            make_futures(),
            make_forward_curve(),
            VALUATION_DATE,
            make_discount_curve(),
            settlement_lag_days=-1,
        )
    with pytest.raises(ValidationError, match="settlement_lag_days"):
        futures_delta(
            make_futures(),
            make_forward_curve(),
            VALUATION_DATE,
            make_discount_curve(),
            settlement_lag_days=-1,
        )
