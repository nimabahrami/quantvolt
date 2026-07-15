"""Download German quarter-hour physical power fundamentals from SMARD.

The selected series cover physical volume drivers needed by PPA experiments:
load plus onshore wind, offshore wind, solar, and gas-fired generation. Raw
weekly provider responses are retained and hashed before a wide analysis table
is produced.
"""

from __future__ import annotations

import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import polars as pl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "smard" / "power_fundamentals_de"
PROCESSED = ROOT / "data" / "processed"
BASE_URL = "https://www.smard.de/app/chart_data"
START_UTC = datetime(2018, 9, 30, 22, 0, tzinfo=UTC)
LOCAL_TIMEZONE = ZoneInfo("Europe/Berlin")
SERIES = {
    "410": "total_load_mwh",
    "4067": "wind_onshore_generation_mwh",
    "1225": "wind_offshore_generation_mwh",
    "4068": "solar_generation_mwh",
    "4071": "gas_generation_mwh",
}


def _get(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return response.content


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _index_url(module: str) -> str:
    return f"{BASE_URL}/{module}/DE/index_quarterhour.json"


def _chunk_url(module: str, timestamp: int) -> str:
    return f"{BASE_URL}/{module}/DE/{module}_DE_quarterhour_{timestamp}.json"


def _selected(timestamps: list[int]) -> list[int]:
    chosen: list[int] = []
    for index, timestamp in enumerate(timestamps):
        start = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        end = (
            datetime.fromtimestamp(timestamps[index + 1] / 1000, tz=UTC)
            if index + 1 < len(timestamps)
            else start + timedelta(days=7)
        )
        if end > START_UTC:
            chosen.append(timestamp)
    return chosen


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    index_content: dict[str, bytes] = {}
    requests: list[tuple[str, int]] = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for module in SERIES:
            content = _get(client, _index_url(module))
            index_content[module] = content
            payload = json.loads(content)
            timestamps = payload.get("timestamps")
            if not isinstance(timestamps, list) or not timestamps:
                raise RuntimeError(f"SMARD module {module} index contained no timestamps")
            requests.extend((module, timestamp) for timestamp in _selected(sorted(timestamps)))

        def fetch(item: tuple[str, int]) -> tuple[str, int, bytes]:
            module, timestamp = item
            return module, timestamp, _get(client, _chunk_url(module, timestamp))

        with ThreadPoolExecutor(max_workers=12) as executor:
            responses = list(executor.map(fetch, requests))

    for module, content in index_content.items():
        _write(RAW / module / "index_quarterhour.json", content)

    values: dict[datetime, dict[str, float]] = {}
    files: list[dict[str, Any]] = []
    for module, timestamp, content in sorted(responses):
        relative = Path(module) / f"{timestamp}.json"
        _write(RAW / relative, content)
        files.append(
            {
                "path": relative.as_posix(),
                "url": _chunk_url(module, timestamp),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        payload = json.loads(content)
        raw_series = payload.get("series")
        if not isinstance(raw_series, list):
            raise RuntimeError(f"SMARD module {module} chunk {timestamp} has no series")
        column = SERIES[module]
        for epoch_ms, raw_value in raw_series:
            if raw_value is None:
                continue
            start = datetime.fromtimestamp(float(epoch_ms) / 1000.0, tz=UTC)
            if start < START_UTC:
                continue
            value = float(raw_value)
            if not math.isfinite(value):
                raise RuntimeError(f"SMARD module {module} has non-finite value at {start}")
            values.setdefault(start, {})[column] = value

    rows: list[dict[str, object]] = []
    for start, observations in sorted(values.items()):
        local = start.astimezone(LOCAL_TIMEZONE)
        rows.append(
            {
                "interval_start_utc": start,
                "interval_end_utc": start + timedelta(minutes=15),
                "local_start": local.isoformat(),
                "local_date": local.date(),
                "utc_offset_minutes": int(local.utcoffset().total_seconds() // 60),
                "duration_minutes": 15,
                **{column: observations.get(column) for column in SERIES.values()},
                "source": "Bundesnetzagentur | SMARD.de",
            }
        )
    frame = pl.DataFrame(rows)
    frame.write_csv(PROCESSED / "smard_de_power_fundamentals_quarter_hour.csv")
    frame.write_parquet(PROCESSED / "smard_de_power_fundamentals_quarter_hour.parquet")

    manifest = {
        "source": "Bundesnetzagentur | SMARD.de",
        "licence": "CC BY 4.0",
        "retrieved_at_utc": datetime.now(tz=UTC).isoformat(),
        "region": "DE",
        "resolution_minutes": 15,
        "series": SERIES,
        "rows": frame.height,
        "first_interval_utc": frame["interval_start_utc"].min().isoformat(),
        "last_interval_utc": frame["interval_start_utc"].max().isoformat(),
        "files": files,
    }
    (RAW / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
