"""Unit tests for the stress-scenario catalogue (Task 39, Req 9.4 / 9.7)."""

from __future__ import annotations

import pytest

from quantvolt.exceptions import EnergyQuantError, ScenarioNotFoundError, ValidationError
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.risk.scenarios import (
    BUILT_IN_SCENARIOS,
    ScenarioCatalogue,
    ScenarioShock,
    carbon_price_shock,
    cold_snap_winter,
    gas_crisis,
    mild_winter_demand_slump,
)

EXPECTED_BUILT_IN_NAMES = {
    "Carbon Price Shock",
    "Cold Snap Winter",
    "European Gas Crisis 2022",
    "Mild Winter Demand Slump",
}


# --- built-in registry -------------------------------------------------------


def test_registry_has_exactly_the_expected_built_ins() -> None:
    assert set(BUILT_IN_SCENARIOS) == EXPECTED_BUILT_IN_NAMES


def test_gas_crisis_lookup_returns_expected_shock() -> None:
    scenario = ScenarioCatalogue().get("European Gas Crisis 2022")
    assert scenario == ScenarioShock(
        name="European Gas Crisis 2022",
        shocks={
            ("TTF", None): 3.0,
            ("NBP", None): 2.5,
            ("EEX_PHELIX_DE", None): 2.0,
            ("EUA", None): 0.3,
        },
    )


def test_cold_snap_shocks_gas_harder_than_power() -> None:
    scenario = ScenarioCatalogue().get("Cold Snap Winter")
    assert scenario.shocks[("TTF", None)] == 1.0
    assert scenario.shocks[("NBP", None)] == 1.0
    assert scenario.shocks[("EEX_PHELIX_DE", None)] == 0.8
    assert scenario.shocks[("EPEX_NL", None)] == 0.8


def test_mild_winter_slump_is_a_negative_relative_shock() -> None:
    scenario = ScenarioCatalogue().get("Mild Winter Demand Slump")
    assert scenario.shocks[("TTF", None)] == -0.4
    assert scenario.shocks[("EPEX_DE", None)] == -0.3


def test_carbon_shock_doubles_eua_and_passes_through_to_power() -> None:
    scenario = ScenarioCatalogue().get("Carbon Price Shock")
    assert scenario.shocks[("EUA", None)] == 1.0
    assert scenario.shocks[("EEX_PHELIX_AT", None)] == 0.25


def test_all_built_in_macro_scenarios_are_commodity_wide() -> None:
    for scenario in BUILT_IN_SCENARIOS.values():
        assert all(period is None for _, period in scenario.shocks)


def test_lookup_without_extras_returns_registry_entry() -> None:
    assert ScenarioCatalogue().get("Cold Snap Winter") is BUILT_IN_SCENARIOS["Cold Snap Winter"]


def test_names_returns_all_built_ins_sorted() -> None:
    names = ScenarioCatalogue().names()
    assert names == sorted(EXPECTED_BUILT_IN_NAMES)
    assert names == sorted(names)


# --- unknown-name error (Req 9.7) --------------------------------------------


def test_unknown_name_raises_scenario_not_found_listing_all_available() -> None:
    with pytest.raises(ScenarioNotFoundError) as excinfo:
        ScenarioCatalogue().get("Beast from the East")
    message = str(excinfo.value)
    assert "Beast from the East" in message
    for name in EXPECTED_BUILT_IN_NAMES:
        assert name in message


def test_unknown_name_error_is_an_energy_quant_error() -> None:
    with pytest.raises(EnergyQuantError):
        ScenarioCatalogue().get("nope")


def test_unknown_name_message_includes_caller_supplied_names() -> None:
    extra = {"Dunkelflaute": ScenarioShock("Dunkelflaute", {("EEX_PHELIX_DE", None): 1.5})}
    with pytest.raises(ScenarioNotFoundError) as excinfo:
        ScenarioCatalogue(extra).get("MISSING")
    assert "Dunkelflaute" in str(excinfo.value)


# --- caller extension seam ----------------------------------------------------


def test_extension_adds_a_brand_new_name() -> None:
    custom = ScenarioShock("Dunkelflaute", {("EEX_PHELIX_DE", None): 1.5})
    catalogue = ScenarioCatalogue({"Dunkelflaute": custom})
    assert catalogue.get("Dunkelflaute") is custom
    assert "Dunkelflaute" in catalogue.names()


def test_caller_override_of_builtin_name_wins() -> None:
    override = ScenarioShock("Cold Snap Winter", {("TTF", None): 2.0})
    catalogue = ScenarioCatalogue({"Cold Snap Winter": override})
    assert catalogue.get("Cold Snap Winter") is override
    assert catalogue.get("Cold Snap Winter") != BUILT_IN_SCENARIOS["Cold Snap Winter"]


