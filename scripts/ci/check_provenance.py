"""Anti-self-referential provenance gates (stdlib-only, no quantvolt import).

Three mechanical checks that make it hard for a market convention, constant, or pricing
kernel to ship without an external, cited source -- the failure mode that let
"TTF: EUR/MBtu" (a wrong currency-per-unit pairing) survive every internal review:

  (a) **Constants provenance**: every module-level ``UPPER_SNAKE = <numeric literal>``
      assignment in ``src/quantvolt/models/*.py`` and ``src/quantvolt/numerics/*.py`` must
      carry a ``# source:`` comment on the same or immediately preceding line (leading-
      underscore names are exempt as internal tolerances, not world-facing facts). A module
      may instead declare a ``provenance:`` scope statement in its module docstring, which
      exempts every constant in that module -- intended for a pure-mathematical coefficient
      set (e.g. rational-approximation coefficients) citing one algorithm source for the
      whole table rather than per-coefficient.

  (b) **Registry <-> manifest**: every entry in ``BUILT_IN_COMMODITIES``
      (``src/quantvolt/models/commodity.py``) must have a matching entry in
      ``docs/market_conventions.json`` with the same ``price_unit`` and ``exchange``, and
      every manifest entry must carry either a full ``source`` (``url``, ``quote``,
      ``fetched``) or a ``citation_status: "pending-verbatim"`` marker that also appears in
      the manifest's top-level ``pending`` array (visible, auditable debt -- never a silent
      gap).

  (c) **Validation coverage**: every public pricing/valuation kernel must appear in
      ``tests/validation/coverage_manifest.json``, categorised honestly as
      ``external-fixture``, ``internal-closed-form``, ``internal-anchor``, or ``blocked``,
      each with the field required to make that category checkable (a ``ref`` that exists on
      disk, or a plain-text ``justification``/``reason``).

Both the registry and the pricing/numerics module trees are parsed statically with
:mod:`ast` -- this script never imports ``quantvolt`` and has no third-party dependency, so
it runs with any Python 3.11+ interpreter, including a bare ``python3`` with no venv.

Usage::

    python scripts/ci/check_provenance.py

Exit status 0 means every check passed; 1 means at least one violation was printed.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC = REPO_ROOT / "src" / "quantvolt"

_SOURCE_COMMENT_RE = re.compile(r"#.*\bsource\s*:", re.IGNORECASE)
_PROVENANCE_DOCSTRING_RE = re.compile(r"\bprovenance\s*:", re.IGNORECASE)

_VALID_CATEGORIES = {
    "external-fixture",
    "internal-closed-form",
    "internal-anchor",
    "blocked",
}
# category -> field that must be present (and, for the fixture/closed-form categories,
# point at a file that exists) to make the category auditable rather than a bare label.
_CATEGORY_REQUIRED_FIELD = {
    "external-fixture": "ref",
    "internal-closed-form": "ref",
    "internal-anchor": "justification",
    "blocked": "reason",
}
_CATEGORIES_REQUIRING_EXISTING_REF = {"external-fixture", "internal-closed-form"}

# Numerics closed-form kernels named explicitly in the provenance-gates task brief, plus the
# three physical-asset kernels and the Bachelier (normal-model) kernels. The bare "bachelier"
# name is also included if a def named exactly "bachelier" ever appears (numerics/*.py) at check
# time -- see enumerate_public_kernels().
_EXPLICIT_NUMERICS_KERNELS = (
    "black76_price",
    "black76_greeks",
    "black76_implied_vol",
    "bachelier_price",
    "bachelier_greeks",
    "bachelier_implied_vol",
    "kirk",
    "margrabe",
    "kemna_vorst",
    "turnbull_wakeman",
)
_ASSET_KERNELS = ("storage_intrinsic", "storage_value", "dispatch_value")


# --- (a) Constants provenance ------------------------------------------------------------


def _is_numeric_literal(node: ast.AST | None) -> tuple[bool, Any]:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return True, node.value
    return False, None


def _assignment_targets_and_value(
    node: ast.stmt,
) -> tuple[list[ast.expr], ast.expr | None] | None:
    if isinstance(node, ast.Assign):
        return list(node.targets), node.value
    if isinstance(node, ast.AnnAssign):
        return [node.target], node.value
    return None


def check_constants_provenance() -> tuple[list[str], list[str]]:
    """Return ``(violations, escape_hatch_modules)`` for check (a)."""
    violations: list[str] = []
    escape_hatch_modules: list[str] = []

    for subdir in ("models", "numerics"):
        directory = SRC / subdir
        for path in sorted(directory.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            tree = ast.parse(source, filename=str(path))
            docstring = ast.get_docstring(tree) or ""
            has_escape_hatch = bool(_PROVENANCE_DOCSTRING_RE.search(docstring))
            rel_path = path.relative_to(REPO_ROOT)
            if has_escape_hatch:
                escape_hatch_modules.append(str(rel_path))

            for node in tree.body:
                parsed = _assignment_targets_and_value(node)
                if parsed is None:
                    continue
                targets, value = parsed
                is_literal, literal_value = _is_numeric_literal(value)
                if not is_literal:
                    continue
                for target in targets:
                    if not isinstance(target, ast.Name):
                        continue
                    name = target.id
                    if name.startswith("_") or not name.isupper():
                        continue
                    if has_escape_hatch:
                        continue
                    lineno = node.lineno
                    same_line = lines[lineno - 1] if 0 <= lineno - 1 < len(lines) else ""
                    # "immediately preceding line" is read as the contiguous block of
                    # comment-only lines directly above the assignment (idiomatic here for
                    # multi-line citations), not strictly a single physical line -- a blank
                    # or code line breaks the block.
                    preceding_block: list[str] = []
                    cursor = lineno - 2
                    while cursor >= 0 and lines[cursor].strip().startswith("#"):
                        preceding_block.append(lines[cursor])
                        cursor -= 1
                    if _SOURCE_COMMENT_RE.search(same_line) or any(
                        _SOURCE_COMMENT_RE.search(line) for line in preceding_block
                    ):
                        continue
                    violations.append(
                        f"{rel_path}:{lineno}: {name} = {literal_value!r} has no "
                        "'# source:' comment on the same or immediately preceding line "
                        "(and the module docstring declares no 'provenance:' escape hatch)"
                    )
    return violations, escape_hatch_modules


# --- (b) Registry <-> manifest ------------------------------------------------------------


def _literal(node: ast.expr | None) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _parse_built_in_commodities() -> dict[str, dict[str, str]]:
    """Static-parse ``BUILT_IN_COMMODITIES`` -> ``{commodity_id: {price_unit, exchange}}``.

    Walks the dict literal's ``CommodityConfig(commodity_id, price_unit, Hub(hub_id,
    exchange, price_unit))`` calls positionally -- no import of ``quantvolt`` required.
    """
    path = SRC / "models" / "commodity.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    registry: dict[str, dict[str, str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(t, ast.Name) and t.id == "BUILT_IN_COMMODITIES" for t in targets):
            continue
        value = node.value
        if not isinstance(value, ast.Dict):
            continue
        for key_node, value_node in zip(value.keys, value.values, strict=True):
            commodity_id = _literal(key_node)
            if not isinstance(commodity_id, str):
                continue
            if not (isinstance(value_node, ast.Call) and len(value_node.args) >= 3):
                continue
            price_unit = _literal(value_node.args[1])
            hub_call = value_node.args[2]
            exchange = None
            if isinstance(hub_call, ast.Call) and len(hub_call.args) >= 2:
                exchange = _literal(hub_call.args[1])
            registry[commodity_id] = {
                "price_unit": str(price_unit) if price_unit is not None else "",
                "exchange": str(exchange) if exchange is not None else "",
            }
    return registry


def check_registry_manifest() -> list[str]:
    """Return violations for check (b)."""
    manifest_path = REPO_ROOT / "docs" / "market_conventions.json"
    if not manifest_path.exists():
        return [f"{manifest_path.relative_to(REPO_ROOT)} does not exist"]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commodities: dict[str, dict[str, Any]] = manifest.get("commodities", {})
    pending_ids = {
        entry.get("commodity_id")
        for entry in manifest.get("pending", [])
        if isinstance(entry, dict)
    }

    registry = _parse_built_in_commodities()
    if not registry:
        return [
            "static parse of BUILT_IN_COMMODITIES in src/quantvolt/models/commodity.py "
            "found zero entries -- check the parser or the registry shape"
        ]

    violations: list[str] = []
    for commodity_id, expected in registry.items():
        entry = commodities.get(commodity_id)
        if entry is None:
            violations.append(
                f"BUILT_IN_COMMODITIES[{commodity_id!r}] has no docs/market_conventions.json "
                "commodities entry"
            )
            continue
        if entry.get("price_unit") != expected["price_unit"]:
            violations.append(
                f"{commodity_id}: manifest price_unit {entry.get('price_unit')!r} != "
                f"registry price_unit {expected['price_unit']!r}"
            )
        if entry.get("exchange") != expected["exchange"]:
            violations.append(
                f"{commodity_id}: manifest exchange {entry.get('exchange')!r} != "
                f"registry exchange {expected['exchange']!r}"
            )

        citation_status = entry.get("citation_status")
        source = entry.get("source")
        if citation_status == "pending-verbatim":
            if not (isinstance(source, dict) and source.get("url")):
                violations.append(
                    f"{commodity_id}: citation_status='pending-verbatim' requires source.url"
                )
            if commodity_id not in pending_ids:
                violations.append(
                    f"{commodity_id}: citation_status='pending-verbatim' but not listed "
                    "in the manifest's top-level 'pending' array"
                )
        elif citation_status is not None:
            violations.append(f"{commodity_id}: unknown citation_status {citation_status!r}")
        else:
            required = ("url", "quote", "fetched")
            missing = [f for f in required if not (isinstance(source, dict) and source.get(f))]
            if missing:
                violations.append(
                    f"{commodity_id}: source is missing {missing} (or declare "
                    "citation_status='pending-verbatim' with a source.url and a 'pending' "
                    "entry instead)"
                )

    for commodity_id in commodities:
        if commodity_id not in registry:
            violations.append(
                f"docs/market_conventions.json has a commodities entry for "
                f"{commodity_id!r} that is not in BUILT_IN_COMMODITIES (stale entry?)"
            )
    return violations


# --- (c) Validation coverage ---------------------------------------------------------------


def _top_level_defs(path: Path) -> dict[str, str]:
    """``{name: "function" | "class"}`` for every top-level def/class in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    defs: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = "function"
        elif isinstance(node, ast.ClassDef):
            defs[node.name] = "class"
    return defs


