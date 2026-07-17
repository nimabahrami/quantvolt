"""Transmission (power) & pipeline (gas) right valuation (Task 80; Req 24; Properties 67-68).

A transport right is the option to move a commodity from a liquid origin hub A to a
liquid destination hub B, exercised period by period only when the locational spread
covers the transport tariff. Thin orchestration over the value objects and the
spread-option engine (``coding-style``: validate -> compute per period -> package):

- **Intrinsic PV** (§12, Property 67): over the shared delivery periods,
  ``V = Σ_i D(t, T_i) · Q_delivered · max(P_B,i - P_A,i - T_AB, 0)`` with
  ``Q_delivered = min(Q, capacity) · (1 - loss)``. The per-period *payoff* the
  property names is the undiscounted ``Q_delivered · max(P_B - P_A - T_AB, 0)``.
- **Extrinsic (option) value** (Req 24.2): when both location volatilities and their
  correlation are supplied, each period is valued as a locational spread option
  (:func:`quantvolt.pricing.spread_option.price_spread_option`) — a call on
  ``P_B - P_A - T_AB`` (``forward1 = P_B``, ``forward2 = P_A``, ``strike = T_AB``,
  ``notional = Q_delivered``). ``time_to_expiry`` is ``day_count`` from
  ``discount_curve.reference_date`` to ``period.last_day`` — the flow decision
  horizon; ``settlement_lag_days`` shifts only the discount-factor lookup date, never
  the volatility horizon. The kernel premium is already discounted, so the
  per-period total value is that premium and the extrinsic value is
  ``premium - intrinsic`` (≥ 0: a spread option is worth at least its discounted
  intrinsic). Without vols/correlation the extrinsic value is zero.
- **Bidirectional** (Req 24.3, Property 68): each period is committed to the
  economically best of ``{A→B (tariff T_AB), B→A (tariff T_BA), no-flow}`` by *total*
  value. Since ``max`` over the two directions never exceeds their sum, a
  bidirectional right is subadditive: its value ≤ (A→B right) + (B→A right). For the
  intrinsic-only case the two directional payoffs are mutually exclusive (both cannot
  cover their tariff at once), so the bound is tight; once each direction carries
  option time value, the inequality is strict.

Perspective / sign convention (the **right holder**): the holder is long the sink
hub (benefits as its price rises) and short the source hub (benefits as its price
falls). So for an active A→B flow ``delta_destination > 0`` and ``delta_origin < 0``;
for an active B→A flow the signs swap. The two per-hub deltas therefore always carry
opposite signs.

Model limitation: the extrinsic path assumes lognormal location forwards (Kirk /
Margrabe) and so requires strictly positive ``P_A`` and ``P_B``; a non-positive
forward propagates the spread-option engine's ``ValidationError``. The intrinsic path
handles negative prices (real in power markets) unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from .._validation import require_non_negative
from ..exceptions import InsufficientDataError, ValidationError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.instruments import PipelineRight, TransmissionRight, TransportDirection
from ..models.schedule import DeliveryPeriod
from ..numerics.daycount import actual_365
from ._dates import settlement_date as _settlement_date
from .spread_option import SpreadOptionRequest, price_spread_option

TransportRight = TransmissionRight | PipelineRight
"""Either transport right — both price through the same engine (Req 24)."""


@dataclass(frozen=True, slots=True)
class TransportPeriodValue:
    """One shared delivery period's transport-right valuation.

    ``payoff`` is the undiscounted per-period intrinsic payoff
    ``Q_delivered · max(P_sink - P_source - tariff, 0)`` (Property 67 form);
    ``intrinsic`` is that payoff discounted at ``discount_factor``; ``extrinsic`` is
    the option time value (0 without vols); ``value = intrinsic + extrinsic``.
    ``direction`` is the committed flow (``None`` for no-flow). ``delta_origin`` and
    ``delta_destination`` are ``∂value/∂P_A`` and ``∂value/∂P_B`` from the holder's
    perspective — always opposite in sign for an active flow.
    """

    period: DeliveryPeriod
    payoff: float
    discount_factor: float
    intrinsic: float
    extrinsic: float
    value: float
    direction: TransportDirection | None
    delta_origin: float
    delta_destination: float


@dataclass(frozen=True, slots=True)
class TransportRightResult:
    """Aggregate transport-right value plus per-period detail (Req 24.1-24.3).

    ``intrinsic``/``extrinsic``/``total`` are the sums over ``per_period`` with
    ``total == intrinsic + extrinsic``. ``delta_origin``/``delta_destination`` are the
    aggregate per-hub deltas (opposite-signed nets), keyed for the portfolio adapter
    by ``origin``/``destination`` commodity ids.
    """

    origin: str
    destination: str
    intrinsic: float
    extrinsic: float
    total: float
    delta_origin: float
    delta_destination: float
    per_period: tuple[TransportPeriodValue, ...]


@dataclass(frozen=True, slots=True)
class _FlowValue:
    """Internal per-period result of a single directional flow (source -> sink).

    ``payoff`` is the undiscounted ``Q_delivered · max(P_sink - P_source - tariff, 0)``;
    ``intrinsic`` is that payoff discounted; ``total`` is the discounted option value
    (or ``intrinsic`` without vols). Deltas are ``∂value/∂P_source`` and
    ``∂value/∂P_sink``.
    """

    payoff: float
    intrinsic: float
    extrinsic: float
    total: float
    delta_source: float
    delta_sink: float


def _prices_by_period(curve: ForwardCurve) -> dict[DeliveryPeriod, float]:
    """One-shot lookup table for a curve's node prices."""
    return {node.period: node.price for node in curve.nodes}


