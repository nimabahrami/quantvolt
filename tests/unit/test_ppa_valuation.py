"""Unit tests for :mod:`quantvolt.pricing.ppa_valuation`'s ``K_t`` resolution.

Covers the time-weighted ``K_t`` fix (AMENDED 2026-07-19, code review FIX 4):
an ``IndexationStep`` taking effect mid-period must contribute its own
time-weighted share of ``K_t``, not be silently dropped by a first-day-only
anchor.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.ppa import PpaContract, PpaVolumeBasis
from quantvolt.models.ppa_terms import IndexationStep, PpaPriceTerms, PpaTerms
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.ppa_valuation import PpaPeriodVolume, PpaVolumeProfile, price_ppa

_POWER = CommodityConfig("DE_POWER", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh"))
_VALUATION_DATE = date(2026, 1, 1)
_JAN_2026 = DeliveryPeriod(2026, 1)


def _contract(*, price_terms: PpaPriceTerms | None) -> PpaContract:
    return PpaContract(
        contract_id="ppa-kt",
        bidding_zone="DE_POWER",
        fixed_price_per_mwh=50.0,
        start_utc=datetime(2025, 1, 1, tzinfo=UTC),
        end_utc=datetime(2028, 1, 1, tzinfo=UTC),
        volume_basis=PpaVolumeBasis.BASELOAD,
        terms=None if price_terms is None else PpaTerms(price=price_terms),
    )


def test_mid_month_indexation_step_is_time_weighted_into_k_t() -> None:
    # Base 50 stepping to 60 effective Jan 15 2026 (UTC midnight): 14 days at 50,
    # 17 days at 60, over a 31-day January.
    price_terms = PpaPriceTerms(
        indexation=(
            IndexationStep(
                effective_from_utc=datetime(2026, 1, 15, tzinfo=UTC), fixed_price_per_mwh=60.0
            ),
        )
    )
    contract = _contract(price_terms=price_terms)
    profile = PpaVolumeProfile((PpaPeriodVolume(period=_JAN_2026, expected_mwh=100.0),))
    forward_curve = ForwardCurve(
        commodity=_POWER,
        market_date=_VALUATION_DATE,
        nodes=(CurveNode(_JAN_2026, 40.0, "observed"),),
    )
    discount_curve = DiscountCurve(
        reference_date=_VALUATION_DATE, tenors=(_JAN_2026.last_day,), factors=(1.0,)
    )

    result = price_ppa(contract, profile, forward_curve, discount_curve, _VALUATION_DATE)

    # K_t(Jan 2026) = (14/31)*50 + (17/31)*60, exactly rounded to the nearest double.
    expected_k_t = 55.483870967741936
    assert result.per_period[0].forward == 40.0
    assert result.per_period[0].cashflow == pytest.approx(
        100.0 * (expected_k_t - 40.0), rel=0.0, abs=1e-9
    )
    assert result.npv == pytest.approx(100.0 * (expected_k_t - 40.0), rel=0.0, abs=1e-9)


def test_flat_indexation_period_matches_old_point_in_time_result() -> None:
    # No indexation step falls inside the period: the time-weighted average degenerates
    # to the single flat base price, matching the pre-fix point-in-time anchor exactly.
    price_terms = PpaPriceTerms(
        indexation=(
            IndexationStep(
                effective_from_utc=datetime(2027, 6, 1, tzinfo=UTC), fixed_price_per_mwh=90.0
            ),
        )
    )
    contract = _contract(price_terms=price_terms)
    profile = PpaVolumeProfile((PpaPeriodVolume(period=_JAN_2026, expected_mwh=10.0),))
    forward_curve = ForwardCurve(
        commodity=_POWER,
        market_date=_VALUATION_DATE,
        nodes=(CurveNode(_JAN_2026, 40.0, "observed"),),
    )
    discount_curve = DiscountCurve(
        reference_date=_VALUATION_DATE, tenors=(_JAN_2026.last_day,), factors=(1.0,)
    )

    result = price_ppa(contract, profile, forward_curve, discount_curve, _VALUATION_DATE)

    assert result.per_period[0].cashflow == 10.0 * (50.0 - 40.0)
