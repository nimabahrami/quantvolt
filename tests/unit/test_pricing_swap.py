"""Unit tests for price_swap (Task 26): NPV, delta, rho, error cases, performance.

Hand-computed two-period fixture (payer-of-fixed / receiver-of-floating):

- reference date 2025-01-01; periods 2025-02 and 2025-03
- settlements: 2025-02-28 (58 days, t = 58/365) and 2025-03-31 (89 days, t = 89/365)
- discount factors at the exact settlement tenors: 0.99 and 0.98
- forwards 52.0 and 47.0; fixed rate 50.0; notional 100.0
- cash flows: (52-50)*100 = 200 and (47-50)*100 = -300
- pv: 0.99*200 = 198 and 0.98*(-300) = -294 -> NPV = -96
- delta: (0.99*100, 0.98*100) = (99, 98)
- rho: (-(58/365)*198 + -(89/365)*(-294)) * 1e-4
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from quantvolt.exceptions import MissingTenorError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import SwapContract
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule
from quantvolt.numerics.daycount import actual_360, actual_365
from quantvolt.pricing.swap import SwapPricingResult, price_swap
from quantvolt.testing import assert_input_unchanged

COMMODITY = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
REFERENCE = date(2025, 1, 1)
FEB = DeliveryPeriod(2025, 2)
MAR = DeliveryPeriod(2025, 3)


def make_swap(fixed_rate: float = 50.0) -> SwapContract:
    return SwapContract(
        commodity=COMMODITY,
        fixed_rate=fixed_rate,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=DeliverySchedule((FEB, MAR)),
    )


def make_forward_curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=COMMODITY,
        market_date=REFERENCE,
        nodes=(CurveNode(FEB, 52.0, "observed"), CurveNode(MAR, 47.0, "observed")),
    )


def make_discount_curve() -> DiscountCurve:
    # Tenors sit exactly on the settlement dates, so the factors are used verbatim.
    return DiscountCurve(
        reference_date=REFERENCE,
        tenors=(date(2025, 2, 28), date(2025, 3, 31)),
        factors=(0.99, 0.98),
    )


def forge_schedule(*periods: DeliveryPeriod) -> DeliverySchedule:
    """Bypass DeliverySchedule's constructor validation.

    A valid schedule cannot carry empty/overlapping periods, so this is the only
    way to exercise price_swap's own defensive boundary guards.
    """
    schedule = object.__new__(DeliverySchedule)
    object.__setattr__(schedule, "periods", periods)
    return schedule


def month_sequence(start_year: int, start_month: int, count: int) -> tuple[DeliveryPeriod, ...]:
    periods: list[DeliveryPeriod] = []
    year, month = start_year, start_month
    for _ in range(count):
        periods.append(DeliveryPeriod(year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(periods)


# --- NPV / delta / rho (hand-computed) ---------------------------------------


def test_two_period_npv_hand_computed() -> None:
    result = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    assert result.npv == pytest.approx(-96.0)


def test_delta_is_discount_factor_times_notional_per_period() -> None:
    result = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    assert result.delta == pytest.approx((0.99 * 100.0, 0.98 * 100.0))


def test_rho_matches_hand_computed_per_bp_formula() -> None:
    result = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    expected = (-(58 / 365) * 198.0 + -(89 / 365) * (-294.0)) * 1e-4
    assert result.rho == pytest.approx(expected)


def test_rho_is_negative_when_every_pv_cash_flow_is_positive() -> None:
    # Receiver-of-floating with all forwards above the fixed rate: positive PVs,
    # so a parallel rate rise shrinks the NPV -> rho < 0.
    result = price_swap(make_swap(fixed_rate=40.0), make_forward_curve(), make_discount_curve())
    assert result.npv > 0.0
    assert result.rho < 0.0


# --- coverage errors (Req 4.4) ------------------------------------------------


def test_delivery_period_missing_from_forward_curve_raises() -> None:
    feb_only = ForwardCurve(
        commodity=COMMODITY,
        market_date=REFERENCE,
        nodes=(CurveNode(FEB, 52.0, "observed"),),
    )
    with pytest.raises(MissingTenorError, match="forward_curve must cover") as excinfo:
        price_swap(make_swap(), feb_only, make_discount_curve())
    assert "DeliveryPeriod(year=2025, month=3)" in str(excinfo.value)


def test_settlement_date_outside_discount_curve_raises() -> None:
    short_curve = DiscountCurve(
        reference_date=REFERENCE, tenors=(date(2025, 2, 28),), factors=(0.99,)
    )
    with pytest.raises(MissingTenorError, match="discount_curve must cover") as excinfo:
        price_swap(make_swap(), make_forward_curve(), short_curve)
    assert "2025-03-31" in str(excinfo.value)


# --- defensive schedule guards (Req 4.1, 4.2) ---------------------------------


def test_empty_schedule_is_impossible_via_the_model() -> None:
    with pytest.raises(ValidationError, match="periods"):
        DeliverySchedule(periods=())


def test_forged_empty_schedule_hits_the_boundary_guard() -> None:
    swap = SwapContract(
        commodity=COMMODITY,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=forge_schedule(),
    )
    with pytest.raises(ValidationError, match=r"swap\.schedule\.periods"):
        price_swap(swap, make_forward_curve(), make_discount_curve())


def test_overlapping_periods_are_impossible_via_the_model() -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        DeliverySchedule(periods=(FEB, FEB))


def test_forged_duplicate_period_rejected_identifying_the_pair() -> None:
    swap = SwapContract(
        commodity=COMMODITY,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=forge_schedule(MAR, FEB, FEB),  # unsorted on purpose: guard must sort
    )
    with pytest.raises(ValidationError, match="overlapping or duplicate") as excinfo:
        price_swap(swap, make_forward_curve(), make_discount_curve())
    message = str(excinfo.value)
    assert "DeliveryPeriod(year=2025, month=2) overlaps DeliveryPeriod(year=2025, month=2)" in (
        message
    )


def test_every_offending_pair_is_reported() -> None:
    may = DeliveryPeriod(2025, 5)
    swap = SwapContract(
        commodity=COMMODITY,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=forge_schedule(FEB, FEB, may, may),
    )
    with pytest.raises(ValidationError) as excinfo:
        price_swap(swap, make_forward_curve(), make_discount_curve())
    message = str(excinfo.value)
    assert message.count("overlaps") == 2
    assert "month=2" in message
    assert "month=5" in message


def test_overlap_guard_fires_before_coverage_checks() -> None:
    # The forged schedule overlaps AND is uncovered by both curves; the ordered
    # validation must raise the overlap ValidationError, not MissingTenorError.
    swap = SwapContract(
        commodity=COMMODITY,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=forge_schedule(DeliveryPeriod(2030, 7), DeliveryPeriod(2030, 7)),
    )
    with pytest.raises(ValidationError, match="overlapping or duplicate"):
        price_swap(swap, make_forward_curve(), make_discount_curve())


# --- performance (Req 4.5), determinism, immutability -------------------------


def make_120_period_setup() -> tuple[SwapContract, ForwardCurve, DiscountCurve]:
    periods = month_sequence(2025, 1, 120)
    swap = SwapContract(
        commodity=COMMODITY,
        fixed_rate=50.0,
        floating_index="TTF_DA",
        notional=100.0,
        schedule=DeliverySchedule(periods),
    )
    forward_curve = ForwardCurve(
        commodity=COMMODITY,
        market_date=date(2024, 12, 31),
        nodes=tuple(
            CurveNode(period, 45.0 + 0.1 * i, "observed") for i, period in enumerate(periods)
        ),
    )
    discount_curve = DiscountCurve(
        reference_date=date(2024, 12, 31),
        tenors=tuple(period.last_day for period in periods),
        factors=tuple(0.999 ** (i + 1) for i in range(len(periods))),
    )
    return swap, forward_curve, discount_curve


def test_120_period_swap_prices_well_under_500ms() -> None:
    swap, forward_curve, discount_curve = make_120_period_setup()
    price_swap(swap, forward_curve, discount_curve)  # warm-up
    start = time.perf_counter()
    result = price_swap(swap, forward_curve, discount_curve)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"120-period swap took {elapsed:.3f}s (budget 0.5s)"
    assert len(result.delta) == 120


def test_identical_inputs_give_identical_results() -> None:
    first = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    second = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    assert first == second  # frozen dataclass equality: npv, delta tuple, and rho
    assert first.npv == second.npv
    assert first.delta == second.delta
    assert first.rho == second.rho


def test_price_swap_does_not_mutate_its_inputs() -> None:
    result = assert_input_unchanged(
        price_swap, make_swap(), make_forward_curve(), make_discount_curve()
    )
    assert isinstance(result, SwapPricingResult)
    assert result.npv == pytest.approx(-96.0)


# --- new keyword-only parameters: day_count, settlement_lag_days, rate_bump ------


def test_new_keyword_defaults_match_hardcoded_behaviour() -> None:
    baseline = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    explicit = price_swap(
        make_swap(),
        make_forward_curve(),
        make_discount_curve(),
        day_count=actual_365,
        settlement_lag_days=0,
        rate_bump=1e-4,
    )
    assert explicit == baseline


def test_day_count_override_changes_rho() -> None:
    baseline = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    with_360 = price_swap(
        make_swap(), make_forward_curve(), make_discount_curve(), day_count=actual_360
    )
    assert with_360.rho != baseline.rho
    # NPV and delta are unaffected by the day-count convention (only rho uses it).
    assert with_360.npv == baseline.npv
    assert with_360.delta == baseline.delta


def test_settlement_lag_days_shifts_discount_lookup() -> None:
    # Shift the discount curve tenors by 2 days so a 2-day lag lands exactly on them.
    lagged_curve = DiscountCurve(
        reference_date=REFERENCE,
        tenors=(date(2025, 3, 2), date(2025, 4, 2)),
        factors=(0.99, 0.98),
    )
    result = price_swap(make_swap(), make_forward_curve(), lagged_curve, settlement_lag_days=2)
    assert result.npv == pytest.approx(-96.0)
    assert result.delta == pytest.approx((0.99 * 100.0, 0.98 * 100.0))


def test_settlement_lag_days_zero_matches_default() -> None:
    baseline = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    explicit = price_swap(
        make_swap(), make_forward_curve(), make_discount_curve(), settlement_lag_days=0
    )
    assert explicit == baseline


def test_settlement_lag_days_negative_rejected() -> None:
    with pytest.raises(ValidationError, match="settlement_lag_days"):
        price_swap(make_swap(), make_forward_curve(), make_discount_curve(), settlement_lag_days=-1)


def test_rate_bump_override_scales_rho() -> None:
    baseline = price_swap(make_swap(), make_forward_curve(), make_discount_curve())
    doubled = price_swap(make_swap(), make_forward_curve(), make_discount_curve(), rate_bump=2e-4)
    assert doubled.rho == pytest.approx(2.0 * baseline.rho)


def test_rate_bump_non_positive_rejected() -> None:
    with pytest.raises(ValidationError, match="rate_bump"):
        price_swap(make_swap(), make_forward_curve(), make_discount_curve(), rate_bump=0.0)
