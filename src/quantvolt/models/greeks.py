"""Shared result vocabulary — the ``Greeks``.

Co-location convention (see ``.kiro/steering/structure.md``): only *shared*
result vocabulary lives in ``models/``. ``Greeks`` earns a place here because it
is reused across every option-style pricer — vanilla, cap/floor strips, tolling,
and portfolio aggregation. Module-specific ``...Request``/``...Result`` types
(e.g. ``VanillaOptionRequest``, ``VanillaOptionResult``) are defined *beside*
their pricer in ``pricing/``, never in this package. There is no ``results.py``
god-module.

``Greeks`` carries its own aggregation arithmetic (``__add__``, ``scale``,
``zero``) rather than exposing raw fields for callers to combine. This is the
Tell-Don't-Ask cure for the Data Class smell (see ``coding-style.md`` §1):
elementwise combination operates only on a ``Greeks``'s own data, so it belongs
on the value object. Strips and portfolios sum per-element Greeks into an
aggregate through these methods instead of reaching into the fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Greeks:
    """First-order (and gamma) option sensitivities.

    All fields are per-unit-of-underlying sensitivities. Instances are immutable
    value objects; the arithmetic helpers return new ``Greeks`` rather than
    mutating in place.
    """

    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float

    def __add__(self, other: Greeks) -> Greeks:
        """Elementwise sum, for aggregating a strip or portfolio of positions."""
        return Greeks(
            delta=self.delta + other.delta,
            gamma=self.gamma + other.gamma,
            vega=self.vega + other.vega,
            theta=self.theta + other.theta,
            rho=self.rho + other.rho,
        )

    def scale(self, factor: float) -> Greeks:
        """Elementwise multiply by ``factor`` (e.g. a position size or weight)."""
        return Greeks(
            delta=self.delta * factor,
            gamma=self.gamma * factor,
            vega=self.vega * factor,
            theta=self.theta * factor,
            rho=self.rho * factor,
        )

    @classmethod
    def zero(cls) -> Greeks:
        """Additive identity — the natural start value when summing Greeks."""
        return cls(delta=0.0, gamma=0.0, vega=0.0, theta=0.0, rho=0.0)
