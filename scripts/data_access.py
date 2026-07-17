"""Resolve research data locally first, then from QuantVolt's verified cache."""

from pathlib import Path

from quantvolt.data import datasets


def local_or_fetch(local_path: Path, dataset_id: str) -> Path:
    """Return a local development file or download its immutable release asset."""
    if local_path.is_file():
        return local_path
    return datasets.fetch(dataset_id)
