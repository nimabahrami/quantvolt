"""Unit tests for transmission cost (Task 42, Property 38)."""

from __future__ import annotations

import pytest

from quantvolt.exceptions import ValidationError
from quantvolt.market.transmission import Pipeline, transmission_cost


class TestPipelineValidation:
    def test_valid_pipeline_constructs(self) -> None:
        pipeline = Pipeline(distance=250.0, tariff=1.75)
        assert pipeline.distance == 250.0
        assert pipeline.tariff == 1.75

    def test_zero_distance_and_tariff_allowed(self) -> None:
        pipeline = Pipeline(distance=0.0, tariff=0.0)
        assert pipeline.distance == 0.0
        assert pipeline.tariff == 0.0

    def test_negative_distance_rejected(self) -> None:
        with pytest.raises(ValidationError, match="distance"):
            Pipeline(distance=-1.0, tariff=1.0)

    def test_negative_tariff_rejected(self) -> None:
        with pytest.raises(ValidationError, match="tariff"):
            Pipeline(distance=100.0, tariff=-0.5)


class TestTransmissionCost:
    def test_known_value(self) -> None:
        pipeline = Pipeline(distance=100.0, tariff=1.5)
        assert transmission_cost(pipeline, 10.0) == pytest.approx(15.0)

    def test_another_known_value(self) -> None:
        pipeline = Pipeline(distance=42.0, tariff=0.25)
        assert transmission_cost(pipeline, 400.0) == pytest.approx(100.0)

    def test_zero_volume_costs_zero(self) -> None:
        pipeline = Pipeline(distance=100.0, tariff=2.0)
        assert transmission_cost(pipeline, 0.0) == 0.0

    def test_negative_volume_rejected(self) -> None:
        pipeline = Pipeline(distance=100.0, tariff=2.0)
        with pytest.raises(ValidationError, match="volume"):
            transmission_cost(pipeline, -5.0)

    def test_deterministic_same_inputs_same_result(self) -> None:
        pipeline = Pipeline(distance=333.0, tariff=1.234)
        first = transmission_cost(pipeline, 87.5)
        second = transmission_cost(pipeline, 87.5)
        assert first == second

    def test_cost_is_non_negative(self) -> None:
        # Property 38: with valid (non-negative) inputs the cost is never negative.
        for tariff in (0.0, 0.01, 3.5):
            for volume in (0.0, 1.0, 1_000.0):
                assert transmission_cost(Pipeline(10.0, tariff), volume) >= 0.0
