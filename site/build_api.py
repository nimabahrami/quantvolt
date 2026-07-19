"""Generate the static API index from QuantVolt's public exports.

Run from the repository root: python3 site/build_api.py
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "quantvolt"
PYPROJECT = ROOT / "pyproject.toml"
OUT = ROOT / "site" / "api-data.js"
COVERAGE_OUT = ROOT / "site" / "api-coverage.json"
MODULE_ORDER = [
    "quantvolt",
    "models",
    "numerics",
    "curves",
    "pricing",
    "portfolio",
    "risk",
    "hedging",
    "assets",
    "curvemodels",
    "stats",
    "market",
    "workflow",
    "data",
    "exceptions",
    "testing",
]
MODULE_DESCRIPTIONS = {
    "quantvolt": "Curated top-level facade for the most common QuantVolt workflows.",
    "models": "Immutable domain objects for commodities, periods, curves and instruments.",
    "numerics": "Pure numerical kernels for pricing, simulation and interpolation.",
    "curves": "Forward-curve construction and no-arbitrage checks.",
    "pricing": "Energy derivatives, spreads, options and settlement pricers.",
    "portfolio": "Portfolio assembly, valuation and realized settlement.",
    "risk": "VaR, CFaR, stress scenarios, covariance and credit risk.",
    "hedging": "Variance-minimizing, cross-commodity and PPA hedging.",
    "assets": "Thermal dispatch, storage and long-dated asset valuation.",
    "curvemodels": "Stochastic single- and multi-commodity forward models.",
    "stats": "Descriptive, stationarity, correlation and mean-reversion statistics.",
    "market": "Transmission, weather and generation reliability utilities.",
    "workflow": "Criteria-driven model selection for structured products.",
    "data": "Optional provider adapters and reproducible data snapshots.",
    "exceptions": "Public exception hierarchy and actionable failure categories.",
    "testing": "Utilities for verifying QuantVolt's non-mutation contract.",
}

AUTHORED_DOCS = {
    "AsianOptionRequest": "Inputs for an Asian option calculation. Select arithmetic or geometric averaging and the requested analytic or seeded Monte Carlo method; all price, volatility, expiry, discounting, averaging and notional assumptions are explicit fields.",
    "BachelierOptionRequest": "Complete Bachelier (normal-model) call or put inputs for a forward that may be negative or zero: type, strike, notional, forward, absolute normal volatility (normal_sigma, NOT the lognormal Black-76 sigma), time to expiry and discount factor.",
    "BachelierOptionResult": "Bachelier (normal-model) option output containing the discounted premium and the complete analytical Greeks object.",
    "BarrierOptionRequest": "Inputs for an analytic barrier option. The barrier direction and knock behavior are encoded by the option/barrier type together with spot/forward, strike, barrier, volatility, expiry and discounting assumptions.",
    "CapFloorRequest": "Inputs for a cap or floor strip over aligned forward, strike, volatility, expiry and discount-factor sequences.",
    "CapFloorResult": "Aggregate cap/floor premium together with the individual caplet or floorlet contributions used to reconcile it.",
    "CommodityConfig": "Immutable commodity definition containing the stable commodity ID, human-readable name and delivery hub.",
    "ExcludedPosition": "A portfolio position omitted from a risk calculation together with the actionable reason for exclusion.",
    "ExoticOptionResult": "Typed exotic-option output containing premium, method attribution and optional Monte Carlo standard error.",
    "Hub": "Immutable market hub definition with stable ID, display name and country or market area.",
    "LookbackOptionRequest": "Inputs for a fixed- or floating-strike lookback option, including observed extrema, volatility, expiry, discounting and notional.",
    "RiskResult": "Portfolio tail-risk output containing VaR and CVaR levels, scenario P&L observations, factor ordering and excluded-position diagnostics.",
    "SwapPricingResult": "Swap valuation output containing total NPV, one forward delta per schedule period and rho for the documented parallel rate bump.",
    "ValuationSource": "Provenance tag for a valuation regime: FORWARD (liquid forward curve), PROJECTED (spot model plus corporate premium, assets.long_dated), or SIMULATED (a precomputed LSMC/dispatch cache, the CachedAssetValuation portfolio wrapper). Propagated onto a Position's tags so downstream risk code can tell the regimes apart.",
    "VanillaOptionRequest": "Complete Black–76 call or put inputs: type, strike, notional, forward, volatility, time to expiry and discount factor.",
    "VanillaOptionResult": "Vanilla option output containing discounted premium and the complete analytical Greeks object.",
    "BUILT_IN_COMMODITIES": "Read-only-by-convention registry of the package's built-in European power, gas and carbon commodity definitions, keyed by stable commodity ID.",
    "Instrument": "Public type alias for the instrument variants that a Portfolio Position can hold.",
    "InterpolationMethod": "Type alias restricting interpolation selection to the supported piecewise-flat, piecewise-linear and cubic-spline method names.",
    "INTERPOLATION_METHODS": "Registry mapping every supported interpolation method name to its numerical implementation.",
    "BUILT_IN_SCENARIOS": "Registry of named historical and hypothetical energy stress scenarios supplied with RiskEngine.",
    "MeanReversionParams": "Estimated Ornstein–Uhlenbeck parameters: mean-reversion speed, long-run level, diffusion volatility and derived half-life.",
    "NormalityTestResult": "Result of one normality test, including test identity, statistic, p-value, sample size and reject/do-not-reject conclusion.",
    "NormalityTestType": "Enumeration of supported normality-test procedures and their serialized identifiers.",
    "StationarityResult": "Stationarity-test output containing procedure, statistic, p-value, critical values, sample size and interpreted stationarity conclusion.",
    "Pipeline": "Gas pipeline description used by transmission utilities, including route identity and capacity assumptions.",
    "DEFAULT_STEPS": "Ordered seven-step model-selection workflow used when ModelingWorkflow is constructed without caller overrides.",
    "KWH_PER_THERM": "Statutory therm in kWh (29.3071), from the ICE UK NBP futures spec.",
    "MWH_PER_THERM": "Statutory therm in MWh; the base therm<->MWh conversion factor.",
    "THERMS_PER_MMBTU": "Definitional therms per MMBtu (10.0): 1 MMBtu = 1e6 Btu = 10 therms.",
    "MWH_PER_MMBTU": "MWh per MMBtu, derived from THERMS_PER_MMBTU * MWH_PER_THERM (0.293071).",
    "PENCE_PER_POUND": "Pence sterling per pound (100.0); the GBp/GBP factor for convert_price.",
}


def project_version() -> str:
    """Read the single package version source used by builds and documentation."""
    with PYPROJECT.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("pyproject.toml must define a non-empty project.version")
    return version


def parse_source(path: Path) -> ast.Module:
    """Parse package source on Python 3.11 too (PEP 695 aliases are metadata here)."""
    source = path.read_text(encoding="utf-8")
    if not hasattr(ast, "TypeAlias"):
        source = re.sub(r"^(\s*)type\s+([A-Za-z_]\w*)\s*=", r"\1\2 =", source, flags=re.MULTILINE)
        source = re.sub(
            r"^(\s*)(async\s+)?def\s+([A-Za-z_]\w*)\[[^\]]+\](\s*\()",
            r"\1\2def \3\4",
            source,
            flags=re.MULTILINE,
        )
        source = re.sub(
            r"^(\s*)class\s+([A-Za-z_]\w*)\[[^\]]+\](\s*[:(])",
            r"\1class \2\3",
            source,
            flags=re.MULTILINE,
        )
    return ast.parse(source)


def literal_all(tree: ast.Module) -> list[str]:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id == "__all__":
                value = node.value
                if value is not None:
                    try:
                        result = ast.literal_eval(value)
                        return [str(x) for x in result]
                    except (ValueError, TypeError):
                        return []
    return []


def imports(tree: ast.Module, package: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        level = node.level
        base_parts = package.split(".")
        if level:
            base_parts = base_parts[: max(1, len(base_parts) - level + 1)]
        module = ".".join(base_parts + ([node.module] if node.module else []))
        for alias in node.names:
            result[alias.asname or alias.name] = f"{module}.{alias.name}"
    return result


def source_for(qualified: str) -> tuple[Path | None, str]:
    parts = qualified.split(".")
    if len(parts) < 2 or parts[0] != "quantvolt":
        return None, parts[-1]
    symbol = parts[-1]
    if len(parts) == 2:
        return PACKAGE / "__init__.py", symbol
    module_parts = parts[1:-1]
    path = PACKAGE.joinpath(*module_parts).with_suffix(".py")
    if not path.exists():
        path = PACKAGE.joinpath(*module_parts, "__init__.py")
    return (path if path.exists() else None), symbol


def signature(node: ast.AST, name: str) -> str:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        text = ast.unparse(node.args)
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        return f"{name}({text}){returns}"
    if isinstance(node, ast.ClassDef):
        for child in node.body:
            if (
                isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and child.name == "__init__"
            ):
                args = ast.unparse(child.args)
                args = args.removeprefix("self, ").removeprefix("self")
                return f"{name}({args})"
        fields = []
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                value = f" = {ast.unparse(child.value)}" if child.value else ""
                fields.append(f"{child.target.id}: {ast.unparse(child.annotation)}{value}")
        return f"{name}({', '.join(fields)})"
    return name


def describe_symbol(public_module: str, name: str, qualified: str) -> dict[str, Any]:
    path, defined_name = source_for(qualified)
    item: dict[str, Any] = {
        "name": name,
        "module": public_module,
        "qualified": qualified,
        "kind": "constant",
        "signature": name,
        "summary": "Public package value.",
        "doc": "",
        "methods": [],
        "fields": [],
        "members": [],
        "source": "",
        "line": 1,
    }
    if path is None:
        return item
    tree = parse_source(path)
    candidates = [n for n in tree.body if getattr(n, "name", None) == defined_name]
    node = candidates[0] if candidates else None
    if node is None:
        # Re-exported through an intermediate module; resolve once more. ``imports()``'s
        # level arithmetic treats its ``package`` argument as the dotted name a bare "."
        # refers to, which is correct for an ``__init__.py`` (whose own dotted name IS its
        # package) but wrong for a leaf module (whose relative imports are relative to its
        # *containing* package, one segment shorter than its own dotted path) -- e.g.
        # ``assets/long_dated.py`` re-exporting a name via ``from ..models.instruments
        # import X``. Strip the leaf module's own segment before computing levels so both
        # cases resolve to the same (correct) Python relative-import semantics.
        module_dotted = qualified.rsplit(".", 1)[0]
        import_package = (
            module_dotted if path.name == "__init__.py" else module_dotted.rsplit(".", 1)[0]
        )
        mapping = imports(tree, import_package)
        if defined_name in mapping and mapping[defined_name] != qualified:
            return describe_symbol(public_module, name, mapping[defined_name])
    if node is not None:
        item["kind"] = "class" if isinstance(node, ast.ClassDef) else "function"
        item["signature"] = signature(node, name)
        doc = ast.get_docstring(node) or ""
        item["doc"] = doc
        item["summary"] = doc.split("\n\n", 1)[0].replace("\n", " ") if doc else item["summary"]
        item["line"] = getattr(node, "lineno", 1)
        if isinstance(node, ast.ClassDef):
            item["fields"] = [
                {
                    "name": child.target.id,
                    "type": ast.unparse(child.annotation),
                    "default": ast.unparse(child.value) if child.value else None,
                }
                for child in node.body
                if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name)
            ]
            item["members"] = [
                {"name": child.targets[0].id, "value": ast.unparse(child.value)}
                for child in node.body
                if isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
                and child.targets[0].id.isupper()
            ]
            item["methods"] = [
                {
                    "name": child.name,
                    "signature": signature(child, child.name),
                    "summary": (
                        (ast.get_docstring(child) or "").split("\n\n", 1)[0].replace("\n", " ")
                    ),
                }
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                and not child.name.startswith("_")
            ]
    if not item["doc"] and name in AUTHORED_DOCS:
        item["doc"] = AUTHORED_DOCS[name]
        item["summary"] = AUTHORED_DOCS[name].split(". ", 1)[0] + "."
    item["source"] = path.relative_to(ROOT).as_posix()
    return item


def build() -> dict[str, Any]:
    modules = []
    symbol_count = 0
    for module_name in MODULE_ORDER:
        if module_name == "quantvolt":
            init = PACKAGE / "__init__.py"
            qualified_module = "quantvolt"
        else:
            package_init = PACKAGE / module_name / "__init__.py"
            init = package_init if package_init.exists() else PACKAGE / f"{module_name}.py"
            qualified_module = f"quantvolt.{module_name}"
        tree = parse_source(init)
        exported = literal_all(tree)
        if not exported:
            exported = [
                node.name
                for node in tree.body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith("_")
            ]
        mapping = imports(tree, qualified_module)
        symbols = [
            describe_symbol(module_name, name, mapping.get(name, f"{qualified_module}.{name}"))
            for name in exported
        ]
        symbols.sort(
            key=lambda x: (
                {"class": 0, "function": 1, "constant": 2}.get(x["kind"], 3),
                x["name"].lower(),
            )
        )
        symbol_count += len(symbols)
        modules.append(
            {
                "name": module_name,
                "qualified": qualified_module,
                "description": MODULE_DESCRIPTIONS[module_name],
                "symbols": symbols,
            }
        )
    return {"version": project_version(), "modules": modules, "symbolCount": symbol_count}


if __name__ == "__main__":
    data = build()
    OUT.write_text(
        "window.API_DATA = " + json.dumps(data, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )
    coverage = {
        "version": data["version"],
        "totals": {
            "modules": len(data["modules"]),
            "symbols": data["symbolCount"],
            "documented": sum(
                bool(symbol["doc"]) for module in data["modules"] for symbol in module["symbols"]
            ),
        },
        "symbols": [
            {
                "public_path": f"{module['qualified']}.{symbol['name']}",
                "kind": symbol["kind"],
                "source": symbol["source"],
                "has_docstring": bool(symbol["doc"]),
                "has_signature": bool(symbol["signature"]),
                "has_fields_or_methods": bool(
                    symbol["fields"] or symbol["methods"] or symbol["members"]
                ),
            }
            for module in data["modules"]
            for symbol in module["symbols"]
        ],
    }
    COVERAGE_OUT.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"Generated {data['symbolCount']} symbols across {len(data['modules'])} modules "
        f"-> {OUT.relative_to(ROOT)}; coverage -> {COVERAGE_OUT.relative_to(ROOT)}"
    )
