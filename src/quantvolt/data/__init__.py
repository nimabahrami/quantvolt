"""quantvolt.data — OPTIONAL imperative shell (`quantvolt[data]`) — provider API adapters.

The analytics core never imports this package (Req 12.1); install the extra
(``pip install quantvolt[data]``) to pull ``httpx``. Adapters return the same value objects
the core consumes, so fetched and caller-supplied data are interchangeable (Req 12.2).
"""

from __future__ import annotations

from ..exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    RateLimitError,
)
from .base import Credentials, DataSource, OAuthClientCredentials, restore, snapshot
from .commercial import EexSource, EpexSource, IceSource, LsegSource, NordPoolSource
from .datasets import DatasetRecord, fetch, info, list_datasets, path, remove, verify
from .entsoe import EntsoeSource
from .entsog import EntsogSource
from .netztransparenz import NetztransparenzSource, attach_rebap_prices, parse_rebap_csv
from .open_meteo import OpenMeteoSource
from .smard import SmardResolution, SmardSource

__all__ = [
    "AuthenticationError",
    "Credentials",
    "DataSource",
    "DataSourceError",
    "DataUnavailableError",
    "DatasetRecord",
    "EexSource",
    "EntsoeSource",
    "EntsogSource",
    "EpexSource",
    "IceSource",
    "LsegSource",
    "NetztransparenzSource",
    "NordPoolSource",
    "OAuthClientCredentials",
    "OpenMeteoSource",
    "RateLimitError",
    "SmardResolution",
    "SmardSource",
    "attach_rebap_prices",
    "fetch",
    "info",
    "list_datasets",
    "parse_rebap_csv",
    "path",
    "remove",
    "restore",
    "snapshot",
    "verify",
]