def _shared_periods(
    right: TransportRight,
    curve_a: ForwardCurve,
    curve_b: ForwardCurve,
) -> tuple[DeliveryPeriod, ...]:
    """Right-schedule periods priced by both curves, in chronological order.

    Reuses the curve-intersection convention of :mod:`quantvolt.pricing.spreads`: an
    empty intersection raises :class:`InsufficientDataError` naming both commodities
    and the requested schedule range rather than returning an empty valuation
    (Req 24.5).
    """
    prices_a = _prices_by_period(curve_a)
    prices_b = _prices_by_period(curve_b)
    shared = tuple(
        period for period in right.schedule.periods if period in prices_a and period in prices_b
    )
    if shared:
        return shared
    periods = right.schedule.periods
    raise InsufficientDataError(
        f"origin curve_a (commodity {curve_a.commodity.commodity_id!r}) and destination "
        f"curve_b (commodity {curve_b.commodity.commodity_id!r}) share no delivery period "
        f"in the right's schedule [{periods[0]!r}, {periods[-1]!r}]; nothing to value"
    )


def _flow_value(
    price_source: float,
    price_sink: float,
    tariff: float,
    sigma_source: float | None,
    sigma_sink: float | None,
    correlation: float | None,
    delivered: float,
    discount_factor: float,
    time_to_expiry: float,
) -> _FlowValue:
    """Value one directional flow ``source -> sink`` for a single period.

    Payoff ``max(P_sink - P_source - tariff, 0)``. Intrinsic is that payoff scaled by
    ``delivered`` and discounted. When vols and correlation are supplied (and there is
    quantity to move) the total is the discounted spread-option premium (call on
    ``P_sink - P_source - tariff``) and the extrinsic value is ``total - intrinsic``;
    otherwise the total equals the intrinsic and the extrinsic value is zero.
    Deltas are returned as ``∂value/∂P_source`` and ``∂value/∂P_sink``.
    """
    spread = price_sink - price_source - tariff
    payoff = delivered * max(spread, 0.0)
    intrinsic = discount_factor * payoff
    # Intrinsic-only path (no vols, or nothing to move); the None-checks also let the
    # type checker narrow sigma_source / sigma_sink to float below.
    if sigma_source is None or sigma_sink is None or delivered <= 0.0:
        edge = discount_factor * delivered if spread > 0.0 else 0.0
        return _FlowValue(
            payoff=payoff,
            intrinsic=intrinsic,
            extrinsic=0.0,
            total=intrinsic,
            delta_source=-edge,
            delta_sink=edge,
        )
    assert correlation is not None  # both-or-neither, enforced by _resolve_vols
    option = price_spread_option(
        SpreadOptionRequest(
            forward1=price_sink,
            forward2=price_source,
            strike=tariff,
            sigma1=sigma_sink,
            sigma2=sigma_source,
            correlation=correlation,
            time_to_expiry=time_to_expiry,
            discount_factor=discount_factor,
            notional=delivered,
        )
    )
    return _FlowValue(
        payoff=payoff,
        intrinsic=intrinsic,
        extrinsic=option.premium - intrinsic,
        total=option.premium,
        delta_source=option.delta2,
        delta_sink=option.delta1,
    )


