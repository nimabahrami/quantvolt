"""Unit tests for curves/builder.py (Task 19, Req 1.1/1.3/1.5/1.6/1.8; Properties 1, 2, 4).

Covers gap-fill + observed/interpolated annotation, reprice residuals, the strictly
ordered boundary validation, caller commodity extensions, input immutability, and a
light 120-period performance sanity check.
"""

from __future__ import annotations

import time
from datetime import date

import pytest

from quantvolt.curves.builder import CurveBuilder, CurveBuildResult
from quantvolt.exceptions import InsufficientDataError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import ForwardCurve
from quantvolt.models.instruments import InstrumentPriceRecord
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.testing import assert_input_unchanged

MARKET_DATE = date(2025, 1, 1)
TTF = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))

JAN = DeliveryPeriod(2025, 1)
FEB = DeliveryPeriod(2025, 2)
MAR = DeliveryPeriod(2025, 3)
APR = DeliveryPeriod(2025, 4)
MAY = DeliveryPeriod(2025, 5)


def _instrument(
    period: DeliveryPeriod, price: float, commodity: CommodityConfig = TTF
) -> InstrumentPriceRecord:
    return InstrumentPriceRecord(
        instrument_id=f"{commodity.commodity_id}-{period.year}-{period.month:02d}",
        commodity=commodity,
        delivery_period=period,
        price=price,
    )


# --- construction: gap fill + node annotation (Req 1.3, Property 2) ----------


def test_piecewise_linear_fills_gaps_and_annotates_nodes() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(MAR, 24.0), _instrument(MAY, 28.0)]
    result = CurveBuilder().build(TTF, MARKET_DATE, instruments, interpolation="piecewise_linear")

    curve = result.curve
    assert [node.period for node in curve.nodes] == [JAN, FEB, MAR, APR, MAY]

    status = {node.period: node.status for node in curve.nodes}
    assert status == {
        JAN: "observed",
        FEB: "interpolated",
        MAR: "observed",
        APR: "interpolated",
        MAY: "observed",
    }
    # Linear fill on a uniform monthly axis: FEB midway 20->24, APR midway 24->28.
    assert curve.price_at(FEB) == pytest.approx(22.0)
    assert curve.price_at(APR) == pytest.approx(26.0)


def test_result_is_curve_build_result_with_empty_warnings_on_clean_curve() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0), _instrument(MAR, 22.0)]
    result = CurveBuilder().build(TTF, MARKET_DATE, instruments)
    assert isinstance(result, CurveBuildResult)
    assert result.arbitrage_warnings == []


def test_reprice_residuals_for_observed_periods_are_zero(  # Req 1.1, Property 1
) -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(MAR, 24.0), _instrument(MAY, 28.0)]
    tolerance = 0.01
    result = CurveBuilder().build(TTF, MARKET_DATE, instruments, tolerance=tolerance)

    assert set(result.reprice_residuals) == {i.instrument_id for i in instruments}
    for residual in result.reprice_residuals.values():
        assert residual == pytest.approx(0.0, abs=1e-12)
        assert residual <= tolerance


def test_arbitrage_warnings_attached_for_inverted_inputs() -> None:
    instruments = [_instrument(JAN, 30.0), _instrument(FEB, 20.0)]
    result = CurveBuilder().build(TTF, MARKET_DATE, instruments, storage_cost=0.0)
    assert len(result.arbitrage_warnings) == 1
    assert result.arbitrage_warnings[0].periods == (JAN, FEB)


def test_negative_storage_cost_rejected_via_builder() -> None:
    """Regression: storage_cost is forwarded unchanged from ``build`` to
    ``ArbitrageChecker.check``, so the negative-value guard must be reachable (and
    reachable in) through this path too, not only when calling the checker directly.
    """
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 20.0)]
    with pytest.raises(ValidationError, match="storage_cost"):
        CurveBuilder().build(TTF, MARKET_DATE, instruments, storage_cost=-5.0)


# --- ordered boundary validation (Req 1.8, 1.6, 1.1; Property 4) -------------


def test_too_few_instruments_for_cubic_spline_raises_insufficient_data() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0), _instrument(MAR, 22.0)]
    with pytest.raises(InsufficientDataError) as excinfo:
        CurveBuilder().build(TTF, MARKET_DATE, instruments, interpolation="cubic_spline")
    message = str(excinfo.value)
    assert "cubic_spline" in message and "4" in message and "3" in message


@pytest.mark.parametrize(
    ("method", "count"),
    [("piecewise_flat", 0), ("piecewise_linear", 1), ("cubic_spline", 3)],
)
def test_minimum_instrument_counts_per_method(method: str, count: int) -> None:
    instruments = [_instrument(DeliveryPeriod(2025, m + 1), 20.0 + m) for m in range(count)]
    with pytest.raises(InsufficientDataError):
        CurveBuilder().build(TTF, MARKET_DATE, instruments, interpolation=method)  # type: ignore[arg-type]


