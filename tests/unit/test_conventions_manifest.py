"""Registry <-> ``docs/market_conventions.json`` agreement (provenance gates, check (b)).

Runs the *exact same* check as ``scripts/ci/check_provenance.py``'s ``check_registry_manifest``
-- loaded from that script by file path (not duplicated) so the pytest matrix and the standalone
CI gate can never silently drift apart. See ``.kiro/steering/provenance.md``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = REPO_ROOT / "scripts" / "ci" / "check_provenance.py"
_MANIFEST_PATH = REPO_ROOT / "docs" / "market_conventions.json"


def _load_check_provenance() -> ModuleType:
    """Import ``scripts/ci/check_provenance.py`` by path (``scripts/ci/`` is not a package)."""
    spec = importlib.util.spec_from_file_location("check_provenance", _SCRIPT_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"could not load spec for {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_check_provenance = _load_check_provenance()


def test_market_conventions_manifest_exists() -> None:
    assert _MANIFEST_PATH.exists(), f"{_MANIFEST_PATH} must exist"


def test_registry_matches_manifest_with_no_violations() -> None:
    violations = _check_provenance.check_registry_manifest()
    assert violations == [], "docs/market_conventions.json <-> BUILT_IN_COMMODITIES:\n" + "\n".join(
        violations
    )


def test_every_built_in_commodity_has_a_cited_manifest_entry() -> None:
    """A second, independently-imported cross-check: the *live* registry import must also match.

    ``check_registry_manifest`` static-parses ``commodity.py`` (by design -- the check script has
    no ``quantvolt`` dependency); this test additionally imports the real package so a future
    restructure of ``BUILT_IN_COMMODITIES`` that the static parser silently mis-parses cannot go
    unnoticed.
    """
    from quantvolt.models.commodity import BUILT_IN_COMMODITIES

    manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    commodities = manifest["commodities"]
    pending_ids = {entry["commodity_id"] for entry in manifest.get("pending", [])}

    for commodity_id, config in BUILT_IN_COMMODITIES.items():
        entry = commodities.get(commodity_id)
        assert entry is not None, f"{commodity_id} missing from market_conventions.json"
        assert entry["price_unit"] == config.price_unit, (
            f"{commodity_id}: manifest price_unit {entry['price_unit']!r} != "
            f"registry price_unit {config.price_unit!r}"
        )
        assert entry["exchange"] == config.hub.exchange, (
            f"{commodity_id}: manifest exchange {entry['exchange']!r} != "
            f"registry exchange {config.hub.exchange!r}"
        )
        if entry.get("citation_status") == "pending-verbatim":
            assert commodity_id in pending_ids, (
                f"{commodity_id}: citation_status='pending-verbatim' but not listed in the "
                "manifest's top-level 'pending' array"
            )
        else:
            source = entry.get("source", {})
            assert source.get("url") and source.get("quote") and source.get("fetched"), (
                f"{commodity_id}: source must have url/quote/fetched, or declare "
                "citation_status='pending-verbatim' with a 'pending' entry instead"
            )