def _pricing_all_names() -> list[str]:
    path = SRC / "pricing" / "__init__.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        is_all_assign = isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        )
        if is_all_assign and isinstance(node.value, (ast.List, ast.Tuple)):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    raise RuntimeError(f"no __all__ list found in {path.relative_to(REPO_ROOT)}")


def _build_defs_map(directory: Path) -> dict[str, tuple[str, Path]]:
    """Parse every ``*.py`` in ``directory`` exactly once -> ``{name: (kind, file)}``.

    Replaces the previous ``names x files`` nested loop (which re-parsed every file once
    per ``__all__`` name) with a single parse-once pass per directory; ``enumerate_public_
    kernels`` then does an O(1) dict lookup per name instead of an O(files) scan.
    """
    defs_map: dict[str, tuple[str, Path]] = {}
    for path in sorted(directory.glob("*.py")):
        for name, kind in _top_level_defs(path).items():
            defs_map[name] = (kind, path)
    return defs_map


def enumerate_public_kernels() -> list[str]:
    """Public pricing/valuation kernels: pricing.__all__ functions (not Request/Result
    classes) + the closed-form numerics kernels + the three physical-asset kernels named in
    the provenance-gates task brief."""
    pricing_dir = SRC / "pricing"
    pricing_defs = _build_defs_map(pricing_dir)
    kernels: set[str] = set()
    for name in _pricing_all_names():
        entry = pricing_defs.get(name)
        if entry is None:
            raise RuntimeError(
                f"pricing.__all__ name {name!r} not found as a top-level def/class under "
                f"{pricing_dir.relative_to(REPO_ROOT)}/*.py"
            )
        kind, _path = entry
        if kind == "function":
            kernels.add(name)

    kernels.update(_EXPLICIT_NUMERICS_KERNELS)
    numerics_dir = SRC / "numerics"
    numerics_defs = _build_defs_map(numerics_dir)
    if "bachelier" in numerics_defs:
        kernels.add("bachelier")
    kernels.update(_ASSET_KERNELS)
    return sorted(kernels)


