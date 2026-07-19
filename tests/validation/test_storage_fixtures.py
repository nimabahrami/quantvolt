"""Property 92: storage fixture agreement vs cmdty-storage (Requirement 6, 7, Task 10).

Loads ``fixtures/storage.json`` (generated offline by
``scripts/fixtures/gen_storage_fixtures.py`` against cmdty-storage), recomputes QuantVolt's
``storage_intrinsic`` / ``storage_value`` per case, and asserts agreement within the Task-8
grid-refinement tolerances.

**Environment note.** The storage fixture generation is BLOCKED without a .NET runtime
(pythonnet/cmdty-storage), so ``storage.json`` is typically absent in this repo. When absent, the
parametrized cases skip cleanly (no reference library, no fabricated numbers) — exactly as the
schema test independently guards any fixture that *is* present. The QuantVolt-side tolerances are
pre-sized by ``scripts/studies/storage_grid_refinement_study.py`` (see
``.kiro/specs/external-validation/storage_grid_refinement.md``): intrinsic rel 5e-3, extrinsic
rel 5e-2.

Expected per-case input schema (what the generator writes; see its docstring):
``inputs`` carries ``case_type`` (``"intrinsic"`` | ``"extrinsic"``), the ``StorageModel`` scalar
fields, a ``ratchets`` spec (``{"kind": "constant"|"step", ...}``), the forward-curve
``prices``/``start`` and ``inventory_step``, and for extrinsic cases a ``factor_model``
(``volatility``, ``dt``, ``path_count``) and ``seed``. ``reference`` carries ``value`` (intrinsic)
or ``total`` (extrinsic).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from _fixtures import (  # type: ignore[import-not-found]
    load_cases,
    tolerance_detail,
    within_tolerance,
)

from quantvolt.assets.storage import (
    StorageFactorModel,
    StorageModel,
    storage_intrinsic,
    storage_value,
)
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod

_PROVENANCE, _CASES = load_cases("storage.json")
_IDS = [c["case_id"] for c in _CASES]

_GAS = CommodityConfig(
    commodity_id="TTF",
    price_unit="EUR/MWh",
    hub=Hub(hub_id="TTF", exchange="ICE", price_unit="EUR/MWh"),
)


def _ratchet(spec: dict[str, Any]) -> Callable[[float], float]:
    """Reconstruct a ratchet callable from a JSON spec (constant or step-by-inventory)."""
    if spec["kind"] == "constant":
        rate = float(spec["rate"])
        return lambda _inv: rate
    if spec["kind"] == "step":
        breakpoints = [(float(bp), float(r)) for bp, r in spec["steps"]]  # ascending inventory
        default = float(spec.get("above", breakpoints[-1][1]))

        def step(inv: float) -> float:
            chosen = default
            for bp, rate in breakpoints:
                if inv <= bp:
                    return rate
                chosen = rate
            return chosen

        return step
    raise ValueError(f"unknown ratchet kind {spec['kind']!r}")


def _build_model(i: dict[str, Any]) -> StorageModel:
    return StorageModel(
        min_inventory=i["min_inventory"],
        max_inventory=i["max_inventory"],
        initial_inventory=i["initial_inventory"],
        terminal_inventory=i["terminal_inventory"],
        injection_rate=_ratchet(i["injection_ratchet"]),
        withdrawal_rate=_ratchet(i["withdrawal_ratchet"]),
        injection_cost=i.get("injection_cost", 0.0),
        withdrawal_cost=i.get("withdrawal_cost", 0.0),
        injection_loss=i.get("injection_loss", 0.0),
        withdrawal_loss=i.get("withdrawal_loss", 0.0),
        carry_cost=i.get("carry_cost", 0.0),
        terminal_penalty=i.get("terminal_penalty"),
    )


def _build_curve(i: dict[str, Any]) -> ForwardCurve:
    start = i.get("start", [2026, 1])
    year0, month0 = int(start[0]), int(start[1])
    nodes = tuple(
        CurveNode(
            period=DeliveryPeriod(
                year=year0 + (month0 - 1 + idx) // 12, month=(month0 - 1 + idx) % 12 + 1
            ),
            price=float(price),
            status="observed",
        )
        for idx, price in enumerate(i["prices"])
    )
    return ForwardCurve(commodity=_GAS, market_date=date(year0, month0, 1), nodes=nodes)


_SKIP_REASON = "storage.json not generated (cmdty-storage BLOCKED: no .NET)"


@pytest.mark.skipif(not _CASES, reason=_SKIP_REASON)
@pytest.mark.parametrize("case", _CASES, ids=_IDS)
def test_storage_case_matches_reference(case: dict[str, Any]) -> None:
    i = case["inputs"]
    model = _build_model(i)
    curve = _build_curve(i)
    step = i.get("inventory_step")
    if i["case_type"] == "intrinsic":
        actual = storage_intrinsic(model, curve, inventory_step=step).value
        ref = case["reference"]["value"]
        tol = case["tolerance"]["value"]
    else:
        fm = i["factor_model"]
        factor = StorageFactorModel(
            volatility=fm["volatility"], dt=fm["dt"], path_count=fm["path_count"]
        )
        actual = storage_value(model, curve, factor, seed=i["seed"], inventory_step=step).total
        ref = case["reference"]["total"]
        tol = case["tolerance"]["total"]
    assert within_tolerance(actual, ref, tol), (
        f"{case['case_id']}: {tolerance_detail(actual, ref, tol)}"
    )


class TestStorageLiveCmdty:
    """Optional maintainer-only live cross-check; skipped without cmdty-storage (Req 7.3)."""

    def test_live_cmdty_available(self) -> None:
        pytest.importorskip("cmdty_storage")
        if not _CASES:
            pytest.skip("storage.json not generated")
        pytest.skip("live cmdty-storage recompute runs in the .NET generation environment")
