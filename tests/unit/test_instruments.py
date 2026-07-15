"""Unit tests for models/instruments.py (Task 8): the instrument hierarchy.

Covers construction with defaults and overrides, correct default settlement/granularity,
boundary validation (notional and heat_rate must be > 0; cost/emissions must be >= 0),
acceptance of negative prices/rates, enum values, and immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.instruments import (
    ForwardContract,
    FuturesContract,
    InstrumentPriceRecord,
    PlantConfig,
    RiskType,
    SettlementType,
    SwapContract,
)
from quantvolt.models.schedule import DeliveryPeriod, DeliverySchedule, Granularity

_HUB = Hub("TTF", "ICE_ENDEX", "EUR/MBtu")
_COMMODITY = CommodityConfig("TTF", "EUR/MBtu", _HUB)
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
