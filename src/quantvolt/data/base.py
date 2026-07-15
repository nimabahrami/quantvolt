"""DataSource protocol, Credentials, errors, and snapshot/replay for the data layer (Task 53).

``quantvolt.data`` is the **optional imperative shell** (``pip install quantvolt[data]``) — the
only part of the library that performs I/O. The analytics core never imports it; the dependency
points inward (``data/`` -> ``models/``), and adapters return the same value objects the core
consumes, so fetched and caller-supplied data are interchangeable (Req 12.1, 12.2).

Credentials are caller-owned (Req 12.3, 12.4): they are read only from an explicit
:class:`Credentials` object or, when that is absent, from the documented
``QUANTVOLT_<PROVIDER>_TOKEN`` environment variables (explicit wins). They are never persisted,
cached, or logged; they are redacted from all string representations and error messages; and
they are transmitted only to their corresponding provider, only over HTTPS.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import urlsplit

import httpx

from ..exceptions import (
    AuthenticationError,
    DataSourceError,
    DataUnavailableError,
    RateLimitError,
)
from ..models.commodity import CommodityConfig
from ..models.curve import ForwardCurve

if TYPE_CHECKING:
    import polars as pl

# The error hierarchy lives in quantvolt.exceptions (single hierarchy, Req 11.5) and is
# re-exported here for the convenience of data-layer callers.
__all__ = [
    "AuthenticationError",
    "Credentials",
    "DataSource",
    "DataSourceError",
    "DataUnavailableError",
    "OAuthClientCredentials",
    "RateLimitError",
    "restore",
    "snapshot",
]


@dataclass(frozen=True)
class Credentials:
    """Caller-owned API keys. Never persisted or logged; redacted in repr.

    Resolution order (Req 12.3): an explicitly constructed ``Credentials`` object always wins;
    :meth:`from_env` is the documented environment-variable fallback. Credentials are read
    from nowhere else.
    """

    token: str | None = None
    api_key: str | None = None

    def __repr__(self) -> str:
        return "Credentials(***)"

    def __str__(self) -> str:
        return "Credentials(***)"

    @classmethod
    def from_env(cls, provider: str) -> Credentials:
        """Read ``QUANTVOLT_<PROVIDER>_TOKEN`` from the environment the caller set."""
        return cls(token=os.environ.get(f"QUANTVOLT_{provider.upper()}_TOKEN"))

    def require_token(self, provider: str) -> str:
        """Return the configured secret (``token``, else ``api_key``) or raise.

        Raises:
            AuthenticationError: If neither ``token`` nor ``api_key`` is set. The message
                names the provider and the ``QUANTVOLT_<PROVIDER>_TOKEN`` environment
                variable — never a credential value (Req 12.5).
        """
        value = self.token or self.api_key
        if value:
            return value
        env_var = f"QUANTVOLT_{provider.upper()}_TOKEN"
        raise AuthenticationError(
            f"{provider}: no credential configured; pass Credentials(token=...) or set the "
            f"{env_var} environment variable (credential values are never shown or logged)"
        )


@dataclass(frozen=True)
class OAuthClientCredentials:
    """Caller-owned OAuth 2 client credentials, always redacted in text output."""

    client_id: str | None = None
    client_secret: str | None = None

    def __repr__(self) -> str:
        return "OAuthClientCredentials(***)"

    def __str__(self) -> str:
        return "OAuthClientCredentials(***)"

    @classmethod
    def from_env(cls, provider: str) -> OAuthClientCredentials:
        """Read the provider's documented client-id and client-secret variables."""
        prefix = f"QUANTVOLT_{provider.upper()}"
        return cls(
            client_id=os.environ.get(f"{prefix}_CLIENT_ID"),
            client_secret=os.environ.get(f"{prefix}_CLIENT_SECRET"),
        )

    def require(self, provider: str) -> tuple[str, str]:
        """Return both OAuth values or raise without exposing either value."""
        if self.client_id and self.client_secret:
            return self.client_id, self.client_secret
        prefix = f"QUANTVOLT_{provider.upper()}"
        raise AuthenticationError(
            f"{provider}: OAuth client credentials are incomplete; pass "
            "OAuthClientCredentials(client_id=..., client_secret=...) or set "
            f"{prefix}_CLIENT_ID and {prefix}_CLIENT_SECRET (credential values are never "
            "shown or logged)"
        )


