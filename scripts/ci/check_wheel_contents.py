"""Verify built wheels do not contain repository datasets or other bulky research files."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main(wheel_name: str) -> None:
    wheel = Path(wheel_name)
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
    forbidden = [name for name in names if name.startswith(("data/", "tests/", "site/"))]
    if forbidden:
        raise SystemExit("wheel contains forbidden files: " + ", ".join(forbidden))
    if not any(name.startswith("quantvolt/") for name in names):
        raise SystemExit("wheel does not contain the quantvolt package")
    print(f"wheel policy verified: {wheel.name} ({wheel.stat().st_size:,} bytes)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_wheel_contents.py WHEEL")
    main(sys.argv[1])