def test_unsupported_commodity_raises_validation_error() -> None:
    madeup = CommodityConfig("MADEUP", "EUR/MWh", Hub("MADEUP", "NONE", "EUR/MWh"))
    instruments = [_instrument(JAN, 20.0, madeup), _instrument(FEB, 21.0, madeup)]
    with pytest.raises(ValidationError) as excinfo:
        CurveBuilder().build(madeup, MARKET_DATE, instruments)
    assert "MADEUP" in str(excinfo.value)


def test_tolerance_out_of_range_raises_validation_error() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0)]
    with pytest.raises(ValidationError) as excinfo:
        CurveBuilder().build(TTF, MARKET_DATE, instruments, tolerance=2.0)
    assert "tolerance" in str(excinfo.value)


def test_unknown_interpolation_method_raises_validation_error() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0)]
    with pytest.raises(ValidationError):
        CurveBuilder().build(TTF, MARKET_DATE, instruments, interpolation="spline")  # type: ignore[arg-type]


def test_duplicate_delivery_periods_are_rejected() -> None:
    """Regression: two instruments quoting the same delivery period must not be
    silently dict-collapsed (last-price-wins) in ``_assemble_curve``; conflicting
    or duplicate quotes are a caller error (Req 1.1's repricing guarantee assumes
    one quote per period).
    """
    duplicate = InstrumentPriceRecord(
        instrument_id="TTF-duplicate-jan",
        commodity=TTF,
        delivery_period=JAN,
        price=999.0,
    )
    instruments = [_instrument(JAN, 20.0), duplicate, _instrument(FEB, 21.0)]
    with pytest.raises(ValidationError) as excinfo:
        CurveBuilder().build(TTF, MARKET_DATE, instruments)
    message = str(excinfo.value)
    assert repr(JAN) in message
    assert "TTF-duplicate-jan" in message
    assert "TTF-2025-01" in message


def test_reprice_residual_exceeding_tolerance_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: ``tolerance`` must actually be enforced against the reprice
    residuals (Req 1.1), not merely validated in range and then ignored. With
    duplicate delivery periods now rejected up front (see
    ``test_duplicate_delivery_periods_are_rejected``), the only way to exercise a
    residual exceeding tolerance is to force the curve's own repricing away from
    an input instrument's price -- this simulates any future assembly bug that
    would otherwise silently violate the Req 1.1 guarantee.
    """
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0)]
    original_price_at = ForwardCurve.price_at

    def bad_price_at(self: ForwardCurve, period: DeliveryPeriod) -> float:
        return original_price_at(self, period) + 10.0

    monkeypatch.setattr(ForwardCurve, "price_at", bad_price_at)
    with pytest.raises(ValidationError) as excinfo:
        CurveBuilder().build(TTF, MARKET_DATE, instruments, tolerance=0.01)
    message = str(excinfo.value)
    assert "tolerance" in message
    assert "TTF-2025-01" in message
    assert "TTF-2025-02" in message


def test_instrument_commodity_mismatch_raises_validation_error() -> None:
    other = CommodityConfig("NBP", "GBp/therm", Hub("NBP", "ICE_ENDEX", "GBp/therm"))
    instruments = [_instrument(JAN, 20.0), _instrument(FEB, 21.0, other)]
    with pytest.raises(ValidationError) as excinfo:
        CurveBuilder().build(TTF, MARKET_DATE, instruments)
    assert "NBP" in str(excinfo.value)


# --- caller commodity extension (Req 1.6, Adapter seam) ----------------------


def test_caller_extra_commodity_is_accepted() -> None:
    custom = CommodityConfig("CUSTOM", "EUR/MWh", Hub("CUSTOM_HUB", "OTC", "EUR/MWh"))
    builder = CurveBuilder(extra_commodities={"CUSTOM": custom})
    instruments = [_instrument(JAN, 40.0, custom), _instrument(MAR, 44.0, custom)]
    result = builder.build(custom, MARKET_DATE, instruments)
    assert result.curve.commodity == custom
    assert len(result.curve.nodes) == 3  # JAN, FEB (filled), MAR


# --- immutability (coding-style.md §7) ---------------------------------------


def test_build_does_not_mutate_its_inputs() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(MAR, 24.0), _instrument(MAY, 28.0)]
    result = assert_input_unchanged(
        CurveBuilder().build, TTF, MARKET_DATE, instruments, interpolation="piecewise_linear"
    )
    assert isinstance(result, CurveBuildResult)


# --- round-trip (Req 1.7) ----------------------------------------------------


def test_from_dict_round_trips_a_built_curve() -> None:
    instruments = [_instrument(JAN, 20.0), _instrument(MAR, 24.0)]
    curve = CurveBuilder().build(TTF, MARKET_DATE, instruments).curve
    assert CurveBuilder.from_dict(curve.to_dict()) == curve


# --- performance sanity check (Req 1.5) --------------------------------------


def test_builds_120_monthly_periods_quickly() -> None:
    instruments = [
        _instrument(DeliveryPeriod(2025 + index // 12, index % 12 + 1), 20.0 + index * 0.1)
        for index in range(120)
    ]
    start = time.perf_counter()
    result = CurveBuilder().build(TTF, MARKET_DATE, instruments, interpolation="cubic_spline")
    elapsed = time.perf_counter() - start
    assert len(result.curve.nodes) == 120
    assert elapsed < 5.0
