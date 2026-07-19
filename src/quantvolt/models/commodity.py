"""Commodity/hub value objects and the built-in commodity registry (Task 4).

The registry is extended, never edited: callers pass a ``dict[str, CommodityConfig]``
that is merged *over* :data:`BUILT_IN_COMMODITIES` (caller entries win). This is the
Adapter seam for Req 1.6 (OCP) and is reused by ``CurveBuilder``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import ValidationError
from .units import PriceUnit


@dataclass(frozen=True, slots=True)
class Hub:
    hub_id: str  # e.g. "TTF", "EEX_PHELIX_DE"
    exchange: str  # e.g. "ICE_ENDEX", "EEX"
    price_unit: str  # e.g. "EUR/MWh", "GBp/therm"

    def __post_init__(self) -> None:
        PriceUnit.parse(self.price_unit)


@dataclass(frozen=True, slots=True)
class CommodityConfig:
    commodity_id: str
    price_unit: str
    hub: Hub

    def __post_init__(self) -> None:
        PriceUnit.parse(self.price_unit)


# Default registry (design §3.4). A module-level constant — NOT a Singleton and
# never mutated; extensions merge over it via merge_commodities/resolve_commodity.
BUILT_IN_COMMODITIES: dict[str, CommodityConfig] = {
    "EEX_PHELIX_DE": CommodityConfig(
        "EEX_PHELIX_DE", "EUR/MWh", Hub("EEX_PHELIX_DE", "EEX", "EUR/MWh")
    ),
    "EEX_PHELIX_AT": CommodityConfig(
        "EEX_PHELIX_AT", "EUR/MWh", Hub("EEX_PHELIX_AT", "EEX", "EUR/MWh")
    ),
    "EPEX_DE": CommodityConfig("EPEX_DE", "EUR/MWh", Hub("EPEX_DE", "EPEX_SPOT", "EUR/MWh")),
    "EPEX_FR": CommodityConfig("EPEX_FR", "EUR/MWh", Hub("EPEX_FR", "EPEX_SPOT", "EUR/MWh")),
    "EPEX_NL": CommodityConfig("EPEX_NL", "EUR/MWh", Hub("EPEX_NL", "EPEX_SPOT", "EUR/MWh")),
    "EPEX_BE": CommodityConfig("EPEX_BE", "EUR/MWh", Hub("EPEX_BE", "EPEX_SPOT", "EUR/MWh")),
    "EPEX_GB": CommodityConfig("EPEX_GB", "GBP/MWh", Hub("EPEX_GB", "EPEX_SPOT", "GBP/MWh")),
    "TTF": CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh")),
    "NBP": CommodityConfig("NBP", "GBp/therm", Hub("NBP", "ICE_ENDEX", "GBp/therm")),
    # THE (Germany), PEG (France), ZTP (Belgium), PSV (Italy): additional liquid European
    # gas hubs (Req 7, deferred). All quoted EUR/MWh on ICE Endex, their native venue
    # quotation -- see docs/market_conventions.json and design.md References for the
    # verbatim ICE product-specification citations (fetched 2026-07-18).
    "THE": CommodityConfig("THE", "EUR/MWh", Hub("THE", "ICE_ENDEX", "EUR/MWh")),
    "PEG": CommodityConfig("PEG", "EUR/MWh", Hub("PEG", "ICE_ENDEX", "EUR/MWh")),
    "ZTP": CommodityConfig("ZTP", "EUR/MWh", Hub("ZTP", "ICE_ENDEX", "EUR/MWh")),
    "PSV": CommodityConfig("PSV", "EUR/MWh", Hub("PSV", "ICE_ENDEX", "EUR/MWh")),
    "EUA": CommodityConfig("EUA", "EUR/tCO2", Hub("EUA", "EEX", "EUR/tCO2")),
}


def merge_commodities(
    extra_commodities: dict[str, CommodityConfig] | None = None,
) -> dict[str, CommodityConfig]:
    """Return a new registry: ``extra_commodities`` merged OVER the built-ins.

    Caller-supplied entries win on id collision (Adapter seam, Req 1.6). Neither
    :data:`BUILT_IN_COMMODITIES` nor ``extra_commodities`` is mutated — the result
    is a fresh dict. ``CurveBuilder`` reuses this to assemble its registry.
    """
    merged = dict(BUILT_IN_COMMODITIES)
    if extra_commodities is not None:
        merged.update(extra_commodities)
    return merged


def resolve_commodity(
    commodity_id: str,
    extra_commodities: dict[str, CommodityConfig] | None = None,
) -> CommodityConfig:
    """Look up ``commodity_id`` in the merged registry (caller entries take precedence).

    Raises :class:`ValidationError` naming the unknown id and listing the available
    ids when no match is found.
    """
    registry = merge_commodities(extra_commodities)
    try:
        return registry[commodity_id]
    except KeyError:
        available = ", ".join(sorted(registry))
        raise ValidationError(
            f"commodity_id {commodity_id!r} is not a known commodity; available ids: {available}"
        ) from None
