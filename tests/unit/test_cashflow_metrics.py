"""Comparable realized profit and risk metrics from caller cash flows."""

import polars as pl
import pytest

from quantvolt import compare_cashflow_strategies
from quantvolt.exceptions import ValidationError


def test_hand_computed_strategy_comparison() -> None:
    data = pl.DataFrame({"merchant": [0.0, 100.0, 200.0], "hedged": [50.0, 100.0, 150.0]})
    result = compare_cashflow_strategies(
        data,
        {"merchant": "merchant", "hedged": "hedged"},
        benchmark="merchant",
        confidence_level=0.5,
    )
    merchant = result.for_strategy("merchant")
    hedged = result.for_strategy("hedged")
    assert merchant.total_cashflow == hedged.total_cashflow == 300.0
    assert merchant.cfar == hedged.cfar == 0.0
    assert hedged.sample_std_cashflow == pytest.approx(50.0)
    assert merchant.sample_std_cashflow == pytest.approx(100.0)
    assert hedged.volatility_reduction_vs_benchmark == pytest.approx(50.0)
    assert hedged.total_difference_vs_benchmark == 0.0


def test_rejects_nonfinite_and_ambiguous_data() -> None:
    data = pl.DataFrame({"a": [1.0, float("nan")], "b": [1.0, 2.0]})
    with pytest.raises(ValidationError, match="finite"):
        compare_cashflow_strategies(data, {"a": "a"}, benchmark="a")
    with pytest.raises(ValidationError, match="distinct"):
        compare_cashflow_strategies(data.select("b"), {"one": "b", "two": "b"}, benchmark="one")
    with pytest.raises(ValidationError, match="not in"):
        compare_cashflow_strategies(data.select("b"), {"one": "b"}, benchmark="missing")


def test_unknown_strategy_lists_available_results() -> None:
    result = compare_cashflow_strategies(
        pl.DataFrame({"cash": [1.0]}), {"merchant": "cash"}, benchmark="merchant"
    )
    with pytest.raises(ValidationError, match="available: merchant"):
        result.for_strategy("hedged")
