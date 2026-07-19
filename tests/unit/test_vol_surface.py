"""Unit tests for models/vol_surface.py (Task 7, Req 8.5).

Covers: VolatilityTenor sigma validation; Moneyness enum values; VolatilitySurface
ordering/duplicate/empty validation; sigma_at exact-hit lookup and MissingTenorError
miss; immutability of both value objects.
"""

from __future__ import annotations

import dataclasses

import pytest

from quantvolt.exceptions import MissingTenorError, ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.models.vol_surface import Moneyness, VolatilitySurface, VolatilityTenor

COMMODITY = CommodityConfig("TTF", "EUR/MWh", Hub("TTF", "ICE_ENDEX", "EUR/MWh"))


def make_surface() -> VolatilitySurface:
    return VolatilitySurface(
        commodity=COMMODITY,
        tenors=(
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.30),
            VolatilityTenor(DeliveryPeriod(2024, 2), 0.28),
            VolatilityTenor(DeliveryPeriod(2024, 6), 0.25),
        ),
    )


# --- Moneyness --------------------------------------------------------------


class TestMoneyness:
    def test_string_values(self) -> None:
        assert Moneyness.ATM == "atm"
        assert Moneyness.OTM == "otm"
        assert Moneyness.ITM == "itm"

    def test_members(self) -> None:
        assert {m.value for m in Moneyness} == {"atm", "otm", "itm"}


# --- VolatilityTenor validation ---------------------------------------------


class TestVolatilityTenor:
    def test_positive_sigma_accepted(self) -> None:
        tenor = VolatilityTenor(DeliveryPeriod(2024, 1), 0.30)
        assert tenor.sigma == 0.30
        assert tenor.period == DeliveryPeriod(2024, 1)

    @pytest.mark.parametrize("bad_sigma", [0.0, -0.01, -1.0])
    def test_non_positive_sigma_rejected(self, bad_sigma: float) -> None:
        with pytest.raises(ValidationError, match="sigma"):
            VolatilityTenor(DeliveryPeriod(2024, 1), bad_sigma)


# --- sigma_at lookup --------------------------------------------------------


class TestSigmaAt:
    @pytest.mark.parametrize(
        ("period", "expected"),
        [
            (DeliveryPeriod(2024, 1), 0.30),
            (DeliveryPeriod(2024, 2), 0.28),
            (DeliveryPeriod(2024, 6), 0.25),
        ],
    )
    def test_exact_hit_returns_stored_sigma(self, period: DeliveryPeriod, expected: float) -> None:
        assert make_surface().sigma_at(period) == expected

    def test_uncovered_period_within_range_raises(self) -> None:
        # 2024-03 lies between covered tenors but has no exact match (no interpolation).
        with pytest.raises(MissingTenorError, match="not covered"):
            make_surface().sigma_at(DeliveryPeriod(2024, 3))

    def test_period_before_first_raises(self) -> None:
        with pytest.raises(MissingTenorError, match="not covered"):
            make_surface().sigma_at(DeliveryPeriod(2023, 12))

    def test_period_after_last_raises(self) -> None:
        with pytest.raises(MissingTenorError, match="not covered"):
            make_surface().sigma_at(DeliveryPeriod(2024, 12))

    def test_error_names_period_and_covered_range(self) -> None:
        with pytest.raises(MissingTenorError) as excinfo:
            make_surface().sigma_at(DeliveryPeriod(2024, 3))
        message = str(excinfo.value)
        assert "month=3" in message  # the offending period
        assert "covered range" in message
        assert "month=1" in message  # first covered period
        assert "month=6" in message  # last covered period


# --- VolatilitySurface construction validation ------------------------------


class TestSurfaceValidation:
    def test_single_tenor_is_valid(self) -> None:
        surface = VolatilitySurface(
            commodity=COMMODITY, tenors=(VolatilityTenor(DeliveryPeriod(2024, 6), 0.25),)
        )
        assert surface.sigma_at(DeliveryPeriod(2024, 6)) == 0.25

    def test_valid_surface_spanning_year_boundary(self) -> None:
        tenors = (
            VolatilityTenor(DeliveryPeriod(2023, 11), 0.30),
            VolatilityTenor(DeliveryPeriod(2023, 12), 0.29),
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.28),
        )
        assert VolatilitySurface(commodity=COMMODITY, tenors=tenors).tenors == tenors

    def test_empty_tenors_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tenors"):
            VolatilitySurface(commodity=COMMODITY, tenors=())

    def test_out_of_order_tenors_rejected(self) -> None:
        tenors = (
            VolatilityTenor(DeliveryPeriod(2024, 3), 0.30),
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.28),
        )
        with pytest.raises(ValidationError, match="strictly increasing"):
            VolatilitySurface(commodity=COMMODITY, tenors=tenors)

    def test_out_of_order_across_years_rejected(self) -> None:
        tenors = (
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.30),
            VolatilityTenor(DeliveryPeriod(2023, 12), 0.28),
        )
        with pytest.raises(ValidationError, match="strictly increasing"):
            VolatilitySurface(commodity=COMMODITY, tenors=tenors)

    def test_duplicate_period_rejected(self) -> None:
        tenors = (
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.30),
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.31),
        )
        with pytest.raises(ValidationError, match="strictly increasing"):
            VolatilitySurface(commodity=COMMODITY, tenors=tenors)

    def test_offending_pair_index_reported(self) -> None:
        tenors = (
            VolatilityTenor(DeliveryPeriod(2024, 1), 0.30),
            VolatilityTenor(DeliveryPeriod(2024, 2), 0.29),
            VolatilityTenor(DeliveryPeriod(2024, 2), 0.28),  # duplicate -> index 1
        )
        with pytest.raises(ValidationError, match="index 1"):
            VolatilitySurface(commodity=COMMODITY, tenors=tenors)


# --- immutability -----------------------------------------------------------


class TestImmutability:
    def test_volatility_tenor_is_frozen(self) -> None:
        tenor = VolatilityTenor(DeliveryPeriod(2024, 1), 0.30)
        with pytest.raises(dataclasses.FrozenInstanceError):
            tenor.sigma = 0.5  # type: ignore[misc]

    def test_volatility_surface_is_frozen(self) -> None:
        surface = make_surface()
        with pytest.raises(dataclasses.FrozenInstanceError):
            surface.tenors = ()  # type: ignore[misc]
