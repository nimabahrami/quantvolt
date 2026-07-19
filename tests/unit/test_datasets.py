"""Optional dataset catalog, cache, integrity, and CLI behavior."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace

import pytest

from quantvolt.cli import main
from quantvolt.data import datasets
from quantvolt.exceptions import DataUnavailableError, ValidationError


def test_catalog_is_sorted_and_complete() -> None:
    records = datasets.list_datasets()
    assert len(records) == 9
    assert [record.dataset_id for record in records] == sorted(
        record.dataset_id for record in records
    )
    assert all(
        record.url.startswith("https://github.com/nimabahrami/quantvolt/releases/")
        for record in records
    )


def test_unknown_dataset_names_available_ids() -> None:
    with pytest.raises(ValidationError, match="available datasets"):
        datasets.info("missing")


def test_cache_dir_honors_environment(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("QUANTVOLT_DATA_DIR", str(tmp_path))
    assert datasets.cache_dir() == tmp_path


def test_fetch_is_atomic_verified_and_reused(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    payload = b"small deterministic dataset\n"
    original = datasets.info("eia-henry-hub-spot-daily")
    record = replace(original, size=len(payload), sha256=hashlib.sha256(payload).hexdigest())
    monkeypatch.setenv("QUANTVOLT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(datasets, "_record", lambda _: record)
    calls = 0

    class Response(io.BytesIO):
        def __enter__(self):
            nonlocal calls
            calls += 1
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        datasets.urllib.request, "urlopen", lambda *args, **kwargs: Response(payload)
    )
    target = datasets.fetch(record.dataset_id)
    assert target.read_bytes() == payload
    assert datasets.verify(record.dataset_id)
    assert datasets.fetch(record.dataset_id) == target
    assert calls == 1
    assert not list(target.parent.glob("tmp*"))


def test_offline_missing_dataset_fails_without_network(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("QUANTVOLT_DATA_DIR", str(tmp_path))
    with pytest.raises(DataUnavailableError, match="offline=True"):
        datasets.fetch("eia-henry-hub-spot-daily", offline=True)


def test_integrity_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("QUANTVOLT_DATA_DIR", str(tmp_path))

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    monkeypatch.setattr(
        datasets.urllib.request, "urlopen", lambda *args, **kwargs: Response(b"corrupt")
    )
    with pytest.raises(DataUnavailableError, match="integrity verification"):
        datasets.fetch("eia-henry-hub-spot-daily")
    assert not datasets.path("eia-henry-hub-spot-daily").exists()


def test_cli_list_json(capsys) -> None:
    assert main(["data", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["dataset_id"] == "eia-henry-hub-spot-daily"
