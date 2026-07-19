# scripts/

Maintainer and CI tooling. None of this ships in the built wheel — see the
`exclude = [..., "scripts/**", ...]` entry under `[tool.maturin]` in
`pyproject.toml`. The analytics core never imports anything under this tree.

## `ci/`

CI gates, run in GitHub Actions on every push (`.github/workflows/tests.yml`,
`.github/workflows/repository-policy.yml`):

- `check_provenance.py` — anti-self-referential provenance checks (constants
  citations, commodity-registry/manifest agreement, validation-coverage
  honesty). Stdlib-only, no `quantvolt` import.
- `check_repository_size.py` — fails if a tracked ordinary Git file exceeds
  the lightweight-repository size policy.
- `check_wheel_contents.py` — verifies a built wheel contains no repository
  datasets or other bulky research files.

## `fixtures/`

Golden-reference generators, run **once by a maintainer** (never in CI) to
(re)generate `tests/validation/fixtures/*.json` against external reference
libraries:

- `_gen_common.py` — shared provenance/tolerance/fixture-writing helpers.
- `gen_black76_fixtures.py`, `gen_bachelier_fixtures.py`,
  `gen_capfloor_fixtures.py`, `gen_spread_fixtures.py` — QuantLib-backed
  generators. QuantLib installs via `uv sync --group validation` /
  `uv pip install "QuantLib>=1.34"` per `[dependency-groups]` in
  `pyproject.toml`; it is never a runtime or CI dependency.
- `generate_quantlib_fixtures.py` — umbrella script running the four
  QuantLib generators above in sequence.
- `gen_storage_fixtures.py` — cmdty-storage-backed generator. cmdty-storage's
  Python wrapper additionally requires a .NET runtime (pythonnet/CLR) — this
  is a fact about cmdty-storage, not quantvolt; users of the library never
  need it. Without a .NET-capable environment the script self-reports
  BLOCKED and writes no fixture rather than fabricate a reference value.

See `docs/validation.md` for the full regeneration workflow and
`tests/validation/fixtures/README.md` for the fixture JSON schema.

## `data/`

Research-data ETL: fetching, preparing, and verifying external market
datasets used in offline experiments and backtests. Not part of the
analytics core and not exercised in CI.

## `studies/`

Offline numerical studies. `storage_grid_refinement_study.py` sizes the
storage-fixture tolerances via a multi-method grid-refinement analysis and
writes its report into `.kiro/specs/external-validation/`.
