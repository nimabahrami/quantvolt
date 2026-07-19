"""Shared helpers for the external-validation fixture-comparison tests.

Pure-stdlib fixture loading — **no reference library is imported here**, so the whole
``tests/validation/`` tree runs in CI with only ``quantvolt`` + stdlib installed
(spec ``.kiro/specs/external-validation/`` design "CI plane"). The offline generator
scripts under ``scripts/`` are the only code that imports QuantLib / cmdty-storage.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES_DIR = Path(__file__).parent / "fixtures"

# Mandatory keys enforced by Property 91 (Requirement 1.2 / 1.3).
REQUIRED_PROVENANCE_FIELDS = (
    "generator",
    "reference_library",
    "reference_library_version",
    "python_version",
    "generated_utc",
    "command",
)
REQUIRED_CASE_FIELDS = ("case_id", "inputs", "reference", "tolerance", "tolerance_rationale")


def fixture_paths() -> list[Path]:
    """Every ``*.json`` fixture on disk, sorted for deterministic test ordering."""
    return sorted(FIXTURES_DIR.glob("*.json"))


def load_fixture(path: Path) -> dict[str, Any]:
    """Parse one fixture file into a dict (raises on malformed JSON — a hard failure)."""
    with path.open(encoding="utf-8") as handle:
        obj: dict[str, Any] = json.load(handle)
    return obj


def load_cases(name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(provenance, cases)`` for the fixture file ``fixtures/<name>``.

    A missing fixture returns an empty case list rather than raising, so a
    comparison suite whose fixture has not yet been generated (or is BLOCKED on an
    unavailable reference environment) collects to zero parametrized cases instead of
    erroring at import time. The schema test (Property 91) independently guards every
    file that *is* present.
    """
    path = FIXTURES_DIR / name
    if not path.exists():
        return {}, []
    obj = load_fixture(path)
    return obj.get("provenance", {}), list(obj.get("cases", []))


def within_tolerance(actual: float, reference: float, tol: dict[str, Any]) -> bool:
    """True if ``actual`` matches ``reference`` within a ``{"kind", "value"}`` bound."""
    kind = tol["kind"]
    value = float(tol["value"])
    diff = abs(actual - reference)
    if kind == "rel":
        return diff <= value * abs(reference)
    if kind == "abs":
        return diff <= value
    raise ValueError(f"unknown tolerance kind {kind!r} (expected 'rel' or 'abs')")


def tolerance_detail(actual: float, reference: float, tol: dict[str, Any]) -> str:
    """Human-readable diff/bound string for assertion messages."""
    kind = tol["kind"]
    value = float(tol["value"])
    diff = abs(actual - reference)
    if kind == "rel":
        bound = value * abs(reference)
        return f"|{actual} - {reference}| = {diff:.3e} > rel bound {value:g}*|ref| = {bound:.3e}"
    return f"|{actual} - {reference}| = {diff:.3e} > abs bound {value:g}"
