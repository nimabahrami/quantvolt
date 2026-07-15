"""Realized power-hedge terms at physical delivery-interval resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .._validation import (
    require_finite,
    require_non_empty,
    require_non_negative,
    require_positive,
)
from ..exceptions import ValidationError
from .interval import PowerDeliveryInterval


class PowerHedgeType(StrEnum):
    """Supported realized payoff shapes."""

    FIXED_PRICE_SWAP = "fixed_price_swap"
    CAP = "cap"
    FLOOR = "floor"
    COLLAR = "collar"


class PowerHedgePosition(StrEnum):
    """Payoff ownership; long swap means receive fixed and pay floating."""

    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class PowerHedgeContract:
    """Terms for one realized, financially settled power hedge.

    ``allocated_premium_per_mwh`` is an explicit allocation to each delivery
    interval, not an option valuation. Long positions pay it and short positions
    receive it. A long collar owns the floor and writes the cap.
    """

    hedge_id: str
    hedge_type: PowerHedgeType
    position: PowerHedgePosition
    start_utc: datetime
    end_utc: datetime
    volume_mwh: float
    strike_per_mwh: float
    upper_strike_per_mwh: float | None = None
    allocated_premium_per_mwh: float = 0.0

    def __post_init__(self) -> None:
        require_non_empty("hedge_id", self.hedge_id)
        if not isinstance(self.hedge_type, PowerHedgeType):
            raise ValidationError(f"invalid hedge_type: {self.hedge_type!r}")
        if not isinstance(self.position, PowerHedgePosition):
            raise ValidationError(f"invalid position: {self.position!r}")
        PowerDeliveryInterval(self.start_utc, self.end_utc)
        require_positive("volume_mwh", self.volume_mwh)
        require_finite("strike_per_mwh", self.strike_per_mwh)
        require_non_negative("allocated_premium_per_mwh", self.allocated_premium_per_mwh)
        if self.hedge_type is PowerHedgeType.COLLAR:
            if self.upper_strike_per_mwh is None:
                raise ValidationError("collar requires upper_strike_per_mwh")
            require_finite("upper_strike_per_mwh", self.upper_strike_per_mwh)
            if self.upper_strike_per_mwh <= self.strike_per_mwh:
                raise ValidationError("collar upper_strike_per_mwh must exceed strike_per_mwh")
        elif self.upper_strike_per_mwh is not None:
            raise ValidationError("upper_strike_per_mwh is valid only for a collar")

    def covers(self, interval: PowerDeliveryInterval) -> bool:
        """Whether the complete delivery interval is inside the hedge term."""
        return self.start_utc <= interval.start_utc and interval.end_utc <= self.end_utc
