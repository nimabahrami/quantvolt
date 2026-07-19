"""Property 92: Kirk / Margrabe spread fixture agreement vs QuantLib (Req 5, 7).

Loads ``fixtures/spread.json``, recomputes QuantVolt's ``kirk`` (K != 0) or ``margrabe`` (K = 0,
the exact exchange-option collapse) per case, and asserts agreement within the declared
tolerance. Runs in CI with no reference library installed.
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

from quantvolt.numerics.spread_models import kirk, margrabe

_PROVENANCE, _CASES = load_cases("spread.json")
_IDS = [c["case_id"] for c in _CASES]


def _quantvolt_premium(case: dict[str, Any]) -> float:
    i = case["inputs"]
    if i["model"] == "margrabe":
        return margrabe(
            i["forward1"],
            i["forward2"],
            i["sigma1"],
            i["sigma2"],
            i["rho"],
            i["time_to_expiry"],
            i["discount_factor"],
        )
    return kirk(
        i["forward1"],
        i["forward2"],
        i["strike"],
        i["sigma1"],
        i["sigma2"],
        i["rho"],
        i["time_to_expiry"],
        i["discount_factor"],
    )


@pytest.mark.skipif(not _CASES, reason="spread.json not generated (reference library offline)")
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_spread_case_matches_reference(case: dict[str, Any]) -> None:
    actual = _quantvolt_premium(case)
    ref = case["reference"]["premium"]
    tol = case["tolerance"]["premium"]
    assert within_tolerance(actual, ref, tol), (
        f"{case['case_id']} premium: {tolerance_detail(actual, ref, tol)}"
    )


@pytest.mark.skipif(not _CASES, reason="spread.json not generated (reference library offline)")
def test_margrabe_collapse_present() -> None:
    """The K=0 Margrabe-collapse cases must exist (Requirement 5.2)."""
    margrabe_cases = [c for c in _CASES if c["inputs"]["model"] == "margrabe"]
    assert margrabe_cases, "fixture should contain K=0 Margrabe-collapse cases"
    for case in margrabe_cases:
        assert case["inputs"]["strike"] == 0.0


class TestSpreadLiveQuantLib:
    """Optional maintainer-only live cross-check; skipped in CI (Requirement 7.3)."""

    def test_live_kirk_reference(self) -> None:
        ql = pytest.importorskip("QuantLib")
        if not _CASES:
            pytest.skip("spread.json not generated")
        today = ql.Date(15, 6, 2026)
        ql.Settings.instance().evaluationDate = today
        day_count = ql.Actual360()

        def process(spot: float, sigma: float, rate: float) -> Any:
            return ql.GeneralizedBlackScholesProcess(
                ql.QuoteHandle(ql.SimpleQuote(spot)),
                ql.YieldTermStructureHandle(ql.FlatForward(today, rate, day_count)),
                ql.YieldTermStructureHandle(ql.FlatForward(today, rate, day_count)),
                ql.BlackVolTermStructureHandle(
                    ql.BlackConstantVol(today, ql.NullCalendar(), sigma, day_count)
                ),
            )

        for case in _CASES:
            i = case["inputs"]
            t, df = i["time_to_expiry"], i["discount_factor"]
            rate = -math.log(df) / t
            exercise = today + ql.Period(round(t * 360.0), ql.Days)
            basket = ql.BasketOption(
                ql.SpreadBasketPayoff(ql.PlainVanillaPayoff(ql.Option.Call, i["strike"])),
                ql.EuropeanExercise(exercise),
            )
            basket.setPricingEngine(
                ql.KirkEngine(
                    process(i["forward1"], i["sigma1"], rate),
                    process(i["forward2"], i["sigma2"], rate),
                    i["rho"],
                )
            )
            assert within_tolerance(
                basket.NPV(), case["reference"]["premium"], case["tolerance"]["premium"]
            )
