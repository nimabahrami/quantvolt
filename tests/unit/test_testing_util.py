"""Unit tests for ``assert_input_unchanged``, the shipped immutability utility (Task 10)."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.greeks import Greeks
from quantvolt.testing import assert_input_unchanged


def test_pure_function_passes_and_forwards_return_value() -> None:
    """A non-mutating function returns normally and its result is forwarded to the caller."""
    data = [1, 2, 3]
    result = assert_input_unchanged(sum, data)
    assert result == 6
    assert data == [1, 2, 3]


def test_return_value_is_the_functions_actual_output() -> None:
    """The forwarded value is exactly what ``func`` returned (identity preserved)."""
    sentinel = object()

    def produce(_x: int) -> object:
        return sentinel

    assert assert_input_unchanged(produce, 1) is sentinel


def test_none_return_is_forwarded() -> None:
    """A function returning ``None`` without mutating inputs passes and forwards ``None``."""

    def read_only(seq: list[int]) -> None:
        _ = sum(seq)

    assert assert_input_unchanged(read_only, [1, 2, 3]) is None


def test_no_arguments() -> None:
    """A zero-argument callable is supported."""
    assert assert_input_unchanged(lambda: 42) == 42


def test_mutated_list_raises_and_names_positional_index() -> None:
    """Mutating a positional list argument raises AssertionError naming index 0 and the change."""

    def append_one(seq: list[int]) -> int:
        seq.append(99)
        return len(seq)

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(append_one, [1, 2, 3])

    message = str(excinfo.value)
    assert "append_one" in message
    assert "positional argument 0" in message
    assert "[1, 2, 3]" in message
    assert "[1, 2, 3, 99]" in message


def test_mutated_dict_raises_and_names_positional_index() -> None:
    """Mutating a passed dict is detected via deep equality."""

    def insert_key(mapping: dict[str, int]) -> None:
        mapping["new"] = 1

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(insert_key, {"a": 1})

    assert "positional argument 0" in str(excinfo.value)


def test_mutation_names_the_correct_positional_index() -> None:
    """Only the mutated argument (index 1) is reported, not the untouched one (index 0)."""

    def mutate_second(_first: list[int], second: list[int]) -> None:
        second.append(0)

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(mutate_second, [1], [2])

    message = str(excinfo.value)
    assert "positional argument 1" in message
    assert "positional argument 0" not in message


def test_works_with_kwargs_when_unchanged() -> None:
    """Keyword arguments are forwarded and verified; a pure function passes."""

    def combine(*, base: list[int], scale: int) -> int:
        return sum(base) * scale

    assert assert_input_unchanged(combine, base=[1, 2], scale=3) == 9


def test_mutated_kwarg_raises_and_names_keyword() -> None:
    """Mutating a keyword argument raises AssertionError naming the keyword."""

    def clear_it(*, payload: dict[str, int]) -> None:
        payload.clear()

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(clear_it, payload={"a": 1})

    message = str(excinfo.value)
    assert "keyword argument 'payload'" in message
    assert "positional argument" not in message


def test_deeply_nested_mutation_is_detected() -> None:
    """Mutation of a nested container (not just the top level) is caught by deep equality."""

    def mutate_inner(rows: list[dict[str, int]]) -> None:
        rows[0]["x"] = 99

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(mutate_inner, [{"x": 1}])

    assert "positional argument 0" in str(excinfo.value)


def test_multiple_mutations_all_reported() -> None:
    """When several inputs are mutated, every culprit is named in one message."""

    def mutate_both(a: list[int], *, b: dict[str, int]) -> None:
        a.append(2)
        b["k"] = 1

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(mutate_both, [1], b={})

    message = str(excinfo.value)
    assert "positional argument 0" in message
    assert "keyword argument 'b'" in message


def test_frozen_dataclass_input_passes() -> None:
    """The library's frozen dataclasses cannot be mutated, so passing them succeeds."""
    greeks = Greeks(delta=0.5, gamma=0.1, vega=0.2, theta=-0.01, rho=0.05)

    def read_delta(g: Greeks) -> float:
        return g.delta

    assert assert_input_unchanged(read_delta, greeks) == 0.5


def test_frozen_dataclass_kwarg_with_nested_frozen_value() -> None:
    """A nested frozen value object passes both by position and by keyword."""
    config = CommodityConfig(
        commodity_id="TTF",
        price_unit="EUR/MWh",
        hub=Hub(hub_id="TTF", exchange="ICE_ENDEX", price_unit="EUR/MWh"),
    )

    def hub_id(*, cfg: CommodityConfig) -> str:
        return cfg.hub.hub_id

    assert assert_input_unchanged(hub_id, cfg=config) == "TTF"


def test_frozen_dataclass_equality_survives_deepcopy() -> None:
    """Sanity: deep-copying a frozen dataclass yields a value-equal snapshot (no false positive)."""
    greeks = Greeks(delta=1.0, gamma=2.0, vega=3.0, theta=4.0, rho=5.0)
    assert assert_input_unchanged(lambda g: g, greeks) == greeks


def test_numpy_array_input_unchanged_passes() -> None:
    """A read-only function taking a NumPy array passes (element-wise eq is reduced to one bool)."""
    arr = np.array([1.0, 2.0, 3.0])

    def total(a: np.ndarray) -> float:
        return float(a.sum())

    assert assert_input_unchanged(total, arr) == 6.0


def test_numpy_array_with_nan_is_treated_as_unchanged() -> None:
    """A NaN-holding array equals its deep copy (equal_nan), avoiding a false positive."""
    arr = np.array([1.0, np.nan, 3.0])
    assert assert_input_unchanged(lambda a: a, arr) is arr


def test_mutated_numpy_array_is_detected() -> None:
    """In-place mutation of a NumPy array argument is caught and reported."""

    def zero_first(a: np.ndarray) -> None:
        a[0] = -999.0

    with pytest.raises(AssertionError) as excinfo:
        assert_input_unchanged(zero_first, np.array([1.0, 2.0]))

    assert "positional argument 0" in str(excinfo.value)


def test_polars_series_input_unchanged_passes() -> None:
    """A read-only function taking a Polars Series passes (.equals() value comparison)."""
    series = pl.Series("p", [10.0, 20.0, 30.0])

    def mean(s: pl.Series) -> float:
        return float(s.mean())

    assert assert_input_unchanged(mean, series) == 20.0


def test_polars_dataframe_kwarg_unchanged_passes() -> None:
    """A Polars DataFrame keyword argument is verified via .equals()."""
    frame = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

    def n_rows(*, df: pl.DataFrame) -> int:
        return df.height

    assert assert_input_unchanged(n_rows, df=frame) == 2
