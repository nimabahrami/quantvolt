"""Explicit, checksummed access to optional QuantVolt research datasets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from ..exceptions import DataUnavailableError, ValidationError

_CATALOG_RESOURCE = "dataset_catalog.json"
_RELEASE_BASE = "https://github.com/nimabahrami/quantvolt/releases/download"
_DATA_DIR_ENV = "QUANTVOLT_DATA_DIR"


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    """One immutable downloadable dataset release record."""

    dataset_id: str
    version: str
    filename: str
    size: int
    sha256: str
    format: str
    license: str
    source: str
    url: str


def _catalog() -> dict[str, Any]:
    resource = files("quantvolt.data").joinpath(_CATALOG_RESOURCE)
    catalog: dict[str, Any] = json.loads(resource.read_text(encoding="utf-8"))
    return catalog


def _record(dataset_id: str) -> DatasetRecord:
    catalog = _catalog()
    try:
        raw = catalog["datasets"][dataset_id]
    except KeyError as error:
        available = ", ".join(sorted(catalog["datasets"]))
        raise ValidationError(
            f"unknown dataset_id {dataset_id!r}; available datasets: {available}"
        ) from error
    url = f"{_RELEASE_BASE}/{catalog['release']}/{raw['filename']}"
    return DatasetRecord(dataset_id=dataset_id, url=url, **raw)


def list_datasets() -> tuple[DatasetRecord, ...]:
    """Return every optional dataset in stable ID order without network access."""
    return tuple(_record(dataset_id) for dataset_id in sorted(_catalog()["datasets"]))


def info(dataset_id: str) -> DatasetRecord:
    """Return catalog metadata for ``dataset_id`` without network access."""
    return _record(dataset_id)


def cache_dir() -> Path:
    """Return the configured dataset cache directory without creating it."""
    configured = os.environ.get(_DATA_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".cache" / "quantvolt" / "datasets"


def path(dataset_id: str) -> Path:
    """Return the expected local path for a dataset, whether downloaded or not."""
    record = _record(dataset_id)
    return cache_dir() / record.version / record.filename


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(dataset_id: str) -> bool:
    """Return whether the cached file exists and matches catalog size and SHA-256."""
    record = _record(dataset_id)
    target = path(dataset_id)
    return (
        target.is_file()
        and target.stat().st_size == record.size
        and _sha256(target) == record.sha256
    )


def fetch(
    dataset_id: str,
    *,
    force: bool = False,
    offline: bool = False,
    timeout: float = 60.0,
) -> Path:
    """Download and atomically cache one dataset after size and hash verification."""
    record = _record(dataset_id)
    target = path(dataset_id)
    if not force and verify(dataset_id):
        return target
    if offline:
        raise DataUnavailableError(
            f"dataset {dataset_id!r} is not present and verified in {target.parent}; "
            "offline=True forbids downloading it"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with (
            urllib.request.urlopen(record.url, timeout=timeout) as response,
            tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output,
        ):
            temporary = Path(output.name)
            shutil.copyfileobj(response, output, length=1024 * 1024)
        actual_size = temporary.stat().st_size
        actual_hash = _sha256(temporary)
        if actual_size != record.size or actual_hash != record.sha256:
            raise DataUnavailableError(
                f"dataset {dataset_id!r} failed integrity verification: expected "
                f"{record.size} bytes and sha256 {record.sha256}, got "
                f"{actual_size} bytes and sha256 {actual_hash}"
            )
        temporary.replace(target)
        return target
    except (OSError, urllib.error.URLError) as error:
        raise DataUnavailableError(
            f"failed to download dataset {dataset_id!r} from {record.url}: {error}"
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def remove(dataset_id: str) -> bool:
    """Remove a cached dataset; return whether a file was removed."""
    target = path(dataset_id)
    if not target.exists():
        return False
    target.unlink()
    return True
