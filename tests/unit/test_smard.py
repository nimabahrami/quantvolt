"""SMARD adapter tests use recorded-style JSON and never call the live provider."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest

from quantvolt.data.smard import SmardResolution, SmardSource, _price_frame
from quantvolt.exceptions import DataSourceError, DataUnavailableError, ValidationError

_CHUNK = 1_759_096_800_000  # 2025-09-28T22:00:00Z
_NEXT_CHUNK = 1_759_701_600_000
_TRANSITION = 1_759_269_600_000  # 2025-09-30T22:00:00Z


def _payload(points: list[list[float | int | None]]) -> str:
    return json.dumps({"meta_data": {"name": "recorded"}, "series": points})


def test_price_frame_preserves_negative_prices_and_utc_intervals() -> None:
    frame = _price_frame(
        json.loads(_payload([[_CHUNK, -5.25], [_CHUNK + 3_600_000, 48.3]])),
        "DE-LU",
        SmardResolution.HOURLY,
    )

    assert frame["price_eur_per_mwh"].to_list() == [-5.25, 48.3]
    assert frame["duration_minutes"].to_list() == [60, 60]
    assert frame["interval_start_utc"][0] == datetime.fromtimestamp(_CHUNK / 1000, tz=UTC)
    assert frame["interval_end_utc"][0] == datetime.fromtimestamp(
        (_CHUNK + 3_600_000) / 1000, tz=UTC
    )


def test_price_frame_skips_provider_null_but_rejects_duplicate() -> None:
    frame = _price_frame(
        json.loads(_payload([[_CHUNK, None], [_CHUNK + 900_000, 10.0]])),
        "DE-LU",
        SmardResolution.QUARTER_HOURLY,
    )
    assert frame.height == 1

    with pytest.raises(DataSourceError, match="duplicate"):
        _price_frame(
            json.loads(_payload([[_CHUNK, 10.0], [_CHUNK, 11.0]])),
            "DE-LU",
            SmardResolution.HOURLY,
        )


def test_source_selects_overlapping_chunk_and_clips_range() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if "index_hour" in request.url.path:
            return httpx.Response(200, json={"timestamps": [_CHUNK, _NEXT_CHUNK]})
        return httpx.Response(
            200,
            text=_payload([[_CHUNK, 1.0], [_CHUNK + 3_600_000, 2.0], [_CHUNK + 7_200_000, 3.0]]),
        )

    source = SmardSource(transport=httpx.MockTransport(handler))
    start = datetime.fromtimestamp((_CHUNK + 3_600_000) / 1000, tz=UTC)
    end = datetime.fromtimestamp((_CHUNK + 7_200_000) / 1000, tz=UTC)

    frame = source.prices(start, end)

    assert frame["price_eur_per_mwh"].to_list() == [2.0]
    assert len(captured) == 2
    assert all(request.url.scheme == "https" for request in captured)


def test_native_prices_switches_resolution_at_market_boundary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "index_hour" in request.url.path or "index_quarterhour" in request.url.path:
            return httpx.Response(200, json={"timestamps": [_CHUNK, _NEXT_CHUNK]})
        if "_hour_" in request.url.path:
            return httpx.Response(
                200,
                text=_payload([[_TRANSITION - 3_600_000, 20.0], [_TRANSITION, 99.0]]),
            )
        return httpx.Response(
            200,
            text=_payload([[_TRANSITION, 21.0], [_TRANSITION + 900_000, 22.0]]),
        )

    source = SmardSource(transport=httpx.MockTransport(handler))
    frame = source.native_prices(
        datetime.fromtimestamp((_TRANSITION - 3_600_000) / 1000, tz=UTC),
        datetime.fromtimestamp((_TRANSITION + 1_800_000) / 1000, tz=UTC),
    )

    assert frame["duration_minutes"].to_list() == [60, 15, 15]
    assert frame["price_eur_per_mwh"].to_list() == [20.0, 21.0, 22.0]


def test_invalid_ranges_and_empty_payload_fail_loudly() -> None:
    instant = datetime(2026, 1, 1, tzinfo=UTC)
    source = SmardSource(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    with pytest.raises(ValidationError, match="strictly after"):
        source.prices(instant, instant)
    with pytest.raises(DataUnavailableError, match="no price points"):
        _price_frame({"series": []}, "DE-LU", SmardResolution.HOURLY)