def _resolve_vols(
    vols: tuple[float, float] | None,
    correlation: float | None,
) -> tuple[float | None, float | None]:
    """Validate the both-or-neither vols/correlation contract (Req 24.2).

    Returns ``(sigma_a, sigma_b)`` (both ``None`` for the intrinsic-only path).
    ``vols`` is ``(sigma_origin, sigma_destination)``; both entries must be > 0 and
    ``correlation`` must lie strictly inside ``(-1, 1)`` (checked by the spread-option
    engine when each period is priced).
    """
    if (vols is None) != (correlation is None):
        raise ValidationError(
            "vols and correlation must be supplied together or both omitted "
            f"(got vols={vols!r}, correlation={correlation!r})"
        )
    if vols is None:
        return None, None
    if len(vols) != 2:
        raise ValidationError(
            f"vols must be a (sigma_origin, sigma_destination) pair, got {vols!r}"
        )
    return vols[0], vols[1]


def value_transport_right(
    right: TransportRight,
    curve_a: ForwardCurve,
    curve_b: ForwardCurve,
    discount_curve: DiscountCurve,
    *,
    vols: tuple[float, float] | None = None,
    correlation: float | None = None,
    day_count: Callable[[date, date], float] = actual_365,
    settlement_lag_days: int = 0,
) -> TransportRightResult:
    """Value a transmission or pipeline right (Req 24.1-24.5, Properties 67-68).

    ``curve_a`` is the origin (hub A) forward curve and ``curve_b`` the destination
    (hub B) curve; their commodity ids must match ``right.origin`` / ``right.destination``
    so curves cannot be silently swapped. Valuation covers the shared periods of both
    curves within the right's schedule (Req 24.5). Each period's settlement is its
    ``last_day`` plus ``settlement_lag_days`` (the swap/tolling convention): the
    discount factor is taken there. For the option path, ``time_to_expiry`` is
    ``day_count`` (default actual/365) from ``discount_curve.reference_date`` to the
    period's ``last_day`` (the flow decision horizon) — ``settlement_lag_days`` never
    shifts the volatility horizon, only the discount-factor lookup date.

    Intrinsic value is ``Σ D · Q_delivered · max(P_B - P_A - T_AB, 0)``. Supplying
    ``vols=(sigma_origin, sigma_destination)`` and ``correlation`` (both or neither,
    Req 24.2) adds the spread-option extrinsic value per period. A ``BIDIRECTIONAL``
    right commits each period to the best of A→B (tariff ``tariff``), B→A (tariff
    ``reverse_tariff``, defaulting to ``tariff``) or no-flow, and is subadditive versus
    two one-way rights (Property 68).

    Args:
        right: The transmission or pipeline right to value.
        curve_a: Origin (hub A) forward curve.
        curve_b: Destination (hub B) forward curve.
        discount_curve: Discount curve for settlement dates.
        vols: Optional ``(sigma_origin, sigma_destination)`` pair (both or
            neither with ``correlation``).
        correlation: Optional origin/destination correlation (both or neither
            with ``vols``).
        day_count: Year-fraction convention for the option ``time_to_expiry``,
            taking ``(start, end)`` (default
            :func:`~quantvolt.numerics.daycount.actual_365`).
        settlement_lag_days: Calendar days added to each period's last day to
            get the settlement date used for the discount factor (default 0,
            non-negative). Does NOT affect the option's ``time_to_expiry``,
            which is always ``day_count`` to ``period.last_day``.

    Raises:
        ValidationError: If ``vols``/``correlation`` are not supplied both-or-neither
            (Req 24.2), if the curve commodity ids do not match ``right.origin`` /
            ``right.destination``, if ``settlement_lag_days`` is negative, or if a
            location forward is non-positive on the option path (from the
            spread-option engine).
        InsufficientDataError: If the two curves share no schedule period (Req 24.5).
        MissingTenorError: If the discount curve does not cover a period's settlement.
    """
    if right.origin != curve_a.commodity.commodity_id:
        raise ValidationError(
            f"curve_a commodity {curve_a.commodity.commodity_id!r} does not match "
            f"right.origin {right.origin!r}; pass the origin (hub A) curve as curve_a"
        )
    if right.destination != curve_b.commodity.commodity_id:
        raise ValidationError(
            f"curve_b commodity {curve_b.commodity.commodity_id!r} does not match "
            f"right.destination {right.destination!r}; pass the destination (hub B) curve "
            "as curve_b"
        )
    require_non_negative("settlement_lag_days", settlement_lag_days)
    sigma_a, sigma_b = _resolve_vols(vols, correlation)

    shared = _shared_periods(right, curve_a, curve_b)
    prices_a = _prices_by_period(curve_a)
    prices_b = _prices_by_period(curve_b)

    effective_quantity = (
        right.quantity if right.capacity is None else min(right.quantity, right.capacity)
    )
    delivered = effective_quantity * (1.0 - right.loss)
    tariff_ab = right.tariff
    tariff_ba = right.tariff if right.reverse_tariff is None else right.reverse_tariff

    per_period: list[TransportPeriodValue] = []
    for period in shared:
        price_a = prices_a[period]
        price_b = prices_b[period]
        settlement = _settlement_date(period, settlement_lag_days)
        discount_factor = discount_curve.discount_factor(settlement)
        # Decision horizon (Req 24.2): time_to_expiry is to the period's last delivery
        # day, NOT the (possibly lagged) settlement date used for discounting above.
        time_to_expiry = day_count(discount_curve.reference_date, period.last_day)
        per_period.append(
            _value_period(
                right.direction,
                period,
                price_a,
                price_b,
                tariff_ab,
                tariff_ba,
                sigma_a,
                sigma_b,
                correlation,
                delivered,
                discount_factor,
                time_to_expiry,
            )
        )

    intrinsic = sum(pv.intrinsic for pv in per_period)
    extrinsic = sum(pv.extrinsic for pv in per_period)
    return TransportRightResult(
        origin=right.origin,
        destination=right.destination,
        intrinsic=intrinsic,
        extrinsic=extrinsic,
        total=intrinsic + extrinsic,
        delta_origin=sum(pv.delta_origin for pv in per_period),
        delta_destination=sum(pv.delta_destination for pv in per_period),
        per_period=tuple(per_period),
    )


