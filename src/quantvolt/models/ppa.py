"""Power-purchase agreement terms at timestamped delivery resolution."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .._validation import require_finite, require_non_empty
from ..exceptions import ValidationError
from .interval import PowerDeliveryInterval
from .ppa_terms import IndexationStep, PpaTerms


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
    terms: PpaTerms | None = None

    def __post_init__(self) -> None:
        require_non_empty("contract_id", self.contract_id)
        require_non_empty("bidding_zone", self.bidding_zone)
        require_finite("fixed_price_per_mwh", self.fixed_price_per_mwh)
        PowerDeliveryInterval(self.start_utc, self.end_utc)
        if self.terms is not None:
            if not isinstance(self.terms, PpaTerms):
                raise ValidationError(
                    f"terms must be None or a PpaTerms, got {type(self.terms).__name__}"
                )
            if self.terms.price is not None:
                self._validate_indexation(self.terms.price.indexation)

    def _validate_indexation(self, indexation: Sequence[IndexationStep]) -> None:
        """Cross-validate indexation steps against this contract's own term.

        Every step's ``effective_from_utc`` must lie strictly inside the
        contract term (``start_utc <= effective_from_utc < end_utc``) and the
        steps must be strictly increasing (already enforced by
        :class:`~.ppa_terms.PpaPriceTerms`; re-checked here for defense in depth
        against the contract's own bounds).
        """
        previous: datetime | None = None
        for index, step in enumerate(indexation):
            if not (self.start_utc <= step.effective_from_utc < self.end_utc):
                raise ValidationError(
                    f"terms.price.indexation[{index}].effective_from_utc must satisfy "
                    f"start_utc <= effective_from_utc < end_utc, got {step.effective_from_utc!r} "
                    f"outside {self.start_utc!r}..{self.end_utc!r}"
                )
            if previous is not None and not step.effective_from_utc > previous:
                raise ValidationError(
                    f"terms.price.indexation[{index}].effective_from_utc must be strictly "
                    f"increasing, got {step.effective_from_utc!r} after previous step {previous!r}"
                )
            previous = step.effective_from_utc

    def covers(self, interval: PowerDeliveryInterval) -> bool:
        """Whether the complete interval falls inside the PPA delivery term."""
        return self.start_utc <= interval.start_utc and interval.end_utc <= self.end_utc
