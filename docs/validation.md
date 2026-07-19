# External validation evidence

This page presents `quantvolt`'s closed-form and Monte Carlo pricers checked against an
**independent, third-party reference implementation** — QuantLib 1.43 — plus internal
analytic-vs-Monte-Carlo convergence checks. It exists because internal unit/property tests
alone cannot rule out a shared blind spot in this codebase's own mathematics; only comparison
against a *different* implementation of the same formula does that.

**Scope.** This is validation of the pricing kernels, not of the whole library, and not of
any specific PPA/hedge/portfolio workflow built on top of them. Nothing here changes
`src/quantvolt/` behaviour: this is checked-in test data (`tests/validation/fixtures/`),
comparison tests (`tests/validation/`), and this documentation page — see
`.kiro/specs/external-validation/`.

**How to read the tables.** `Reference` is the value QuantLib 1.43 produced at fixture
*generation* time (frozen into the checked-in JSON — QuantLib is a maintainer-only
dependency-group, never installed in CI or shipped to users). `QuantVolt` is recomputed live by
the script below. `Diff` is `|QuantVolt − Reference|`. `Tolerance` is the declared bound with its
rationale. `Seed` is `n/a` for closed-form comparisons and an explicit integer for Monte Carlo
rows.

## Anti-drift check

Every number in the tables below is **pasted verbatim** from an actual run of
[`site/examples/verify_validation.py`](../site/examples/verify_validation.py):

```bash
.venv/bin/python site/examples/verify_validation.py
```

If a future change makes this script print different numbers, this page has drifted and must be
regenerated (rerun the script, re-paste its output — do not hand-edit a number).

## Black-76: premium, Greeks, implied vol vs QuantLib `blackFormula`

**Provenance** (from `tests/validation/fixtures/black76.json`, verbatim):

```json
{
  "command": "python scripts/fixtures/generate_quantlib_fixtures.py",
  "generated_utc": "2026-07-18T18:23:36.592308+00:00",
  "generator": "scripts/fixtures/gen_black76_fixtures.py",
  "python_version": "3.11.14",
  "reference_library": "QuantLib",
  "reference_library_version": "1.43"
}
```

764 cases over the grid `F/K ∈ {0.5, 0.8, 0.95, 1.0, 1.05, 1.25, 2.0}` × `σ ∈ {0.05, 0.20, 0.55,
1.00}` × `T ∈ {0.02, 0.25, 1.0, 3.0}` × `DF ∈ {1.0, 0.97, 0.85}`, calls and puts, plus degenerate
`σ = 0` / `T = 0` edges. Two representative cases (ATM, `σ=0.20`, `T=1.0`, `DF=0.97`) and both
degenerate edges are shown; all 764 cases run in
`tests/validation/test_black76_fixtures.py`.

| Case | Inputs | Reference (QuantLib 1.43) | QuantVolt | Diff | Tolerance | Seed |
|---|---|---|---|---|---|---|
| `call_F100_K100_s0.2_T1_DF0.97` premium | call, F=100, K=100, σ=0.20, T=1.0, DF=0.97 | 7.726600432 | 7.726600432 | 0.000e+00 | rel 1e-9 | n/a |
| `call_F100_K100_s0.2_T1_DF0.97` delta | (same) | 0.5236330022 | 0.5236330022 | 1.110e-16 | rel 1e-9 | n/a |
| `call_F100_K100_s0.2_T1_DF0.97` gamma | (same) | 0.01925219855 | 0.01925219855 | 3.469e-18 | rel 1e-9 | n/a |
| `call_F100_K100_s0.2_T1_DF0.97` vega | (same) | 38.50439711 | 38.50439711 | 0.000e+00 | rel 1e-9 | n/a |
| `call_F100_K100_s0.2_T1_DF0.97` implied_vol | round-trip from reference premium | 0.2 | 0.2 | 5.274e-16 | rel 1e-7 | n/a |
| `put_F100_K100_s0.2_T1_DF0.97` premium | put, F=100, K=100, σ=0.20, T=1.0, DF=0.97 | 7.726600432 | 7.726600432 | 0.000e+00 | rel 1e-9 | n/a |
| `put_F100_K100_s0.2_T1_DF0.97` delta | (same) | -0.4463669978 | -0.4463669978 | 1.110e-16 | rel 1e-9 | n/a |
| `put_F100_K100_s0.2_T1_DF0.97` gamma | (same) | 0.01925219855 | 0.01925219855 | 3.469e-18 | rel 1e-9 | n/a |
| `put_F100_K100_s0.2_T1_DF0.97` vega | (same) | 38.50439711 | 38.50439711 | 0.000e+00 | rel 1e-9 | n/a |
| `put_F100_K100_s0.2_T1_DF0.97` implied_vol | round-trip from reference premium | 0.2 | 0.2 | 5.274e-16 | rel 1e-7 | n/a |
| `degenerate_call_F100_K80_s0_T1_DF1` | call, F=100, K=80, σ=0, T=1.0, DF=1.0 | discounted intrinsic = 20 | 20 | 0 | exact identity | n/a |
| `degenerate_call_F100_K80_s0.2_T0_DF1` | call, F=100, K=80, σ=0.20, T=0, DF=1.0 | discounted intrinsic = 20 | 20 | 0 | exact identity | n/a |