class DataSource(Protocol):
    """An adapter implements only the methods its provider actually supports.

    Free adapters (ENTSO-E, ENTSOG, Open-Meteo) provide spot/day-ahead prices, fundamentals,
    and weather; ``forward_curve`` is implemented **only** by commercial adapters or replaced
    by caller-supplied curves (Req 12.8).
    """

    def forward_curve(self, commodity: CommodityConfig, market_date: date) -> ForwardCurve: ...
    def price_series(self, commodity: CommodityConfig, start: date, end: date) -> pl.Series: ...
    def temperatures(self, location: str, start: date, end: date) -> pl.DataFrame: ...


class _SupportsToDict(Protocol):
    """A value object that serialises itself (serialisation lives on the model)."""

    def to_dict(self) -> dict[str, Any]: ...


def snapshot(obj: _SupportsToDict) -> dict[str, Any]:
    """Serialise a fetched value object to a JSON-friendly snapshot (Req 12.7).

    The fetch itself is non-deterministic (live data), but a persisted snapshot makes every
    downstream analytic reproducible: :func:`restore` rebuilds an equal value object, and the
    core's determinism (Req 11.2) guarantees identical results from identical inputs.
    Snapshots contain only market data — never credentials.
    """
    return obj.to_dict()


def restore(data: dict[str, Any]) -> ForwardCurve:
    """Rebuild a :class:`ForwardCurve` from a :func:`snapshot` dict (Req 12.7).

    ``restore(snapshot(curve)) == curve``, so re-running analytics from a stored snapshot
    reproduces identical results.
    """
    return ForwardCurve.from_dict(data)


def _require_https(url: str) -> None:
    """Refuse any non-HTTPS provider URL (Req 12.4). All adapters call this before a request.

    The error names only the scheme and host — never the query string, which may carry a
    credential.
    """
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise DataSourceError(
            f"refusing non-HTTPS provider URL (scheme {parts.scheme!r}, "
            f"host {parts.hostname or ''!r}); credentials are transmitted only over HTTPS"
        )


def _raise_for_status(provider: str, status_code: int) -> None:
    """Map a provider HTTP status onto the library error hierarchy (Req 12.5).

    Messages name the provider and the credential *name* (the env var), never a credential
    value, and never echo the request URL or response body.
    """
    if status_code in (401, 403):
        env_var = f"QUANTVOLT_{provider.upper()}_TOKEN"
        raise AuthenticationError(
            f"{provider}: credential missing or rejected by the provider "
            f"(HTTP {status_code}); check Credentials(token=...) or {env_var} "
            "(credential values are never shown or logged)"
        )
    if status_code == 429:
        raise RateLimitError(f"{provider}: rate limit exceeded (HTTP 429); retry later")
    if status_code >= 400:
        raise DataSourceError(f"{provider}: provider request failed (HTTP {status_code})")


def _is_transient_status(status_code: int) -> bool:
    """HTTP 5xx or 429 (rate limit) — the only statuses a retry can plausibly help."""
    return status_code >= 500 or status_code == 429


def _get_with_retries(
    client: httpx.Client,
    url: str,
    params: dict[str, str],
    *,
    headers: dict[str, str] | None = None,
    max_retries: int,
    backoff_seconds: float,
) -> httpx.Response:
    """One HTTPS GET with deterministic exponential-backoff retry on transient failures.

    Shared by every free adapter (Task retry knob) so the retry policy is defined once.
    Retries only on ``httpx.TransportError`` (connection failures) and HTTP 5xx / 429 —
    a non-transient client error (4xx other than 429) is returned immediately for the
    caller's usual :func:`_raise_for_status` mapping (unchanged fail-loudly behaviour).

    Backoff is deterministic (no jitter, per the library's determinism convention):
    ``backoff_seconds * 2**attempt`` between attempts, ``attempt`` starting at 0. With
    ``max_retries=0`` (the default for every adapter) no retry ever happens and the
    call is bit-for-bit today's single GET.
    """
    attempt = 0
    while True:
        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TransportError:
            if attempt >= max_retries:
                raise
        else:
            if attempt >= max_retries or not _is_transient_status(response.status_code):
                return response
        time.sleep(backoff_seconds * (2**attempt))
        attempt += 1
