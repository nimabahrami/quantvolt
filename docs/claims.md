# Claims registry

Every quantitative or reliability claim quantvolt's documentation makes about itself, with a
pointer to the test (or CI configuration) that checks it. This page exists so a claim is never
just asserted — a reader (or a reviewer) can open the evidence file and run it.

"Evidence" below always names a file that exists in this repository at the time of writing;
where the underlying validation is not yet possible (see the storage row), that is stated
plainly rather than glossed over.

| Claim | Evidence |
| --- | --- |
| Black-76 (vanilla option, greeks, implied vol) prices agree with QuantLib 1.43 | [`tests/validation/test_black76_fixtures.py`](../tests/validation/test_black76_fixtures.py) against the checked-in [`tests/validation/fixtures/black76.json`](../tests/validation/fixtures/black76.json) (`reference_library_version: "1.43"`) |
| Bachelier (normal-model) option prices agree with QuantLib 1.43 | [`tests/validation/test_bachelier_fixtures.py`](../tests/validation/test_bachelier_fixtures.py) against [`tests/validation/fixtures/bachelier.json`](../tests/validation/fixtures/bachelier.json) (`reference_library_version: "1.43"`) |
| Kirk (and Margrabe) spread-option prices agree with QuantLib 1.43 | [`tests/validation/test_spread_fixtures.py`](../tests/validation/test_spread_fixtures.py) against [`tests/validation/fixtures/spread.json`](../tests/validation/fixtures/spread.json) (`reference_library_version: "1.43"`) |
| Cap/floor (caplet-by-caplet) prices agree with QuantLib 1.43 | [`tests/validation/test_capfloor_fixtures.py`](../tests/validation/test_capfloor_fixtures.py) against [`tests/validation/fixtures/capfloor.json`](../tests/validation/fixtures/capfloor.json) (`reference_library_version: "1.43"`) |
| Same-seed Monte Carlo runs are reproducible (identical premium, standard error, and paths) | [`tests/unit/test_monte_carlo.py::test_same_seed_gives_identical_premium_and_standard_error`](../tests/unit/test_monte_carlo.py), [`tests/unit/test_correlated_mc.py::test_same_seed_gives_identical_paths`](../tests/unit/test_correlated_mc.py), [`tests/unit/test_mc_var.py::test_same_seed_gives_identical_result`](../tests/unit/test_mc_var.py), and the property test [`tests/property/test_cross_cutting_properties.py::test_monte_carlo_honours_the_seed`](../tests/property/test_cross_cutting_properties.py) |
| Deterministic (non-Monte-Carlo) pricing is repeatable: identical inputs give identical outputs | [`tests/property/test_cross_cutting_properties.py::test_futures_and_swap_pricing_is_deterministic`](../tests/property/test_cross_cutting_properties.py) and `test_option_pricing_and_mark_to_market_are_deterministic` in the same file |
| Public functions never mutate caller-supplied inputs | the shared [`quantvolt.testing.assert_input_unchanged`](../src/quantvolt/testing.py) helper, used across 35 test modules, including [`tests/unit/test_curve.py::test_from_dict_does_not_mutate_input`](../tests/unit/test_curve.py) and `test_price_at_does_not_mutate_inputs` in the same file |
| Portfolio valuation reports positions of an unregistered/unpriceable type in `unpriced` rather than silently dropping or mis-valuing them | [`tests/unit/test_portfolio_valuation.py::test_unregistered_type_lands_in_unpriced_and_rest_still_valued`](../tests/unit/test_portfolio_valuation.py) and `test_all_unpriced_book_totals_zero` in the same file |
| The analytics core never imports the optional `quantvolt.data` layer, and adapter credentials never leak into a repr, error message, or snapshot | [`tests/unit/test_data_isolation.py`](../tests/unit/test_data_isolation.py) (`TestImportIsolation`, `TestCredentialSecurity`, `TestSnapshotRoundTrip` classes) |
| Wheels are built and published for Linux (x86_64, aarch64), Windows (x64), and macOS (x86_64, aarch64), plus an sdist | [`.github/workflows/release.yml`](../.github/workflows/release.yml) (`linux`, `windows`, `macos`, `sdist` jobs and their platform matrices) |
| Storage (intrinsic and extrinsic) valuation cross-checked against an external reference library | **Pending** — the cmdty-storage cross-check is blocked in this environment (no .NET/pythonnet runtime), so [`tests/validation/test_storage_fixtures.py`](../tests/validation/test_storage_fixtures.py) collects zero cases (`tests/validation/fixtures/storage.json` does not exist). In its place: an analytic-vs-Monte-Carlo convergence check ([`tests/validation/test_mc_convergence.py::test_storage_extrinsic_vanishes_at_low_vol`](../tests/validation/test_mc_convergence.py)), a DP-vs-LP intrinsic cross-check ([`tests/validation/test_storage_lp_crosscheck.py`](../tests/validation/test_storage_lp_crosscheck.py)), and an internal grid-refinement study ([`scripts/studies/storage_grid_refinement_study.py`](../scripts/studies/storage_grid_refinement_study.py)). See [`tests/validation/coverage_manifest.json`](../tests/validation/coverage_manifest.json) entries for `storage_intrinsic` / `storage_value` (`category: "blocked"`) for the full, machine-checked reasoning. |

## How this table is kept honest

- [`scripts/ci/check_provenance.py`](../scripts/ci/check_provenance.py) already enforces, separately, that every public pricing/valuation kernel has an entry in
  [`tests/validation/coverage_manifest.json`](../tests/validation/coverage_manifest.json) categorised as `external-fixture`, `internal-closed-form`, `internal-anchor`, or
  `blocked` — this page is a human-readable summary of a subset of that machine-checked registry, not a replacement for it.
- [`scripts/ci/check_docs.py`](../scripts/ci/check_docs.py) lints this file (along with the rest of the public docs) for banned marketing phrases, stray internal-spec
  references, and double punctuation, so claims stay in a factual, evidence-first register.