**Tolerance rationale (`black76.json`, verbatim):** "premium & delta/gamma/vega rel 1e-9: both
closed forms; residual = the two normal-CDF implementations' difference (QuantLib blackFormula /
forward-native BlackCalculator, vs quantvolt black76). theta/rho rel 1e-6: 4th-order central
finite difference of the reference premium (O(h^4) truncation, ~2e-7 worst-case across the
grid). implied_vol rel 1e-7: root-finder termination." Degenerate `σ=0`/`T=0` cases assert the
documented discounted-intrinsic identity (`black76.py:88-92`), not a QuantLib inversion.

## Cap/floor strip: caplet-by-caplet vs QuantLib `blackFormula`

**Provenance** (verbatim):

```json
{
  "command": "python scripts/fixtures/generate_quantlib_fixtures.py",
  "generated_utc": "2026-07-18T18:23:36.727856+00:00",
  "generator": "scripts/fixtures/gen_capfloor_fixtures.py",
  "python_version": "3.11.14",
  "reference_library": "QuantLib",
  "reference_library_version": "1.43"
}
```

**Important scope note (from the fixture `notes`, verbatim):** "Caplet-by-caplet blackFormula
reference. QuantLib's interest-rate cap machinery (ql.Cap / BlackCapFloorEngine) is NOT used:
Ibor forwards and accrual day-counts make it not comparable to an energy cap on delivery-period
forward prices (Requirement 4.1). strip_premium == sum(caplet_premiums) is the additivity
identity." — i.e. each *caplet* forward/σ/T/DF is priced against QuantLib's `blackFormula`
individually; QuantLib's rate-cap product is a different instrument and is deliberately not used
as the reference.

3 strips / 24 caplets total (`tests/validation/test_capfloor_fixtures.py`). One 6-caplet strip
(`cap_strip0_K50_N1000_n6`, strike 50, notional 1000) shown in full:

| Case | Inputs | Reference (QuantLib 1.43) | QuantVolt | Diff | Tolerance | Seed |
|---|---|---|---|---|---|---|
| caplet[0] | F=52.0, σ=0.60, T=0.08, DF=0.995 | 4517.459195 | 4517.459195 | 0.000e+00 | rel 1e-9 | n/a |
| caplet[1] | F=48.0, σ=0.55, T=0.17, DF=0.99 | 3459.688772 | 3459.688772 | 0.000e+00 | rel 1e-9 | n/a |
| caplet[2] | F=45.0, σ=0.50, T=0.25, DF=0.985 | 2596.488389 | 2596.488389 | 3.183e-12 | rel 1e-9 | n/a |
| caplet[3] | F=47.0, σ=0.45, T=0.33, DF=0.98 | 3556.624178 | 3556.624178 | 6.821e-12 | rel 1e-9 | n/a |
| caplet[4] | F=55.0, σ=0.40, T=0.42, DF=0.975 | 8066.936741 | 8066.936741 | 0.000e+00 | rel 1e-9 | n/a |
| caplet[5] | F=60.0, σ=0.38, T=0.50, DF=0.97 | 11804.264053 | 11804.26405 | 0.000e+00 | rel 1e-9 | n/a |
| strip (Property 94 additivity) | Σ of the 6 caplets above | 34001.461326 | 34001.46133 | 7.276e-12 | rel 1e-9 | n/a |

**Tolerance rationale (verbatim):** "rel 1e-9: each caplet reference is QuantLib blackFormula on
that period's own forward/sigma/T/DF (convention-identical to `price_cap_floor`'s Black-76
caplet), so the residual is only the two normal-CDF implementations' difference. The strip
premium is the exact sum of the per-caplet references (Property 94 additivity)."

## Spread options: Kirk / Margrabe vs QuantLib's Kirk spread engine

**Provenance** (verbatim):

```json
{
  "command": "python scripts/fixtures/generate_quantlib_fixtures.py",
  "generated_utc": "2026-07-18T18:23:36.800074+00:00",
  "generator": "scripts/fixtures/gen_spread_fixtures.py",
  "python_version": "3.11.14",
  "reference_library": "QuantLib",
  "reference_library_version": "1.43"
}
```

