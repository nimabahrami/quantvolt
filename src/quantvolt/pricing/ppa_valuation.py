"""PPA intrinsic mark-to-market — a forward-looking valuation distinct from the
realized-settlement functions of :mod:`quantvolt.pricing.ppa` (Tasks 19-22; Req 15-17;
Property 84).

:func:`quantvolt.pricing.ppa.settle_ppa_interval` reconciles what actually happened over
one delivered interval from metered data; it needs no probability model. This module
answers a different question — *what is an unexpired PPA worth today, against the
forward curve* — as a **discounted-cash-flow identity**, not a stochastic model:

    ``npv = sum_t DF(t) * V_t * (K_t - capture_t * F_t)``

- ``DF(t)`` is the discount factor at the period's settlement date (``period.last_day``,
  base design §2.5 discounting convention).
- ``F_t`` is the forward price at that period.
- ``V_t`` is the expected delivered energy (MWh) for the period.
- ``capture_t`` is the capture factor (how much of the flat forward the plant's shape
  actually captures; ``1.0`` for a baseload-like assumption).
- ``K_t`` is the PPA's contractual price for the period.

The **producer sign** (``fixed - spot``/``fixed - forward``) follows
``ppa-power-hedging`` (:mod:`quantvolt.pricing.ppa`): a producer is long the fixed price
and short the (capture-weighted) forward.

K_t resolution
--------------
``K_t`` defaults to the contract's flat ``fixed_price_per_mwh``. When a
:class:`~quantvolt.models.ppa_terms.PpaPriceTerms` is available — either passed
explicitly via the optional ``price_terms`` argument, or (when ``price_terms`` is
``None``) discovered on ``contract.terms.price`` — ``K_t`` is a **time-weighted**
average of the resolved indexation-then-clamp price
(:meth:`~quantvolt.models.ppa_terms.PpaPriceTerms.effective_price`) across the whole
delivery period, **not** a single point-in-time lookup (AMENDED 2026-07-19, code
review FIX 4; supersedes an earlier first-day-anchor declared decision that dropped
any :class:`~quantvolt.models.ppa_terms.IndexationStep` falling mid-period).

The period ``[period_start_utc, period_end_utc)`` — the first calendar day of the
month at UTC midnight to the first calendar day of the *next* month at UTC midnight
(the same anchor convention as before, now used as an interval rather than a single
point; see :func:`_period_bounds_utc`) — is partitioned at every ``IndexationStep``
boundary falling strictly inside it. Each resulting segment's constant, floor/cap-
clamped price is weighted by its share of the period's total seconds:

    ``K_t = sum_i (segment_i_seconds / period_seconds) * effective_price(segment_i_start)``

This mirrors the settlement-side resolution in :mod:`quantvolt.pricing.ppa`
(``_resolve_effective_price``), which anchors indexation lookup at an interval's own
start; here, since each valuation period is a whole calendar month rather than a
timestamped sub-hourly interval, a single point-in-time anchor would silently drop
any indexation step that takes effect mid-month, materially misstating the
mark-to-market. Time-weighting is the coherent generalisation for a period-level
``K_t`` and is itself a declared design decision of this module (documented on
:func:`price_ppa`).

This is an **adaptation** of the original spec text: Requirement 15.4, as authored,
found the ``ppa-contract-terms`` spec / ``PpaPriceTerms`` type not yet landed and
therefore specified a ``price_terms`` argument that was a no-op when absent. That type
has since landed (``models/ppa_terms.py``), so this module consumes
``contract.terms.price`` directly rather than leaving the argument inert; the
``price_terms`` argument is retained (spec API-shape compatibility) as an explicit
override that takes precedence over ``contract.terms.price`` when supplied. See
``tasks.md`` Task 20 for this adaptation note.

Explicitly excluded: negative-price optionality
------------------------------------------------
A PPA's negative-price clause (:class:`~quantvolt.models.ppa_terms.NegativePriceClause`)
is **spot optionality** — its trigger depends on a future spot price outcome, not a
deterministic identity — and is **never** consulted here (Req 15.5). Modelling it would
require an option-pricing kernel with a market-index choice this spec is not authorised
to make; silently folding it into ``K_t`` would misstate the intrinsic MtM as if the
clause were certain to (or never to) trigger.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import pairwise
from typing import Any

from .._validation import require_non_negative, require_positive
from ..exceptions import ExpiredContractError, ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.ppa import PpaContract
from ..models.ppa_terms import PpaPriceTerms
from ..models.schedule import DeliveryPeriod


@dataclass(frozen=True, slots=True)
class PpaPeriodVolume:
    """Expected delivered energy and capture factor for one delivery period (Req 15.1).

    ``expected_mwh`` is the forecast delivered energy for the period (non-negative — a
    period with no expected generation is a legitimate, zero-value input, not an error).
    ``capture_factor`` scales the flat forward down (or up) to the plant's expected
    realised price relative to the flat baseload forward; it defaults to ``1.0`` (a
    baseload-like assumption) and must be strictly positive.
    """

    period: DeliveryPeriod
    expected_mwh: float
    capture_factor: float = 1.0

    def __post_init__(self) -> None:
        require_non_negative("expected_mwh", self.expected_mwh)
        require_positive("capture_factor", self.capture_factor)


@dataclass(frozen=True, slots=True)
class PpaVolumeProfile:
    """A non-empty, strictly period-increasing run of :class:`PpaPeriodVolume` (Req 15.1)."""

    volumes: tuple[PpaPeriodVolume, ...]

    def __post_init__(self) -> None:
        if len(self.volumes) == 0:
            raise ValidationError("volumes must be non-empty")
        for index, (previous, current) in enumerate(
            zip(self.volumes, self.volumes[1:], strict=False)
        ):
            if previous.period >= current.period:
                raise ValidationError(
                    "volumes must be strictly increasing by period with no duplicates or "
                    f"overlaps; offending pair at index {index}: {previous.period!r} is not "
                    f"before {current.period!r}"
                )


@dataclass(frozen=True, slots=True)
class PpaPeriodValuation:
    """One period's detail behind the aggregate :class:`PpaValuationResult` (Req 15.2)."""

    period: DeliveryPeriod
    forward: float
    discount_factor: float
    expected_mwh: float
    capture_factor: float
    cashflow: float  # DF(t) * V_t * (K_t - capture_t * F_t)
    delta: float  # -DF(t) * V_t * capture_t


