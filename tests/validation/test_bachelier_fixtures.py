"""Bachelier fixture agreement vs the checked-in QuantLib references (spec
``bachelier-negative-forwards`` Requirement 6).

Loads ``fixtures/bachelier.json``, recomputes QuantVolt's Bachelier premium / Greeks / normal-
implied-vol for every case, and asserts agreement within the case's declared tolerance. Runs in
CI with **no** reference library installed (the numbers are frozen in the fixture). The matrix
deliberately spans **negative and zero** forwards and strikes — the whole point of the Bachelier
model. Degenerate ``sigma_N=0`` / ``T=0`` cases assert QuantVolt's documented discounted-intrinsic
identity instead of a QuantLib inversion.

An optional ``pytest.importorskip("QuantLib")`` live class recomputes the QuantLib reference
directly for maintainer use; it is skipped whenever QuantLib is absent, so it never runs in CI.
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

from quantvolt.numerics.bachelier import (
    bachelier_greeks,
    bachelier_implied_vol,
    bachelier_price,
)

_PROVENANCE, _CASES = load_cases("bachelier.json")
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
    otype, forward, strike = i["option_type"], i["forward"], i["strike"]
    sigma, t, df = i["normal_sigma"], i["time_to_expiry"], i["discount_factor"]
    reference = case["reference"]

    values: dict[str, float] = {"premium": bachelier_price(otype, forward, strike, sigma, t, df)}
    if any(name in reference for name in _GREEK_GETTERS):
        greeks = bachelier_greeks(otype, forward, strike, sigma, t, df)
        for name, getter in _GREEK_GETTERS.items():
            if name in reference:
                values[name] = getter(greeks)
    if "implied_vol" in reference:
        # Tight Brent tolerance so the recovered vol matches the reference to rel 1e-7.
        values["implied_vol"] = bachelier_implied_vol(
            otype, reference["premium"], forward, strike, t, df, tol=1e-12
        )
    return values


@pytest.mark.skipif(not _CASES, reason="bachelier.json not generated (reference library offline)")
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_bachelier_case_matches_reference(case: dict[str, Any]) -> None:
    values = _quantvolt_values(case)
    reference = case["reference"]
    tolerance = case["tolerance"]
    for name, ref in reference.items():
        actual = values[name]
        tol = tolerance[name]
        assert within_tolerance(actual, ref, tol), (
            f"{case['case_id']} {name}: {tolerance_detail(actual, ref, tol)}"
        )


@pytest.mark.skipif(not _CASES, reason="bachelier.json not generated (reference library offline)")
def test_degenerate_cases_use_intrinsic_identity() -> None:
    """Every degenerate case's premium is the discounted intrinsic (degenerate branch)."""
    degenerate = [c for c in _CASES if c["inputs"].get("degenerate")]
    assert degenerate, "fixture should contain degenerate sigma_N=0/T=0 edge cases"
    for case in degenerate:
        i = case["inputs"]
        forward, strike, df = i["forward"], i["strike"], i["discount_factor"]
        intrinsic = df * (
            max(forward - strike, 0.0) if i["option_type"] == "call" else max(strike - forward, 0.0)
        )
        premium = bachelier_price(
            i["option_type"], forward, strike, i["normal_sigma"], i["time_to_expiry"], df
        )
        assert premium == pytest.approx(intrinsic, abs=1e-12)
        assert premium == pytest.approx(case["reference"]["premium"], abs=1e-12)


@pytest.mark.skipif(not _CASES, reason="bachelier.json not generated (reference library offline)")
def test_negative_forward_cases_present() -> None:
    """The fixture must exercise negative forwards and strikes — the model's raison d'etre."""
    assert any(c["inputs"]["forward"] < 0 for c in _CASES), "no negative-forward cases in fixture"
    assert any(c["inputs"]["strike"] < 0 for c in _CASES), "no negative-strike cases in fixture"


class TestBachelierLiveQuantLib:
    """Optional maintainer-only live cross-check; skipped in CI."""

    def test_live_reference_matches_fixture(self) -> None:
        ql = pytest.importorskip("QuantLib")
        if not _CASES:
            pytest.skip("bachelier.json not generated")
        ql_type = {"call": ql.Option.Call, "put": ql.Option.Put}
        for case in _CASES:
            if case["inputs"].get("degenerate"):
                continue
            i = case["inputs"]
            premium = ql.bachelierBlackFormula(
                ql_type[i["option_type"]],
                i["strike"],
                i["forward"],
                i["normal_sigma"] * math.sqrt(i["time_to_expiry"]),
                i["discount_factor"],
            )
            assert within_tolerance(
                premium, case["reference"]["premium"], case["tolerance"]["premium"]
            )