def check_validation_coverage() -> list[str]:
    manifest_path = REPO_ROOT / "tests" / "validation" / "coverage_manifest.json"
    if not manifest_path.exists():
        return [f"{manifest_path.relative_to(REPO_ROOT)} does not exist"]

    manifest: dict[str, dict[str, Any]] = json.loads(manifest_path.read_text(encoding="utf-8"))
    kernels = enumerate_public_kernels()

    violations: list[str] = []
    for kernel in kernels:
        entry = manifest.get(kernel)
        if entry is None:
            violations.append(
                f"public kernel {kernel!r} is missing from tests/validation/coverage_manifest.json"
            )
            continue
        category = entry.get("category")
        if category not in _VALID_CATEGORIES:
            violations.append(
                f"{kernel}: category {category!r} is not one of {sorted(_VALID_CATEGORIES)}"
            )
            continue
        field = _CATEGORY_REQUIRED_FIELD[category]
        field_value = entry.get(field)
        if not field_value or not isinstance(field_value, str):
            violations.append(
                f"{kernel}: category {category!r} requires a non-empty string {field!r} field"
            )
            continue
        if category in _CATEGORIES_REQUIRING_EXISTING_REF:
            ref_path = REPO_ROOT / field_value
            if not ref_path.exists():
                violations.append(f"{kernel}: ref {field_value!r} does not exist on disk")

    for kernel in manifest:
        if kernel.startswith("$"):
            continue  # e.g. "$comment" -- documentation, not a kernel entry
        if kernel not in kernels:
            violations.append(
                f"tests/validation/coverage_manifest.json has entry {kernel!r} that is not "
                "a currently enumerated public kernel (stale entry?)"
            )
    return violations


