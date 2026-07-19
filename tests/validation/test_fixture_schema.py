"""Property 91: fixture provenance & case-field completeness (Requirement 1, 7.2).

Loads every ``tests/validation/fixtures/*.json``, asserts it parses and carries a complete
``provenance`` block and that every case carries the mandatory fields. Runs with **no**
reference library installed (spec ``.kiro/specs/external-validation/`` design "CI plane").

A malformed or provenance-incomplete fixture is a hard test failure, never a skip
(design "Error handling").
"""

from __future__ import annotations

from pathlib import Path

import pytest
from _fixtures import (  # type: ignore[import-not-found]
    REQUIRED_CASE_FIELDS,
    REQUIRED_PROVENANCE_FIELDS,
    fixture_paths,
    load_fixture,
)

_PATHS = fixture_paths()


def test_fixtures_directory_exists() -> None:
    from _fixtures import FIXTURES_DIR  # type: ignore[import-not-found]

    assert FIXTURES_DIR.is_dir()


@pytest.mark.skipif(not _PATHS, reason="no fixtures generated yet (reference library offline)")
@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_fixture_parses_and_has_top_level_keys(path: Path) -> None:
    obj = load_fixture(path)
    assert isinstance(obj, dict), f"{path.name}: top level must be a JSON object"
    assert "provenance" in obj, f"{path.name}: missing top-level 'provenance'"
    assert "cases" in obj, f"{path.name}: missing top-level 'cases'"
    assert isinstance(obj["cases"], list), f"{path.name}: 'cases' must be a list"
    assert obj["cases"], f"{path.name}: 'cases' must be non-empty"


@pytest.mark.skipif(not _PATHS, reason="no fixtures generated yet (reference library offline)")
@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_provenance_complete(path: Path) -> None:
    provenance = load_fixture(path)["provenance"]
    for field in REQUIRED_PROVENANCE_FIELDS:
        assert field in provenance, f"{path.name}: provenance missing {field!r}"
        assert provenance[field], f"{path.name}: provenance {field!r} is empty"


@pytest.mark.skipif(not _PATHS, reason="no fixtures generated yet (reference library offline)")
@pytest.mark.parametrize("path", _PATHS, ids=lambda p: p.name)
def test_every_case_has_required_fields(path: Path) -> None:
    cases = load_fixture(path)["cases"]
    seen: set[str] = set()
    for index, case in enumerate(cases):
        for field in REQUIRED_CASE_FIELDS:
            assert field in case, f"{path.name}: case[{index}] missing {field!r}"
        case_id = case["case_id"]
        assert case_id not in seen, f"{path.name}: duplicate case_id {case_id!r}"
        seen.add(case_id)
