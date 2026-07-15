"""Futures and forward pricing (Task 25).

Thin orchestration over the value objects (design §2.5): validate at the boundary,
look up the forward price and discount factor, apply the NPV formula

    ``NPV = discount_factor(settlement_date) * (forward_price - contract_price) * notional``

where the settlement date is the last calendar day of the delivery period. Futures
and bilateral forwards price identically here, so both are accepted (Req 3.1-3.4;
Properties 10, 11).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .._validation import require_non_negative, require_positive
from ..exceptions import ExpiredContractError
from ..models.curve import ForwardCurve
from ..models.discount_curve import DiscountCurve
from ..models.instruments import ForwardContract, FuturesContract


@dataclass(frozen=True, slots=True)
class FuturesPricingResult:
    """NPV and forward-price delta of a futures/forward contract."""

    npv: float
    delta: float


def _forward_price_and_discount_factor(
    contract: FuturesContract | ForwardContract,
    forward_curve: ForwardCurve,
    valuation_date: date,
    discount_curve: DiscountCurve,
    settlement_lag_days: int = 0,
) -> tuple[float, float]:
    """Validate then look up ``(forward_price, discount_factor)`` for ``contract``.

    Boundary validation (before any computation, Property 11): a contract whose
    delivery period ended strictly before ``valuation_date`` raises
    :class:`ExpiredContractError` (checked against the delivery period's last day,
    unaffected by ``settlement_lag_days``, which only shifts the discount-factor
    lookup date). A forward curve without the contract's period or a discount curve
    not covering the settlement date raises
    :class:`~quantvolt.exceptions.MissingTenorError`, which propagates (Req 3.4).
    """
    require_non_negative("settlement_lag_days", settlement_lag_days)
    delivery_end = contract.delivery_period.last_day
    if delivery_end < valuation_date:
        raise ExpiredContractError(
            f"contract.delivery_period {contract.delivery_period!r} ended on "
            f"{delivery_end.isoformat()}, strictly before valuation_date "
            f"{valuation_date.isoformat()}; expired contracts cannot be priced"
        )
    settlement_date = delivery_end + timedelta(days=settlement_lag_days)
    forward_price = forward_curve.price_at(contract.delivery_period)
    discount_factor = discount_curve.discount_factor(settlement_date)
    return forward_price, discount_factor


def price_futures(
    contract: FuturesContract | ForwardContract,
    forward_curve: ForwardCurve,
    valuation_date: date,
    discount_curve: DiscountCurve,
    *,
    settlement_lag_days: int = 0,
) -> FuturesPricingResult:
    """Price a futures or forward contract against a forward curve (Req 3.1, 3.2).

    ``NPV = discount_factor(settlement_date) * (forward_price - contract_price) * notional``
    with a positive notional meaning long; ``delta`` is :func:`futures_delta` at the
    default bump. ``settlement_date`` is the delivery period's last day plus
    ``settlement_lag_days`` calendar days.

    Args:
        contract: The futures or forward contract to price.
        forward_curve: Must have a node for ``contract.delivery_period``.
        valuation_date: The date NPV is computed as of.
        discount_curve: Must cover the settlement date.
        settlement_lag_days: Calendar days added to the delivery period's last
            day to get the settlement date used for the discount factor
            (default 0, non-negative).

    Raises:
        ValidationError: If ``settlement_lag_days`` is negative.
        ExpiredContractError: If the delivery period ended strictly before
            ``valuation_date`` (Req 3.3).
        MissingTenorError: If ``forward_curve`` has no node for the delivery period
            or ``discount_curve`` does not cover the settlement date (Req 3.4).
    """
    forward_price, discount_factor = _forward_price_and_discount_factor(
        contract, forward_curve, valuation_date, discount_curve, settlement_lag_days
    )
    npv = discount_factor * (forward_price - contract.contract_price) * contract.notional
    delta = futures_delta(
        contract,
        forward_curve,
        valuation_date,
        discount_curve,
        settlement_lag_days=settlement_lag_days,
    )
    return FuturesPricingResult(npv=npv, delta=delta)


def futures_delta(
    contract: FuturesContract | ForwardContract,
    forward_curve: ForwardCurve,
    valuation_date: date,
    discount_curve: DiscountCurve,
    bump: float = 1.0,
    *,
    settlement_lag_days: int = 0,
) -> float:
    """Delta of the contract NPV to the forward price, by central finite difference.

    Reprices at ``forward_price ± bump`` and returns
    ``(npv_up - npv_down) / (2 * bump)``. The NPV is linear in the forward price,
    so the central difference is exact for any ``bump > 0`` and always equals
    ``discount_factor(settlement_date) * notional``.

    Args:
        contract: The futures or forward contract to price.
        forward_curve: Must have a node for ``contract.delivery_period``.
        valuation_date: The date NPV is computed as of.
        discount_curve: Must cover the settlement date.
        bump: Forward-price bump size, strictly positive.
        settlement_lag_days: Calendar days added to the delivery period's last
            day to get the settlement date, matching :func:`price_futures` so
            price and delta agree (default 0, non-negative).

    Raises:
        ValidationError: If ``bump`` is not strictly positive, or
            ``settlement_lag_days`` is negative.
        ExpiredContractError: If the delivery period ended strictly before
            ``valuation_date`` (Req 3.3).
        MissingTenorError: If ``forward_curve`` has no node for the delivery period
            or ``discount_curve`` does not cover the settlement date (Req 3.4).
    """
    require_positive("bump", bump)
    forward_price, discount_factor = _forward_price_and_discount_factor(
        contract, forward_curve, valuation_date, discount_curve, settlement_lag_days
    )
    npv_up = discount_factor * (forward_price + bump - contract.contract_price) * contract.notional
    npv_down = (
        discount_factor * (forward_price - bump - contract.contract_price) * contract.notional
    )
    return (npv_up - npv_down) / (2.0 * bump)