@dataclass(frozen=True, slots=True)
class PpaValuationResult:
    """Producer-side intrinsic mark-to-market: aggregate NPV plus per-period detail
    and per-period producer delta, keyed ``(contract.bidding_zone, period)`` (Req 15.3)."""

    npv: float
    per_period: tuple[PpaPeriodValuation, ...]
    delta: dict[tuple[str, DeliveryPeriod], float]


def _period_bounds_utc(period: DeliveryPeriod) -> tuple[datetime, datetime]:
    """The UTC ``[start, end)`` instants spanning ``period`` (AMENDED 2026-07-19, FIX 4).

    ``start`` is the period's first calendar day at UTC midnight (the same anchor this
    module always used); ``end`` is the first calendar day of the *next* month at UTC
    midnight. This is a declared design decision of this module, chosen as the closest
    analogue — for a whole-month valuation period — to
    :mod:`quantvolt.pricing.ppa`'s own convention of anchoring indexation lookup at an
    interval's ``start_utc`` (see ``_resolve_effective_price``).
    """
    start = datetime(period.year, period.month, 1, tzinfo=UTC)
    if period.month == 12:
        end = datetime(period.year + 1, 1, 1, tzinfo=UTC)
    else:
        end = datetime(period.year, period.month + 1, 1, tzinfo=UTC)
    return start, end


def _time_weighted_k_t(price_terms: PpaPriceTerms, period: DeliveryPeriod, *, base: float) -> float:
    """Time-weighted ``K_t`` across ``period``, partitioned at ``IndexationStep`` boundaries.

    See the module docstring's "K_t resolution" section (AMENDED 2026-07-19, code review
    FIX 4). Each segment's own floor/cap-clamped price
    (:meth:`~quantvolt.models.ppa_terms.PpaPriceTerms.effective_price`) is weighted by its
    share of the period's total seconds; a period with no indexation step falling inside
    it degenerates to a single segment, i.e. the old point-in-time result.
    """
    period_start, period_end = _period_bounds_utc(period)
    period_seconds = (period_end - period_start).total_seconds()
    boundaries = [period_start]
    boundaries.extend(
        step.effective_from_utc
        for step in price_terms.indexation
        if period_start < step.effective_from_utc < period_end
    )
    boundaries.append(period_end)
    weighted = 0.0
    for segment_start, segment_end in pairwise(boundaries):
        segment_seconds = (segment_end - segment_start).total_seconds()
        segment_price = price_terms.effective_price(segment_start, base=base)
        weighted += (segment_seconds / period_seconds) * segment_price
    return weighted


