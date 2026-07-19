"""Anti-drift check for the validation evidence page (docs/validation.md, site "validation"
page). Recomputes a curated subset (~10 cases) of the checked-in QuantLib golden fixtures
under ``tests/validation/fixtures/`` and prints exactly the numbers pasted into those pages.

Runs with NO reference library installed (the reference numbers are frozen in the checked-in
fixtures, generated offline by the ``scripts/gen_*_fixtures.py`` maintainer tools against
QuantLib 1.43 -- see ``tests/validation/fixtures/README.md``). If this script's printed output
ever stops matching the page, the page has drifted and must be regenerated from a fresh run.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast

from quantvolt.numerics.black76 import black76_greeks, black76_implied_vol, black76_price
from quantvolt.numerics.monte_carlo import asian_monte_carlo
from quantvolt.numerics.spread_models import kirk, margrabe
from quantvolt.pricing.vanilla import CapFloorRequest, VanillaOptionRequest, price_cap_floor

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "validation" / "fixtures"


def _load(name: str) -> dict[str, Any]:
    with (FIXTURES_DIR / name).open(encoding="utf-8") as handle:
        result: dict[str, Any] = json.load(handle)
    return result


def _check(label: str, actual: float, reference: float, tol: dict[str, Any]) -> None:
    """Print, then assert, ``actual`` against ``reference`` within ``tol`` (a fixture
    ``{"kind": "rel"|"abs", "value": ...}`` bound)."""
    diff = abs(actual - reference)
    print(
        f"{label:<58} quantvolt={actual:.10g}  reference={reference:.10g}  "
        f"diff={diff:.3e}  tol={tol['kind']} {tol['value']:g}"
    )
    if tol["kind"] == "rel":
        assert diff <= tol["value"] * abs(reference), label
    else:
        assert diff <= tol["value"], label


def black76_section() -> None:
    fixture = _load("black76.json")
    cases = fixture["cases"]
    print("=== Black-76 vs QuantLib 1.43 (black76.json) ===")
    print("provenance:", json.dumps(fixture["provenance"], sort_keys=True))

    non_degenerate = [c for c in cases if not c["inputs"].get("degenerate")]

    def _atm_year(option_type: str) -> dict[str, Any]:
        """The at-the-money, 1-year, DF=0.97 case for ``option_type`` -- a representative,
        non-trivial illustration rather than a deep-OTM case that rounds to zero."""
        return next(
            c
            for c in non_degenerate
            if c["inputs"]["option_type"] == option_type
            and c["inputs"]["sigma"] == 0.20
            and c["inputs"]["time_to_expiry"] == 1.0
            and c["inputs"]["discount_factor"] == 0.97
            and c["inputs"]["forward"] == c["inputs"]["strike"]
        )

    degenerate_sigma0 = next(
        c for c in cases if c["inputs"].get("degenerate") and c["inputs"]["sigma"] == 0.0
    )
    degenerate_t0 = next(
        c for c in cases if c["inputs"].get("degenerate") and c["inputs"]["time_to_expiry"] == 0.0
    )

    for case in (_atm_year("call"), _atm_year("put")):
        i, ref, tol = case["inputs"], case["reference"], case["tolerance"]
        label = case["case_id"]
        args = (
            i["option_type"],
            i["forward"],
            i["strike"],
            i["sigma"],
            i["time_to_expiry"],
            i["discount_factor"],
        )
        premium = black76_price(*args)
        _check(f"premium[{label}]", premium, ref["premium"], tol["premium"])
        greeks = black76_greeks(*args)
        greek_values = (("delta", greeks.delta), ("gamma", greeks.gamma), ("vega", greeks.vega))
        for name, value in greek_values:
            if name in ref:
                _check(f"{name}[{label}]", value, ref[name], tol[name])
        if "implied_vol" in ref:
            # Recovered from the reference premium with a tight Brent tolerance (matching
            # tests/validation/test_black76_fixtures.py) so the round trip matches to rel 1e-7.
            iv = black76_implied_vol(
                i["option_type"],
                ref["premium"],
                i["forward"],
                i["strike"],
                i["time_to_expiry"],
                i["discount_factor"],
                tol=1e-12,
            )
            _check(f"implied_vol[{label}]", iv, ref["implied_vol"], tol["implied_vol"])

    for case, tag in ((degenerate_sigma0, "sigma=0"), (degenerate_t0, "T=0")):
        i = case["inputs"]
        premium = black76_price(
            i["option_type"],
            i["forward"],
            i["strike"],
            i["sigma"],
            i["time_to_expiry"],
            i["discount_factor"],
        )
        is_call = i["option_type"] == "call"
        payoff = (i["forward"] - i["strike"]) if is_call else (i["strike"] - i["forward"])
        intrinsic = i["discount_factor"] * max(payoff, 0.0)
        print(
            f"degenerate[{tag}] {case['case_id']}: "
            f"quantvolt={premium:.10g}  discounted-intrinsic={intrinsic:.10g}"
        )
        assert premium == intrinsic, case["case_id"]


def capfloor_section() -> None:
    fixture = _load("capfloor.json")
    case = fixture["cases"][0]
    print("\n=== Cap/floor strip vs QuantLib blackFormula, caplet-by-caplet (capfloor.json) ===")
    print("provenance:", json.dumps(fixture["provenance"], sort_keys=True))
    i, ref, tol = case["inputs"], case["reference"], case["tolerance"]
    option_type = cast(Literal["cap", "floor"], i["option_type"])
    request = CapFloorRequest(
        option_type=option_type,
        strike=i["strike"],
        notional=i["notional"],
        caplets=tuple(
            VanillaOptionRequest(
                option_type=option_type,
                strike=i["strike"],
                notional=i["notional"],
                forward=leg["forward"],
                sigma=leg["sigma"],
                time_to_expiry=leg["time_to_expiry"],
                discount_factor=leg["discount_factor"],
            )
            for leg in i["caplets"]
        ),
    )
    result = price_cap_floor(request)
    caplet_refs = ref["caplet_premiums"]
    caplet_pairs = zip(result.per_period, caplet_refs, strict=True)
    caplet_tol = tol["caplet_premiums"]
    for index, (per, caplet_ref) in enumerate(caplet_pairs):
        _check(f"caplet[{index}] {case['case_id']}", per.premium, caplet_ref, caplet_tol)
    _check(f"strip {case['case_id']}", result.premium, ref["strip_premium"], tol["strip_premium"])


def spread_section() -> None:
    fixture = _load("spread.json")
    cases = fixture["cases"]
    print("\n=== Kirk / Margrabe vs QuantLib Kirk spread engine (spread.json) ===")
    print("provenance:", json.dumps(fixture["provenance"], sort_keys=True))
    margrabe_case = next(c for c in cases if c["inputs"]["model"] == "margrabe")
    kirk_case = next(
        c for c in cases if c["inputs"]["model"] == "kirk" and c["inputs"]["strike"] > 0
    )
    for case in (margrabe_case, kirk_case):
        i, ref, tol = case["inputs"], case["reference"], case["tolerance"]
        f1, f2, s1, s2 = i["forward1"], i["forward2"], i["sigma1"], i["sigma2"]
        rho, t, df = i["rho"], i["time_to_expiry"], i["discount_factor"]
        if i["model"] == "margrabe":
            premium = margrabe(f1, f2, s1, s2, rho, t, df)
        else:
            premium = kirk(f1, f2, i["strike"], s1, s2, rho, t, df)
        _check(f"premium[{case['case_id']}]", premium, ref["premium"], tol["premium"])


def mc_convergence_section() -> None:
    """One seeded analytic-vs-MC convergence check (mirrors test_mc_convergence.py),
    reproduced here because the fixtures cover closed-form-vs-QuantLib only, not MC."""
    print("\n=== Analytic-vs-Monte-Carlo convergence sample (test_mc_convergence.py) ===")
    forward, strike, sigma, t, df = 100.0, 100.0, 0.20, 1.0, 0.97
    seed, paths, k = 42, 200_000, 5.0
    mc, se = asian_monte_carlo(forward, strike, sigma, t, df, 1, "call", False, seed, paths)
    closed = black76_price("call", forward, strike, sigma, t, df)
    diff = abs(mc - closed)
    print(
        f"black76_vanilla_vs_single_fixing_mc          mc={mc:.6f}  closed_form={closed:.6f}  "
        f"diff={diff:.4f}  bound={k:g}*SE={k * se:.4f}  seed={seed}  paths={paths}"
    )
    assert diff <= k * se


def main() -> None:
    black76_section()
    capfloor_section()
    spread_section()
    mc_convergence_section()
    print("\nAll curated cases within declared tolerance (no reference library imported).")


if __name__ == "__main__":
    main()
