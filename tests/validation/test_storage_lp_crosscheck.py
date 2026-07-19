"""Fast CI cross-check: storage intrinsic DP vs the grid-free LP oracle (Task 8, Req 6.4).

A second, independent method for the intrinsic storage value: ``storage_intrinsic`` solves a
backward-induction DP over a discretised inventory grid; :func:`_lp_reference.storage_intrinsic_lp`
solves the *same* continuous problem exactly as a linear program (derivation in that module's
docstring, from ``storage.py`` §``_transition_coeffs`` :313-331 and base spec §2.24). The DP
value converges to the LP value **from below** as the grid refines, so the ``DP - LP`` gap is the
true inventory-discretisation error.

The case is deliberately **misaligned** (ratchets 37.3 / 29.7 land on no coarse grid) so the
discretisation error is real, not a grid-alignment artefact. Kept well under ~2s: two small DP
solves plus one tiny LP. The full multi-method study lives in
``scripts/studies/storage_grid_refinement_study.py`` (offline).
"""

from __future__ import annotations

from datetime import date

from _lp_reference import storage_intrinsic_lp  # type: ignore[import-not-found]

from quantvolt.assets.storage import StorageModel, storage_intrinsic
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod

# Intrinsic discretisation tolerance sized by the grid-refinement study: the measured worst
# DP-vs-LP relative gap at grid_steps=200 across the misaligned constant-rate case family is
# <= 0.3%; 5e-3 (0.5%) covers it with margin. See storage_grid_refinement.md.
_INTRINSIC_REL_TOL = 5e-3

_GAS = CommodityConfig(
    commodity_id="TTF",
    price_unit="EUR/MWh",
    hub=Hub(hub_id="TTF", exchange="ICE", price_unit="EUR/MWh"),
)
_PRICES = [20.0, 19.0, 21.0, 24.0, 27.0, 30.0, 32.0, 31.0, 28.0, 25.0, 22.0, 20.0]


def _curve() -> ForwardCurve:
    nodes = tuple(
        CurveNode(period=DeliveryPeriod(year=2026, month=i + 1), price=p, status="observed")
        for i, p in enumerate(_PRICES)
    )
    return ForwardCurve(commodity=_GAS, market_date=date(2026, 1, 1), nodes=nodes)


def _model() -> StorageModel:
    # Ratchets 37.3 / 29.7 deliberately miss every coarse inventory grid -> real discretisation.
    return StorageModel(
        min_inventory=0.0,
        max_inventory=100.0,
        initial_inventory=0.0,
        terminal_inventory=0.0,
        injection_rate=lambda _inv: 37.3,
        withdrawal_rate=lambda _inv: 29.7,
    )


def test_dp_matches_lp_within_intrinsic_tolerance() -> None:
    model, curve = _model(), _curve()
    lp_value = storage_intrinsic_lp(model, _PRICES)
    dp_value = storage_intrinsic(model, curve, grid_steps=200).value
    assert abs(dp_value - lp_value) <= _INTRINSIC_REL_TOL * abs(lp_value), (
        f"DP(grid=200)={dp_value} vs LP={lp_value}: "
        f"rel gap {abs(dp_value - lp_value) / abs(lp_value):.3e} > {_INTRINSIC_REL_TOL:g}"
    )


def test_dp_converges_to_lp_monotonically() -> None:
    model, curve = _model(), _curve()
    lp_value = storage_intrinsic_lp(model, _PRICES)
    coarse = storage_intrinsic(model, curve, grid_steps=50).value
    fine = storage_intrinsic(model, curve, grid_steps=200).value
    # DP is a restriction of the LP to grid points -> it never overshoots the exact optimum.
    assert coarse <= lp_value + 1e-9
    assert fine <= lp_value + 1e-9
    # Refining the grid cannot worsen the discretisation error.
    assert abs(fine - lp_value) <= abs(coarse - lp_value)