def _resolve_k_t(
    contract: PpaContract,
    period: DeliveryPeriod,
    price_terms: PpaPriceTerms | None,
) -> float:
    """Resolve ``K_t``: an explicit ``price_terms`` override wins; otherwise
    ``contract.terms.price`` is consumed if present; otherwise the flat
    ``fixed_price_per_mwh`` (indexation/clamp are a no-op when neither is present).
    When a :class:`~quantvolt.models.ppa_terms.PpaPriceTerms` is present, ``K_t`` is the
    time-weighted average produced by :func:`_time_weighted_k_t`."""
    base = contract.fixed_price_per_mwh
    terms = price_terms
    if terms is None and contract.terms is not None:
        terms = contract.terms.price
    if terms is None:
        return base
    return _time_weighted_k_t(terms, period, base=base)


def price_ppa(
    contract: PpaContract,
    profile: PpaVolumeProfile,
    forward_curve: ForwardCurve,
    discount_curve: DiscountCurve,
    valuation_date: date,
    price_terms: PpaPriceTerms | None = None,
) -> PpaValuationResult:
    """Producer-side intrinsic mark-to-market of an unexpired PPA (Req 15.2).

    ``npv = sum_t DF(t) * V_t * (K_t - capture_t * F_t)``, where ``DF(t)`` is
    ``discount_curve.discount_factor(period.last_day)``, ``F_t`` is
    ``forward_curve.price_at(period)``, ``V_t`` is ``expected_mwh``, ``capture_t`` is
    ``capture_factor``, and ``K_t`` is the (possibly indexed/clamped) PPA fixed price —
    see the module docstring's "K_t resolution" section. The producer sign
    (``fixed - capture * forward``) follows ``ppa-power-hedging``
    (:mod:`quantvolt.pricing.ppa`).

    Each period's producer delta is ``delta_t = -DF(t) * V_t * capture_t`` — the NPV
    sensitivity to a unit bump of that period's forward — keyed
    ``(contract.bidding_zone, period)`` (the forward-curve key is the PPA's
    ``bidding_zone``, following the transport-right precedent of keying by the curve
    identifier).

    The PPA's negative-price clause (spot optionality) is **excluded** from this
    intrinsic MtM and never consulted (Req 15.5) — see the module docstring.

    Args:
        contract: The PPA whose fixed price (and, if attached, ``terms.price``
            indexation/clamp) supplies ``K_t``.
        profile: The expected-volume profile to value; every period must be covered by
            both ``forward_curve`` and ``discount_curve``.
        forward_curve: Supplies ``F_t``; must have a node for every period in ``profile``.
        discount_curve: Supplies ``DF(t)``; must cover every period's settlement date
            (``period.last_day``).
        valuation_date: The date NPV is computed as of. A period whose delivery ended
            strictly before this date is an expired cash flow, not a forward-looking
            one, and raises (the same convention as
            :func:`quantvolt.pricing.futures.price_futures`).
        price_terms: An optional explicit :class:`~quantvolt.models.ppa_terms.PpaPriceTerms`
            override; when ``None`` (the default), ``contract.terms.price`` is consumed
            if present, else ``K_t`` is the flat ``contract.fixed_price_per_mwh``.

    Returns:
        The aggregate NPV, per-period detail, and the per-period producer delta dict.

    Raises:
        ValidationError: If ``contract`` is not a :class:`~quantvolt.models.ppa.PpaContract`.
        ExpiredContractError: If any period in ``profile`` ended strictly before
            ``valuation_date``.
        MissingTenorError: If ``forward_curve`` has no node for a period, or
            ``discount_curve`` does not cover a period's settlement date.
    """
    if not isinstance(contract, PpaContract):
        raise ValidationError(f"contract must be a PpaContract, got {type(contract).__name__}")
    per_period: list[PpaPeriodValuation] = []
    delta: dict[tuple[str, DeliveryPeriod], float] = {}
    npv = 0.0
    for volume in profile.volumes:
        period = volume.period
        delivery_end = period.last_day
        if delivery_end < valuation_date:
            raise ExpiredContractError(
                f"profile period {period!r} ended on {delivery_end.isoformat()}, strictly "
                f"before valuation_date {valuation_date.isoformat()}; expired periods cannot "
                "be priced"
            )
        forward = forward_curve.price_at(period)
        discount_factor = discount_curve.discount_factor(delivery_end)
        k_t = _resolve_k_t(contract, period, price_terms)
        cashflow = discount_factor * volume.expected_mwh * (k_t - volume.capture_factor * forward)
        period_delta = -discount_factor * volume.expected_mwh * volume.capture_factor
        npv += cashflow
        delta[(contract.bidding_zone, period)] = period_delta
        per_period.append(
            PpaPeriodValuation(
                period=period,
                forward=forward,
                discount_factor=discount_factor,
                expected_mwh=volume.expected_mwh,
                capture_factor=volume.capture_factor,
                cashflow=cashflow,
                delta=period_delta,
            )
        )
    return PpaValuationResult(npv=npv, per_period=tuple(per_period), delta=delta)


