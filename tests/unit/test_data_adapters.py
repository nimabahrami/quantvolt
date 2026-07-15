"""Unit tests for the provider adapters (Tasks 54-57).

All HTTP is mocked with ``httpx.MockTransport`` over inline recorded-style payloads —
zero live network calls (tech.md).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx
import polars as pl
import pytest

from quantvolt.data.base import Credentials
from quantvolt.data.commercial import (
    EexSource,
    EpexSource,
    IceSource,
    LsegSource,
    NordPoolSource,
    _CommercialSource,
)
from quantvolt.data.entsoe import EntsoeSource, _parse_interval_points, _period_stamp
from quantvolt.data.entsog import EntsogSource
from quantvolt.data.open_meteo import OpenMeteoSource
from quantvolt.exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    RateLimitError,
    ValidationError,
)
from quantvolt.market.weather import degree_days
from quantvolt.models.commodity import BUILT_IN_COMMODITIES, CommodityConfig, Hub

_TOKEN = "recorded-test-token-91c2"


def _mock_transport(
    payload: str = "", status: int = 200
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """A MockTransport returning a canned response, plus the captured requests."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, text=payload)

    return httpx.MockTransport(handler), captured


def _sequential_mock_transport(
    responses: list[tuple[int, str]],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    """A MockTransport returning ``responses`` in order (last one repeats), for retry tests."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        status, payload = responses[min(len(captured) - 1, len(responses) - 1)]
        return httpx.Response(status, text=payload)

    return httpx.MockTransport(handler), captured


# --- ENTSO-E (Task 54) — recorded-style payload fixtures -----------------------------------

# Minimal documented subset: Publication_MarketDocument -> TimeSeries -> Period -> Point
# (position + price.amount). Positions arrive out of order to exercise position sorting.
# The Period spans exactly 3 hourly positions (23:00 -> 02:00) so every position is present
# and no A03 gap-fill is triggered here (see TestGapFilling for that).
_ENTSOE_PRICES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <mRID>recorded-a44</mRID>
  <type>A44</type>
  <TimeSeries>
    <mRID>1</mRID>
    <currency_Unit.name>EUR</currency_Unit.name>
    <price_Measure_Unit.name>MWH</price_Measure_Unit.name>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T02:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>2</position><price.amount>48.30</price.amount></Point>
      <Point><position>1</position><price.amount>50.10</price.amount></Point>
      <Point><position>3</position><price.amount>-5.25</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# Period spans exactly 2 quarter-hour positions (23:00 -> 23:30) so both are present and no
# A03 gap-fill is triggered here (see TestGapFilling for that).
_ENTSOE_LOAD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
  <mRID>recorded-a65</mRID>
  <type>A65</type>
  <TimeSeries>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-01T23:30Z</end></timeInterval>
      <resolution>PT15M</resolution>
      <Point><position>1</position><quantity>42150</quantity></Point>
      <Point><position>2</position><quantity>41800</quantity></Point>
    </Period>
  </TimeSeries>
</GL_MarketDocument>
"""

_ENTSOE_ACK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:8:1">
  <mRID>recorded-ack</mRID>
  <Reason><code>999</code><text>No matching data found</text></Reason>
</Acknowledgement_MarketDocument>
"""

_ENTSOE_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <mRID>recorded-empty</mRID>
</Publication_MarketDocument>
"""

_POWER_DE = BUILT_IN_COMMODITIES["EPEX_DE"]
_START, _END = date(2026, 1, 1), date(2026, 1, 3)


class TestEntsoeSource:
    def test_price_frame_preserves_utc_delivery_intervals(self) -> None:
        transport, _ = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        frame = source.price_frame(_POWER_DE, _START, _END)

        assert frame["interval_start_utc"].to_list() == [
            datetime(2026, 1, 1, 23, tzinfo=UTC),
            datetime(2026, 1, 2, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 1, tzinfo=UTC),
        ]
        assert frame["interval_end_utc"].to_list() == [
            datetime(2026, 1, 2, 0, tzinfo=UTC),
            datetime(2026, 1, 2, 1, tzinfo=UTC),
            datetime(2026, 1, 2, 2, tzinfo=UTC),
        ]
        assert frame["duration_hours"].to_list() == [1.0, 1.0, 1.0]
        assert frame["position"].to_list() == [1, 2, 3]
        assert frame["value"].to_list() == pytest.approx([50.10, 48.30, -5.25])

    def test_price_series_parses_documented_xml_subset(self) -> None:
        transport, _ = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        series = source.price_series(_POWER_DE, _START, _END)

        assert series.name == "EPEX_DE"
        assert series.dtype == pl.Float64
        assert series.to_list() == pytest.approx([50.10, 48.30, -5.25])

    def test_request_is_https_with_token_and_area_params(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        source.price_series(_POWER_DE, _START, _END)

        (request,) = captured
        assert request.url.scheme == "https"
        assert request.url.params["securityToken"] == _TOKEN
        assert request.url.params["documentType"] == "A44"
        assert request.url.params["in_Domain"] == "10Y1001A1001A82H"
        assert request.url.params["out_Domain"] == "10Y1001A1001A82H"
        # Regression (bug fix): 2026-01-01/2026-01-03 are local (Europe/Berlin, CET=UTC+1)
        # calendar delivery days; local midnight converts to the previous day 23:00 UTC —
        # not the naive local-clock stamp "202601010000"/"202601030000".
        assert request.url.params["periodStart"] == "202512312300"
        assert request.url.params["periodEnd"] == "202601022300"

    def test_explicit_credentials_beat_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUANTVOLT_ENTSOE_TOKEN", "env-token-should-lose")
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        source.price_series(_POWER_DE, _START, _END)

        assert captured[0].url.params["securityToken"] == _TOKEN
        assert "env-token-should-lose" not in str(captured[0].url)

    def test_env_token_used_when_no_explicit_credentials(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUANTVOLT_ENTSOE_TOKEN", _TOKEN)
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(transport=transport)

        source.price_series(_POWER_DE, _START, _END)

        assert captured[0].url.params["securityToken"] == _TOKEN

    def test_missing_token_raises_before_any_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("QUANTVOLT_ENTSOE_TOKEN", raising=False)
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(transport=transport)

        with pytest.raises(AuthenticationError) as excinfo:
            source.price_series(_POWER_DE, _START, _END)

        assert "entsoe" in str(excinfo.value)
        assert "QUANTVOLT_ENTSOE_TOKEN" in str(excinfo.value)
        assert captured == []

    @pytest.mark.parametrize("status", [401, 403])
    def test_rejected_token_maps_to_authentication_error(self, status: int) -> None:
        transport, _ = _mock_transport(status=status)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        with pytest.raises(AuthenticationError) as excinfo:
            source.price_series(_POWER_DE, _START, _END)

        message = str(excinfo.value)
        assert "entsoe" in message
        assert "QUANTVOLT_ENTSOE_TOKEN" in message
        assert _TOKEN not in message

    def test_429_maps_to_rate_limit_error(self) -> None:
        transport, _ = _mock_transport(status=429)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(RateLimitError, match="entsoe"):
            source.price_series(_POWER_DE, _START, _END)

    def test_500_maps_to_data_source_error(self) -> None:
        transport, _ = _mock_transport(status=500)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(DataSourceError, match="500"):
            source.price_series(_POWER_DE, _START, _END)

    def test_acknowledgement_maps_to_data_unavailable(self) -> None:
        transport, _ = _mock_transport(_ENTSOE_ACK_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(DataUnavailableError, match="entsoe"):
            source.price_series(_POWER_DE, _START, _END)

    def test_document_without_points_maps_to_data_unavailable(self) -> None:
        transport, _ = _mock_transport(_ENTSOE_EMPTY_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(DataUnavailableError, match="no data points"):
            source.price_series(_POWER_DE, _START, _END)

    def test_unparseable_xml_maps_to_data_source_error(self) -> None:
        transport, _ = _mock_transport("this is not xml <<<")
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(DataSourceError, match="XML"):
            source.price_series(_POWER_DE, _START, _END)

    def test_non_power_hub_raises_naming_it(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        with pytest.raises(DataSourceError, match="TTF"):
            source.price_series(BUILT_IN_COMMODITIES["TTF"], _START, _END)
        assert captured == []

    def test_load_parses_quantity_points(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_LOAD_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        series = source.load(_POWER_DE, _START, _END)

        assert series.name == "EPEX_DE_load"
        assert series.to_list() == pytest.approx([42150.0, 41800.0])
        assert captured[0].url.params["documentType"] == "A65"
        assert captured[0].url.params["processType"] == "A16"

    def test_load_frame_preserves_quarter_hour_resolution(self) -> None:
        transport, _ = _mock_transport(_ENTSOE_LOAD_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        frame = source.load_frame(_POWER_DE, _START, _END)

        assert frame["interval_start_utc"].to_list() == [
            datetime(2026, 1, 1, 23, tzinfo=UTC),
            datetime(2026, 1, 1, 23, 15, tzinfo=UTC),
        ]
        assert frame["duration_hours"].to_list() == [0.25, 0.25]

    def test_generation_parses_quantity_points(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_LOAD_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)

        series = source.generation(_POWER_DE, _START, _END)

        assert series.name == "EPEX_DE_generation"
        assert series.to_list() == pytest.approx([42150.0, 41800.0])
        assert captured[0].url.params["documentType"] == "A75"

    def test_free_source_exposes_no_forward_curve(self) -> None:
        assert not hasattr(EntsoeSource(Credentials(token=_TOKEN)), "forward_curve")


class TestEntsoeConstructorParams:
    """New keyword-only constructor parameters: base_url, timeout_seconds, max_retries,
    backoff_seconds, bidding_zone_overrides. Defaults reproduce today's behaviour exactly."""

    def test_base_url_default_matches_explicit_production_url(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        EntsoeSource(
            Credentials(token=_TOKEN),
            transport=transport,
            base_url="https://web-api.tp.entsoe.eu/api",
        ).price_series(_POWER_DE, _START, _END)
        assert captured[0].url.host == "web-api.tp.entsoe.eu"

    def test_base_url_override_changes_request_host(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(
            Credentials(token=_TOKEN),
            transport=transport,
            base_url="https://mirror.example.com/api",
        )
        source.price_series(_POWER_DE, _START, _END)
        assert captured[0].url.host == "mirror.example.com"

    def test_timeout_seconds_default_matches_explicit_30(self) -> None:
        default = EntsoeSource(Credentials(token=_TOKEN))
        explicit = EntsoeSource(Credentials(token=_TOKEN), timeout_seconds=30.0)
        assert default._timeout_seconds == explicit._timeout_seconds == 30.0

    def test_timeout_seconds_override_changes_stored_value(self) -> None:
        source = EntsoeSource(Credentials(token=_TOKEN), timeout_seconds=5.0)
        assert source._timeout_seconds == 5.0

    def test_non_positive_timeout_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="timeout_seconds"):
            EntsoeSource(Credentials(token=_TOKEN), timeout_seconds=0.0)

    def test_max_retries_default_zero_gives_no_retry_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(500, ""), (200, _ENTSOE_PRICES_XML)])
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        with pytest.raises(DataSourceError):
            source.price_series(_POWER_DE, _START, _END)
        assert len(captured) == 1

    def test_max_retries_override_retries_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(500, ""), (200, _ENTSOE_PRICES_XML)])
        source = EntsoeSource(
            Credentials(token=_TOKEN), transport=transport, max_retries=1, backoff_seconds=0.0
        )
        series = source.price_series(_POWER_DE, _START, _END)
        assert len(captured) == 2
        assert series.to_list() == pytest.approx([50.10, 48.30, -5.25])

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValidationError, match="max_retries"):
            EntsoeSource(Credentials(token=_TOKEN), max_retries=-1)

    def test_negative_backoff_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="backoff_seconds"):
            EntsoeSource(Credentials(token=_TOKEN), backoff_seconds=-1.0)

    def test_bidding_zone_overrides_default_none_keeps_builtin_map(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        EntsoeSource(Credentials(token=_TOKEN), transport=transport).price_series(
            _POWER_DE, _START, _END
        )
        assert captured[0].url.params["in_Domain"] == "10Y1001A1001A82H"

    def test_bidding_zone_overrides_adds_a_new_hub(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        new_hub_commodity = CommodityConfig(
            commodity_id="XX",
            price_unit="EUR/MWh",
            hub=Hub(hub_id="NEW_HUB", exchange="X", price_unit="EUR/MWh"),
        )
        source = EntsoeSource(
            Credentials(token=_TOKEN),
            transport=transport,
            bidding_zone_overrides={"NEW_HUB": "10YNEWHUB------X"},
            timezone_overrides={"NEW_HUB": "Europe/Berlin"},
        )
        source.price_series(new_hub_commodity, _START, _END)
        assert captured[0].url.params["in_Domain"] == "10YNEWHUB------X"

    def test_new_hub_without_timezone_override_raises_naming_it(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        new_hub_commodity = CommodityConfig(
            commodity_id="XX",
            price_unit="EUR/MWh",
            hub=Hub(hub_id="NEW_HUB", exchange="X", price_unit="EUR/MWh"),
        )
        source = EntsoeSource(
            Credentials(token=_TOKEN),
            transport=transport,
            bidding_zone_overrides={"NEW_HUB": "10YNEWHUB------X"},
        )
        with pytest.raises(DataSourceError, match="NEW_HUB"):
            source.price_series(new_hub_commodity, _START, _END)
        assert captured == []

    def test_timezone_overrides_default_none_keeps_builtin_map(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        EntsoeSource(Credentials(token=_TOKEN), transport=transport).price_series(
            _POWER_DE, _START, _END
        )
        # EPEX_DE (Europe/Berlin, CET winter) -> local midnight is 23:00 UTC the day before.
        assert captured[0].url.params["periodStart"] == "202512312300"

    def test_timezone_overrides_changes_stamp_for_existing_hub(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(
            Credentials(token=_TOKEN),
            transport=transport,
            timezone_overrides={"EPEX_GB": "Europe/Berlin"},
        )
        source.price_series(BUILT_IN_COMMODITIES["EPEX_GB"], _START, _END)
        # With the override, EPEX_GB now uses Europe/Berlin instead of its built-in
        # Europe/London, so the stamp shifts by the CET/GMT offset.
        assert captured[0].url.params["periodStart"] == "202512312300"


class TestEntsoeLocalDeliveryDaySemantics:
    """Regression tests for the entsoe.py:65 bug: a naive local-clock stamp silently shifted
    every CET/CEST query window by 1-2h. ``_period_stamp`` must interpret ``day`` as a local
    calendar delivery day and convert local midnight to UTC."""

    def test_winter_cet_stamp_is_utc_plus_one(self) -> None:
        # CET = UTC+1 in January -> local midnight 2026-01-01 00:00 CET = 2025-12-31 23:00 UTC.
        assert _period_stamp(date(2026, 1, 1), ZoneInfo("Europe/Berlin")) == "202512312300"

    def test_summer_cest_stamp_is_utc_plus_two(self) -> None:
        # CEST = UTC+2 in July -> local midnight 2026-07-01 00:00 CEST = 2026-06-30 22:00 UTC.
        assert _period_stamp(date(2026, 7, 1), ZoneInfo("Europe/Berlin")) == "202606302200"

    def test_gb_winter_stamp_is_utc_plus_zero(self) -> None:
        # GMT = UTC+0 in January -> local midnight equals the UTC stamp.
        assert _period_stamp(date(2026, 1, 1), ZoneInfo("Europe/London")) == "202601010000"

    def test_gb_summer_bst_stamp_is_utc_plus_one(self) -> None:
        # BST = UTC+1 in July -> local midnight 2026-07-01 00:00 BST = 2026-06-30 23:00 UTC.
        assert _period_stamp(date(2026, 7, 1), ZoneInfo("Europe/London")) == "202606302300"

    def test_summer_query_uses_dst_offset_end_to_end(self) -> None:
        transport, captured = _mock_transport(_ENTSOE_PRICES_XML)
        source = EntsoeSource(Credentials(token=_TOKEN), transport=transport)
        source.price_series(_POWER_DE, date(2026, 7, 1), date(2026, 7, 3))
        assert captured[0].url.params["periodStart"] == "202606302200"
        assert captured[0].url.params["periodEnd"] == "202607022200"


# --- ENTSO-E A03 gap-fill and chronological-order fixtures (entsoe.py:85, :96) -------------

# A 4-hour Period at hourly resolution where position 3 is omitted (its value repeats
# position 2's 48.30) -> A03 semantics require forward-filling it rather than shortening
# the series.
_ENTSOE_GAP_MIDDLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T03:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>50.10</price.amount></Point>
      <Point><position>2</position><price.amount>48.30</price.amount></Point>
      <Point><position>4</position><price.amount>-5.25</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# A 4-hour Period where positions 3 and 4 are both omitted (trailing omission) -> forward-fill
# to the end of the Period using position 2's value.
_ENTSOE_GAP_TRAILING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T03:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>50.10</price.amount></Point>
      <Point><position>2</position><price.amount>48.30</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# Position 1 omitted -> malformed per the standard (position 1 is always present) -> raise.
_ENTSOE_GAP_MISSING_FIRST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>2</position><price.amount>48.30</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# Fully-populated A01-style period (every position present) — must be unchanged by gap-fill.
_ENTSOE_FULLY_POPULATED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>50.10</price.amount></Point>
      <Point><position>2</position><price.amount>48.30</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# Two Periods (day 2 then day 1, permuted document order) in one TimeSeries.
_ENTSOE_PERMUTED_PERIODS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-02T23:00Z</start><end>2026-01-03T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>200.0</price.amount></Point>
      <Point><position>2</position><price.amount>210.0</price.amount></Point>
    </Period>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>100.0</price.amount></Point>
      <Point><position>2</position><price.amount>110.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""

# Two TimeSeries (permuted document order: series "2" for the later day appears first).
_ENTSOE_PERMUTED_TIME_SERIES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><mRID>2</mRID>
    <Period>
      <timeInterval><start>2026-01-02T23:00Z</start><end>2026-01-03T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>200.0</price.amount></Point>
      <Point><position>2</position><price.amount>210.0</price.amount></Point>
    </Period>
  </TimeSeries>
  <TimeSeries><mRID>1</mRID>
    <Period>
      <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T01:00Z</end></timeInterval>
      <resolution>PT60M</resolution>
      <Point><position>1</position><price.amount>100.0</price.amount></Point>
      <Point><position>2</position><price.amount>110.0</price.amount></Point>
    </Period>
  </TimeSeries>
</Publication_MarketDocument>
"""


class TestEntsoeGapFilling:
    """Regression tests for the entsoe.py:96 bug: A03 omits a Point when its value repeats
    the previous position's value; the parser must forward-fill, not shorten, the series."""

    def test_omitted_middle_position_forward_fills(self) -> None:
        frame = _parse_interval_points("entsoe", _ENTSOE_GAP_MIDDLE_XML, "price.amount")
        assert frame["position"].to_list() == [1, 2, 3, 4]
        assert frame["value"].to_list() == pytest.approx([50.10, 48.30, 48.30, -5.25])

    def test_omitted_trailing_positions_forward_fill_to_period_end(self) -> None:
        frame = _parse_interval_points("entsoe", _ENTSOE_GAP_TRAILING_XML, "price.amount")
        assert frame["position"].to_list() == [1, 2, 3, 4]
        assert frame["value"].to_list() == pytest.approx([50.10, 48.30, 48.30, 48.30])
        assert frame["interval_end_utc"][-1] == datetime(2026, 1, 2, 3, tzinfo=UTC)

    def test_fully_populated_period_is_unchanged(self) -> None:
        frame = _parse_interval_points("entsoe", _ENTSOE_FULLY_POPULATED_XML, "price.amount")
        assert frame["position"].to_list() == [1, 2]
        assert frame["value"].to_list() == pytest.approx([50.10, 48.30])

    def test_missing_first_position_raises(self) -> None:
        with pytest.raises(DataSourceError, match="position 1"):
            _parse_interval_points("entsoe", _ENTSOE_GAP_MISSING_FIRST_XML, "price.amount")


class TestEntsoeChronologicalOrder:
    """Regression tests for the entsoe.py:85 bug: TimeSeries/Periods must be processed in
    chronological order of their timeInterval start, not raw document order."""

    def test_permuted_periods_within_one_series_sort_chronologically(self) -> None:
        frame = _parse_interval_points("entsoe", _ENTSOE_PERMUTED_PERIODS_XML, "price.amount")
        assert frame["value"].to_list() == pytest.approx([100.0, 110.0, 200.0, 210.0])
        assert frame["interval_start_utc"].to_list() == sorted(
            frame["interval_start_utc"].to_list()
        )

    def test_permuted_time_series_sort_chronologically(self) -> None:
        frame = _parse_interval_points("entsoe", _ENTSOE_PERMUTED_TIME_SERIES_XML, "price.amount")
        assert frame["value"].to_list() == pytest.approx([100.0, 110.0, 200.0, 210.0])
        assert frame["time_series_id"].to_list() == ["1", "1", "2", "2"]


# --- ENTSOG (Task 55) — recorded-style payload fixture -------------------------------------

_ENTSOG_FLOWS_JSON = """{
  "operationalData": [
    {
      "pointKey": "ITP-00096",
      "directionKey": "entry",
      "periodFrom": "2026-01-01T06:00:00+01:00",
      "value": 152340.5,
      "unit": "kWh/d"
    },
    {
      "pointKey": "ITP-00096",
      "directionKey": "entry",
      "periodFrom": "2026-01-02T06:00:00+01:00",
      "value": null,
      "unit": "kWh/d"
    }
  ]
}"""

# Regression fixture (entsog.py:154-155 bug): pointKey/directionKey are JSON null. The
# fallback (the caller's point_key/direction) must be used, mirroring how value/unit are
# already null-guarded — not the literal string "None".
_ENTSOG_NULL_KEYS_JSON = """{
  "operationalData": [
    {
      "pointKey": null,
      "directionKey": null,
      "periodFrom": "2026-01-01T06:00:00+01:00",
      "value": 100.0,
      "unit": "kWh/d"
    }
  ]
}"""


class TestEntsogSource:
    def test_null_point_and_direction_keys_fall_back_to_caller_values(self) -> None:
        transport, _ = _mock_transport(_ENTSOG_NULL_KEYS_JSON)
        source = EntsogSource(transport=transport)

        frame = source.flows("ITP-00096", _START, _END, direction="exit")

        assert frame["point"].to_list() == ["ITP-00096"]
        assert frame["direction"].to_list() == ["exit"]

    def test_flows_parses_json_records(self) -> None:
        transport, _ = _mock_transport(_ENTSOG_FLOWS_JSON)
        source = EntsogSource(transport=transport)

        frame = source.flows("ITP-00096", _START, _END)

        assert frame.columns == ["point", "direction", "date", "value", "unit"]
        assert frame["point"].to_list() == ["ITP-00096", "ITP-00096"]
        assert frame["date"].to_list() == [date(2026, 1, 1), date(2026, 1, 2)]
        assert frame["value"].to_list() == [152340.5, None]
        assert frame["unit"].to_list() == ["kWh/d", "kWh/d"]

    def test_entsog_is_keyless_no_token_required_or_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("QUANTVOLT_ENTSOG_TOKEN", raising=False)
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        source = EntsogSource(transport=transport)

        source.flows("ITP-00096", _START, _END)

        (request,) = captured
        assert request.url.scheme == "https"
        assert "token" not in str(request.url).lower()

    def test_flow_query_params(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, direction="exit")

        params = captured[0].url.params
        assert params["indicator"] == "Physical Flow"
        assert params["periodType"] == "day"
        assert params["pointKey"] == "ITP-00096"
        assert params["directionKey"] == "exit"
        assert params["from"] == "2026-01-01"
        assert params["to"] == "2026-01-03"

    def test_empty_records_map_to_data_unavailable(self) -> None:
        transport, _ = _mock_transport('{"operationalData": []}')
        with pytest.raises(DataUnavailableError, match="ITP-00096"):
            EntsogSource(transport=transport).flows("ITP-00096", _START, _END)

    def test_429_maps_to_rate_limit_error(self) -> None:
        transport, _ = _mock_transport(status=429)
        with pytest.raises(RateLimitError, match="entsog"):
            EntsogSource(transport=transport).flows("ITP-00096", _START, _END)

    def test_401_maps_to_authentication_error(self) -> None:
        transport, _ = _mock_transport(status=401)
        with pytest.raises(AuthenticationError, match="entsog"):
            EntsogSource(transport=transport).flows("ITP-00096", _START, _END)

    def test_unparseable_json_maps_to_data_source_error(self) -> None:
        transport, _ = _mock_transport("not json at all")
        with pytest.raises(DataSourceError, match="JSON"):
            EntsogSource(transport=transport).flows("ITP-00096", _START, _END)

    def test_free_source_exposes_no_forward_curve(self) -> None:
        assert not hasattr(EntsogSource(), "forward_curve")


class TestEntsogConstructorAndMethodParams:
    """New keyword-only params: constructor base_url/timeout_seconds/max_retries/
    backoff_seconds, and ``flows`` period_type/indicator/limit. Defaults reproduce
    today's behaviour exactly."""

    def test_base_url_default_matches_explicit_production_url(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(
            transport=transport, base_url="https://transparency.entsog.eu/api/v4/operationalData"
        ).flows("ITP-00096", _START, _END)
        assert captured[0].url.host == "transparency.entsog.eu"

    def test_base_url_override_changes_request_host(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(
            transport=transport, base_url="https://mirror.example.com/v4/operationalData"
        ).flows("ITP-00096", _START, _END)
        assert captured[0].url.host == "mirror.example.com"

    def test_timeout_seconds_default_matches_explicit_30(self) -> None:
        default = EntsogSource()
        explicit = EntsogSource(timeout_seconds=30.0)
        assert default._timeout_seconds == explicit._timeout_seconds == 30.0

    def test_timeout_seconds_override_changes_stored_value(self) -> None:
        assert EntsogSource(timeout_seconds=5.0)._timeout_seconds == 5.0

    def test_non_positive_timeout_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="timeout_seconds"):
            EntsogSource(timeout_seconds=0.0)

    def test_max_retries_default_zero_gives_no_retry_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(500, ""), (200, _ENTSOG_FLOWS_JSON)])
        source = EntsogSource(transport=transport)
        with pytest.raises(DataSourceError):
            source.flows("ITP-00096", _START, _END)
        assert len(captured) == 1

    def test_max_retries_override_retries_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(500, ""), (200, _ENTSOG_FLOWS_JSON)])
        source = EntsogSource(transport=transport, max_retries=1, backoff_seconds=0.0)
        frame = source.flows("ITP-00096", _START, _END)
        assert len(captured) == 2
        assert frame["point"].to_list() == ["ITP-00096", "ITP-00096"]

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValidationError, match="max_retries"):
            EntsogSource(max_retries=-1)

    def test_negative_backoff_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="backoff_seconds"):
            EntsogSource(backoff_seconds=-1.0)

    def test_period_type_default_matches_explicit_day(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, period_type="day")
        assert captured[0].url.params["periodType"] == "day"

    def test_period_type_override_changes_query_param(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, period_type="month")
        assert captured[0].url.params["periodType"] == "month"

    def test_indicator_default_matches_explicit_physical_flow(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows(
            "ITP-00096", _START, _END, indicator="Physical Flow"
        )
        assert captured[0].url.params["indicator"] == "Physical Flow"

    def test_indicator_override_changes_query_param(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, indicator="Allocation")
        assert captured[0].url.params["indicator"] == "Allocation"

    def test_limit_default_matches_explicit_minus_one(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, limit=-1)
        assert captured[0].url.params["limit"] == "-1"

    def test_limit_override_changes_query_param(self) -> None:
        transport, captured = _mock_transport(_ENTSOG_FLOWS_JSON)
        EntsogSource(transport=transport).flows("ITP-00096", _START, _END, limit=100)
        assert captured[0].url.params["limit"] == "100"


# --- Open-Meteo (Task 56) — recorded-style payload fixture ---------------------------------

_OPEN_METEO_JSON = """{
  "latitude": 52.37,
  "longitude": 4.9,
  "daily_units": {"time": "iso8601", "temperature_2m_mean": "\\u00b0C"},
  "daily": {
    "time": ["2026-01-01", "2026-01-02", "2026-01-03"],
    "temperature_2m_mean": [5.0, 30.0, null]
  }
}"""

_LOCATION = "52.37,4.90"


class TestOpenMeteoSource:
    def test_temperatures_returns_weather_compatible_frame(self) -> None:
        transport, _ = _mock_transport(_OPEN_METEO_JSON)
        source = OpenMeteoSource(transport=transport)

        frame = source.temperatures(_LOCATION, _START, _END)

        assert frame.columns == ["location", "date", "temp_celsius"]
        assert frame["location"].to_list() == [_LOCATION, _LOCATION]  # null day dropped
        assert frame["date"].to_list() == [date(2026, 1, 1), date(2026, 1, 2)]
        assert frame["temp_celsius"].to_list() == pytest.approx([5.0, 30.0])

    def test_fetched_frame_feeds_degree_days_directly(self) -> None:
        transport, _ = _mock_transport(_OPEN_METEO_JSON)
        frame = OpenMeteoSource(transport=transport).temperatures(_LOCATION, _START, _END)

        result = degree_days(frame)

        assert result["hdd"].to_list() == pytest.approx([13.0, 0.0])
        assert result["cdd"].to_list() == pytest.approx([0.0, 12.0])

    def test_open_meteo_is_keyless_no_token_required_or_sent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("QUANTVOLT_OPEN_METEO_TOKEN", raising=False)
        transport, captured = _mock_transport(_OPEN_METEO_JSON)

        OpenMeteoSource(transport=transport).temperatures(_LOCATION, _START, _END)

        (request,) = captured
        assert request.url.scheme == "https"
        assert "token" not in str(request.url).lower()
        assert request.url.params["latitude"] == "52.37"
        assert request.url.params["longitude"] == "4.9"
        assert request.url.params["daily"] == "temperature_2m_mean"
        assert request.url.params["start_date"] == "2026-01-01"
        assert request.url.params["end_date"] == "2026-01-03"

    @pytest.mark.parametrize("bad", ["Amsterdam", "52.37", "52.37,abc", "999,4.9", "52,999"])
    def test_malformed_location_raises_validation_error(self, bad: str) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        with pytest.raises(ValidationError, match="location"):
            OpenMeteoSource(transport=transport).temperatures(bad, _START, _END)
        assert captured == []

    def test_missing_daily_block_maps_to_data_unavailable(self) -> None:
        transport, _ = _mock_transport('{"latitude": 52.37}')
        with pytest.raises(DataUnavailableError, match="open_meteo"):
            OpenMeteoSource(transport=transport).temperatures(_LOCATION, _START, _END)

    def test_all_null_temperatures_map_to_data_unavailable(self) -> None:
        payload = '{"daily": {"time": ["2026-01-01"], "temperature_2m_mean": [null]}}'
        transport, _ = _mock_transport(payload)
        with pytest.raises(DataUnavailableError, match="no temperatures"):
            OpenMeteoSource(transport=transport).temperatures(_LOCATION, _START, _END)

    def test_429_maps_to_rate_limit_error(self) -> None:
        transport, _ = _mock_transport(status=429)
        with pytest.raises(RateLimitError, match="open_meteo"):
            OpenMeteoSource(transport=transport).temperatures(_LOCATION, _START, _END)

    def test_free_source_exposes_no_forward_curve(self) -> None:
        assert not hasattr(OpenMeteoSource(), "forward_curve")


class TestOpenMeteoConstructorParams:
    """New keyword-only constructor parameters: base_url, timeout_seconds, max_retries,
    backoff_seconds, daily_variable, timezone. Defaults reproduce today's behaviour exactly."""

    def test_base_url_default_matches_explicit_production_url(self) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        OpenMeteoSource(
            transport=transport, base_url="https://archive-api.open-meteo.com/v1/archive"
        ).temperatures(_LOCATION, _START, _END)
        assert captured[0].url.host == "archive-api.open-meteo.com"

    def test_base_url_override_changes_request_host(self) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        OpenMeteoSource(
            transport=transport, base_url="https://mirror.example.com/v1/archive"
        ).temperatures(_LOCATION, _START, _END)
        assert captured[0].url.host == "mirror.example.com"

    def test_timeout_seconds_default_matches_explicit_30(self) -> None:
        default = OpenMeteoSource()
        explicit = OpenMeteoSource(timeout_seconds=30.0)
        assert default._timeout_seconds == explicit._timeout_seconds == 30.0

    def test_timeout_seconds_override_changes_stored_value(self) -> None:
        assert OpenMeteoSource(timeout_seconds=5.0)._timeout_seconds == 5.0

    def test_non_positive_timeout_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="timeout_seconds"):
            OpenMeteoSource(timeout_seconds=0.0)

    def test_max_retries_default_zero_gives_no_retry_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(429, ""), (200, _OPEN_METEO_JSON)])
        source = OpenMeteoSource(transport=transport)
        with pytest.raises(RateLimitError):
            source.temperatures(_LOCATION, _START, _END)
        assert len(captured) == 1

    def test_max_retries_override_retries_on_transient_failure(self) -> None:
        transport, captured = _sequential_mock_transport([(429, ""), (200, _OPEN_METEO_JSON)])
        source = OpenMeteoSource(transport=transport, max_retries=1, backoff_seconds=0.0)
        frame = source.temperatures(_LOCATION, _START, _END)
        assert len(captured) == 2
        assert frame["temp_celsius"].to_list() == pytest.approx([5.0, 30.0])

    def test_negative_max_retries_raises(self) -> None:
        with pytest.raises(ValidationError, match="max_retries"):
            OpenMeteoSource(max_retries=-1)

    def test_negative_backoff_seconds_raises(self) -> None:
        with pytest.raises(ValidationError, match="backoff_seconds"):
            OpenMeteoSource(backoff_seconds=-1.0)

    def test_daily_variable_default_matches_explicit(self) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        OpenMeteoSource(transport=transport, daily_variable="temperature_2m_mean").temperatures(
            _LOCATION, _START, _END
        )
        assert captured[0].url.params["daily"] == "temperature_2m_mean"

    def test_daily_variable_override_changes_query_and_parses_response(self) -> None:
        payload = '{"daily": {"time": ["2026-01-01"], "temperature_2m_max": [9.5]}}'
        transport, captured = _mock_transport(payload)
        frame = OpenMeteoSource(
            transport=transport, daily_variable="temperature_2m_max"
        ).temperatures(_LOCATION, _START, _END)
        assert captured[0].url.params["daily"] == "temperature_2m_max"
        assert frame["temp_celsius"].to_list() == pytest.approx([9.5])

    def test_timezone_default_matches_explicit_utc(self) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        OpenMeteoSource(transport=transport, timezone="UTC").temperatures(_LOCATION, _START, _END)
        assert captured[0].url.params["timezone"] == "UTC"

    def test_timezone_override_changes_query_param(self) -> None:
        transport, captured = _mock_transport(_OPEN_METEO_JSON)
        OpenMeteoSource(transport=transport, timezone="Europe/Amsterdam").temperatures(
            _LOCATION, _START, _END
        )
        assert captured[0].url.params["timezone"] == "Europe/Amsterdam"


# --- Commercial stubs (Task 57) -------------------------------------------------------------

_COMMERCIAL_SOURCES: list[tuple[type[_CommercialSource], str]] = [
    (EexSource, "eex"),
    (IceSource, "ice"),
    (EpexSource, "epex"),
    (NordPoolSource, "nordpool"),
    (LsegSource, "lseg"),
]


class TestCommercialStubs:
    @pytest.mark.parametrize(("source_cls", "provider"), _COMMERCIAL_SOURCES)
    def test_forward_curve_raises_naming_provider_and_credential(
        self, source_cls: type[_CommercialSource], provider: str
    ) -> None:
        with pytest.raises(DataSourceError) as excinfo:
            source_cls().forward_curve(BUILT_IN_COMMODITIES["EUA"], date(2026, 7, 15))
        message = str(excinfo.value)
        assert provider in message
        assert "commercial licence" in message
        assert f"QUANTVOLT_{provider.upper()}_TOKEN" in message

    @pytest.mark.parametrize(("source_cls", "provider"), _COMMERCIAL_SOURCES)
    def test_settlement_prices_raise_until_configured(
        self, source_cls: type[_CommercialSource], provider: str
    ) -> None:
        with pytest.raises(DataSourceError, match=provider):
            source_cls().settlement_prices(BUILT_IN_COMMODITIES["EUA"], _START, _END)

    def test_stub_raises_even_with_credentials_supplied(self) -> None:
        source = EexSource(Credentials(api_key=_TOKEN))
        with pytest.raises(DataSourceError) as excinfo:
            source.forward_curve(BUILT_IN_COMMODITIES["EUA"], date(2026, 7, 15))
        assert _TOKEN not in str(excinfo.value)

    def test_only_commercial_sources_expose_forward_curve(self) -> None:
        for source_cls, _ in _COMMERCIAL_SOURCES:
            assert hasattr(source_cls(), "forward_curve")
        assert not hasattr(EntsoeSource(Credentials(token=_TOKEN)), "forward_curve")
        assert not hasattr(EntsogSource(), "forward_curve")
        assert not hasattr(OpenMeteoSource(), "forward_curve")
