# Golden validation fixtures

Checked-in JSON fixtures holding **independent third-party reference values** for
`quantvolt`'s pricers. Generated **offline** by the scripts under `scripts/` from a pinned
reference library (QuantLib / cmdty-storage); compared in CI (with **no** reference library
installed) by the fast fixture-comparison tests under `tests/validation/`.

See the spec `.kiro/specs/external-validation/` (design "Fixture schema") and the evidence
page `docs/validation.md`.

## Provenance rule (hard requirement)

**No reference number is ever typed from memory.** Every number in every fixture enters the
file at generation time from the pinned reference-library run. Each file records the exact
`reference_library_version` it was produced against. Regenerate with the commands in
`docs/validation.md`; do not hand-edit reference values.

## File format

One JSON object per file, serialized with `json.dump(obj, f, indent=2, sort_keys=True)` so
regeneration produces minimal, diff-friendly changes. Each file has exactly two top-level
keys:

```jsonc
{
  "provenance": {
    "generator": "scripts/fixtures/gen_black76_fixtures.py",   // checked-in script that wrote the file
    "reference_library": "QuantLib",                    // reference library name
    "reference_library_version": "1.34",                // exact pinned version at generation
    "python_version": "3.11.14",                         // interpreter used at generation
    "generated_utc": "2026-07-18T19:35:00+00:00",       // ISO-8601 generation timestamp
    "command": "python scripts/fixtures/gen_black76_fixtures.py" // exact command run
  },
  "cases": [
    {
      "case_id": "call_F100_K100_s0.20_T1.0_DF0.97",   // unique within the file
      "inputs": { "...": "all model inputs" },           // everything QuantVolt needs to recompute
      "reference": { "premium": 7.965, "...": "..." },   // reference value(s) from the library
      "tolerance": { "premium": {"kind": "rel", "value": 1e-9} },
      "tolerance_rationale": "why this tolerance is correct",
      "notes": "optional free text (mapping risks, conventions, markers)"
    }
  ]
}
```

### Mandatory fields (enforced by `tests/validation/test_fixture_schema.py`, Property 91)

- `provenance`: `generator`, `reference_library`, `reference_library_version`,
  `python_version`, `generated_utc`, `command`.
- each `cases[]` entry: `case_id`, `inputs`, a reference value (`reference`), `tolerance`,
  `tolerance_rationale`.

### Tolerance object

`tolerance` is a mapping from an output name (e.g. `premium`, `delta`, `implied_vol`) to
`{"kind": "rel" | "abs", "value": <float>}`. `"rel"` compares `|a - b| <= value * |ref|`;
`"abs"` compares `|a - b| <= value`.

### Degenerate-edge marker

Black-76 cases at `sigma == 0` or `time_to_expiry == 0` carry `inputs.degenerate: true`. The
comparison test then asserts QuantVolt's documented discounted-intrinsic identity
(`src/quantvolt/numerics/black76.py:88-92`) rather than a QuantLib inversion.

## Files

| File | Generator | Reference | Family |
|------|-----------|-----------|--------|
| `black76.json` | `scripts/fixtures/gen_black76_fixtures.py` | QuantLib `blackFormula` | Black-76 premium / Greeks / implied vol |
| `capfloor.json` | `scripts/fixtures/gen_capfloor_fixtures.py` | QuantLib `blackFormula` (caplet-by-caplet) | cap/floor strip + additivity |
| `spread.json` | `scripts/fixtures/gen_spread_fixtures.py` | QuantLib Kirk spread engine | Kirk / Margrabe |
| `storage.json` | `scripts/fixtures/gen_storage_fixtures.py` | cmdty-storage (offline; .NET) | intrinsic / extrinsic — see caveats |
