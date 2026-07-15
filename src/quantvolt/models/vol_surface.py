"""Volatility surface value objects and moneyness (Task 7).

Pure, immutable domain vocabulary (Tell-Don't-Ask): a :class:`VolatilitySurface`
answers queries about *its own* implied-vol term structure via
:meth:`~VolatilitySurface.sigma_at`; callers never index into ``.tenors[i].sigma``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .._validation import require_non_empty, require_positive
from ..exceptions import MissingTenorError, ValidationError
from .commodity import CommodityConfig
from .schedule import DeliveryPeriod


class Moneyness(StrEnum):
    """Option moneyness relative to the forward (design §3.1)."""

    ATM = "atm"
    OTM = "otm"
    ITM = "itm"


@dataclass(frozen=True, slots=True)
class VolatilityTenor:
    """A single point on the vol term structure: an implied vol for one delivery period.

    ``sigma`` is an annualised implied volatility and is validated eagerly to be
    strictly positive in :meth:`__post_init__`.
    """

    period: DeliveryPeriod
    sigma: float  # annualised implied volatility

    def __post_init__(self) -> None:
        require_positive("sigma", self.sigma)


@dataclass(frozen=True, slots=True)
class VolatilitySurface:
    """A commodity's implied-vol term structure, one :class:`VolatilityTenor` per period.

    Consistency invariants (validated eagerly in :meth:`__post_init__`):

    - ``tenors`` is non-empty.
    - ``tenors`` is strictly increasing by :attr:`VolatilityTenor.period`, so there
      are no duplicate periods; the surface validates this for itself rather than
      trusting callers (Tell-Don't-Ask).
    """

    commodity: CommodityConfig
    tenors: tuple[VolatilityTenor, ...]

    def __post_init__(self) -> None:
        require_non_empty("tenors", self.tenors)
        for index, (prev, curr) in enumerate(zip(self.tenors, self.tenors[1:], strict=False)):
            if prev.period >= curr.period:
                raise ValidationError(
                    "tenors must be strictly increasing by period with no "
                    f"duplicates; offending pair at index {index}: "
                    f"{prev.period!r} is not before {curr.period!r}"
                )

    def sigma_at(self, period: DeliveryPeriod) -> float:
        """Annualised implied vol for an exact ``period`` match.

        This is an exact-period lookup, not interpolation. Raises
        :class:`MissingTenorError` naming ``period`` and the covered range when the
        surface has no tenor for it.
        """
        for tenor in self.tenors:
            if tenor.period == period:
                return tenor.sigma
        first, last = self.tenors[0].period, self.tenors[-1].period
        raise MissingTenorError(
            f"period {period!r} is not covered by the volatility surface; "
            f"covered range [{first!r}, {last!r}]"
        )
