"""Data-layer isolation & security tests (Task 58; Req 12.1, 12.3, 12.4, 12.5, 12.7).

The core must never pull in ``quantvolt.data``; credentials must never leak into any string
representation, error message, or snapshot; and snapshots must reproduce identical downstream
results, making fetched and caller-supplied data fully interchangeable.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import httpx
import polars as pl
import pytest

from quantvolt.data.base import Credentials, restore, snapshot
from quantvolt.data.entsoe import EntsoeSource
from quantvolt.exceptions import AuthenticationError
from quantvolt.market.weather import degree_days
from quantvolt.models.commodity import BUILT_IN_COMMODITIES
from quantvolt.models.curve import CurveNode, ForwardCurve
from quantvolt.models.discount_curve import DiscountCurve
from quantvolt.models.instruments import FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.pricing.futures import price_futures

_SECRET = "leaky-secret-token-b7e4"
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "quantvolt"

# Import statements that would couple the core to the data layer, in any spelling reachable
# from inside the package (absolute, or relative from any depth).
_FORBIDDEN_IMPORT_PREFIXES = (
    "import quantvolt.data",
    "from quantvolt.data",
    "from quantvolt import data",
    "from .data",
    "from ..data",
    "from ...data",
    "from . import data",
    "from .. import data",
)


class TestImportIsolation:
    def test_importing_the_core_never_loads_the_data_package(self) -> None:
        """Req 12.1: `import quantvolt` in a fresh interpreter pulls no quantvolt.data.*"""
        code = (
            "import quantvolt, sys; "
            "loaded = [m for m in sys.modules if m.startswith('quantvolt.data')]; "
            "assert not loaded, f'core imported data layer: {loaded}'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_no_core_source_file_imports_the_data_layer(self) -> None:
        """Static sweep of every core module for any import of quantvolt.data."""
        assert _SRC_ROOT.is_dir(), f"source tree not found at {_SRC_ROOT}"
        offenders: list[str] = []
        for path in sorted(_SRC_ROOT.rglob("*.py")):
            relative = path.relative_to(_SRC_ROOT)
            if relative.parts[0] == "data":
                continue  # the data layer itself may import its own modules
            for line_number, line in enumerate(path.read_text().splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith(_FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(f"{relative}:{line_number}: {stripped}")
        assert offenders == [], f"core modules import the data layer: {offenders}"

    def test_core_packages_were_swept(self) -> None:
        """Guard the sweep itself: every implemented core package is present and scanned."""
        for package in (
            "models",
            "numerics",
            "curves",
            "pricing",
            "risk",
            "stats",
            "market",
            "workflow",
            "portfolio",
        ):
            assert (_SRC_ROOT / package).is_dir(), f"expected core package {package!r}"


def _entsoe_401_transport() -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(401, text="unauthorised"))


def _curve() -> ForwardCurve:
    return ForwardCurve(
        commodity=BUILT_IN_COMMODITIES["EPEX_DE"],
        market_date=date(2026, 7, 15),
        nodes=(
            CurveNode(DeliveryPeriod(2026, 9), 84.5, "observed"),
            CurveNode(DeliveryPeriod(2026, 10), 91.25, "interpolated"),
        ),
    )


class TestCredentialSecurity:
    def test_secret_never_appears_in_repr_or_str(self) -> None:
        credentials = Credentials(token=_SECRET, api_key=_SECRET)
        assert _SECRET not in repr(credentials)
        assert _SECRET not in str(credentials)
        assert repr(credentials) == "Credentials(***)"

    def test_secret_never_appears_in_rejected_credential_error(self) -> None:
        source = EntsoeSource(Credentials(token=_SECRET), transport=_entsoe_401_transport())
        with pytest.raises(AuthenticationError) as excinfo:
            source.price_series(BUILT_IN_COMMODITIES["EPEX_DE"], date(2026, 1, 1), date(2026, 1, 2))
        assert _SECRET not in str(excinfo.value)
        assert _SECRET not in repr(excinfo.value)

    def test_missing_credential_error_names_only_provider_and_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("QUANTVOLT_ENTSOE_TOKEN", _SECRET)
        credentials = Credentials.from_env("entsoe")
        with pytest.raises(AuthenticationError) as excinfo:
            Credentials().require_token("entsoe")
        assert _SECRET not in str(excinfo.value)
        assert credentials.token == _SECRET  # env value was readable, but never leaked

    def test_secret_never_appears_in_a_snapshot(self) -> None:
        # Snapshots carry market data only; serialise one end-to-end and sweep for the secret.
        payload = json.dumps(snapshot(_curve()))
        assert _SECRET not in payload


class TestSnapshotRoundTrip:
    def test_restored_snapshot_reproduces_identical_pricing(self) -> None:
        """Req 12.7: analytics from a snapshot are bit-identical to the original run."""
        curve = _curve()
        contract = FuturesContract(
            commodity=BUILT_IN_COMMODITIES["EPEX_DE"],
            delivery_period=DeliveryPeriod(2026, 9),
            contract_price=80.0,
            notional=100.0,
        )
        discount_curve = DiscountCurve(
            reference_date=date(2026, 7, 15),
            tenors=(date(2026, 8, 31), date(2026, 12, 31)),
            factors=(0.997, 0.988),
        )
        valuation_date = date(2026, 7, 15)

        restored = restore(json.loads(json.dumps(snapshot(curve))))
        original = price_futures(contract, curve, valuation_date, discount_curve)
        replayed = price_futures(contract, restored, valuation_date, discount_curve)

        assert restored == curve
        assert replayed.npv == original.npv
        assert replayed.delta == original.delta


_ENTSOE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Publication_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3">
  <TimeSeries><Period>
    <timeInterval><start>2026-01-01T23:00Z</start><end>2026-01-02T01:00Z</end></timeInterval>
    <resolution>PT60M</resolution>
    <Point><position>1</position><price.amount>50.10</price.amount></Point>
    <Point><position>2</position><price.amount>48.30</price.amount></Point>
  </Period></TimeSeries>
</Publication_MarketDocument>
"""

_OPEN_METEO_JSON = (
    '{"daily": {"time": ["2026-01-01", "2026-01-02"], "temperature_2m_mean": [5.0, 30.0]}}'
)


class TestInterchangeability:
    def test_fetched_price_series_equals_caller_supplied(self) -> None:
        """Req 12.2: a fetched value object is indistinguishable from a caller-built one."""
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=_ENTSOE_XML))
        source = EntsoeSource(Credentials(token="t"), transport=transport)

        fetched = source.price_series(
            BUILT_IN_COMMODITIES["EPEX_DE"], date(2026, 1, 1), date(2026, 1, 2)
        )
        caller_supplied = pl.Series(name="EPEX_DE", values=[50.10, 48.30], dtype=pl.Float64)

        assert fetched.equals(caller_supplied)
        assert fetched.mean() == caller_supplied.mean()

    def test_fetched_temperatures_run_degree_days_identically(self) -> None:
        from quantvolt.data.open_meteo import OpenMeteoSource

        transport = httpx.MockTransport(lambda request: httpx.Response(200, text=_OPEN_METEO_JSON))
        fetched = OpenMeteoSource(transport=transport).temperatures(
            "52.37,4.90", date(2026, 1, 1), date(2026, 1, 2)
        )
        caller_supplied = pl.DataFrame(
            {
                "location": ["52.37,4.90", "52.37,4.90"],
                "date": [date(2026, 1, 1), date(2026, 1, 2)],
                "temp_celsius": [5.0, 30.0],
            }
        )

        assert fetched.equals(caller_supplied)
        assert degree_days(fetched).equals(degree_days(caller_supplied))
