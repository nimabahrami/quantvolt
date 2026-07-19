"""Shared utilities for the OFFLINE external-validation fixture generators.

Maintainer-only tooling (spec ``.kiro/specs/external-validation/``). These scripts import a
reference library (QuantLib) and ``quantvolt``; they are **wheel-excluded** and **never** run
in CI. The analytics core never imports anything here.

Provenance rule (hard): every reference number written to a fixture comes from the live
pinned reference-library run in this process — never typed from memory. This module builds
the mandatory ``provenance`` block from the *actually installed* library version and writes
JSON with ``indent=2, sort_keys=True`` for diff-friendly regeneration (Requirement 1).
"""

from __future__ import annotations

import json
import platform
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES_DIR = REPO_ROOT / "tests" / "validation" / "fixtures"


def quantlib_version() -> str:
    """The exact installed QuantLib version (read live, never hard-coded)."""
    import QuantLib as ql

    return str(ql.__version__)


def make_provenance(
    generator: str, reference_library: str, version: str, command: str
) -> dict[str, str]:
    """Assemble the mandatory provenance block from the live environment (Requirement 1.2)."""
    return {
        "generator": generator,
        "reference_library": reference_library,
        "reference_library_version": version,
        "python_version": platform.python_version(),
        "generated_utc": datetime.now(UTC).isoformat(),
        "command": command,
    }


