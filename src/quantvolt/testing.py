"""Shipped test utility (Req 11.4): assert a library function does not mutate its inputs.

Public, importable as ``from quantvolt.testing import assert_input_unchanged``. Callers
wrap any pure library function to prove it leaves its arguments untouched (immutability
invariant, ``coding-style.md`` §7) while still receiving the function's return value.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import ParamSpec, TypeVar

import numpy as np

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _inputs_equal(before: object, after: object) -> bool:
    """Value-equality that stays a single ``bool`` for array-like library inputs.

    A plain ``before == after`` is unusable here: NumPy arrays and Polars ``Series`` /
    ``DataFrame`` return an *element-wise* result (an array / a Series), whose truth value
    is ambiguous. This helper reduces each such comparison to one boolean so the caller's
    inputs — which are frequently ``np.ndarray`` or ``pl.Series`` — can be checked for
    mutation. Scalars, dataclasses, and built-in containers fall through to ``==``.
    """
    # Polars Series / DataFrame expose value-equality via .equals(); detected by module
    # name so Polars need not be imported by the core.
    if type(before).__module__.split(".", 1)[0] == "polars":
        return bool(before.equals(after))  # type: ignore[attr-defined]

    # NumPy arrays (and objects exposing the array protocol) compare element-wise.
    if isinstance(before, np.ndarray) or hasattr(before, "__array__"):
        a = np.asarray(before)
        b = np.asarray(after)
        if a.shape != b.shape:
            return False
        # equal_nan only applies to floating arrays; NaN-holding inputs are still "unchanged".
        if a.dtype.kind == "f" and b.dtype.kind == "f":
            return bool(np.array_equal(a, b, equal_nan=True))
        return bool(np.array_equal(a, b))

    result = before == after
    if isinstance(result, bool):
        return result
    # Last resort: some other array-like __eq__ returned a non-bool; collapse it.
    return bool(np.asarray(result).all())


def assert_input_unchanged(func: Callable[_P, _R], *args: _P.args, **kwargs: _P.kwargs) -> _R:
    """Call ``func`` and assert it did not mutate any of its inputs; return its result.

    A deep copy of every positional and keyword argument is taken *before* ``func`` runs.
    After the call each original argument is compared (deep, value equality) against its
    pre-call snapshot. Any difference means ``func`` mutated a caller-owned object. The
    comparison handles ``np.ndarray`` and Polars ``Series`` / ``DataFrame`` inputs, not
    only scalars and built-in containers.

    Args:
        func: The callable under test.
        *args: Positional arguments forwarded to ``func``.
        **kwargs: Keyword arguments forwarded to ``func``.

    Returns:
        Whatever ``func`` returned, so callers can chain assertions on the output.

    Raises:
        AssertionError: If any input differs from its pre-call deep copy. The message
            names each mutated positional index / keyword and shows ``before -> after``.
    """
    before_args = copy.deepcopy(args)
    before_kwargs = copy.deepcopy(kwargs)

    result = func(*args, **kwargs)

    mutations: list[str] = []
    for index, before in enumerate(before_args):
        after = args[index]
        if not _inputs_equal(before, after):
            mutations.append(f"positional argument {index} changed: {before!r} -> {after!r}")
    for name, before in before_kwargs.items():
        after = kwargs[name]
        if not _inputs_equal(before, after):
            mutations.append(f"keyword argument {name!r} changed: {before!r} -> {after!r}")

    if mutations:
        func_name = getattr(func, "__name__", repr(func))
        raise AssertionError(f"{func_name} mutated its input(s): " + "; ".join(mutations))

    return result
