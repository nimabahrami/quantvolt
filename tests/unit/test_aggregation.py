"""Unit tests for risk/aggregation.py (Task 40, Req 9.3, Property 22): delta aggregation.

Covers cell-by-cell aggregation correctness (each cell equals the hand-computed sum of
per-position deltas), the dense union grid with zeros where a position has no exposure,
sorted rows/columns, the empty-input matrix, ``delta_at`` lookups including absent
combinations, shape self-validation, and input immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.models.commodity import CommodityConfig, Hub
from quantvolt.models.instruments import FuturesContract
from quantvolt.models.schedule import DeliveryPeriod
from quantvolt.portfolio.model import Position, PricedPosition
from quantvolt.risk.aggregation import DeltaMatrix, aggregate_delta
from quantvolt.testing import assert_input_unchanged

_TTF = CommodityConfig("TTF", "EUR/MBtu", Hub("TTF", "ICE_ENDEX", "EUR/MBtu"))
_JAN = DeliveryPeriod(2026, 1)
_FEB = DeliveryPeriod(2026, 2)
_MAR = DeliveryPeriod(2026, 3)
_POSITION = Position(FuturesContract(_TTF, _JAN, contract_price=30.0, notional=100.0))


def _priced(delta: dict[tuple[str, DeliveryPeriod], float]) -> PricedPosition:
    """A PricedPosition around a fixed instrument; only ``delta`` matters for aggregation."""
    return PricedPosition(position=_POSITION, npv=0.0, delta=delta)


class TestAggregateDelta:
    def test_property_22_each_cell_is_sum_of_position_deltas(self) -> None:
        positions = [
            _priced({("TTF", _JAN): 10.0, ("TTF", _FEB): 5.0}),
            _priced({("TTF", _JAN): -4.0, ("EEX_PHELIX_DE", _JAN): 2.5}),
            _priced({("TTF", _FEB): 1.5}),
        ]
        matrix = aggregate_delta(positions)
        assert matrix.delta_at("TTF", _JAN) == 10.0 + -4.0
        assert matrix.delta_at("TTF", _FEB) == 5.0 + 1.5
        assert matrix.delta_at("EEX_PHELIX_DE", _JAN) == 2.5
        assert matrix.delta_at("EEX_PHELIX_DE", _FEB) == 0.0  # dense grid: absent cell is 0.0

    def test_union_grid_pads_absent_combinations_with_zero(self) -> None:
        ttf_only = _priced({("TTF", _JAN): 10.0})
        eex_only = _priced({("EEX_PHELIX_DE", _FEB): 7.0})
        matrix = aggregate_delta([ttf_only, eex_only])
        assert matrix.commodities == ("EEX_PHELIX_DE", "TTF")
        assert matrix.periods == (_JAN, _FEB)
        assert matrix.values == ((0.0, 7.0), (10.0, 0.0))

    def test_rows_and_columns_are_sorted(self) -> None:
        positions = [
            _priced({("TTF", _MAR): 1.0}),
            _priced({("NBP", _JAN): 2.0}),
            _priced({("EEX_PHELIX_DE", _FEB): 3.0}),
        ]
        matrix = aggregate_delta(positions)
        assert matrix.commodities == ("EEX_PHELIX_DE", "NBP", "TTF")  # lexicographic rows
        assert matrix.periods == (_JAN, _FEB, _MAR)  # chronological columns

    def test_empty_positions_list_yields_empty_matrix(self) -> None:
        matrix = aggregate_delta([])
        assert matrix.commodities == ()
        assert matrix.periods == ()
        assert matrix.values == ()

    def test_positions_with_empty_delta_contribute_nothing(self) -> None:
        real = _priced({("TTF", _JAN): 10.0})
        with_empty = aggregate_delta([_priced({}), real, _priced({})])
        assert with_empty == aggregate_delta([real])

    def test_only_empty_deltas_yield_empty_matrix(self) -> None:
        matrix = aggregate_delta([_priced({}), _priced({})])
        assert matrix == DeltaMatrix(commodities=(), periods=(), values=())

    def test_inputs_not_mutated(self) -> None:
        positions = [
            _priced({("TTF", _JAN): 10.0, ("TTF", _FEB): 5.0}),
            _priced({("EEX_PHELIX_DE", _JAN): -3.0}),
        ]
        matrix = assert_input_unchanged(aggregate_delta, positions)
        assert matrix.delta_at("TTF", _JAN) == 10.0


class TestDeltaMatrix:
    def _matrix(self) -> DeltaMatrix:
        return DeltaMatrix(
            commodities=("EEX_PHELIX_DE", "TTF"),
            periods=(_JAN, _FEB),
            values=((1.0, 2.0), (3.0, 4.0)),
        )

    def test_delta_at_present_cells(self) -> None:
        matrix = self._matrix()
        assert matrix.delta_at("EEX_PHELIX_DE", _JAN) == 1.0
        assert matrix.delta_at("EEX_PHELIX_DE", _FEB) == 2.0
        assert matrix.delta_at("TTF", _JAN) == 3.0
        assert matrix.delta_at("TTF", _FEB) == 4.0

    def test_delta_at_absent_commodity_is_zero(self) -> None:
        assert self._matrix().delta_at("NBP", _JAN) == 0.0

    def test_delta_at_absent_period_is_zero(self) -> None:
        assert self._matrix().delta_at("TTF", _MAR) == 0.0

    def test_row_count_must_match_commodities(self) -> None:
        with pytest.raises(ValidationError, match="row"):
            DeltaMatrix(commodities=("TTF",), periods=(_JAN,), values=())

    def test_column_count_must_match_periods(self) -> None:
        with pytest.raises(ValidationError, match="column"):
            DeltaMatrix(commodities=("TTF",), periods=(_JAN, _FEB), values=((1.0,),))

    def test_is_frozen(self) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            self._matrix().values = ()  # type: ignore[misc]
