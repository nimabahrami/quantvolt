"""Commercial-provider stubs (Task 57): forward/futures curves, EUA, settlement prices.

Forward and futures curves are available **only** from commercial providers or from
caller-supplied data (Req 12.8); the free adapters (ENTSO-E, ENTSOG, Open-Meteo) never expose
a ``forward_curve`` method. Each stub below documents the paid credential it will use and
raises a clear :class:`~quantvolt.exceptions.DataSourceError` until a commercial licence is
configured and the adapter implemented. EUA carbon allowances flow through the same methods
using the built-in ``"EUA"`` commodity (listed on EEX / ICE).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from ..exceptions import DataSourceError
from ..models.commodity import CommodityConfig
from ..models.curve import ForwardCurve
from .base import Credentials

if TYPE_CHECKING:
    import polars as pl


class _CommercialSource:
    """Shared stub base: every data method raises until a paid credential is usable.

    Subclasses set ``provider`` (the credential key, giving the env var
    ``QUANTVOLT_<PROVIDER>_TOKEN``) and ``display_name`` (the human-readable vendor).
    """

    provider = "commercial"
    display_name = "a commercial provider"

    def __init__(self, credentials: Credentials | None = None) -> None:
        """Explicit ``credentials`` win; otherwise ``QUANTVOLT_<PROVIDER>_TOKEN`` is read."""
        self._credentials = credentials or Credentials.from_env(self.provider)

    def _not_configured(self, method: str) -> DataSourceError:
        env_var = f"QUANTVOLT_{self.provider.upper()}_TOKEN"
        return DataSourceError(
            f"{self.provider}: {method} requires a commercial licence with "
            f"{self.display_name}; once licensed, configure Credentials(api_key=...) or "
            f"{env_var} — or supply the data yourself. Free adapters (ENTSO-E, ENTSOG, "
            "Open-Meteo) are never forward-curve sources (Req 12.8)."
        )

    def forward_curve(self, commodity: CommodityConfig, market_date: date) -> ForwardCurve:
        """Forward/futures curve as of ``market_date`` — commercial data (Req 12.8).

        Raises:
            DataSourceError: Always, until a commercial licence is configured; the message
                names the provider and the credential to configure.
        """
        raise self._not_configured("forward_curve")

    def settlement_prices(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series:
        """Exchange settlement prices over ``[start, end]``, incl. EUA via the ``"EUA"``
        commodity — commercial data.

        Raises:
            DataSourceError: Always, until a commercial licence is configured; the message
                names the provider and the credential to configure.
        """
        raise self._not_configured("settlement_prices")


class EexSource(_CommercialSource):
    """EEX Group market data: power/gas futures curves, EUA and settlement prices.

    Requires a paid EEX Group data subscription. Configure ``Credentials(api_key=...)`` or
    ``QUANTVOLT_EEX_TOKEN``.
    """

    provider = "eex"
    display_name = "EEX Group"


class IceSource(_CommercialSource):
    """ICE Endex market data: TTF/NBP gas futures curves, EUA and settlement prices.

    Requires a paid ICE data licence. Configure ``Credentials(api_key=...)`` or
    ``QUANTVOLT_ICE_TOKEN``.
    """

    provider = "ice"
    display_name = "ICE Endex"


class EpexSource(_CommercialSource):
    """EPEX SPOT market data beyond the free transparency feeds.

    Requires a paid EPEX SPOT data agreement. Configure ``Credentials(api_key=...)`` or
    ``QUANTVOLT_EPEX_TOKEN``.
    """

    provider = "epex"
    display_name = "EPEX SPOT"


class NordPoolSource(_CommercialSource):
    """Nord Pool market data: Nordic/Baltic curves and settlement prices.

    Requires a paid Nord Pool data licence. Configure ``Credentials(api_key=...)`` or
    ``QUANTVOLT_NORDPOOL_TOKEN``.
    """

    provider = "nordpool"
    display_name = "Nord Pool"


class LsegSource(_CommercialSource):
    """LSEG (Refinitiv) market data: broker forward curves and settlement prices.

    Requires a paid LSEG/Refinitiv subscription. Configure ``Credentials(api_key=...)`` or
    ``QUANTVOLT_LSEG_TOKEN``.
    """

    provider = "lseg"
    display_name = "LSEG (Refinitiv)"
