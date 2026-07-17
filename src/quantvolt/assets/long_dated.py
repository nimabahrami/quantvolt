"""Long-dated / projected-spot valuation governance (Task 76; Req 23.1-23.4).

Long tenors run past the liquid forward curve. Beyond that horizon there is no
tradable benchmark, so a value must be *projected* from a spot model plus an
explicit corporate risk premium — and such a value carries far more risk than a
forward-covered one. This module keeps the two regimes strictly separated so that
long-dated risk is never understated (Req 23):

- :func:`valuation_benchmark` returns the **forward-curve** price where the period
  is liquid, and otherwise a **projected-spot** value tagged distinctly, so a
  projected figure can never be mistaken for a forward-based one (Req 23.1-23.2).
- :func:`var_applicability_guard` flags short-horizon VaR as *inapplicable* for a
  position valued off projected spot (Req 23.3): VaR is meaningful only in liquid
  markets (Chapter-10 caveat).
- :func:`furthest_forward_lower_bound` implements the "furthest liquid forward is a
  lower bound for later tenors" trick **only for storable commodities**, and
  refuses it for non-storable power (Req 23.4).

Tagging semantics
-----------------
:class:`ValuationSource` is the single vocabulary of provenance tags. Its two
values, ``"forward"`` and ``"projected"``, are exactly the strings a caller should
propagate onto a :class:`~quantvolt.portfolio.model.Position`'s ``tags`` so that
downstream risk code can tell the regimes apart. :class:`BenchmarkResult` carries
the tag prominently in its ``source`` field.

Intended wiring (this module does not touch ``risk/``)
------------------------------------------------------
1. Value a long-dated period with :func:`valuation_benchmark`; read
   ``result.source``.
2. Build the ``Position`` carrying ``result.source`` (i.e. the string
   ``ValuationSource.PROJECTED`` / ``ValuationSource.FORWARD``) in its ``tags``,
   and the ``PricedPosition`` from ``result.value``.
3. Before including the position in an MC-VaR / parametric-VaR run, *consult*
   :func:`var_applicability_guard`: a projected-valued position returns
   ``applicable=False`` (or, with ``strict=True``, raises) so the risk caller can
   exclude it or switch to CFaR / scenario analysis. The VaR modules stay
   unchanged; they simply query this verdict.

Design choices
--------------
- ``spot_model`` is a **pure callable** ``DeliveryPeriod -> float`` returning the
  model's projected spot expectation for a period. The library treats it as data
  and never mutates it.
- Storability is a **caller-declared** ``storable: bool`` argument, not inferred
  from ``commodity_id`` / ``price_unit``. Per the library's "the caller supplies
  all data" principle, whether the carry / cash-and-carry argument holds is a
  market judgement the caller owns; the library refuses to guess it from naming
  conventions.
- The corporate risk premium must be an explicitly *corporate*-tagged
  :class:`CorporatePremium` (via :class:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind`).
  A market-tagged or untagged premium is rejected — the premium is never applied
  silently (Req 19.3).

Dependency note: this module imports value objects from ``models/``, ``numerics/``
and the :class:`~quantvolt.portfolio.model.PricedPosition` value object; none of
those import ``assets/``, so the dependency graph stays acyclic. It never imports
``risk/``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from ..exceptions import MissingTenorError, ValidationError
from ..models.curve import ForwardCurve
from ..models.schedule import DeliveryPeriod
from ..numerics.risk_adjustment import PriceOfRiskKind
from ..portfolio.model import PricedPosition

# A pure projection of a period to its model spot expectation (documented, never mutated).
SpotModel = Callable[[DeliveryPeriod], float]


class ValuationSource(StrEnum):
    """Provenance of a long-dated valuation; the tag that separates the two regimes.

    The string values double as the ``Position.tags`` markers a caller propagates so
    that :func:`var_applicability_guard` (and any risk code) can tell a projected
    value apart from a forward-based one.
    """

    FORWARD = "forward"  # liquid forward curve covers the period (Req 23.1)
    PROJECTED = "projected"  # projected from a spot model + corporate premium (Req 23.2)


@dataclass(frozen=True, slots=True)
class CorporatePremium:
    """A projected-spot risk premium with an explicit price-of-risk provenance.

    ``kind`` has no default: the caller must state the provenance explicitly, so the
    premium is never applied silently (Req 19.3). :func:`valuation_benchmark` accepts
    only a :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`
    premium; a market-tagged one reflects traded quotes, not the firm's own long-dated
    risk appetite, and cannot stand in for it.

    Attributes:
        premium: The additive corporate risk premium in the commodity's price unit,
            applied as ``projected_spot = spot_model(period) + premium`` (Req 23.2).
            May be negative.
        kind: Provenance of the premium; must be
            :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`.
    """

    premium: float
    kind: PriceOfRiskKind


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """A long-dated valuation with its provenance tag carried prominently.

    ``source`` is the load-bearing field: :attr:`ValuationSource.FORWARD` means the
    value is the liquid forward price (Req 23.1); :attr:`ValuationSource.PROJECTED`
    means it is a projected-spot value (Req 23.2) that carries much higher risk and
    for which short-horizon VaR is inapplicable.
    """

    period: DeliveryPeriod
    value: float
    source: ValuationSource

    @property
    def is_projected(self) -> bool:
        """``True`` iff this value came from projected spot rather than the forward curve."""
        return self.source == ValuationSource.PROJECTED

    @property
    def var_applicable(self) -> bool:
        """``True`` iff short-horizon VaR is meaningful for a position at this benchmark.

        Convenience mirror of :func:`var_applicability_guard` for a single period:
        forward-based values are VaR-applicable, projected-spot values are not.
        """
        return self.source == ValuationSource.FORWARD


@dataclass(frozen=True, slots=True)
class VarApplicabilityVerdict:
    """Whether short-horizon VaR is applicable to a position, with the reason.

    A frozen verdict an MC-VaR / parametric-VaR caller can consult without this module
    reaching into the risk engines. ``applicable`` is ``False`` for projected-spot
    positions (Req 23.3); ``reason`` states why in human-readable form.
    """

    applicable: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LowerBoundResult:
    """The furthest-forward lower bound for an illiquid later tenor (storable only).

    Attributes:
        period: The illiquid tenor the bound is computed for.
        lower_bound: The furthest visible forward price, used as a lower bound.
        furthest_forward_period: The period the bound was read from (the curve's
            furthest node), retained for auditability.
    """

    period: DeliveryPeriod
    lower_bound: float
    furthest_forward_period: DeliveryPeriod


def valuation_benchmark(
    period: DeliveryPeriod,
    forward_curve: ForwardCurve,
    spot_model: SpotModel,
    corporate_premium: CorporatePremium,
) -> BenchmarkResult:
    """Value ``period`` off the forward curve where liquid, else off projected spot.

    Where the liquid ``forward_curve`` covers ``period``, the forward price is the
    valuation benchmark and no projected-spot value is substituted (Req 23.1). A
    period present on the curve counts as forward-based whether its node is
    ``observed`` or ``interpolated`` — both lie within the liquid forward span. Where
    the curve does not cover ``period``, the value is projected as
    ``spot_model(period) + corporate_premium.premium`` and tagged
    :attr:`ValuationSource.PROJECTED` (Req 23.2).

    ``corporate_premium`` is validated eagerly (before the liquidity branch) so a
    market-tagged or untagged premium is rejected regardless of this period's
    liquidity — the corporate risk premium is never applied silently (Req 19.3).

    Args:
        period: The delivery period to value.
        forward_curve: The liquid forward curve; membership of ``period`` decides the
            regime.
        spot_model: Pure callable ``DeliveryPeriod -> float`` giving the model spot
            expectation used when no liquid forward exists. Never mutated.
        corporate_premium: The additive corporate risk premium, explicitly tagged
            :attr:`~quantvolt.numerics.risk_adjustment.PriceOfRiskKind.CORPORATE`.

    Returns:
        A :class:`BenchmarkResult` whose ``source`` tags the regime prominently.

    Raises:
        ValidationError: If ``corporate_premium`` is not an explicitly corporate-tagged
            :class:`CorporatePremium`.
    """
    _require_corporate_premium(corporate_premium)
    liquid_price = _forward_price_if_liquid(forward_curve, period)
    if liquid_price is not None:
        return BenchmarkResult(period=period, value=liquid_price, source=ValuationSource.FORWARD)
    projected_value = spot_model(period) + corporate_premium.premium
    return BenchmarkResult(period=period, value=projected_value, source=ValuationSource.PROJECTED)


def var_applicability_guard(
    position: PricedPosition,
    *,
    strict: bool = False,
) -> VarApplicabilityVerdict:
    """Flag short-horizon VaR as inapplicable for a projected-spot-valued position.

    Reads the position's provenance from ``position.position.tags``: a position
    carrying the :attr:`ValuationSource.PROJECTED` tag was valued off projected spot,
    for which short-horizon VaR is not meaningful — VaR is meaningful only in liquid
    markets (Chapter-10 caveat, Req 23.3). Absence of that tag is treated as
    forward-based / liquid and therefore VaR-applicable.

    Designed to be *consulted* by MC-VaR / parametric-VaR callers: they inspect the
    returned verdict and exclude the position (or switch to CFaR / scenario analysis)
    without this module modifying ``risk/``. With ``strict=True`` the guard instead
    raises for an inapplicable position, for callers that prefer to hard-fail.

    Args:
        position: The priced position to judge, as consumed by the risk engines.
        strict: When ``True``, raise :class:`ValidationError` for a projected-spot
            position instead of returning an ``applicable=False`` verdict.

    Returns:
        A :class:`VarApplicabilityVerdict` with ``applicable`` and a ``reason``.

    Raises:
        ValidationError: If ``strict`` is ``True`` and the position is projected-valued.
    """
    if _is_projected_valued(position):
        reason = (
            "position is valued off projected spot (carries the "
            f"{ValuationSource.PROJECTED.value!r} tag); short-horizon VaR is inapplicable "
            "because VaR is meaningful only in liquid markets (Chapter-10 caveat, Req 23.3). "
            "Use an explicitly extended holding period, CFaR, or scenario analysis instead."
        )
        if strict:
            raise ValidationError(reason)
        return VarApplicabilityVerdict(applicable=False, reason=reason)
    reason = (
        "position is valued off a liquid forward curve (no "
        f"{ValuationSource.PROJECTED.value!r} tag); standard short-horizon VaR applies "
        "(Req 23.1/23.3)."
    )
    return VarApplicabilityVerdict(applicable=True, reason=reason)


def furthest_forward_lower_bound(
    forward_curve: ForwardCurve,
    period: DeliveryPeriod,
    *,
    storable: bool,
) -> LowerBoundResult:
    """Use the furthest visible forward as a lower bound for an illiquid later tenor.

    For a **storable** commodity the cash-and-carry / no-arbitrage relationship links
    a later delivery to a nearer one, so the furthest liquid forward price is a valid
    lower bound for tenors beyond the curve (Req 23.4). This helper returns that bound
    for ``period`` (which must be strictly later than the furthest liquid forward).

    For a **non-storable** commodity such as power (``storable=False``) the bound is
    refused: non-storability breaks the carry argument, so a nearer forward does not
    bound a later illiquid tenor and the furthest forward is not a valid lower bound
    (Req 23.4). Storability is caller-declared, never inferred from the commodity.

    Args:
        forward_curve: The liquid forward curve; its furthest node supplies the bound.
        period: The illiquid tenor to bound; must be strictly later than the furthest
            liquid forward.
        storable: Caller's declaration that the commodity is storable. ``False``
            (e.g. power) refuses the bound.

    Returns:
        A :class:`LowerBoundResult` carrying the bound and the period it came from.

    Raises:
        ValidationError: If ``storable`` is ``False`` (non-storable / power), or if
            ``period`` is not strictly later than the furthest liquid forward.
    """
    if not storable:
        raise ValidationError(
            "storable=False: the furthest-forward lower bound is refused for non-storable "
            "commodities such as power (Req 23.4). Non-storability breaks the "
            "cash-and-carry / no-arbitrage argument that lets a nearer liquid forward bound "
            "a later illiquid tenor, so the furthest forward is not a valid lower bound for "
            "power."
        )
    furthest = forward_curve.nodes[-1]
    if period <= furthest.period:
        raise ValidationError(
            f"period {period!r} is not beyond the furthest liquid forward {furthest.period!r}; "
            "the furthest-forward lower bound applies only to illiquid tenors strictly later "
            "than the furthest liquid forward (Req 23.4)"
        )
    return LowerBoundResult(
        period=period,
        lower_bound=furthest.price,
        furthest_forward_period=furthest.period,
    )


def _require_corporate_premium(corporate_premium: CorporatePremium) -> None:
    """Reject a premium that is not an explicitly corporate-tagged :class:`CorporatePremium`.

    Guards both the untagged case (a caller passing a bare number rather than a
    :class:`CorporatePremium`) and the market-tagged case, naming ``corporate_premium``
    so the violated contract is unambiguous (Req 19.3).
    """
    if not isinstance(corporate_premium, CorporatePremium):
        raise ValidationError(
            "corporate_premium must be a CorporatePremium explicitly tagged "
            f"{PriceOfRiskKind.CORPORATE!r} (Req 19.3/23.2); the projected-spot risk premium "
            f"must never be applied untagged, got {type(corporate_premium).__name__}"
        )
    if corporate_premium.kind != PriceOfRiskKind.CORPORATE:
        raise ValidationError(
            f"corporate_premium.kind must be {PriceOfRiskKind.CORPORATE!r} for projected-spot "
            f"valuation (Req 19.3/23.2); a {corporate_premium.kind!r}-tagged premium reflects "
            "traded quotes, not the firm's long-dated risk appetite, and cannot stand in for "
            "the corporate risk premium — state the corporate price of risk explicitly"
        )


def _forward_price_if_liquid(forward_curve: ForwardCurve, period: DeliveryPeriod) -> float | None:
    """Return the forward price for ``period`` if the curve covers it, else ``None``.

    Tell-Don't-Ask: delegates the node lookup to :meth:`ForwardCurve.price_at` rather
    than scanning ``forward_curve.nodes`` here, and translates its
    :class:`~quantvolt.exceptions.MissingTenorError` (illiquid tenor) into ``None``.
    """
    try:
        return forward_curve.price_at(period)
    except MissingTenorError:
        return None


def _is_projected_valued(position: PricedPosition) -> bool:
    """``True`` iff the position carries the projected-spot provenance tag."""
    return ValuationSource.PROJECTED.value in position.position.tags
