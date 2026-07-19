"""OFFLINE generator: cap/floor strip golden fixture vs QuantLib (Requirement 4, Task 4).

Maintainer-only tool (spec ``.kiro/specs/external-validation/``). Wheel-excluded, never run in
CI. Writes ``tests/validation/fixtures/capfloor.json``.

Mathematics is cited, never restated from memory: cap/floor strip additivity is base spec
``.kiro/specs/power-energy-quant-analysis/design.md`` §2.7 and Property 16; the pricer is
``src/quantvolt/pricing/vanilla.py:117`` (``price_cap_floor``), which prices each period as an
independent Black-76 caplet/floorlet (a caplet is a call on the floating price, a floorlet a
put) and returns both the per-period results and their exact sum.

**Reference construction (Requirement 4.1).** Each caplet/floorlet reference is built
*individually* via ``QuantLib.blackFormula(type, K, F_i, sigma_i*sqrt(T_i), DF_i)`` with that
period's own forward, volatility, time-to-expiry and discount factor, scaled by the strip
notional. QuantLib's interest-rate cap machinery (``ql.Cap`` / ``ql.BlackCapFloorEngine``) is
deliberately **NOT** used: it prices Ibor-forward caplets with accrual day-counts and an index
fixing/payment schedule, which is *not comparable* to an energy cap on a delivery-period forward
price. ``blackFormula`` on each period's forward is the genuinely comparable reference.

**Strip additivity (Requirement 4.2 / Property 94).** Each case records the per-caplet
references and their sum; the comparison test asserts ``price_cap_floor(...).premium`` equals
that sum (and equals the sum of QuantVolt's own per-period premiums).

Usage::

    uv pip install "QuantLib>=1.34"
    python scripts/fixtures/gen_capfloor_fixtures.py
"""

from __future__ import annotations

import math
from typing import Any

import QuantLib as ql
from _gen_common import (  # type: ignore[import-not-found]
    check_within,
    rel,
    write_quantlib_fixture,
)

from quantvolt.pricing.vanilla import CapFloorRequest, VanillaOptionRequest, price_cap_floor

_QL_TYPE = {"cap": ql.Option.Call, "floor": ql.Option.Put}

# One caplet leg: (forward, sigma, time_to_expiry, discount_factor).
_Leg = tuple[float, float, float, float]

# Deterministic strips: (option_type, strike, notional, [(forward, sigma, T, DF), ...]).
# Forwards are seasonal; vols decline with maturity (Samuelson); DFs decline with T.
_STRIPS: tuple[tuple[str, float, float, tuple[_Leg, ...]], ...] = (
    (
        "cap",
        50.0,
        1000.0,
        (
            (52.0, 0.60, 0.08, 0.995),
            (48.0, 0.55, 0.17, 0.990),
            (45.0, 0.50, 0.25, 0.985),
            (47.0, 0.45, 0.33, 0.980),
            (55.0, 0.40, 0.42, 0.975),
            (60.0, 0.38, 0.50, 0.970),
        ),
    ),
    (
        "floor",
        50.0,
        1000.0,
        (
            (52.0, 0.60, 0.08, 0.995),
            (48.0, 0.55, 0.17, 0.990),
            (45.0, 0.50, 0.25, 0.985),
            (47.0, 0.45, 0.33, 0.980),
            (55.0, 0.40, 0.42, 0.975),
            (60.0, 0.38, 0.50, 0.970),
        ),
    ),
    (
        "cap",
        30.0,
        500.0,
        tuple(
            (
                30.0 + 5.0 * math.sin(month / 12.0 * 2.0 * math.pi),
                0.70 - 0.02 * month,
                (month + 1) / 12.0,
                0.999 - 0.004 * month,
            )
            for month in range(12)
        ),
    ),
)


def _caplet_reference(option_type: str, strike: float, notional: float, leg: _Leg) -> float:
    forward, sigma, t, df = leg
    premium = ql.blackFormula(_QL_TYPE[option_type], strike, forward, sigma * math.sqrt(t), df)
    return notional * float(premium)


def _strip_case(
    option_type: str, strike: float, notional: float, legs: tuple[_Leg, ...], index: int
) -> dict[str, Any]:
    caplet_refs = [_caplet_reference(option_type, strike, notional, leg) for leg in legs]
    strip_ref = math.fsum(caplet_refs)

    request = CapFloorRequest(
        option_type=option_type,  # type: ignore[arg-type]
        strike=strike,
        notional=notional,
        caplets=tuple(
            VanillaOptionRequest(
                option_type=option_type,  # type: ignore[arg-type]
                strike=strike,
                notional=notional,
                forward=leg[0],
                sigma=leg[1],
                time_to_expiry=leg[2],
                discount_factor=leg[3],
            )
            for leg in legs
        ),
    )
    result = price_cap_floor(request)

    case_id = f"{option_type}_strip{index}_K{strike:g}_N{notional:g}_n{len(legs)}"
    tol = rel(1e-9)
    # Generation self-check: QuantVolt per-period premiums and the strip total must already
    # agree with the caplet-by-caplet references (fail loudly on a broken fixture).
    for i, (per, ref) in enumerate(zip(result.per_period, caplet_refs, strict=True)):
        check_within(per.premium, ref, tol, f"{case_id}.caplet[{i}]")
    check_within(result.premium, strip_ref, tol, f"{case_id}.strip_premium")

    return {
        "case_id": case_id,
        "inputs": {
            "option_type": option_type,
            "strike": strike,
            "notional": notional,
            "caplets": [
                {
                    "forward": leg[0],
                    "sigma": leg[1],
                    "time_to_expiry": leg[2],
                    "discount_factor": leg[3],
                }
                for leg in legs
            ],
        },
        "reference": {
            "caplet_premiums": caplet_refs,
            "strip_premium": strip_ref,
        },
        "tolerance": {"caplet_premiums": tol, "strip_premium": tol},
        "tolerance_rationale": (
            "rel 1e-9: each caplet reference is QuantLib blackFormula on that period's own "
            "forward/sigma/T/DF (convention-identical to price_cap_floor's Black-76 caplet), so "
            "the residual is only the two normal-CDF implementations' difference. The strip "
            "premium is the exact sum of the per-caplet references (Property 94 additivity)."
        ),
        "notes": (
            "Caplet-by-caplet blackFormula reference. QuantLib's interest-rate cap machinery "
            "(ql.Cap / BlackCapFloorEngine) is NOT used: Ibor forwards and accrual day-counts "
            "make it not comparable to an energy cap on delivery-period forward prices "
            "(Requirement 4.1). strip_premium == sum(caplet_premiums) is the additivity identity."
        ),
    }


def build_cases() -> list[dict[str, Any]]:
    return [
        _strip_case(otype, strike, notional, legs, idx)
        for idx, (otype, strike, notional, legs) in enumerate(_STRIPS)
    ]


def main() -> None:
    cases = build_cases()
    path = write_quantlib_fixture(
        "capfloor.json", "scripts/fixtures/gen_capfloor_fixtures.py", cases
    )
    total_caplets = sum(len(c["reference"]["caplet_premiums"]) for c in cases)
    print(f"wrote {path} : {len(cases)} strip cases ({total_caplets} caplets total)")


if __name__ == "__main__":
    main()
