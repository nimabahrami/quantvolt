"""Unit tests for models/instruments.py (Task 8): the instrument hierarchy.

Covers construction with defaults and overrides, correct default settlement/granularity,
boundary validation (notional and heat_rate must be > 0; cost/emissions must be >= 0),
acceptance of negative prices/rates, enum values, and immutability.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.instruments import (
    CachedAssetValuation,
    CapFloorStripContract,
    CapFloorType,
    ForwardContract,
    FuturesContract,
    InstrumentPriceRecord,
    OptionSide,
    OptionType,
    PlantConfig,
    RiskType,
    SettlementType,
    SpreadOptionContract,
    SwapContract,
    TollingAgreement,
    ValuationSource,
    VanillaOptionContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule, Granularity

_HUB = Hub("TTF", "ICE_ENDEX", "EUR/MWh")
_COMMODITY = CommodityConfig("TTF", "EUR/MWh", _HUB)
_PERIOD = DeliveryPeriod(2024, 6)
_SCHEDULE = DeliverySchedule(
    (DeliveryPeriod(2024, 1), DeliveryPeriod(2024, 2), DeliveryPeriod(2024, 3))
)


class TestSettlementType:
    def test_values(self) -> None:
        assert SettlementType.PHYSICAL == "physical"
        assert SettlementType.FINANCIAL == "financial"

    def test_members(self) -> None:
        assert {s.value for s in SettlementType} == {"physical", "financial"}


class TestRiskType:
    def test_values(self) -> None:
        assert RiskType.EXECUTION == "execution"
        assert RiskType.BASIS == "basis"
        assert RiskType.LIQUIDITY == "liquidity"
        assert RiskType.CREDIT == "credit"
        assert RiskType.STORAGE == "storage"
        assert RiskType.TRANSMISSION == "transmission"

    def test_members(self) -> None:
        assert {r.value for r in RiskType} == {
            "execution",
            "basis",
            "liquidity",
            "credit",
            "storage",
            "transmission",
        }


class TestInstrumentPriceRecord:
    def test_construction(self) -> None:
        record = InstrumentPriceRecord(
            instrument_id="TTF_2024_06",
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            price=25.5,
        )
        assert record.instrument_id == "TTF_2024_06"
        assert record.commodity is _COMMODITY
        assert record.delivery_period == _PERIOD
        assert record.price == 25.5

    def test_negative_price_accepted(self) -> None:
        record = InstrumentPriceRecord("neg", _COMMODITY, _PERIOD, price=-40.0)
        assert record.price == -40.0


class TestFuturesContract:
    def test_defaults(self) -> None:
        contract = FuturesContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            contract_price=30.0,
            notional=1000.0,
        )
        assert contract.granularity is Granularity.MONTHLY
        assert contract.settlement_type is SettlementType.FINANCIAL

    def test_overrides(self) -> None:
        contract = FuturesContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            contract_price=30.0,
            notional=1000.0,
            granularity=Granularity.QUARTERLY,
            settlement_type=SettlementType.PHYSICAL,
        )
        assert contract.granularity is Granularity.QUARTERLY
        assert contract.settlement_type is SettlementType.PHYSICAL

    def test_negative_contract_price_accepted(self) -> None:
        contract = FuturesContract(_COMMODITY, _PERIOD, contract_price=-5.0, notional=1.0)
        assert contract.contract_price == -5.0

    @pytest.mark.parametrize("notional", [0.0, -1.0, -1000.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            FuturesContract(_COMMODITY, _PERIOD, contract_price=30.0, notional=notional)


class TestForwardContract:
    def test_defaults(self) -> None:
        contract = ForwardContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            contract_price=30.0,
            notional=1000.0,
        )
        assert contract.granularity is Granularity.MONTHLY
        assert contract.settlement_type is SettlementType.PHYSICAL
        assert contract.counterparty is None

    def test_overrides(self) -> None:
        contract = ForwardContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            contract_price=30.0,
            notional=1000.0,
            granularity=Granularity.YEARLY,
            settlement_type=SettlementType.FINANCIAL,
            counterparty="ACME_ENERGY",
        )
        assert contract.granularity is Granularity.YEARLY
        assert contract.settlement_type is SettlementType.FINANCIAL
        assert contract.counterparty == "ACME_ENERGY"

    def test_negative_contract_price_accepted(self) -> None:
        contract = ForwardContract(_COMMODITY, _PERIOD, contract_price=-12.0, notional=1.0)
        assert contract.contract_price == -12.0

    @pytest.mark.parametrize("notional", [0.0, -1.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            ForwardContract(_COMMODITY, _PERIOD, contract_price=30.0, notional=notional)


class TestSwapContract:
    def test_defaults_and_accepts_schedule(self) -> None:
        swap = SwapContract(
            commodity=_COMMODITY,
            fixed_rate=25.0,
            floating_index="TTF_DA",
            notional=1000.0,
            schedule=_SCHEDULE,
        )
        assert swap.granularity is Granularity.MONTHLY
        assert swap.schedule is _SCHEDULE
        assert swap.floating_index == "TTF_DA"

    def test_override_granularity(self) -> None:
        swap = SwapContract(
            commodity=_COMMODITY,
            fixed_rate=25.0,
            floating_index="EPEX_SPOT_DE",
            notional=1000.0,
            schedule=_SCHEDULE,
            granularity=Granularity.DAILY,
        )
        assert swap.granularity is Granularity.DAILY

    def test_negative_fixed_rate_accepted(self) -> None:
        swap = SwapContract(_COMMODITY, -3.5, "TTF_DA", notional=1.0, schedule=_SCHEDULE)
        assert swap.fixed_rate == -3.5

    @pytest.mark.parametrize("notional", [0.0, -50.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            SwapContract(_COMMODITY, 25.0, "TTF_DA", notional=notional, schedule=_SCHEDULE)


class TestPlantConfig:
    def test_construction(self) -> None:
        plant = PlantConfig(
            heat_rate=2.0,
            variable_om_cost=3.5,
            emissions_intensity=0.2,
            fuel_type="gas",
        )
        assert plant.heat_rate == 2.0
        assert plant.variable_om_cost == 3.5
        assert plant.emissions_intensity == 0.2
        assert plant.fuel_type == "gas"

    def test_zero_cost_and_emissions_accepted(self) -> None:
        plant = PlantConfig(
            heat_rate=2.0,
            variable_om_cost=0.0,
            emissions_intensity=0.0,
            fuel_type="coal",
        )
        assert plant.variable_om_cost == 0.0
        assert plant.emissions_intensity == 0.0

    @pytest.mark.parametrize("heat_rate", [0.0, -1.0])
    def test_non_positive_heat_rate_rejected(self, heat_rate: float) -> None:
        with pytest.raises(ValidationError, match="heat_rate"):
            PlantConfig(heat_rate, 3.5, 0.2, "gas")

    def test_negative_variable_om_cost_rejected(self) -> None:
        with pytest.raises(ValidationError, match="variable_om_cost"):
            PlantConfig(2.0, -0.1, 0.2, "gas")

    def test_negative_emissions_intensity_rejected(self) -> None:
        with pytest.raises(ValidationError, match="emissions_intensity"):
            PlantConfig(2.0, 3.5, -0.2, "gas")


class TestImmutability:
    def test_futures_is_frozen(self) -> None:
        contract = FuturesContract(_COMMODITY, _PERIOD, 30.0, 1000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.notional = 2000.0  # type: ignore[misc]

    def test_forward_is_frozen(self) -> None:
        contract = ForwardContract(_COMMODITY, _PERIOD, 30.0, 1000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.counterparty = "X"  # type: ignore[misc]

    def test_swap_is_frozen(self) -> None:
        swap = SwapContract(_COMMODITY, 25.0, "TTF_DA", 1000.0, _SCHEDULE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            swap.fixed_rate = 26.0  # type: ignore[misc]

    def test_plant_is_frozen(self) -> None:
        plant = PlantConfig(2.0, 3.5, 0.2, "gas")
        with pytest.raises(dataclasses.FrozenInstanceError):
            plant.heat_rate = 3.0  # type: ignore[misc]

    def test_price_record_is_frozen(self) -> None:
        record = InstrumentPriceRecord("id", _COMMODITY, _PERIOD, 10.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            record.price = 11.0  # type: ignore[misc]


# --- portfolio-native-pricers spec: OptionType/OptionSide, VanillaOptionContract,
# SpreadOptionContract, TollingAgreement (Reqs 4, 5, 14) --------------------------------


class TestOptionType:
    def test_values(self) -> None:
        assert OptionType.CALL == "call"
        assert OptionType.PUT == "put"

    def test_members(self) -> None:
        assert {t.value for t in OptionType} == {"call", "put"}


class TestOptionSide:
    def test_values(self) -> None:
        assert OptionSide.LONG == "long"
        assert OptionSide.SHORT == "short"

    def test_members(self) -> None:
        assert {s.value for s in OptionSide} == {"long", "short"}


class TestVanillaOptionContract:
    def test_defaults(self) -> None:
        contract = VanillaOptionContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            option_type=OptionType.CALL,
            strike=40.0,
            notional=1000.0,
        )
        assert contract.side is OptionSide.LONG
        assert contract.expiry is None

    def test_overrides(self) -> None:
        expiry = DeliveryPeriod(2024, 5).last_day
        contract = VanillaOptionContract(
            commodity=_COMMODITY,
            delivery_period=_PERIOD,
            option_type=OptionType.PUT,
            strike=40.0,
            notional=1000.0,
            side=OptionSide.SHORT,
            expiry=expiry,
        )
        assert contract.option_type is OptionType.PUT
        assert contract.side is OptionSide.SHORT
        assert contract.expiry == expiry

    @pytest.mark.parametrize("strike", [0.0, -1.0, -40.0])
    def test_non_positive_strike_rejected(self, strike: float) -> None:
        with pytest.raises(ValidationError, match="strike"):
            VanillaOptionContract(_COMMODITY, _PERIOD, OptionType.CALL, strike, 1000.0)

    @pytest.mark.parametrize("notional", [0.0, -1.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            VanillaOptionContract(_COMMODITY, _PERIOD, OptionType.CALL, 40.0, notional)

    def test_is_frozen(self) -> None:
        contract = VanillaOptionContract(_COMMODITY, _PERIOD, OptionType.CALL, 40.0, 1000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.strike = 50.0  # type: ignore[misc]


class TestSpreadOptionContract:
    def test_defaults(self) -> None:
        contract = SpreadOptionContract(
            commodity_1="EEX_PHELIX_DE",
            commodity_2="TTF",
            delivery_period=_PERIOD,
            strike=5.0,
            notional=1000.0,
        )
        assert contract.leg2_weight == 1.0
        assert contract.side is OptionSide.LONG
        assert contract.expiry is None

    def test_zero_strike_accepted_margrabe_selector(self) -> None:
        contract = SpreadOptionContract("EEX_PHELIX_DE", "TTF", _PERIOD, 0.0, 1000.0)
        assert contract.strike == 0.0

    @pytest.mark.parametrize("strike", [-1.0, -40.0])
    def test_negative_strike_rejected(self, strike: float) -> None:
        with pytest.raises(ValidationError, match="strike"):
            SpreadOptionContract("EEX_PHELIX_DE", "TTF", _PERIOD, strike, 1000.0)

    @pytest.mark.parametrize("notional", [0.0, -1.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            SpreadOptionContract("EEX_PHELIX_DE", "TTF", _PERIOD, 5.0, notional)

    @pytest.mark.parametrize("leg2_weight", [0.0, -2.0])
    def test_non_positive_leg2_weight_rejected(self, leg2_weight: float) -> None:
        with pytest.raises(ValidationError, match="leg2_weight"):
            SpreadOptionContract(
                "EEX_PHELIX_DE", "TTF", _PERIOD, 5.0, 1000.0, leg2_weight=leg2_weight
            )

    def test_is_frozen(self) -> None:
        contract = SpreadOptionContract("EEX_PHELIX_DE", "TTF", _PERIOD, 5.0, 1000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            contract.strike = 10.0  # type: ignore[misc]


_PLANT = PlantConfig(heat_rate=2.0, variable_om_cost=3.0, emissions_intensity=0.2, fuel_type="gas")


class TestTollingAgreement:
    def test_defaults(self) -> None:
        agreement = TollingAgreement(
            plant=_PLANT,
            power_commodity_id="EEX_PHELIX_DE",
            fuel_commodity_id="TTF",
            eua_commodity_id="EUA",
            schedule=_SCHEDULE,
        )
        assert agreement.capacity == 1.0
        assert agreement.settlement_lag_days == 0

    def test_overrides(self) -> None:
        agreement = TollingAgreement(
            plant=_PLANT,
            power_commodity_id="EEX_PHELIX_DE",
            fuel_commodity_id="TTF",
            eua_commodity_id="EUA",
            schedule=_SCHEDULE,
            capacity=50.0,
            settlement_lag_days=2,
        )
        assert agreement.capacity == 50.0
        assert agreement.settlement_lag_days == 2

    @pytest.mark.parametrize("capacity", [0.0, -1.0])
    def test_non_positive_capacity_rejected(self, capacity: float) -> None:
        with pytest.raises(ValidationError, match="capacity"):
            TollingAgreement(_PLANT, "EEX_PHELIX_DE", "TTF", "EUA", _SCHEDULE, capacity=capacity)

    def test_negative_settlement_lag_days_rejected(self) -> None:
        with pytest.raises(ValidationError, match="settlement_lag_days"):
            TollingAgreement(
                _PLANT, "EEX_PHELIX_DE", "TTF", "EUA", _SCHEDULE, settlement_lag_days=-1
            )

    def test_is_frozen(self) -> None:
        agreement = TollingAgreement(_PLANT, "EEX_PHELIX_DE", "TTF", "EUA", _SCHEDULE)
        with pytest.raises(dataclasses.FrozenInstanceError):
            agreement.capacity = 10.0  # type: ignore[misc]


class TestValuationSource:
    """DEFERRED-roadmap extension (portfolio-native-pricers Req 19): a third value,
    ``SIMULATED``, alongside the two base-spec values ``FORWARD``/``PROJECTED``
    (see ``tests/unit/test_long_dated.py::TestValuationSource`` for those two)."""

    def test_simulated_value(self) -> None:
        assert ValuationSource.SIMULATED == "simulated"

    def test_three_values(self) -> None:
        assert {s.value for s in ValuationSource} == {"forward", "projected", "simulated"}


class TestCachedAssetValuation:
    def test_construction_and_defaults(self) -> None:
        wrapper = CachedAssetValuation(
            asset_id="plant-1",
            npv=1_000.0,
            delta={("EEX_PHELIX_DE", _PERIOD): 25.0},
            valuation_date=date(2026, 1, 1),
            source=ValuationSource.SIMULATED,
        )
        assert wrapper.asset_id == "plant-1"
        assert wrapper.npv == 1_000.0
        assert wrapper.delta == {("EEX_PHELIX_DE", _PERIOD): 25.0}
        assert wrapper.standard_error is None

    def test_standard_error_override(self) -> None:
        wrapper = CachedAssetValuation(
            "plant-1", 1_000.0, {}, date(2026, 1, 1), ValuationSource.SIMULATED, standard_error=12.5
        )
        assert wrapper.standard_error == 12.5

    def test_empty_asset_id_rejected(self) -> None:
        with pytest.raises(ValidationError, match="asset_id"):
            CachedAssetValuation("", 1_000.0, {}, date(2026, 1, 1), ValuationSource.SIMULATED)

    @pytest.mark.parametrize("npv", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_npv_rejected(self, npv: float) -> None:
        with pytest.raises(ValidationError, match="npv"):
            CachedAssetValuation("plant-1", npv, {}, date(2026, 1, 1), ValuationSource.SIMULATED)

    @pytest.mark.parametrize("standard_error", [-1.0, float("nan"), float("inf")])
    def test_invalid_standard_error_rejected(self, standard_error: float) -> None:
        with pytest.raises(ValidationError, match="standard_error"):
            CachedAssetValuation(
                "plant-1",
                1_000.0,
                {},
                date(2026, 1, 1),
                ValuationSource.SIMULATED,
                standard_error=standard_error,
            )

    def test_delta_is_defensively_copied(self) -> None:
        source_delta = {("EEX_PHELIX_DE", _PERIOD): 25.0}
        wrapper = CachedAssetValuation(
            "plant-1", 1_000.0, source_delta, date(2026, 1, 1), ValuationSource.SIMULATED
        )
        source_delta[("EEX_PHELIX_DE", _PERIOD)] = 999.0
        assert wrapper.delta == {("EEX_PHELIX_DE", _PERIOD): 25.0}

    def test_is_frozen(self) -> None:
        wrapper = CachedAssetValuation(
            "plant-1", 1_000.0, {}, date(2026, 1, 1), ValuationSource.SIMULATED
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            wrapper.npv = 0.0  # type: ignore[misc]


class TestCapFloorType:
    def test_values(self) -> None:
        assert CapFloorType.CAP == "cap"
        assert CapFloorType.FLOOR == "floor"


class TestCapFloorStripContract:
    def test_defaults(self) -> None:
        strip = CapFloorStripContract(
            commodity=_COMMODITY,
            schedule=_SCHEDULE,
            cap_floor_type=CapFloorType.CAP,
            strike=40.0,
            notional=1_000.0,
        )
        assert strip.side == OptionSide.LONG

    def test_side_override(self) -> None:
        strip = CapFloorStripContract(
            _COMMODITY, _SCHEDULE, CapFloorType.FLOOR, 40.0, 1_000.0, side=OptionSide.SHORT
        )
        assert strip.side == OptionSide.SHORT

    @pytest.mark.parametrize("strike", [0.0, -5.0])
    def test_non_positive_strike_rejected(self, strike: float) -> None:
        with pytest.raises(ValidationError, match="strike"):
            CapFloorStripContract(_COMMODITY, _SCHEDULE, CapFloorType.CAP, strike, 1_000.0)

    @pytest.mark.parametrize("notional", [0.0, -1.0])
    def test_non_positive_notional_rejected(self, notional: float) -> None:
        with pytest.raises(ValidationError, match="notional"):
            CapFloorStripContract(_COMMODITY, _SCHEDULE, CapFloorType.CAP, 40.0, notional)

    def test_is_frozen(self) -> None:
        strip = CapFloorStripContract(_COMMODITY, _SCHEDULE, CapFloorType.CAP, 40.0, 1_000.0)
        with pytest.raises(dataclasses.FrozenInstanceError):
            strip.strike = 10.0  # type: ignore[misc]
