"""Fail CI when new ordinary Git files violate the lightweight-repository policy."""

from __future__ import annotations

import subprocess
from pathlib import Path

MAX_TRACKED_BYTES = 1_000_000
ALLOWED_LARGE_PREFIXES = ("site/assets/",)


def main() -> None:
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    violations: list[str] = []
    for encoded in tracked:
        if not encoded:
            continue
        relative = encoded.decode()
        path = Path(relative)
        if not path.is_file() or relative.startswith(ALLOWED_LARGE_PREFIXES):
            continue
        size = path.stat().st_size
        if size > MAX_TRACKED_BYTES:
            violations.append(f"{relative}: {size:,} bytes")
    if violations:
        joined = "\n  ".join(violations)
        raise SystemExit(
            "ordinary Git files must be <= 1 MB; publish datasets as release assets:\n  "
            + joined
        )
    print("repository size policy verified")


if __name__ == "__main__":
    main()