def test_construction_does_not_mutate_builtins_or_caller_dict() -> None:
    builtins_before = dict(BUILT_IN_SCENARIOS)
    extra = {
        "Cold Snap Winter": ScenarioShock("Cold Snap Winter", {("TTF", None): 2.0}),
        "Dunkelflaute": ScenarioShock("Dunkelflaute", {("EEX_PHELIX_DE", None): 1.5}),
    }
    extra_before = dict(extra)

    catalogue = ScenarioCatalogue(extra)
    catalogue.get("Dunkelflaute")

    assert builtins_before == BUILT_IN_SCENARIOS
    assert "Dunkelflaute" not in BUILT_IN_SCENARIOS
    assert extra == extra_before


def test_catalogue_is_independent_of_later_caller_dict_mutation() -> None:
    extra = {"Dunkelflaute": ScenarioShock("Dunkelflaute", {("EEX_PHELIX_DE", None): 1.5})}
    catalogue = ScenarioCatalogue(extra)
    extra["Late Addition"] = ScenarioShock("Late Addition", {("TTF", None): 0.1})
    with pytest.raises(ScenarioNotFoundError):
        catalogue.get("Late Addition")


def test_default_catalogue_matches_builtins() -> None:
    assert ScenarioCatalogue().names() == ScenarioCatalogue(None).names()
    assert ScenarioCatalogue().names() == sorted(BUILT_IN_SCENARIOS)


# --- ScenarioShock value object ------------------------------------------------


def test_period_specific_shock_key_is_supported() -> None:
    period = DeliveryPeriod(2026, 1)
    shock = ScenarioShock("Jan-26 TTF squeeze", {("TTF", period): 0.5, ("TTF", None): 0.1})
    assert shock.shocks[("TTF", period)] == 0.5


def test_empty_name_is_rejected() -> None:
    with pytest.raises(ValidationError, match="name"):
        ScenarioShock("", {("TTF", None): 1.0})


def test_empty_shocks_is_rejected() -> None:
    with pytest.raises(ValidationError, match="shocks"):
        ScenarioShock("Empty", {})


def test_scenario_shock_is_frozen() -> None:
    shock = ScenarioShock("Frozen", {("TTF", None): 1.0})
    with pytest.raises(AttributeError):
        shock.name = "other"  # type: ignore[misc]
    with pytest.raises(AttributeError):
        shock.shocks = {}  # type: ignore[misc]


# --- factory functions (task: expose hardcoded shock magnitudes) -------------


def test_gas_crisis_default_matches_registry_entry() -> None:
    assert gas_crisis() == BUILT_IN_SCENARIOS["European Gas Crisis 2022"]


def test_gas_crisis_override_changes_the_shocks() -> None:
    custom = gas_crisis(ttf_shock=1.0, nbp_shock=0.5, german_power_shock=0.2, eua_shock=0.1)
    assert custom.shocks[("TTF", None)] == 1.0
    assert custom.shocks[("NBP", None)] == 0.5
    assert custom.shocks[("EEX_PHELIX_DE", None)] == 0.2
    assert custom.shocks[("EUA", None)] == 0.1
    assert custom != BUILT_IN_SCENARIOS["European Gas Crisis 2022"]


def test_cold_snap_winter_default_matches_registry_entry() -> None:
    assert cold_snap_winter() == BUILT_IN_SCENARIOS["Cold Snap Winter"]


def test_cold_snap_winter_override_changes_the_shocks() -> None:
    custom = cold_snap_winter(gas_shock=2.0, power_shock=1.5)
    assert custom.shocks[("TTF", None)] == 2.0
    assert custom.shocks[("EEX_PHELIX_DE", None)] == 1.5
    assert custom != BUILT_IN_SCENARIOS["Cold Snap Winter"]


def test_mild_winter_demand_slump_default_matches_registry_entry() -> None:
    assert mild_winter_demand_slump() == BUILT_IN_SCENARIOS["Mild Winter Demand Slump"]


def test_mild_winter_demand_slump_override_changes_the_shocks() -> None:
    custom = mild_winter_demand_slump(gas_shock=-0.8, power_shock=-0.6)
    assert custom.shocks[("TTF", None)] == -0.8
    assert custom.shocks[("EEX_PHELIX_DE", None)] == -0.6
    assert custom != BUILT_IN_SCENARIOS["Mild Winter Demand Slump"]


def test_carbon_price_shock_default_matches_registry_entry() -> None:
    assert carbon_price_shock() == BUILT_IN_SCENARIOS["Carbon Price Shock"]


def test_carbon_price_shock_override_changes_the_shocks() -> None:
    custom = carbon_price_shock(eua_shock=2.0, power_shock=0.5)
    assert custom.shocks[("EUA", None)] == 2.0
    assert custom.shocks[("EEX_PHELIX_AT", None)] == 0.5
    assert custom != BUILT_IN_SCENARIOS["Carbon Price Shock"]


def test_registry_is_built_from_factory_defaults() -> None:
    assert {
        "European Gas Crisis 2022": gas_crisis(),
        "Cold Snap Winter": cold_snap_winter(),
        "Mild Winter Demand Slump": mild_winter_demand_slump(),
        "Carbon Price Shock": carbon_price_shock(),
    } == BUILT_IN_SCENARIOS