def write_fixture(name: str, provenance: dict[str, str], cases: list[dict[str, Any]]) -> Path:
    """Serialize ``{provenance, cases}`` to ``fixtures/<name>`` (indent=2, sort_keys=True)."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    path = FIXTURES_DIR / name
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"provenance": provenance, "cases": cases}, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def write_quantlib_fixture(name: str, generator_relpath: str, cases: list[dict[str, Any]]) -> Path:
    """Build the QuantLib provenance block and write the fixture, in one call.

    Wraps the ``make_provenance(reference_library="QuantLib", version=quantlib_version(),
    command=...)`` + :func:`write_fixture` sequence every QuantLib-backed generator
    (``gen_bachelier_fixtures.py``, ``gen_black76_fixtures.py``, ``gen_capfloor_fixtures.py``,
    ``gen_spread_fixtures.py``) repeated verbatim except for ``name``/``generator_relpath``.

    Args:
        name: The fixture file name (e.g. ``"bachelier.json"``), passed to :func:`write_fixture`.
        generator_relpath: The generator's own repo-relative path (e.g.
            ``"scripts/gen_bachelier_fixtures.py"``), used for both the provenance
            ``generator`` field and the ``command`` fallback.
        cases: The built case list.
    """
    provenance = make_provenance(
        generator=generator_relpath,
        reference_library="QuantLib",
        version=quantlib_version(),
        command=_cli_command() or f"python {generator_relpath}",
    )
    return write_fixture(name, provenance, cases)


def rel(value: float) -> dict[str, Any]:
    """A relative-tolerance object ``{"kind": "rel", "value": value}``."""
    return {"kind": "rel", "value": value}


def abs_(value: float) -> dict[str, Any]:
    """An absolute-tolerance object ``{"kind": "abs", "value": value}``."""
    return {"kind": "abs", "value": value}


def tol_for(reference: float, rel_value: float, abs_floor: float) -> dict[str, Any]:
    """Pick a magnitude-appropriate tolerance for one reference number.

    A relative tolerance is meaningless as ``reference -> 0`` (a deep-OTM theta of ~1e-167
    would demand ~1e-174 agreement). So when the relative bound ``rel_value*|reference|`` would
    fall below ``abs_floor``, fall back to an absolute bound ``abs_floor``; otherwise use the
    relative bound. Keeps the single-``kind`` fixture schema while staying robust near zero.
    """
    if rel_value * abs(reference) < abs_floor:
        return abs_(abs_floor)
    return rel(rel_value)


def fd_first(f: Callable[[float], float], x: float, h: float) -> float:
    """4th-order central first derivative ``[8(f(x+h)-f(x-h)) - (f(x+2h)-f(x-2h))]/(12h)``.

    Shared by every generator's finite-difference Greeks (``gen_bachelier_fixtures.py``'s
    delta/vega/theta/rho and ``gen_black76_fixtures.py``'s theta/rho), which previously each
    defined or inlined this identical stencil.
    """
    return (8.0 * (f(x + h) - f(x - h)) - (f(x + 2 * h) - f(x - 2 * h))) / (12.0 * h)


def degenerate_case(
    *,
    option_type: str,
    forward: float,
    strike: float,
    sigma: float,
    t: float,
    df: float,
    sigma_field: str,
    ql_premium: Callable[[str, float, float, float, float], float],
    qv_premium: Callable[[str, float, float, float, float, float], float],
    tolerance_rationale: str,
) -> dict[str, Any]:
    """Shared degenerate-edge (``sigma*sqrt(T) == 0``) case builder for the Black-76 and
    Bachelier QuantLib generators.

    Both generators' ``_degenerate_case`` were structurally identical apart from: the sigma
    input's field name (``sigma_field``: ``"sigma"`` for Black-76, ``"normal_sigma"`` for
    Bachelier), the model-specific ``ql_premium``/``qv_premium`` callables (both share the
    identical positional signature ``(option_type, forward, strike, sigma_or_stddev, ...,
    discount_factor)`` in both callers -- ``ql_premium``'s 4th positional arg is ``stdDev``,
    ``qv_premium``'s is ``time_to_expiry``, but that is exactly how each caller already invokes
    them), and the exact wording of ``tolerance_rationale`` (each names its own QuantLib
    function and kernel citation).
    """
    premium = ql_premium(option_type, forward, strike, 0.0, df)
    case_id = f"degenerate_{option_type}_F{forward:g}_K{strike:g}_s{sigma:g}_T{t:g}_DF{df:g}"
    tol = abs_(1e-12)
    check_within(
        qv_premium(option_type, forward, strike, sigma, t, df),
        premium,
        tol,
        f"{case_id}.premium",
    )
    return {
        "case_id": case_id,
        "inputs": {
            "option_type": option_type,
            "forward": forward,
            "strike": strike,
            sigma_field: sigma,
            "time_to_expiry": t,
            "discount_factor": df,
            "degenerate": True,
        },
        "reference": {"premium": premium},
        "tolerance": {"premium": tol},
        "tolerance_rationale": tolerance_rationale,
        "notes": (
            "degenerate edge; comparison uses the intrinsic identity, not a QuantLib inversion."
        ),
    }


def check_within(actual: float, reference: float, tol: dict[str, Any], label: str) -> None:
    """Self-check at generation time: raise if QuantVolt already disagrees with the reference.

    A generator that writes a case its own library recomputes outside tolerance would be
    checking in a broken fixture; failing loudly here (spec provenance discipline) prevents
    that. ``label`` names the offending case/field in the message.
    """
    diff = abs(actual - reference)
    kind, value = tol["kind"], float(tol["value"])
    bound = value * abs(reference) if kind == "rel" else value
    if diff > bound:
        raise AssertionError(
            f"generation self-check failed for {label}: |{actual} - {reference}| = {diff:.3e} "
            f"> {kind} bound {bound:.3e}"
        )


def _cli_command() -> str:
    """The exact command run, for the provenance ``command`` field.

    Renders ``sys.argv[0]`` relative to the repo root when possible (so the recorded command
    is the repo-relative invocation), falling back to the raw argv otherwise.
    """
    if not sys.argv:
        return ""
    script = Path(sys.argv[0]).resolve()
    try:
        script_str = str(script.relative_to(REPO_ROOT))
    except ValueError:
        script_str = sys.argv[0]
    return "python " + " ".join([script_str, *sys.argv[1:]]).strip()
