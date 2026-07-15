"""Smoke test: the package imports and exposes its public exception hierarchy."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import quantvolt
import quantvolt._core as native_core
import quantvolt.exceptions as exceptions


def test_version() -> None:
    assert quantvolt.__version__


def test_exception_hierarchy() -> None:
    declared = {
        value
        for value in vars(exceptions).values()
        if inspect.isclass(value)
        and value.__module__ == exceptions.__name__
        and value.__name__.endswith("Error")
    }
    assert declared
    assert all(issubclass(error, quantvolt.EnergyQuantError) for error in declared)
    assert issubclass(quantvolt.NumericalError, ValueError)


def test_native_stub_matches_runtime_signatures() -> None:
    stub_path = Path(quantvolt.__file__).with_name("_core.pyi")
    tree = ast.parse(stub_path.read_text(encoding="utf-8"))
    stub_functions = {
        node.name: [argument.arg for argument in node.args.args]
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }
    runtime_functions = {
        name: list(inspect.signature(getattr(native_core, name)).parameters)
        for name in stub_functions
    }
    assert runtime_functions == stub_functions


def test_validation_helper() -> None:
    from quantvolt._validation import (
        require_finite,
        require_integer_at_least,
        require_length,
        require_positive,
    )

    try:
        require_positive("x", -1.0)
    except quantvolt.ValidationError as exc:
        assert "x" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValidationError")

    for guard in (
        lambda: require_finite("finite", float("nan")),
        lambda: require_integer_at_least("count", True, 1),
        lambda: require_integer_at_least("count", 0, 1),
        lambda: require_length("items", [1], 2),
    ):
        try:
            guard()
        except quantvolt.ValidationError:
            pass
        else:  # pragma: no cover
            raise AssertionError("expected ValidationError")
