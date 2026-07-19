"""Discount curve with linear interpolation."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import date

from .._validation import require_discount_factor, require_non_empty
from ..exceptions import MissingTenorError, ValidationError


@dataclass(frozen=True, slots=True)
class DiscountCurve:
    """A term structure of discount factors keyed by tenor date.

    ``tenors`` and ``factors`` are parallel, so ``factors[i]`` is the discount
    factor observed for ``tenors[i]``.

    Conventions (validated eagerly in ``__post_init__``):

    - ``tenors`` is non-empty and strictly increasing.
    - Every tenor lies strictly *after* ``reference_date`` (``tenor > reference_date``);
      a discount curve prices future cash flows, so ``reference_date`` itself is not a tenor.
    - Every factor lies in ``(0, 1]`` (see :func:`require_discount_factor`).
    """

    reference_date: date
    tenors: tuple[date, ...]
    factors: tuple[float, ...]  # parallel to tenors

    def __post_init__(self) -> None:
        require_non_empty("tenors", self.tenors)
        if len(self.tenors) != len(self.factors):
            raise ValidationError(
                "tenors and factors must have equal length, "
                f"got {len(self.tenors)} tenors and {len(self.factors)} factors"
            )
        for earlier, later in zip(self.tenors, self.tenors[1:], strict=False):
            if later <= earlier:
                raise ValidationError(
                    "tenors must be strictly increasing, "
                    f"got {earlier.isoformat()} not before {later.isoformat()}"
                )
        for i, tenor in enumerate(self.tenors):
            if tenor <= self.reference_date:
                raise ValidationError(
                    f"tenors[{i}] must be > reference_date, "
                    f"got {tenor.isoformat()} <= {self.reference_date.isoformat()}"
                )
        for i, factor in enumerate(self.factors):
            require_discount_factor(f"factors[{i}]", factor)

    def discount_factor(self, target_date: date) -> float:
        """Discount factor for ``target_date`` by linear interpolation.

        Interpolation is linear in the discount factor against time in days from
        ``reference_date``, between the two bracketing tenors. An exact tenor match
        returns its stored factor. Interpolation is only defined within
        ``[tenors[0], tenors[-1]]``: a ``target_date`` before the first tenor
        (including ``reference_date`` itself) or after the last tenor raises
        :class:`MissingTenorError`.
        """
        first, last = self.tenors[0], self.tenors[-1]
        if target_date < first or target_date > last:
            raise MissingTenorError(
                f"target_date {target_date.isoformat()} is outside the covered range "
                f"[{first.isoformat()}, {last.isoformat()}]"
            )
        idx = bisect.bisect_left(self.tenors, target_date)
        if self.tenors[idx] == target_date:
            return self.factors[idx]
        lo_date, hi_date = self.tenors[idx - 1], self.tenors[idx]
        lo_factor, hi_factor = self.factors[idx - 1], self.factors[idx]
        x = (target_date - self.reference_date).days
        x_lo = (lo_date - self.reference_date).days
        x_hi = (hi_date - self.reference_date).days
        weight = (x - x_lo) / (x_hi - x_lo)
        return lo_factor + weight * (hi_factor - lo_factor)
