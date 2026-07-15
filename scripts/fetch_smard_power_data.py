"""Download and normalize SMARD DE/LU day-ahead power prices.

The raw weekly JSON responses are retained with SHA-256 hashes.  The processed
dataset uses hourly products before the European 15-minute day-ahead transition
and native quarter-hour products from 2025-10-01 local market time onward.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from quantvolt.data.smard import SmardResolution, _price_frame

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "smard" / "day_ahead_price_de_lu"
PROCESSED = ROOT / "data" / "processed"
BASE_URL = "https://www.smard.de/app/chart_data/4169/DE-LU"
TRANSITION_UTC = datetime(2025, 9, 30, 22, 0, tzinfo=UTC)


def _get(client: httpx.Client, url: str) -> bytes:
    response = client.get(url)
    response.raise_for_status()
    return response.content


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _index(client: httpx.Client, resolution: SmardResolution) -> tuple[bytes, list[int]]:
    content = _get(client, f"{BASE_URL}/index_{resolution.value}.json")
    payload = json.loads(content)
    timestamps = payload.get("timestamps")
    if not isinstance(timestamps, list) or not timestamps:
        raise RuntimeError(f"SMARD {resolution.value} index contained no timestamps")
    return content, sorted(int(value) for value in timestamps)


def _chunk_url(resolution: SmardResolution, timestamp: int) -> str:
    return f"{BASE_URL}/4169_DE-LU_{resolution.value}_{timestamp}.json"


def _selected_chunks(
    resolution: SmardResolution, timestamps: list[int]
) -> list[tuple[SmardResolution, int]]:
    selected: list[tuple[SmardResolution, int]] = []
    for index, timestamp in enumerate(timestamps):
        start = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
        end = (
            datetime.fromtimestamp(timestamps[index + 1] / 1000, tz=UTC)
            if index + 1 < len(timestamps)
            else start + timedelta(days=7)
        )
        is_native_hour = resolution is SmardResolution.HOURLY and start < TRANSITION_UTC
        is_native_quarter = resolution is SmardResolution.QUARTER_HOURLY and end > TRANSITION_UTC
        if is_native_hour or is_native_quarter:
            selected.append((resolution, timestamp))
    return selected


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        hour_index, hour_timestamps = _index(client, SmardResolution.HOURLY)
        quarter_index, quarter_timestamps = _index(client, SmardResolution.QUARTER_HOURLY)
        _write(RAW / "index_hour.json", hour_index)
        _write(RAW / "index_quarterhour.json", quarter_index)
        chunks = _selected_chunks(SmardResolution.HOURLY, hour_timestamps)
        chunks += _selected_chunks(SmardResolution.QUARTER_HOURLY, quarter_timestamps)

        def fetch(item: tuple[SmardResolution, int]) -> tuple[SmardResolution, int, bytes]:
            resolution, timestamp = item
            return resolution, timestamp, _get(client, _chunk_url(resolution, timestamp))

        with ThreadPoolExecutor(max_workers=8) as executor:
            responses = list(executor.map(fetch, chunks))

    files: list[dict[str, Any]] = []
    frames: list[pl.DataFrame] = []
    for resolution, timestamp, content in sorted(responses, key=lambda item: (item[0], item[1])):
        relative = Path(resolution.value) / f"{timestamp}.json"
        path = RAW / relative
        _write(path, content)
        files.append(
            {
                "path": relative.as_posix(),
                "url": _chunk_url(resolution, timestamp),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        frame = _price_frame(json.loads(content), "DE-LU", resolution)
        if resolution is SmardResolution.HOURLY:
            frame = frame.filter(pl.col("interval_start_utc") < TRANSITION_UTC)
        else:
            frame = frame.filter(pl.col("interval_start_utc") >= TRANSITION_UTC)
        if not frame.is_empty():
            frames.append(frame)

    combined = (
        pl.concat(frames)
        .unique(subset=["interval_start_utc"], keep="first")
        .sort("interval_start_utc")
    )
    combined.write_csv(PROCESSED / "smard_de_lu_day_ahead_native.csv")
    combined.write_parquet(PROCESSED / "smard_de_lu_day_ahead_native.parquet")

    manifest = {
        "source": "Bundesnetzagentur | SMARD.de",
        "licence": "CC BY 4.0",
        "retrieved_at_utc": datetime.now(tz=UTC).isoformat(),
        "bidding_zone": "DE-LU",
        "filter": "4169",
        "native_resolution_transition_utc": TRANSITION_UTC.isoformat(),
        "rows": combined.height,
        "first_interval_utc": combined["interval_start_utc"].min().isoformat(),
        "last_interval_utc": combined["interval_start_utc"].max().isoformat(),
        "files": files,
    }
    (RAW / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
