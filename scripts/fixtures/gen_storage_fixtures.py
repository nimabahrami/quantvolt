"""OFFLINE generator: storage golden fixture vs cmdty-storage (Requirement 6, Task 9).

Maintainer-only tool (spec ``.kiro/specs/external-validation/``). Wheel-excluded, never run in
CI. Would write ``tests/validation/fixtures/storage.json``.

**ENVIRONMENT-DEPENDENT (BLOCKED without .NET).** cmdty-storage is a pythonnet/.NET package; it
is not pip-installable the way QuantLib is and needs a CLR/.NET runtime (generation likely in a
Linux container). If ``pythonnet`` (``clr``) is not importable, this script prints a BLOCKED
notice and **exits without writing any fixture** — it never fabricates reference values
(provenance rule). The QuantLib fixtures stand alone; the QuantVolt-side tolerances are pre-sized
by ``scripts/studies/storage_grid_refinement_study.py`` (Task 8). See ``docs/validation.md``.

Mathematics is cited, never restated from memory: storage LSMC valuation is base spec
``.kiro/specs/power-energy-quant-analysis/design.md`` §2.24 and Properties 64-65, kernel
``src/quantvolt/assets/storage.py`` (``storage_intrinsic`` :382, ``storage_value`` :553,
transition cash-flow conventions ``_transition_coeffs`` :313-331, LSMC basis ``[1, S, S^2]`` :571).

Five golden cases (Requirement 6.2), each echoing BOTH parameterisations (QuantVolt and
cmdty-storage) for auditability:

1. Deterministic **intrinsic** — 12-node seasonal curve, constant ratchets, zero costs, hard
   terminal (``terminal_penalty is None``). Compared to ``storage_intrinsic``.
2. Stochastic **extrinsic** — QuantVolt GBM ``sigma`` matched to a cmdty-storage mean-reversion
   ~ 0, matched path counts, both standard errors recorded. Compared to ``storage_value``.
3. **Costs + fuel-in-kind losses** — injection/withdrawal costs plus loss fractions.
4. **Step ratchets** — breakpoints on both grids (cmdty-storage ratchet interpolation set to STEP,
   not linear).
5. **Terminal both ways** — hard (``terminal_penalty is None``) vs soft (``terminal_penalty``
   set). NOTE: ``StorageModel`` has **no ``terminal_storage_npv`` callable** (only the scalar
   ``terminal_penalty``, storage.py:117,132, ``_terminal_values`` :364-371); the cmdty-storage
   terminal-value function is mapped to the linear penalty ``terminal_penalty * |ΔV|``.

Mapping risks documented per case (Requirement 6.3), each of which could otherwise be mistaken
for a real disagreement:

* **Undiscounted DP.** QuantVolt sums raw per-period cash flows with no PV discounting
  (storage.py module docstring; ``_transition_coeffs`` :313-331) -> set cmdty-storage rates to 0.
* **Granularity.** Monthly-vs-daily: use cmdty-storage monthly frequency if available; else
  document the one-sided bias (cmdty-storage >= QuantVolt from finer re-optimisation).
* **Rate units.** Per-period vs per-day rates: days-in-month scaling.
* **Loss direction.** QuantVolt injection buys ``delta/(1-loss)``, withdrawal delivers
  ``w*(1-loss)`` (``_transition_coeffs`` :313-331; module docstring :34-38).
* **Carry.** QuantVolt's ``carry_cost`` has no cmdty-storage equivalent (set 0; case 3 uses
  throughput costs instead).

Tolerances are those sized by the multi-method grid-refinement study (Task 8, Requirement 6.4;
``.kiro/specs/external-validation/storage_grid_refinement.md``) and defined as the module
constants below. The study replaced the previous single-case sweep (whose "0.00%" was a
grid-*alignment* artefact) with an exact grid-free LP cross-check, Richardson extrapolation, a
perfect-foresight bracket, SE calibration and a basis-sensitivity probe. Its two load-bearing
corrections to the old tolerances:

* the intrinsic ``rel 5e-3`` holds ONLY at a fine grid -- the measured DP-vs-LP discretisation
  gap on *misaligned* constant-rate cases is < 0.3% at ``grid_steps = 200`` but ~2% at
  ``grid_steps = 50`` -- so the fixture MUST use ``grid_steps >= INTRINSIC_MIN_GRID_STEPS``;
* the extrinsic ``rel 5e-2`` is valid only for an intrinsic-*anchored* extrinsic case; for a
  material-extrinsic (flat-curve) total the heavy-tailed MC band is tens of percent, so a
  relative % is the wrong instrument and an absolute ``EXTRINSIC_SE_MULTIPLE * standard_error``
  band must be used instead.

Usage (in a .NET-capable environment)::

    pip install cmdty-storage   # requires pythonnet / .NET
    python scripts/fixtures/gen_storage_fixtures.py
"""

