"""Credit VaR — counterparty default / rating migration loss distribution.

Credit VaR is a *credit* risk measure, not a mark-to-market market-VaR. It asks: over the
one migration horizon defined by the supplied default/migration probabilities, how large
could the loss from counterparty **default** be, at the 95% / 99% confidence level? The
measure is driven by a one-factor Gaussian copula that links every counterparty's default
event to a single shared systematic *market factor*, so defaults are simulated jointly
with the market rather than independently.

Request surface
---------------
``credit_var(positions, transition, exposures=None, recovery=0.4, seed=0, *,
path_count=100_000, asset_correlation=0.2)``

* ``positions: Sequence[PricedPosition]`` — the priced book. Each position's credit
  counterparty is read from its instrument (``ForwardContract.counterparty``; any
  instrument without that attribute, or with ``counterparty=None``, is treated as
  credit-risk-free). Counterparty-less positions are **never dropped silently**: they are
  collected into ``CreditVaRResult.credit_risk_free`` and excluded from the loss
  simulation.
* ``transition: Mapping[str, ArrayLike]`` — per-counterparty one-period **rating-migration
  row**: the probability distribution over next-period rating states, with the **last**
  state being *default* (absorbing). Each row must have entries in ``[0, 1]`` and sum to
  ``1`` within ``1e-9``; the default-state probability driving loss is the last
  entry. A pure survive/default counterparty is expressed as ``[1 - p, p]``. Every supplied
  row is validated (even for counterparties not present on any position); every
  credit-bearing counterparty (one that appears on a position) must have a row, else a
  :class:`~quantvolt.exceptions.ValidationError` naming the counterparty is raised.
* ``exposures: Mapping[str, float] | None`` — optional per-counterparty exposure. When a
  counterparty is present here, that value is authoritative; otherwise its exposure is
  derived from the book by **close-out netting** — the sum of its positions' NPVs.
  Either way the exposure-at-default is floored at zero (see EAD convention below).
* ``recovery: float | Mapping[str, float]`` — recovery rate in ``[0, 1]``, either one
  scalar applied to every counterparty or a per-counterparty mapping (which must cover
  every credit-bearing counterparty). Loss-given-default is ``LGD = 1 - recovery``.
* ``seed: int`` — RNG seed (``>= 0``). Credit VaR is bit-for-bit reproducible given the
  same inputs and ``seed`` (Req 17.3 / 11.2); the seed is echoed on the result.
* ``path_count: int`` (keyword-only) — number of Monte Carlo paths (``>= 1``).
* ``asset_correlation: float`` (keyword-only) — the copula's systematic factor loading
  ``rho in [0, 1]`` (the "asset correlation"). ``rho = 0`` makes defaults independent;
  larger ``rho`` couples them more tightly through the market factor, fattening the loss
  tail. Expected loss is invariant to ``rho`` (linearity of expectation); only the VaR
  quantiles respond to it.

Joint default / market simulation (one-factor Gaussian copula)
--------------------------------------------------------------
For each path we draw one shared systematic market factor ``M ~ N(0, 1)`` and, per
counterparty, an idiosyncratic ``eps_c ~ N(0, 1)``. The counterparty's latent asset
variable is ``X_c = sqrt(rho)*M + sqrt(1-rho)*eps_c`` (standard normal). Mapping it through
the normal CDF gives a uniform ``U_c = Phi(X_c)``, and the counterparty defaults on that
path iff ``U_c < p_c`` where ``p_c`` is its default probability. This is the standard
copula-to-uniform construction: the marginal default probability is exactly ``p_c`` while
the shared ``M`` makes defaults co-move with the market and with one another.
Using the uniform form (rather than a ``Phi^{-1}(p)`` threshold on ``X``) keeps the
degenerate probabilities ``p = 0`` (never) and ``p = 1`` (always) exact without infinities.

EAD / LGD / loss and sign convention
-------------------------------------
Exposure-at-default is ``EAD_c = max(exposure_c, 0)`` — you can only lose the net positive
value a defaulting counterparty owes you; a net-negative (out-of-the-money) position
carries no credit loss. Loss on a path is the sum over that path's defaulted counterparties
of ``LGD_c * EAD_c``::

    loss = sum_{c defaulted} (1 - recovery_c) * max(exposure_c, 0)

Loss is a non-negative currency amount in the units of the positions' NPVs, so credit VaR
is always ``>= 0`` and ``credit_var_99 >= credit_var_95``. ``credit_var_95`` / ``credit_var_99``
are the 95th / 99th percentiles of the path losses (``numpy.percentile``, default linear
interpolation — matching :mod:`quantvolt.risk.engine`); ``expected_credit_loss`` is the
Monte Carlo sample mean of the path losses. Each counterparty's ``expected_loss`` in the
detail is the closed-form ``p_c * LGD_c * EAD_c`` (exact, no MC noise); the reported
``expected_credit_loss`` converges to their sum as ``path_count`` grows.

Probability measure and limitations
------------------------------------
* **Measure.** The default/migration probabilities are real-world (physical ``P``)
  probabilities; this is an economic-capital / limit measure, not a risk-neutral price.
* **Horizon.** Implicitly the one period over which the supplied probabilities apply
  (e.g. one year); this function does not itself carry calendar time.
* **Default-only loss.** Only migration to the *default* state produces loss (an
  exposure-at-default model). Non-default rating migrations are validated (rows sum to 1)
  but modelled as zero loss; a mark-to-market credit-migration VaR would require
  credit-spread revaluation, which is out of scope here.
* **Netting / collateral.** Exposure is netted per counterparty and floored at zero; no
  collateral, no potential-future-exposure profile, and no wrong-way-risk coupling between
  a counterparty's default and the size of its exposure are modelled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
from scipy.stats import norm  # type: ignore[import-untyped]

from .._validation import require_probability
from ..exceptions import ValidationError
from ._levels import DEFAULT_CONFIDENCES, var_quantiles
from ._levels import validate_confidence_pair as _validate_confidence_pair

if TYPE_CHECKING:
    from ..portfolio.model import PricedPosition

_ROW_SUM_TOL = 1e-9

# DEFAULT_CONFIDENCES (95% / 99%) is a re-exported public name, sourced from the
# shared ``risk/_levels.py`` helper (see its module docstring) rather than
# duplicated here.


@dataclass(frozen=True, slots=True)
class CounterpartyCreditDetail:
    """Per-counterparty credit inputs and closed-form expected loss.

    ``exposure`` is the exposure-at-default ``EAD = max(net exposure, 0)`` actually used in
    the simulation; ``lgd`` is ``1 - recovery``; ``expected_loss`` is the analytic
    ``default_probability * lgd * exposure`` (exact, independent of the Monte Carlo draw).
    """

    counterparty: str
    default_probability: float
    exposure: float
    lgd: float
    expected_loss: float


@dataclass(frozen=True, slots=True)
class CreditVaRResult:
    """Outcome of a :func:`credit_var` computation.

    ``credit_var_95`` / ``credit_var_99`` are the (95% / 99% by default) credit-loss
    quantiles and
    ``expected_credit_loss`` the mean loss (see the module docstring for the exact
    definitions and sign convention); all three are ``>= 0`` and
    ``credit_var_99 >= credit_var_95``. ``per_counterparty`` holds one
    :class:`CounterpartyCreditDetail` per credit-bearing counterparty, ordered by
    counterparty id. ``credit_risk_free`` lists the positions carrying no counterparty,
    reported rather than dropped silently. ``seed``, ``path_count`` and
    ``asset_correlation`` are echoed for reproducibility.
    """

    credit_var_95: float
    credit_var_99: float
    expected_credit_loss: float
    per_counterparty: tuple[CounterpartyCreditDetail, ...]
    credit_risk_free: tuple[PricedPosition, ...]
    seed: int
    path_count: int
    asset_correlation: float


def _default_probability(counterparty: str, row: npt.ArrayLike) -> float:
    """Validate one counterparty's migration row and return its default probability.

    The row must be a 1-D probability vector with entries in ``[0, 1]`` summing to ``1``
    within ``1e-9``; the default-state probability is its last entry. Every
    violation raises a :class:`~quantvolt.exceptions.ValidationError` naming the
    counterparty and the constraint.
    """
    vector = np.asarray(row, dtype=np.float64)
    if vector.ndim != 1 or vector.shape[0] == 0:
        raise ValidationError(
            f"transition row for counterparty {counterparty!r} must be a non-empty 1-D "
            f"probability vector, got shape {vector.shape}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValidationError(
            f"transition row for counterparty {counterparty!r} must be finite, got {vector!r}"
        )
    for index, value in enumerate(vector):
        if not (0.0 <= value <= 1.0):
            raise ValidationError(
                f"transition probability for counterparty {counterparty!r} at index {index} "
                f"must be in [0, 1], got {float(value)!r}"
            )
    row_sum = float(vector.sum())
    if abs(row_sum - 1.0) > _ROW_SUM_TOL:
        raise ValidationError(
            f"transition row for counterparty {counterparty!r} must sum to 1 within "
            f"{_ROW_SUM_TOL}, got sum {row_sum!r}"
        )
    return float(vector[-1])


def _recovery_for(counterparty: str, recovery: float | Mapping[str, float]) -> float:
    """Resolve and validate the recovery rate for one counterparty.

    A scalar ``recovery`` applies to every counterparty; a mapping must contain the
    counterparty. The value is validated to lie in ``[0, 1]`` with a message naming the
    parameter (and counterparty, for a mapping).
    """
    if isinstance(recovery, Mapping):
        if counterparty not in recovery:
            raise ValidationError(
                f"recovery mapping is missing an entry for counterparty {counterparty!r}"
            )
        value = recovery[counterparty]
        require_probability(f"recovery[{counterparty!r}]", value)
        return float(value)
    require_probability("recovery", recovery)
    return float(recovery)


def credit_var(
    positions: Sequence[PricedPosition],
    transition: Mapping[str, npt.ArrayLike],
    exposures: Mapping[str, float] | None = None,
    recovery: float | Mapping[str, float] = 0.4,
    seed: int = 0,
    *,
    path_count: int = 100_000,
    asset_correlation: float = 0.2,
    confidences: Sequence[float] = DEFAULT_CONFIDENCES,
) -> CreditVaRResult:
    """Compute Credit VaR and expected credit loss over the priced book.

    Counterparty-less positions are set aside as credit-risk-free; every credit-bearing
    counterparty's default event is drawn jointly with a shared systematic market factor
    via a one-factor Gaussian copula, and the path loss is the sum of ``LGD * EAD`` over
    that path's defaulted counterparties. See the module docstring for the request surface,
    the copula construction, the EAD/LGD conventions, the sign convention, and the
    limitations.

    Args:
        positions: The priced book; each position's counterparty is read from its
            instrument (``ForwardContract.counterparty``; missing / ``None`` -> risk-free).
        transition: Per-counterparty one-period migration row (last state = default;
            entries in ``[0, 1]``; sums to ``1`` within ``1e-9``).
        exposures: Optional per-counterparty exposure; where absent, exposure is the
            net (summed) NPV of that counterparty's positions. EAD is floored at zero.
        recovery: Recovery rate in ``[0, 1]``, scalar or per-counterparty. ``LGD = 1 - r``.
        seed: RNG seed (``>= 0``); results are reproducible under it.
        path_count: Number of Monte Carlo paths (``>= 1``).
        asset_correlation: Copula systematic-factor loading ``rho in [0, 1]``.
        confidences: The two credit-VaR confidence levels (fractions in ``(0, 1)``,
            matching :mod:`quantvolt.risk.parametric_var`'s convention) reported as
            ``credit_var_95`` / ``credit_var_99``; defaults to ``(0.95, 0.99)``.

    Returns:
        A :class:`CreditVaRResult`.

    Raises:
        ValidationError: If ``seed < 0``, ``path_count < 1``, ``asset_correlation`` or any
            recovery is outside ``[0, 1]``, a transition row has an out-of-range probability
            or does not sum to 1 within ``1e-9`` (message names the counterparty), a
            supplied exposure is non-finite, a credit-bearing counterparty has no
            transition row (message names the counterparty), or
            ``confidences`` does not contain exactly 2 strictly ascending levels in
            ``(0, 1)``.
    """
    if seed < 0:
        raise ValidationError(f"seed must be a non-negative integer, got {seed}")
    if path_count < 1:
        raise ValidationError(f"path_count must be >= 1, got {path_count}")
    require_probability("asset_correlation", asset_correlation)
    var_lo_pct, var_hi_pct = _validate_confidence_pair(
        confidences, low_name="credit_var_95", high_name="credit_var_99"
    )

    # Validate every supplied transition row (Req 17.4: "any supplied" probability), even
    # for counterparties absent from the book; keep the default probabilities for lookup.
    default_probabilities = {
        counterparty: _default_probability(counterparty, row)
        for counterparty, row in transition.items()
    }

    # Partition positions: counterparty-less -> credit-risk-free; the rest netted per
    # counterparty (close-out netting). Deterministic counterparty order (sorted) so the
    # RNG draw and the reported detail are reproducible.
    credit_risk_free: list[PricedPosition] = []
    netted_npv: dict[str, float] = {}
    for position in positions:
        counterparty = getattr(position.position.instrument, "counterparty", None)
        if counterparty is None:
            credit_risk_free.append(position)
        else:
            netted_npv[counterparty] = netted_npv.get(counterparty, 0.0) + position.npv

    counterparties = sorted(netted_npv)
    details: list[CounterpartyCreditDetail] = []
    probs = np.empty(len(counterparties), dtype=np.float64)
    loss_amounts = np.empty(len(counterparties), dtype=np.float64)  # LGD * EAD per counterparty
    for index, counterparty in enumerate(counterparties):
        if counterparty not in default_probabilities:
            raise ValidationError(
                f"no transition/default probability supplied for counterparty {counterparty!r} "
                "(it appears on a position but is absent from `transition`)"
            )
        if exposures is not None and counterparty in exposures:
            raw_exposure = float(exposures[counterparty])
            if not np.isfinite(raw_exposure):
                raise ValidationError(
                    f"exposure for counterparty {counterparty!r} must be finite, "
                    f"got {raw_exposure!r}"
                )
        else:
            raw_exposure = netted_npv[counterparty]
        ead = max(raw_exposure, 0.0)
        prob = default_probabilities[counterparty]
        lgd = 1.0 - _recovery_for(counterparty, recovery)
        probs[index] = prob
        loss_amounts[index] = lgd * ead
        details.append(
            CounterpartyCreditDetail(
                counterparty=counterparty,
                default_probability=prob,
                exposure=ead,
                lgd=lgd,
                expected_loss=prob * lgd * ead,
            )
        )

    if counterparties:
        rng = np.random.default_rng(seed)
        market = rng.standard_normal(path_count)  # shared systematic market factor M
        idiosyncratic = rng.standard_normal((path_count, len(counterparties)))  # eps_c
        rho = float(asset_correlation)
        latent = np.sqrt(rho) * market[:, None] + np.sqrt(1.0 - rho) * idiosyncratic  # X_c
        uniform = np.asarray(norm.cdf(latent), dtype=np.float64)  # U_c = Phi(X_c)
        defaulted = uniform < probs[None, :]
        losses = defaulted @ loss_amounts  # sum over defaulted counterparties per path
    else:
        losses = np.zeros(path_count, dtype=np.float64)

    credit_var_95, credit_var_99 = var_quantiles(losses, var_lo_pct, var_hi_pct)
    return CreditVaRResult(
        credit_var_95=credit_var_95,
        credit_var_99=credit_var_99,
        expected_credit_loss=float(losses.mean()),
        per_counterparty=tuple(details),
        credit_risk_free=tuple(credit_risk_free),
        seed=seed,
        path_count=path_count,
        asset_correlation=float(asset_correlation),
    )
