"""OFFLINE orchestrator: regenerate every QuantLib-backed validation fixture.

Maintainer-only convenience wrapper (spec ``.kiro/specs/external-validation/``). Runs the three
QuantLib generators in order (Black-76, cap/floor, spread), each of which writes a diff-friendly
``json.dump(..., indent=2, sort_keys=True)`` fixture under ``tests/validation/fixtures/`` with a
live provenance block. Wheel-excluded, never run in CI.

The cmdty-storage fixture (``scripts/fixtures/gen_storage_fixtures.py``) is NOT run here: it
needs a pythonnet/.NET runtime and is generated separately offline (see docs/validation.md).

Usage::

    uv pip install "QuantLib>=1.34"
    python scripts/fixtures/generate_quantlib_fixtures.py
"""

from __future__ import annotations

import gen_black76_fixtures  # type: ignore[import-not-found]
import gen_capfloor_fixtures  # type: ignore[import-not-found]
import gen_spread_fixtures  # type: ignore[import-not-found]


def main() -> None:
    gen_black76_fixtures.main()
    gen_capfloor_fixtures.main()
    gen_spread_fixtures.main()


if __name__ == "__main__":
    main()