from __future__ import annotations

import sys

# --- Per-case fixture tolerances, sized by the Task-8 grid-refinement study -----------------
# Source: scripts/studies/storage_grid_refinement_study.py; report
# .kiro/specs/external-validation/storage_grid_refinement.md (Requirement 6.4). These are the
# tolerances the five golden cases below will carry when the .NET generation runs.

# INTRINSIC: relative, tight -- pure inventory-grid discretisation, cross-checked against the
# exact grid-free LP oracle (tests/validation/_lp_reference.py). Valid only at a fine grid.
INTRINSIC_REL_TOL = 5e-3
# The fixture MUST discretise at least this finely: worst measured DP-vs-LP gap is < 0.3% at
# grid_steps=200 (5e-3 covers it ~2x) but ~2% at grid_steps=50 (would fail 5e-3).
INTRINSIC_MIN_GRID_STEPS = 200

# EXTRINSIC (total): relative band for an intrinsic-ANCHORED extrinsic case only -- the exact
# intrinsic dominates the total, so MC noise on the small extrinsic is << 5% of the total.
EXTRINSIC_REL_TOL = 5e-2
# For a MATERIAL-extrinsic (flat-curve) case the total is pure, heavy-tailed optionality and a
# relative % is meaningless; compare within an absolute k*standard_error band instead.
EXTRINSIC_SE_MULTIPLE = 4

# One-line rationale per golden case (Requirement 1.3 tolerance_rationale), tied to measured
# numbers in the study report. Keyed by the case_id the .NET body will emit.
TOLERANCE_RATIONALE: dict[str, str] = {
    "intrinsic_seasonal": (
        f"rel {INTRINSIC_REL_TOL:g}: intrinsic DP-vs-exact-LP discretisation gap is < 0.3% at "
        f"grid_steps >= {INTRINSIC_MIN_GRID_STEPS} (Task-8 study, C1/C3/C5); tight grid required."
    ),
    "extrinsic_seasonal": (
        f"rel {EXTRINSIC_REL_TOL:g}: seasonal curve anchors the total on the exact intrinsic, so "
        "the LSMC MC band + basis spread are << 5% of total (Task-8 study, SE calibration)."
    ),
    "costs_losses": (
        f"rel {INTRINSIC_REL_TOL:g}: intrinsic-type case; DP-vs-LP gap < 0.3% at grid_steps >= "
        f"{INTRINSIC_MIN_GRID_STEPS} with the loss/cost conventions replicated in the LP (C3)."
    ),
    "step_ratchets": (
        f"rel {INTRINSIC_REL_TOL:g}: inventory-dependent ratchet is NOT LP-representable; sized "
        "from Richardson extrapolation of the grid sweep (Task-8 study, C4). Fine grid required."
    ),
    "terminal_hard_vs_soft": (
        f"rel {INTRINSIC_REL_TOL:g}: soft-terminal split-variable LP matches the DP to < 0.3% at "
        f"grid_steps >= {INTRINSIC_MIN_GRID_STEPS} (Task-8 study, C5)."
    ),
}


def cmdty_storage_available() -> bool:
    """True only if the pythonnet CLR bridge cmdty-storage needs is importable."""
    try:
        import clr  # type: ignore[import-not-found]  # noqa: F401  (pythonnet)
    except ImportError:
        return False
    try:
        import cmdty_storage  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return False
    return True


def main() -> None:
    if not cmdty_storage_available():
        print(
            "BLOCKED-environment: cmdty-storage (pythonnet / .NET) is not available here.\n"
            "No storage.json fixture written — reference values are NEVER fabricated "
            "(provenance rule). Run this generator in a .NET-capable environment (e.g. a Linux "
            "container with pythonnet + cmdty-storage installed). The QuantLib fixtures stand "
            "alone; QuantVolt-side tolerances are pre-sized by "
            "scripts/studies/storage_grid_refinement_study.py (see docs/validation.md).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # --- .NET-capable path (not exercised in this environment) ---------------------------
    # The five-case build + BOTH-parameterisation echo + provenance write goes here, using the
    # mappings documented in this module's docstring. Left unimplemented in this environment so
    # no reference value is ever produced without a live cmdty-storage run. When implemented, it
    # must call quantvolt storage_intrinsic/storage_value for the QuantVolt echo and cmdty_storage
    # for the reference, and write via
    # scripts/fixtures/_gen_common.write_fixture("storage.json", ...).
    raise NotImplementedError(
        "cmdty-storage generation body is intentionally unimplemented in this .NET-less "
        "environment; implement against a live cmdty-storage install per the module docstring."
    )


if __name__ == "__main__":
    main()
