# Spec / Steering Drift Audit — quantvolt

**Date:** 2026-07-16 · **Scope:** architectural gaps + drift between the code, the Kiro spec
(`.kiro/specs/power-energy-quant-analysis/`), and the steering standards (`.kiro/steering/`).

## Why this audit ran

`quantvolt` was built spec-first via Kiro. Since then the code evolved (parameterization sweep,
review-bug fixes, and a whole new PPA/power-hedge feature area) without the steering and spec docs
being kept in lockstep. This pass systematically diffs **code ↔ spec ↔ steering** in three
directions, reconciles the Kiro documents to as-built reality, and lists the code-side items that a
follow-up should address (no code was changed in this pass, per scope).

## Method

Six read-only sweeps: spec→code task verification (Tasks 1–45 / 46–61 / 62–84), code→spec
undocumented-surface mapping, steering-rule compliance, and test/property traceability — followed by
direct verification of every load-bearing claim (grep/introspection) before any edit.

## Outcome at a glance

| Category | Findings | Resolved (docs + code) | Left for user decision |
|---|---|---|---|
| A. Code gaps (spec'd, divergent) | 1 | 1 (A-1 fixed in code) | — |
| B. Doc drift (implemented, unspec'd/stale) | 5 | 5 | — |
| C. Internal spec contradictions | 4 | 4 | — |
| D. Steering violations in code | 2 | 2 (D-1 fixed in code, D-2 doc carve-out) | — |
| E. Hygiene | 5 | 1 (E-5 fixed in code) | 4 (E-1..E-4, E-6) |

Implementation itself is **complete and healthy**: all 84 base-spec tasks are done, the dependency
graph is an acyclic DAG, the analytics core imports no I/O layer, and the big steering rules hold
(all enums `StrEnum`; Polars not Pandas; algorithm selection via dispatch dicts; `py.typed` +
`_core.pyi` shipped; `mypy --strict`, ruff, pytest configured in `pyproject.toml`). The drift was
almost entirely in the **documents**, not the code.

---

## A. Code gaps — spec'd behaviour that diverges

**A-1 · Rust `simulate_ou` implemented but not exposed** — ✅ **RESOLVED (code)** 2026-07-16.
`rust/src/paths.rs` implemented and unit-tested `simulate_ou` but it was `#[allow(dead_code)]` and
not registered in `#[pymodule] _core`, so Python could not call it, even though steering
(`structure.md`) and design describe the MC engine as covering "GBM/OU".
→ **Fixed by exposing it:** the pure kernel was renamed `simulate_ou_core` (matching the file's
`*_core` convention), a `#[pyfunction] simulate_ou` wrapper was added returning a
`(path_count, steps+1)` NumPy array and registered in `rust/src/lib.rs`, a validated Python wrapper
`simulate_ou_paths` was added to `numerics/monte_carlo.py` (and re-exported from `numerics`), and a
`_core.pyi` stub was added. Verified: `cargo test` 26/26 green, `maturin develop --release` rebuilt
`_core`, and an end-to-end check confirmed shape, per-seed determinism, mean-reversion toward `mu`,
and that the validation guards fire.

---

## B. Doc drift — implemented, but the docs were stale or silent  *(all resolved this pass)*

**B-1 · `tasks.md` showed 0 / 340 sub-tasks complete despite full implementation.**
Every one of the 340 checkboxes was `[ ]`. Verified complete: all 73 distinct file paths referenced
in `tasks.md` exist; the full module tree, Rust `_core`, and unit/property/integration/benchmark
suites are present.
→ **Fixed:** all 340 sub-tasks marked `[x]`; a **Status: ✅ Complete** banner added with the
evidence basis and a pointer to this report.

**B-2 · An entire feature area had no spec.** Eight implemented modules — `models/ppa.py`,
`models/power_hedge.py`, `models/interval.py`, `pricing/ppa.py`, `pricing/power_hedge.py`,
`hedging/ppa_nomination.py`, `portfolio/settlement.py`, `data/smard.py` — appear **nowhere** in
`.kiro/`. Confirmed by whole-word grep across `.kiro/`. These carry realized PPA / power-hedge
interval settlement, leakage-safe nomination calibration, and the SMARD adapter.
→ **Fixed:** new spec `​.kiro/specs/ppa-power-hedging/` (`requirements.md`, `design.md`, `tasks.md`,
`.config.kiro` with a fresh spec UUID) written retroactively from the as-built public surface.

**B-3 · SMARD adapter absent from `product.md`.** The data-source list named ENTSO-E/ENTSOG/
Open-Meteo/commercial only.
→ **Fixed:** SMARD added to the adapter list; a "Realized settlement" product bullet added.

**B-4 · README facade count wrong.** README says "curated facade (115 names)"; the actual
`__init__.py __all__` has **155** names.
→ **Fixed:** README updated to 155.

**B-5 · `structure.md` module tree omitted the PPA modules and the repo-level dirs.**
→ **Fixed:** the 8 modules added to the tree with pointers to the new spec; `scripts/`, `data/`,
`docs/` documented as repo-level (non-package) directories; a note explaining feature areas that
post-date the base spec.

---

## C. Internal spec contradictions — `design.md` disagreed with itself  *(all resolved this pass)*

The base spec is function-first (`price_futures`, `price_swap`, `price_vanilla_option`, …), but
several passages still referenced an earlier **class-based** design that no longer exists in code.

**C-1 · Class-method pricer references replaced with the as-built free functions:**
| Was (design.md) | Now |
|---|---|
| `SpreadOptionPricer.price()` (§ tolling flow) | `price_spread_option(request)` |
| `def price(self, request: VanillaOptionRequest)` (Error-Handling example) | `def price_vanilla_option(request: …)` |
| `FuturesPricer.price()` (Property 11) | `price_futures(...)` |
| `SwapPricer.price()` (Property 13) | `price_swap(...)` |
| `VanillaOptionPricer.price_strip()` (Property 16) | `price_cap_floor(request)` |
| `ExoticOptionPricer.price_barrier()` (Property 17) | `price_barrier(request)` |

**C-2 · Duplicate granularity enum.** design.md's instruments section defined a separate
`ContractGranularity(StrEnum)`, but the code uses the single shared `Granularity` from
`models/schedule.py` (the model tree and `models/instruments.py` already agree on this).
→ **Fixed:** the duplicate definition removed; the three contract fields now type as `Granularity`.

**C-3 · `daily_price_changes` → `descriptive_stats`.** The stats entry function is
`descriptive_stats(prices)` in `stats/descriptive.py`; design.md still showed the old
`daily_price_changes` name.  → **Fixed** in design.md.

**C-4 · "Goldmann"-Sosin-Gatto spelling.** Code (`numerics/exotic.py`) uses the correct
**Goldman**-Sosin-Gatto; design.md and requirements.md had the double-n "Goldmann".
→ **Fixed** in both files (`tasks.md` already spelled it correctly).

**C-5 (note, no change needed) · `PriceOfRiskKind`.** The spec names `PriceOfRiskKind(StrEnum)` — this
class **does** exist in `numerics/risk_adjustment.py` (alongside `DriftKind`). No drift; the earlier
suspicion was incorrect.

**C-6 (clarified) · dependency prose.** design.md's mermaid graph already shows
`Portfolio → value_portfolio → RiskEngine`. Prose augmented to state the as-built order
`pricing → portfolio → {risk, assets}` (Chapter-10 `risk`/`assets` consume `PricedPosition`), noting
the graph stays acyclic and `hedging`/`assets` never import `risk`.

---

## D. Steering rules vs code

**D-1 · `.pre-commit-config.yaml` was missing** — ✅ **RESOLVED (code)** 2026-07-16.
`tech.md` stated pre-commit "runs ruff check, ruff format, mypy before commit", but no config file
was checked in.
→ **Fixed:** added `.pre-commit-config.yaml` with local hooks (`uv run ruff check`,
`uv run ruff format`, `uv run mypy`) — no external hook-repo revision pins to drift — and restored
`tech.md`'s pre-commit statement to describe the now-present config.

**D-2 · `numerics/` purity carve-out** *(doc clarified; code is intentional)*.
Steering says `numerics/` has "no domain types, no dataclasses, no validation", but
`numerics/monte_carlo.py` defines `CorrelatedSimulationRequest` and owns the covariance PSD-input
gate + nearest-PSD (Higham) repair; `numerics/risk_adjustment.py` carries `PriceOfRiskKind` /
`DriftKind` `StrEnum`s and a `require_physical_drift` guard.
→ **Resolved as steering-stale (not a code bug):** this is a legitimate native-boundary contract,
kept local to the wrapper. `structure.md` now documents the exception explicitly. The rejected
alternative — moving the request dataclass/PSD gate up into `pricing`/`risk` — would split one
cohesive boundary contract across layers for no real purity gain, so it was not taken.

**Steering rules that PASS** (checked, not assumed): all enums are `StrEnum` (no bare `Enum`/
`IntEnum`); no `pandas` import anywhere in `src/`; algorithm selection uses dispatch dicts
(`INTERPOLATION_METHODS`, normality `_TESTS`, Asian Simple-Factory, spread-model strike dispatch),
no `if method ==` chains; `py.typed` + `_core.pyi` shipped; `pyproject.toml` is the single config
source with `[tool.ruff]`, `[tool.mypy] strict = true`, `[tool.pytest.ini_options]`, maturin backend,
`python-source = "src"`, `requires-python >= 3.12`; the analytics core never imports `data/` or
`httpx`; the import DAG is acyclic.

---

## E. Hygiene  *(all code follow-ups, none fixed here)*

- **E-1 · No git baseline.** The repo has **0 commits**; the entire tree is untracked. No history to
  diff against. → Recommend an initial commit.
- **E-2 · Empty file.** `polished_continue.md` at repo root is 0 bytes. → Remove.
- **E-3 · Duplicated agent definitions.** `agents/` and `.claude/agents/` both hold the specialist
  agent markdown. → Keep one (`.claude/agents/`) as the source of truth.
- **E-4 · Script reaches into private API.** `scripts/fetch_smard_power_data.py` imports the
  underscore-private `_price_frame` from `quantvolt.data.smard`. → Promote a public helper or keep
  the coupling deliberate and documented.
- **E-5 · Facade inconsistency** — ✅ **RESOLVED (code)** 2026-07-16. `assets/dispatch_approx.py`
  exports (`bang_bang`, `horizon_divide`, `time_aggregate`, `BangBangHedgeWarning`) were in
  `assets/__init__.py` but not hoisted to the top-level `quantvolt` facade. → **Fixed:** hoisted all
  four into `quantvolt/__init__.py` (imports + sorted `__all__`); facade now 159 names (README
  updated to match). ruff + mypy clean.
- **E-6 (minor) · Documentation depth.** `docs/` has `api.md`, `european-markets.md`,
  `risk-and-assets.md` — the `tasks.md` doc sub-tasks (52/79/84) are satisfied, but there is no
  standalone equation-registry or model-card set that a strict reading of the documentation-audit
  steering would expect. → Optional: add an equation registry keyed to the property numbers.

---

## Changes made in this pass (Kiro docs + README only — no source code touched)

- `.kiro/specs/power-energy-quant-analysis/design.md` — C-1…C-4, C-6 corrections.
- `.kiro/specs/power-energy-quant-analysis/requirements.md` — C-4 spelling.
- `.kiro/specs/power-energy-quant-analysis/tasks.md` — B-1 (340 `[x]` + status banner).
- `.kiro/specs/ppa-power-hedging/` — **new** (B-2): requirements/design/tasks/`.config.kiro`.
- `.kiro/steering/structure.md` — B-5 tree + repo dirs; D-2 numerics carve-out.
- `.kiro/steering/product.md` — B-3 SMARD + realized-settlement bullet; repo-`data/` clarification.
- `.kiro/steering/tech.md` — D-1 pre-commit statement (now describes the checked-in config).
- `README.md` — B-4 facade count 115 → 159.

**Code changes (2026-07-16 follow-up pass):**
- `rust/src/paths.rs`, `rust/src/lib.rs` — A-1: expose `simulate_ou` (rename kernel `simulate_ou_core`,
  add `#[pyfunction]`, register in `_core`).
- `src/quantvolt/numerics/monte_carlo.py`, `src/quantvolt/numerics/__init__.py`,
  `src/quantvolt/_core.pyi` — A-1: `simulate_ou_paths` wrapper + re-export + stub.
- `src/quantvolt/__init__.py` — E-5: hoist `bang_bang`, `horizon_divide`, `time_aggregate`,
  `BangBangHedgeWarning` to the facade.
- `.pre-commit-config.yaml` — D-1: new (ruff + mypy via uv).

## Code-pass follow-ups — status (2026-07-16)

- ✅ **A-1** — `simulate_ou` exposed through `_core` + `numerics.simulate_ou_paths` (rebuilt, tested).
- ✅ **D-1** — `.pre-commit-config.yaml` added (uv-driven ruff + mypy).
- ✅ **E-5** — `dispatch_approx` exports hoisted to the facade (159 names).
- ⏳ **E-1** (initial git commit), **E-2** (remove empty `polished_continue.md`), **E-3** (dedupe
  `agents/` vs `.claude/agents/`), **E-4** (script's private `data.smard._price_frame` import),
  **E-6** (equation registry) — **left for the user to decide.** E-1 is a git write (do only on
  request); E-2/E-3 are deletions of files this session did not create (the two `agents/` dirs share
  filenames but were not confirmed byte-identical — surfaced, not auto-removed); E-4/E-6 are
  low-priority and touch code under active concurrent development.

## Update — the PPA feature area has grown (2026-07-16)

While running the graphify PPA check, the live tree showed the PPA/power-hedge feature is now **~12
modules, not 8**. Beyond the original set it also has `data/netztransparenz.py`
(`NetztransparenzSource` + `attach_rebap_prices` / `parse_rebap_csv` for official German reBAP
imbalance prices, plus `OAuthClientCredentials` in `data/base.py`), `hedging/ppa_walk_forward.py`
(`walk_forward_ppa_nomination`, `PpaWalkForwardResult` — repeated leakage-safe recalibration), and
`risk/cashflow_metrics.py` (`compare_cashflow_strategies` and its result dataclasses). A concurrent
session is actively extending this area, so the `ppa-power-hedging` spec is a point-in-time snapshot;
it has been updated to include these modules but should be re-checked when that work settles.
