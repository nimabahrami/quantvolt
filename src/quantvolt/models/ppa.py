"""Power-purchase agreement terms at timestamped delivery resolution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .._validation import require_finite, require_non_empty
from .interval import PowerDeliveryInterval


class PpaVolumeBasis(StrEnum):
    """How the contracted energy volume is determined for each interval."""

    BASELOAD = "baseload"
    SHAPED = "shaped"
    PAY_AS_PRODUCED = "pay_as_produced"


class PpaSettlementType(StrEnum):
    """Whether the PPA delivers energy or settles only its fixed-for-floating difference."""

    PHYSICAL = "physical"
    FINANCIAL_CFD = "financial_cfd"


@dataclass(frozen=True, slots=True)
class PpaContract:
    """Producer-side PPA commercial terms.

    The interval volume is deliberately supplied to settlement rather than
    embedded here: a shaped profile can contain tens of thousands of intervals,
    while a pay-as-produced profile is known only after metering.
    """

    contract_id: str
    bidding_zone: str
    fixed_price_per_mwh: float
    start_utc: datetime
    end_utc: datetime
    volume_basis: PpaVolumeBasis
    settlement_type: PpaSettlementType = PpaSettlementType.PHYSICAL
    counterparty: str | None = None

    def __post_init__(self) -> None:
        require_non_empty("contract_id", self.contract_id)
        require_non_empty("bidding_zone", self.bidding_zone)
        require_finite("fixed_price_per_mwh", self.fixed_price_per_mwh)
        PowerDeliveryInterval(self.start_utc, self.end_utc)

    def covers(self, interval: PowerDeliveryInterval) -> bool:
        """Whether the complete interval falls inside the PPA delivery term."""
        return self.start_utc <= interval.start_utc and interval.end_utc <= self.end_utc