def _value_period(
    direction: TransportDirection,
    period: DeliveryPeriod,
    price_a: float,
    price_b: float,
    tariff_ab: float,
    tariff_ba: float,
    sigma_a: float | None,
    sigma_b: float | None,
    correlation: float | None,
    delivered: float,
    discount_factor: float,
    time_to_expiry: float,
) -> TransportPeriodValue:
    """Value one shared period for the right's direction, mapping flows to hub A/B deltas.

    A→B is the flow source=A, sink=B (tariff ``tariff_ab``); B→A is source=B, sink=A
    (tariff ``tariff_ba``). A BIDIRECTIONAL right commits the period to whichever of
    the two flows (or no-flow) has the greatest *total* value — the economically best
    choice for the single shared capacity unit.
    """
    a_to_b = _flow_value(
        price_a,
        price_b,
        tariff_ab,
        sigma_a,
        sigma_b,
        correlation,
        delivered,
        discount_factor,
        time_to_expiry,
    )
    if direction is TransportDirection.A_TO_B:
        return _period_from_flow(
            period, a_to_b, TransportDirection.A_TO_B, discount_factor, origin_is_source=True
        )

    b_to_a = _flow_value(
        price_b,
        price_a,
        tariff_ba,
        sigma_b,
        sigma_a,
        correlation,
        delivered,
        discount_factor,
        time_to_expiry,
    )
    if direction is TransportDirection.B_TO_A:
        return _period_from_flow(
            period, b_to_a, TransportDirection.B_TO_A, discount_factor, origin_is_source=False
        )

    # BIDIRECTIONAL: commit the shared capacity to the best of {A→B, B→A, no-flow}.
    if a_to_b.total <= 0.0 and b_to_a.total <= 0.0:
        return TransportPeriodValue(
            period=period,
            payoff=0.0,
            discount_factor=discount_factor,
            intrinsic=0.0,
            extrinsic=0.0,
            value=0.0,
            direction=None,
            delta_origin=0.0,
            delta_destination=0.0,
        )
    if a_to_b.total >= b_to_a.total:
        return _period_from_flow(
            period, a_to_b, TransportDirection.A_TO_B, discount_factor, origin_is_source=True
        )
    return _period_from_flow(
        period, b_to_a, TransportDirection.B_TO_A, discount_factor, origin_is_source=False
    )


def _period_from_flow(
    period: DeliveryPeriod,
    flow: _FlowValue,
    direction: TransportDirection,
    discount_factor: float,
    *,
    origin_is_source: bool,
) -> TransportPeriodValue:
    """Package a directional :class:`_FlowValue` as a :class:`TransportPeriodValue`.

    ``origin_is_source`` maps the flow's source/sink deltas onto hubs A (origin) and
    B (destination): for A→B the origin is the source, for B→A the origin is the sink.
    """
    if origin_is_source:
        delta_origin, delta_destination = flow.delta_source, flow.delta_sink
    else:
        delta_origin, delta_destination = flow.delta_sink, flow.delta_source
    return TransportPeriodValue(
        period=period,
        payoff=flow.payoff,
        discount_factor=discount_factor,
        intrinsic=flow.intrinsic,
        extrinsic=flow.extrinsic,
        value=flow.total,
        direction=direction,
        delta_origin=delta_origin,
        delta_destination=delta_destination,
    )
