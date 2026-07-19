"""Unit tests for the commodity registry and its extension seam (Task 4, Req 1.6)."""

from __future__ import annotations

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import (
    BUILT_IN_COMMODITIES,
    CommodityConfig,
    Hub,
    merge_commodities,
    resolve_commodity,
)


def test_registry_has_exactly_the_fourteen_built_ins() -> None:
    assert set(BUILT_IN_COMMODITIES) == {
        "EEX_PHELIX_DE",
        "EEX_PHELIX_AT",
        "EPEX_DE",
        "EPEX_FR",
        "EPEX_NL",
        "EPEX_BE",
        "EPEX_GB",
        "TTF",
        "NBP",
        "THE",
        "PEG",
        "ZTP",
        "PSV",
        "EUA",
    }


def test_builtin_lookup_returns_expected_config() -> None:
    ttf = resolve_commodity("TTF")
    assert ttf == CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))
    assert ttf.hub.exchange == "ICE_ENDEX"


def test_nbp_native_quotation_is_pence_per_therm() -> None:
    nbp = resolve_commodity("NBP")
    assert nbp == CommodityConfig("NBP", "GBp/therm", Hub("NBP", "ICE_ENDEX", "GBp/therm"))


@pytest.mark.parametrize("hub_id", ["THE", "PEG", "ZTP", "PSV"])
def test_deferred_european_gas_hubs_are_eur_per_mwh_on_ice_endex(hub_id: str) -> None:
    """Requirement 7 (deferred, Task 13): THE/PEG/ZTP/PSV at EUR/MWh, ICE Endex."""
    config = resolve_commodity(hub_id)
    assert config == CommodityConfig(hub_id, "EUR/MWh", Hub(hub_id, "ICE_ENDEX", "EUR/MWh"))


def test_builtin_lookup_without_extras_matches_registry_entry() -> None:
    assert resolve_commodity("EUA") is BUILT_IN_COMMODITIES["EUA"]


def test_extension_adds_a_brand_new_id() -> None:
    nordpool = CommodityConfig("NP_SYS", "EUR/MWh", Hub("NP_SYS", "NORDPOOL", "EUR/MWh"))
    resolved = resolve_commodity("NP_SYS", {"NP_SYS": nordpool})
    assert resolved is nordpool


def test_caller_override_of_builtin_id_wins() -> None:
    # Same id as a built-in, but pointing at a different hub/exchange.
    override = CommodityConfig("TTF", "USD/MMBtu", Hub("TTF", "CUSTOM_ICE", "USD/MMBtu"))
    resolved = resolve_commodity("TTF", {"TTF": override})
    assert resolved is override
    assert resolved != BUILT_IN_COMMODITIES["TTF"]


def test_merge_commodities_precedence_and_new_entry() -> None:
    override = CommodityConfig("EUA", "USD/tCO2", Hub("EUA", "CUSTOM", "USD/tCO2"))
    extra = {
        "EUA": override,
        "NEW_HUB": CommodityConfig("NEW_HUB", "EUR/MWh", Hub("NEW_HUB", "X", "EUR/MWh")),
    }
    merged = merge_commodities(extra)
    assert merged["EUA"] is override  # caller wins
    assert merged["NEW_HUB"] is extra["NEW_HUB"]  # new id added
    assert merged["TTF"] is BUILT_IN_COMMODITIES["TTF"]  # untouched built-in retained


def test_merge_commodities_none_returns_all_builtins() -> None:
    assert merge_commodities(None) == BUILT_IN_COMMODITIES
    assert merge_commodities() == BUILT_IN_COMMODITIES


def test_unknown_id_raises_validation_error_listing_available() -> None:
    with pytest.raises(ValidationError) as excinfo:
        resolve_commodity("NOT_A_HUB")
    message = str(excinfo.value)
    assert "NOT_A_HUB" in message
    # Every available id is enumerated in the message.
    for commodity_id in BUILT_IN_COMMODITIES:
        assert commodity_id in message


def test_unknown_id_message_includes_caller_supplied_ids() -> None:
    extra = {"CUSTOM": CommodityConfig("CUSTOM", "EUR/MWh", Hub("CUSTOM", "X", "EUR/MWh"))}
    with pytest.raises(ValidationError) as excinfo:
        resolve_commodity("MISSING", extra)
    assert "CUSTOM" in str(excinfo.value)


def test_resolve_does_not_mutate_builtins_or_caller_dict() -> None:
    before_builtins = dict(BUILT_IN_COMMODITIES)
    extra = {"CUSTOM": CommodityConfig("CUSTOM", "EUR/MWh", Hub("CUSTOM", "X", "EUR/MWh"))}
    extra_before = dict(extra)

    resolve_commodity("TTF", extra)
    resolve_commodity("CUSTOM", extra)

    assert before_builtins == BUILT_IN_COMMODITIES
    assert "CUSTOM" not in BUILT_IN_COMMODITIES
    assert extra == extra_before


def test_merge_result_is_independent_of_builtins() -> None:
    custom = CommodityConfig("CUSTOM", "EUR/MWh", Hub("CUSTOM", "X", "EUR/MWh"))
    merged = merge_commodities({"CUSTOM": custom})
    merged.pop("TTF")  # mutating the returned dict must not affect the constant
    assert "TTF" in BUILT_IN_COMMODITIES
    assert "CUSTOM" not in BUILT_IN_COMMODITIES


def test_value_objects_are_frozen() -> None:
    hub = Hub("H", "E", "EUR/MWh")
    with pytest.raises(AttributeError):
        hub.hub_id = "other"  # type: ignore[misc]
    cfg = CommodityConfig("C", "EUR/MWh", hub)
    with pytest.raises(AttributeError):
        cfg.price_unit = "other"  # type: ignore[misc]


def test_registry_invariant_every_builtin_parses_and_config_matches_hub() -> None:
    """Property 78 (unit-level check): every built-in config/hub parses to a valid
    PriceUnit, and a config's price_unit agrees with its hub's price_unit."""
    from quantvolt.models.units import PriceUnit

    for config in BUILT_IN_COMMODITIES.values():
        PriceUnit.parse(config.price_unit)
        PriceUnit.parse(config.hub.price_unit)
        assert config.price_unit == config.hub.price_unit


def test_no_builtin_entry_uses_mbtu() -> None:
    # Compare the denominator exactly: "MBtu" is a substring of the valid "MMBtu",
    # so a substring check would false-fail if an MMBtu built-in were ever added.
    for config in BUILT_IN_COMMODITIES.values():
        assert config.price_unit.split("/")[1] != "MBtu"
        assert config.hub.price_unit.split("/")[1] != "MBtu"


def test_hub_construction_rejects_invalid_price_unit() -> None:
    with pytest.raises(ValidationError):
        Hub("H", "E", "EUR/MBtu")


def test_commodity_config_construction_rejects_invalid_price_unit() -> None:
    with pytest.raises(ValidationError):
        CommodityConfig("C", "EUR/MBtu", Hub("H", "E", "EUR/MWh"))
