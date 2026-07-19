"""Property 92: Black-76 fixture agreement vs the checked-in QuantLib references (Req 3, 7).

Loads ``fixtures/black76.json``, recomputes QuantVolt's Black-76 premium / Greeks / implied vol
for every case, and asserts agreement within the case's declared tolerance. Runs in CI with
**no** reference library installed (the numbers are frozen in the fixture). Degenerate
``sigma=0`` / ``T=0`` cases assert QuantVolt's documented discounted-intrinsic identity
(black76.py:88-92) instead of a QuantLib inversion.

An optional ``pytest.importorskip("QuantLib")`` live class recomputes the QuantLib reference
directly for maintainer use; it is skipped whenever QuantLib is absent, so it never runs in CI
(Requirement 7.3).
"""

from __future__ import annotations

import math
from typing import Any

import pytest
from _fixtures import (  # type: ignore[import-not-found]
    load_cases,
    tolerance_detail,
    within_tolerance,
)

from quantvolt.numerics.black76 import black76_greeks, black76_implied_vol, black76_price

_PROVENANCE, _CASES = load_cases("black76.json")
_IDS = [c["case_id"] for c in _CASES]

_GREEK_GETTERS = {
    "delta": lambda g: g.delta,
    "gamma": lambda g: g.gamma,
    "vega": lambda g: g.vega,
    "theta": lambda g: g.theta,
    "rho": lambda g: g.rho,
}


def _quantvolt_values(case: dict[str, Any]) -> dict[str, float]:
    """Recompute every QuantVolt output the fixture references, keyed like ``reference``."""
    i = case["inputs"]
    otype, F, K = i["option_type"], i["forward"], i["strike"]
    sigma, t, df = i["sigma"], i["time_to_expiry"], i["discount_factor"]
    reference = case["reference"]

    values: dict[str, float] = {"premium": black76_price(otype, F, K, sigma, t, df)}
    if any(name in reference for name in _GREEK_GETTERS):
        greeks = black76_greeks(otype, F, K, sigma, t, df)
        for name, getter in _GREEK_GETTERS.items():
            if name in reference:
                values[name] = getter(greeks)
    if "implied_vol" in reference:
        # Tight Brent tolerance so the recovered vol matches the reference to rel 1e-7.
        values["implied_vol"] = black76_implied_vol(
            otype, reference["premium"], F, K, t, df, tol=1e-12
        )
    return values


@pytest.mark.skipif(not _CASES, reason="black76.json not generated (reference library offline)")
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_black76_case_matches_reference(case: dict[str, Any]) -> None:
    values = _quantvolt_values(case)
    reference = case["reference"]
    tolerance = case["tolerance"]
    for name, ref in reference.items():
        actual = values[name]
        tol = tolerance[name]
        assert within_tolerance(actual, ref, tol), (
            f"{case['case_id']} {name}: {tolerance_detail(actual, ref, tol)}"
        )


@pytest.mark.skipif(not _CASES, reason="black76.json not generated (reference library offline)")
def test_degenerate_cases_use_intrinsic_identity() -> None:
    """Every degenerate case's premium is the discounted intrinsic (black76.py:88-92)."""
    degenerate = [c for c in _CASES if c["inputs"].get("degenerate")]
    assert degenerate, "fixture should contain degenerate sigma=0/T=0 edge cases (Req 3.2)"
    for case in degenerate:
        i = case["inputs"]
        F, K, df = i["forward"], i["strike"], i["discount_factor"]
        intrinsic = df * (max(F - K, 0.0) if i["option_type"] == "call" else max(K - F, 0.0))
        premium = black76_price(i["option_type"], F, K, i["sigma"], i["time_to_expiry"], df)
        assert premium == pytest.approx(intrinsic, abs=1e-12)
        assert premium == pytest.approx(case["reference"]["premium"], abs=1e-12)


class TestBlack76LiveQuantLib:
    """Optional maintainer-only live cross-check; skipped in CI (Requirement 7.3)."""

    def test_live_reference_matches_fixture(self) -> None:
        ql = pytest.importorskip("QuantLib")
        if not _CASES:
            pytest.skip("black76.json not generated")
        ql_type = {"call": ql.Option.Call, "put": ql.Option.Put}
        for case in _CASES:
            if case["inputs"].get("degenerate"):
                continue
            i = case["inputs"]
            premium = ql.blackFormula(
                ql_type[i["option_type"]],
                i["strike"],
                i["forward"],
                i["sigma"] * math.sqrt(i["time_to_expiry"]),
                i["discount_factor"],
            )
            assert within_tolerance(
                premium, case["reference"]["premium"], case["tolerance"]["premium"]
            )
