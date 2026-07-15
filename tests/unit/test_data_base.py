"""Unit tests for the data-layer foundation (Task 53): credentials, errors, snapshot, HTTPS."""

from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

import quantvolt.data as data_pkg
from quantvolt.data.base import Credentials, _get_with_retries, _require_https, restore, snapshot
from quantvolt.exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    EnergyQuantError,
    RateLimitError,
)
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.schedule import DeliveryPeriod

_SECRET = "super-secret-token-3f9a"


def _curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=BUILT_IN_COMMODITIES["TTF"],
        market_date=date(2026, 6, 30),
        nodes=(
            CurveNode(DeliveryPeriod(2026, 8), 31.5, "observed"),
            CurveNode(DeliveryPeriod(2026, 9), 32.25, "interpolated"),
        ),
    )


class TestCredentials:
    def test_repr_always_redacts(self) -> None:
        credentials = Credentials(token=_SECRET, api_key=_SECRET)
        assert repr(credentials) == "Credentials(***)"
        assert _SECRET not in repr(credentials)

    def test_str_always_redacts(self) -> None:
        credentials = Credentials(token=_SECRET)
        assert str(credentials) == "Credentials(***)"
        assert _SECRET not in str(credentials)

    def test_from_env_reads_documented_variable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUANTVOLT_ENTSOE_TOKEN", _SECRET)
        assert Credentials.from_env("entsoe").token == _SECRET

    def test_from_env_uppercases_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("QUANTVOLT_OPEN_METEO_TOKEN", _SECRET)
        assert Credentials.from_env("open_meteo").token == _SECRET

    def test_from_env_missing_variable_gives_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("QUANTVOLT_ENTSOE_TOKEN", raising=False)
        assert Credentials.from_env("entsoe").token is None

    def test_require_token_returns_token(self) -> None:
        assert Credentials(token=_SECRET).require_token("entsoe") == _SECRET

    def test_require_token_falls_back_to_api_key(self) -> None:
        assert Credentials(api_key=_SECRET).require_token("eex") == _SECRET

    def test_require_token_missing_names_provider_and_env_var(self) -> None:
        with pytest.raises(AuthenticationError) as excinfo:
            Credentials().require_token("entsoe")
        message = str(excinfo.value)
        assert "entsoe" in message
        assert "QUANTVOLT_ENTSOE_TOKEN" in message

    def test_require_token_treats_empty_string_as_missing(self) -> None:
        with pytest.raises(AuthenticationError):
            Credentials(token="").require_token("entsoe")


class TestErrorHierarchy:
    def test_data_source_error_is_energy_quant_error(self) -> None:
        assert issubclass(DataSourceError, EnergyQuantError)

    @pytest.mark.parametrize("error", [AuthenticationError, RateLimitError, DataUnavailableError])
    def test_specific_errors_are_data_source_errors(self, error: type[DataSourceError]) -> None:
        assert issubclass(error, DataSourceError)

    def test_base_module_reexports_the_exceptions_classes(self) -> None:
        from quantvolt.data import base

        assert base.DataSourceError is DataSourceError
        assert base.AuthenticationError is AuthenticationError
        assert base.RateLimitError is RateLimitError
        assert base.DataUnavailableError is DataUnavailableError

    def test_package_reexports_foundation_names(self) -> None:
        assert data_pkg.Credentials is Credentials
        assert data_pkg.snapshot is snapshot
        assert data_pkg.restore is restore
        assert data_pkg.DataSourceError is DataSourceError


class TestSnapshotRestore:
    def test_round_trip_returns_equal_curve(self) -> None:
        curve = _curve()
        assert restore(snapshot(curve)) == curve

    def test_snapshot_is_json_serialisable(self) -> None:
        payload = json.dumps(snapshot(_curve()))
        assert "TTF" in payload

    def test_round_trip_through_json_returns_equal_curve(self) -> None:
        curve = _curve()
        restored = restore(json.loads(json.dumps(snapshot(curve))))
        assert restored == curve
        assert restored.price_at(DeliveryPeriod(2026, 8)) == curve.price_at(DeliveryPeriod(2026, 8))


class TestRequireHttps:
    def test_https_url_passes(self) -> None:
        _require_https("https://web-api.tp.entsoe.eu/api")

    def test_http_url_raises_data_source_error(self) -> None:
        with pytest.raises(DataSourceError, match="HTTPS"):
            _require_https("http://web-api.tp.entsoe.eu/api")

    def test_other_scheme_raises_data_source_error(self) -> None:
        with pytest.raises(DataSourceError):
            _require_https("ftp://example.com/data")

    def test_error_never_echoes_the_query_string(self) -> None:
        with pytest.raises(DataSourceError) as excinfo:
            _require_https(f"http://example.com/api?securityToken={_SECRET}")
        assert _SECRET not in str(excinfo.value)


def _counting_transport(statuses: list[int]) -> tuple[httpx.MockTransport, list[int]]:
    """A MockTransport returning ``statuses`` in order (last one repeats); records attempts."""
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        status = statuses[min(len(attempts) - 1, len(statuses) - 1)]
        return httpx.Response(status)

    return httpx.MockTransport(handler), attempts


class TestGetWithRetries:
    """The shared retry helper backing every free adapter's ``max_retries`` knob."""

    def test_default_max_retries_zero_makes_one_attempt_on_transient_failure(self) -> None:
        transport, attempts = _counting_transport([500, 200])
        with httpx.Client(transport=transport) as client:
            response = _get_with_retries(
                client, "https://example.com", {}, max_retries=0, backoff_seconds=0.0
            )
        assert len(attempts) == 1
        assert response.status_code == 500

    def test_max_retries_override_retries_transient_status_until_success(self) -> None:
        transport, attempts = _counting_transport([500, 429, 200])
        with httpx.Client(transport=transport) as client:
            response = _get_with_retries(
                client, "https://example.com", {}, max_retries=2, backoff_seconds=0.0
            )
        assert len(attempts) == 3
        assert response.status_code == 200

    def test_non_transient_status_returned_immediately_without_retry(self) -> None:
        transport, attempts = _counting_transport([404, 200])
        with httpx.Client(transport=transport) as client:
            response = _get_with_retries(
                client, "https://example.com", {}, max_retries=3, backoff_seconds=0.0
            )
        assert len(attempts) == 1
        assert response.status_code == 404

    def test_transport_error_retried_up_to_max_retries(self) -> None:
        attempts: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempts.append(1)
            raise httpx.ConnectError("boom", request=request)

        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client, pytest.raises(httpx.ConnectError):
            _get_with_retries(client, "https://example.com", {}, max_retries=2, backoff_seconds=0.0)
        assert len(attempts) == 3  # initial attempt + 2 retries

    def test_backoff_seconds_default_matches_explicit_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr(
            "quantvolt.data.base.time.sleep", lambda seconds: sleeps.append(seconds)
        )
        transport, _ = _counting_transport([500, 200])
        with httpx.Client(transport=transport) as client:
            _get_with_retries(client, "https://example.com", {}, max_retries=1, backoff_seconds=1.0)
        assert sleeps == [1.0]

    def test_backoff_seconds_override_changes_sleep_duration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sleeps: list[float] = []
        monkeypatch.setattr(
            "quantvolt.data.base.time.sleep", lambda seconds: sleeps.append(seconds)
        )
        transport, _ = _counting_transport([500, 500, 200])
        with httpx.Client(transport=transport) as client:
            _get_with_retries(
                client, "https://example.com", {}, max_retries=2, backoff_seconds=0.25
            )
        assert sleeps == [0.25, 0.5]  # deterministic exponential backoff, no jitter
