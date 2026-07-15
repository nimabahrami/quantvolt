"""Unit tests for assets/long_dated.py (Task 76): long-dated / projected-spot governance.

Validates Requirements 23.1-23.4 and Correctness Property 66 (projected-spot tagging,
VaR inapplicability, and the storable-only furthest-forward lower bound refused for power).
"""

from __future__ import annotations

from datetime import date

import pytest

from quantvolt.assets.long_dated import (
    BenchmarkResult,
    CorporatePremium,
    LowerBoundResult,
    ValuationSource,
    VarApplicabilityVerdict,
    furthest_forward_lower_bound,
    valuation_benchmark,
    var_applicability_guard,
)
from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.instruments import FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.numerics.risk_adjustment import PriceOfRiskKind
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.testing import assert_input_unchanged

# --- Fixtures / builders --------------------------------------------------------------

GAS = CommodityConfig("TTF", "EUR/MBtu", Hub("TTF", "ICE_ENDEX", "EUR/MBtu"))
POWER = CommodityConfig("EEX_PHELIX_DE", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh"))

# Liquid span: 2027-01 (observed) and 2027-02 (interpolated). The furthest liquid
# forward is the 2027-02 node at 24.0.
LIQUID_OBSERVED = DeliveryPeriod(2027, 1)
LIQUID_INTERPOLATED = DeliveryPeriod(2027, 2)
ILLIQUID = DeliveryPeriod(2035, 6)  # far beyond the curve


def make_curve(commodity: CommodityConfig = GAS) -> ForwardCurve:
    return ForwardCurve(
        commodity=commodity,
        market_date=date(2026, 12, 1),
        nodes=(
            CurveNode(period=LIQUID_OBSERVED, price=20.0, status="observed"),
            CurveNode(period=LIQUID_INTERPOLATED, price=24.0, status="interpolated"),
        ),
    )


def spot_model(period: DeliveryPeriod) -> float:
    """Deterministic, hand-computable projected spot: 40 + 0.5*(year - 2030)."""
    return 40.0 + 0.5 * (period.year - 2030)


def corporate(premium: float = 7.5) -> CorporatePremium:
    return CorporatePremium(premium=premium, kind=PriceOfRiskKind.CORPORATE)


def make_priced_position(*, tags: tuple[str, ...], npv: float = 100.0) -> PricedPosition:
    instrument = FuturesContract(
        commodity=GAS,
        delivery_period=ILLIQUID,
        contract_price=50.0,
        notional=1.0,
    )
    return PricedPosition(
        position=Position(instrument=instrument, position_id="pos-1", tags=tags),
        npv=npv,
    )


# --- valuation_benchmark: forward regime (Req 23.1) -----------------------------------


class TestForwardRegime:
    def test_liquid_observed_period_uses_exact_curve_price(self) -> None:
        result = valuation_benchmark(LIQUID_OBSERVED, make_curve(), spot_model, corporate())
        assert result.source == ValuationSource.FORWARD
        assert result.value == 20.0  # exact node price, no premium applied
        assert result.period == LIQUID_OBSERVED

    def test_liquid_interpolated_period_is_still_forward_based(self) -> None:
        # An interpolated node lies within the liquid forward span -> forward, not projected.
        result = valuation_benchmark(LIQUID_INTERPOLATED, make_curve(), spot_model, corporate())
        assert result.source == ValuationSource.FORWARD
        assert result.value == 24.0

    def test_forward_result_flags(self) -> None:
        result = valuation_benchmark(LIQUID_OBSERVED, make_curve(), spot_model, corporate())
        assert result.is_projected is False
        assert result.var_applicable is True


# --- valuation_benchmark: projected regime (Req 23.2) ---------------------------------


class TestProjectedRegime:
    def test_missing_period_uses_projected_spot_plus_premium_hand_computed(self) -> None:
        # spot_model(2035-06) = 40 + 0.5*(2035 - 2030) = 42.5; + premium 7.5 = 50.0.
        result = valuation_benchmark(ILLIQUID, make_curve(), spot_model, corporate(7.5))
        assert result.source == ValuationSource.PROJECTED
        assert result.value == pytest.approx(50.0)
        assert result.period == ILLIQUID

    def test_negative_premium_is_applied(self) -> None:
        # 42.5 + (-2.5) = 40.0.
        result = valuation_benchmark(ILLIQUID, make_curve(), spot_model, corporate(-2.5))
        assert result.source == ValuationSource.PROJECTED
        assert result.value == pytest.approx(40.0)

    def test_projected_result_flags(self) -> None:
        result = valuation_benchmark(ILLIQUID, make_curve(), spot_model, corporate())
        assert result.is_projected is True
        assert result.var_applicable is False


# --- valuation_benchmark: corporate-premium provenance (Req 19.3) ---------------------


class TestCorporatePremiumProvenance:
    def test_market_tagged_premium_rejected_naming_parameter(self) -> None:
        market_premium = CorporatePremium(premium=7.5, kind=PriceOfRiskKind.MARKET)
        with pytest.raises(ValidationError, match="corporate_premium"):
            valuation_benchmark(ILLIQUID, make_curve(), spot_model, market_premium)

    def test_untagged_premium_rejected_naming_parameter(self) -> None:
        # A bare float carries no provenance -> rejected as untagged.
        with pytest.raises(ValidationError, match="corporate_premium"):
            valuation_benchmark(ILLIQUID, make_curve(), spot_model, 7.5)  # type: ignore[arg-type]

    def test_market_tagged_rejected_even_when_period_is_liquid(self) -> None:
        # The premium contract is validated eagerly, regardless of this period's liquidity.
        market_premium = CorporatePremium(premium=7.5, kind=PriceOfRiskKind.MARKET)
        with pytest.raises(ValidationError, match="corporate_premium"):
            valuation_benchmark(LIQUID_OBSERVED, make_curve(), spot_model, market_premium)


# --- var_applicability_guard (Req 23.3) -----------------------------------------------


class TestVarApplicabilityGuard:
    def test_projected_valued_position_is_inapplicable_with_reason(self) -> None:
        position = make_priced_position(tags=(ValuationSource.PROJECTED.value,))
        verdict = var_applicability_guard(position)
        assert isinstance(verdict, VarApplicabilityVerdict)
        assert verdict.applicable is False
        assert "projected" in verdict.reason
        assert "liquid" in verdict.reason  # cites the "VaR only in liquid markets" caveat

    def test_forward_valued_position_is_applicable(self) -> None:
        position = make_priced_position(tags=(ValuationSource.FORWARD.value,))
        verdict = var_applicability_guard(position)
        assert verdict.applicable is True
        assert verdict.reason

    def test_untagged_position_is_treated_as_applicable(self) -> None:
        position = make_priced_position(tags=())
        assert var_applicability_guard(position).applicable is True

    def test_strict_mode_raises_for_projected_position(self) -> None:
        position = make_priced_position(tags=(ValuationSource.PROJECTED.value,))
        with pytest.raises(ValidationError, match="projected"):
            var_applicability_guard(position, strict=True)

    def test_strict_mode_passes_forward_position(self) -> None:
        position = make_priced_position(tags=(ValuationSource.FORWARD.value,))
        verdict = var_applicability_guard(position, strict=True)
        assert verdict.applicable is True


# --- furthest_forward_lower_bound (Req 23.4, Property 66) ------------------------------


class TestFurthestForwardLowerBound:
    def test_storable_returns_furthest_forward_price(self) -> None:
        # Storable (gas): the furthest liquid forward is the 2027-02 node at 24.0.
        result = furthest_forward_lower_bound(make_curve(GAS), ILLIQUID, storable=True)
        assert isinstance(result, LowerBoundResult)
        assert result.lower_bound == 24.0
        assert result.period == ILLIQUID
        assert result.furthest_forward_period == LIQUID_INTERPOLATED

    def test_power_non_storable_is_refused_naming_reason(self) -> None:
        with pytest.raises(ValidationError, match="power") as exc_info:
            furthest_forward_lower_bound(make_curve(POWER), ILLIQUID, storable=False)
        message = str(exc_info.value)
        assert "storable=False" in message
        assert "carry" in message  # non-storability breaks the carry argument

    def test_period_not_beyond_furthest_forward_raises(self) -> None:
        # A period on/within the curve is not an illiquid later tenor.
        with pytest.raises(ValidationError, match="beyond the furthest liquid forward"):
            furthest_forward_lower_bound(make_curve(GAS), LIQUID_OBSERVED, storable=True)


# --- determinism (Req 11.2) & immutability (Req 11.4) ---------------------------------


class TestDeterminismAndImmutability:
    def test_valuation_benchmark_is_deterministic(self) -> None:
        first = valuation_benchmark(ILLIQUID, make_curve(), spot_model, corporate())
        second = valuation_benchmark(ILLIQUID, make_curve(), spot_model, corporate())
        assert first == second
        assert isinstance(first, BenchmarkResult)

    def test_lower_bound_is_deterministic(self) -> None:
        first = furthest_forward_lower_bound(make_curve(GAS), ILLIQUID, storable=True)
        second = furthest_forward_lower_bound(make_curve(GAS), ILLIQUID, storable=True)
        assert first == second

    def test_valuation_benchmark_does_not_mutate_inputs(self) -> None:
        result = assert_input_unchanged(
            valuation_benchmark,
            ILLIQUID,
            make_curve(),
            spot_model,
            corporate(),
        )
        assert result.source == ValuationSource.PROJECTED

    def test_lower_bound_does_not_mutate_inputs(self) -> None:
        result = assert_input_unchanged(
            furthest_forward_lower_bound,
            make_curve(GAS),
            ILLIQUID,
            storable=True,
        )
        assert result.lower_bound == 24.0

    def test_guard_does_not_mutate_inputs(self) -> None:
        position = make_priced_position(tags=(ValuationSource.PROJECTED.value,))
        verdict = assert_input_unchanged(var_applicability_guard, position)
        assert verdict.applicable is False


# --- ValuationSource vocabulary -------------------------------------------------------


class TestValuationSource:
    def test_tag_string_values(self) -> None:
        assert ValuationSource.FORWARD == "forward"
        assert ValuationSource.PROJECTED == "projected"
        assert {s.value for s in ValuationSource} == {"forward", "projected"}
