"""Transmission cost (Task 42).

Base version: the caller supplies distance + tariff (the data they actually have); the library
computes the cost. No hub map, capacity, congestion model, or pipeline registry — those are caller
data the library does not provide. Because there is no registry, this is a plain function.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._validation import require_non_negative


@dataclass(frozen=True, slots=True)
class Pipeline:
    distance: float  # e.g. km — informational / for the caller's own tariff derivation
    tariff: float  # transmission cost per unit volume, e.g. EUR/MWh

    def __post_init__(self) -> None:
        require_non_negative("distance", self.distance)
        require_non_negative("tariff", self.tariff)


def transmission_cost(pipeline: Pipeline, volume: float) -> float:
    """Total transmission cost = tariff * volume (Property 38: deterministic, non-negative).

    Args:
        pipeline: The pipeline whose tariff applies (validated at construction).
        volume: Volume transported, in the tariff's volume unit (e.g. MWh).

    Returns:
        The total cost, ``pipeline.tariff * volume``. Non-negative by construction.

    Raises:
        ValidationError: If ``volume`` is negative.
    """
    require_non_negative("volume", volume)
    return pipeline.tariff * volume
