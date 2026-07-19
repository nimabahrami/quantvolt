"""QuantVolt command-line entry point."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast


class _DatasetRecordLike(Protocol):
    """Structural stand-in for ``quantvolt.data.datasets.DatasetRecord``.

    The core (including this CLI entry point) must never statically import
    ``quantvolt.data`` (Req 12.1; enforced by
    ``tests/unit/test_data_isolation.py::test_no_core_source_file_imports_the_data_layer``),
    so this protocol names only the attributes the CLI itself reads rather than importing
    the real dataclass.
    """

    dataset_id: str
    version: str
    filename: str
    size: int
    sha256: str
    format: str
    license: str
    source: str
    url: str


class _DatasetsModule(Protocol):
    """Structural type for the ``quantvolt.data.datasets`` submodule.

    ``quantvolt.data.datasets`` is imported lazily by name (rather than with a normal
    ``import`` statement) so that CLI subcommands other than ``data`` never trigger the
    optional ``quantvolt[data]`` extra's dependency (``httpx``, pulled in transitively via
    ``quantvolt.data.__init__``). This protocol lets mypy still check the call sites below
    against the submodule's real signatures without a static import of the data layer.
    """

    def list_datasets(self) -> tuple[_DatasetRecordLike, ...]: ...
    def info(self, dataset_id: str) -> _DatasetRecordLike: ...
    def fetch(self, dataset_id: str, *, force: bool = ..., offline: bool = ...) -> Path: ...
    def verify(self, dataset_id: str) -> bool: ...
    def path(self, dataset_id: str) -> Path: ...
    def remove(self, dataset_id: str) -> bool: ...


def _datasets() -> _DatasetsModule:
    """Load the optional data layer only after the CLI is invoked."""
    return cast("_DatasetsModule", import_module("quantvolt.data.datasets"))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantvolt")
    commands = parser.add_subparsers(dest="command", required=True)
    data = commands.add_parser("data", help="manage optional research datasets")
    operations = data.add_subparsers(dest="operation", required=True)
    listing = operations.add_parser("list")
    listing.add_argument("--json", action="store_true", dest="as_json")
    for name in ("info", "fetch", "verify", "path", "remove"):
        operation = operations.add_parser(name)
        operation.add_argument("dataset_id")
        if name == "fetch":
            operation.add_argument("--force", action="store_true")
            operation.add_argument("--offline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Execute the QuantVolt CLI and return a process exit status."""
    args = _parser().parse_args(argv)
    datasets = _datasets()
    if args.operation == "list":
        records = datasets.list_datasets()
        if args.as_json:
            print(json.dumps([asdict(cast(Any, record)) for record in records], indent=2))
        else:
            for record in records:
                print(f"{record.dataset_id:38} {record.version:8} {record.size:>10} bytes")
        return 0
    dataset_id = args.dataset_id
    if args.operation == "info":
        print(json.dumps(asdict(cast(Any, datasets.info(dataset_id))), indent=2))
    elif args.operation == "fetch":
        print(datasets.fetch(dataset_id, force=args.force, offline=args.offline))
    elif args.operation == "verify":
        valid = datasets.verify(dataset_id)
        print("verified" if valid else "missing or invalid")
        return 0 if valid else 1
    elif args.operation == "path":
        print(datasets.path(dataset_id))
    elif args.operation == "remove":
        print("removed" if datasets.remove(dataset_id) else "not present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
