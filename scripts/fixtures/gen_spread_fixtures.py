"""OFFLINE generator: Kirk / Margrabe spread-option fixture vs QuantLib (Requirement 5, Task 5).

Maintainer-only tool (spec ``.kiro/specs/external-validation/``). Wheel-excluded, never run in
CI. Writes ``tests/validation/fixtures/spread.json``.

Mathematics is cited, never restated from memory: Margrabe (zero-strike exchange) and Kirk
(non-zero-strike spread) live in base spec
``.kiro/specs/power-energy-quant-analysis/design.md`` §2.9 and Property 18, kernel
``src/quantvolt/numerics/spread_models.py``.

**Reference (Requirement 5.1).** QuantLib's ``KirkEngine`` on a two-asset ``BasketOption`` with
a ``SpreadBasketPayoff(PlainVanillaPayoff(Call, K))``. The engine is *process-based*, so the
QuantVolt forward inputs are mapped verbatim as follows:

    Each leg's process is a ``GeneralizedBlackScholesProcess`` with **dividend yield set equal
    to its risk-free rate** (q = r), so the process spot equals the forward: F = S*exp((r-q)T)
    = S. Both legs share one flat rate r = -ln(DF)/T, so the engine's discount factor is
    exp(-rT) = DF. Time is measured with Actual/360 and an exercise date T*360 days out, and
    T in {0.25, 0.5, 1.0} maps to the integer day counts {90, 180, 360}, so the engine's year
    fraction equals T exactly (no day-count rounding). Under this mapping the engine's Kirk
    approximation is convention-identical to ``quantvolt.numerics.spread_models.kirk`` /
    ``margrabe``.

**Grid (Requirement 5.2).** K in {0, 2.5, 5, 10} x rho in {-0.5, 0, 0.3, 0.61, 0.9} x T in
{0.25, 0.5, 1.0}, over two forward/vol configurations (a power-vs-gas spark-spread-scale pair
and a financial pair). The K = 0 cases are the **Margrabe collapse** and are compared against
``margrabe`` (the exact exchange-option form), the K != 0 cases against ``kirk``.

**Secondary Haug (2007) reference (Requirement 5.3): BLOCKED.** The physical book is not
available in this environment, so the 3-5 transcribed Haug spread-option table values are
omitted rather than recalled from memory; the QuantLib fixtures stand alone. See docs/validation.md.

Usage::

    uv pip install "QuantLib>=1.34"
    python scripts/fixtures/gen_spread_fixtures.py
"""

from __future__ import annotations

import math
from typing import Any

import QuantLib as ql
from _gen_common import (  # type: ignore[import-not-found]
    check_within,
    tol_for,
    write_quantlib_fixture,
)

from quantvolt.numerics.spread_models import kirk, margrabe

# (label, forward1, forward2, sigma1, sigma2)
_CONFIGS = (
    ("spark", 45.0, 30.0, 0.50, 0.40),
    ("fin", 100.0, 90.0, 0.35, 0.30),
)
_STRIKES = (0.0, 2.5, 5.0, 10.0)
_RHOS = (-0.5, 0.0, 0.3, 0.61, 0.9)
_TENORS = (0.25, 0.5, 1.0)


def _make_process(
    spot: float, sigma: float, rate: float, today: ql.Date, day_count: ql.DayCounter
) -> ql.GeneralizedBlackScholesProcess:
    spot_h = ql.QuoteHandle(ql.SimpleQuote(spot))
    rate_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, rate, day_count))
    # dividend yield q = r -> process spot equals the forward.
    div_ts = ql.YieldTermStructureHandle(ql.FlatForward(today, rate, day_count))
    vol_ts = ql.BlackVolTermStructureHandle(
        ql.BlackConstantVol(today, ql.NullCalendar(), sigma, day_count)
    )
    return ql.GeneralizedBlackScholesProcess(spot_h, div_ts, rate_ts, vol_ts)


def _ql_kirk(
    forward1: float,
    forward2: float,
    strike: float,
    sigma1: float,
    sigma2: float,
    rho: float,
    t: float,
    df: float,
) -> float:
    today = ql.Date(15, 6, 2026)
    ql.Settings.instance().evaluationDate = today
    day_count = ql.Actual360()
    rate = -math.log(df) / t
    days = round(t * 360.0)
    exercise = today + ql.Period(days, ql.Days)
    process1 = _make_process(forward1, sigma1, rate, today, day_count)
    process2 = _make_process(forward2, sigma2, rate, today, day_count)
    payoff = ql.PlainVanillaPayoff(ql.Option.Call, strike)
    basket = ql.BasketOption(ql.SpreadBasketPayoff(payoff), ql.EuropeanExercise(exercise))
    basket.setPricingEngine(ql.KirkEngine(process1, process2, rho))
    return float(basket.NPV())


def _case(
    label: str,
    forward1: float,
    forward2: float,
    sigma1: float,
    sigma2: float,
    strike: float,
    rho: float,
    t: float,
    df: float,
) -> dict[str, Any]:
    reference = _ql_kirk(forward1, forward2, strike, sigma1, sigma2, rho, t, df)
    is_margrabe = strike == 0.0
    model = "margrabe" if is_margrabe else "kirk"
    if is_margrabe:
        qv = margrabe(forward1, forward2, sigma1, sigma2, rho, t, df)
    else:
        qv = kirk(forward1, forward2, strike, sigma1, sigma2, rho, t, df)

    case_id = f"{model}_{label}_K{strike:g}_rho{rho:g}_T{t:g}_DF{df:g}"
    tol = tol_for(reference, 1e-9, 1e-12)
    check_within(qv, reference, tol, f"{case_id}.premium")

    return {
        "case_id": case_id,
        "inputs": {
            "model": model,
            "forward1": forward1,
            "forward2": forward2,
            "strike": strike,
            "sigma1": sigma1,
            "sigma2": sigma2,
            "rho": rho,
            "time_to_expiry": t,
            "discount_factor": df,
        },
        "reference": {"premium": reference},
        "tolerance": {"premium": tol},
        "tolerance_rationale": (
            "rel 1e-9 (abs floor 1e-12 near zero): QuantLib KirkEngine under the documented "
            "q=r -> spot=forward mapping is convention-identical to quantvolt kirk/margrabe, so "
            "the residual is only the two normal-CDF implementations' difference. K=0 collapses "
            "to the exact Margrabe form and is compared against margrabe()."
        ),
        "notes": (
            "Mapping (verbatim): each leg's GeneralizedBlackScholesProcess has dividend yield = "
            "risk-free rate (q=r) so the process spot equals the forward; both legs share "
            "r=-ln(DF)/T so the engine discount = DF; Actual/360 with T*360 integer days gives an "
            "exact year fraction. model='margrabe' (K=0) compares margrabe(); model='kirk' "
            "compares kirk()."
        ),
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for label, f1, f2, s1, s2 in _CONFIGS:
        for strike in _STRIKES:
            for rho in _RHOS:
                for t in _TENORS:
                    cases.append(_case(label, f1, f2, s1, s2, strike, rho, t, 0.97))
    return cases


def main() -> None:
    cases = build_cases()
    path = write_quantlib_fixture("spread.json", "scripts/fixtures/gen_spread_fixtures.py", cases)
    n_margrabe = sum(1 for c in cases if c["inputs"]["model"] == "margrabe")
    n_kirk = len(cases) - n_margrabe
    print(f"wrote {path} : {len(cases)} cases ({n_margrabe} Margrabe-collapse, {n_kirk} Kirk)")


if __name__ == "__main__":
    main()