**Mapping (from the fixture `notes`, verbatim, applies to every case):** "each leg's
GeneralizedBlackScholesProcess has dividend yield = risk-free rate (q=r) so the process spot
equals the forward; both legs share r=-ln(DF)/T so the engine discount = DF; Actual/360 with
T\*360 integer days gives an exact year fraction. model='margrabe' (K=0) compares margrabe();
model='kirk' compares kirk()."

120 cases over `K ∈ {0, 2.5, 5, 10}` × `ρ ∈ {-0.5, 0, 0.3, 0.61, 0.9}` × ≥1 vol pair × `T ∈ {0.25,
0.5, 1.0}` (`tests/validation/test_spread_fixtures.py`). Two representative cases shown:

| Case | Inputs | Reference (QuantLib 1.43) | QuantVolt | Diff | Tolerance | Seed |
|---|---|---|---|---|---|---|
| `margrabe_spark_K0_rho-0.5_T0.25_DF0.97` | F1=45, F2=30, K=0 (Margrabe collapse), σ1=0.50, σ2=0.40, ρ=-0.5, T=0.25, DF=0.97 | 15.614354483 | 15.61435448 | 0.000e+00 | rel 1e-9 | n/a |
| `kirk_spark_K2.5_rho-0.5_T0.25_DF0.97` | F1=45, F2=30, K=2.5 (Kirk), σ1=0.50, σ2=0.40, ρ=-0.5, T=0.25, DF=0.97 | 13.618859591 | 13.61885959 | 3.553e-15 | rel 1e-9 | n/a |

**Tolerance rationale (verbatim):** "rel 1e-9 (abs floor 1e-12 near zero): QuantLib KirkEngine
under the documented q=r -> spot=forward mapping is convention-identical to quantvolt
kirk/margrabe, so the residual is only the two normal-CDF implementations' difference. K=0
collapses to the exact Margrabe form and is compared against margrabe()."

## Gas storage vs cmdty-storage — BLOCKED (environment)

`tests/validation/fixtures/storage.json` does **not exist**. `scripts/fixtures/gen_storage_fixtures.py`
requires cmdty-storage, which runs on pythonnet/.NET; that runtime is unavailable in this
implementation environment, so the generator reports BLOCKED and **writes no fixture** rather
than fabricate a reference value. `tests/validation/test_storage_fixtures.py` collects zero
parametrized cases and is skipped in CI. See `.kiro/specs/external-validation/tasks.md` (Task 9)
for the full 5-case design (intrinsic, extrinsic, costs/losses, step ratchets, terminal
hard-vs-soft) and every documented parameter-mapping risk.

**In the meantime, tolerances were sized from an internal QuantVolt-only multi-method study**
(no reference library) — see
[`.kiro/specs/external-validation/storage_grid_refinement.md`](../.kiro/specs/external-validation/storage_grid_refinement.md).
It replaces the earlier single-case sweep (whose "0.00% across grids" was a grid-*alignment*
artefact) with an **exact grid-free LP cross-check** of the intrinsic DP, Richardson
extrapolation, a perfect-foresight bracket of the LSMC extrinsic, an SE calibration and a basis
probe. Results: the **intrinsic tolerance rel 0.5% holds only at a fine grid** — on *misaligned*
constant-rate cases the DP-vs-exact-LP discretisation gap is `< 0.3%` at `grid_steps = 200` but
`~2%` at `grid_steps = 50`, so the fixture must use `grid_steps ≥ 200`; the **extrinsic tolerance
rel 5%** is valid for an intrinsic-anchored case, while a material-extrinsic (flat-curve) total is
heavy-tailed and must instead be compared within an absolute `k·standard_error` band. The reported
Monte Carlo SE is verified honest (seed-to-seed std and `1/√N` scaling), and the `[1, S, S²]`
(`storage.py:571`)-vs-cubic basis spread sits within one SE. These are the tolerances the
(not-yet-generated) `storage.json` fixture will use.

## Analytic-vs-Monte-Carlo convergence

`tests/validation/test_mc_convergence.py` checks the Rust Monte Carlo engine end-to-end against
QuantVolt's *own* closed forms (not QuantLib — there is no independent MC reference here). Every
test is seeded and expresses its tolerance as `k × reported_standard_error`. One representative
row, reproduced by `verify_validation.py`:

| Case | Inputs | Closed form (QuantVolt) | Monte Carlo (QuantVolt) | Diff | Tolerance | Seed |
|---|---|---|---|---|---|---|
| Black-76 vanilla vs `asian_monte_carlo(averaging_points=1)` | F=100, K=100, σ=0.20, T=1.0, DF=0.97, 200,000 paths | 7.726600 | 7.716017 | 0.0106 | 5 × SE = 0.1427 | 42 |