# --- Report ----------------------------------------------------------------------------


def main() -> int:
    constants_violations, escape_hatch_modules = check_constants_provenance()
    registry_violations = check_registry_manifest()
    coverage_violations = check_validation_coverage()

    print("=== (a) Constants provenance: src/quantvolt/{models,numerics}/*.py ===")
    if constants_violations:
        for v in constants_violations:
            print(f"  VIOLATION: {v}")
    else:
        print("  OK -- every UPPER_SNAKE numeric-literal constant has a '# source:' comment.")
    if escape_hatch_modules:
        print("  Modules using the 'provenance:' docstring escape hatch:")
        for m in escape_hatch_modules:
            print(f"    - {m}")
    else:
        print("  No modules use the 'provenance:' docstring escape hatch.")

    print("\n=== (b) Registry <-> docs/market_conventions.json ===")
    if registry_violations:
        for v in registry_violations:
            print(f"  VIOLATION: {v}")
    else:
        print("  OK -- every BUILT_IN_COMMODITIES entry matches a cited manifest entry.")

    print("\n=== (c) Validation coverage: tests/validation/coverage_manifest.json ===")
    if coverage_violations:
        for v in coverage_violations:
            print(f"  VIOLATION: {v}")
    else:
        print("  OK -- every public pricing/valuation kernel has an honest coverage entry.")

    total = len(constants_violations) + len(registry_violations) + len(coverage_violations)
    print(f"\n{total} violation(s) found.")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
