"""Unit tests for the native Monte Carlo wrapper (Task 59, Reqs 6.1, 6.5, 11.2).

Exercises ``numerics.monte_carlo.asian_monte_carlo`` — the thin typed wrapper over the
Rust ``quantvolt._core`` engine: (a) Property 27 determinism (same seed → bit-identical
``(premium, standard_error)``; different seed → different stream); (b) statistical
agreement of the geometric MC with the Kemna-Vorst closed form; (c) call/put ordering
sanity; (d) the native guards surface as ``ValueError``; (e) a coarse Req 6.5 speed
sanity — 100k paths x 252 fixings in single-digit seconds.

The engine's conventions (documented in ``_core.pyi`` and ``rust/src/paths.rs``):
antithetic variates always on, fixings equally spaced at ``t_k = k*T/m``, determinism
is per-seed for the Rust RNG — the stream does **not** match NumPy's.
"""

from __future__ import annotations

import time
from typing import Literal

import pytest

import quantvolt.numerics.monte_carlo as monte_carlo_module
from quantvolt.exceptions import NativeExtensionError, ValidationError
from quantvolt.numerics.exotic import kemna_vorst
from quantvolt.numerics.monte_carlo import asian_monte_carlo


def test_missing_native_extension_raises_library_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(monte_carlo_module, "_HAVE_CORE", False)
    with pytest.raises(NativeExtensionError, match=r"quantvolt\._core"):
        asian_monte_carlo(
            forward=100.0,
            strike=100.0,
            sigma=0.2,
            time_to_expiry=1.0,
            discount_factor=1.0,
            averaging_points=12,
            option_type="call",
            geometric=False,
            seed=1,
            path_count=100,
        )


_FORWARD = 100.0
_STRIKE = 100.0
_SIGMA = 0.25
_EXPIRY = 0.5
_DF = 0.97
_POINTS = 252


# --- (a) Property 27: determinism per seed (Req 11.2) --------------------------


def test_same_seed_gives_identical_premium_and_standard_error() -> None:
    def run() -> tuple[float, float]:
        return asian_monte_carlo(
            _FORWARD,
            _STRIKE,
            _SIGMA,
            _EXPIRY,
            _DF,
            _POINTS,
            "call",
            geometric=False,
            seed=42,
            path_count=10_000,
        )

    assert run() == run()


def test_different_seeds_give_different_premiums() -> None:
    def run(seed: int) -> tuple[float, float]:
        return asian_monte_carlo(
            _FORWARD,
            _STRIKE,
            _SIGMA,
            _EXPIRY,
            _DF,
            _POINTS,
            "call",
            geometric=False,
            seed=seed,
            path_count=10_000,
        )

    assert run(1)[0] != run(2)[0]


# --- (b) geometric MC agrees with the Kemna-Vorst closed form -------------------


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_geometric_mc_within_three_standard_errors_of_kemna_vorst(
    option_type: Literal["call", "put"],
) -> None:
    # Kemna-Vorst assumes continuous averaging; 252 daily fixings sit close enough
    # that the discretisation bias is well inside the MC noise at this path count.
    premium, standard_error = asian_monte_carlo(
        _FORWARD,
        _STRIKE,
        _SIGMA,
        _EXPIRY,
        _DF,
        _POINTS,
        option_type,
        geometric=True,
        seed=2024,
        path_count=100_000,
    )
    reference = kemna_vorst(_FORWARD, _STRIKE, _SIGMA, _EXPIRY, _DF, option_type)
    assert standard_error > 0.0
    assert abs(premium - reference) < 3.0 * standard_error


# --- (c) ordering sanity ---------------------------------------------------------


def test_call_worth_more_than_put_when_forward_above_strike() -> None:
    def price(option_type: Literal["call", "put"]) -> float:
        return asian_monte_carlo(
            105.0,
            95.0,
            _SIGMA,
            _EXPIRY,
            _DF,
            _POINTS,
            option_type,
            geometric=False,
            seed=7,
            path_count=20_000,
        )[0]

    assert price("call") > price("put")


# --- (d) native input guards surface as ValueError -------------------------------


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("path_count", {"path_count": 0}),
        ("averaging_points", {"averaging_points": 0}),
        ("forward", {"forward": float("nan")}),
        ("sigma", {"sigma": float("inf")}),
    ],
)
def test_native_guards_raise_value_error_naming_the_parameter(
    field: str,
    kwargs: dict[str, float],
) -> None:
    base: dict[str, float] = {
        "forward": _FORWARD,
        "strike": _STRIKE,
        "sigma": _SIGMA,
        "time_to_expiry": _EXPIRY,
        "discount_factor": _DF,
        "averaging_points": _POINTS,
        "seed": 1,
        "path_count": 1000,
    }
    base.update(kwargs)
    with pytest.raises(ValueError, match=field):
        asian_monte_carlo(option_type="call", geometric=False, **base)  # type: ignore[arg-type]


# --- Fix 2 regression: negative/zero time_to_expiry must raise, not silently return (0, 0) ---


@pytest.mark.parametrize("time_to_expiry", [-0.5, 0.0])
def test_non_positive_time_to_expiry_raises_validation_error(time_to_expiry: float) -> None:
    # Previously only require_finite'd: a negative T reached the Rust kernel as NaN and
    # silently returned (0.0, 0.0) instead of raising (verified).
    with pytest.raises(ValidationError, match="time_to_expiry"):
        asian_monte_carlo(
            _FORWARD,
            _STRIKE,
            _SIGMA,
            time_to_expiry,
            _DF,
            _POINTS,
            "call",
            geometric=False,
            seed=1,
            path_count=1000,
        )


# --- (e) Req 6.5 coarse speed sanity ----------------------------------------------


def test_hundred_thousand_paths_at_daily_fixings_completes_quickly() -> None:
    start = time.perf_counter()
    asian_monte_carlo(
        _FORWARD,
        _STRIKE,
        _SIGMA,
        _EXPIRY,
        _DF,
        252,
        "call",
        geometric=False,
        seed=42,
        path_count=100_000,
    )
    assert time.perf_counter() - start < 5.0


# --- (f) keyword-only antithetic override -----------------------------------------


def test_default_antithetic_matches_explicit_true() -> None:
    def run(**kwargs: object) -> tuple[float, float]:
        return asian_monte_carlo(
            _FORWARD,
            _STRIKE,
            _SIGMA,
            _EXPIRY,
            _DF,
            _POINTS,
            "call",
            geometric=False,
            seed=42,
            path_count=10_000,
            **kwargs,  # type: ignore[arg-type]
        )

    assert run() == run(antithetic=True)


def test_antithetic_false_changes_the_result_for_the_same_seed() -> None:
    def run(antithetic: bool) -> tuple[float, float]:
        return asian_monte_carlo(
            _FORWARD,
            _STRIKE,
            _SIGMA,
            _EXPIRY,
            _DF,
            _POINTS,
            "call",
            geometric=False,
            seed=42,
            path_count=10_000,
            antithetic=antithetic,
        )

    with_antithetic = run(True)
    without_antithetic = run(False)
    assert with_antithetic != without_antithetic
    # Still deterministic per-seed with antithetic off.
    assert run(False) == without_antithetic