def make_ppa_pricer(profiles: Mapping[str, PpaVolumeProfile]) -> Callable[[Any, Any], Any]:
    """Build a ``pricers=`` entry that opts ``PpaContract`` positions into ``value_portfolio``
    (Req 16).

    Returned as a plain closure (typed loosely as ``Callable[[Any, Any], Any]`` here to
    keep this module's dependencies to ``models/*`` and ``_validation``, per this spec's
    acyclic dependency design — it is never imported by ``portfolio/model.py`` or
    ``portfolio/valuation.py``); at the call site it has exactly the shape
    ``portfolio.valuation.Pricer`` expects: ``(Position, MarketData) -> PricedPosition``.
    Register it explicitly:

        ``value_portfolio(book, market, pricers={PpaContract: make_ppa_pricer(profiles)})``

    ``PpaContract`` is deliberately **NOT** added to ``DEFAULT_PRICERS`` (Req 16.2): a
    raise-on-missing-profile default pricer would silently break every existing mixed
    book that holds an unmodelled PPA (base-spec Req 13.3's "lands in unpriced"
    semantics). Only callers who explicitly opt in via this factory get a missing-profile
    error instead of a silent ``unpriced`` landing (Req 16.3).

    Args:
        profiles: Maps a PPA's ``contract_id`` to the :class:`PpaVolumeProfile` to value
            it against.

    Returns:
        A pricer closure ``(position, market_data) -> PricedPosition``: looks up the
        curve at ``instrument.bidding_zone``, delegates to :func:`price_ppa`, and
        packages the result (``reference_prices`` populated from each period's forward).

    Raises (at call time, when the returned closure is invoked):
        ValidationError: If the position's instrument is not a ``PpaContract``, or its
            ``contract_id`` has no entry in ``profiles`` (naming the missing key and
            listing the available ones).
    """

    def _pricer(position: Any, market_data: Any) -> Any:
        # Local import: pricing/ppa_valuation.py depends only on models/* + _validation
        # at module scope (this spec's dependency design); PricedPosition is only needed
        # inside the closure body, once the caller actually invokes it.
        from ..portfolio.model import PricedPosition

        instrument = position.instrument
        if not isinstance(instrument, PpaContract):
            raise ValidationError(
                "position.instrument must be a PpaContract for this pricer, "
                f"got {type(instrument).__name__}"
            )
        profile = profiles.get(instrument.contract_id)
        if profile is None:
            available = ", ".join(repr(key) for key in sorted(profiles)) or "none"
            raise ValidationError(
                f"profiles has no PpaVolumeProfile for contract_id "
                f"{instrument.contract_id!r}; available contract ids: {available}"
            )
        curve = market_data.curve_for(instrument.bidding_zone)
        result = price_ppa(
            instrument, profile, curve, market_data.discount_curve, market_data.valuation_date
        )
        reference_prices = {
            (instrument.bidding_zone, period_value.period): period_value.forward
            for period_value in result.per_period
        }
        return PricedPosition(
            position=position,
            npv=result.npv,
            delta=dict(result.delta),
            reference_prices=reference_prices,
        )

    return _pricer
