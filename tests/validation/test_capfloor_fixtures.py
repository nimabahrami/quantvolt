"""Property 92 & 94: cap/floor strip fixture agreement + strip additivity (Req 4, 7).

Loads ``fixtures/capfloor.json``, recomputes QuantVolt's ``price_cap_floor`` for every strip, and
asserts (a) each per-period premium matches its caplet-by-caplet QuantLib reference and (b) the
strip premium equals the sum of those references (Property 94 additivity, mirroring base-spec
Property 16 / pricing/vanilla.py:117). Runs in CI with no reference library installed.
"""

from __future__ import annotations

import math
from typing import Any, Literal, cast

import pytest
from _fixtures import (  # type: ignore[import-not-found]
    load_cases,
    tolerance_detail,
    within_tolerance,
)

from quantvolt.pricing.vanilla import CapFloorRequest, VanillaOptionRequest, price_cap_floor

_PROVENANCE, _CASES = load_cases("capfloor.json")
_IDS = [c["case_id"] for c in _CASES]


def _build_request(case: dict[str, Any]) -> CapFloorRequest:
    i = case["inputs"]
    option_type = cast(Literal["cap", "floor"], i["option_type"])
    return CapFloorRequest(
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


@pytest.mark.skipif(not _CASES, reason="capfloor.json not generated (reference library offline)")
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_capfloor_per_period_matches_reference(case: dict[str, Any]) -> None:
    result = price_cap_floor(_build_request(case))
    caplet_refs = case["reference"]["caplet_premiums"]
    tol = case["tolerance"]["caplet_premiums"]
    assert len(result.per_period) == len(caplet_refs)
    for index, (per, ref) in enumerate(zip(result.per_period, caplet_refs, strict=True)):
        assert within_tolerance(per.premium, ref, tol), (
            f"{case['case_id']} caplet[{index}]: {tolerance_detail(per.premium, ref, tol)}"
        )


@pytest.mark.skipif(not _CASES, reason="capfloor.json not generated (reference library offline)")
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_strip_additivity(case: dict[str, Any]) -> None:
    """Property 94: strip premium == sum of the per-caplet references."""
    result = price_cap_floor(_build_request(case))
    strip_ref = case["reference"]["strip_premium"]
    caplet_refs = case["reference"]["caplet_premiums"]
    tol = case["tolerance"]["strip_premium"]
    # The fixture's own additivity identity.
    assert strip_ref == pytest.approx(math.fsum(caplet_refs), rel=1e-12)
    # QuantVolt's strip premium equals the summed reference.
    assert within_tolerance(result.premium, strip_ref, tol), (
        f"{case['case_id']} strip: {tolerance_detail(result.premium, strip_ref, tol)}"
    )
    # QuantVolt's own additivity (per-period sum equals the aggregate).
    assert result.premium == pytest.approx(
        math.fsum(p.premium for p in result.per_period), rel=1e-12
    )


class TestCapFloorLiveQuantLib:
    """Optional maintainer-only live cross-check; skipped in CI (Requirement 7.3)."""

    def test_live_caplet_references(self) -> None:
        ql = pytest.importorskip("QuantLib")
        if not _CASES:
            pytest.skip("capfloor.json not generated")
        ql_type = {"cap": ql.Option.Call, "floor": ql.Option.Put}
        for case in _CASES:
            i = case["inputs"]
            for leg, ref in zip(i["caplets"], case["reference"]["caplet_premiums"], strict=True):
                premium = i["notional"] * ql.blackFormula(
                    ql_type[i["option_type"]],
                    i["strike"],
                    leg["forward"],
                    leg["sigma"] * math.sqrt(leg["time_to_expiry"]),
                    leg["discount_factor"],
                )
                assert within_tolerance(premium, ref, case["tolerance"]["caplet_premiums"])
