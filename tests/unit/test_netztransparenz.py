from __future__ import annotations

from datetime import UTC, datetime

import httpx
import polars as pl
import pytest

from quantvolt.data import (
    NetztransparenzSource,
    OAuthClientCredentials,
    attach_rebap_prices,
    parse_rebap_csv,
)
from quantvolt.exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    ValidationError,
)

_HEADER = (
    "Datum;Zeitzone;von;bis;Datenkategorie;Datentyp;Einheit;reBAP unterdeckt;reBAP ueberdeckt\n"
)
_CSV = _HEADER + (
    "10.06.2023;UTC;23:45;00:00;reBAP;Qualitätsgesichert;EUR/MWh;103,97;98,12\n"
    "11.06.2023;UTC;00:00;00:15;reBAP;Qualitätsgesichert;EUR/MWh;-5,50;-8,25\n"
)


def test_parse_rebap_csv_preserves_asymmetry_negative_prices_and_midnight() -> None:
    frame = parse_rebap_csv(_CSV)

    assert frame.columns == [
        "interval_start_utc",
        "interval_end_utc",
        "shortfall_price_per_mwh",
        "excess_price_per_mwh",
        "unit",
        "source",
    ]
    assert frame["interval_start_utc"].to_list() == [
        datetime(2023, 6, 10, 23, 45, tzinfo=UTC),
        datetime(2023, 6, 11, 0, 0, tzinfo=UTC),
    ]
    assert frame["interval_end_utc"][0] == datetime(2023, 6, 11, 0, 0, tzinfo=UTC)
    assert frame["shortfall_price_per_mwh"].to_list() == [103.97, -5.5]
    assert frame["excess_price_per_mwh"].to_list() == [98.12, -8.25]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (_CSV.replace(";UTC;", ";CET;", 1), "timezone must be UTC"),
        (_CSV.replace("23:45;00:00", "23:45;00:30"), "not exactly 15 minutes"),
        (_CSV + _CSV.splitlines()[1] + "\n", "duplicate interval"),
        (_CSV.replace("103,97", "", 1), "missing under-covered"),
    ],
)
def test_parse_rebap_csv_rejects_unsafe_provider_data(body: str, message: str) -> None:
    with pytest.raises((DataSourceError, DataUnavailableError), match=message):
        parse_rebap_csv(body)


def test_attach_rebap_prices_uses_both_exact_interval_keys_and_preserves_rows() -> None:
    prices = parse_rebap_csv(_CSV)
    caller = pl.DataFrame(
        {
            "from": prices["interval_start_utc"],
            "to": prices["interval_end_utc"],
            "metered_mwh": [1.2, 1.1],
        }
    )

    result = attach_rebap_prices(
        caller, prices, interval_start_column="from", interval_end_column="to"
    )

    assert result["metered_mwh"].to_list() == [1.2, 1.1]
    assert result["shortfall_price_per_mwh"].to_list() == [103.97, -5.5]
    assert caller.columns == ["from", "to", "metered_mwh"]


def test_attach_rebap_prices_rejects_missing_match_and_overwrite() -> None:
    prices = parse_rebap_csv(_CSV)
    missing = pl.DataFrame(
        {
            "interval_start_utc": [datetime(2023, 6, 12, tzinfo=UTC)],
            "interval_end_utc": [datetime(2023, 6, 12, 0, 15, tzinfo=UTC)],
        }
    )
    with pytest.raises(DataUnavailableError, match="no exact reBAP match"):
        attach_rebap_prices(missing, prices)
    with pytest.raises(ValidationError, match="already contains"):
        attach_rebap_prices(
            missing.with_columns(pl.lit(1.0).alias("shortfall_price_per_mwh")), prices
        )


def test_oauth_credentials_are_redacted_and_support_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUANTVOLT_NETZTRANSPARENZ_CLIENT_ID", "client-value")
    monkeypatch.setenv("QUANTVOLT_NETZTRANSPARENZ_CLIENT_SECRET", "secret-value")
    credentials = OAuthClientCredentials.from_env("netztransparenz")

    assert credentials.require("netztransparenz") == ("client-value", "secret-value")
    assert "client-value" not in repr(credentials)
    assert "secret-value" not in str(credentials)


def test_source_uses_oauth_bearer_and_official_date_path() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.host == "identity.netztransparenz.de":
            assert request.content == (
                b"grant_type=client_credentials&client_id=my-client&client_secret=my-secret"
            )
            return httpx.Response(200, json={"access_token": "ephemeral-token"})
        assert request.headers["Authorization"] == "Bearer ephemeral-token"
        assert request.url.raw_path.endswith(b"/2023-06-10T23%3A45%3A00/2023-06-11T00%3A15%3A00")
        return httpx.Response(200, text=_CSV)

    source = NetztransparenzSource(
        OAuthClientCredentials("my-client", "my-secret"),
        transport=httpx.MockTransport(handler),
    )
    result = source.rebap(
        datetime(2023, 6, 10, 23, 45, tzinfo=UTC),
        datetime(2023, 6, 11, 0, 15, tzinfo=UTC),
    )

    assert result.height == 2
    assert len(requests) == 2


def test_source_fails_before_network_without_credentials() -> None:
    source = NetztransparenzSource(OAuthClientCredentials())
    with pytest.raises(AuthenticationError, match="CLIENT_ID"):
        source.rebap(datetime(2023, 6, 10, tzinfo=UTC), datetime(2023, 6, 11, tzinfo=UTC))