The full suite additionally covers: Margrabe (exact) vs correlated-forwards MC at `K=0`; Kirk
(approximation) vs the same MC at `K≠0` with a documented bias allowance
(`max(1% × kirk, 4×SE)`); Turnbull-Wakeman vs discrete arithmetic-Asian MC (looser, documented
band — no closed reference exists for the discrete average); MC put-call parity
`call − put = DF·(F − K)`; and storage extrinsic → 0 as `σ → 1e-4`. See the module docstring in
`tests/validation/test_mc_convergence.py` for every case's exact inputs and allowance.

## Honest caveats and known limitations

- **cmdty-storage cross-check is BLOCKED on this environment** (no .NET/pythonnet runtime). The
  storage kernels (`storage_intrinsic`, `storage_value`) have **not** been checked against an
  independent third-party implementation. The strongest internal evidence is a **second,
  grid-free method**: the intrinsic DP is cross-checked against an exact linear-programming oracle
  (`tests/validation/_lp_reference.py`, run in CI by `test_storage_lp_crosscheck.py` and across a
  case family by the grid-refinement study). Two internal methods agreeing (`DP ↔ LP`) is strong
  evidence of *consistency*, not of agreement with an independent engine; that remains the job of
  the (BLOCKED) cmdty-storage fixture. Generating `storage.json` needs a .NET-capable (likely
  Linux container) environment; see the regeneration instructions below and
  `.kiro/specs/external-validation/tasks.md` Task 9.
- **Storage parameter-mapping risks**, documented so a future cmdty-storage run is not mistaken
  for a real disagreement: QuantVolt's dynamic program is **undiscounted** (cmdty-storage rates
  must be set to 0 for comparability); monthly-vs-daily re-optimisation granularity biases
  cmdty-storage `>=` QuantVolt; rate units need days-in-month scaling; QuantVolt's loss
  convention is injection buys `δ/(1−loss)` and withdrawal delivers `w·(1−loss)`
  (`storage.py:313-331`); QuantVolt's `carry_cost` has no cmdty-storage equivalent.
- **Haug (2007) secondary spread-option check is BLOCKED** — the physical book was unavailable
  at implementation time. No Haug table value was recalled from memory or fabricated; only the
  QuantLib-backed spread fixture stands.
- **Barrier and lookback options have no analytic-vs-Monte-Carlo cross-check.** The
  continuous-monitoring closed forms in `numerics/exotic.py` require a Broadie-Glasserman-Kou
  discretisation correction to be comparable to a discretely-monitored Monte Carlo simulation;
  implementing that correction was out of scope here, so this is recorded as a limitation, not
  silently skipped.
- **Greeks compared via finite difference are not independent closed forms.** `theta`/`rho` in
  the Black-76 fixture are 4th-order central finite differences *of the QuantLib premium*, not a
  second independent analytic formula — the comparison still validates QuantVolt's theta/rho
  against QuantLib's premium surface, but the residual includes finite-difference truncation
  error (hence the looser rel 1e-6 tolerance vs rel 1e-9 for premium/delta/gamma/vega).
- **This page covers pricing kernels only.** It says nothing about the correctness of PPA
  settlement accounting, portfolio aggregation, or risk-engine scenario logic — those are
  covered by this repository's unit and property test suites, not by this external-validation
  evidence.

## Regenerating the fixtures

The reference libraries are **never** a runtime or CI dependency — see the PEP 735 group below.
Regenerate a fixture only when you have the reference library installed locally:

```bash
# QuantLib-backed fixtures (black76.json, capfloor.json, spread.json)
uv sync --group validation          # installs QuantLib>=1.34 from [dependency-groups] validation
# or: uv pip install "QuantLib>=1.34"
python scripts/fixtures/gen_black76_fixtures.py
python scripts/fixtures/gen_capfloor_fixtures.py
python scripts/fixtures/gen_spread_fixtures.py

# cmdty-storage fixture (storage.json) -- requires a .NET/pythonnet-capable environment
python scripts/fixtures/gen_storage_fixtures.py
```

CI never installs the `validation` dependency group and never runs a generator script; it only
runs the fixture-comparison tests in `tests/validation/` against the checked-in JSON.

## See also

- [`.kiro/specs/external-validation/`](../.kiro/specs/external-validation/) — the full
  requirements/design/tasks for this validation work.
- [`tests/validation/fixtures/README.md`](../tests/validation/fixtures/README.md) — the fixture
  JSON schema.
- [`site/examples/verify_validation.py`](../site/examples/verify_validation.py) — the anti-drift
  script this page's numbers are pasted from.
