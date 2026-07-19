"""Grid-free linear-programming oracle for the storage *intrinsic* value (test-only).

This is a **test oracle**, not product code — it lives under ``tests/`` deliberately (it is
not a public kernel and never enters ``src/quantvolt`` or the coverage manifest). It is an
*independent second method* for the intrinsic (forward-locked) storage problem: where the
shipped :func:`quantvolt.assets.storage.storage_intrinsic` solves a backward-induction
dynamic program over a **discretised inventory grid**, this module solves the **same
continuous optimisation** exactly as a linear program over per-period inject/withdraw flows.
The DP value therefore converges *to the LP value from below* as the grid is refined, and the
``DP - LP`` gap at any grid is the true inventory-discretisation error (used by
``scripts/studies/storage_grid_refinement_study.py`` and ``test_storage_lp_crosscheck.py``).

Derivation (from the documented model dynamics only — a declared independent construction)
------------------------------------------------------------------------------------------
The dynamics are cited from ``src/quantvolt/assets/storage.py`` (module docstring and
``_transition_coeffs`` :313-331) and base spec ``power-energy-quant-analysis`` §2.24; **no
formula is restated from memory** — every coefficient below mirrors ``_transition_coeffs``.

Decision variables for a horizon of ``T`` delivery periods (constant ratchets only):

* ``a_t >= 0`` — working gas *injected* in period ``t`` (``t = 0 .. T-1``);
* ``w_t >= 0`` — working gas *withdrawn* in period ``t``;
* ``V_t`` — working-gas inventory entering period ``t`` (``V_0`` fixed; ``V_1 .. V_T`` free);
* ``dp, dm >= 0`` — split terminal-deviation variables, only for a *soft* terminal target.

Inventory balance (equality): ``V_{t+1} = V_t + a_t - w_t`` with ``V_0 = initial_inventory``.

Undiscounted objective to **maximise** (exactly ``_transition_coeffs``' per-period cash flow,
summed with no present-value discounting — storage.py keeps the DP undiscounted):

    sum_t [ -a_t * P_t / (1 - injection_loss) - injection_cost * a_t     # inject leg
            + w_t * (1 - withdrawal_loss) * P_t - withdrawal_cost * w_t  # withdraw leg
            - carry_cost * V_{t+1} ]                                     # carry on end-period inv
    - terminal_penalty * (dp + dm)                                       # soft terminal (only)

Bounds: ``0 <= a_t <= injection_rate``, ``0 <= w_t <= withdrawal_rate``,
``min_inventory <= V_t <= max_inventory``. A *hard* terminal target pins
``V_T = terminal_inventory`` (a degenerate bound); a *soft* target adds
``V_T - dp + dm = terminal_inventory`` and penalises ``dp + dm`` in the objective.

Because injecting and withdrawing in the same period both cost money (loss and/or throughput
cost), any optimum uses at most one leg per period, so the LP's ``a_t - w_t`` reproduces the
DP's signed ``delta`` and the two objectives coincide in the continuous limit. With
``injection/withdrawal_cost = 0`` and no losses a simultaneous both-legs solution is merely
value-neutral, so the optimal *value* still matches.

**Applicability.** Constant ratchets only: inventory-*dependent* ratchets
(``injection_rate``/``withdrawal_rate`` varying with the fill level) make the per-period flow
bounds state-dependent and are **not** representable as a single LP — those cases fall back to
grid-refinement / Richardson extrapolation (study component 2).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from scipy.optimize import linprog

from quantvolt.assets.storage import StorageModel


@dataclass(frozen=True, slots=True)
class PreparedLp:
    """The price-invariant part of the storage-intrinsic LP (constraints only).

    ``A_eq``/``b_eq``/``bounds`` depend only on ``model`` and ``horizon`` — never on the
    per-period prices — so a caller solving the same ``(model, horizon)`` for many price
    paths (e.g. the perfect-foresight loop in ``scripts/studies/storage_grid_refinement_study.py``)
    builds this once via :func:`prepare_lp` and reuses it across paths via
    :func:`solve_prepared`, instead of rebuilding the constraint matrix per path.
    """

    horizon: int
    n_var: int
    i_a: int
    i_w: int
    i_v: int
    i_dp: int
    i_dm: int
    inj_loss: float
    wd_loss: float
    inj_cost: float
    wd_cost: float
    carry: float
    soft: bool
    terminal_penalty: float | None
    a_eq: npt.NDArray[np.float64]
    b_eq: npt.NDArray[np.float64]
    bounds: list[tuple[float, float | None]]


def prepare_lp(model: StorageModel, horizon: int) -> PreparedLp:
    """Build the constant-ratchet storage-intrinsic LP's constraints once (see module docstring).

    Requires *constant* ratchets — the injection/withdrawal rates are sampled once at
    ``min_inventory``; asserting they are flat over the operable inventory range is the
    caller's responsibility (this oracle is only invoked on constant-rate cases).
    """
    inj_rate = float(model.injection_rate(model.min_inventory))
    wd_rate = float(model.withdrawal_rate(model.min_inventory))
    inj_loss, wd_loss = model.injection_loss, model.withdrawal_loss
    inj_cost, wd_cost = model.injection_cost, model.withdrawal_cost
    carry = model.carry_cost
    v0 = model.initial_inventory
    soft = model.terminal_penalty is not None

    n_a = n_w = n_v = horizon
    n_var = n_a + n_w + n_v + (2 if soft else 0)
    i_a, i_w, i_v = 0, n_a, n_a + n_w
    i_dp, i_dm = i_v + n_v, i_v + n_v + 1

    # Inventory-balance equalities V_{t+1} - V_t - a_t + w_t = 0 (V_0 = initial).
    a_eq: list[npt.NDArray[np.float64]] = []
    b_eq: list[float] = []
    for t in range(horizon):
        row = np.zeros(n_var, dtype=np.float64)
        row[i_v + t] = 1.0
        if t >= 1:
            row[i_v + t - 1] = -1.0
        row[i_a + t] = -1.0
        row[i_w + t] = 1.0
        a_eq.append(row)
        b_eq.append(v0 if t == 0 else 0.0)
    if soft:
        row = np.zeros(n_var, dtype=np.float64)
        row[i_v + horizon - 1] = 1.0
        row[i_dp] = -1.0
        row[i_dm] = 1.0
        a_eq.append(row)
        b_eq.append(model.terminal_inventory)

    bounds: list[tuple[float, float | None]] = [(0.0, inj_rate)] * horizon + [
        (0.0, wd_rate)
    ] * horizon
    for t in range(1, horizon + 1):
        if t == horizon and not soft:
            bounds.append((model.terminal_inventory, model.terminal_inventory))
        else:
            bounds.append((model.min_inventory, model.max_inventory))
    if soft:
        bounds += [(0.0, None), (0.0, None)]

    return PreparedLp(
        horizon=horizon,
        n_var=n_var,
        i_a=i_a,
        i_w=i_w,
        i_v=i_v,
        i_dp=i_dp,
        i_dm=i_dm,
        inj_loss=inj_loss,
        wd_loss=wd_loss,
        inj_cost=inj_cost,
        wd_cost=wd_cost,
        carry=carry,
        soft=soft,
        terminal_penalty=model.terminal_penalty,
        a_eq=np.array(a_eq),
        b_eq=np.array(b_eq),
        bounds=bounds,
    )


def solve_prepared(prep: PreparedLp, prices: npt.NDArray[np.float64] | list[float]) -> float:
    """Solve the LP prepared by :func:`prepare_lp` for one ``prices`` path.

    Only the objective's price-dependent coefficients are rebuilt per call; ``A_eq``,
    ``b_eq`` and ``bounds`` are reused unchanged from ``prep``.
    """
    price = np.asarray(prices, dtype=np.float64)
    horizon = prep.horizon

    # Objective (maximise): coefficients mirror _transition_coeffs (storage.py:313-331).
    obj = np.zeros(prep.n_var, dtype=np.float64)
    obj[prep.i_a : prep.i_a + horizon] = -(price / (1.0 - prep.inj_loss)) - prep.inj_cost
    obj[prep.i_w : prep.i_w + horizon] = price * (1.0 - prep.wd_loss) - prep.wd_cost
    obj[prep.i_v : prep.i_v + horizon] -= prep.carry  # carry on each end-of-period inv
    if prep.soft:
        obj[prep.i_dp] = obj[prep.i_dm] = -float(prep.terminal_penalty or 0.0)

    result = linprog(-obj, A_eq=prep.a_eq, b_eq=prep.b_eq, bounds=prep.bounds, method="highs")
    if not result.success:
        raise RuntimeError(f"storage intrinsic LP failed: {result.message}")
    return float(-result.fun)


def storage_intrinsic_lp(
    model: StorageModel, prices: npt.NDArray[np.float64] | list[float]
) -> float:
    """Exact grid-free intrinsic value via the LP derived in this module's docstring.

    ``prices`` are the per-period delivery prices in chronological order (the forward-curve
    node prices for an intrinsic valuation, or a single realised spot path for a
    perfect-foresight bound). Requires *constant* ratchets (see :func:`prepare_lp`).

    A thin wrapper: prepares the LP once for this single ``prices`` path and solves it.
    Callers who need to solve the same ``(model, horizon)`` for many paths should call
    :func:`prepare_lp` once and :func:`solve_prepared` per path instead.
    """
    price = np.asarray(prices, dtype=np.float64)
    horizon = int(price.shape[0])
    prep = prepare_lp(model, horizon)
    return solve_prepared(prep, price)
