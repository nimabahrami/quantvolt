"""QuantVolt command-line entry point."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from importlib import import_module


def _datasets():
    """Load the optional data layer only after the CLI is invoked."""
    return import_module("quantvolt.data.datasets")


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
            print(json.dumps([asdict(record) for record in records], indent=2))
        else:
            for record in records:
                print(f"{record.dataset_id:38} {record.version:8} {record.size:>10} bytes")
        return 0
    dataset_id = args.dataset_id
    if args.operation == "info":
        print(json.dumps(asdict(datasets.info(dataset_id)), indent=2))
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
